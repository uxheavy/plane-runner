# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from copy import deepcopy
import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from django.db import IntegrityError, connection, transaction
from django.db.models import Max
from django.utils import timezone

from plane.agent.validation import (
    MAX_AGENT_COLLECTION_ITEMS,
    PROFILE_MODEL_KEYS,
    PROFILE_RUNTIME_KEYS,
    PROFILE_TOOL_KEYS,
    AgentValueError,
    validate_bounded_json,
    validate_bounded_list,
    validate_bounded_string_list,
    validate_profile_dictionary,
)
from plane.db.models import (
    AgentActor,
    AgentHRProposal,
    AgentRole,
    AssignmentContract,
    AssignmentState,
    InputEventKind,
    InvocationState,
    OutcomeState,
    OutcomeSubmission,
    EvaluatorReview,
    EvaluatorVerdict,
    ProfileVersion,
    RecoveryIntent,
    RunAttempt,
    RunInputEvent,
    RunLineageReason,
    RunState,
    RunTerminalEvent,
    RuntimeInvocation,
    RuntimeInvocationControl,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeUsageObservation,
    HRProposalKind,
    HRProposalState,
    TerminalEventKind,
    TerminalEventSource,
)
from plane.db.models.project import ProjectMember
from plane.db.models.user import User
from plane.db.models.workspace import WorkspaceMember
from plane.utils.permissions.workspace import Admin
from plane.agent.tools.disclosure import compose_tool_catalog

from .errors import AgentDomainError
from .runtime_contract import (
    MAX_BOUNDED_BYTE_COUNT,
    MAX_BOUNDED_PROMPT_BYTES,
    MAX_BOUNDED_TEXT_BYTES,
    MAX_BOUNDED_TOKEN_BYTES,
    MAX_INTEGER,
    PROTOCOL,
    RuntimeContractError,
    canonical_json,
    command_fingerprint,
    contract_digests,
    content_digest,
    promote_legacy_command_fingerprint,
    namespaced_ref,
    snapshot_digest,
    validate_invocation_envelope,
    validate_run_snapshot,
)


class InvalidTransitionError(AgentDomainError):
    """Raised when a record is asked to enter an illegal lifecycle state."""


class RecoveryIntentRequiredError(AgentDomainError):
    """Raised when a terminal or unknown run is reused without explicit lineage."""


class IdempotencyConflictError(AgentDomainError):
    """Raised when an idempotency key is reused for a different command binding."""


class TerminalEventRequiredError(AgentDomainError):
    """Raised when an invocation would finish without a visible Plane event."""


_RUNTIME_LEASE_TTL = timedelta(minutes=5)

MAX_DELEGATION_DEPTH = 8
MAX_DELEGATION_FAN_OUT = 64
MAX_DELEGATION_BUDGET = 2**63 - 1


def _lock_assignment_run(run_id):
    """Lock the lifecycle path in the canonical assignment-then-run order."""

    run_ref = RunAttempt.objects.only("assignment_id").get(pk=run_id)
    assignment = AssignmentContract.objects.select_for_update().get(pk=run_ref.assignment_id)
    run = RunAttempt.objects.select_for_update().get(pk=run_id)
    run.assignment = assignment
    return assignment, run


def lock_invocation_path(invocation_id):
    """Lock assignment, run, and invocation before runtime control or terminal rows.

    Every cross-record runtime path uses this seam.  The acquisition order is
    intentionally structural: AssignmentContract, RunAttempt,
    RuntimeInvocation, then RuntimeInvocationControl or RunTerminalEvent.
    """

    invocation_ref = RuntimeInvocation.objects.only("run_id").filter(invocation_id=str(invocation_id)).first()
    if invocation_ref is None:
        invocation_ref = RuntimeInvocation.objects.only("run_id").get(pk=invocation_id)
    assignment, run = _lock_assignment_run(invocation_ref.run_id)
    invocation = RuntimeInvocation.objects.select_for_update().get(pk=invocation_ref.pk)
    invocation.run = run
    return assignment, run, invocation


def _lock_outcome_path(outcome_id):
    """Lock an outcome after its assignment, run, and current invocation."""

    outcome_ref = OutcomeSubmission.objects.only("run_id").get(pk=outcome_id)
    assignment, run = _lock_assignment_run(outcome_ref.run_id)
    invocation = None
    if run.last_invocation_id:
        invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=run.last_invocation_id)
    outcome = OutcomeSubmission.objects.select_for_update().select_related("run").get(pk=outcome_id)
    outcome.run = run
    return assignment, run, invocation, outcome


def _command_id(value):
    if value is None:
        return None
    return str(getattr(value, "pk", value))


def _command_fingerprint(operation, binding):
    return command_fingerprint(operation, binding)


def _is_legacy_fingerprint(value):
    return isinstance(value, str) and value.startswith("legacy1:")


def _promote_legacy_binding(instance, current_fingerprint):
    if not instance.command_fingerprint.startswith("legacy1:"):
        return
    promoted = promote_legacy_command_fingerprint(instance.command_fingerprint, current_fingerprint)
    updated = instance.__class__.all_objects.filter(
        pk=instance.pk, command_fingerprint=instance.command_fingerprint
    ).update(command_fingerprint=promoted)
    if updated != 1:
        instance.refresh_from_db(fields=["command_fingerprint"])
        if instance.command_fingerprint != promoted:
            raise IdempotencyConflictError("Legacy idempotency binding changed during retry")
    else:
        instance.command_fingerprint = promoted


def _legacy_match(instance, matches, message, current_fingerprint):
    if not _is_legacy_fingerprint(instance.command_fingerprint) or not matches(instance):
        raise IdempotencyConflictError(message)
    _promote_legacy_binding(instance, current_fingerprint)
    return True


_LEGACY_ABSENT = object()


def _legacy_optional(value):
    return _LEGACY_ABSENT if value is None else value


def _legacy_optional_matches(existing, requested):
    existing_value = _legacy_optional(existing)
    requested_value = _legacy_optional(requested)
    if existing_value is _LEGACY_ABSENT or requested_value is _LEGACY_ABSENT:
        return existing_value is requested_value
    return existing_value == requested_value


def _legacy_created_by_matches(existing, created_by):
    return _legacy_optional_matches(existing.created_by_id, _command_id(created_by))


def _legacy_foreign_key_matches(existing_id, requested):
    return _legacy_optional_matches(existing_id, _command_id(requested))


_ASSIGNMENT_TRANSITIONS = {
    AssignmentState.READY: {AssignmentState.ACTIVE, AssignmentState.CANCELLED},
    AssignmentState.ACTIVE: {AssignmentState.COMPLETED, AssignmentState.REVISION, AssignmentState.CANCELLED},
    AssignmentState.REVISION: {AssignmentState.ACTIVE, AssignmentState.CANCELLED},
    AssignmentState.COMPLETED: set(),
    AssignmentState.CANCELLED: set(),
}

_RUN_TRANSITIONS = {
    RunState.QUEUED: {
        RunState.RUNNING,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
        RunState.OUTCOME_UNKNOWN,
    },
    RunState.RUNNING: {
        RunState.WAITING_FOR_INPUT,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
        RunState.OUTCOME_UNKNOWN,
    },
    RunState.WAITING_FOR_INPUT: {
        RunState.RUNNING,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
        RunState.OUTCOME_UNKNOWN,
    },
    RunState.SUCCEEDED: set(),
    RunState.FAILED: set(),
    RunState.BLOCKED: set(),
    RunState.CANCELLED: set(),
    RunState.OUTCOME_UNKNOWN: set(),
}

_INVOCATION_TERMINAL_STATES = {
    InvocationState.SUCCEEDED,
    InvocationState.FAILED,
    InvocationState.BLOCKED,
    InvocationState.CANCELLED,
    InvocationState.OUTCOME_UNKNOWN,
}

_CODE_MODE_USAGE_FIELDS = (
    "inputTokens",
    "outputTokens",
    "durationMs",
    "codeModeInputBytes",
    "codeModeOutputBytes",
    "codeModeCalls",
    "codeModeSpillBytes",
)
_CODE_MODE_RESERVATION_TTL = timedelta(minutes=5)

_RESERVED_PROFILE_KEYS = {
    "allowlist",
    "allowed_operations",
    "allowedOperations",
    "operation_allowlist",
    "operationAllowlist",
    "authorization",
    "permissions",
    "denylist",
}
_CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,219}$")


def _ensure_non_empty(value, field_name, *, limit=MAX_BOUNDED_TEXT_BYTES):
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > limit:
        raise AgentDomainError(f"{field_name} must be a non-empty string within {limit} UTF-8 bytes")
    return value


def _ensure_bounded_text(value, field_name, *, limit=MAX_BOUNDED_TEXT_BYTES):
    if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
        raise AgentDomainError(f"{field_name} must fit within {limit} UTF-8 bytes")
    return value


def _credential_ref(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _CREDENTIAL_REF_PATTERN.fullmatch(value):
        raise AgentDomainError("credential_ref must be an opaque namespaced reference")
    return value


def _as_list(
    value,
    field_name,
    *,
    min_items=0,
    max_items=MAX_AGENT_COLLECTION_ITEMS,
    max_bytes=MAX_BOUNDED_BYTE_COUNT,
    max_string_bytes=MAX_BOUNDED_TEXT_BYTES,
    reject_credentials=False,
):
    try:
        return validate_bounded_list(
            value,
            field_name,
            min_items=min_items,
            max_items=max_items,
            max_bytes=max_bytes,
            max_string_bytes=max_string_bytes,
            reject_credentials=reject_credentials,
        )
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc


def _as_dict(
    value,
    field_name,
    *,
    max_items=MAX_AGENT_COLLECTION_ITEMS,
    max_bytes=MAX_BOUNDED_BYTE_COUNT,
    max_string_bytes=MAX_BOUNDED_TEXT_BYTES,
    reject_credentials=False,
):
    try:
        result = validate_bounded_json(
            value or {},
            field_name,
            max_items=max_items,
            max_bytes=max_bytes,
            max_string_bytes=max_string_bytes,
            reject_credentials=reject_credentials,
        )
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc
    if not isinstance(result, dict):
        raise AgentDomainError(f"{field_name} must be an object")
    return result


def _same_json(left, right):
    try:
        return canonical_json(left) == canonical_json(right)
    except RuntimeContractError:
        return False


def _legacy_json_matches(existing, requested):
    if existing is None or requested is None:
        return _legacy_optional_matches(existing, requested)
    return _same_json(existing, requested)


def _legacy_run_matches(
    existing, assignment, profile, snapshot, lineage_of, lineage_reason, recovery_of, recovery_intent, created_by
):
    return (
        existing.assignment_id == assignment.id
        and existing.profile_version_id == profile.id
        and _legacy_json_matches(existing.snapshot, snapshot)
        and _legacy_foreign_key_matches(existing.lineage_of_id, lineage_of)
        and _legacy_optional_matches(existing.lineage_reason, lineage_reason)
        and _legacy_foreign_key_matches(existing.recovery_of_id, recovery_of)
        and _legacy_optional_matches(existing.recovery_intent, recovery_intent)
        and _legacy_created_by_matches(existing, created_by)
    )


def _legacy_input_matches(existing, run, kind, payload, pending_ref, created_by):
    return (
        existing.run_id == run.id
        and existing.kind == kind
        and _legacy_json_matches(existing.payload, payload)
        and _legacy_optional_matches(existing.pending_input_ref, pending_ref)
        and _legacy_created_by_matches(existing, created_by)
    )


def _legacy_full_usage(value):
    counters = ("inputTokens", "outputTokens", "durationMs")
    if not isinstance(value, dict) or set(value) != set(counters):
        return None
    result = {}
    for field in counters:
        amount = value[field]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            return None
        result[field] = amount
    return result


def _legacy_invocation_usage(existing):
    run = RunAttempt.all_objects.get(pk=existing.run_id)
    invocations = list(RuntimeInvocation.all_objects.filter(run_id=run.id).order_by("ordinal", "id"))
    total = _legacy_full_usage(run.snapshot.get("totalBudget"))
    final = _legacy_full_usage(run.cumulative_usage)
    if total is None or final is None:
        return None
    before = {field: 0 for field in total}
    for index, invocation in enumerate(invocations):
        remaining = invocation.envelope.get("remainingBudget")
        remaining = _legacy_full_usage(remaining)
        if remaining is None:
            return None
        observed_before = {field: total[field] - remaining[field] for field in before}
        if observed_before != before or any(value < 0 for value in observed_before.values()):
            return None
        if index + 1 < len(invocations):
            next_remaining = invocations[index + 1].envelope.get("remainingBudget")
            next_remaining = _legacy_full_usage(next_remaining)
            if next_remaining is None:
                return None
            after = {field: total[field] - next_remaining[field] for field in before}
        else:
            after = final
        delta = {field: after[field] - before[field] for field in before}
        if any(value < 0 for value in delta.values()):
            return None
        if invocation.id == existing.id:
            return delta if _same_json(invocation.usage, delta) else None
        before = after
    return None


def _legacy_trigger_matches(existing, trigger_binding, input_event, input_event_ref):
    persisted = existing.envelope.get("trigger")
    if not isinstance(persisted, dict) or trigger_binding is None:
        return False
    requested = {"kind": trigger_binding} if isinstance(trigger_binding, str) else trigger_binding
    if not isinstance(requested, dict) or not _same_json(requested, persisted):
        return False
    persisted_refs = existing.envelope.get("newContextEventRefs")
    if not isinstance(persisted_refs, list) or len(persisted_refs) > 1:
        return False
    persisted_event_ref = persisted_refs[0] if persisted_refs else None
    requested_event_ref = input_event.event_ref if input_event is not None else input_event_ref
    return _legacy_optional_matches(persisted_event_ref, requested_event_ref)


def _legacy_invocation_matches(
    existing,
    run,
    requested_invocation_ref,
    trigger_binding,
    input_event,
    input_event_ref,
    usage_delta,
    created_by,
):
    persisted_refs = existing.envelope.get("newContextEventRefs")
    if not isinstance(persisted_refs, list) or len(persisted_refs) > 1:
        return False
    persisted_event_ref = persisted_refs[0] if persisted_refs else None
    requested_event_ref = input_event.event_ref if input_event is not None else input_event_ref
    return (
        existing.run_id == run.id
        and _legacy_optional_matches(existing.invocation_id, requested_invocation_ref)
        and _legacy_optional_matches(persisted_event_ref, requested_event_ref)
        and _legacy_trigger_matches(existing, trigger_binding, input_event, input_event_ref)
        and _legacy_json_matches(existing.usage, usage_delta)
        and _legacy_created_by_matches(existing, created_by)
        and _legacy_invocation_usage(existing) is not None
    )


def _legacy_outcome_matches(existing, run, summary, artifacts, evidence, created_by):
    return (
        existing.run_id == run.id
        and existing.summary == summary
        and _legacy_json_matches(existing.artifacts, artifacts)
        and _legacy_json_matches(existing.evidence, evidence)
        and _legacy_created_by_matches(existing, created_by)
    )


def _legacy_terminal_matches(
    existing,
    invocation,
    run,
    kind,
    source,
    product_ref,
    product_event_ref,
    reason,
    cancellation,
    event_key,
):
    return (
        existing.invocation_id == invocation.id
        and existing.run_id == run.id
        and existing.kind == kind
        and existing.source == source
        and existing.product_ref == product_ref
        and existing.product_event_ref == product_event_ref
        and existing.reason == reason
        and _legacy_optional_matches(existing.cancellation_ref, cancellation)
        and _legacy_optional_matches(existing.idempotency_key, event_key)
    )


def _ensure_scope(workspace, project):
    if project is not None and project.workspace_id != workspace.id:
        raise AgentDomainError("Project must belong to the requested workspace")


def _ensure_actor_scope(actor, workspace, project):
    if actor.workspace_id != workspace.id:
        raise AgentDomainError("Agent actor is outside the requested workspace")
    if actor.project_id is not None and actor.project_id != getattr(project, "id", None):
        raise AgentDomainError("Project-scoped Agent actor cannot cross project boundaries")


def _ensure_actor_active(actor):
    if not actor.is_active:
        raise AgentDomainError("Inactive Agent actors cannot receive new work")


def _normalise_ref(value, namespace, field_name):
    if not isinstance(value, str) or not value.startswith(f"{namespace}:"):
        raise AgentDomainError(f"{field_name} is not a valid runtime reference")
    try:
        result = namespaced_ref(namespace, value)
    except RuntimeContractError as exc:
        raise AgentDomainError(f"{field_name} is not a valid runtime reference") from exc
    if not result.startswith(f"{namespace}:"):
        raise AgentDomainError(f"{field_name} is not a valid runtime reference")
    return result


def _normalise_idempotency(value, field_name):
    if value is None:
        return namespaced_ref("idempotency", str(uuid4()))
    value = _ensure_non_empty(value, field_name, limit=MAX_BOUNDED_TOKEN_BYTES)
    return _normalise_ref(value, "idempotency", field_name)


def _target_runtime_ref(value, field_name):
    """Encode an exact caller target into the L1 target-ref namespace."""

    value = _ensure_non_empty(value, field_name, limit=255)
    if value.startswith("target:"):
        return _normalise_ref(value, "target", field_name)
    # Plane target identifiers may contain their own namespace and spaces.  A
    # reversible byte encoding preserves those distinctions without lossy
    # replacement or truncation in the L1 reference.
    encoded = value.encode("utf-8").hex()
    try:
        return namespaced_ref("target", f"literal-{encoded}")
    except RuntimeContractError as exc:
        raise AgentDomainError(f"{field_name} cannot fit the accepted target reference") from exc


def _lock_idempotency_key(key):
    """Serialize all creators using one key before their check-and-insert."""

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


_IDEMPOTENCY_BINDINGS = (
    (AssignmentContract, "delegation_key"),
    (AgentHRProposal, "idempotency_key"),
    (RunAttempt, "creation_idempotency_key"),
    (RunInputEvent, "idempotency_key"),
    (RuntimeInvocation, "idempotency_key"),
    (RuntimeEventIngress, "idempotency_key"),
    (RuntimeExitEvidence, "idempotency_key"),
    (OutcomeSubmission, "submission_idempotency_key"),
    (RunTerminalEvent, "idempotency_key"),
    (EvaluatorReview, "idempotency_key"),
)
_COMPOSITE_COMMAND_BINDINGS = frozenset(
    {
        frozenset({RunAttempt, RuntimeInvocation}),
    }
)


def _assert_idempotency_key_is_unclaimed(key, *, current_model):
    """Keep one caller key from binding to two different Plane commands."""

    for model, field_name in _IDEMPOTENCY_BINDINGS:
        if model is current_model:
            continue
        if frozenset({current_model, model}) in _COMPOSITE_COMMAND_BINDINGS:
            continue
        if model.all_objects.filter(**{field_name: key}).exists():
            raise IdempotencyConflictError("Idempotency key is bound to another Plane command")


def _create_with_conflict_resolution(model, *, fields, key_lookup, alternate_lookup=None, compatible, message):
    """Create under a savepoint and turn uniqueness races into typed results."""

    try:
        with transaction.atomic():
            return model.objects.create(**fields)
    except IntegrityError as exc:
        existing = model.all_objects.filter(**key_lookup).first()
        if existing is None and alternate_lookup is not None:
            existing = model.all_objects.filter(**alternate_lookup).first()
        if existing is None:
            raise
        if compatible(existing):
            return existing
        raise IdempotencyConflictError(message) from exc


def _profile_prompt(profile):
    parts = [part.strip() for part in (profile.persona, profile.instructions) if part and part.strip()]
    if profile.expected_outcomes:
        outcomes = [
            _ensure_non_empty(item, f"expected_outcomes[{index}]")
            for index, item in enumerate(profile.expected_outcomes)
        ]
        parts.append("Expected outcomes:\n" + "\n".join(f"- {item}" for item in outcomes))
    return _ensure_non_empty("\n\n".join(parts), "behavioral_prompt", limit=MAX_BOUNDED_PROMPT_BYTES)


def _snapshot_context(profile):
    contexts = []
    for index, raw in enumerate(profile.context_refs):
        if isinstance(raw, str):
            context_ref = _normalise_ref(raw, "context", f"context_refs[{index}]")
            revision = "1"
            digest = content_digest({"contextRef": context_ref, "source": raw})
        elif isinstance(raw, dict):
            context_ref = _normalise_ref(
                raw.get("contextRef", raw.get("context_ref")), "context", f"context_refs[{index}]"
            )
            revision = _ensure_non_empty(
                str(raw.get("revision", "1")), f"context_refs[{index}].revision", limit=MAX_BOUNDED_TOKEN_BYTES
            )
            digest = raw.get("contentDigest", raw.get("content_digest")) or content_digest(raw)
        else:
            raise AgentDomainError(f"context_refs[{index}] must be a string or object")
        contexts.append({"contextRef": context_ref, "revision": revision, "contentDigest": digest})
    return contexts


def _snapshot_tool_catalog(profile, assignment):
    try:
        return compose_tool_catalog(profile, assignment)
    except ValueError as exc:
        raise AgentDomainError(str(exc)) from exc


def _runtime_policy(profile):
    defaults = _as_dict(profile.runtime_defaults, "runtime_defaults")
    budget = defaults.get("totalBudget", defaults.get("total_budget", {}))
    if not isinstance(budget, dict):
        raise AgentDomainError("runtime_defaults.total_budget must be an object")
    total_budget = {
        "inputTokens": budget.get("inputTokens", budget.get("input_tokens", 100_000)),
        "outputTokens": budget.get("outputTokens", budget.get("output_tokens", 20_000)),
        "durationMs": budget.get("durationMs", budget.get("duration_ms", 3_600_000)),
    }
    for field, value in total_budget.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > MAX_INTEGER:
            raise AgentDomainError(f"runtime_defaults.total_budget.{field} is invalid")
    policy = {
        "model": {
            "provider": _ensure_non_empty(
                str(defaults.get("provider", "plane")), "runtime_defaults.provider", limit=MAX_BOUNDED_TOKEN_BYTES
            ),
            "model": _ensure_non_empty(
                str(defaults.get("model", "default")), "runtime_defaults.model", limit=MAX_BOUNDED_TOKEN_BYTES
            ),
        },
        "adapter": _ensure_non_empty(
            str(defaults.get("adapter", "plane-agent-runtime")),
            "runtime_defaults.adapter",
            limit=MAX_BOUNDED_TOKEN_BYTES,
        ),
        "isolation": "single-invocation",
        "maxEventPayloadBytes": defaults.get("maxEventPayloadBytes", defaults.get("max_event_payload_bytes", 65_536)),
        "maxArtifactBytes": defaults.get(
            "maxArtifactBytes", defaults.get("max_artifact_bytes", MAX_BOUNDED_BYTE_COUNT)
        ),
        "maxReceiptBytes": defaults.get("maxReceiptBytes", defaults.get("max_receipt_bytes", 65_536)),
        "maxCodeModeInputBytes": defaults.get(
            "maxCodeModeInputBytes", defaults.get("max_code_mode_input_bytes", 65_536)
        ),
        "maxCodeModeOutputBytes": defaults.get(
            "maxCodeModeOutputBytes", defaults.get("max_code_mode_output_bytes", 65_536)
        ),
        "maxCodeModeCalls": defaults.get("maxCodeModeCalls", defaults.get("max_code_mode_calls", 64)),
    }
    for field in (
        "maxEventPayloadBytes",
        "maxArtifactBytes",
        "maxReceiptBytes",
        "maxCodeModeInputBytes",
        "maxCodeModeOutputBytes",
        "maxCodeModeCalls",
    ):
        value = policy[field]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_BOUNDED_BYTE_COUNT:
            raise AgentDomainError(f"runtime_defaults.{field} is invalid")
    return policy, total_budget


def _build_snapshot(assignment, profile, run_id, snapshot=None):
    run_ref = _normalise_ref(f"run:{run_id}", "run", "run_id")
    if snapshot is not None:
        if not isinstance(snapshot, dict):
            raise AgentDomainError("snapshot must be an object")
        snapshot = _as_dict(snapshot, "snapshot")
        if snapshot.get("runId") != run_ref:
            raise AgentDomainError("Run snapshot must bind to the new RunAttempt")
        try:
            validate_run_snapshot(snapshot)
        except RuntimeContractError as exc:
            raise AgentDomainError(str(exc)) from exc
        return snapshot

    runtime_policy, total_budget = _runtime_policy(profile)
    assignment_snapshot = {
        "assignmentRef": _normalise_ref(f"assignment:{assignment.id}", "assignment", "assignment_id"),
        "revision": str(assignment.revision),
        "targetRef": _target_runtime_ref(assignment.target_ref, "target_ref"),
        "objective": _ensure_non_empty(assignment.objective, "objective"),
        "acceptanceCriteria": [
            _ensure_non_empty(item, f"acceptance_criteria[{index}]")
            for index, item in enumerate(assignment.acceptance_criteria)
        ],
    }
    content = {
        "protocol": PROTOCOL,
        "workspaceRef": _normalise_ref(f"workspace:{assignment.workspace_id}", "workspace", "workspace_id"),
        "runId": run_ref,
        "assignment": assignment_snapshot,
        "actorRef": _normalise_ref(f"actor:{profile.actor_id}", "actor", "actor_id"),
        "profile": {
            "profileRef": _normalise_ref(f"profile-version:{profile.id}", "profile-version", "profile_version_id"),
            "revision": str(profile.version),
            "role": profile.role,
            "behavioralPrompt": _profile_prompt(profile),
        },
        "context": _snapshot_context(profile),
        "toolCatalog": _snapshot_tool_catalog(profile, assignment),
        "runtimePolicy": runtime_policy,
        "totalBudget": total_budget,
        "contractDigests": contract_digests(),
    }
    snapshot = {**content, "contentDigest": snapshot_digest(content)}
    try:
        validate_run_snapshot(snapshot)
    except RuntimeContractError as exc:
        raise AgentDomainError(str(exc)) from exc
    return snapshot


def _ensure_profile_scope(assignment, profile):
    if profile.actor_id != assignment.assignee_id:
        raise AgentDomainError("Run profile must belong to the assignment's assignee")
    if (profile.workspace_id, profile.project_id) != (assignment.workspace_id, assignment.project_id):
        raise AgentDomainError("Run profile and assignment must share Plane scope")


def _state(value, enum, field_name):
    try:
        return enum(value)
    except ValueError as exc:
        raise AgentDomainError(f"Unknown {field_name}: {value}") from exc


def _transition_assignment_locked(assignment, target, *, updated_by=None):
    target = _state(target, AssignmentState, "assignment state")
    if target not in _ASSIGNMENT_TRANSITIONS[assignment.state]:
        raise InvalidTransitionError(f"Assignment cannot move from {assignment.state} to {target}")
    if target == AssignmentState.REVISION:
        assignment.revision += 1
    assignment.state = target
    if updated_by is not None:
        assignment.updated_by = updated_by
        assignment.save(
            _allow_lifecycle=True,
            created_by_id=assignment.created_by_id,
            disable_auto_set_user=True,
        )
    else:
        assignment.save(_allow_lifecycle=True, created_by_id=assignment.created_by_id)
    return assignment


def _delegation_actor(actor, *, expected_role=AgentRole.DELEGATOR):
    actor = AgentActor.objects.select_related("active_profile").get(pk=actor.pk)
    _ensure_actor_active(actor)
    if actor.active_profile_id is None or actor.active_profile.role != expected_role:
        raise AgentDomainError(f"Only an Agent with the current {expected_role} role may perform this operation")
    return actor


def _bounded_delegation_json(value, field_name):
    try:
        return validate_bounded_json(value or {}, field_name, max_items=64)
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc


def _budget_number(value, *keys):
    if not isinstance(value, dict):
        return None
    for key in keys:
        candidate = value.get(key)
        if candidate is not None:
            if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate < 0:
                raise AgentDomainError(f"budget.{key} must be a non-negative integer")
            if candidate > MAX_DELEGATION_BUDGET:
                raise AgentDomainError(f"budget.{key} exceeds the accepted delegation bound")
            return candidate
    return None


def _scope_is_subset(child, parent):
    """Return whether a child scope is no broader than its parent's scope."""

    if not parent:
        return True
    if not child:
        return True
    for key, value in child.items():
        if key not in parent:
            return False
        parent_value = parent[key]
        if isinstance(parent_value, list):
            if not isinstance(value, list) or not all(item in parent_value for item in value):
                return False
        elif isinstance(parent_value, dict):
            if not isinstance(value, dict) or not _scope_is_subset(value, parent_value):
                return False
        elif value != parent_value:
            return False
    return True


def _delegation_budget_totals(root):
    totals = {}
    rows = AssignmentContract.all_objects.filter(root_assignment=root).values_list("budget", flat=True)
    for budget in rows:
        if not isinstance(budget, dict):
            continue
        for total_key, aliases in {
            "inputTokens": ("inputTokens", "input_tokens"),
            "outputTokens": ("outputTokens", "output_tokens"),
            "durationMs": ("durationMs", "duration_ms"),
            "units": ("units", "total_units"),
        }.items():
            amount = _budget_number(budget, *aliases)
            if amount is not None:
                totals[total_key] = totals.get(total_key, 0) + amount
    return totals


def _ensure_delegation_bounds(parent, *, child_scope, child_budget, depth):
    if depth > MAX_DELEGATION_DEPTH:
        raise AgentDomainError("Delegation maximum depth exceeded")
    root = parent.root_assignment or parent
    root_budget = root.budget or {}
    max_depth = _budget_number(root_budget, "maxDepth", "max_depth")
    if max_depth is not None and depth > max_depth:
        raise AgentDomainError("Delegation maximum depth exceeded")
    max_fan_out = _budget_number(parent.budget, "maxFanOut", "max_fan_out")
    if max_fan_out is None:
        max_fan_out = _budget_number(root_budget, "maxFanOut", "max_fan_out")
    max_fan_out = max_fan_out if max_fan_out is not None else MAX_DELEGATION_FAN_OUT
    if parent.lineage_children.count() >= max_fan_out:
        raise AgentDomainError("Delegation maximum fan-out exceeded")
    if not _scope_is_subset(child_scope, parent.scope):
        raise AgentDomainError("Delegated assignment scope cannot escalate its parent scope")
    totals = _delegation_budget_totals(root)
    for total_key, aliases in {
        "inputTokens": ("inputTokens", "input_tokens"),
        "outputTokens": ("outputTokens", "output_tokens"),
        "durationMs": ("durationMs", "duration_ms"),
        "units": ("units", "total_units"),
    }.items():
        amount = _budget_number(child_budget, *aliases)
        cap_aliases = {
            "inputTokens": ("maxInputTokens", "max_input_tokens"),
            "outputTokens": ("maxOutputTokens", "max_output_tokens"),
            "durationMs": ("maxDurationMs", "max_duration_ms"),
            "units": ("maxUnits", "max_units"),
        }
        cap = _budget_number(root_budget, *cap_aliases[total_key])
        if amount is not None and cap is not None and totals.get(total_key, 0) + amount > cap:
            raise AgentDomainError("Delegated assignment cumulative budget exceeded")


def _delegation_fingerprint(
    parent, assignee, *, target_ref, objective, acceptance_criteria, context_refs, scope, budget, delegated_by
):
    return _command_fingerprint(
        "delegate_assignment",
        {
            "parentAssignmentId": _command_id(parent),
            "assigneeId": _command_id(assignee),
            "targetRef": target_ref,
            "objective": objective,
            "acceptanceCriteria": acceptance_criteria,
            "contextRefs": context_refs,
            "scope": scope,
            "budget": budget,
            "delegatedBy": _command_id(delegated_by),
        },
    )


@transaction.atomic
def create_actor(
    *,
    workspace,
    display_name,
    project=None,
    credential_ref=None,
    principal=None,
    chief_of_staff_for=None,
    created_by=None,
):
    _ensure_scope(workspace, project)
    display_name = _ensure_non_empty(display_name, "display_name", limit=255)
    if principal is None:
        principal = User(
            username=f"plane_agent_{uuid4().hex}",
            email=f"plane-agent-{uuid4().hex}@plane.internal",
            display_name=display_name,
            is_bot=True,
            is_active=True,
            is_password_autoset=True,
        )
        principal.set_unusable_password()
        principal.save(force_insert=True)
        WorkspaceMember.objects.create(workspace=workspace, member=principal, role=15, is_active=True)
        if project is not None:
            ProjectMember.objects.create(project=project, member=principal, role=15, is_active=True)
    else:
        principal = User.objects.get(pk=getattr(principal, "pk", principal))
        if not principal.is_active or not principal.is_bot:
            raise AgentDomainError("AgentActor principal must be an active dedicated Plane Agent identity")
    if chief_of_staff_for is not None:
        chief_of_staff_for = User.objects.get(pk=getattr(chief_of_staff_for, "pk", chief_of_staff_for))
        if chief_of_staff_for.is_bot or not chief_of_staff_for.is_active:
            raise AgentDomainError("Chief-of-staff provisioning requires an active human subject")
        if not WorkspaceMember.objects.filter(
            workspace=workspace,
            member=chief_of_staff_for,
            is_active=True,
        ).exists():
            raise AgentDomainError("Chief-of-staff provisioning requires the human's live workspace membership")
    return AgentActor.objects.create(
        workspace=workspace,
        project=project,
        display_name=display_name,
        principal=principal,
        credential_ref=_credential_ref(credential_ref),
        chief_of_staff_for=chief_of_staff_for,
        created_by=created_by,
    )


@transaction.atomic
def create_profile(
    actor,
    *,
    role,
    instructions,
    version=None,
    display_name=None,
    persona="",
    expected_outcomes=None,
    model_defaults=None,
    runtime_defaults=None,
    context_refs=None,
    tool_presentation=None,
    memory_scopes=None,
    created_by=None,
):
    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    _ensure_actor_active(actor)
    role = _state(role, AgentRole, "Agent role")
    instructions = _ensure_non_empty(instructions, "instructions", limit=MAX_BOUNDED_PROMPT_BYTES)
    display_name = _ensure_non_empty(display_name or actor.display_name, "display_name", limit=255)
    persona = persona or ""
    if not isinstance(persona, str) or len(persona.encode("utf-8")) > MAX_BOUNDED_PROMPT_BYTES:
        raise AgentDomainError(f"persona must fit within {MAX_BOUNDED_PROMPT_BYTES} UTF-8 bytes")
    try:
        model_defaults = validate_profile_dictionary(model_defaults, "model_defaults", allowed_keys=PROFILE_MODEL_KEYS)
        runtime_defaults = validate_profile_dictionary(
            runtime_defaults,
            "runtime_defaults",
            allowed_keys=PROFILE_RUNTIME_KEYS,
        )
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc
    try:
        tool_presentation = validate_bounded_json(
            tool_presentation or {},
            "tool_presentation",
            reject_credentials=True,
            allowed_keys=PROFILE_TOOL_KEYS,
        )
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc
    if _RESERVED_PROFILE_KEYS.intersection(tool_presentation):
        raise AgentDomainError("Profile presentation cannot define authorization or operation allowlists")
    try:
        expected_outcomes = validate_bounded_string_list(expected_outcomes, "expected_outcomes", max_items=32)
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc
    context_refs = _as_list(context_refs, "context_refs", max_items=64, max_string_bytes=MAX_BOUNDED_TOKEN_BYTES)
    memory_scopes = _as_list(memory_scopes, "memory_scopes", max_items=64, max_string_bytes=MAX_BOUNDED_TOKEN_BYTES)
    if version is None:
        latest = (
            ProfileVersion.objects.filter(actor=actor).order_by("-version").values_list("version", flat=True).first()
        )
        version = (latest or 0) + 1
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise AgentDomainError("Profile versions start at 1")
    profile = ProfileVersion.objects.create(
        workspace=actor.workspace,
        project=actor.project,
        actor=actor,
        version=version,
        display_name=display_name,
        role=role,
        persona=persona,
        instructions=instructions,
        expected_outcomes=expected_outcomes,
        model_defaults=model_defaults,
        runtime_defaults=runtime_defaults,
        context_refs=context_refs,
        tool_presentation=tool_presentation,
        memory_scopes=memory_scopes,
        created_by=created_by,
    )
    actor.active_profile = profile
    actor.save(update_fields=["active_profile"])
    return profile


@transaction.atomic
def create_assignment(
    assignee,
    *,
    target_ref,
    objective,
    acceptance_criteria=None,
    context_refs=None,
    project=None,
    lineage_of=None,
    delegated_by=None,
    scope=None,
    budget=None,
    idempotency_key=None,
    created_by=None,
):
    assignee = AgentActor.objects.get(pk=assignee.pk)
    _ensure_actor_active(assignee)
    project = project if project is not None else assignee.project
    _ensure_actor_scope(assignee, assignee.workspace, project)
    target_ref = _ensure_non_empty(target_ref, "target_ref", limit=255)
    objective = _ensure_non_empty(objective, "objective")
    lineage_parent = None
    if lineage_of is not None:
        lineage_parent = AssignmentContract.objects.select_for_update().get(pk=lineage_of.pk)
        lineage_of = lineage_parent
        if lineage_of.workspace_id != assignee.workspace_id or (
            lineage_of.project_id is not None and lineage_of.project_id != (project.id if project else None)
        ):
            raise AgentDomainError("Assignment lineage is outside the Agent's Plane scope")
        if delegated_by is None:
            raise AgentDomainError("Delegated assignments require a dedicated delegator")
        delegated_by = _delegation_actor(delegated_by)
        if delegated_by.id != lineage_parent.assignee_id:
            raise AgentDomainError("Only the parent assignment's delegator may create its child")
    elif delegated_by is not None:
        raise AgentDomainError("A delegator can only be recorded on a child assignment")
    try:
        acceptance_criteria = validate_bounded_string_list(
            acceptance_criteria,
            "acceptance_criteria",
            min_items=1,
            max_items=32,
            max_string_bytes=MAX_BOUNDED_TEXT_BYTES,
        )
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc
    context_refs = _as_list(context_refs, "context_refs", max_items=64, max_string_bytes=MAX_BOUNDED_TOKEN_BYTES)
    scope_value = _bounded_delegation_json(scope, "scope")
    budget_value = _bounded_delegation_json(budget, "budget")
    delegation_key = _normalise_idempotency(idempotency_key, "delegation idempotency_key") if lineage_parent else None
    delegation_fingerprint = None
    root_assignment = None
    delegation_depth = 0
    if lineage_parent is not None:
        if idempotency_key is None:
            raise AgentDomainError("Delegated assignments require an idempotency key")
        if scope is None:
            scope_value = deepcopy(lineage_parent.scope or {})
        if budget is None:
            budget_value = deepcopy(lineage_parent.budget or {})
        delegation_depth = lineage_parent.delegation_depth + 1
        root_assignment = lineage_parent.root_assignment or lineage_parent
        delegation_fingerprint = _delegation_fingerprint(
            lineage_parent,
            assignee,
            target_ref=target_ref,
            objective=objective,
            acceptance_criteria=acceptance_criteria,
            context_refs=context_refs,
            scope=scope_value,
            budget=budget_value,
            delegated_by=delegated_by,
        )
        _lock_idempotency_key(delegation_key)
        existing = AssignmentContract.all_objects.filter(delegation_key=delegation_key).first()
        if existing is not None:
            if existing.delegation_command_fingerprint != delegation_fingerprint:
                raise IdempotencyConflictError("Delegation idempotency key is bound to another Plane command")
            return existing
        _assert_idempotency_key_is_unclaimed(delegation_key, current_model=AssignmentContract)
        if lineage_parent.state == AssignmentState.CANCELLED:
            raise InvalidTransitionError("Cancelled assignments cannot receive delegated work")
        _ensure_delegation_bounds(
            lineage_parent,
            child_scope=scope_value,
            child_budget=budget_value,
            depth=delegation_depth,
        )
    return AssignmentContract.objects.create(
        workspace=assignee.workspace,
        project=project,
        assignee=assignee,
        lineage_of=lineage_of,
        root_assignment=root_assignment,
        delegated_by=delegated_by,
        delegation_key=delegation_key,
        delegation_command_fingerprint=delegation_fingerprint,
        delegation_depth=delegation_depth,
        scope=scope_value,
        budget=budget_value,
        target_ref=target_ref,
        objective=objective,
        acceptance_criteria=acceptance_criteria,
        context_refs=context_refs,
        state=AssignmentState.READY,
        created_by=created_by,
    )


@transaction.atomic
def delegate_assignment(
    parent,
    assignee,
    *,
    target_ref,
    objective,
    acceptance_criteria,
    context_refs=None,
    scope=None,
    budget=None,
    idempotency_key,
    delegated_by=None,
    created_by=None,
):
    """Create one ordinary child assignment with bounded immutable lineage."""

    parent = AssignmentContract.objects.select_for_update().get(pk=parent.pk)
    delegated_by = delegated_by or parent.assignee
    return create_assignment(
        assignee,
        target_ref=target_ref,
        objective=objective,
        acceptance_criteria=acceptance_criteria,
        context_refs=context_refs,
        project=parent.project,
        lineage_of=parent,
        delegated_by=delegated_by,
        scope=scope,
        budget=budget,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )


def _hr_state_fingerprint(*, actor=None, assignment=None, subject_user=None):
    if actor is not None:
        value = {
            "actorId": _command_id(actor),
            "displayName": actor.display_name,
            "isActive": actor.is_active,
            "activeProfileId": _command_id(actor.active_profile_id),
            "principalId": _command_id(actor.principal_id),
        }
    elif assignment is not None:
        value = {
            "assignmentId": _command_id(assignment),
            "assigneeId": _command_id(assignment.assignee_id),
            "state": assignment.state,
            "revision": assignment.revision,
        }
    else:
        value = {"subjectUserId": _command_id(subject_user)}
    return content_digest(value).replace("content:", "command:")


def _ensure_human_workspace_admin(workspace, human):
    if (
        human is None
        or getattr(human, "is_anonymous", False)
        or not getattr(human, "is_active", False)
        or getattr(human, "is_bot", False)
    ):
        raise AgentDomainError("Human HR decisions require an authenticated workspace administrator")
    if not WorkspaceMember.objects.filter(
        workspace=workspace,
        member=human,
        role=Admin,
        is_active=True,
    ).exists():
        raise AgentDomainError("Human HR decisions require a current workspace administrator")


def ensure_human_workspace_admin(workspace, human):
    """Expose the one live human-governance check to non-HTTP lifecycle adapters."""

    _ensure_human_workspace_admin(workspace, human)


def _validate_hr_profile(profile):
    try:
        return validate_bounded_json(profile or {}, "requested_profile", max_items=64, reject_credentials=True)
    except AgentValueError as exc:
        raise AgentDomainError(str(exc)) from exc


@transaction.atomic
def propose_hr_change(
    *,
    workspace,
    proposed_by,
    kind,
    rationale,
    idempotency_key,
    subject_actor=None,
    subject_user=None,
    requested_principal=None,
    target_assignment=None,
    requested_assignee=None,
    requested_role=None,
    requested_display_name="",
    requested_profile=None,
    project=None,
    created_by=None,
):
    """Record a replay-safe HR proposal; no Plane control state changes here."""

    proposed_by = _delegation_actor(proposed_by, expected_role=AgentRole.HR)
    kind = _state(kind, HRProposalKind, "HR proposal kind")
    key = _normalise_idempotency(idempotency_key, "HR proposal idempotency_key")
    rationale = _ensure_non_empty(rationale, "rationale")
    requested_profile = _validate_hr_profile(requested_profile)
    project = project if project is not None else getattr(subject_actor, "project", None)
    if project is not None and project.workspace_id != workspace.id:
        raise AgentDomainError("HR proposal project is outside the workspace")
    if subject_actor is not None:
        subject_actor = AgentActor.objects.select_for_update().get(pk=subject_actor.pk)
        _ensure_actor_scope(subject_actor, workspace, project if subject_actor.project_id else None)
    if target_assignment is not None:
        target_assignment = AssignmentContract.objects.select_for_update().get(pk=target_assignment.pk)
        if (target_assignment.workspace_id, target_assignment.project_id) != (
            workspace.id,
            getattr(project, "id", None),
        ):
            raise AgentDomainError("HR assignment target is outside the proposal scope")
    if requested_assignee is not None:
        requested_assignee = AgentActor.objects.get(pk=requested_assignee.pk)
        _ensure_actor_scope(requested_assignee, workspace, project if requested_assignee.project_id else None)
    if requested_role is not None:
        requested_role = _state(requested_role, AgentRole, "requested Agent role")
    if kind in {HRProposalKind.HIRE, HRProposalKind.CHIEF_OF_STAFF}:
        if subject_actor is not None:
            raise AgentDomainError("Hire proposals cannot already have an Agent subject")
        if not requested_display_name.strip():
            requested_display_name = (
                f"{subject_user.display_name}'s Chief of Staff"
                if kind == HRProposalKind.CHIEF_OF_STAFF and subject_user is not None
                else "Proposed Plane Agent"
            )
        if requested_role is None:
            requested_role = AgentRole.CHIEF_OF_STAFF if kind == HRProposalKind.CHIEF_OF_STAFF else AgentRole.WORKER
        if kind == HRProposalKind.CHIEF_OF_STAFF:
            if subject_user is None:
                raise AgentDomainError("Chief-of-staff provisioning requires a human subject")
            if (
                subject_user.is_bot
                or not subject_user.is_active
                or not WorkspaceMember.objects.filter(
                    workspace=workspace,
                    member=subject_user,
                    is_active=True,
                ).exists()
            ):
                raise AgentDomainError("Chief-of-staff provisioning requires the human's live workspace membership")
            if AgentActor.objects.filter(chief_of_staff_for=subject_user).exists():
                raise AgentDomainError("The human already has a chief-of-staff Agent")
    elif kind in {HRProposalKind.ROLE_CHANGE, HRProposalKind.SUSPEND, HRProposalKind.RETIRE}:
        if subject_actor is None:
            raise AgentDomainError("This HR proposal requires an Agent subject")
        if kind == HRProposalKind.ROLE_CHANGE and requested_role is None:
            raise AgentDomainError("Role changes require a requested role")
    elif kind == HRProposalKind.REASSIGN:
        if target_assignment is None or requested_assignee is None:
            raise AgentDomainError("Reassignment proposals require an assignment and a new assignee")
    if requested_principal is not None and not requested_principal.is_bot:
        raise AgentDomainError("HR proposals cannot attach a human as an Agent principal")
    expected = _hr_state_fingerprint(actor=subject_actor, assignment=target_assignment, subject_user=subject_user)
    binding = {
        "workspaceId": _command_id(workspace),
        "kind": kind,
        "proposedBy": _command_id(proposed_by),
        "subjectActor": _command_id(subject_actor),
        "subjectUser": _command_id(subject_user),
        "requestedPrincipal": _command_id(requested_principal),
        "targetAssignment": _command_id(target_assignment),
        "requestedAssignee": _command_id(requested_assignee),
        "requestedRole": requested_role,
        "requestedDisplayName": requested_display_name,
        "requestedProfile": requested_profile,
        "expectedState": expected,
        "rationale": rationale,
    }
    fingerprint = _command_fingerprint("propose_hr_change", binding)
    _lock_idempotency_key(key)
    existing = AgentHRProposal.all_objects.filter(idempotency_key=key).first()
    if existing is not None:
        if existing.command_fingerprint != fingerprint:
            raise IdempotencyConflictError("HR proposal idempotency key is bound to another Plane command")
        return existing
    _assert_idempotency_key_is_unclaimed(key, current_model=AgentHRProposal)
    return AgentHRProposal.objects.create(
        workspace=workspace,
        project=project,
        kind=kind,
        state=HRProposalState.PROPOSED,
        proposed_by=proposed_by,
        subject_actor=subject_actor,
        subject_user=subject_user,
        requested_principal=requested_principal,
        target_assignment=target_assignment,
        requested_assignee=requested_assignee,
        requested_role=requested_role,
        requested_display_name=requested_display_name,
        requested_profile=requested_profile,
        expected_state_fingerprint=expected,
        rationale=rationale,
        idempotency_key=key,
        command_fingerprint=fingerprint,
        created_by=created_by,
    )


def _hr_profile_fields(proposal):
    profile = dict(proposal.requested_profile or {})
    allowed = {
        "display_name",
        "instructions",
        "persona",
        "expected_outcomes",
        "model_defaults",
        "runtime_defaults",
        "context_refs",
        "tool_presentation",
        "memory_scopes",
        "version",
    }
    if set(profile) - allowed:
        raise AgentDomainError("HR profile proposals may only contain behavioral profile fields")
    profile.setdefault("instructions", f"Operate as the Plane Agent {proposal.requested_role} role.")
    profile.setdefault("display_name", proposal.requested_display_name)
    return profile


@transaction.atomic
def decide_hr_proposal(proposal, *, human_reviewer, approved, decision_note="", idempotency_key=None):
    """Apply or reject one proposal only after a live human admin decision."""

    proposal = AgentHRProposal.objects.select_for_update().get(pk=proposal.pk)
    _ensure_human_workspace_admin(proposal.workspace, human_reviewer)
    if proposal.state != HRProposalState.PROPOSED:
        if idempotency_key is not None and proposal.decision_idempotency_key not in {None, idempotency_key}:
            raise IdempotencyConflictError("HR decision idempotency key is bound to another decision")
        return proposal
    decision_key = _normalise_idempotency(
        idempotency_key or f"idempotency:hr-decision-{proposal.id}",
        "HR decision idempotency_key",
    )
    decision_note = _ensure_bounded_text(decision_note, "review_note")
    if not approved:
        proposal.state = HRProposalState.REJECTED
        proposal.reviewed_by = human_reviewer
        proposal.reviewed_at = timezone.now()
        proposal.review_note = decision_note
        proposal.decision_idempotency_key = decision_key
        proposal.save(_allow_lifecycle=True, created_by_id=proposal.created_by_id)
        return proposal

    if proposal.subject_actor_id:
        current_actor = AgentActor.objects.select_for_update().get(pk=proposal.subject_actor_id)
        current_assignment = None
    elif proposal.target_assignment_id:
        current_actor = None
        current_assignment = AssignmentContract.objects.select_for_update().get(pk=proposal.target_assignment_id)
    else:
        current_actor = None
        current_assignment = None
    if (
        proposal.kind == HRProposalKind.CHIEF_OF_STAFF
        and AgentActor.objects.filter(chief_of_staff_for=proposal.subject_user).exists()
    ):
        raise AgentDomainError("Chief-of-staff proposal is stale because the human already has an Agent")
    if proposal.expected_state_fingerprint != _hr_state_fingerprint(
        actor=current_actor, assignment=current_assignment, subject_user=proposal.subject_user
    ):
        raise AgentDomainError("HR proposal is stale; current Plane control state changed")

    applied_actor = current_actor
    if proposal.kind in {HRProposalKind.HIRE, HRProposalKind.CHIEF_OF_STAFF}:
        applied_actor = create_actor(
            workspace=proposal.workspace,
            project=proposal.project,
            display_name=proposal.requested_display_name,
            principal=proposal.requested_principal,
            chief_of_staff_for=proposal.subject_user if proposal.kind == HRProposalKind.CHIEF_OF_STAFF else None,
            created_by=human_reviewer,
        )
        if applied_actor.chief_of_staff_for_id:
            owner_member = WorkspaceMember.objects.filter(
                workspace=proposal.workspace, member_id=applied_actor.chief_of_staff_for_id, is_active=True
            ).first()
            agent_member = WorkspaceMember.objects.filter(
                workspace=proposal.workspace, member_id=applied_actor.principal_id, is_active=True
            ).first()
            if owner_member is None or agent_member is None:
                raise AgentDomainError("Chief-of-staff provisioning requires the human's live workspace membership")
            agent_member.role = owner_member.role
            agent_member.save(update_fields=["role", "updated_at"])
    elif proposal.kind == HRProposalKind.ROLE_CHANGE:
        if current_actor is None or not current_actor.is_active:
            raise AgentDomainError("Role changes require a current active Agent")
    elif proposal.kind in {HRProposalKind.SUSPEND, HRProposalKind.RETIRE}:
        if current_actor is None:
            raise AgentDomainError("Suspension requires a current Agent")
        current_actor.is_active = False
        current_actor.save(update_fields=["is_active", "updated_at"])
    elif proposal.kind == HRProposalKind.REASSIGN:
        if current_assignment is None or proposal.requested_assignee_id is None:
            raise AgentDomainError("Reassignment proposal is incomplete")
        current_assignment.assignee_id = proposal.requested_assignee_id
        current_assignment.save(_allow_reassignment=True, created_by_id=proposal.created_by_id)

    if proposal.kind in {HRProposalKind.HIRE, HRProposalKind.CHIEF_OF_STAFF, HRProposalKind.ROLE_CHANGE}:
        profile_fields = _hr_profile_fields(proposal)
        create_profile(
            applied_actor,
            role=proposal.requested_role,
            instructions=profile_fields.pop("instructions"),
            created_by=human_reviewer,
            **profile_fields,
        )
        applied_actor.refresh_from_db()
    proposal.state = HRProposalState.APPROVED
    proposal.reviewed_by = human_reviewer
    proposal.reviewed_at = timezone.now()
    proposal.review_note = decision_note
    proposal.decision_idempotency_key = decision_key
    proposal.applied_actor = applied_actor
    proposal.save(_allow_lifecycle=True, created_by_id=proposal.created_by_id)
    return proposal


@transaction.atomic
def propose_chief_of_staff(*, workspace, human, proposed_by, idempotency_key, rationale, created_by=None):
    """Use HR governance for the one least-privileged chief-of-staff relationship."""

    return propose_hr_change(
        workspace=workspace,
        proposed_by=proposed_by,
        kind=HRProposalKind.CHIEF_OF_STAFF,
        subject_user=human,
        requested_role=AgentRole.CHIEF_OF_STAFF,
        requested_display_name=f"{human.display_name}'s Chief of Staff",
        rationale=rationale,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )


@transaction.atomic
def transition_assignment(assignment, target, *, outcome=None):
    locked = AssignmentContract.objects.select_for_update().get(pk=assignment.pk)
    target = _state(target, AssignmentState, "assignment state")
    if target in {AssignmentState.COMPLETED, AssignmentState.REVISION}:
        if outcome is None:
            raise InvalidTransitionError("Assignment review transitions require an outcome submission")
        locked_outcome = OutcomeSubmission.objects.select_for_update().select_related("run").get(pk=outcome.pk)
        if locked_outcome.run.assignment_id != locked.id:
            raise InvalidTransitionError("Assignment review outcome belongs to another assignment")
        expected = OutcomeState.ACCEPTED if target == AssignmentState.COMPLETED else OutcomeState.REVISION_REQUESTED
        if locked_outcome.state != expected:
            raise InvalidTransitionError("Assignment review transition does not match the outcome decision")
    return _transition_assignment_locked(locked, target)


def _cancel_run_without_invocation_locked(run):
    """Cancel a queued run before it ever became a runtime dispatch."""

    if run.state != RunState.QUEUED or run.last_invocation_id or run.invocation_count:
        raise InvalidTransitionError("Only an invocation-free queued run may be cancelled without a terminal event")
    run.state = RunState.CANCELLED
    run.pending_input_ref = None
    run.save(_allow_lifecycle=True, created_by_id=run.created_by_id)
    return run


def _cancel_assignment_run(run):
    """Reconcile one non-terminal run through the canonical runtime control seam."""

    _assignment, locked_run = _lock_assignment_run(run.pk)
    if locked_run.state in {
        RunState.SUCCEEDED,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
        RunState.OUTCOME_UNKNOWN,
    }:
        return locked_run
    if locked_run.last_invocation_id:
        from plane.agent.runtime import request_runtime_cancellation

        invocation = RuntimeInvocation.objects.get(invocation_id=locked_run.last_invocation_id)
        return request_runtime_cancellation(invocation, reason="The assignment tree was cancelled.")
    if locked_run.state in {
        RunState.SUCCEEDED,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
        RunState.OUTCOME_UNKNOWN,
    }:
        return locked_run
    return _cancel_run_without_invocation_locked(locked_run)


@transaction.atomic
def cancel_assignment(assignment, *, operator=None):
    """Cancel an assignment subtree and reconcile every dispatchable descendant."""

    if operator is not None:
        _ensure_human_workspace_admin(assignment.workspace, operator)
    locked = AssignmentContract.objects.select_for_update().get(pk=assignment.pk)
    assignments = [locked]
    frontier = [locked.id]
    while frontier:
        children = list(
            AssignmentContract.objects.select_for_update().filter(lineage_of_id__in=frontier).order_by("id")
        )
        assignments.extend(children)
        frontier = [child.id for child in children]

    for current in assignments:
        if current.state not in {AssignmentState.COMPLETED, AssignmentState.CANCELLED}:
            _transition_assignment_locked(current, AssignmentState.CANCELLED, updated_by=operator)

    for current in assignments:
        runs = RunAttempt.objects.filter(assignment=current).order_by("id")
        for run in runs:
            _cancel_assignment_run(run)
    return AssignmentContract.objects.get(pk=locked.pk)


def _uuid_from_ref(value, field_name):
    try:
        return UUID(str(value).split(":", 1)[1])
    except (IndexError, ValueError, AttributeError) as exc:
        raise AgentDomainError(f"{field_name} must identify a Plane UUID reference") from exc


@transaction.atomic
def create_run(
    assignment,
    profile,
    *,
    snapshot=None,
    idempotency_key=None,
    lineage_of=None,
    lineage_reason=None,
    recovery_of=None,
    recovery_intent=None,
    created_by=None,
):
    locked_assignment = AssignmentContract.objects.select_for_update().get(pk=assignment.pk)
    profile = ProfileVersion.objects.select_related("actor").get(pk=profile.pk)
    _ensure_profile_scope(locked_assignment, profile)
    _ensure_actor_active(profile.actor)
    if locked_assignment.state in {AssignmentState.COMPLETED, AssignmentState.CANCELLED}:
        raise AgentDomainError("Terminal assignments cannot create runs")

    recovery_intent = (
        _state(recovery_intent, RecoveryIntent, "recovery intent") if recovery_intent is not None else None
    )
    lineage_reason = (
        _state(lineage_reason, RunLineageReason, "run lineage reason") if lineage_reason is not None else None
    )
    snapshot_value = _as_dict(snapshot, "snapshot") if snapshot is not None else None
    creation_key = None
    creation_fingerprint = None
    if idempotency_key is not None:
        creation_key = _normalise_idempotency(idempotency_key, "run idempotency_key")
        creation_fingerprint = _command_fingerprint(
            "create_run",
            {
                "assignmentId": _command_id(locked_assignment),
                "profileVersionId": _command_id(profile),
                "snapshot": snapshot_value,
                "lineageOf": _command_id(lineage_of),
                "lineageReason": lineage_reason,
                "recoveryOf": _command_id(recovery_of),
                "recoveryIntent": recovery_intent,
                "createdBy": _command_id(created_by),
            },
        )
        _lock_idempotency_key(creation_key)
        existing = RunAttempt.all_objects.filter(creation_idempotency_key=creation_key).first()
        if existing is not None:
            if existing.command_fingerprint != creation_fingerprint:
                if _is_legacy_fingerprint(existing.command_fingerprint):
                    _legacy_match(
                        existing,
                        lambda row: _legacy_run_matches(
                            row,
                            locked_assignment,
                            profile,
                            snapshot_value,
                            lineage_of,
                            lineage_reason,
                            recovery_of,
                            recovery_intent,
                            created_by,
                        ),
                        "Run idempotency key is bound to another Plane command",
                        creation_fingerprint,
                    )
                else:
                    raise IdempotencyConflictError("Run idempotency key is bound to another Plane command")
            return existing
        _assert_idempotency_key_is_unclaimed(creation_key, current_model=RunAttempt)
    source = None
    if lineage_of is not None:
        source = RunAttempt.objects.select_for_update().get(pk=lineage_of.pk)
        if source.assignment_id != locked_assignment.id:
            raise RecoveryIntentRequiredError("Run lineage must name a run on this assignment")
        if source.state not in {
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
            RunState.OUTCOME_UNKNOWN,
        }:
            raise RecoveryIntentRequiredError("Run lineage must name a terminal or unknown source run")
    if recovery_of is not None:
        recovery_source = RunAttempt.objects.select_for_update().get(pk=recovery_of.pk)
        if recovery_source.assignment_id != locked_assignment.id or recovery_source.state != RunState.OUTCOME_UNKNOWN:
            raise RecoveryIntentRequiredError("Recovery must name an outcome-unknown run on this assignment")
        if source is not None and source.id != recovery_source.id:
            raise RecoveryIntentRequiredError("Run lineage and recovery source must identify the same run")
        source = recovery_source
        if recovery_intent is None:
            raise RecoveryIntentRequiredError("Recovery intent must be explicit")
        lineage_reason = (
            RunLineageReason.RECOVERY if recovery_intent == RecoveryIntent.RECONCILE else RunLineageReason.FRESH_RUN
        )
    if recovery_intent is not None and recovery_of is None:
        raise RecoveryIntentRequiredError("Recovery intent requires an outcome-unknown source run")

    previous_terminal = RunAttempt.objects.filter(
        assignment=locked_assignment,
        state__in=[RunState.FAILED, RunState.BLOCKED, RunState.CANCELLED, RunState.OUTCOME_UNKNOWN],
    ).exists()
    if previous_terminal and source is None:
        raise RecoveryIntentRequiredError("A terminal or unknown run requires explicit new-run lineage")
    if locked_assignment.state == AssignmentState.REVISION:
        if source is None or source.state != RunState.SUCCEEDED or lineage_reason != RunLineageReason.HUMAN_REVISION:
            raise RecoveryIntentRequiredError("A revised assignment requires explicit human-revision lineage")
        if not OutcomeSubmission.objects.filter(run=source, state=OutcomeState.REVISION_REQUESTED).exists():
            raise RecoveryIntentRequiredError("Human-revision lineage must name a returned outcome")
    if source is not None:
        if lineage_reason is None:
            raise RecoveryIntentRequiredError("Run lineage reason must be explicit")
        if (
            source.state in {RunState.FAILED, RunState.BLOCKED, RunState.CANCELLED}
            and lineage_reason != RunLineageReason.FRESH_RUN
        ):
            raise RecoveryIntentRequiredError("Terminal run continuation requires an explicit fresh-run lineage")

    run_id = (
        _uuid_from_ref(snapshot_value["runId"], "snapshot.runId")
        if snapshot_value is not None and snapshot_value.get("runId")
        else uuid4()
    )
    resolved_snapshot = _build_snapshot(locked_assignment, profile, run_id, snapshot=snapshot_value)
    if locked_assignment.state in {AssignmentState.READY, AssignmentState.REVISION}:
        _transition_assignment_locked(locked_assignment, AssignmentState.ACTIVE)
        assignment.state = locked_assignment.state
        assignment.revision = locked_assignment.revision
    run_fields = dict(
        id=run_id,
        workspace=locked_assignment.workspace,
        project=locked_assignment.project,
        assignment=locked_assignment,
        actor=profile.actor,
        profile_version=profile,
        snapshot=resolved_snapshot,
        snapshot_content_digest=resolved_snapshot["contentDigest"],
        state=RunState.QUEUED,
        cumulative_usage={"inputTokens": 0, "outputTokens": 0, "durationMs": 0},
        creation_idempotency_key=creation_key,
        command_fingerprint=creation_fingerprint,
        lineage_of=source,
        lineage_reason=lineage_reason,
        recovery_of=source if recovery_of is not None else None,
        recovery_intent=recovery_intent,
        created_by=created_by,
    )
    if creation_key is None:
        return RunAttempt.objects.create(**run_fields)
    return _create_with_conflict_resolution(
        RunAttempt,
        fields=run_fields,
        key_lookup={"creation_idempotency_key": creation_key},
        compatible=lambda existing: (
            existing.command_fingerprint == creation_fingerprint
            or (
                _is_legacy_fingerprint(existing.command_fingerprint)
                and _legacy_match(
                    existing,
                    lambda row: _legacy_run_matches(
                        row,
                        locked_assignment,
                        profile,
                        snapshot_value,
                        lineage_of,
                        lineage_reason,
                        recovery_of,
                        recovery_intent,
                        created_by,
                    ),
                    "Run idempotency key is bound to another Plane command",
                    creation_fingerprint,
                )
            )
        ),
        message="Run idempotency key is bound to another Plane command",
    )


def _usage(value):
    value = _as_dict(value, "usage")
    allowed = {"inputTokens", "outputTokens", "durationMs"}
    if set(value) - allowed:
        raise AgentDomainError("usage contains fields outside the accepted runtime budget")
    result = {}
    for field, amount in value.items():
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0 or amount > MAX_INTEGER:
            raise AgentDomainError(f"usage.{field} is invalid")
        result[field] = amount
    return result


def _remaining_budget(run):
    budget = run.snapshot["totalBudget"]
    usage = run.cumulative_usage or {}
    return {
        field: max(0, budget[field] - int(usage.get(field, 0)))
        for field in ("inputTokens", "outputTokens", "durationMs")
    }


def _iso_timestamp(value=None):
    return (value or timezone.now()).isoformat().replace("+00:00", "Z")


def _ensure_runtime_control(invocation, *, created_by=None):
    return RuntimeInvocationControl.objects.get_or_create(
        invocation=invocation,
        defaults={
            "workspace": invocation.workspace,
            "project": invocation.project,
            "created_by": created_by or invocation.created_by,
        },
    )[0]


@transaction.atomic
def record_input_event(
    run, *, payload, kind=InputEventKind.HUMAN_INPUT, pending_input_ref=None, idempotency_key=None, created_by=None
):
    assignment, run = _lock_assignment_run(run.pk)
    kind = _state(kind, InputEventKind, "input event kind")
    key = (
        _normalise_idempotency(idempotency_key, "input event idempotency_key") if idempotency_key is not None else None
    )
    payload = _as_dict(payload, "Input event payload")
    pending_ref = (
        _normalise_ref(pending_input_ref, "event", "pending_input_ref") if pending_input_ref is not None else None
    )
    if key is not None:
        _lock_idempotency_key(key)
        existing = RunInputEvent.all_objects.select_for_update().filter(idempotency_key=key).first()
        if existing is not None:
            replay_pending_ref = pending_ref or existing.pending_input_ref
            event_fingerprint = _command_fingerprint(
                "record_input_event",
                {
                    "runId": _command_id(run),
                    "kind": kind,
                    "payload": payload,
                    "pendingInputRef": replay_pending_ref,
                    "createdBy": _command_id(created_by),
                },
            )
            if existing.run_id != run.id or (pending_ref is not None and existing.pending_input_ref != pending_ref):
                raise IdempotencyConflictError("Input event idempotency key is bound to another Plane command")
            if existing.command_fingerprint != event_fingerprint:
                if _is_legacy_fingerprint(existing.command_fingerprint):
                    _legacy_match(
                        existing,
                        lambda row: _legacy_input_matches(row, run, kind, payload, replay_pending_ref, created_by),
                        "Input event idempotency key is bound to another Plane command",
                        event_fingerprint,
                    )
                else:
                    raise IdempotencyConflictError("Input event idempotency key is bound to another Plane command")
            return existing
        _assert_idempotency_key_is_unclaimed(key, current_model=RunInputEvent)
    if pending_ref is None:
        raise AgentDomainError("Input events require the exact pending input reference")
    if assignment.state == AssignmentState.CANCELLED:
        raise InvalidTransitionError("Cancelled assignments cannot receive new input")
    if run.state != RunState.WAITING_FOR_INPUT:
        if RunInputEvent.all_objects.filter(run=run, pending_input_ref=pending_ref).exists():
            raise IdempotencyConflictError("The pending input question has already been answered")
        raise InvalidTransitionError("Input events require a run that is explicitly waiting for input")
    if run.pending_input_ref != pending_ref:
        raise AgentDomainError("Input event does not match the run's pending input reference")
    _ensure_actor_active(run.actor)
    if RunInputEvent.all_objects.filter(run=run, pending_input_ref=pending_ref).exists():
        raise IdempotencyConflictError("The pending input question has already been answered")
    event_fingerprint = (
        _command_fingerprint(
            "record_input_event",
            {
                "runId": _command_id(run),
                "kind": kind,
                "payload": payload,
                "pendingInputRef": pending_ref,
                "createdBy": _command_id(created_by),
            },
        )
        if key is not None
        else None
    )
    max_sequence = RunInputEvent.all_objects.filter(run=run).aggregate(max_sequence=Max("sequence"))["max_sequence"]
    sequence = (max_sequence or 0) + 1
    event_uuid = uuid4()
    event_ref = namespaced_ref("event", str(event_uuid))
    fields = dict(
        workspace=run.workspace,
        project=run.project,
        run=run,
        event_ref=event_ref,
        kind=kind,
        sequence=sequence,
        payload=deepcopy(payload),
        payload_digest=content_digest(payload),
        pending_input_ref=pending_ref,
        is_authoritative=True,
        idempotency_key=key,
        command_fingerprint=event_fingerprint,
        created_by=created_by,
    )
    try:
        if key is None:
            event = RunInputEvent.objects.create(**fields)
        else:
            event = _create_with_conflict_resolution(
                RunInputEvent,
                fields=fields,
                key_lookup={"idempotency_key": key},
                compatible=lambda existing: (
                    existing.run_id == run.id
                    and existing.pending_input_ref == pending_ref
                    and existing.command_fingerprint == event_fingerprint
                ),
                message="Input event idempotency key or pending input reference is already consumed",
            )
    except IntegrityError as exc:
        if RunInputEvent.all_objects.filter(run=run, pending_input_ref=pending_ref).exists():
            raise IdempotencyConflictError("The pending input question has already been answered") from exc
        raise

    invocation = None
    if run.last_invocation_id:
        invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=run.last_invocation_id)
        if invocation.state not in {InvocationState.RUNNING, InvocationState.WAITING_FOR_INPUT}:
            raise InvalidTransitionError("The current invocation cannot continue after human input")
    run.state = RunState.RUNNING
    run.pending_input_ref = None
    run.save(_allow_lifecycle=True, created_by_id=run.created_by_id)
    if invocation is not None and invocation.state == InvocationState.WAITING_FOR_INPUT:
        invocation.state = InvocationState.RUNNING
        invocation.save(_allow_lifecycle=True, created_by_id=invocation.created_by_id)
    return event


def _make_trigger(run, trigger, input_event):
    if trigger is None:
        trigger = "initial" if run.invocation_count == 0 else "continuation"
    if isinstance(trigger, str):
        trigger = {"kind": trigger}
    trigger = _as_dict(trigger, "invocation trigger")
    kind = trigger.get("kind")
    if kind == "initial":
        if run.invocation_count != 0:
            raise AgentDomainError("Only the first invocation may use the initial trigger")
        return {"kind": "initial"}
    if kind not in {"human_input", "recoverable_restart", "continuation"}:
        raise AgentDomainError("Invocation trigger is not supported by the accepted runtime contract")
    if input_event is None:
        raise AgentDomainError("Non-initial invocation requires a Plane-owned input/context event")
    event_ref = input_event.event_ref
    if kind == "human_input":
        return {
            "kind": "human_input",
            "eventRef": event_ref,
            "pendingInputEventRef": input_event.pending_input_ref or event_ref,
            "answerFactDigest": input_event.payload_digest,
        }
    return {"kind": kind, "eventRef": event_ref}


@transaction.atomic
def record_invocation(
    run,
    *,
    invocation_id=None,
    invocation_ref=None,
    idempotency_key=None,
    trigger=None,
    input_event=None,
    input_event_ref=None,
    usage=None,
    created_by=None,
):
    assignment = AssignmentContract.objects.select_for_update().get(pk=run.assignment_id)
    run = RunAttempt.objects.select_for_update().get(pk=run.pk)
    key = _normalise_idempotency(idempotency_key, "invocation idempotency_key")
    requested_invocation_ref = None
    if invocation_id is not None:
        if isinstance(invocation_id, UUID):
            requested_invocation_ref = namespaced_ref("invocation", str(invocation_id))
        else:
            requested_invocation_ref = _normalise_ref(invocation_id, "invocation", "invocation_id")
    elif invocation_ref is not None:
        try:
            requested_invocation_ref = namespaced_ref(
                "invocation",
                str(invocation_ref) if isinstance(invocation_ref, UUID) else str(UUID(str(invocation_ref))),
            )
        except (ValueError, AttributeError) as exc:
            raise AgentDomainError("invocation_ref must be a UUID") from exc
    if input_event is None and input_event_ref is not None:
        input_event_ref = _normalise_ref(input_event_ref, "event", "input_event_ref")
        input_event = RunInputEvent.objects.get(event_ref=input_event_ref)
    if input_event is not None:
        input_event = RunInputEvent.objects.get(pk=input_event.pk)
        if input_event.run_id != run.id:
            raise AgentDomainError("Invocation input event belongs to another run")
        if not input_event.is_authoritative:
            raise AgentDomainError("Non-authoritative legacy input evidence cannot drive an invocation")
    trigger_binding = trigger
    if isinstance(trigger_binding, str):
        trigger_binding = {"kind": trigger_binding}
    elif trigger_binding is not None:
        trigger_binding = _as_dict(trigger_binding, "invocation trigger")
    usage_value = _usage(usage)
    usage_delta = {field: usage_value.get(field, 0) for field in ("inputTokens", "outputTokens", "durationMs")}
    invocation_fingerprint = _command_fingerprint(
        "record_invocation",
        {
            "runId": _command_id(run),
            "invocationId": requested_invocation_ref,
            "trigger": trigger_binding,
            "inputEventRef": input_event.event_ref if input_event is not None else input_event_ref,
            "usage": usage_delta,
            "createdBy": _command_id(created_by),
        },
    )
    _lock_idempotency_key(key)
    existing = RuntimeInvocation.all_objects.filter(idempotency_key=key).first()
    if existing is not None:
        if existing.command_fingerprint != invocation_fingerprint:
            if _is_legacy_fingerprint(existing.command_fingerprint):
                _legacy_match(
                    existing,
                    lambda row: _legacy_invocation_matches(
                        row,
                        run,
                        requested_invocation_ref,
                        trigger_binding,
                        input_event,
                        input_event_ref,
                        usage_delta,
                        created_by,
                    ),
                    "Invocation idempotency key is bound to another Plane command",
                    invocation_fingerprint,
                )
            else:
                raise IdempotencyConflictError("Invocation idempotency key is bound to another Plane command")
        _ensure_runtime_control(existing, created_by=created_by)
        return existing
    _assert_idempotency_key_is_unclaimed(key, current_model=RuntimeInvocation)
    if assignment.state == AssignmentState.CANCELLED:
        raise InvalidTransitionError("Cancelled assignments cannot receive new invocations")
    if run.state not in {RunState.QUEUED, RunState.RUNNING, RunState.WAITING_FOR_INPUT}:
        raise InvalidTransitionError(f"Run {run.id} cannot receive an invocation from {run.state}")
    trigger_value = _make_trigger(run, trigger, input_event)
    invocation_uuid = None
    if requested_invocation_ref is not None:
        try:
            invocation_uuid = UUID(requested_invocation_ref.split(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise AgentDomainError("invocation_id must identify a Plane UUID reference") from exc
    invocation_uuid = invocation_uuid or uuid4()
    invocation_ref_value = namespaced_ref("invocation", str(invocation_uuid))
    conflicting_invocation = RuntimeInvocation.all_objects.filter(invocation_id=invocation_ref_value).first()
    if conflicting_invocation is not None:
        if conflicting_invocation.run_id != run.id:
            raise IdempotencyConflictError("Invocation id is bound to another run")
        if conflicting_invocation.idempotency_key != key:
            raise IdempotencyConflictError("Invocation id is already bound to another idempotency key")
        _ensure_runtime_control(conflicting_invocation, created_by=created_by)
        return conflicting_invocation
    remaining = _remaining_budget(run)
    envelope = {
        "protocol": PROTOCOL,
        "workspaceRef": run.snapshot["workspaceRef"],
        "actorRef": run.snapshot["actorRef"],
        "runId": run.snapshot["runId"],
        "invocationId": invocation_ref_value,
        "runSnapshotDigest": run.snapshot["contentDigest"],
        "trigger": trigger_value,
        "newContextEventRefs": [input_event.event_ref] if input_event is not None else [],
        "remainingBudget": remaining,
        "lease": {
            "leaseId": namespaced_ref("lease", str(uuid4())),
            "expiresAt": _iso_timestamp(timezone.now() + _RUNTIME_LEASE_TTL),
            "renewAfterMs": 30_000,
        },
        "cancellationRef": namespaced_ref("cancellation", str(uuid4())),
        "causationRef": namespaced_ref("causation", str(uuid4())),
        "correlationId": namespaced_ref("correlation", str(run.id)),
        "idempotencyKey": key,
    }
    try:
        validate_run_snapshot(run.snapshot)
    except RuntimeContractError as exc:
        raise AgentDomainError(str(exc)) from exc
    try:
        validate_invocation_envelope(envelope)
    except RuntimeContractError as exc:
        raise AgentDomainError(str(exc)) from exc
    cumulative_usage = deepcopy(run.cumulative_usage or {})
    for field in ("inputTokens", "outputTokens", "durationMs"):
        cumulative_usage[field] = int(cumulative_usage.get(field, 0)) + usage_value.get(field, 0)
        if cumulative_usage[field] > MAX_INTEGER:
            raise AgentDomainError(f"cumulative_usage.{field} exceeds the accepted integer limit")
    invocation_fields = dict(
        workspace=run.workspace,
        project=run.project,
        run=run,
        ordinal=run.invocation_count + 1,
        invocation_id=invocation_ref_value,
        idempotency_key=key,
        command_fingerprint=invocation_fingerprint,
        envelope=envelope,
        usage=usage_delta,
        state=InvocationState.RUNNING,
        created_by=created_by,
    )
    invocation = _create_with_conflict_resolution(
        RuntimeInvocation,
        fields=invocation_fields,
        key_lookup={"idempotency_key": key},
        alternate_lookup={"invocation_id": invocation_ref_value},
        compatible=lambda existing: (
            existing.run_id == run.id
            and existing.invocation_id == invocation_ref_value
            and existing.idempotency_key == key
            and (
                existing.command_fingerprint == invocation_fingerprint
                or (
                    _is_legacy_fingerprint(existing.command_fingerprint)
                    and _legacy_match(
                        existing,
                        lambda row: _legacy_invocation_matches(
                            row,
                            run,
                            requested_invocation_ref,
                            trigger_binding,
                            input_event,
                            input_event_ref,
                            usage_delta,
                            created_by,
                        ),
                        "Invocation idempotency key or invocation id is bound to another Plane command",
                        invocation_fingerprint,
                    )
                )
            )
        ),
        message="Invocation idempotency key or invocation id is bound to another Plane command",
    )
    run.state = RunState.RUNNING
    if input_event is not None:
        run.pending_input_ref = None
    run.invocation_count += 1
    run.last_invocation_id = invocation_ref_value
    run.cumulative_usage = cumulative_usage
    run.save(_allow_lifecycle=True, created_by_id=run.created_by_id)
    _ensure_runtime_control(invocation, created_by=created_by)
    return invocation


@transaction.atomic
def reconcile_runtime_usage(run, invocation, usage=None, *, created_by=None):
    """Persist accepted runtime usage before the supervisor records an outcome."""

    usage_value = _usage(usage)
    normalized = {field: int(usage_value.get(field, 0)) for field in ("inputTokens", "outputTokens", "durationMs")}
    _assignment, locked_run, locked_invocation = lock_invocation_path(invocation.pk)
    if locked_invocation.run_id != locked_run.id:
        raise AgentDomainError("Runtime usage is not bound to its stored run")
    existing = RuntimeUsageObservation.objects.filter(invocation=locked_invocation).first()
    if existing is not None:
        if existing.usage != normalized:
            raise IdempotencyConflictError("Runtime usage is already reconciled with a different value")
        return existing
    cumulative = deepcopy(locked_run.cumulative_usage or {})
    budget = locked_run.snapshot["totalBudget"]
    for field, amount in normalized.items():
        cumulative[field] = int(cumulative.get(field, 0)) + amount
        if cumulative[field] > int(budget[field]):
            raise AgentDomainError(f"Runtime usage {field} exceeds the remaining run budget")
    observation = RuntimeUsageObservation.objects.create(
        workspace=locked_run.workspace,
        project=locked_run.project,
        invocation=locked_invocation,
        run=locked_run,
        actor=locked_run.actor,
        usage=normalized,
        fingerprint=content_digest({"invocationRef": locked_invocation.invocation_id, "usage": normalized}),
        created_by=created_by or locked_invocation.created_by,
    )
    locked_run.cumulative_usage = cumulative
    locked_run.save(_allow_lifecycle=True, update_fields=["cumulative_usage"])
    return observation


def _code_mode_usage_fields(
    *,
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
    input_bytes=0,
    output_bytes=0,
    calls=0,
    spill_bytes=0,
):
    fields = {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "durationMs": duration_ms,
        "codeModeInputBytes": input_bytes,
        "codeModeOutputBytes": output_bytes,
        "codeModeCalls": calls,
        "codeModeSpillBytes": spill_bytes,
    }
    for field, value in fields.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > MAX_INTEGER:
            raise AgentDomainError(f"Code Mode usage {field} is invalid")
    return fields


def _code_mode_reservations(run):
    value = run.code_mode_reserved_usage if isinstance(run.code_mode_reserved_usage, dict) else {}
    reservations = value.get("reservations", [])
    return reservations if isinstance(reservations, list) else []


def _reservation_usage_totals(reservations):
    totals = {field: 0 for field in _CODE_MODE_USAGE_FIELDS}
    for reservation in reservations:
        usage = reservation.get("usage", {}) if isinstance(reservation, dict) else {}
        for field in totals:
            amount = usage.get(field, 0)
            if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
                totals[field] += amount
    return totals


def code_mode_reserved_totals(run):
    """Return the active pre-dispatch Code Mode reservations on a run."""

    return _reservation_usage_totals(_code_mode_reservations(run))


def _code_mode_stored_records(run, invocation):
    _assignment, locked_run, locked_invocation = lock_invocation_path(invocation.pk)
    if locked_invocation.run_id != locked_run.id or locked_invocation.workspace_id != locked_run.workspace_id:
        raise AgentDomainError("Code Mode usage is not bound to the stored run and invocation")
    if locked_run.actor_id != locked_run.profile_version.actor_id:
        raise AgentDomainError("Code Mode usage has an invalid Plane actor binding")
    if locked_invocation.state in _INVOCATION_TERMINAL_STATES:
        raise InvalidTransitionError("A terminal invocation cannot receive Code Mode usage")
    try:
        snapshot = validate_run_snapshot(locked_run.snapshot)
        validate_invocation_envelope(locked_invocation.envelope)
    except RuntimeContractError as exc:
        raise AgentDomainError(f"Code Mode usage contract is invalid: {exc}") from exc
    if locked_run.snapshot_content_digest != snapshot["contentDigest"]:
        raise AgentDomainError("Code Mode usage snapshot digest does not match the stored run")
    return locked_run, locked_invocation, snapshot


def _code_mode_limits(snapshot):
    runtime_policy = snapshot["runtimePolicy"]
    limits = {
        "codeModeInputBytes": runtime_policy.get("maxCodeModeInputBytes"),
        "codeModeOutputBytes": runtime_policy.get("maxCodeModeOutputBytes"),
        "codeModeCalls": runtime_policy.get("maxCodeModeCalls"),
        "codeModeSpillBytes": runtime_policy.get("maxArtifactBytes"),
    }
    if any(value is None for value in limits.values()):
        raise AgentDomainError("Code Mode limits are absent from the immutable run snapshot")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in limits.values()):
        raise AgentDomainError("Code Mode limits are invalid in the immutable run snapshot")
    return limits


def _code_mode_reservation_expired(reservation, now):
    expires_at = reservation.get("expiresAt") if isinstance(reservation, dict) else None
    if not isinstance(expires_at, str):
        return True
    try:
        return datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= now
    except ValueError:
        return True


@transaction.atomic
def reap_code_mode_reservations(run):
    """Drop abandoned reservations while holding the Plane run lifecycle lock."""

    _assignment, locked_run = _lock_assignment_run(run.pk)
    now = timezone.now()
    active = [
        reservation
        for reservation in _code_mode_reservations(locked_run)
        if not _code_mode_reservation_expired(reservation, now)
    ]
    if len(active) != len(_code_mode_reservations(locked_run)):
        locked_run.code_mode_reserved_usage = {"reservations": active}
        locked_run.save(_allow_lifecycle=True, update_fields=["code_mode_reserved_usage"])
    return locked_run


@transaction.atomic
def reserve_code_mode_usage(run, invocation, **usage):
    """Atomically reserve every cumulative Code Mode dimension before dispatch."""

    fields = _code_mode_usage_fields(**usage)
    locked_run, locked_invocation, snapshot = _code_mode_stored_records(run, invocation)
    now = timezone.now()
    reservations = [
        reservation
        for reservation in _code_mode_reservations(locked_run)
        if not _code_mode_reservation_expired(reservation, now)
    ]
    reserved = _reservation_usage_totals(reservations)
    actual = code_mode_usage_totals(locked_run)
    cumulative = locked_run.cumulative_usage or {}
    total_budget = snapshot["totalBudget"]
    for field in ("inputTokens", "outputTokens", "durationMs"):
        available = int(total_budget[field]) - int(cumulative.get(field, 0)) - reserved[field]
        if fields[field] > available:
            raise AgentDomainError(f"Code Mode {field} budget is exhausted")
    limits = _code_mode_limits(snapshot)
    for field, limit in limits.items():
        available = limit - actual[field] - reserved[field]
        if fields[field] > available:
            raise AgentDomainError(f"Code Mode {field} budget is exhausted")
    reservation = {
        "reservationRef": namespaced_ref("reservation", str(uuid4())),
        "invocationRef": locked_invocation.invocation_id,
        "expiresAt": (now + _CODE_MODE_RESERVATION_TTL).isoformat().replace("+00:00", "Z"),
        "usage": fields,
    }
    locked_run.code_mode_reserved_usage = {"reservations": [*reservations, reservation]}
    locked_run.save(_allow_lifecycle=True, update_fields=["code_mode_reserved_usage"])
    return locked_run, reservation


@transaction.atomic
def reconcile_code_mode_usage(run, invocation, reservation, **usage):
    """Commit trusted actual usage and release its pre-dispatch reservation."""

    fields = _code_mode_usage_fields(**usage)
    locked_run, locked_invocation, _snapshot = _code_mode_stored_records(run, invocation)
    reservation_ref = reservation.get("reservationRef") if isinstance(reservation, dict) else None
    reservations = _code_mode_reservations(locked_run)
    matching = next((row for row in reservations if row.get("reservationRef") == reservation_ref), None)
    if matching is None:
        existing = any(
            isinstance(payload, dict) and payload.get("reservationRef") == reservation_ref
            for payload in RunInputEvent.all_objects.filter(
                run_id=locked_run.id,
                kind=InputEventKind.CODE_MODE_USAGE,
            ).values_list("payload", flat=True)
        )
        if existing:
            return locked_run
        raise AgentDomainError("Code Mode reservation is absent or already reaped")
    if matching.get("invocationRef") != locked_invocation.invocation_id:
        raise AgentDomainError("Code Mode reservation is bound to another invocation")
    reserved_usage = matching.get("usage", {})
    if any(fields[field] > int(reserved_usage.get(field, 0)) for field in _CODE_MODE_USAGE_FIELDS):
        raise AgentDomainError("Code Mode actual usage exceeds its reservation")
    remaining = [row for row in reservations if row.get("reservationRef") != reservation_ref]
    cumulative_usage = deepcopy(locked_run.cumulative_usage or {})
    for field in ("inputTokens", "outputTokens", "durationMs"):
        cumulative_usage[field] = int(cumulative_usage.get(field, 0)) + fields[field]
    if any(fields.values()):
        actual = code_mode_usage_totals(locked_run)
        usage_payload = {
            "invocationRef": locked_invocation.invocation_id,
            "reservationRef": reservation_ref,
            "usage": fields,
            "cumulative": {field: actual[field] + fields[field] for field in _CODE_MODE_USAGE_FIELDS},
        }
        max_sequence = RunInputEvent.all_objects.filter(run=locked_run).aggregate(max_sequence=Max("sequence"))[
            "max_sequence"
        ]
        RunInputEvent.objects.create(
            workspace=locked_run.workspace,
            project=locked_run.project,
            run=locked_run,
            event_ref=namespaced_ref("event", str(uuid4())),
            kind=InputEventKind.CODE_MODE_USAGE,
            sequence=(max_sequence or 0) + 1,
            payload=usage_payload,
            payload_digest=content_digest(usage_payload),
            created_by=locked_run.created_by,
        )
    # The integrated lifecycle guard derives cumulative usage from immutable
    # runtime invocations and Code Mode usage events. Append the event before
    # updating the aggregate so the guarded write observes the complete fact
    # set in one transaction.
    locked_run.code_mode_reserved_usage = {"reservations": remaining}
    locked_run.cumulative_usage = cumulative_usage
    locked_run.save(_allow_lifecycle=True, update_fields=["code_mode_reserved_usage", "cumulative_usage"])
    return locked_run


@transaction.atomic
def record_code_mode_usage(run, invocation, **usage):
    """Compatibility wrapper that reserves and reconciles one exact usage delta."""

    locked_run, reservation = reserve_code_mode_usage(run, invocation, **usage)
    return reconcile_code_mode_usage(locked_run, invocation, reservation, **usage)


def code_mode_usage_totals(run):
    """Derive persisted Code Mode counters from immutable Plane usage facts."""

    totals = {
        "inputTokens": 0,
        "outputTokens": 0,
        "durationMs": 0,
        "codeModeInputBytes": 0,
        "codeModeOutputBytes": 0,
        "codeModeCalls": 0,
        "codeModeSpillBytes": 0,
    }
    rows = RunInputEvent.all_objects.filter(run_id=run.pk, kind=InputEventKind.CODE_MODE_USAGE).values_list(
        "payload", flat=True
    )
    for row in rows:
        usage = row.get("usage", {}) if isinstance(row, dict) else {}
        for field in totals:
            amount = usage.get(field, 0)
            if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
                totals[field] += amount
    return totals


@transaction.atomic
def transition_run(run, target, *, pending_input_ref=None):
    target = _state(target, RunState, "run state")
    _assignment, locked = _lock_assignment_run(run.pk)
    if target == RunState.SUCCEEDED:
        raise InvalidTransitionError("Runs succeed only when an outcome is explicitly submitted")
    if target not in _RUN_TRANSITIONS[locked.state]:
        raise InvalidTransitionError(f"Run cannot move from {locked.state} to {target}")
    pending_ref = None
    if target == RunState.WAITING_FOR_INPUT:
        if pending_input_ref is None:
            raise AgentDomainError("Waiting runs require an explicit pending input reference")
        pending_ref = _normalise_ref(pending_input_ref, "event", "pending_input_ref")
    if target in {RunState.FAILED, RunState.BLOCKED, RunState.CANCELLED}:
        if not locked.last_invocation_id:
            raise TerminalEventRequiredError(
                "Terminal run state requires a runtime invocation and visible product event"
            )
        _assignment, invocation_run, invocation = lock_invocation_path(locked.last_invocation_id)
        if invocation_run.id != locked.id:
            raise AgentDomainError("The run's current invocation is bound to another run")
        kind = {
            RunState.FAILED: TerminalEventKind.RUN_FAILURE,
            RunState.BLOCKED: TerminalEventKind.RUN_BLOCKER,
            RunState.CANCELLED: TerminalEventKind.RUN_CANCELLATION,
        }[target]
        _create_terminal_event_locked(
            invocation,
            locked,
            kind=kind,
            source=TerminalEventSource.SUPERVISOR,
            product_ref=namespaced_ref("product-event", f"terminal-{invocation.id}"),
            reason=f"Run transitioned to {target}",
            idempotency_key=namespaced_ref("idempotency", f"terminal-{invocation.id}-{target}"),
        )
        return locked
    locked.state = target
    locked.pending_input_ref = pending_ref if target == RunState.WAITING_FOR_INPUT else None
    locked.save(_allow_lifecycle=True, created_by_id=locked.created_by_id)
    if locked.last_invocation_id and target == RunState.WAITING_FOR_INPUT:
        invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=locked.last_invocation_id)
        if invocation.state == InvocationState.RUNNING:
            invocation.state = InvocationState.WAITING_FOR_INPUT
            invocation.save(_allow_lifecycle=True, created_by_id=invocation.created_by_id)
    return locked


def _terminal_state(kind):
    return {
        TerminalEventKind.RUN_FAILURE: (InvocationState.FAILED, RunState.FAILED),
        TerminalEventKind.RUN_BLOCKER: (InvocationState.BLOCKED, RunState.BLOCKED),
        TerminalEventKind.RUN_CANCELLATION: (InvocationState.CANCELLED, RunState.CANCELLED),
        TerminalEventKind.OUTCOME_SUBMISSION: (InvocationState.SUCCEEDED, RunState.SUCCEEDED),
    }[kind]


def _create_terminal_event_locked(
    invocation,
    run,
    *,
    kind,
    source,
    product_ref,
    reason,
    idempotency_key,
    cancellation_ref=None,
):
    event_key = _normalise_idempotency(idempotency_key, "terminal event idempotency_key")
    _lock_idempotency_key(event_key)
    invocation_state, run_state = _terminal_state(kind)
    existing = RunTerminalEvent.all_objects.select_for_update().filter(invocation=invocation).first()
    if kind in {
        TerminalEventKind.RUN_FAILURE,
        TerminalEventKind.RUN_BLOCKER,
        TerminalEventKind.RUN_CANCELLATION,
    }:
        event_ref = product_ref
    elif existing is not None:
        event_ref = existing.product_event_ref
    else:
        event_ref = namespaced_ref("product-event", str(uuid4()))
    cancellation = (
        _normalise_ref(cancellation_ref, "cancellation", "cancellation_ref")
        if cancellation_ref is not None
        else namespaced_ref("cancellation", f"terminal-{invocation.id}")
        if kind == TerminalEventKind.RUN_CANCELLATION
        else None
    )
    reason_value = _ensure_non_empty(reason, "terminal reason") if reason else ""
    terminal_fingerprint = _command_fingerprint(
        "record_terminal_event",
        {
            "invocationId": _command_id(invocation),
            "runId": _command_id(run),
            "kind": kind,
            "source": source,
            "productRef": product_ref,
            "productEventRef": event_ref,
            "idempotencyKey": event_key,
            "reason": reason_value,
            "cancellationRef": cancellation,
        },
    )
    if existing is not None:
        if existing.command_fingerprint != terminal_fingerprint:
            if _is_legacy_fingerprint(existing.command_fingerprint):
                _legacy_match(
                    existing,
                    lambda row: _legacy_terminal_matches(
                        row,
                        invocation,
                        run,
                        kind,
                        source,
                        product_ref,
                        event_ref,
                        reason_value,
                        cancellation,
                        event_key,
                    ),
                    "Terminal event is bound to another Plane command",
                    terminal_fingerprint,
                )
            else:
                raise IdempotencyConflictError("Terminal event is bound to another Plane command")
        return existing
    conflicting = RunTerminalEvent.all_objects.filter(idempotency_key=event_key).first()
    if conflicting is not None:
        if conflicting.command_fingerprint != terminal_fingerprint:
            if _is_legacy_fingerprint(conflicting.command_fingerprint):
                _legacy_match(
                    conflicting,
                    lambda row: _legacy_terminal_matches(
                        row,
                        invocation,
                        run,
                        kind,
                        source,
                        product_ref,
                        event_ref,
                        reason_value,
                        cancellation,
                        event_key,
                    ),
                    "Terminal event idempotency key is bound to another Plane command",
                    terminal_fingerprint,
                )
            else:
                raise IdempotencyConflictError("Terminal event idempotency key is bound to another Plane command")
        return conflicting
    _assert_idempotency_key_is_unclaimed(event_key, current_model=RunTerminalEvent)
    invocation.state = invocation_state
    invocation.save(_allow_lifecycle=True, created_by_id=invocation.created_by_id)
    run.state = run_state
    run.pending_input_ref = None
    run.save(_allow_lifecycle=True, created_by_id=run.created_by_id)
    event_fields = dict(
        workspace=run.workspace,
        project=run.project,
        invocation=invocation,
        run=run,
        kind=kind,
        source=source,
        product_ref=product_ref,
        product_event_ref=event_ref,
        idempotency_key=event_key,
        command_fingerprint=terminal_fingerprint,
        reason=reason_value,
        cancellation_ref=cancellation,
        visible=True,
    )
    return _create_with_conflict_resolution(
        RunTerminalEvent,
        fields=event_fields,
        key_lookup={"idempotency_key": event_key},
        alternate_lookup={"product_event_ref": event_ref},
        compatible=lambda existing: existing.invocation_id == invocation.id
        and (
            existing.command_fingerprint == terminal_fingerprint
            or (
                _is_legacy_fingerprint(existing.command_fingerprint)
                and _legacy_match(
                    existing,
                    lambda row: _legacy_terminal_matches(
                        row,
                        invocation,
                        run,
                        kind,
                        source,
                        product_ref,
                        event_ref,
                        reason_value,
                        cancellation,
                        event_key,
                    ),
                    "Terminal event idempotency key or product event is bound to another invocation",
                    terminal_fingerprint,
                )
            )
        ),
        message="Terminal event idempotency key or product event is bound to another invocation",
    )


def _replay_outcome_terminal_locked(run, outcome):
    if not run.last_invocation_id:
        raise TerminalEventRequiredError("Outcome submission requires a runtime invocation")
    invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=run.last_invocation_id)
    terminal = RunTerminalEvent.all_objects.filter(invocation=invocation).first()
    if terminal is None:
        raise TerminalEventRequiredError("Outcome submission is missing its terminal product event")
    return _create_terminal_event_locked(
        invocation,
        run,
        kind=TerminalEventKind.OUTCOME_SUBMISSION,
        source=TerminalEventSource.RUNTIME,
        product_ref=namespaced_ref("outcome-submission", str(outcome.id)),
        reason="",
        idempotency_key=namespaced_ref("idempotency", f"outcome-{outcome.id}"),
    )


@transaction.atomic
def finalize_invocation(invocation, *, kind, reason="", source=TerminalEventSource.SUPERVISOR, idempotency_key=None):
    _assignment, run, invocation = lock_invocation_path(invocation.pk)
    kind = _state(kind, TerminalEventKind, "terminal event kind")
    source = _state(source, TerminalEventSource, "terminal event source")
    if kind == TerminalEventKind.OUTCOME_SUBMISSION:
        raise TerminalEventRequiredError("Outcome terminal events must be created with an OutcomeSubmission")
    if invocation.state in _INVOCATION_TERMINAL_STATES and not hasattr(invocation, "terminal_event"):
        raise TerminalEventRequiredError("Terminal invocation state has no visible Plane terminal event")
    product_event_ref = namespaced_ref("product-event", f"terminal-{invocation.id}-{kind}")
    event_idempotency_key = idempotency_key or namespaced_ref("idempotency", f"terminal-{invocation.id}-{kind}")
    return _create_terminal_event_locked(
        invocation,
        run,
        kind=kind,
        source=source,
        product_ref=product_event_ref,
        reason=reason,
        idempotency_key=event_idempotency_key,
    )


@transaction.atomic
def propose_outcome(run, *, summary, artifacts=None, evidence=None, idempotency_key=None, created_by=None):
    summary = _ensure_non_empty(summary, "summary")
    artifacts_value = _as_list(artifacts, "artifacts", max_items=64)
    evidence_value = _as_list(evidence, "evidence", max_items=64)
    _assignment, run = _lock_assignment_run(run.pk)
    key = _normalise_idempotency(idempotency_key, "outcome idempotency_key") if idempotency_key is not None else None
    outcome_fingerprint = None
    if key is not None:
        outcome_fingerprint = _command_fingerprint(
            "propose_outcome",
            {
                "runId": _command_id(run),
                "summary": summary,
                "artifacts": artifacts_value,
                "evidence": evidence_value,
                "createdBy": _command_id(created_by),
            },
        )
        _lock_idempotency_key(key)
        existing = OutcomeSubmission.all_objects.filter(submission_idempotency_key=key).first()
        if existing is not None:
            if existing.command_fingerprint != outcome_fingerprint:
                if _is_legacy_fingerprint(existing.command_fingerprint):
                    _legacy_match(
                        existing,
                        lambda row: _legacy_outcome_matches(
                            row, run, summary, artifacts_value, evidence_value, created_by
                        ),
                        "Outcome idempotency key is bound to another Plane command",
                        outcome_fingerprint,
                    )
                else:
                    raise IdempotencyConflictError("Outcome idempotency key is bound to another Plane command")
            _replay_outcome_terminal_locked(run, existing)
            return existing
        _assert_idempotency_key_is_unclaimed(key, current_model=OutcomeSubmission)
    if run.state not in {RunState.RUNNING, RunState.WAITING_FOR_INPUT}:
        raise InvalidTransitionError(f"Run cannot submit an outcome from {run.state}")
    if not run.last_invocation_id:
        raise TerminalEventRequiredError("Outcome submission requires a runtime invocation")
    invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=run.last_invocation_id)
    if invocation.run_id != run.id or invocation.state not in {
        InvocationState.RUNNING,
        InvocationState.WAITING_FOR_INPUT,
    }:
        raise InvalidTransitionError("The current invocation cannot submit an outcome")
    outcome_fields = dict(
        workspace=run.workspace,
        project=run.project,
        run=run,
        summary=summary,
        artifacts=artifacts_value,
        evidence=evidence_value,
        state=OutcomeState.PROPOSED,
        submission_idempotency_key=key,
        command_fingerprint=outcome_fingerprint,
        created_by=created_by,
    )
    if key is None:
        outcome = OutcomeSubmission.objects.create(**outcome_fields)
    else:
        outcome = _create_with_conflict_resolution(
            OutcomeSubmission,
            fields=outcome_fields,
            key_lookup={"submission_idempotency_key": key},
            alternate_lookup={"run_id": run.id},
            compatible=lambda existing: (
                existing.run_id == run.id
                and existing.submission_idempotency_key == key
                and (
                    existing.command_fingerprint == outcome_fingerprint
                    or (
                        _is_legacy_fingerprint(existing.command_fingerprint)
                        and _legacy_match(
                            existing,
                            lambda row: _legacy_outcome_matches(
                                row, run, summary, artifacts_value, evidence_value, created_by
                            ),
                            "Outcome idempotency key or run is bound to another Plane command",
                            outcome_fingerprint,
                        )
                    )
                )
            ),
            message="Outcome idempotency key or run is bound to another Plane command",
        )
    return_value = _create_terminal_event_locked(
        invocation,
        run,
        kind=TerminalEventKind.OUTCOME_SUBMISSION,
        source=TerminalEventSource.RUNTIME,
        product_ref=namespaced_ref("outcome-submission", str(outcome.id)),
        reason="",
        idempotency_key=namespaced_ref("idempotency", f"outcome-{outcome.id}"),
    )
    if return_value.kind != TerminalEventKind.OUTCOME_SUBMISSION:
        raise TerminalEventRequiredError("Outcome submission did not create its terminal product event")
    return outcome


@transaction.atomic
def review_outcome(
    outcome,
    *,
    evaluator,
    feedback="",
    criteria=None,
    verdict=EvaluatorVerdict.ACCEPT,
    provenance=None,
    idempotency_key=None,
):
    feedback = _ensure_bounded_text(feedback, "evaluator_feedback")
    _assignment, _run, _invocation, locked = _lock_outcome_path(outcome.pk)
    verdict = _state(verdict, EvaluatorVerdict, "evaluator verdict")
    if locked.state != OutcomeState.PROPOSED:
        existing_review = EvaluatorReview.objects.filter(outcome=locked).first()
        if existing_review is not None and existing_review.verdict == verdict:
            return locked
        raise InvalidTransitionError(f"Outcome cannot be evaluated from {locked.state}")
    evaluator = AgentActor.objects.select_related("active_profile").get(pk=evaluator.pk)
    _ensure_actor_active(evaluator)
    if evaluator.active_profile_id is None or evaluator.active_profile.role != AgentRole.EVALUATOR:
        raise AgentDomainError("Only an Agent with the current evaluator role may review outcomes")
    if evaluator.id == locked.run.actor_id:
        raise AgentDomainError("Independent evaluator review is required; an Agent cannot evaluate its own outcome")
    if evaluator.workspace_id != locked.workspace_id or (
        evaluator.project_id is not None and evaluator.project_id != locked.project_id
    ):
        raise AgentDomainError("Evaluator is outside the outcome's Plane scope")
    criteria_value = _as_list(
        criteria if criteria is not None else [{"criterion": "outcome evidence", "result": "reviewed"}],
        "evaluator_criteria",
        max_items=32,
    )
    provenance_value = _as_dict(provenance, "evaluator_provenance") if provenance is not None else {}
    provenance_value.update(
        {
            "outcomeRef": namespaced_ref("outcome-submission", str(locked.id)),
            "runRef": namespaced_ref("run", str(locked.run_id)),
            "evaluatorActorRef": namespaced_ref("agent-actor", str(evaluator.id)),
            "evaluatorProfileRef": namespaced_ref("profile-version", str(evaluator.active_profile_id)),
        }
    )
    recommendation = feedback or "Evaluator review recorded; human decision remains required."
    review_key = _normalise_idempotency(
        idempotency_key or f"idempotency:evaluator-{locked.id}",
        "evaluator review idempotency_key",
    )
    review_fingerprint = _command_fingerprint(
        "review_outcome",
        {
            "outcomeId": _command_id(locked),
            "evaluatorId": _command_id(evaluator),
            "profileVersionId": _command_id(evaluator.active_profile),
            "criteria": criteria_value,
            "verdict": verdict,
            "recommendation": recommendation,
            "provenance": provenance_value,
        },
    )
    _lock_idempotency_key(review_key)
    existing = EvaluatorReview.all_objects.filter(idempotency_key=review_key).first()
    if existing is not None:
        if existing.command_fingerprint != review_fingerprint or existing.outcome_id != locked.id:
            raise IdempotencyConflictError("Evaluator review idempotency key is bound to another Plane command")
        return locked
    _assert_idempotency_key_is_unclaimed(review_key, current_model=EvaluatorReview)
    existing = EvaluatorReview.all_objects.filter(outcome=locked).first()
    if existing is not None:
        if existing.command_fingerprint != review_fingerprint:
            raise IdempotencyConflictError("Outcome already has a different evaluator recommendation")
        return locked
    EvaluatorReview.objects.create(
        workspace=locked.workspace,
        project=locked.project,
        outcome=locked,
        run=locked.run,
        evaluator=evaluator,
        evaluator_profile=evaluator.active_profile,
        criteria=criteria_value,
        verdict=verdict,
        recommendation=recommendation,
        provenance=provenance_value,
        idempotency_key=review_key,
        command_fingerprint=review_fingerprint,
        reviewed_at=timezone.now(),
        created_by=locked.created_by,
    )
    locked.evaluator = evaluator
    locked.evaluator_feedback = recommendation
    locked.evaluator_reviewed_at = timezone.now()
    locked.state = OutcomeState.EVALUATOR_REVIEWED
    locked.save(_allow_lifecycle=True, created_by_id=locked.created_by_id)
    return locked


def _require_reviewed_outcome(outcome):
    if (
        outcome.state != OutcomeState.EVALUATOR_REVIEWED
        or outcome.evaluator_id is None
        or outcome.evaluator_reviewed_at is None
    ):
        raise InvalidTransitionError("Human outcome decisions require evaluator review")


@transaction.atomic
def accept_outcome(outcome, *, human_reviewer, decision_note=""):
    assignment, _run, _invocation, locked = _lock_outcome_path(outcome.pk)
    if human_reviewer is None:
        raise AgentDomainError("Human acceptance requires a reviewer")
    _ensure_human_workspace_admin(locked.workspace, human_reviewer)
    if locked.state == OutcomeState.ACCEPTED:
        return locked
    decision_note = _ensure_bounded_text(decision_note, "human_decision_note")
    _require_reviewed_outcome(locked)
    pending = {assignment.id}
    while pending:
        child_ids = set(AssignmentContract.objects.filter(lineage_of_id__in=pending).values_list("id", flat=True))
        if not child_ids:
            break
        if AssignmentContract.objects.filter(
            id__in=child_ids,
            state__in=[AssignmentState.READY, AssignmentState.ACTIVE, AssignmentState.REVISION],
        ).exists():
            raise AgentDomainError("Parent outcome cannot be accepted while delegated assignments remain unfinished")
        pending = child_ids
    locked.state = OutcomeState.ACCEPTED
    locked.human_reviewer = human_reviewer
    locked.updated_by = human_reviewer
    locked.human_decision_note = decision_note
    locked.human_decided_at = timezone.now()
    locked.save(_allow_lifecycle=True, created_by_id=locked.created_by_id, disable_auto_set_user=True)
    _transition_assignment_locked(assignment, AssignmentState.COMPLETED, updated_by=human_reviewer)
    return locked


@transaction.atomic
def request_revision(outcome, *, human_reviewer, decision_note=""):
    assignment, _run, _invocation, locked = _lock_outcome_path(outcome.pk)
    if human_reviewer is None:
        raise AgentDomainError("Revision requests require a reviewer")
    _ensure_human_workspace_admin(locked.workspace, human_reviewer)
    if locked.state == OutcomeState.REVISION_REQUESTED:
        return locked
    decision_note = _ensure_bounded_text(decision_note, "human_decision_note")
    _require_reviewed_outcome(locked)
    locked.state = OutcomeState.REVISION_REQUESTED
    locked.human_reviewer = human_reviewer
    locked.updated_by = human_reviewer
    locked.human_decision_note = decision_note
    locked.human_decided_at = timezone.now()
    locked.save(_allow_lifecycle=True, created_by_id=locked.created_by_id, disable_auto_set_user=True)
    _transition_assignment_locked(assignment, AssignmentState.REVISION, updated_by=human_reviewer)
    return locked

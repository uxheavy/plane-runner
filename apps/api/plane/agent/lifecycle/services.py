# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from copy import deepcopy
import re
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
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
    AgentRole,
    AssignmentContract,
    AssignmentState,
    InputEventKind,
    InvocationState,
    OutcomeState,
    OutcomeSubmission,
    ProfileVersion,
    RecoveryIntent,
    RunAttempt,
    RunInputEvent,
    RunLineageReason,
    RunState,
    RunTerminalEvent,
    RuntimeInvocation,
    TerminalEventKind,
    TerminalEventSource,
)

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


class AgentDomainError(ValidationError):
    """Base error for invalid Plane Agent domain commands."""


class InvalidTransitionError(AgentDomainError):
    """Raised when a record is asked to enter an illegal lifecycle state."""


class RecoveryIntentRequiredError(AgentDomainError):
    """Raised when a terminal or unknown run is reused without explicit lineage."""


class IdempotencyConflictError(AgentDomainError):
    """Raised when an idempotency key is reused for a different command binding."""


class TerminalEventRequiredError(AgentDomainError):
    """Raised when an invocation would finish without a visible Plane event."""


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

_RESERVED_PROFILE_KEYS = {
    "allowlist",
    "allowed_operations",
    "authorization",
    "permissions",
    "denylist",
}
_CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,219}$")


def _ensure_non_empty(value, field_name, *, limit=MAX_BOUNDED_TEXT_BYTES):
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > limit:
        raise AgentDomainError(f"{field_name} must be a non-empty string within {limit} UTF-8 bytes")
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


def _snapshot_tool_catalog(profile):
    presentation = profile.tool_presentation
    for key in _RESERVED_PROFILE_KEYS:
        if key in presentation:
            raise AgentDomainError("Profile presentation cannot define authorization or operation allowlists")
    raw_operations = presentation.get("eager_operations", presentation.get("eagerOperations", []))
    raw_operations = _as_list(raw_operations, "tool_presentation.eager_operations")
    operations = []
    for index, raw in enumerate(raw_operations):
        if not isinstance(raw, dict):
            raise AgentDomainError(f"tool_presentation.eager_operations[{index}] must be an object")
        operation_ref = _normalise_ref(
            raw.get("operationRef", raw.get("operation_ref")),
            "operation",
            f"tool_presentation.eager_operations[{index}].operationRef",
        )
        schema_digest = raw.get("schemaDigest", raw.get("schema_digest")) or content_digest(
            {"operationRef": operation_ref}
        )
        disclosure = raw.get("disclosure", "progressive")
        if not isinstance(disclosure, str) or disclosure not in {"eager", "progressive"}:
            raise AgentDomainError("tool presentation disclosure is invalid")
        operations.append({"operationRef": operation_ref, "schemaDigest": schema_digest, "disclosure": disclosure})
    catalog = {"eagerOperations": operations}
    return {
        "catalogDigest": presentation.get("catalogDigest", presentation.get("catalog_digest"))
        or content_digest(catalog),
        "eagerOperations": operations,
    }


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
    }
    for field in ("maxEventPayloadBytes", "maxArtifactBytes", "maxReceiptBytes"):
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
        "toolCatalog": _snapshot_tool_catalog(profile),
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


def _transition_assignment_locked(assignment, target):
    target = _state(target, AssignmentState, "assignment state")
    if target not in _ASSIGNMENT_TRANSITIONS[assignment.state]:
        raise InvalidTransitionError(f"Assignment cannot move from {assignment.state} to {target}")
    if target == AssignmentState.REVISION:
        assignment.revision += 1
    assignment.state = target
    assignment.save(_allow_lifecycle=True)
    return assignment


@transaction.atomic
def create_actor(*, workspace, display_name, project=None, credential_ref=None, created_by=None):
    _ensure_scope(workspace, project)
    display_name = _ensure_non_empty(display_name, "display_name", limit=255)
    return AgentActor.objects.create(
        workspace=workspace,
        project=project,
        display_name=display_name,
        credential_ref=_credential_ref(credential_ref),
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
    created_by=None,
):
    assignee = AgentActor.objects.get(pk=assignee.pk)
    _ensure_actor_active(assignee)
    project = project if project is not None else assignee.project
    _ensure_actor_scope(assignee, assignee.workspace, project)
    target_ref = _ensure_non_empty(target_ref, "target_ref", limit=255)
    objective = _ensure_non_empty(objective, "objective")
    if lineage_of is not None:
        lineage_of = AssignmentContract.objects.get(pk=lineage_of.pk)
        if (lineage_of.workspace_id, lineage_of.project_id) != (assignee.workspace_id, project.id if project else None):
            raise AgentDomainError("Assignment lineage is outside the Agent's Plane scope")
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
    return AssignmentContract.objects.create(
        workspace=assignee.workspace,
        project=project,
        assignee=assignee,
        lineage_of=lineage_of,
        target_ref=target_ref,
        objective=objective,
        acceptance_criteria=acceptance_criteria,
        context_refs=context_refs,
        state=AssignmentState.READY,
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


@transaction.atomic
def cancel_assignment(assignment):
    return transition_assignment(assignment, AssignmentState.CANCELLED)


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


def _iso_timestamp():
    return timezone.now().isoformat().replace("+00:00", "Z")


@transaction.atomic
def record_input_event(
    run, *, payload, kind=InputEventKind.HUMAN_INPUT, pending_input_ref=None, idempotency_key=None, created_by=None
):
    run = RunAttempt.objects.select_for_update().get(pk=run.pk)
    kind = _state(kind, InputEventKind, "input event kind")
    key = (
        _normalise_idempotency(idempotency_key, "input event idempotency_key") if idempotency_key is not None else None
    )
    payload = _as_dict(payload, "Input event payload")
    pending_ref = (
        _normalise_ref(pending_input_ref, "event", "pending_input_ref") if pending_input_ref is not None else None
    )
    if pending_ref is None:
        raise AgentDomainError("Input events require the exact pending input reference")
    event_fingerprint = None
    if key is not None:
        event_fingerprint = _command_fingerprint(
            "record_input_event",
            {
                "runId": _command_id(run),
                "kind": kind,
                "payload": payload,
                "pendingInputRef": pending_ref,
                "createdBy": _command_id(created_by),
            },
        )
    if key is not None:
        _lock_idempotency_key(key)
        existing = RunInputEvent.all_objects.filter(idempotency_key=key).first()
        if existing is not None:
            if existing.command_fingerprint != event_fingerprint:
                if _is_legacy_fingerprint(existing.command_fingerprint):
                    _legacy_match(
                        existing,
                        lambda row: _legacy_input_matches(row, run, kind, payload, pending_ref, created_by),
                        "Input event idempotency key is bound to another Plane command",
                        event_fingerprint,
                    )
                else:
                    raise IdempotencyConflictError("Input event idempotency key is bound to another run")
            return existing
    if run.state != RunState.WAITING_FOR_INPUT:
        raise InvalidTransitionError("Input events require a run that is explicitly waiting for input")
    if run.pending_input_ref != pending_ref:
        raise AgentDomainError("Input event does not match the run's pending input reference")
    _ensure_actor_active(run.actor)
    sequence = RunInputEvent.all_objects.filter(run=run).count() + 1
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
        idempotency_key=key,
        command_fingerprint=event_fingerprint,
        created_by=created_by,
    )
    if key is None:
        return RunInputEvent.objects.create(**fields)
    return _create_with_conflict_resolution(
        RunInputEvent,
        fields=fields,
        key_lookup={"idempotency_key": key},
        compatible=lambda existing: (
            existing.run_id == run.id
            and (
                existing.command_fingerprint == event_fingerprint
                or (
                    _is_legacy_fingerprint(existing.command_fingerprint)
                    and _legacy_match(
                        existing,
                        lambda row: _legacy_input_matches(row, run, kind, payload, pending_ref, created_by),
                        "Input event idempotency key is bound to another Plane command",
                        event_fingerprint,
                    )
                )
            )
        ),
        message="Input event idempotency key is bound to another Plane command",
    )


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
        return existing
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
            "expiresAt": _iso_timestamp(),
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
    run.save(_allow_lifecycle=True)
    return invocation


@transaction.atomic
def transition_run(run, target, *, pending_input_ref=None):
    target = _state(target, RunState, "run state")
    locked = RunAttempt.objects.select_for_update().get(pk=run.pk)
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
        invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=locked.last_invocation_id)
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
    locked.save(_allow_lifecycle=True)
    if locked.last_invocation_id and target == RunState.WAITING_FOR_INPUT:
        invocation = RuntimeInvocation.objects.select_for_update().get(invocation_id=locked.last_invocation_id)
        if invocation.state == InvocationState.RUNNING:
            invocation.state = InvocationState.WAITING_FOR_INPUT
            invocation.save(_allow_lifecycle=True)
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
    invocation.state = invocation_state
    invocation.save(_allow_lifecycle=True)
    run.state = run_state
    run.pending_input_ref = None
    run.save(_allow_lifecycle=True)
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
    invocation = RuntimeInvocation.objects.select_for_update().get(pk=invocation.pk)
    run = RunAttempt.objects.select_for_update().get(pk=invocation.run_id)
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
    run = RunAttempt.objects.select_for_update().get(pk=run.pk)
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
def review_outcome(outcome, *, evaluator, feedback=""):
    locked = OutcomeSubmission.objects.select_for_update().select_related("run").get(pk=outcome.pk)
    if locked.state != OutcomeState.PROPOSED:
        raise InvalidTransitionError(f"Outcome cannot be evaluated from {locked.state}")
    evaluator = AgentActor.objects.select_related("active_profile").get(pk=evaluator.pk)
    _ensure_actor_active(evaluator)
    if evaluator.active_profile_id is None or evaluator.active_profile.role != AgentRole.EVALUATOR:
        raise AgentDomainError("Only an Agent with the current evaluator role may review outcomes")
    if evaluator.workspace_id != locked.workspace_id or (
        evaluator.project_id is not None and evaluator.project_id != locked.project_id
    ):
        raise AgentDomainError("Evaluator is outside the outcome's Plane scope")
    locked.evaluator = evaluator
    locked.evaluator_feedback = feedback
    locked.evaluator_reviewed_at = timezone.now()
    locked.state = OutcomeState.EVALUATOR_REVIEWED
    locked.save(_allow_lifecycle=True)
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
    locked = OutcomeSubmission.objects.select_for_update().select_related("run").get(pk=outcome.pk)
    _require_reviewed_outcome(locked)
    if human_reviewer is None:
        raise AgentDomainError("Human acceptance requires a reviewer")
    locked.state = OutcomeState.ACCEPTED
    locked.human_reviewer = human_reviewer
    locked.human_decision_note = decision_note
    locked.human_decided_at = timezone.now()
    locked.save(_allow_lifecycle=True)
    assignment = AssignmentContract.objects.select_for_update().get(pk=locked.run.assignment_id)
    _transition_assignment_locked(assignment, AssignmentState.COMPLETED)
    return locked


@transaction.atomic
def request_revision(outcome, *, human_reviewer, decision_note=""):
    locked = OutcomeSubmission.objects.select_for_update().select_related("run").get(pk=outcome.pk)
    _require_reviewed_outcome(locked)
    if human_reviewer is None:
        raise AgentDomainError("Revision requests require a reviewer")
    locked.state = OutcomeState.REVISION_REQUESTED
    locked.human_reviewer = human_reviewer
    locked.human_decision_note = decision_note
    locked.human_decided_at = timezone.now()
    locked.save(_allow_lifecycle=True)
    assignment = AssignmentContract.objects.select_for_update().get(pk=locked.run.assignment_id)
    _transition_assignment_locked(assignment, AssignmentState.REVISION)
    return locked

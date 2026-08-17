"""One disposable Plane supervisor invocation for the configured G4 proof."""

from __future__ import annotations

# Django must be initialized before importing Plane models and lifecycle services.
# ruff: noqa: E402

import hashlib
import io
import json
import os
import secrets
import sys
import time
import uuid
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
sys.path.insert(0, "/workspace/apps/api")

import django

django.setup()

from django.core.management import call_command
from django.test import override_settings
from plane.agent.lifecycle import (
    create_actor,
    create_assignment,
    delegate_assignment,
    create_profile,
    create_run,
    finalize_invocation,
    record_input_event,
    record_invocation,
    reconcile_provider_attempts,
)
from plane.agent.runtime.supervisor import _provider_unknown_failure
from plane.agent.runtime.supervisor import request_runtime_cancellation
from plane.agent.schedules.services import create_schedule, fire_schedule
from plane.db.models import (
    AgentRole,
    AgentScheduleFireState,
    Issue,
    IssueAssignee,
    IssueLabel,
    InputEventKind,
    InvocationState,
    OutcomeSubmission,
    Project,
    ProjectMember,
    RunInputEvent,
    RunTerminalEvent,
    RuntimeInvocationControl,
    RuntimeProviderAttempt,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeUsageObservation,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.operation_gateway import (
    OperationGatewayAudit,
    OperationGatewayIdempotency,
)

if os.environ.get("G4_SCENARIO_DESCRIPTOR"):
    from agent_g4_manager_route import build_manager_route_evidence
    from agent_g4_worker_route import (
        attempt_actor_substitution,
        build_worker_route_evidence,
        context_state_counts,
        govern_worker_skill,
        replay_worker_rename,
        seed_worker_context,
        worker_code_mode_controls,
        worker_readback_facts,
    )

_LIVE_USAGE_KEYS = ("inputTokens", "outputTokens", "durationMs")
_THRESHOLD_KEYS = frozenset(
    {"permittedSuccessRateMin", "deniedRejectionRateMin", "maxLatencyP95Ms", "maxErrorRate"}
)
_TERMINAL_LIFECYCLE_PROTOCOL = "hermes.terminal-lifecycle/v1"
_TERMINAL_LIFECYCLE_STATUSES = frozenset(
    {"ok", "replayed", "denied", "conflict", "unavailable", "invalid"}
)
_TERMINAL_LIFECYCLE_ACTIONS = frozenset({"none", "proposal", "applied"})
_TERMINAL_LIFECYCLE_EXIT_CATEGORIES = frozenset(
    {
        "unknown",
        "text_response",
        "terminal_action",
        "max_iterations_reached",
        "budget_exhausted",
        "interrupted_by_user",
        "session_persistence_failed",
        "guardrail_halt",
        "local_processing_error",
        "error_near_max_iterations",
        "partial_stream_recovery",
        "other",
    }
)
_S00_PUBLICATION_REF_FIELDS = (
    "productRef",
    "operationAttemptRef",
    "operationRef",
    "applicationServiceRef",
    "gatewayReceiptRef",
    "receiptRef",
    "auditReceiptRef",
    "productEventRef",
)
_S00_GATE_PREDICATE_FIELDS = (
    ("invocation_succeeded", ("actual",)),
    ("run_succeeded", ("actual",)),
    ("one_visible_outcome_terminal", ("terminalCount", "outcomeCount", "terminalKind")),
    (
        "one_applied_outcome_publication",
        ("count", "action", "productKind", *_S00_PUBLICATION_REF_FIELDS, "expectedProductRef"),
    ),
    (
        "terminal_binding",
        (
            "source",
            "terminalRunRef",
            "expectedRunRef",
            "outcomeRunRef",
            "terminalInvocationRef",
            "expectedInvocationRef",
            "terminalProductRef",
            "expectedOutcomeRef",
            "terminalProductEventRef",
            "publishedProductEventRef",
        ),
    ),
    ("runtime_exit_completed", ("kind", "hasFailure")),
)


def _approved_thresholds(raw: str) -> dict[str, int | float]:
    """Parse the authority-validated thresholds forwarded by the live shell."""

    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("G4 approved thresholds are invalid") from exc
    if not isinstance(value, dict) or set(value) != _THRESHOLD_KEYS:
        raise RuntimeError("G4 approved thresholds are invalid")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value.values()):
        raise RuntimeError("G4 approved thresholds are invalid")
    return value


def _s00_gate_projection(value):
    raw_gate = value
    raw_predicates = raw_gate.get("predicates") if isinstance(raw_gate, dict) else None
    predicates = {}
    for name, fields in _S00_GATE_PREDICATE_FIELDS:
        raw = raw_predicates.get(name) if isinstance(raw_predicates, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        bounded = {"passed": raw.get("passed") is True}
        for field in fields:
            raw_value = raw.get(field)
            if field in {"count", "terminalCount", "outcomeCount"}:
                bounded[field] = raw_value if type(raw_value) is int and 0 <= raw_value <= 256 else 0
            elif field == "hasFailure":
                bounded[field] = raw_value is True
            else:
                bounded[field] = _s00_safe_ref(raw_value)
        predicates[name] = bounded
    first_failed = next((name for name, row in predicates.items() if row["passed"] is not True), None)
    return {
        "status": "passed" if isinstance(raw_gate, dict) and raw_gate.get("passed") is True else "failed",
        "firstFailedPredicate": first_failed,
        "predicates": predicates,
    }


def _receipt_canaries(canary_ids, *, passed):
    canary_ids = canary_ids if isinstance(canary_ids, dict) else {}
    return {
        key: {
            "id": _s00_safe_ref(canary_ids.get(key)),
            "status": expected_status if passed else "not_evaluated",
            "passed": passed,
        }
        for key, expected_status in (("permitted", "allowed"), ("denied", "denied"))
    }


def _receipt_semantic_digest(receipt):
    import hashlib
    import json

    payload = {key: value for key, value in receipt.items() if key != "semanticDigest"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _attach_receipt_semantic_digest(receipt):
    receipt["semanticDigest"] = _receipt_semantic_digest(receipt)
    return receipt


def _s00_safe_ref(value):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128:
        return "unavailable"
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:/-"
    lowered = value.lower()
    if any(term in lowered for term in ("password", "secret", "token", "credential", "authorization", "api_key")):
        return "unavailable"
    return value if all(character in allowed for character in value) else "unavailable"


def _s00_terminal_replay_gate(
    *,
    run_ref,
    terminal_run_ref,
    outcome_run_ref,
    invocation_ref,
    terminal_invocation_ref,
    run_state,
    invocation_state,
    terminal_kind,
    terminal_source,
    terminal_product_ref,
    terminal_product_event_ref,
    outcome_ref,
    terminal_count,
    outcome_count,
    applied_publication_bindings,
    runtime_exit_kind,
    runtime_exit_failure,
):
    bindings = applied_publication_bindings if isinstance(applied_publication_bindings, list) else []
    binding_count = min(len(bindings), 256)
    binding = bindings[0] if binding_count == 1 and isinstance(bindings[0], dict) else {}
    publication = {
        "count": binding_count,
        "action": binding.get("action"),
        "productKind": binding.get("productKind"),
        **{
            field: _s00_safe_ref(binding.get(field))
            for field in _S00_PUBLICATION_REF_FIELDS
        },
    }
    expected_run_ref = _s00_safe_ref(run_ref)
    expected_invocation_ref = _s00_safe_ref(invocation_ref)
    expected_outcome_ref = _s00_safe_ref(outcome_ref)
    predicates = {
        "invocation_succeeded": {
            "passed": invocation_state == "succeeded",
            "actual": invocation_state,
        },
        "run_succeeded": {
            "passed": run_state == "succeeded",
            "actual": run_state,
        },
        "one_visible_outcome_terminal": {
            "passed": terminal_count == 1 and outcome_count == 1 and terminal_kind == "outcome_submission",
            "terminalCount": terminal_count,
            "outcomeCount": outcome_count,
            "terminalKind": terminal_kind,
        },
        "one_applied_outcome_publication": {
            "passed": (
                publication["count"] == 1
                and publication["action"] == "applied"
                and publication["productKind"] == "outcome_submission"
                and all(publication[field] != "unavailable" for field in _S00_PUBLICATION_REF_FIELDS)
                and publication["operationRef"] == "operation:agent.outcome.publish"
                and publication["productRef"] == expected_outcome_ref
            ),
            **publication,
            "expectedProductRef": expected_outcome_ref,
        },
        "terminal_binding": {
            "passed": (
                terminal_source == "runtime"
                and _s00_safe_ref(terminal_run_ref) == expected_run_ref
                and _s00_safe_ref(outcome_run_ref) == expected_run_ref
                and _s00_safe_ref(terminal_invocation_ref) == expected_invocation_ref
                and _s00_safe_ref(terminal_product_ref) == expected_outcome_ref
                and _s00_safe_ref(terminal_product_event_ref) == publication["productEventRef"]
            ),
            "source": terminal_source,
            "terminalRunRef": _s00_safe_ref(terminal_run_ref),
            "expectedRunRef": expected_run_ref,
            "outcomeRunRef": _s00_safe_ref(outcome_run_ref),
            "terminalInvocationRef": _s00_safe_ref(terminal_invocation_ref),
            "expectedInvocationRef": expected_invocation_ref,
            "terminalProductRef": _s00_safe_ref(terminal_product_ref),
            "expectedOutcomeRef": expected_outcome_ref,
            "terminalProductEventRef": _s00_safe_ref(terminal_product_event_ref),
            "publishedProductEventRef": publication["productEventRef"],
        },
        "runtime_exit_completed": {
            "passed": runtime_exit_kind == "completed" and runtime_exit_failure is None,
            "kind": runtime_exit_kind,
            "hasFailure": runtime_exit_failure is not None,
        },
    }
    return {"passed": all(predicate["passed"] for predicate in predicates.values()), "predicates": predicates}


def _s00_publication_evidence(value):
    if not isinstance(value, dict):
        return {"count": 0, "refs": []}
    return {
        "count": value.get("count", 0),
        "refs": [
            {field: row[field] for field in _S00_PUBLICATION_REF_FIELDS}
            for row in value.get("refs", [])
            if isinstance(row, dict) and all(field in row for field in _S00_PUBLICATION_REF_FIELDS)
        ],
    }


def _bounded_terminal_lifecycle_observation(value):
    """Validate and retain Hermes' bounded terminal-lifecycle observation."""

    if not isinstance(value, str):
        return None
    try:
        observation = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(observation, dict) or observation.get("protocol") != _TERMINAL_LIFECYCLE_PROTOCOL:
        return None
    expected = {
        "protocol",
        "category",
        "hook_installed",
        "terminal_action_observed",
        "terminal_reason",
        "terminal_action",
        "outcome_publication",
        "finalization",
    }
    if set(observation) != expected or observation["category"] != "terminal_lifecycle":
        raise RuntimeError("terminal lifecycle observation schema invalid")
    if observation["hook_installed"] is not True or type(observation["terminal_action_observed"]) is not bool:
        raise RuntimeError("terminal lifecycle hook state invalid")
    if observation["terminal_reason"] not in {"product_outcome_published", "none"}:
        raise RuntimeError("terminal lifecycle reason invalid")

    def counter(value):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
            raise RuntimeError("terminal lifecycle counter invalid")
        return value

    def snapshot(value, fields):
        if not isinstance(value, dict) or not set(fields).issubset(value):
            raise RuntimeError("terminal lifecycle snapshot invalid")
        return {field: counter(value[field]) for field in fields}

    terminal_action = observation["terminal_action"]
    if terminal_action is not None:
        if not isinstance(terminal_action, dict) or set(terminal_action) != {
            "reason",
            "observed_at",
            "api_call_count",
            "provider_responses",
            "iteration_budget_used",
            "iteration_budget_remaining",
        }:
            raise RuntimeError("terminal lifecycle action invalid")
        terminal_action = {
            "reason": terminal_action["reason"],
            "observed_at": terminal_action["observed_at"],
            **snapshot(
                terminal_action,
                (
                    "api_call_count",
                    "provider_responses",
                    "iteration_budget_used",
                    "iteration_budget_remaining",
                ),
            ),
        }
        if terminal_action["reason"] not in {"product_outcome_published", "terminal_action_observed"}:
            raise RuntimeError("terminal lifecycle action reason invalid")
        if terminal_action["observed_at"] != "post_tool_batch":
            raise RuntimeError("terminal lifecycle action timing invalid")

    outcome_publication = observation["outcome_publication"]
    if outcome_publication is not None:
        if not isinstance(outcome_publication, dict) or set(outcome_publication) != {
            "status",
            "replayed",
            "publication_action",
            "operation_ref",
            "terminal_armed",
        }:
            raise RuntimeError("terminal lifecycle publication invalid")
        if (
            outcome_publication["status"] not in _TERMINAL_LIFECYCLE_STATUSES
            or type(outcome_publication["replayed"]) is not bool
            or outcome_publication["publication_action"] not in _TERMINAL_LIFECYCLE_ACTIONS
            or outcome_publication["operation_ref"] not in {"none", "operation:agent.outcome.publish"}
            or type(outcome_publication["terminal_armed"]) is not bool
        ):
            raise RuntimeError("terminal lifecycle publication values invalid")
        outcome_publication = dict(outcome_publication)

    finalization_value = observation["finalization"]
    finalization_fields = (
        "api_call_count",
        "provider_responses",
        "max_iterations",
        "iteration_budget_max_total",
        "iteration_budget_used",
        "iteration_budget_remaining",
    )
    if not isinstance(finalization_value, dict) or set(finalization_value) != set(
        finalization_fields
    ) | {"exit_reason_before_mapping", "exit_reason_after_mapping"}:
        raise RuntimeError("terminal lifecycle finalization invalid")
    finalization = {
        field: counter(finalization_value[field])
        for field in finalization_fields
    }
    for field in ("exit_reason_before_mapping", "exit_reason_after_mapping"):
        value = finalization_value.get(field)
        if value not in _TERMINAL_LIFECYCLE_EXIT_CATEGORIES:
            raise RuntimeError("terminal lifecycle exit category invalid")
        finalization[field] = value
    return {
        "protocol": _TERMINAL_LIFECYCLE_PROTOCOL,
        "category": "terminal_lifecycle",
        "hook_installed": True,
        "terminal_action_observed": observation["terminal_action_observed"],
        "terminal_reason": observation["terminal_reason"],
        "terminal_action": terminal_action,
        "outcome_publication": outcome_publication,
        "finalization": finalization,
    }


def _s00_transcript_evidence(event_ids, *, required):
    bounded_event_ids = list(event_ids)[:32] if isinstance(event_ids, (list, tuple)) else []
    return {
        "status": "observed" if bounded_event_ids else "not_observed",
        "requirement": "required" if required else "not_required",
        "count": len(bounded_event_ids),
        "eventIds": bounded_event_ids,
    }


def _semantic_state_digest(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _semantic_issue_digest(issue) -> str:
    snapshot = {
        "name": issue.name,
        "description": issue.description_json,
        "state": str(issue.state_id) if issue.state_id is not None else None,
        "priority": issue.priority,
        "assignees": sorted(
            str(value)
            for value in IssueAssignee.objects.filter(issue=issue, deleted_at__isnull=True).values_list(
                "assignee_id", flat=True
            )
        ),
        "labels": sorted(
            (str(label_id), label_name)
            for label_id, label_name in IssueLabel.objects.filter(issue=issue, deleted_at__isnull=True).values_list(
                "label_id", "label__name"
            )
        ),
    }
    return _semantic_state_digest(snapshot)


def _binding() -> dict[str, str]:
    candidate = os.environ["G4_CANDIDATE"]
    expected_candidate = os.environ["G4_EXPECTED_CANDIDATE"]
    if (
        len(candidate) != 40
        or len(expected_candidate) != 40
        or any(character not in "0123456789abcdef" for character in candidate + expected_candidate)
        or candidate != expected_candidate
    ):
        raise RuntimeError("live invocation candidate does not match the external expectedCandidate")
    return {
        "candidateCommit": candidate,
        "g3Baseline": os.environ["G4_G3_BASELINE"],
        "hermesCommit": os.environ["G4_HERMES"],
        "mcpGitlink": os.environ["G4_MCP"],
        "sdkGitlink": os.environ["G4_SDK"],
        "runtimeImageTag": os.environ["G4_RUNTIME_IMAGE_TAG"],
        "runtimeImageDigest": os.environ["G4_RUNTIME_IMAGE_DIGEST"],
        "runtimeImageRevision": os.environ["G4_RUNTIME_IMAGE_REVISION"],
        "runtimeContract": os.environ["G4_RUNTIME_CONTRACT"],
        "apiArtifact": {
            "imageTag": os.environ["G4_API_IMAGE_TAG"],
            "imageDigest": os.environ["G4_API_IMAGE_DIGEST"],
            "sourceRevision": os.environ["G4_API_SOURCE_REVISION"],
            "contract": os.environ["G4_API_CONTRACT"],
        },
    }


def _provider_descriptor() -> dict[str, str]:
    """Require the API invocation environment to equal validated authority data."""

    try:
        descriptor = json.loads(os.environ["G4_PROVIDER_DESCRIPTOR_JSON"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("live invocation provider descriptor is unavailable") from exc
    fields = {
        "name": "PLANE_AGENT_RUNTIME_PROVIDER",
        "model": "PLANE_AGENT_RUNTIME_PROVIDER_MODELS",
        "baseUrl": "PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL",
        "host": "PLANE_AGENT_RUNTIME_PROVIDER_HOST",
        "path": "PLANE_AGENT_RUNTIME_PROVIDER_PATH",
        "credentialSource": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE",
        "credentialRef": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF",
        "credentialName": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME",
    }
    if set(descriptor) != set(fields) or any(
        not isinstance(descriptor[key], str) or not descriptor[key] for key in fields
    ):
        raise RuntimeError("live invocation provider descriptor is malformed")
    if any(os.environ.get(environment_key) != descriptor[key] for key, environment_key in fields.items()):
        raise RuntimeError("live invocation provider descriptor environment mismatch")
    return descriptor


def _provider_relay_descriptor() -> dict[str, object]:
    try:
        descriptor = json.loads(os.environ["G4_PROVIDER_RELAY_JSON"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("live invocation provider relay descriptor is unavailable") from exc
    required = {
        "protocol",
        "transport",
        "childNetworkPolicy",
        "externalEgressOwner",
        "hostGatewaySeparate",
        "hermesHookStatus",
    }
    if not isinstance(descriptor, dict) or set(descriptor) != required:
        raise RuntimeError("live invocation provider relay descriptor is malformed")
    return descriptor


def _scenario_descriptor():
    path = os.environ.get("G4_SCENARIO_DESCRIPTOR")
    digest = os.environ.get("G4_SCENARIO_SHA256")
    if not path and not digest:
        return None
    if not path or not digest:
        raise RuntimeError("live invocation scenario descriptor inputs are incomplete")
    try:
        from agent_g4_live_scenario import ScenarioError, load_descriptor, select_commission
    except ImportError as exc:
        raise RuntimeError("live invocation scenario parser is unavailable") from exc
    try:
        descriptor = load_descriptor(path, digest)
        commission_id = os.environ.get("G4_SCENARIO_COMMISSION_ID", "")
        return select_commission(descriptor, commission_id) if commission_id else descriptor
    except ScenarioError as exc:
        raise RuntimeError(f"live invocation scenario descriptor rejected: {exc}") from exc


def _scenario_legacy_s00(scenario):
    return scenario is None or (
        scenario.scenario_id == "worker"
        and scenario.expected is None
        and not scenario.setup.actors
        and scenario.setup.lineage is None
        and scenario.setup.schedule is None
        and not scenario.setup.preconditions
        and scenario.controls.continuation is None
        and scenario.controls.revision is None
        and scenario.controls.cancellation is None
        and scenario.controls.fault == "none"
    )


def _scenario_readback(
    scenario,
    audit_rows,
    run,
    assignment,
    *,
    explicit_publication=None,
    lineage_assignment=None,
    schedule=None,
    schedule_fire=None,
):
    if scenario is None or scenario.expected is None:
        return None, None
    operations = {}
    for row in audit_rows:
        if row.get("phase") != "outcome":
            continue
        operation_id = row.get("operation_id")
        if not isinstance(operation_id, str):
            continue
        item = operations.setdefault(operation_id, {"operationId": operation_id, "count": 0, "outcome": "not_observed"})
        item["count"] += 1
        item["outcome"] = "success" if row.get("outcome") in {"success", "replay"} else "denied" if row.get("outcome") == "denied" else "not_observed"
    assignment_count = int(getattr(assignment, "pk", None) is not None)
    run_count = int(getattr(run, "pk", None) is not None)
    invocation_count = run.invocations.count() if run_count else 0
    audit_count = len(audit_rows)
    input_event_count = RunInputEvent.objects.filter(run=run).count() if run_count else 0
    from agent_g4_live_scenario import explicit_publication_expectations

    publication_records, publication_events, publication_evidence = explicit_publication_expectations(
        explicit_publication
    )
    terminal_kinds = ("outcome_submission", "run_failure", "run_blocker", "run_cancellation")
    terminal_rows = (
        list(RunTerminalEvent.objects.filter(run=run, visible=True).values_list("kind", flat=True))
        if run_count
        else []
    )
    records = [
        {"kind": "assignment", "count": assignment_count},
        {"kind": "run", "count": run_count},
        {"kind": "invocation", "count": invocation_count},
        {"kind": "input_event", "count": input_event_count},
        {"kind": "audit", "count": audit_count},
        *publication_records,
        {"kind": "terminal_event", "count": len(terminal_rows)},
        {"kind": "lineage_assignment", "count": int(getattr(lineage_assignment, "pk", None) is not None)},
        {"kind": "schedule", "count": int(getattr(schedule, "pk", None) is not None)},
        {
            "kind": "schedule_fire",
            "count": int(
                getattr(schedule_fire, "pk", None) is not None
                and schedule_fire.state == AgentScheduleFireState.CREATED
            ),
        },
    ]
    products = [*publication_events, {"kind": "input_event", "count": input_event_count}]
    products.extend({"kind": kind, "count": terminal_rows.count(kind)} for kind in terminal_kinds)
    evidence_kinds = [row["kind"] for row in records if row["count"]]
    if "publication" in publication_evidence and "publication" not in evidence_kinds:
        evidence_kinds.append("publication")
    from agent_g4_live_scenario import evaluate_expectations
    actual = {"operations": list(operations.values()), "records": records, "productEvents": products, "evidenceKinds": evidence_kinds}
    return actual, evaluate_expectations(scenario.expected, **{"operations": actual["operations"], "records": records, "product_events": products, "evidence_kinds": evidence_kinds})


def _run_continuation_supervisor(invocation, stdout, stderr):
    call_command(
        "agent_supervisor", invocation_ref=invocation.invocation_id, worker_id="g4-live-configured-worker",
        lease_seconds=300, model_call_allowance=16, stdout=stdout, stderr=stderr,
    )


def _record_continuation_invocation(run, event, suffix, user, trigger):
    return record_invocation(
        run, idempotency_key=f"idempotency:g4-live-continuation-{suffix}",
        trigger={"kind": trigger}, input_event=event, created_by=user,
    )


def build_failure_evidence(
    *,
    binding,
    failure_phase,
    error_class,
    exit_code,
    run_id,
    run_state,
    invocation_id,
    invocation_state,
    provider_attempts,
    terminal_kind,
    failure_code=None,
    failure_reason=None,
    runtime_exit=None,
    runtime_event_kind_counts=None,
    terminal_code=None,
    terminal_reason=None,
    s00_gate=None,
    authority_id=None,
    canary_ids=None,
    provider_relay=None,
    scenario=None,
    scenario_gate=None,
    plane_host_operation_receipts=False,
    plane_operation_audit=None,
    terminal_lifecycle=None,
):
    """Return one bounded failure object without copying runtime observations."""

    import json

    binding_fields = (
        "candidateCommit",
        "g3Baseline",
        "hermesCommit",
        "mcpGitlink",
        "sdkGitlink",
        "runtimeImageTag",
        "runtimeImageDigest",
        "runtimeImageRevision",
        "runtimeContract",
        "apiArtifact",
    )
    failure_stages = {
        "initialization",
        "compose",
        "audit-bootstrap",
        "runtime-start",
        "runtime-health",
        "api-invocation",
    }
    error_classes = {
        "CommandError",
        "ConnectionError",
        "FileNotFoundError",
        "ImportError",
        "ImproperlyConfigured",
        "ModuleNotFoundError",
        "OperationalError",
        "PermissionError",
        "RuntimeError",
        "TimeoutError",
    }
    invocation_states = {
        "queued",
        "running",
        "waiting_for_input",
        "succeeded",
        "failed",
        "blocked",
        "cancelled",
        "outcome_unknown",
    }
    attempt_phases = {"intent", "started", "completed", "failed", "outcome_unknown"}
    status_classes = {"", "not_sent", "unknown", "error", "2xx", "4xx", "5xx", "transport"}
    error_codes = {"", "pre_send_failure", "outcome_unknown", "provider_error", "runtime_error", "upstream_error"}
    terminal_kinds = {"none", "outcome_submission", "run_failure", "run_blocker", "run_cancellation"}
    failure_codes = {
        "runtime_transport_pre_dispatch_failure",
        "runtime_configuration_pre_dispatch_failure",
        "runtime_process_failed",
        "runtime_process_timeout",
        "runtime_process_cancelled",
        "runtime_process_output_invalid",
        "runtime_supervisor_pre_dispatch_failure",
        "budget_exhausted",
        "runtime_error",
        "missing_outcome",
        "outcome_unknown",
    }
    reason_phases = {
        "runtime_transport",
        "runtime_configuration",
        "runtime_process",
        "launcher",
        "runtime_supervisor",
        "provider_relay",
    }
    failure_details = {
        "dispatch_rejected",
        "process_start_failed",
        "process_exit",
        "bootstrap_argv_rejected",
        "process_timeout",
        "process_cancelled",
        "process_output_invalid",
        "unclassified_exception",
        "missing_outcome",
        "upstream_result_unavailable",
    }
    failure_subreasons = {
        "credential_reference_not_allowed",
        "credential_source_unavailable",
        "credential_source_invalid",
        "credential_source_oversized",
        "credential_resolver_failed",
        "credential_resolver_output_invalid",
        "credential_lease_binding",
        "credential_lease_expired",
        "credential_lease_revoked",
        "credential_lease_rotated",
        "credential_lease_metadata_invalid",
        "credential_state_unavailable",
        "credential_state_invalid",
        "provider_attempt_evidence_rejected",
        "runtime_configuration_rejected",
        "model_call_budget_exhausted",
        "runtime_execution_failed",
        "completed_without_explicit_outcome",
        "upstream_exception",
        "upstream_channel_closed",
        "upstream_timeout",
        "channel_closed_after_upstream",
        "reconciliation_required",
        "request_rejected",
        "auth",
        "rate_limited",
        "upstream_unavailable",
    }
    runtime_exit_kinds = {"completed", "waiting_for_input", "failed", "blocked", "cancelled"}
    runtime_failure_codes = {"budget_exhausted", "runtime_error"}
    runtime_failure_causes = {
        "host_operation_failure",
        "cancellation_monitor_failure",
        "invalid_usage_accounting",
        "static_configuration_failure",
    }
    operation_ids = (
        "search_workspace",
        "work_item.read",
        "catalog.search",
        "catalog.describe",
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    )
    operation_statuses = {"success", "denied", "conflict", "unavailable", "absent"}
    operation_error_codes = {
        "NOT_AUTHORIZED",
        "IDEMPOTENCY_CONFLICT",
        "PLANE_CONFLICT",
        "OPERATION_UNAVAILABLE",
        "OUTCOME_UNKNOWN",
        "VALIDATION_ERROR",
        "OPERATION_REJECTED",
        "UPSTREAM_FAILURE",
    }
    max_operation_audit_count = 8
    runtime_event_kinds = {
        "progress_observed",
        "conversation_publication_observed",
        "input_request_observed",
        "artifact_observed",
        "usage_observed",
        "outcome_submission_observed",
        "failure_observed",
        "blocker_observed",
        "transcript_evidence_observed",
    }
    terminal_reason_categories = failure_details | failure_subreasons | runtime_failure_causes

    def bounded_operation_audit(value):
        summary = {
            operation_id: {
                "operationId": operation_id,
                "status": "absent",
                "errorCode": None,
                "count": 0,
            }
            for operation_id in operation_ids
        }
        if not isinstance(value, (list, tuple)):
            return [summary[operation_id] for operation_id in operation_ids]
        for row in value[:64]:
            if not isinstance(row, dict):
                continue
            operation_id = row.get("operationId", row.get("operation_id"))
            if operation_id not in summary:
                continue
            item = summary[operation_id]
            item["count"] = min(item["count"] + 1, max_operation_audit_count)
            status = row.get("status")
            outcome = row.get("outcome")
            error_code = row.get("errorCode", row.get("error_code"))
            if status not in operation_statuses:
                if outcome in {"success", "replay"}:
                    status = "success"
                elif outcome == "denied":
                    status = "denied"
                elif outcome == "outcome_unknown":
                    status = "unavailable"
                elif outcome == "intent":
                    status = "unavailable"
                elif outcome == "failure":
                    status = "conflict" if error_code in {"IDEMPOTENCY_CONFLICT", "PLANE_CONFLICT"} else "unavailable"
            if status in operation_statuses and status != "absent":
                item["status"] = status
                item["errorCode"] = error_code if error_code in operation_error_codes else None
            target_digest = row.get("targetDigest", row.get("target_digest"))
            if (
                isinstance(target_digest, str)
                and operation_id.startswith("work_item.")
                and len(target_digest) == 64
                and all(character in "0123456789abcdef" for character in target_digest)
            ):
                item["targetDigest"] = target_digest
        return [summary[operation_id] for operation_id in operation_ids]

    def bounded_identifier(value):
        if value is None:
            return None
        text = str(value)
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        if (
            len(text.encode("utf-8")) > 128
            or not text
            or any(char not in allowed for char in text)
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in text)
        ):
            return "unavailable"
        return text

    def bounded_host_operation_failure(value):
        required = {
            "operationId",
            "attemptRef",
            "receiptRef",
            "status",
            "errorCode",
            "codeModePhase",
        }
        if not isinstance(value, dict) or set(value) != required:
            return None
        status = value.get("status")
        phase = value.get("codeModePhase")
        if status not in {"denied", "conflict", "unavailable", "invalid"}:
            return None
        if phase not in {"host_callback", "unavailable"}:
            return None
        operation_id = bounded_identifier(value.get("operationId"))
        attempt_ref = bounded_identifier(value.get("attemptRef"))
        receipt_ref = bounded_identifier(value.get("receiptRef"))
        error_code = bounded_identifier(value.get("errorCode"))
        if (
            operation_id is None
            or attempt_ref is None
            or receipt_ref is None
            or error_code is None
        ):
            return None
        return {
            "operationId": operation_id,
            "attemptRef": attempt_ref,
            "receiptRef": receipt_ref,
            "status": status,
            "errorCode": error_code,
            "codeModePhase": phase,
        }

    def bounded_binding_value(key, value):
        if not isinstance(value, str) or len(value.encode("utf-8")) > 128:
            return "unavailable"
        hexadecimal = "0123456789abcdef"
        if key in {"candidateCommit", "g3Baseline", "hermesCommit", "mcpGitlink", "sdkGitlink", "runtimeImageRevision"}:
            return value if len(value) == 40 and all(char in hexadecimal for char in value) else "unavailable"
        if key == "runtimeImageDigest":
            digest_prefix, separator, digest = value.partition(":")
            return (
                value
                if digest_prefix == "sha256"
                and separator
                and len(digest) == 64
                and all(char in hexadecimal for char in digest)
                else "unavailable"
            )
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/-"
        if not value or any(char not in allowed for char in value):
            return "unavailable"
        return value

    def bounded_state(value):
        return value if value in invocation_states else "unknown"

    bounded_binding = {
        key: bounded_binding_value(key, binding[key])
        for key in binding_fields
        if isinstance(binding, dict) and key in binding and key != "apiArtifact"
    }
    if isinstance(binding, dict) and "apiArtifact" in binding:
        artifact = binding["apiArtifact"]
        if not isinstance(artifact, dict) or set(artifact) != {"imageTag", "imageDigest", "sourceRevision", "contract"}:
            bounded_binding["apiArtifact"] = {
                "imageTag": "unavailable",
                "imageDigest": "unavailable",
                "sourceRevision": "unavailable",
                "contract": "unavailable",
            }
        else:
            bounded_binding["apiArtifact"] = {
                "imageTag": bounded_binding_value("apiImageTag", artifact["imageTag"]),
                "imageDigest": bounded_binding_value("runtimeImageDigest", artifact["imageDigest"]),
                "sourceRevision": bounded_binding_value("runtimeImageRevision", artifact["sourceRevision"]),
                "contract": bounded_binding_value("apiContract", artifact["contract"]),
            }
    attempts = []
    for row in list(provider_attempts or [])[:32]:
        if not isinstance(row, dict):
            continue
        phase = row.get("phase") if row.get("phase") in attempt_phases else "unknown"
        status_class = row.get("statusClass") if row.get("statusClass") in status_classes else "unknown"
        error_code = row.get("errorCode") if row.get("errorCode") in error_codes else (
            "provider_error" if status_class in {"error", "4xx", "5xx"} else "unspecified"
        )
        reason_subreason = row.get("reasonSubreason")
        if not isinstance(reason_subreason, str) or reason_subreason not in failure_subreasons:
            reason_subreason = ""
        sequence = row.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1 or sequence > 256:
            sequence = 0
        bounded_attempt = {
            "sequence": sequence,
            "phase": phase,
            "upstreamInitiated": row.get("upstreamInitiated") is True,
            "statusClass": status_class,
            "errorCode": error_code,
        }
        if reason_subreason:
            bounded_attempt["reasonSubreason"] = reason_subreason
        attempts.append(bounded_attempt)

    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or not 1 <= exit_code <= 255:
        exit_code = 1

    reason = {}
    if isinstance(failure_reason, str):
        try:
            candidate = json.loads(failure_reason)
        except (TypeError, ValueError):
            candidate = None
        if isinstance(candidate, dict):
            base_keys = {"failureCode", "failurePhase", "failureDetail"}
            optional_keys = {
                "failureSubreason",
                "failureCause",
                "hostOperationFailure",
                "providerAttemptRef",
                "providerEventRef",
            }
            if base_keys.issubset(candidate) and not set(candidate).difference(
                base_keys | optional_keys
            ):
                reason = dict(candidate)
                if "hostOperationFailure" in reason:
                    bounded_host_failure = bounded_host_operation_failure(reason["hostOperationFailure"])
                    if bounded_host_failure is None:
                        reason.pop("hostOperationFailure", None)
                    else:
                        reason["hostOperationFailure"] = bounded_host_failure
    reason_code = reason.get("failureCode")
    bounded_failure_code = (
        reason_code
        if isinstance(reason_code, str) and reason_code in failure_codes
        else failure_code
        if isinstance(failure_code, str) and failure_code in failure_codes
        else "unspecified"
    )
    reason_phase = reason.get("failurePhase")
    reason_detail = reason.get("failureDetail")
    bounded_failure_phase = (
        reason_phase if isinstance(reason_phase, str) and reason_phase in reason_phases else "unavailable"
    )
    bounded_failure_detail = (
        reason_detail if isinstance(reason_detail, str) and reason_detail in failure_details else "unavailable"
    )
    reason_subreason = reason.get("failureSubreason")
    bounded_failure_subreason = (
        reason_subreason
        if isinstance(reason_subreason, str) and reason_subreason in failure_subreasons
        else "unavailable"
    )
    reason_cause = reason.get("failureCause")
    bounded_failure_cause = (
        reason_cause
        if isinstance(reason_cause, str) and reason_cause in runtime_failure_causes
        else None
    )

    bounded_runtime_exit = {"present": False, "kind": "unknown", "finalSequence": None, "failure": None}
    if isinstance(runtime_exit, dict):
        runtime_exit_kind = runtime_exit.get("kind")
        bounded_runtime_exit["present"] = True
        bounded_runtime_exit["kind"] = (
            runtime_exit_kind if runtime_exit_kind in runtime_exit_kinds else "unknown"
        )
        final_sequence = runtime_exit.get("finalSequence")
        bounded_runtime_exit["finalSequence"] = (
            final_sequence
            if isinstance(final_sequence, int) and not isinstance(final_sequence, bool) and 0 <= final_sequence <= 256
            else None
        )
        runtime_failure = runtime_exit.get("failure")
        if isinstance(runtime_failure, dict):
            runtime_failure_code = runtime_failure.get("code")
            bounded_runtime_exit["failure"] = {
                "code": runtime_failure_code if runtime_failure_code in runtime_failure_codes else "unavailable",
                "retryable": runtime_failure.get("retryable") is True,
            }
            runtime_failure_cause = runtime_failure.get("cause")
            if (
                runtime_failure_code == "runtime_error"
                and runtime_failure_cause in runtime_failure_causes
            ):
                bounded_runtime_exit["failure"]["cause"] = runtime_failure_cause

    bounded_event_kind_counts = {}
    if isinstance(runtime_event_kind_counts, dict):
        for kind, count in list(runtime_event_kind_counts.items())[: len(runtime_event_kinds)]:
            if kind not in runtime_event_kinds:
                continue
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 256:
                continue
            bounded_event_kind_counts[kind] = count

    bounded_terminal_code = (
        terminal_code if isinstance(terminal_code, str) and terminal_code in failure_codes else "unavailable"
    )
    bounded_terminal_reason_category = "unavailable"
    if isinstance(terminal_reason, str):
        try:
            terminal_reason_value = json.loads(terminal_reason)
        except (TypeError, ValueError):
            terminal_reason_value = None
        if isinstance(terminal_reason_value, dict):
            category = (
                terminal_reason_value.get("failureCause")
                or terminal_reason_value.get("failureSubreason")
                or terminal_reason_value.get("failureDetail")
            )
            if category in terminal_reason_categories:
                bounded_terminal_reason_category = category

    if terminal_kind not in terminal_kinds:
        terminal_kind = "unknown"
    if terminal_kind == "unknown":
        terminal = {"present": False, "kind": "unknown"}
    else:
        terminal = {"present": terminal_kind != "none", "kind": terminal_kind}
    if terminal["present"]:
        terminal.update(
            {
                "code": bounded_terminal_code,
                "reasonCategory": bounded_terminal_reason_category,
            }
        )

    bounded_failure = {
        "phase": failure_phase if failure_phase in failure_stages else "unknown",
        "errorClass": error_class if error_class in error_classes else "unspecified",
        "exitCode": exit_code,
        "reasonCode": bounded_failure_code,
        "reasonPhase": bounded_failure_phase,
        "reasonDetail": bounded_failure_detail,
        "reasonSubreason": bounded_failure_subreason,
    }
    if bounded_failure_cause is not None:
        bounded_failure["reasonCause"] = bounded_failure_cause
    bounded_host_failure = bounded_host_operation_failure(reason.get("hostOperationFailure"))
    if bounded_host_failure is not None:
        bounded_failure["hostOperationFailure"] = bounded_host_failure
    for field, prefix in (
        ("providerAttemptRef", "provider-attempt:"),
        ("providerEventRef", "provider-event:"),
    ):
        value = reason.get(field)
        if isinstance(value, str) and value.startswith(prefix) and bounded_identifier(value) != "unavailable":
            bounded_failure[field] = bounded_identifier(value)

    receipt = {
        "schemaVersion": "plane-agent-g4/live-failure/v1",
        "status": "failed",
        "binding": bounded_binding,
        "authorityId": _s00_safe_ref(authority_id),
        "canaries": _receipt_canaries(canary_ids, passed=False),
        "failure": bounded_failure,
        "run": {"present": run_id is not None, "id": bounded_identifier(run_id), "state": bounded_state(run_state)},
        "invocation": {
            "present": invocation_id is not None,
            "id": bounded_identifier(invocation_id),
            "state": bounded_state(invocation_state),
        },
        "runtimeExit": bounded_runtime_exit,
        "runtimeEventIngress": {"kindCounts": bounded_event_kind_counts},
        "providerAttempts": attempts,
        "terminal": terminal,
        "s00Gate": _s00_gate_projection(s00_gate),
        "planeHostOperationReceipts": plane_host_operation_receipts is True,
        "planeOperationAudit": bounded_operation_audit(plane_operation_audit),
    }
    if provider_relay is not None:
        receipt["providerRelay"] = provider_relay
    if scenario is not None:
        receipt["scenario"] = scenario
    if scenario_gate is not None:
        receipt["scenarioGate"] = scenario_gate
    if terminal_lifecycle is not None:
        receipt["terminalLifecycle"] = terminal_lifecycle
    return _attach_receipt_semantic_digest(receipt)


def _supervisor_failure_reason(output):
    """Extract only the bounded dispatch classification emitted by Plane."""

    import json

    if not isinstance(output, str):
        return None
    allowed_keys = {
        "failureCode",
        "failurePhase",
        "failureDetail",
        "failureSubreason",
        "failureCause",
        "providerAttemptRef",
        "providerEventRef",
    }
    required_keys = allowed_keys - {"failureSubreason", "providerAttemptRef", "providerEventRef"}
    allowed_shapes = {
        frozenset(required_keys),
        frozenset(required_keys | {"failureSubreason"}),
        frozenset(required_keys - {"failureCause"}),
        frozenset((required_keys - {"failureCause"}) | {"failureSubreason"}),
    }
    host_failure_fields = {
        "operationId",
        "attemptRef",
        "receiptRef",
        "status",
        "errorCode",
        "codeModePhase",
    }

    def bounded_host_failure(value):
        if not isinstance(value, dict) or set(value) != host_failure_fields:
            return None
        if value["status"] not in {"denied", "conflict", "unavailable", "invalid"}:
            return None
        if value["codeModePhase"] not in {"host_callback", "unavailable"}:
            return None
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        bounded = {}
        for field in ("operationId", "attemptRef", "receiptRef", "errorCode"):
            item = value[field]
            if not isinstance(item, str) or not item or len(item.encode("utf-8")) > 128:
                return None
            if any(char not in allowed for char in item):
                return None
            bounded[field] = item
        bounded["status"] = value["status"]
        bounded["codeModePhase"] = value["codeModePhase"]
        return bounded

    for line in reversed(output.splitlines()):
        marker = " failure="
        if marker not in line:
            continue
        raw = line.rsplit(marker, 1)[1]
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        value_keys = frozenset(value)
        diagnostic_refs = value_keys & {"providerAttemptRef", "providerEventRef"}
        if value_keys - diagnostic_refs not in allowed_shapes:
            if (
                "hostOperationFailure" not in value
                or value_keys - diagnostic_refs - {"hostOperationFailure"} not in allowed_shapes
            ):
                continue
        if not all(
            isinstance(value.get(item), str)
            for item in (
                "failureCode",
                "failurePhase",
                "failureDetail",
                "failureSubreason",
                "failureCause",
            )
            if item in value
        ):
            continue
        if "hostOperationFailure" in value:
            bounded = bounded_host_failure(value["hostOperationFailure"])
            if bounded is None:
                continue
            value = dict(value)
            value["hostOperationFailure"] = bounded
        for field, prefix in (
            ("providerAttemptRef", "provider-attempt:"),
            ("providerEventRef", "provider-event:"),
        ):
            if field in value:
                item = value[field]
                allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:/-"
                if (
                    not isinstance(item, str)
                    or not item.startswith(prefix)
                    or len(item.encode("utf-8")) > 128
                    or any(character not in allowed for character in item)
                ):
                    break
        else:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return None


def _provider_attempts_have_unknown_evidence(provider_attempts, control=None):
    """Classify provider uncertainty only from durable non-terminal evidence."""

    if control is not None and (
        getattr(control, "state", "") == "outcome_unknown"
        or getattr(control, "failure_code", "") == "outcome_unknown"
    ):
        return True
    return any(
        attempt.phase == "outcome_unknown"
        or attempt.error_code == "outcome_unknown"
        or (
            attempt.upstream_initiated
            and attempt.phase in {"intent", "started"}
            and getattr(attempt, "terminal_at", None) is None
        )
        for attempt in provider_attempts
    )


def _provider_unknown_failure_reason(invocation, provider_attempts, control=None):
    if invocation is None or not _provider_attempts_have_unknown_evidence(provider_attempts, control):
        return None
    provider_failure = _provider_unknown_failure(invocation)
    return (
        json.dumps(provider_failure, sort_keys=True, separators=(",", ":"))
        if provider_failure is not None
        else None
    )


def _prepare_shared_worker_setup(scenario, provider, provider_relay, suffix, *, cache):
    """Create Maya once; bounded commissions then receive separate run snapshots."""

    if cache.get("setup") is not None:
        return cache["setup"]

    email = f"g4-live-{suffix}@plane.test"
    user = User.objects.create(email=email, username=email, first_name="G4", last_name="Live")
    user.set_password(secrets.token_urlsafe(32))
    user.save(update_fields=["password"])
    workspace = Workspace.objects.create(name=f"G4 Live {suffix}", owner=user, slug=f"g4-live-{suffix}")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
    project = Project.objects.create(
        name="G4 Live Project", identifier=f"G{suffix[:2].upper()}", workspace=workspace, created_by=user
    )
    ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=project,
        workspace=workspace,
        created_by=user,
    )
    issue = Issue.objects.create(name="G4 Live Issue", project=project, workspace=workspace, created_by=user)
    actor = create_actor(
        workspace=workspace,
        project=project,
        display_name=(scenario.profile.name if scenario is not None else "G4 configured provider worker"),
        credential_ref="plane-credential:g4-live",
        created_by=user,
    )
    context_facts = {}
    if scenario is not None and scenario.scenario_id == "worker":
        context_facts.update(
            seed_worker_context(
                actor=actor,
                workspace=workspace,
                project=project,
                user=user,
                suffix=suffix,
                provider=provider["name"],
                model=scenario.profile.model_policy.model,
            )
        )
    scenario_agent_roles = {
        "worker": AgentRole.WORKER,
        "delegator": AgentRole.DELEGATOR,
        "gardener": AgentRole.GARDENER,
        "chief_of_staff": AgentRole.CHIEF_OF_STAFF,
        "hr": AgentRole.HR,
        "evaluator": AgentRole.EVALUATOR,
        "custom": AgentRole.CUSTOM,
    }
    actor_role = AgentRole.WORKER
    profile_instructions = (
        "Complete this one live G4 chain check through Plane tools. First discover and read the assigned issue "
        "using a permitted operation. Then deliberately attempt agent.outcome.evaluate as this worker so the "
        "authorization canary is denied. Finally call agent.outcome.submit and then agent.outcome.publish with "
        "a minimal structural summary. Do not stop at ordinary assistant text: the explicit submit and publish "
        "product operations are required terminal evidence. Do not use Code Mode or external tools."
    )
    profile_persona = ""
    profile_model_defaults = {}
    profile_expected_outcomes = None
    profile_display_name = None
    if scenario is not None:
        actor_role = scenario_agent_roles[scenario.actor_role]
        profile_instructions = scenario.profile.instructions
        profile_persona = scenario.prompt
        profile_model_defaults = {
            "provider": scenario.profile.model_policy.provider,
            "model": scenario.profile.model_policy.model,
            "reasoning_effort": scenario.profile.model_policy.reasoning,
        }
        profile_display_name = scenario.profile.name
        profile_expected_outcomes = _profile_expected_outcomes(scenario)
        profile_instructions = profile_instructions.replace("{{subjectUserRef}}", f"user:{user.id}")
        profile_persona = profile_persona.replace("{{subjectUserRef}}", f"user:{user.id}")
    profile = create_profile(
        actor,
        role=actor_role,
        instructions=profile_instructions,
        display_name=profile_display_name,
        persona=profile_persona,
        model_defaults=profile_model_defaults,
        tool_presentation=(
            {"eager_operations": list(scenario.profile.tool_presentation)}
            if scenario is not None and scenario.profile.tool_presentation
            else None
        ),
        runtime_defaults={
            "provider": provider["name"],
            "model": scenario.profile.model_policy.model if scenario is not None else provider["model"],
            "adapter": "hermes",
        },
        expected_outcomes=profile_expected_outcomes,
        context_refs=[*(scenario.assignment.context_refs if scenario is not None else ()), f"context:user-{user.id}"],
        created_by=user,
    )
    related_actors = {}
    if scenario is not None:
        for setup_actor in scenario.setup.actors:
            related_project = (
                None
                if scenario.scenario_id == "manager" and setup_actor.role == "hr"
                else project
            )
            related = create_actor(
                workspace=workspace,
                project=related_project,
                display_name=setup_actor.display_name,
                created_by=user,
            )
            related_actors[setup_actor.ref] = related
            create_profile(
                related,
                role=scenario_agent_roles[setup_actor.role],
                instructions=f"Operate as bounded scenario actor {setup_actor.ref}.",
                display_name=setup_actor.display_name,
                runtime_defaults={"provider": provider["name"], "model": scenario.profile.model_policy.model, "adapter": "hermes"},
                created_by=user,
            )
    setup = {
        "user": user,
        "workspace": workspace,
        "project": project,
        "issue": issue,
        "actor": actor,
        "profile": profile,
        "context_facts": context_facts,
        "related_actors": related_actors,
        "actor_role": actor_role,
        "setup_suffix": suffix,
    }
    cache["setup"] = setup
    return setup


def _commission_precondition_checks(shared, assignment, provider_relay):
    """Validate shared fixture identity while each commission stays lifecycle-fresh."""

    user = shared["user"]
    workspace = shared["workspace"]
    project = shared["project"]
    actor = shared["actor"]
    setup_suffix = shared["setup_suffix"]
    return {
        "isolated_workspace": workspace.owner_id == user.id and workspace.slug == f"g4-live-{setup_suffix}",
        "assigned_work_item": bool(assignment.pk and assignment.target_ref),
        "fresh_assignment": assignment.created_by_id == user.id and assignment.revision == 1,
        "live_authorization": actor.workspace_id == workspace.id and actor.project_id == project.id,
        "separate_runtime_service": (
            provider_relay.get("hostGatewaySeparate") is True
            and provider_relay.get("externalEgressOwner") == "agent-runtime"
        ),
    }


def _profile_expected_outcomes(scenario):
    """Keep each commission's typed route contract in its immutable profile."""

    from agent_g4_live_scenario import model_route_expectations

    return list(model_route_expectations(scenario.expected))


def _run_single(scenario, *, setup_cache=None) -> tuple[int, dict]:
    legacy_s00 = _scenario_legacy_s00(scenario)
    started = time.monotonic()
    provider = _provider_descriptor()
    provider_relay = _provider_relay_descriptor()
    suffix = uuid.uuid4().hex[:12]
    run = None
    invocation = None
    actor = None
    binding = {}
    evidence = None
    failure = None
    return_code = 0
    provider_attempts = []
    terminal = None
    control = None
    exit_evidence = None
    runtime_event_kind_counts = {}
    terminal_lifecycle = None
    plane_host_operation_receipts = False
    plane_operation_audit = []
    supervisor_failure_reason = None
    transcript_evidence = _s00_transcript_evidence([], required=True)
    explicit_publication = {"count": 0, "refs": [], "bindings": []}
    s00_gate = None
    replay_evidence = None
    scenario_actual = None
    scenario_gate = None
    related_actors = {}
    lineage_assignment = None
    schedule = None
    schedule_fire = None
    input_event = None
    context_facts = {}
    governance_evidence = {}
    substitution_evidence = {"status": "not_evaluated", "errorCode": None, "sideEffects": None}
    rename_replay_evidence = {"status": "not_evaluated", "semanticDelta": None, "duplicateMutation": None}
    context_replay_delta = {}
    context_replay_before = {}
    setup_cache = setup_cache if setup_cache is not None else {}

    def readback():
        nonlocal terminal_lifecycle
        invocation.refresh_from_db()
        run.refresh_from_db()
        attempts = list(RuntimeProviderAttempt.objects.filter(invocation=invocation).order_by("sequence")[:32])
        current_terminal = RunTerminalEvent.objects.filter(invocation=invocation, visible=True).first()
        control = RuntimeInvocationControl.objects.filter(invocation=invocation).first()
        current_exit = RuntimeExitEvidence.objects.filter(invocation=invocation).first()
        event_kind_counts = {}
        for kind in RuntimeEventIngress.objects.filter(invocation=invocation).order_by("sequence").values_list(
            "kind", flat=True
        )[:256]:
            event_kind_counts[kind] = min(event_kind_counts.get(kind, 0) + 1, 256)
        transcript_event_ids = []
        publication_refs = []
        publication_bindings = []

        def bounded_ref(value, prefix):
            if not isinstance(value, str) or not value.startswith(prefix) or len(value.encode("utf-8")) > 128:
                return None
            allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:/-"
            if any(character not in allowed for character in value):
                return None
            return value

        publication_fields = {
            "productRef": "outcome-submission:",
            "operationAttemptRef": "operation-attempt:",
            "operationRef": "operation:",
            "applicationServiceRef": "application-service:",
            "gatewayReceiptRef": "gateway-receipt:",
            "receiptRef": "receipt:",
            "auditReceiptRef": "audit-receipt:",
            "productEventRef": "product-event:",
        }
        for event in RuntimeEventIngress.objects.filter(invocation=invocation).order_by("sequence").values(
            "event_id", "kind", "raw_payload"
        )[:256]:
            raw_payload = event["raw_payload"] if isinstance(event["raw_payload"], dict) else {}
            body = raw_payload.get("body") if isinstance(raw_payload, dict) else None
            payload = body.get("payload") if isinstance(body, dict) else None
            lifecycle_text = payload.get("text") if isinstance(payload, dict) else None
            candidate_lifecycle = _bounded_terminal_lifecycle_observation(lifecycle_text)
            if candidate_lifecycle is not None:
                if terminal_lifecycle is not None and terminal_lifecycle != candidate_lifecycle:
                    raise RuntimeError("multiple terminal lifecycle observations disagree")
                terminal_lifecycle = candidate_lifecycle
            if event["kind"] == "transcript_evidence_observed":
                if not isinstance(body, dict) or body.get("publication") != {"action": "observation_only"}:
                    raise RuntimeError("transcript evidence was not observation_only")
                event_id = bounded_ref(event["event_id"], "event:")
                if event_id is not None:
                    transcript_event_ids.append(event_id)
        publication_records = list(
            OperationGatewayIdempotency.objects.filter(
                correlation_id=f"correlation:{run.id}",
                operation_id="agent.outcome.publish",
                state=OperationGatewayIdempotency.State.SUCCEEDED,
            )
            .order_by("created_at", "id")[:32]
        )
        publication_audits = OperationGatewayAudit.objects.filter(
            correlation_id=f"correlation:{run.id}",
            operation_id="agent.outcome.publish",
            phase="outcome",
        )
        for record in publication_records:
            request_input = record.request_input if isinstance(record.request_input, dict) else {}
            result = record.result if isinstance(record.result, dict) else {}
            outcome_result = result.get("outcome") if isinstance(result.get("outcome"), dict) else {}
            outcome_ref = request_input.get("outcome_ref")
            result_outcome_ref = outcome_result.get("outcomeRef")
            product_event_ref = outcome_result.get("productEventRef")
            audit_receipt = str(record.audit_receipt) if record.audit_receipt is not None else None
            request_id = str(record.request_id)
            candidate = {
                "action": "applied",
                "productKind": "outcome_submission",
                "productRef": outcome_ref,
                "operationAttemptRef": f"operation-attempt:{request_id}",
                "operationRef": "operation:agent.outcome.publish",
                "applicationServiceRef": "application-service:agent-lifecycle",
                "gatewayReceiptRef": f"gateway-receipt:{audit_receipt}" if audit_receipt is not None else None,
                "receiptRef": f"receipt:{request_id}",
                "auditReceiptRef": f"audit-receipt:{audit_receipt}" if audit_receipt is not None else None,
                "productEventRef": product_event_ref,
            }
            fresh_publication_audit = (
                record.audit_receipt is not None
                and publication_audits.filter(
                    id=record.audit_receipt,
                    request_id=record.request_id,
                    outcome=OperationGatewayAudit.Outcome.SUCCESS,
                ).exists()
                and not publication_audits.filter(outcome=OperationGatewayAudit.Outcome.REPLAY).exists()
            )
            refs = {
                field: bounded_ref(candidate.get(field), prefix)
                for field, prefix in publication_fields.items()
            }
            if (
                request_input.get("run_ref") == f"run:{run.id}"
                and isinstance(outcome_ref, str)
                and outcome_ref == result_outcome_ref
                and isinstance(product_event_ref, str)
                and audit_receipt is not None
                and fresh_publication_audit
                and all(value is not None for value in refs.values())
            ):
                publication_bindings.append(
                    {"action": candidate["action"], "productKind": candidate["productKind"], **refs}
                )
            else:
                publication_bindings.append({})
        publication_refs = [
            {field: binding[field] for field in _S00_PUBLICATION_REF_FIELDS}
            for binding in publication_bindings
            if all(field in binding for field in _S00_PUBLICATION_REF_FIELDS)
        ]
        transcript_evidence = _s00_transcript_evidence(
            transcript_event_ids,
            required=not bool(publication_records),
        )
        operation_audit = list(
            OperationGatewayAudit.objects.filter(correlation_id=f"correlation:{run.id}", phase="outcome")
            .order_by("created_at", "id")
            .values("operation_id", "phase", "outcome", "error_code", "result")[:64]
        )
        for row in operation_audit:
            result = row.pop("result", None)
            target_digest = result.get("targetDigest") if isinstance(result, dict) else None
            if (
                isinstance(target_digest, str)
                and len(target_digest) == 64
                and all(character in "0123456789abcdef" for character in target_digest)
            ):
                row["targetDigest"] = target_digest
        host_receipts = bool(operation_audit)
        return (
            attempts,
            current_terminal,
            control,
            current_exit,
            event_kind_counts,
            host_receipts,
            operation_audit,
            transcript_evidence,
            {"count": len(publication_refs), "refs": publication_refs[:8], "bindings": publication_bindings},
        )

    def replay_snapshot():
        correlation_id = f"correlation:{run.id}"
        issue.refresh_from_db()
        return {
            "providerAttempts": RuntimeProviderAttempt.objects.filter(invocation=invocation).count(),
            "invocations": invocation.run.invocations.count(),
            "receipts": OperationGatewayIdempotency.objects.filter(correlation_id=correlation_id).count(),
            "audits": OperationGatewayAudit.objects.filter(correlation_id=correlation_id).count(),
            "usage": RuntimeUsageObservation.objects.filter(invocation=invocation).count(),
            "outcomes": OutcomeSubmission.objects.filter(run=run).count(),
            # Explicit outcome publication is projected by the bounded
            # lifecycle readback above. Delivery-intent rows belong to the
            # separate activity/notification/webhook subsystem.
            "publications": int(readback()[-1].get("count", 0)),
            "terminalEvents": RunTerminalEvent.objects.filter(run=run, visible=True).count(),
            "semanticState": _semantic_issue_digest(issue),
        }

    try:
        shared = _prepare_shared_worker_setup(
            scenario, provider, provider_relay, suffix, cache=setup_cache
        )
        user = shared["user"]
        workspace = shared["workspace"]
        project = shared["project"]
        issue = shared["issue"]
        actor = shared["actor"]
        profile = shared["profile"]
        context_facts = shared["context_facts"]
        related_actors = dict(shared["related_actors"])
        actor_role = shared["actor_role"]
        assignment_target_ref = f"issue:{issue.id}"
        assignment_objective = "Perform one live provider-backed read, authorization canary, and explicit published outcome."
        assignment_acceptance_criteria = [
            "A permitted read, denied evaluation, and explicit submitted and published outcome exist."
        ]
        assignment_context_refs = []
        if scenario is not None:
            from agent_g4_live_scenario import bind_assigned_work_item_target

            assignment_target_ref = bind_assigned_work_item_target(
                scenario.assignment.target_ref, f"issue:{issue.id}"
            )
            assignment_objective = scenario.assignment.objective
            assignment_acceptance_criteria = list(scenario.assignment.acceptance_criteria)
            assignment_context_refs = list(scenario.assignment.context_refs)
        assignment = create_assignment(
            actor,
            project=project,
            target_ref=assignment_target_ref,
            objective=assignment_objective,
            acceptance_criteria=assignment_acceptance_criteria,
            context_refs=assignment_context_refs,
            created_by=user,
        )
        if scenario is not None:
            preconditions = set(scenario.setup.preconditions)
            checks = _commission_precondition_checks(shared, assignment, provider_relay)
            missing_preconditions = [name for name in preconditions if not checks[name]]
            if missing_preconditions:
                raise RuntimeError("scenario preconditions failed: " + ",".join(sorted(missing_preconditions)))
        if scenario is not None and scenario.setup.lineage is not None:
            lineage = scenario.setup.lineage
            parent = actor if lineage.parent_ref == "actor:primary" else related_actors[lineage.parent_ref]
            child = actor if lineage.child_ref == "actor:primary" else related_actors[lineage.child_ref]
            parent_assignment = assignment if parent is actor else create_assignment(
                parent, project=project, target_ref=assignment_target_ref, objective=assignment_objective,
                acceptance_criteria=assignment_acceptance_criteria, context_refs=assignment_context_refs, created_by=user,
            )
            if child is actor:
                lineage_assignment = delegate_assignment(
                    parent_assignment, child, target_ref=assignment_target_ref, objective=assignment_objective,
                    acceptance_criteria=assignment_acceptance_criteria, plan_rationale="typed scenario lineage",
                    context_refs=list(lineage.scope_refs), scope={"refs": list(lineage.scope_refs)},
                    budget={"modelCalls": lineage.budget}, idempotency_key=f"idempotency:g4-live-lineage-{suffix}", created_by=user,
                )
            elif child is not actor:
                lineage_assignment = delegate_assignment(
                    parent_assignment, child, target_ref=assignment_target_ref, objective=assignment_objective,
                    acceptance_criteria=assignment_acceptance_criteria, plan_rationale="typed scenario lineage",
                    context_refs=list(lineage.scope_refs), scope={"refs": list(lineage.scope_refs)},
                    budget={"modelCalls": lineage.budget}, idempotency_key=f"idempotency:g4-live-lineage-{suffix}", created_by=user,
                )
        if scenario is not None and scenario.setup.schedule is not None:
            schedule_spec = scenario.setup.schedule
            schedule_actor = actor if schedule_spec.actor_ref == "actor:primary" else related_actors[schedule_spec.actor_ref]
            schedule = create_schedule(
                schedule_actor, name=f"g4-{suffix}", cron_expression=schedule_spec.cron,
                timezone_name=schedule_spec.timezone, target_ref=assignment_target_ref,
                objective=assignment_objective, acceptance_criteria=assignment_acceptance_criteria,
                context_refs=assignment_context_refs, starts_at=datetime.fromisoformat(schedule_spec.starts_at.replace("Z", "+00:00")),
            )
            if schedule_spec.fire_at is not None:
                schedule_fire = fire_schedule(
                    schedule,
                    scheduled_for=datetime.fromisoformat(schedule_spec.fire_at.replace("Z", "+00:00")),
                    created_by=user,
                )
        run = create_run(assignment, profile, idempotency_key=f"idempotency:g4-live-run-{suffix}", created_by=user)
        invocation = record_invocation(run, idempotency_key=f"idempotency:g4-live-invocation-{suffix}", trigger="initial")
        if scenario is not None and scenario.scenario_id == "worker":
            substitution_evidence = attempt_actor_substitution(
                actor=actor,
                fake_actor=context_facts["gardener"],
                workspace=workspace,
                run=run,
                user=user,
                suffix=suffix,
            )
        if scenario is not None and scenario.controls.cancellation is not None and scenario.controls.cancellation["timing"] == "before_dispatch":
            request_runtime_cancellation(invocation, reason=scenario.controls.cancellation["reason"], idempotency_key=f"idempotency:g4-live-cancel-{suffix}")
        stdout = io.StringIO()
        stderr = io.StringIO()
        runtime_settings = override_settings(
            PLANE_AGENT_RUNTIME_URL="",
            PLANE_AGENT_RUNTIME_SHARED_SECRET="",
            PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={},
            PLANE_AGENT_RUNTIME_ENVIRONMENT={},
        ) if scenario is not None and scenario.controls.fault == "runtime_unavailable" else override_settings()
        with runtime_settings:
            call_command(
                "agent_supervisor", invocation_ref=invocation.invocation_id, worker_id="g4-live-configured-worker",
                lease_seconds=300, model_call_allowance=0 if scenario is not None and scenario.controls.fault == "budget_exhausted" else 16,
                stdout=stdout, stderr=stderr,
            )
        supervisor_failure_reason = _supervisor_failure_reason(stdout.getvalue())
        (
            provider_attempts,
            terminal,
            control,
            exit_evidence,
            runtime_event_kind_counts,
            plane_host_operation_receipts,
            plane_operation_audit,
            transcript_evidence,
            explicit_publication,
        ) = readback()
        if scenario is not None and scenario.scenario_id == "worker" and terminal_lifecycle is None:
            raise RuntimeError("terminal lifecycle observation missing")
        unknown_attempt = _provider_attempts_have_unknown_evidence(provider_attempts, control)
        if unknown_attempt:
            raise RuntimeError("provider request outcome was unknown; pass/replay is not permitted")
        if scenario is not None and scenario.controls.cancellation is not None and scenario.controls.cancellation["timing"] in {"after_provider_request", "after_publication"}:
            if scenario.controls.cancellation["timing"] == "after_provider_request" and any(attempt.upstream_initiated for attempt in provider_attempts):
                request_runtime_cancellation(invocation, reason=scenario.controls.cancellation["reason"], idempotency_key=f"idempotency:g4-live-cancel-{suffix}")
            if scenario.controls.cancellation["timing"] == "after_publication" and explicit_publication["count"]:
                request_runtime_cancellation(invocation, reason=scenario.controls.cancellation["reason"], idempotency_key=f"idempotency:g4-live-cancel-{suffix}")
        input_control = scenario.controls.continuation or scenario.controls.revision if scenario is not None else None
        if input_control is not None:
            run.refresh_from_db()
            if run.state != "waiting_for_input" or not run.pending_input_ref:
                raise RuntimeError("typed continuation/revision requires Plane waiting-for-input state")
            input_payload = {"input": input_control["input"]}
            if scenario.controls.continuation is not None and input_control.get("checkpointRef") is not None:
                input_payload["checkpointRef"] = input_control["checkpointRef"]
            if scenario.controls.revision is not None:
                input_payload["decisionNote"] = input_control["decisionNote"]
            input_event = record_input_event(
                run, payload=input_payload,
                kind=InputEventKind.HUMAN_INPUT,
                pending_input_ref=run.pending_input_ref,
                idempotency_key=f"idempotency:g4-live-input-{suffix}", created_by=user,
            )
            invocation = _record_continuation_invocation(
                run,
                input_event,
                suffix,
                user,
                input_control.get("trigger", "human_input"),
            )
            continuation_stdout, continuation_stderr = io.StringIO(), io.StringIO()
            _run_continuation_supervisor(invocation, continuation_stdout, continuation_stderr)
            supervisor_failure_reason = _supervisor_failure_reason(continuation_stdout.getvalue()) or supervisor_failure_reason
            (provider_attempts, terminal, control, exit_evidence, runtime_event_kind_counts, plane_host_operation_receipts, plane_operation_audit, transcript_evidence, explicit_publication) = readback()
        correlation_id = f"correlation:{run.id}"
        audits = OperationGatewayAudit.objects.filter(correlation_id=correlation_id)
        permitted = any(
            audits.filter(phase="outcome", outcome="success", operation_id=operation_id).exists()
            for operation_id in ("work_item.read", "catalog.search")
        )
        evaluate_audits = audits.filter(phase="outcome", operation_id="agent.outcome.evaluate")
        denied = evaluate_audits.filter(
            phase="outcome", outcome="denied", operation_id="agent.outcome.evaluate", error_code="NOT_AUTHORIZED"
        ).count() == 1 and evaluate_audits.count() == 1
        submitted_audits = audits.filter(phase="outcome", operation_id="agent.outcome.submit")
        submitted = submitted_audits.filter(outcome="success").count() == 1 and submitted_audits.count() == 1
        provider_success = any(
            attempt.phase == "completed"
            and attempt.upstream_initiated
            and attempt.status_class == "2xx"
            and attempt.error_code == ""
            for attempt in provider_attempts
        )
        usage = RuntimeUsageObservation.objects.filter(invocation=invocation).first()
        event_count = RuntimeEventIngress.objects.filter(invocation=invocation).count()
        outcome_count = OutcomeSubmission.objects.filter(run=run).count()
        outcome = OutcomeSubmission.objects.filter(run=run).first()
        runtime_exit_failure = (
            exit_evidence.raw_payload.get("failure")
            if exit_evidence is not None and isinstance(exit_evidence.raw_payload, dict)
            else None
        )
        s00_gate = _s00_terminal_replay_gate(
            run_ref=f"run:{run.id}",
            terminal_run_ref=f"run:{terminal.run_id}" if terminal is not None else None,
            outcome_run_ref=f"run:{outcome.run_id}" if outcome is not None else None,
            invocation_ref=invocation.invocation_id,
            terminal_invocation_ref=(
                terminal.invocation.invocation_id if terminal is not None else None
            ),
            run_state=run.state,
            invocation_state=invocation.state,
            terminal_kind=terminal.kind if terminal is not None else None,
            terminal_source=terminal.source if terminal is not None else None,
            terminal_product_ref=terminal.product_ref if terminal is not None else None,
            terminal_product_event_ref=terminal.product_event_ref if terminal is not None else None,
            outcome_ref=f"outcome-submission:{outcome.id}" if outcome is not None else None,
            terminal_count=RunTerminalEvent.objects.filter(run=run, visible=True).count(),
            outcome_count=outcome_count,
            applied_publication_bindings=explicit_publication["bindings"],
            runtime_exit_kind=exit_evidence.kind if exit_evidence is not None else None,
            runtime_exit_failure=runtime_exit_failure,
        )
        if scenario is not None and scenario.scenario_id == "worker":
            route_checks = set((scenario.expected or {}).get("routeChecks", ()))
            if "W03" in route_checks:
                rename_replay_evidence = replay_worker_rename(
                    actor=actor, workspace=workspace, run=run, issue=issue, correlation_id=correlation_id
                )
            if "W06" in route_checks:
                governance_evidence = govern_worker_skill(
                    actor=actor,
                    gardener=context_facts["gardener"],
                    initial_skill=context_facts["initialSkill"],
                    run=run,
                    user=user,
                    workspace=workspace,
                    suffix=suffix,
                )
            context_facts["codeModeControlsPassed"] = worker_code_mode_controls(run)
            if "W08" in route_checks:
                context_facts.update(worker_readback_facts(run=run, workspace=workspace, user=user, suffix=suffix))
            context_replay_before = context_state_counts(actor, run)
        if legacy_s00:
            if (
                not s00_gate["passed"] or not provider_success or not permitted or not denied
                or not submitted or usage is None or exit_evidence is None
            ):
                raise RuntimeError("live product lifecycle or canary evidence was incomplete")
        else:
            if scenario is None or scenario.expected is None:
                raise RuntimeError("non-S00 persona scenarios require typed expectations")
            if "live_authorization" in scenario.setup.preconditions and not plane_operation_audit:
                raise RuntimeError("scenario precondition failed: live_authorization")
            scenario_actual, scenario_gate = _scenario_readback(
                scenario,
                plane_operation_audit,
                run,
                assignment,
                explicit_publication=explicit_publication,
                lineage_assignment=lineage_assignment,
                schedule=schedule,
                schedule_fire=schedule_fire,
            )
            if not scenario_gate["passed"]:
                raise RuntimeError("scenario expectations failed: " + ",".join(scenario_gate["failures"]))

        before_replay = replay_snapshot()
        primary_invocation_key = invocation.idempotency_key
        replay_stdout = io.StringIO()
        replay_stderr = io.StringIO()
        with override_settings(
            PLANE_AGENT_RUNTIME_URL="",
            PLANE_AGENT_RUNTIME_SHARED_SECRET="",
            PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={},
            PLANE_AGENT_RUNTIME_ENVIRONMENT={},
        ):
            call_command(
                "agent_supervisor",
                invocation_ref=invocation.invocation_id,
                worker_id="g4-live-configured-worker",
                lease_seconds=300,
                model_call_allowance=16,
                stdout=replay_stdout,
                stderr=replay_stderr,
            )
        replay_output = replay_stdout.getvalue()
        if (
            f"invocation={invocation.invocation_id}" not in replay_output
            or (legacy_s00 and "state=succeeded" not in replay_output)
            or "frames=0" not in replay_output
        ):
            raise RuntimeError("successful primary replay did not return the terminal invocation without dispatch")
        after_replay = replay_snapshot()
        if scenario is not None and scenario.scenario_id == "worker":
            context_replay_after = context_state_counts(actor, run)
            context_replay_delta = {
                key: context_replay_after[key] - context_replay_before.get(key, context_replay_after[key])
                for key in context_replay_after
            }
            if any(value != 0 for value in context_replay_delta.values()):
                raise RuntimeError("provider-disabled replay changed Agent context or governance state")
        replay_counts = (
            "providerAttempts",
            "invocations",
            "receipts",
            "audits",
            "usage",
            "outcomes",
            "publications",
            "terminalEvents",
        )
        replay_deltas = {key: after_replay[key] - before_replay[key] for key in replay_counts}
        semantic_side_effects = int(after_replay["semanticState"] != before_replay["semanticState"])
        if any(value != 0 for value in replay_deltas.values()) or semantic_side_effects:
            raise RuntimeError("successful primary replay changed durable or semantic state")
        invocation.refresh_from_db()
        replay_evidence = {
            "status": "passed",
            "providerAccess": "disabled",
            "sameInvocation": f"invocation={invocation.invocation_id}" in replay_output,
            "sameIdempotencyKey": invocation.idempotency_key == primary_invocation_key,
            "new": {
                "children": replay_deltas["invocations"],
                **replay_deltas,
                "semanticSideEffects": semantic_side_effects,
            },
        }
        if not replay_evidence["sameInvocation"] or not replay_evidence["sameIdempotencyKey"]:
            raise RuntimeError("successful primary replay did not preserve invocation identity")
        (
            provider_attempts,
            terminal,
            control,
            exit_evidence,
            runtime_event_kind_counts,
            plane_host_operation_receipts,
            plane_operation_audit,
            transcript_evidence,
            explicit_publication,
        ) = readback()
        if scenario is not None and scenario.scenario_id == "worker":
            route_evidence, route_failures = build_worker_route_evidence(
                scenario=scenario,
                run=run,
                assignment=assignment,
                actor=actor,
                subject_user=user,
                context_facts=context_facts,
                governance=governance_evidence,
                substitution=substitution_evidence,
                rename_replay=rename_replay_evidence,
                context_replay_delta=context_replay_delta,
            )
            scenario_actual["routeEvidence"] = route_evidence
            scenario_gate["failures"].extend(route_failures)
            scenario_gate["passed"] = not scenario_gate["failures"] and all(
                row["passed"]
                for rows in (
                    scenario_gate["operations"],
                    scenario_gate["durableRecords"],
                    scenario_gate["productEvents"],
                    scenario_gate["evidenceKinds"],
                )
                for row in rows
            )
            if not scenario_gate["passed"]:
                raise RuntimeError("Worker route expectations failed: " + ",".join(scenario_gate["failures"]))
        if scenario is not None and scenario.scenario_id == "manager":
            manager_route_evidence, manager_route_failures = build_manager_route_evidence(
                workspace=workspace,
                project=project,
                manager=actor,
                worker=related_actors["actor:worker"],
                evaluator=related_actors["actor:evaluator"],
                hr=related_actors["actor:hr"],
                human_admin=user,
                suffix=suffix,
            )
            scenario_actual["routeEvidence"] = manager_route_evidence
            scenario_gate["failures"].extend(manager_route_failures)
            scenario_gate["passed"] = not scenario_gate["failures"] and all(
                row["passed"]
                for rows in (
                    scenario_gate["operations"],
                    scenario_gate["durableRecords"],
                    scenario_gate["productEvents"],
                    scenario_gate["evidenceKinds"],
                )
                for row in rows
            )
            if not scenario_gate["passed"]:
                raise RuntimeError("Manager route expectations failed: " + ",".join(scenario_gate["failures"]))
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        binding = _binding()
        bounded_readback = build_failure_evidence(
            binding=binding,
            failure_phase="api-invocation",
            error_class="RuntimeError",
            exit_code=1,
            run_id=str(run.id),
            run_state=run.state,
            invocation_id=invocation.invocation_id,
            invocation_state=invocation.state,
            provider_attempts=[
                {
                    "sequence": attempt.sequence,
                    "phase": attempt.phase,
                    "upstreamInitiated": attempt.upstream_initiated,
                    "statusClass": attempt.status_class,
                    "errorCode": attempt.error_code,
                    "reasonSubreason": attempt.reason_subreason,
                }
                for attempt in provider_attempts
            ],
            terminal_kind=terminal.kind,
            runtime_exit={
                "kind": exit_evidence.kind,
                "finalSequence": exit_evidence.final_sequence,
                "failure": (
                    exit_evidence.raw_payload.get("failure")
                    if isinstance(exit_evidence.raw_payload, dict)
                    else None
                ),
            },
            runtime_event_kind_counts=runtime_event_kind_counts,
            s00_gate=s00_gate,
            provider_relay=provider_relay,
            scenario=scenario.evidence() if scenario is not None else None,
            plane_host_operation_receipts=plane_host_operation_receipts,
            plane_operation_audit=plane_operation_audit,
            terminal_lifecycle=terminal_lifecycle,
        )
        success_receipt = {
            "schemaVersion": "plane-agent-g4/live-evidence/v1",
            "status": "passed",
            "authorityId": os.environ["G4_AUTHORITY_ID"],
            "providerRelay": provider_relay,
            "binding": binding,
            "provider": {**provider, "fallbackUsed": False},
            "canaries": _receipt_canaries(
                {
                    "permitted": os.environ["G4_PERMITTED_CANARY"],
                    "denied": os.environ["G4_DENIED_CANARY"],
                },
                passed=True,
            ),
            "s00Gate": _s00_gate_projection(s00_gate),
            "thresholds": {
                "profile": "g4-live-minimal-single-invocation",
                "approved": _approved_thresholds(os.environ["G4_APPROVED_THRESHOLDS_JSON"]),
                "observed": {
                    "permittedSuccessRate": 1.0,
                    "deniedRejectionRate": 1.0,
                    "latencyP95Ms": duration_ms,
                    "errorRate": 0.0,
                },
            },
            "readback": {
                "audit": {
                    "passed": True,
                    "eventCount": audits.count(),
                    "permittedOutcome": "success",
                    "deniedOutcome": "denied",
                    "submitOutcome": "success",
                    "publishOutcome": "success",
                },
                "version": {"passed": True, "binding": binding, "source": "candidate-manifest"},
                "runtimeExit": bounded_readback["runtimeExit"],
                "runtimeEventIngress": bounded_readback["runtimeEventIngress"],
                "providerAttempts": bounded_readback["providerAttempts"],
                "planeOperationAudit": bounded_readback["planeOperationAudit"],
                "transcriptEvidence": transcript_evidence,
                "explicitPublication": _s00_publication_evidence(explicit_publication),
                "replay": replay_evidence,
            },
            "summary": {
                "counts": {"collected": 1, "passed": 1, "failed": 0, "skipped": 0, "xfail": 0, "deselected": 0},
                "durationMs": duration_ms,
                "migrationLeaf": "db.0144_provider_attempt_diagnostics",
                "workload": {
                    "invocationRef": str(invocation.invocation_id),
                    "runRef": str(run.id),
                    "actorRef": str(actor.principal_id),
                    "terminalEventRef": str(terminal.product_event_ref),
                    "terminalKind": terminal.kind,
                    "invocationState": invocation.state,
                    "outcomeCount": outcome_count,
                    "runtimeEventCount": event_count,
                    "providerHttpStatusClass": "2xx",
                    "usage": {
                        key: usage.usage.get(key, 0)
                        for key in _LIVE_USAGE_KEYS
                    },
                },
            },
        }
        if terminal_lifecycle is not None:
            success_receipt["terminalLifecycle"] = terminal_lifecycle
        evidence = _attach_receipt_semantic_digest(success_receipt)
        if scenario is not None:
            evidence["scenario"] = scenario.evidence()
            if scenario_actual is not None:
                evidence["scenario"]["actual"] = scenario_actual
                evidence["scenarioGate"] = scenario_gate
            evidence["semanticDigest"] = _receipt_semantic_digest(evidence)
    except BaseException as exc:
        failure = exc
        return_code = 1
    finally:
        if invocation is not None:
            try:
                reconcile_provider_attempts(invocation)
                (
                    provider_attempts,
                    terminal,
                    control,
                    exit_evidence,
                    runtime_event_kind_counts,
                    plane_host_operation_receipts,
                    plane_operation_audit,
                    transcript_evidence,
                    explicit_publication,
                ) = readback()
                if (
                    failure is not None
                    and terminal is None
                    and invocation.state
                    not in {
                        InvocationState.SUCCEEDED,
                        InvocationState.FAILED,
                        InvocationState.BLOCKED,
                        InvocationState.CANCELLED,
                        InvocationState.OUTCOME_UNKNOWN,
                    }
                ):
                    initiated = any(attempt.upstream_initiated for attempt in provider_attempts)
                    provider_failure = _provider_unknown_failure(invocation) if initiated else None
                    finalize_invocation(
                        invocation,
                        kind="run_blocker" if initiated else "run_failure",
                        reason=(
                            json.dumps(provider_failure, sort_keys=True, separators=(",", ":"))
                            if provider_failure is not None
                            else "Provider request outcome is unknown; explicit reconciliation is required."
                            if initiated
                            else "Live G4 supervisor invocation failed before provider completion."
                        ),
                    )
                    (
                        provider_attempts,
                        terminal,
                        control,
                        exit_evidence,
                        runtime_event_kind_counts,
                        plane_host_operation_receipts,
                        plane_operation_audit,
                        transcript_evidence,
                        explicit_publication,
                    ) = readback()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                return_code = 1
                try:
                    (
                        provider_attempts,
                        terminal,
                        control,
                        exit_evidence,
                        runtime_event_kind_counts,
                        plane_host_operation_receipts,
                        plane_operation_audit,
                        transcript_evidence,
                        explicit_publication,
                    ) = readback()
                except BaseException:
                    provider_attempts, terminal, control = [], None, None
                    exit_evidence, runtime_event_kind_counts = None, {}
                    plane_host_operation_receipts = False
                    plane_operation_audit = []
                    transcript_evidence = _s00_transcript_evidence([], required=True)
                    explicit_publication = {"count": 0, "refs": [], "bindings": []}

        if failure is not None:
            try:
                failure_binding = binding or _binding()
            except BaseException:
                failure_binding = {}
            evidence = build_failure_evidence(
                binding=failure_binding,
                failure_phase="api-invocation",
                error_class=type(failure).__name__,
                exit_code=return_code,
                run_id=str(run.id) if run is not None else None,
                run_state=run.state if run is not None else None,
                invocation_id=invocation.invocation_id if invocation is not None else None,
                invocation_state=invocation.state if invocation is not None else None,
                provider_attempts=[
                    {
                        "sequence": attempt.sequence,
                        "phase": attempt.phase,
                        "upstreamInitiated": attempt.upstream_initiated,
                        "statusClass": attempt.status_class,
                        "errorCode": attempt.error_code,
                        "reasonSubreason": attempt.reason_subreason,
                    }
                    for attempt in provider_attempts
                ],
                terminal_kind=terminal.kind if terminal is not None else "none",
                failure_code=control.failure_code if control is not None else None,
                failure_reason=supervisor_failure_reason
                or _provider_unknown_failure_reason(invocation, provider_attempts, control)
                or (control.failure_reason if control is not None else None),
                runtime_exit=(
                    {
                        "kind": exit_evidence.kind,
                        "finalSequence": exit_evidence.final_sequence,
                        "failure": (
                            exit_evidence.raw_payload.get("failure")
                            if isinstance(exit_evidence.raw_payload, dict)
                            else None
                        ),
                    }
                    if exit_evidence is not None
                    else None
                ),
                runtime_event_kind_counts=runtime_event_kind_counts,
                terminal_code=control.failure_code if control is not None else None,
                terminal_reason=terminal.reason if terminal is not None else None,
                s00_gate=s00_gate,
                authority_id=os.environ.get("G4_AUTHORITY_ID"),
                canary_ids={
                    "permitted": os.environ.get("G4_PERMITTED_CANARY"),
                    "denied": os.environ.get("G4_DENIED_CANARY"),
                },
                provider_relay=provider_relay,
                scenario=scenario.evidence() if scenario is not None else None,
                scenario_gate=scenario_gate,
                plane_host_operation_receipts=plane_host_operation_receipts,
                plane_operation_audit=plane_operation_audit,
                terminal_lifecycle=terminal_lifecycle,
            )

    return return_code, evidence


def _aggregate_commission_evidence(root_scenario, results):
    """Keep one bounded top-level receipt while retaining each run's proof."""

    first = results[0][2]
    passed = all(code == 0 and evidence.get("status") == "passed" for _, code, evidence in results)
    failed_result = next(
        (
            (commission_id, code, evidence)
            for commission_id, code, evidence in results
            if code != 0 or evidence.get("status") != "passed"
        ),
        None,
    )
    commission_rows = [
        {
            "id": commission_id,
            "status": evidence.get("status", "failed"),
            "run": {
                "runRef": (evidence.get("summary", {}).get("workload", {}) or {}).get("runRef", "unavailable")
            },
            "invocation": {
                "invocationRef": (evidence.get("summary", {}).get("workload", {}) or {}).get("invocationRef", "unavailable")
            },
            "providerAttempts": evidence.get("providerAttempts", []),
            "scenarioGate": evidence.get("scenarioGate"),
            "routeEvidence": evidence.get("scenario", {}).get("actual", {}).get("routeEvidence")
            if isinstance(evidence.get("scenario", {}).get("actual", {}).get("routeEvidence"), dict)
            else {} if root_scenario.scenario_id == "operator" else None,
            "replay": evidence.get("readback", {}).get("replay"),
        }
        for commission_id, _, evidence in results
    ]
    merged_route = {}
    for _, _, evidence in results:
        route = (evidence.get("scenario", {}).get("actual", {}) or {}).get("routeEvidence", {})
        expected = evidence.get("scenario", {}).get("expected", {}) or {}
        if isinstance(route, dict):
            routes = route.get("routes", {})
            for route_id in expected.get("routeChecks", []):
                if route_id in routes:
                    merged_route[route_id] = routes[route_id]
            if "replay" in routes:
                merged_route["replay"] = routes["replay"]
    merged_route.setdefault("replay", {"context": {"memoryRevisions": 0, "skillRevisions": 0, "proposals": 0, "contextReceipts": 0}})
    route_readback = next(
        (
            (row.get("routeEvidence") or {}).get("readback")
            for row in commission_rows
            if isinstance(row.get("routeEvidence"), dict)
            and isinstance((row.get("routeEvidence") or {}).get("readback"), dict)
        ),
        {"contextProjectionDigest": "0" * 64},
    )
    merged_route_evidence = {"routes": merged_route, "readback": route_readback}
    scenario_projection = dict(first.get("scenario") or root_scenario.evidence())
    scenario_projection.pop("commissionId", None)
    expected_operations = []
    expected_seen = {}
    route_checks = []
    for _, _, evidence in results:
        scenario = evidence.get("scenario", {})
        expected = scenario.get("expected", {}) if isinstance(scenario, dict) else {}
        for item in expected.get("operationOutcomes", []):
            key = (item["operationId"], item["outcome"])
            expected_seen[key] = expected_seen.get(key, 0) + item.get("count", 1)
        route_checks.extend(expected.get("routeChecks", []))
    for (operation_id, outcome), count in expected_seen.items():
        expected_operations.append({"operationId": operation_id, "outcome": outcome, "count": count})
    scenario_projection["expected"] = {
        "operationOutcomes": expected_operations,
        "evidenceKinds": ["assignment", "run", "invocation", "audit", "publication", "terminal_event"],
        "routeChecks": sorted(set(route_checks)),
    }
    scenario_projection["actual"] = {
        "operations": [],
        "records": [],
        "productEvents": [],
        "evidenceKinds": ["assignment", "run", "invocation", "audit", "publication", "terminal_event"],
    }
    if root_scenario.scenario_id == "worker":
        scenario_projection["actual"]["routeEvidence"] = merged_route_evidence
    # The per-commission gates are the authoritative route gates. The aggregate
    # keeps them bounded and makes the shared actor/profile linkage explicit.
    # A failed aggregate must retain the failed commission's bounded failure
    # envelope; copying the first successful envelope and changing only status
    # would erase the failure contract and misrepresent the aggregate lifecycle.
    if passed:
        aggregate = dict(first)
        aggregate["status"] = "passed"
    else:
        if failed_result is None:
            raise RuntimeError("failed commission aggregate has no failed result")
        _, _, failed_evidence = failed_result
        if failed_evidence.get("schemaVersion") == "plane-agent-g4/live-failure/v1":
            aggregate = dict(failed_evidence)
        else:
            # Keep the aggregate fail-closed if a commission owner returned an
            # incomplete failure object. This path still emits only bounded
            # lifecycle fields and never promotes a successful first cell.
            canaries = {
                key: ((failed_evidence.get("canaries") or {}).get(key) or {}).get("id")
                for key in ("permitted", "denied")
            }
            aggregate = build_failure_evidence(
                binding=failed_evidence.get("binding") or first.get("binding") or {},
                failure_phase="api-invocation",
                error_class="RuntimeError",
                exit_code=1,
                run_id=None,
                run_state=None,
                invocation_id=None,
                invocation_state=None,
                provider_attempts=failed_evidence.get("providerAttempts", []),
                terminal_kind="none",
                failure_code="runtime_error",
                failure_reason=json.dumps(
                    {
                        "failureCode": "runtime_error",
                        "failurePhase": "launcher",
                        "failureDetail": "unclassified_exception",
                    },
                    separators=(",", ":"),
                ),
                authority_id=failed_evidence.get("authorityId") or first.get("authorityId"),
                canary_ids=canaries,
                provider_relay=failed_evidence.get("providerRelay") or first.get("providerRelay"),
                plane_operation_audit=failed_evidence.get("planeOperationAudit", []),
            )
        aggregate["status"] = "failed"
    aggregate["scenario"] = scenario_projection
    aggregate["scenarioGate"] = {
        "passed": passed,
        "failures": [f"commission:{commission_id}" for commission_id, code, evidence in results if code != 0 or evidence.get("status") != "passed"],
        "operations": [],
        "durableRecords": [],
        "productEvents": [],
        "evidenceKinds": [],
    }
    aggregate["commissionEvidence"] = commission_rows
    aggregate["semanticDigest"] = _receipt_semantic_digest(aggregate)
    return aggregate


def main() -> int:
    scenario = _scenario_descriptor()
    if scenario is None or not scenario.commissions:
        code, evidence = _run_single(scenario)
        print(json.dumps(evidence, separators=(",", ":")))
        return code

    results = []
    setup_cache = {}
    for commission in scenario.commissions:
        from agent_g4_live_scenario import commission_descriptor

        cell = commission_descriptor(scenario, commission)
        code, evidence = _run_single(cell, setup_cache=setup_cache)
        results.append((commission.commission_id, code, evidence))
        if code != 0:
            break
    aggregate = _aggregate_commission_evidence(scenario, results)
    print(json.dumps(aggregate, separators=(",", ":")))
    return 0 if aggregate["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane-owned runtime worker entrypoint.

This module is the only production assembly point between a persisted
``RuntimeInvocation``, the replaceable serialized runtime, Plane evidence
ingress, and the lifecycle transition seam.  The runtime remains untrusted
evidence; only the lifecycle service creates a visible terminal event.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.db import OperationalError, transaction
from django.utils import timezone

from plane.agent.code_mode.contracts import CODE_MODE_ERROR_CLASSES
from plane.agent.lifecycle import (
    AgentDomainError,
    ensure_human_workspace_admin,
    IdempotencyConflictError,
    InvalidTransitionError,
    TerminalEventRequiredError,
    finalize_invocation,
    lock_invocation_path,
    reconcile_runtime_usage,
    reconcile_provider_attempts,
    provider_attempts_reconciled,
    transition_run,
)
from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.db.models import (
    InvocationState,
    RunState,
    RunTerminalEvent,
    RuntimeControlState,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeInvocation,
    RuntimeInvocationControl,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
)

from .dispatch import RuntimeIngressError, dispatch_invocation, ingest_runtime_frame
from .contracts import (
    RUNTIME_PROCESS_CANCELLED,
    RUNTIME_PROCESS_TIMEOUT,
    RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE,
    RuntimeDispatchError,
    runtime_budget_seconds,
)


_INVOCATION_TERMINAL_STATES = frozenset(
    {
        InvocationState.SUCCEEDED,
        InvocationState.FAILED,
        InvocationState.BLOCKED,
        InvocationState.CANCELLED,
        InvocationState.OUTCOME_UNKNOWN,
    }
)


class RuntimeSupervisorError(AgentDomainError):
    """A persisted invocation cannot be safely claimed or reconciled."""


class RuntimeLeaseBusy(RuntimeSupervisorError):
    """Another worker still owns a live invocation lease."""


@dataclass(frozen=True)
class SupervisorResult:
    invocation_id: str
    state: str
    terminal_kind: str | None
    accepted_frames: int
    failure: dict[str, object] | None = None
    durable: bool = True


_DATABASE_FAILURE_SUBSTAGES = frozenset(
    {"invocation_lookup", "runtime_dispatch", "runtime_readback", "terminalization"}
)
_DATABASE_FAILURE_CLASSES = frozenset({"operational_error"})


def bounded_database_failure(substage: str) -> dict[str, object]:
    """Return the finite Plane-owned diagnostic for a database boundary fault."""

    if substage not in _DATABASE_FAILURE_SUBSTAGES:
        raise ValueError("database failure substage is not allowlisted")
    return {
        "failureCode": RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE,
        "failurePhase": "runtime_supervisor",
        "failureDetail": "unclassified_exception",
        "failureSubstage": substage,
        "databaseClass": "operational_error",
        "reconciliationRequired": True,
    }


def _undurable_database_failure(invocation_id: Any) -> SupervisorResult:
    return SupervisorResult(
        str(invocation_id),
        "unknown",
        None,
        0,
        bounded_database_failure("terminalization"),
        durable=False,
    )


_FAILURE_CLASSIFICATIONS: dict[str, dict[str, str]] = {
    "budget_exhausted": {
        "failureCode": "budget_exhausted",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "model_call_budget_exhausted",
    },
    "runtime_error": {
        "failureCode": "runtime_error",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "runtime_execution_failed",
    },
    "missing_outcome": {
        "failureCode": "missing_outcome",
        "failurePhase": "runtime_supervisor",
        "failureDetail": "missing_outcome",
        "failureSubreason": "completed_without_explicit_outcome",
    },
}
_RUNTIME_FAILURE_CAUSES = frozenset(
    {
        "host_operation_failure",
        "cancellation_monitor_failure",
        "invalid_usage_accounting",
        "static_configuration_failure",
        "dependency_failure",
        "permission_failure",
        "resource_failure",
        "timeout_failure",
        "provider_client_failure",
        "relay_session_failure",
        "runtime_unknown_failure",
        "provider_auth_failure",
        "provider_entitlement_failure",
        "provider_rate_limit",
        "provider_request_failure",
        "provider_transport_failure",
        "provider_unknown_failure",
    }
)
_RUNTIME_CALLBACK_PHASES = frozenset(
    {"before_host_call", "host_return", "model_observation_emit", "adapter_event"}
)
_RUNTIME_FAILURE_PHASES = frozenset(
    {"agent_initialization", "tool_configuration", "conversation", "unknown"}
)
_RUNTIME_FAILURE_EXCEPTION_CLASSES = frozenset(
    {
        "ModuleNotFoundError",
        "ImportError",
        "PermissionError",
        "MemoryError",
        "TimeoutError",
        "OSError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "APIConnectionError",
        "APIError",
        "APIResponseValidationError",
        "APIStatusError",
        "APITimeoutError",
        "AuthenticationError",
        "BadRequestError",
        "ConflictError",
        "InternalServerError",
        "NotFoundError",
        "PermissionDeniedError",
        "RateLimitError",
        "UnprocessableEntityError",
        "ConnectTimeout",
        "PoolTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "Unknown",
    }
)


def _bounded_runtime_host_diagnostic(failure: object) -> dict[str, str]:
    if not isinstance(failure, dict):
        return {}
    phase = failure.get("callbackPhase")
    operation_ref_digest = failure.get("operationRefDigest")
    if (
        phase not in _RUNTIME_CALLBACK_PHASES
        or not isinstance(operation_ref_digest, str)
        or len(operation_ref_digest) != 64
        or any(char not in "0123456789abcdef" for char in operation_ref_digest)
    ):
        return {}
    return {"callbackPhase": phase, "operationRefDigest": operation_ref_digest}


def _bounded_runtime_code_mode_diagnostic(failure: object) -> dict[str, str]:
    if not isinstance(failure, dict):
        return {}
    status = failure.get("codeModeHostStatus")
    failure_class = failure.get("codeModeFailureClass")
    error_class = failure.get("codeModeErrorClass")
    if not isinstance(status, str) or status not in {
        "ok",
        "replayed",
        "denied",
        "conflict",
        "unavailable",
        "invalid",
    } or not isinstance(failure_class, str) or failure_class not in {
        "code_mode",
        "callback",
        "transport",
        "contract",
        "unknown",
    }:
        return {}
    if error_class is not None and (
        not isinstance(error_class, str) or error_class not in CODE_MODE_ERROR_CLASSES
    ):
        return {}
    bounded = {
        "codeModeHostStatus": status,
        "codeModeFailureClass": failure_class,
    }
    if error_class is not None:
        bounded["codeModeErrorClass"] = error_class
    return bounded


def _bounded_runtime_failure_diagnostic(failure: object) -> dict[str, str]:
    if not isinstance(failure, dict):
        return {}
    phase = failure.get("runtimePhase")
    exception_class = failure.get("exceptionClass")
    if phase not in _RUNTIME_FAILURE_PHASES or exception_class not in _RUNTIME_FAILURE_EXCEPTION_CLASSES:
        return {}
    return {"runtimePhase": phase, "exceptionClass": exception_class}


@dataclass(frozen=True)
class _Claim:
    invocation: RuntimeInvocation
    control: RuntimeInvocationControl
    outcome_unknown: bool = False


def _control(invocation: RuntimeInvocation, *, lock: bool = False) -> RuntimeInvocationControl:
    queryset = RuntimeInvocationControl.objects.select_for_update() if lock else RuntimeInvocationControl.objects
    try:
        return queryset.get(invocation=invocation)
    except RuntimeInvocationControl.DoesNotExist:
        return RuntimeInvocationControl.objects.create(
            workspace=invocation.workspace,
            project=invocation.project,
            invocation=invocation,
        )


def _validate_claim_binding(invocation: RuntimeInvocation) -> None:
    run = invocation.run
    if (
        invocation.workspace_id != run.workspace_id
        or invocation.project_id != run.project_id
        or run.assignment.assignee_id != run.actor_id
        or run.profile_version.actor_id != run.actor_id
        or run.last_invocation_id != invocation.invocation_id
        or not run.actor.is_active
    ):
        raise RuntimeSupervisorError("runtime invocation is not bound to the current Plane actor, assignment, and run")
    try:
        snapshot = validate_run_snapshot(run.snapshot)
        envelope = validate_invocation_envelope(invocation.envelope)
    except RuntimeContractError as exc:
        raise RuntimeSupervisorError(f"stored runtime contract is invalid: {exc}") from exc
    if (
        snapshot["workspaceRef"] != invocation.envelope["workspaceRef"]
        or snapshot["actorRef"] != invocation.envelope["actorRef"]
        or snapshot["runId"] != invocation.envelope["runId"]
        or snapshot["contentDigest"] != envelope["runSnapshotDigest"]
        or envelope["invocationId"] != invocation.invocation_id
    ):
        raise RuntimeSupervisorError("runtime invocation binding does not match the immutable Plane snapshot")


def _claim(invocation: RuntimeInvocation, worker_id: str, lease_seconds: int) -> _Claim | None:
    if not isinstance(worker_id, str) or not worker_id or len(worker_id.encode("utf-8")) > 128:
        raise RuntimeSupervisorError("worker_id must be a bounded non-empty identifier")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
        raise RuntimeSupervisorError("lease_seconds must be a positive integer")
    with transaction.atomic():
        _assignment, run, stored = lock_invocation_path(invocation.pk)
        stored.run = run
        control = _control(stored, lock=True)
        if stored.state in _INVOCATION_TERMINAL_STATES or control.state == RuntimeControlState.RELEASED:
            return None
        _validate_claim_binding(stored)
        now = timezone.now()
        if control.state == RuntimeControlState.OUTCOME_UNKNOWN:
            return _Claim(stored, control, outcome_unknown=True)
        if control.state == RuntimeControlState.LEASED:
            if control.lease_expires_at and control.lease_expires_at > now:
                raise RuntimeLeaseBusy("runtime invocation is leased by another worker")
            control.state = RuntimeControlState.OUTCOME_UNKNOWN
            control.outcome_unknown_at = now
            control.failure_code = "outcome_unknown"
            control.failure_reason = "The previous runtime lease expired before reconciliation."
            control.save(
                _allow_lifecycle=True,
                update_fields=["state", "outcome_unknown_at", "failure_code", "failure_reason", "updated_at"],
            )
            return _Claim(stored, control, outcome_unknown=True)
        if stored.state not in {InvocationState.QUEUED, InvocationState.RUNNING}:
            raise RuntimeSupervisorError(f"invocation cannot be claimed from {stored.state}")
        control.state = RuntimeControlState.LEASED
        control.lease_owner = worker_id
        control.lease_expires_at = now + timedelta(seconds=lease_seconds)
        control.dispatch_started_at = control.dispatch_started_at or now
        control.save(
            _allow_lifecycle=True,
            update_fields=["state", "lease_owner", "lease_expires_at", "dispatch_started_at", "updated_at"],
        )
        stored.run = stored.run
        return _Claim(stored, control)


def _set_failure(control: RuntimeInvocationControl, *, code: str, reason: str, unknown: bool = False) -> None:
    control.failure_code = str(code)[:64]
    control.failure_reason = str(reason)[:4096]
    if unknown:
        control.state = RuntimeControlState.OUTCOME_UNKNOWN
        control.outcome_unknown_at = control.outcome_unknown_at or timezone.now()


def _terminalize_db(
    invocation_id: Any,
    *,
    kind: str,
    reason: str,
    code: str,
    outcome_unknown: bool = False,
    failure: dict[str, str] | None = None,
) -> SupervisorResult:
    failure = failure or _FAILURE_CLASSIFICATIONS.get(code)
    with transaction.atomic():
        _assignment, run, invocation = lock_invocation_path(invocation_id)
        control = _control(invocation, lock=True)
        terminal = RunTerminalEvent.objects.filter(invocation=invocation).first()
        if terminal is None:
            terminal = finalize_invocation(invocation, kind=kind, reason=reason)
        elif outcome_unknown and terminal.kind == "outcome_submission":
            # An outcome callback can commit its visible event before the
            # supervisor receives a late provider-attempt terminal notice.
            # Keep that one immutable event and leave product lifecycle state
            # unchanged; control state below records the reconciliation stop.
            # A late provider notice cannot authorize an illegal succeeded ->
            # outcome_unknown transition.
            pass
        _set_failure(control, code=code, reason=reason, unknown=outcome_unknown)
        if not outcome_unknown:
            control.state = RuntimeControlState.RELEASED
        control.lease_owner = None
        control.lease_expires_at = None
        control.save(
            _allow_lifecycle=True,
            update_fields=[
                "state",
                "lease_owner",
                "lease_expires_at",
                "failure_code",
                "failure_reason",
                "outcome_unknown_at",
                "updated_at",
            ],
        )
        invocation.refresh_from_db()
        return SupervisorResult(invocation.invocation_id, invocation.state, terminal.kind, 0, failure)


def _terminalize(
    invocation_id: Any,
    **kwargs: Any,
) -> SupervisorResult:
    """Terminalize once, retaining bounded supervisor evidence on DB failure."""

    try:
        return _terminalize_db(invocation_id, **kwargs)
    except OperationalError:
        return _undurable_database_failure(invocation_id)


def _release(invocation_id: Any, *, state: str | None = None) -> None:
    with transaction.atomic():
        _assignment, _run, invocation = lock_invocation_path(invocation_id)
        control = _control(invocation, lock=True)
        control.state = RuntimeControlState.RELEASED
        control.lease_owner = None
        control.lease_expires_at = None
        control.save(_allow_lifecycle=True, update_fields=["state", "lease_owner", "lease_expires_at", "updated_at"])


def _durable_control(invocation_id: Any) -> RuntimeInvocationControl | None:
    return RuntimeInvocationControl.objects.filter(invocation_id=invocation_id).first()


def _serialized_failure(reason: dict[str, object]) -> str:
    return json.dumps(reason, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _provider_unknown_failure(invocation: RuntimeInvocation) -> dict[str, str] | None:
    """Return the last bounded provider diagnostic for an initiated unknown request."""

    attempt = (
        RuntimeProviderAttempt.objects.filter(invocation=invocation, upstream_initiated=True)
        .order_by("-sequence")
        .first()
    )
    if attempt is None:
        return None
    failure = {
        "failureCode": "outcome_unknown",
        "failurePhase": attempt.reason_phase or "provider_relay",
        "failureDetail": "upstream_result_unavailable",
        "failureSubreason": attempt.reason_subreason or "reconciliation_required",
    }
    failure["providerAttemptRef"] = f"provider-attempt:{attempt.id}"
    if attempt.event_ref:
        failure["providerEventRef"] = attempt.event_ref
    return failure


def _runtime_exit_failure_classification(
    failure: object,
    *,
    provider_unknown_evidence: dict[str, str] | None = None,
) -> dict[str, object] | None:
    """Return a bounded live envelope for a finite child terminal failure."""

    if not isinstance(failure, dict):
        return None
    code = failure.get("code")
    classification = _FAILURE_CLASSIFICATIONS.get(code)
    if classification is None:
        return None
    bounded = dict(classification)
    cause = failure.get("cause")
    if code == "runtime_error" and cause in _RUNTIME_FAILURE_CAUSES:
        # A provider-unknown cause is meaningful only when Plane durably
        # recorded an unresolved upstream attempt for this invocation. A
        # completed or failed provider request is not unknown evidence.
        if cause == "provider_unknown_failure" and provider_unknown_evidence is None:
            cause = "runtime_unknown_failure"
        bounded["failureCause"] = cause
        if cause == "provider_unknown_failure" and provider_unknown_evidence is not None:
            bounded.update(provider_unknown_evidence)
    child_diagnostic = RuntimeDispatchError._bounded_child_diagnostic(failure.get("childDiagnostic"))
    if child_diagnostic is not None:
        bounded["childDiagnostic"] = child_diagnostic
    bounded.update(_bounded_runtime_host_diagnostic(failure))
    bounded.update(_bounded_runtime_code_mode_diagnostic(failure))
    bounded.update(_bounded_runtime_failure_diagnostic(failure))
    return bounded


def _terminalize_dispatch_failure(
    invocation: RuntimeInvocation,
    reason: dict[str, object],
    *,
    known_dispatch_failure: bool = False,
) -> SupervisorResult:
    try:
        reconcile_provider_attempts(invocation)
    except OperationalError:
        return terminalize_pre_dispatch_failure(invocation, bounded_database_failure("runtime_dispatch"))
    upstream_attempt_exists = RuntimeProviderAttempt.objects.filter(
        invocation=invocation,
        upstream_initiated=True,
    ).exists()
    bounded_failure = known_dispatch_failure and not upstream_attempt_exists
    if upstream_attempt_exists:
        provider_reason = _provider_unknown_failure(invocation) or {
            "failureCode": "outcome_unknown",
            "failurePhase": "provider_relay",
            "failureDetail": "upstream_result_unavailable",
            "failureSubreason": "reconciliation_required",
        }
        if reason.get("failureCode") in {RUNTIME_PROCESS_TIMEOUT, RUNTIME_PROCESS_CANCELLED}:
            # Preserve a trusted local deadline/cancellation classification. The
            # initiated provider attempt still forces outcome_unknown state, but
            # relay cleanup must not erase why the runtime stopped.
            preserved_reason = dict(reason)
            for field in ("providerAttemptRef", "providerEventRef"):
                if field in provider_reason:
                    preserved_reason[field] = provider_reason[field]
            reason = preserved_reason
        else:
            reason = provider_reason
    else:
        reason = dict(reason)
    return _terminalize(
        invocation.pk,
        kind="run_blocker",
        reason=_serialized_failure(reason),
        code=reason["failureCode"] if bounded_failure else "outcome_unknown",
        outcome_unknown=not bounded_failure,
        failure=dict(reason),
    )


def terminalize_pre_dispatch_failure(
    invocation: RuntimeInvocation,
    failure: dict[str, object] | None = None,
) -> SupervisorResult:
    """Persist one bounded result when setup fails before runtime dispatch.

    Expected setup failures carry the same finite classification used by the
    serialized runtime seam.  An unclassified exception deliberately keeps
    the invocation in ``outcome_unknown`` so a caller cannot infer that no
    external work happened from a missing provider-attempt row.
    """

    try:
        return _terminalize_pre_dispatch_failure(invocation, failure)
    except OperationalError:
        return _undurable_database_failure(invocation.invocation_id)


def _terminalize_pre_dispatch_failure(
    invocation: RuntimeInvocation,
    failure: dict[str, object] | None = None,
) -> SupervisorResult:
    existing = RunTerminalEvent.objects.filter(invocation=invocation).first()
    if existing is not None:
        invocation.refresh_from_db()
        return SupervisorResult(invocation.invocation_id, invocation.state, existing.kind, 0)

    is_database_failure = (
        isinstance(failure, dict)
        and failure.get("failureSubstage") in _DATABASE_FAILURE_SUBSTAGES
        and failure.get("databaseClass") in _DATABASE_FAILURE_CLASSES
        and failure == bounded_database_failure(failure["failureSubstage"])
    )
    if is_database_failure:
        return _terminalize(
            invocation.pk,
            kind="run_blocker",
            reason=_serialized_failure(failure),
            code="outcome_unknown",
            outcome_unknown=True,
            failure=dict(failure),
        )

    if failure is None:
        return _terminalize(
            invocation.pk,
            kind="run_blocker",
            reason="Runtime supervisor setup did not produce a bounded result.",
            code="outcome_unknown",
            outcome_unknown=True,
        )

    child_diagnostic = failure.get("childDiagnostic")
    host_operation_failure = failure.get("hostOperationFailure")
    dispatch_error = RuntimeDispatchError(
        "runtime supervisor setup rejected dispatch",
        failure_code=failure.get("failureCode"),
        failure_phase=failure.get("failurePhase"),
        failure_detail=failure.get("failureDetail"),
        failure_subreason=failure.get("failureSubreason"),
        child_diagnostic=child_diagnostic if isinstance(child_diagnostic, dict) else None,
        host_operation_failure=host_operation_failure if isinstance(host_operation_failure, dict) else None,
    )
    if not dispatch_error.has_allowlisted_failure:
        return terminalize_pre_dispatch_failure(invocation)
    return _terminalize_dispatch_failure(
        invocation,
        dispatch_error.public_failure(),
        known_dispatch_failure=True,
    )


def runtime_invocation_cancelled(invocation_id: Any) -> bool:
    """Read durable cancellation/lease state for host RPC and supervision."""

    control = _durable_control(invocation_id)
    if control is None:
        return False
    return bool(
        control.cancellation_requested_at
        or control.state == RuntimeControlState.OUTCOME_UNKNOWN
        or (control.lease_expires_at is not None and control.lease_expires_at <= timezone.now())
    )


def runtime_invocation_cancellation_requested(invocation_id: Any) -> bool:
    control = _durable_control(invocation_id)
    return bool(control and control.cancellation_requested_at)


@transaction.atomic
def request_runtime_cancellation(
    invocation: RuntimeInvocation,
    *,
    reason: str = "Cancelled by an administrator",
    operator=None,
    idempotency_key: str | None = None,
):
    """Record cancellation durably and create the one visible event immediately.

    ``idempotency_key`` is the caller's durable operator command key.  When
    supplied, it is bound to the Plane terminal event before any runtime-side
    enforcement is attempted; the runtime HTTP stop remains only best-effort.
    """

    assignment, run, stored = lock_invocation_path(invocation.pk)
    stored.run = run
    if operator is not None:
        ensure_human_workspace_admin(assignment.workspace, operator)
    if stored.state in _INVOCATION_TERMINAL_STATES:
        terminal = RunTerminalEvent.objects.filter(invocation=stored).first()
        if terminal is None:
            raise TerminalEventRequiredError("Terminal invocation state has no visible Plane terminal event")
        if terminal.kind != "run_cancellation":
            if idempotency_key is not None:
                raise IdempotencyConflictError("Invocation already has a different terminal product event")
            return stored
        if idempotency_key is not None:
            finalize_invocation(
                stored,
                kind="run_cancellation",
                reason=str(reason)[:4096],
                idempotency_key=idempotency_key,
            )
        return stored
    control = _control(stored, lock=True)
    if control.cancellation_requested_at is None:
        control.cancellation_requested_at = timezone.now()
        control.cancellation_reason = str(reason)[:4096]
        control.save(
            _allow_lifecycle=True, update_fields=["cancellation_requested_at", "cancellation_reason", "updated_at"]
        )
    if not RunTerminalEvent.objects.filter(invocation=stored).exists():
        finalize_invocation(
            stored,
            kind="run_cancellation",
            reason=control.cancellation_reason,
            idempotency_key=idempotency_key,
        )
    control.state = RuntimeControlState.RELEASED
    control.lease_owner = None
    control.lease_expires_at = None
    control.save(_allow_lifecycle=True, update_fields=["state", "lease_owner", "lease_expires_at", "updated_at"])
    stored.refresh_from_db()
    return stored


def _observed_usage(invocation: RuntimeInvocation) -> dict[str, int]:
    totals = {"inputTokens": 0, "outputTokens": 0, "durationMs": 0}
    events = RuntimeEventIngress.objects.filter(invocation=invocation).order_by("sequence")
    for event in events:
        body = event.raw_payload.get("body", {})
        if body.get("kind") != "usage_observed":
            continue
        usage = body.get("usage", {})
        for field in totals:
            totals[field] += int(usage[field])
    return totals


def _reconcile_accepted_usage(invocation: RuntimeInvocation) -> None:
    usage = _observed_usage(invocation)
    if any(usage.values()):
        reconcile_runtime_usage(invocation.run, invocation, usage)


def _finish_exit(invocation: RuntimeInvocation, accepted_frames: int) -> SupervisorResult:
    open_attempts = list(
        RuntimeProviderAttempt.objects.filter(invocation=invocation, terminal_at__isnull=True)
    )
    if open_attempts:
        reconciled = reconcile_provider_attempts(invocation)
        if any(attempt.upstream_initiated for attempt in reconciled):
            failure = _provider_unknown_failure(invocation)
            return _terminalize(
                invocation.pk,
                kind="run_blocker",
                reason=_serialized_failure(failure)
                if failure is not None
                else "Provider request outcome is unknown; explicit reconciliation is required.",
                code="outcome_unknown",
                outcome_unknown=True,
                failure=failure,
            )
        if not provider_attempts_reconciled(invocation):
            return _terminalize(
                invocation.pk,
                kind="run_failure",
                reason="Provider attempt evidence could not be reconciled.",
                code="provider_attempt_reconciliation_failed",
            )
    if RuntimeProviderAttempt.objects.filter(
        invocation=invocation,
        phase=RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN,
    ).exists():
        failure = _provider_unknown_failure(invocation)
        return _terminalize(
            invocation.pk,
            kind="run_blocker",
            reason=_serialized_failure(failure)
            if failure is not None
            else "Provider request outcome is unknown; explicit reconciliation is required.",
            code="outcome_unknown",
            outcome_unknown=True,
            failure=failure,
        )
    exit_evidence = RuntimeExitEvidence.objects.get(invocation=invocation)
    if exit_evidence.kind == "completed":
        terminal = RunTerminalEvent.objects.filter(invocation=invocation).first()
        if terminal is None or terminal.kind != "outcome_submission":
            failure = _FAILURE_CLASSIFICATIONS["missing_outcome"]
            return _terminalize(
                invocation.pk,
                kind="run_failure",
                reason=_serialized_failure(failure),
                code="missing_outcome",
                failure=failure,
            )
        _release(invocation.pk)
        invocation.refresh_from_db()
        return SupervisorResult(invocation.invocation_id, invocation.state, terminal.kind, accepted_frames)
    if exit_evidence.kind == "waiting_for_input":
        input_event_ref = exit_evidence.raw_payload.get("inputEventRef")
        if not RuntimeEventIngress.objects.filter(
            invocation=invocation,
            event_id=input_event_ref,
            kind="input_request_observed",
        ).exists():
            return _terminalize(
                invocation.pk,
                kind="run_failure",
                reason="Runtime waiting exit did not identify an accepted input request.",
                code="invalid_waiting_exit",
            )
        try:
            transition_run(invocation.run, RunState.WAITING_FOR_INPUT, pending_input_ref=input_event_ref)
        except (AgentDomainError, InvalidTransitionError, TerminalEventRequiredError) as exc:
            return _terminalize(
                invocation.pk,
                kind="run_failure",
                reason=str(exc),
                code="invalid_waiting_exit",
            )
        _release(invocation.pk)
        invocation.refresh_from_db()
        return SupervisorResult(invocation.invocation_id, invocation.state, None, accepted_frames)
    failure = exit_evidence.raw_payload.get("failure", {})
    code = failure.get("code", "runtime_error") if isinstance(failure, dict) else "runtime_error"
    reason = (
        failure.get("message", "Runtime invocation failed")
        if isinstance(failure, dict)
        else "Runtime invocation failed"
    )
    unknown_attempt = (
        RuntimeProviderAttempt.objects.filter(
            invocation=invocation,
            upstream_initiated=True,
            phase=RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN,
        )
        .order_by("-sequence")
        .first()
    )
    provider_unknown_evidence = None
    if unknown_attempt is not None:
        provider_unknown_evidence = {
            "providerAttemptRef": f"provider-attempt:{unknown_attempt.id}"
        }
        if unknown_attempt.event_ref:
            provider_unknown_evidence["providerEventRef"] = unknown_attempt.event_ref
    failure_classification = _runtime_exit_failure_classification(
        failure,
        provider_unknown_evidence=provider_unknown_evidence,
    )
    terminal_reason = (
        _serialized_failure(failure_classification)
        if failure_classification is not None
        else reason
    )
    terminal_kind = {
        "failed": "run_failure",
        "blocked": "run_blocker",
        "cancelled": "run_cancellation",
    }.get(exit_evidence.kind)
    if terminal_kind is None:
        return _terminalize(
            invocation.pk,
            kind="run_failure",
            reason="Runtime exit kind is unsupported.",
            code="invalid_exit",
        )
    return _terminalize(
        invocation.pk,
        kind=terminal_kind,
        reason=terminal_reason,
        code=code,
        failure=failure_classification,
    )


def run_runtime_invocation(
    invocation: RuntimeInvocation,
    *,
    transport: Any,
    worker_id: str = "plane-agent-worker",
    lease_seconds: int | None = None,
) -> SupervisorResult:
    """Claim, dispatch, ingest, reconcile, and lifecycle-finish one invocation."""

    if transport is None or not callable(getattr(transport, "dispatch", None)):
        raise RuntimeSupervisorError("a serialized runtime transport is required")
    if lease_seconds is None:
        try:
            lease_seconds = math.ceil(runtime_budget_seconds(invocation.envelope))
        except (TypeError, ValueError) as exc:
            envelope_lease = invocation.envelope.get("lease")
            expires_at = envelope_lease.get("expiresAt") if isinstance(envelope_lease, dict) else None
            try:
                budget_expired = isinstance(expires_at, str) and datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                ) <= datetime.now(dt_timezone.utc)
            except (TypeError, ValueError):
                budget_expired = False
            if budget_expired:
                return _terminalize(
                    invocation.pk,
                    kind="run_failure",
                    reason="Runtime invocation budget is exhausted.",
                    code="budget_exhausted",
                )
            raise RuntimeSupervisorError("runtime invocation duration budget is invalid") from exc
    try:
        claim = _claim(invocation, worker_id, lease_seconds)
    except OperationalError:
        return terminalize_pre_dispatch_failure(invocation, bounded_database_failure("invocation_lookup"))
    if claim is None:
        try:
            stored = RuntimeInvocation.objects.get(pk=invocation.pk)
            terminal = RunTerminalEvent.objects.filter(invocation=stored).first()
        except OperationalError:
            return terminalize_pre_dispatch_failure(invocation, bounded_database_failure("runtime_readback"))
        return SupervisorResult(stored.invocation_id, stored.state, terminal.kind if terminal else None, 0)
    if claim.outcome_unknown:
        try:
            reconcile_provider_attempts(claim.invocation)
        except OperationalError:
            return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure("runtime_readback"))
        return _terminalize(
            claim.invocation.pk,
            kind="run_blocker",
            reason="Runtime outcome is unknown; reconciliation is required before retry.",
            code="outcome_unknown",
            outcome_unknown=True,
        )
    try:
        cancellation_requested = runtime_invocation_cancellation_requested(claim.invocation.pk)
    except OperationalError:
        return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure("runtime_readback"))
    if cancellation_requested:
        return _terminalize(
            claim.invocation.pk,
            kind="run_cancellation",
            reason="Runtime cancellation was requested before dispatch.",
            code="cancelled",
        )

    accepted_frames = 0
    stage = "runtime_dispatch"
    try:
        frames = dispatch_invocation(claim.invocation, transport)
        stage = "runtime_readback"
        for frame in frames:
            ingest_runtime_frame(claim.invocation, frame)
            accepted_frames += 1
        _reconcile_accepted_usage(claim.invocation)
        return _finish_exit(claim.invocation, accepted_frames)
    except RuntimeIngressError as exc:
        try:
            _reconcile_accepted_usage(claim.invocation)
        except OperationalError:
            return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure("runtime_readback"))
        except AgentDomainError as usage_error:
            return _terminalize(
                claim.invocation.pk,
                kind="run_failure",
                reason=str(usage_error),
                code="budget_exhausted" if "exceeds" in str(usage_error) else "usage_reconciliation_failed",
            )
        return _terminalize(
            claim.invocation.pk,
            kind="run_failure",
            reason=str(exc),
            code="malformed_runtime_evidence",
        )
    except RuntimeDispatchError as exc:
        try:
            return _terminalize_dispatch_failure(
                claim.invocation,
                exc.public_failure(),
                known_dispatch_failure=exc.has_allowlisted_failure,
            )
        except OperationalError:
            return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure(stage))
    except OperationalError:
        return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure(stage))
    except Exception:
        try:
            _reconcile_accepted_usage(claim.invocation)
        except OperationalError:
            return terminalize_pre_dispatch_failure(claim.invocation, bounded_database_failure("runtime_readback"))
        except AgentDomainError as usage_error:
            return _terminalize(
                claim.invocation.pk,
                kind="run_failure",
                reason=str(usage_error),
                code="budget_exhausted" if "exceeds" in str(usage_error) else "usage_reconciliation_failed",
            )
        if runtime_invocation_cancellation_requested(claim.invocation.pk):
            return _terminalize(
                claim.invocation.pk,
                kind="run_cancellation",
                reason="Runtime cancellation stopped the child process.",
                code="cancelled",
            )
        return _terminalize_dispatch_failure(
            claim.invocation,
            {
                "failureCode": RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE,
                "failurePhase": "runtime_supervisor",
                "failureDetail": "unclassified_exception",
            },
        )


__all__ = [
    "RuntimeLeaseBusy",
    "RuntimeSupervisorError",
    "SupervisorResult",
    "bounded_database_failure",
    "_provider_unknown_failure",
    "request_runtime_cancellation",
    "run_runtime_invocation",
    "terminalize_pre_dispatch_failure",
    "runtime_invocation_cancelled",
    "runtime_invocation_cancellation_requested",
]

"""Plane-owned runtime worker entrypoint.

This module is the only production assembly point between a persisted
``RuntimeInvocation``, the replaceable serialized runtime, Plane evidence
ingress, and the lifecycle transition seam.  The runtime remains untrusted
evidence; only the lifecycle service creates a visible terminal event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from plane.agent.lifecycle import (
    AgentDomainError,
    ensure_human_workspace_admin,
    IdempotencyConflictError,
    InvalidTransitionError,
    TerminalEventRequiredError,
    finalize_invocation,
    lock_invocation_path,
    reconcile_runtime_usage,
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
)

from .dispatch import RuntimeIngressError, dispatch_invocation, ingest_runtime_frame


DEFAULT_LEASE_SECONDS = 300
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


def _terminalize(
    invocation_id: Any,
    *,
    kind: str,
    reason: str,
    code: str,
    outcome_unknown: bool = False,
) -> SupervisorResult:
    with transaction.atomic():
        _assignment, _run, invocation = lock_invocation_path(invocation_id)
        control = _control(invocation, lock=True)
        terminal = RunTerminalEvent.objects.filter(invocation=invocation).first()
        if terminal is None:
            terminal = finalize_invocation(invocation, kind=kind, reason=reason)
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
        return SupervisorResult(invocation.invocation_id, invocation.state, terminal.kind, 0)


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
    exit_evidence = RuntimeExitEvidence.objects.get(invocation=invocation)
    if exit_evidence.kind == "completed":
        terminal = RunTerminalEvent.objects.filter(invocation=invocation).first()
        if terminal is None or terminal.kind != "outcome_submission":
            return _terminalize(
                invocation.pk,
                kind="run_failure",
                reason="Runtime completed without an explicit Plane outcome submission.",
                code="missing_outcome",
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
    return _terminalize(invocation.pk, kind=terminal_kind, reason=reason, code=code)


def run_runtime_invocation(
    invocation: RuntimeInvocation,
    *,
    transport: Any,
    worker_id: str = "plane-agent-worker",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> SupervisorResult:
    """Claim, dispatch, ingest, reconcile, and lifecycle-finish one invocation."""

    if transport is None or not callable(getattr(transport, "dispatch", None)):
        raise RuntimeSupervisorError("a serialized runtime transport is required")
    claim = _claim(invocation, worker_id, lease_seconds)
    if claim is None:
        stored = RuntimeInvocation.objects.get(pk=invocation.pk)
        terminal = RunTerminalEvent.objects.filter(invocation=stored).first()
        return SupervisorResult(stored.invocation_id, stored.state, terminal.kind if terminal else None, 0)
    if claim.outcome_unknown:
        return _terminalize(
            claim.invocation.pk,
            kind="run_blocker",
            reason="Runtime outcome is unknown; reconciliation is required before retry.",
            code="outcome_unknown",
            outcome_unknown=True,
        )
    if runtime_invocation_cancellation_requested(claim.invocation.pk):
        return _terminalize(
            claim.invocation.pk,
            kind="run_cancellation",
            reason="Runtime cancellation was requested before dispatch.",
            code="cancelled",
        )

    accepted_frames = 0
    try:
        frames = dispatch_invocation(claim.invocation, transport)
        for frame in frames:
            ingest_runtime_frame(claim.invocation, frame)
            accepted_frames += 1
        _reconcile_accepted_usage(claim.invocation)
        return _finish_exit(claim.invocation, accepted_frames)
    except RuntimeIngressError as exc:
        try:
            _reconcile_accepted_usage(claim.invocation)
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
    except Exception:
        try:
            _reconcile_accepted_usage(claim.invocation)
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
        return _terminalize(
            claim.invocation.pk,
            kind="run_blocker",
            reason="Runtime process outcome is unknown; explicit reconciliation is required.",
            code="outcome_unknown",
            outcome_unknown=True,
        )


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "RuntimeLeaseBusy",
    "RuntimeSupervisorError",
    "SupervisorResult",
    "request_runtime_cancellation",
    "run_runtime_invocation",
    "runtime_invocation_cancelled",
    "runtime_invocation_cancellation_requested",
]

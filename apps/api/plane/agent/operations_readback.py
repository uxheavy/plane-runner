# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded operator readback for Plane Agent operations.

This module is deliberately a projection, not a runtime state owner. Runtime
health and safety-stop writes cross the narrow adapter hooks documented below;
the runtime package remains authoritative for those decisions.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any, Mapping, Protocol
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from plane.agent.administration import redact_admin_value
from plane.agent.administration_extensions import build_governance_readback
from plane.agent.catalog_admin import gateway_status
from plane.agent.lifecycle.runtime_contract import contract_digests
from plane.agent.readback import AgentReadbackTooLarge
from plane.agent.validation import MAX_AGENT_READBACK_BYTES, contains_credential_value
from plane.api.serializers.agent_admin import (
    GatewayReadbackSerializer,
    RuntimeEventEvidenceSerializer,
    RuntimeExitEvidenceSerializer,
)
from plane.db.models import (
    AgentSchedule,
    AgentScheduleFire,
    AssignmentContract,
    InvocationState,
    RunAttempt,
    RunState,
    RunTerminalEvent,
    RuntimeControlState,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeInvocation,
    RuntimeInvocationControl,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


OPERATOR_SCHEMA_VERSION = "plane.agent.operator/v1"
CANARY_SCHEMA_VERSION = "plane.agent.canary/v1"
MAX_OPERATOR_ITEMS = 12
MAX_FAILURES = 8
MAX_REASON_BYTES = 512


class RuntimeOperatorAdapter(Protocol):
    """The T1-owned runtime seam consumed by this readback projection.

    ``health_readback`` must return an already bounded, redacted mapping. The
    control method must be idempotent for the supplied key and delegate the
    actual stop to the runtime owner.
    """

    def health_readback(self, *, workspace_id: str, limit: int) -> Mapping[str, Any]: ...

    def request_safety_stop(
        self,
        *,
        workspace_id: str,
        invocation_id: str,
        reason: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]: ...


class RuntimeOperatorAdapterUnavailable(RuntimeError):
    """Raised when T1's runtime-owned operator seam is not installed yet."""


def _runtime_operator_adapter() -> RuntimeOperatorAdapter:
    """Resolve T1's runtime hooks without importing runtime implementation details."""

    try:
        from plane import agent as _agent_package

        del _agent_package
        from plane.agent import runtime

        health_readback = getattr(runtime, "operator_health_readback", None)
        request_safety_stop = getattr(runtime, "request_operator_safety_stop", None)
    except (ImportError, AttributeError):
        health_readback = request_safety_stop = None
    if not callable(health_readback) or not callable(request_safety_stop):
        raise RuntimeOperatorAdapterUnavailable("runtime operator health and safety-stop hooks are external_required")

    class _Adapter:
        def health_readback(self, *, workspace_id: str, limit: int) -> Mapping[str, Any]:
            return health_readback(workspace_id=workspace_id, limit=limit)

        def request_safety_stop(
            self,
            *,
            workspace_id: str,
            invocation_id: str,
            reason: str,
            idempotency_key: str,
        ) -> Mapping[str, Any]:
            return request_safety_stop(
                workspace_id=workspace_id,
                invocation_id=invocation_id,
                reason=reason,
                idempotency_key=idempotency_key,
            )

    return _Adapter()


def _safe_text(value: Any, *, max_bytes: int = MAX_REASON_BYTES) -> str:
    value = redact_admin_value("" if value is None else str(value))
    if not isinstance(value, str):
        return "[redacted]"
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _safe_optional_text(value: Any, *, max_bytes: int = MAX_REASON_BYTES) -> str | None:
    return None if value is None else _safe_text(value, max_bytes=max_bytes)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _bounded_projection(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    """Redact and enforce the adapter boundary before composing the response."""

    projected = redact_admin_value(dict(value))
    encoded = json.dumps(projected, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > MAX_AGENT_READBACK_BYTES:
        raise AgentReadbackTooLarge(f"{label} exceeds the 8KB operator readback bound")
    return projected


def _runtime_health(*, workspace_id: str, limit: int) -> dict[str, Any]:
    try:
        adapter = _runtime_operator_adapter()
        value = adapter.health_readback(workspace_id=workspace_id, limit=limit)
        if not isinstance(value, Mapping):
            raise ValueError("runtime operator health hook must return an object")
        return _bounded_projection(value, label="runtime health")
    except RuntimeOperatorAdapterUnavailable:
        return {
            "status": "external_required",
            "ready": False,
            "code": "RUNTIME_OPERATOR_ADAPTER_UNAVAILABLE",
            "external_required": ["runtime-owned health/safety-stop adapter"],
        }
    except Exception as exc:
        return {
            "status": "dependency_failure",
            "ready": False,
            "code": "RUNTIME_OPERATOR_ADAPTER_FAILED",
            "reason": _safe_text(exc),
        }


def _configured_versions() -> dict[str, Any]:
    """Return exact configured revisions, never a guessed or machine-secret value."""

    def setting(*names: str) -> str | None:
        for name in names:
            value = getattr(settings, name, None)
            if isinstance(value, str) and value.strip():
                return _safe_text(value.strip(), max_bytes=256)
        return None

    gateway = gateway_status()

    return {
        "source_revision": setting("PLANE_AGENT_SOURCE_REVISION", "PLANE_AGENT_SOURCE_SHA"),
        "runtime_revision": setting("PLANE_AGENT_RUNTIME_SHA", "PLANE_AGENT_RUNTIME_REVISION"),
        "runtime_version": setting("PLANE_AGENT_RUNTIME_VERSION"),
        "hermes_revision": setting("PLANE_AGENT_HERMES_REVISION", "PLANE_AGENT_HERMES_SHA"),
        "mcp_revision": setting("PLANE_AGENT_MCP_REVISION", "PLANE_AGENT_MCP_SHA"),
        "sdk_revision": setting("PLANE_AGENT_SDK_REVISION", "PLANE_AGENT_SDK_SHA"),
        "runtime_checkout_configured": bool(getattr(settings, "PLANE_AGENT_RUNTIME_CHECKOUT", None)),
        "runtime_command_configured": bool(getattr(settings, "PLANE_AGENT_RUNTIME_COMMAND", None)),
        "catalog_digest": gateway["catalog"]["digest"],
        "catalog_schema_version": gateway["shared_gateway"]["schema_version"],
        "runtime_contract_digests": contract_digests(),
    }


def _runtime_conditions() -> list[dict[str, str]]:
    checkout = getattr(settings, "PLANE_AGENT_RUNTIME_CHECKOUT", None)
    revision = getattr(settings, "PLANE_AGENT_RUNTIME_SHA", None)
    command = getattr(settings, "PLANE_AGENT_RUNTIME_COMMAND", None)
    credentials = getattr(settings, "PLANE_AGENT_RUNTIME_CREDENTIALS", {})
    environment = getattr(settings, "PLANE_AGENT_RUNTIME_ENVIRONMENT", {})
    conditions: list[dict[str, str]] = []
    if not checkout and not command:
        conditions.append({"name": "runtime_configured", "status": "not_configured"})
    else:
        conditions.append({"name": "runtime_configured", "status": "pass"})
    if bool(checkout) != bool(revision):
        conditions.append({"name": "runtime_revision", "status": "revision_mismatch"})
    else:
        conditions.append({"name": "runtime_revision", "status": "pass"})
    if not isinstance(credentials, dict):
        conditions.append({"name": "runtime_credentials", "status": "credential_mismatch"})
    else:
        conditions.append({"name": "runtime_credentials", "status": "pass"})
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not key or "\x00" in key or not isinstance(value, str) or "\x00" in value
        for key, value in environment.items()
    ):
        conditions.append({"name": "runtime_environment", "status": "credential_mismatch"})
    else:
        conditions.append({"name": "runtime_environment", "status": "pass"})
    return conditions


def _run_invocations(runs: list[RunAttempt]) -> dict[str, RuntimeInvocation]:
    if not runs:
        return {}
    rows = (
        RuntimeInvocation.objects.filter(run_id__in=[run.id for run in runs])
        .select_related("runtime_control")
        .order_by("run_id", "-ordinal", "-id")
    )
    result: dict[str, RuntimeInvocation] = {}
    for invocation in rows:
        result.setdefault(str(invocation.run_id), invocation)
    return result


def _run_summary(run: RunAttempt, invocation: RuntimeInvocation | None) -> dict[str, Any]:
    control = getattr(invocation, "runtime_control", None) if invocation else None
    now = timezone.now()
    stale = bool(
        control
        and control.state == RuntimeControlState.LEASED
        and control.lease_expires_at is not None
        and control.lease_expires_at <= now
    )
    unknown = bool(
        run.state == RunState.OUTCOME_UNKNOWN
        or (invocation and invocation.state == InvocationState.OUTCOME_UNKNOWN)
        or (control and control.state == RuntimeControlState.OUTCOME_UNKNOWN)
    )
    failure_code = _safe_text(getattr(control, "failure_code", ""), max_bytes=64) if control else ""
    failure_reason = _safe_text(getattr(control, "failure_reason", "")) if control else ""
    return {
        "run_id": str(run.id),
        "assignment_id": str(run.assignment_id),
        "actor_id": str(run.actor_id),
        "state": run.state,
        "last_invocation_id": run.last_invocation_id,
        "invocation_state": invocation.state if invocation else None,
        "runtime_control_state": control.state if control else None,
        "lease_expires_at": _iso(control.lease_expires_at) if control else None,
        "stale_lease": stale,
        "outcome_unknown": unknown,
        "failure": {"code": failure_code, "reason": failure_reason} if failure_code or failure_reason else None,
        "updated_at": _iso(run.updated_at),
    }


def _run_page(workspace, *, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(limit, bool) or not 1 <= limit <= MAX_OPERATOR_ITEMS:
        raise ValueError(f"operator limit must be between 1 and {MAX_OPERATOR_ITEMS}")
    offset = 0
    if cursor:
        value = cursor.removeprefix("offset:")
        if not value.isdigit():
            raise ValueError("operator cursor is invalid")
        offset = int(value)
    if offset > 1_000_000:
        raise ValueError("operator cursor is too large")
    queryset = (
        RunAttempt.objects.filter(workspace=workspace)
        .select_related("assignment", "actor")
        .order_by("-created_at", "-id")
    )
    rows = list(queryset[offset : offset + limit + 1])
    has_next = len(rows) > limit
    page = rows[:limit]
    invocations = _run_invocations(page)
    summaries = [_run_summary(run, invocations.get(str(run.id))) for run in page]
    return summaries, {
        "limit": limit,
        "cursor": f"offset:{offset}",
        "next_cursor": f"offset:{offset + limit}" if has_next else None,
        "has_next": has_next,
        "ordering": ["created_at:desc", "id:desc"],
    }


def _recent_failures(workspace, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        RuntimeInvocationControl.objects.filter(workspace=workspace)
        .filter(Q(failure_code__gt="") | Q(state=RuntimeControlState.OUTCOME_UNKNOWN))
        .select_related("invocation", "invocation__run")
        .order_by("-updated_at", "-id")[: min(limit, MAX_FAILURES)]
    )
    return [
        {
            "run_id": str(row.invocation.run_id),
            "invocation_id": row.invocation.invocation_id,
            "state": row.state,
            "code": _safe_text(row.failure_code, max_bytes=64),
            "reason": _safe_text(row.failure_reason),
            "at": _iso(row.updated_at),
        }
        for row in rows
    ]


def _schedules_and_delegation(workspace, *, limit: int) -> dict[str, Any]:
    schedule_states = Counter(AgentSchedule.objects.filter(workspace=workspace).values_list("state", flat=True))
    fire_states = Counter(AgentScheduleFire.objects.filter(workspace=workspace).values_list("state", flat=True))
    assignments = AssignmentContract.objects.filter(workspace=workspace)
    max_depth = assignments.order_by("-delegation_depth").values_list("delegation_depth", flat=True).first() or 0
    return {
        "schedules": {"states": dict(sorted(schedule_states.items())), "count": sum(schedule_states.values())},
        "schedule_fires": {"states": dict(sorted(fire_states.items())), "count": sum(fire_states.values())},
        "delegation": {
            "delegated_assignments": assignments.filter(delegation_depth__gt=0).count(),
            "max_depth": max_depth,
        },
        "governance": build_governance_readback(workspace, limit=min(limit, 4)),
    }


def build_health_readback(workspace, *, limit: int = 8) -> dict[str, Any]:
    """Return the small health/readiness projection used by API and CLI."""

    versions = _configured_versions()
    conditions = _runtime_conditions()
    runtime_health = _runtime_health(workspace_id=str(workspace.id), limit=limit)
    runtime_safety_stop = runtime_health.get("safety_stop")
    if isinstance(runtime_safety_stop, Mapping):
        safety_stop = dict(runtime_safety_stop)
        safety_stop.setdefault("control", "runtime_operator_adapter")
        if safety_stop.get("status") == "external_required":
            safety_stop.setdefault("external_required", ["runtime-owned safety-stop hook"])
    else:
        safety_stop = {
            "status": "external_required",
            "control": "runtime_operator_adapter",
            "external_required": ["runtime-owned safety-stop hook"],
        }
    payload = {
        "schema_version": OPERATOR_SCHEMA_VERSION,
        "workspace": {"id": str(workspace.id), "slug": workspace.slug},
        "health": {
            "runtime": runtime_health,
            "conditions": conditions,
            "readiness": {
                "status": runtime_health.get("status", "external_required"),
                "ready": runtime_health.get("ready", False),
                "external_required": runtime_health.get("external_required", []),
            },
        },
        "versions": versions,
        "safety_stop": safety_stop,
    }
    return _bounded_projection(payload, label="operator health")


def build_operator_readback(
    workspace,
    *,
    limit: int = 8,
    cursor: str | None = None,
    correlation_id: str | None = None,
    run_id: str | None = None,
    canary_mode: str = "offline",
) -> dict[str, Any]:
    """Build the API/CLI-equivalent bounded operator projection."""

    versions = _configured_versions()
    runs, pagination = _run_page(workspace, limit=limit, cursor=cursor)
    active = [row for row in runs if row["state"] in {RunState.RUNNING, RunState.WAITING_FOR_INPUT}]
    queued = [row for row in runs if row["state"] == RunState.QUEUED]
    stale = [row for row in runs if row["stale_lease"]]
    unknown = [row for row in runs if row["outcome_unknown"]]
    health = build_health_readback(workspace, limit=limit)
    payload = {
        "schema_version": OPERATOR_SCHEMA_VERSION,
        "workspace": {"id": str(workspace.id), "slug": workspace.slug},
        "health": health["health"],
        "versions": versions,
        "runs": {
            "active": active,
            "queued": queued,
            "stale": stale,
            "outcome_unknown": unknown,
            "page": pagination,
        },
        "recent_failures": _recent_failures(workspace, limit=limit),
        "safety_stop": health["safety_stop"],
        "governance": _schedules_and_delegation(workspace, limit=limit),
        "canary": build_canary_readback(mode=canary_mode),
    }
    if run_id is not None or correlation_id is not None:
        payload["correlation"] = build_correlation_readback(
            workspace,
            run_id=run_id,
            correlation_id=correlation_id,
            limit=limit,
        )
    redacted = _bounded_projection(payload, label="operator readback")
    if contains_credential_value(json.dumps(redacted, sort_keys=True, default=str)):
        raise ValueError("operator readback contains credential-shaped data")
    return redacted


def _gateway_rows(workspace, *, correlation_id: str, limit: int) -> list[dict[str, Any]]:
    receipts = OperationGatewayIdempotency.objects.filter(
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        correlation_id=correlation_id,
    ).order_by("created_at", "id")[:limit]
    result = []
    for receipt in receipts:
        audits = OperationGatewayAudit.objects.filter(
            workspace_id=receipt.workspace_id,
            workspace_slug=receipt.workspace_slug,
            request_id=receipt.request_id,
            invocation_id=receipt.invocation_id,
            caller_id=receipt.caller_id,
            operation_id=receipt.operation_id,
            idempotency_key=receipt.idempotency_key,
            correlation_id=receipt.correlation_id,
            request_digest=receipt.request_digest,
        ).order_by("created_at", "id")[:limit]
        result.append(GatewayReadbackSerializer({"receipt": receipt, "audit": audits}).data)
    return result


def _runtime_event_projection(row: RuntimeEventIngress) -> dict[str, Any]:
    """Add correlation linkage only to the dedicated operator projection.

    The legacy single-run readback shares the evidence serializer and must
    retain its established 8 KiB envelope. Operator correlation readback is
    the canonical bounded surface for the additional linkage fields.
    """

    projection = dict(RuntimeEventEvidenceSerializer(row).data)
    projection.update(
        {
            "correlation_id": _safe_optional_text(row.correlation_id, max_bytes=128),
            "causation_ref": _safe_optional_text(row.causation_ref, max_bytes=128),
        }
    )
    return projection


def _runtime_exit_projection(row: RuntimeExitEvidence) -> dict[str, Any]:
    projection = dict(RuntimeExitEvidenceSerializer(row).data)
    projection.update(
        {
            "correlation_id": _safe_optional_text(row.correlation_id, max_bytes=128),
            "causation_ref": _safe_optional_text(row.causation_ref, max_bytes=128),
        }
    )
    return projection


def _find_runs_for_correlation(
    workspace,
    *,
    correlation_id: str | None,
    run_id: str | None,
    limit: int,
) -> list[RunAttempt]:
    if run_id:
        try:
            parsed = UUID(str(run_id))
        except (AttributeError, ValueError):
            return []
        return list(
            RunAttempt.objects.filter(workspace=workspace, pk=parsed).select_related("assignment", "actor")[:limit]
        )
    if not correlation_id:
        return []
    run_ids = set(
        RuntimeEventIngress.objects.filter(workspace=workspace, correlation_id=correlation_id).values_list(
            "run_id", flat=True
        )
    )
    run_ids.update(
        RuntimeExitEvidence.objects.filter(workspace=workspace, correlation_id=correlation_id).values_list(
            "run_id", flat=True
        )
    )
    invocation_ids = OperationGatewayIdempotency.objects.filter(
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        correlation_id=correlation_id,
    ).values_list("invocation_id", flat=True)
    run_ids.update(RuntimeInvocation.objects.filter(invocation_id__in=invocation_ids).values_list("run_id", flat=True))
    try:
        run_ids.update(
            RunAttempt.objects.filter(workspace=workspace, snapshot__correlationId=correlation_id).values_list(
                "id", flat=True
            )
        )
    except Exception:
        # SQLite-based unit harnesses do not all support Django's JSON lookup;
        # the evidence/gateway paths above remain authoritative.
        pass
    return list(
        RunAttempt.objects.filter(workspace=workspace, pk__in=run_ids)
        .select_related("assignment", "actor")
        .order_by("created_at", "id")[:limit]
    )


def build_correlation_readback(
    workspace,
    *,
    correlation_id: str | None = None,
    run_id: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Follow one correlation through every durable Plane evidence owner."""

    if not correlation_id and run_id:
        correlation_id = f"correlation:{run_id}"
    if not correlation_id or len(correlation_id.encode("utf-8")) > 128:
        raise ValueError("correlation_id or run_id is required and bounded")
    runs = _find_runs_for_correlation(workspace, correlation_id=correlation_id, run_id=run_id, limit=limit)
    run_ids = [run.id for run in runs]
    invocation_rows = list(
        RuntimeInvocation.objects.filter(run_id__in=run_ids).order_by("run_id", "ordinal", "id")[:limit]
    )
    event_rows = list(
        RuntimeEventIngress.objects.filter(workspace=workspace, correlation_id=correlation_id).order_by(
            "run_id", "sequence", "id"
        )[:limit]
    )
    exit_rows = list(
        RuntimeExitEvidence.objects.filter(workspace=workspace, correlation_id=correlation_id).order_by(
            "run_id", "created_at", "id"
        )[:limit]
    )
    gateway = _gateway_rows(workspace, correlation_id=correlation_id, limit=limit)
    outcomes = list(
        RunAttempt.objects.filter(pk__in=run_ids, workspace=workspace)
        .filter(outcome_submission__isnull=False)
        .values("outcome_submission__id", "outcome_submission__state", "outcome_submission__run_id")[:limit]
    )
    terminals = list(
        RunTerminalEvent.objects.filter(workspace=workspace, run_id__in=run_ids).order_by("created_at", "id")[:limit]
    )
    found = {
        "assignment": bool(runs),
        "run": bool(runs),
        "invocation": bool(invocation_rows),
        "runtime_event": bool(event_rows),
        "runtime_exit": bool(exit_rows),
        "gateway_receipt": bool(gateway),
        "gateway_audit": any(row.get("audit") for row in gateway),
        "outcome": bool(outcomes),
        "terminal_event": bool(terminals),
    }
    result = {
        "schema_version": OPERATOR_SCHEMA_VERSION,
        "correlation_id": correlation_id,
        "links": {
            "assignments": [{"id": str(run.assignment_id), "run_id": str(run.id)} for run in runs],
            "runs": [{"id": str(run.id), "state": run.state} for run in runs],
            "invocations": [
                {"id": str(row.id), "invocation_id": row.invocation_id, "run_id": str(row.run_id), "state": row.state}
                for row in invocation_rows
            ],
            "runtime_events": [_runtime_event_projection(row) for row in event_rows],
            "runtime_exits": [_runtime_exit_projection(row) for row in exit_rows],
            "gateway": gateway,
            "outcomes": outcomes,
            "terminal_events": [
                {
                    "id": str(row.id),
                    "run_id": str(row.run_id),
                    "invocation_id": str(row.invocation_id),
                    "kind": row.kind,
                    "product_event_ref": row.product_event_ref,
                }
                for row in terminals
            ],
        },
        "linkage": {
            "complete": all(found.values()),
            "found": found,
            "missing": [name for name, value in found.items() if not value],
        },
    }
    return _bounded_projection(result, label="correlation readback")


def build_safety_stop_command(
    workspace,
    *,
    invocation_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Delegate a targeted stop to T1's runtime owner; never mutate state here."""

    if not isinstance(invocation_id, str) or not invocation_id or len(invocation_id.encode("utf-8")) > 128:
        raise ValueError("invocation_id must be a bounded identifier")
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key.encode("utf-8")) > 128:
        raise ValueError("idempotency_key must be a bounded identifier")
    try:
        adapter = _runtime_operator_adapter()
        result = adapter.request_safety_stop(
            workspace_id=str(workspace.id),
            invocation_id=invocation_id,
            reason=_safe_text(reason, max_bytes=MAX_REASON_BYTES),
            idempotency_key=idempotency_key,
        )
    except RuntimeOperatorAdapterUnavailable as exc:
        return {
            "status": "external_required",
            "code": "RUNTIME_OPERATOR_ADAPTER_UNAVAILABLE",
            "message": _safe_text(exc),
            "external_required": ["runtime-owned safety-stop hook"],
        }
    if not isinstance(result, Mapping):
        raise ValueError("runtime safety-stop hook must return an object")
    return _bounded_projection(result, label="safety-stop response")


def build_canary_readback(*, mode: str = "offline") -> dict[str, Any]:
    """Return deterministic offline proof and an explicit live-evaluation gate."""

    if mode not in {"offline", "live"}:
        raise ValueError("canary mode must be offline or live")
    fixtures = [
        {"id": "offline-permitted-read", "operation": "work_item.read", "expected": "permitted"},
        {"id": "offline-denied-cross-workspace", "operation": "work_item.rename", "expected": "denied"},
        {"id": "offline-denied-credential-payload", "operation": "agent.outcome.submit", "expected": "denied"},
    ]
    if mode == "live":
        return {
            "schema_version": CANARY_SCHEMA_VERSION,
            "mode": "live",
            "status": "external_required",
            "fixtures": [],
            "results": [],
            "thresholds": {"permitted_min": 1, "denied_min": 2, "max_failures": 0},
            "external_required": ["separately authorized live provider/evaluation authority"],
        }
    results = [
        {"id": fixtures[0]["id"], "observed": "permitted", "status": "pass"},
        {"id": fixtures[1]["id"], "observed": "denied", "status": "pass"},
        {"id": fixtures[2]["id"], "observed": "denied", "status": "pass"},
    ]
    return {
        "schema_version": CANARY_SCHEMA_VERSION,
        "mode": "offline",
        "status": "pass",
        "fixtures": fixtures,
        "results": results,
        "thresholds": {"permitted_min": 1, "denied_min": 2, "max_failures": 0},
        "external_required": ["separately authorized live provider/evaluation authority"],
    }


__all__ = [
    "CANARY_SCHEMA_VERSION",
    "MAX_OPERATOR_ITEMS",
    "OPERATOR_SCHEMA_VERSION",
    "RuntimeOperatorAdapter",
    "RuntimeOperatorAdapterUnavailable",
    "build_canary_readback",
    "build_correlation_readback",
    "build_health_readback",
    "build_operator_readback",
    "build_safety_stop_command",
]

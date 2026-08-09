# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared bounded readback projection for the Agent administration surfaces."""

from __future__ import annotations

import json
from typing import Any

from plane.agent.administration import redact_admin_value
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.api.serializers.agent_admin import (
    AgentActorAdminSerializer,
    AssignmentAdminSerializer,
    GatewayReadbackSerializer,
    OutcomeAdminSerializer,
    ProfileVersionAdminSerializer,
    RunAdminSerializer,
    RunInputEventAdminSerializer,
    RuntimeEventEvidenceSerializer,
    RuntimeExitEvidenceSerializer,
    RuntimeInvocationReadbackSerializer,
    RuntimeUsageObservationAdminSerializer,
    TerminalEventAdminSerializer,
)
from plane.db.models import (
    OutcomeSubmission,
    RunAttempt,
    RunInputEvent,
    RunTerminalEvent,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeInvocation,
    RuntimeProviderAttempt,
    RuntimeUsageObservation,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


MAX_AGENT_READBACK_ITEMS = 100


class AgentReadbackTooLarge(ValueError):
    """Raised when a serialized administration projection exceeds its byte bound."""


def validate_readback_limit(limit: int) -> int:
    if isinstance(limit, bool) or not 1 <= limit <= MAX_AGENT_READBACK_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_AGENT_READBACK_ITEMS}")
    return limit


def _bounded_snapshot_projection(snapshot: Any) -> dict[str, Any]:
    """Keep run identity and policy while avoiding duplicate tool/prompt payloads."""

    if not isinstance(snapshot, dict):
        return {}
    projection = {
        key: snapshot[key]
        for key in (
            "protocol",
            "workspaceRef",
            "runId",
            "actorRef",
            "runtimePolicy",
            "totalBudget",
            "contractDigests",
            "contentDigest",
        )
        if key in snapshot
    }
    for key in ("assignment", "profile"):
        value = snapshot.get(key)
        if isinstance(value, dict):
            projection[key] = {
                field: value[field]
                for field in ("assignmentRef", "profileRef", "revision", "targetRef", "role")
                if field in value
            }
    return projection


def _run_readback(run: RunAttempt) -> dict[str, Any]:
    serialized = RunAdminSerializer(run).data
    serialized["snapshot"] = _bounded_snapshot_projection(serialized.get("snapshot"))
    return serialized


def _gateway_readback(run: RunAttempt, *, limit: int) -> list[dict[str, Any]]:
    """Read only receipts emitted for this persisted run's canonical correlation."""

    receipts = OperationGatewayIdempotency.objects.filter(
        workspace_id=run.workspace_id,
        workspace_slug=run.workspace.slug,
        caller_id=run.actor.principal_id,
        correlation_id=f"correlation:{run.id}",
    ).order_by("-created_at", "-id")[:limit]
    readback = []
    for receipt in receipts:
        audit = OperationGatewayAudit.objects.filter(
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
        readback.append(GatewayReadbackSerializer({"receipt": receipt, "audit": audit}).data)
    return readback


def _provider_attempt_readback(run: RunAttempt, *, limit: int) -> list[dict[str, Any]]:
    """Expose only structural provider-attempt reconciliation facts."""

    attempts = RuntimeProviderAttempt.objects.filter(run=run).order_by("created_at", "sequence", "id")[:limit]
    return [
        {
            "attempt_id": str(attempt.id),
            "invocation_id": attempt.invocation.invocation_id,
            "phase": attempt.phase,
            "provider": attempt.provider,
            "model": attempt.model,
            "destination_host": attempt.destination_host,
            "destination_path": attempt.destination_path,
            "request_id": attempt.request_id,
            "sequence": attempt.sequence,
            "upstream_initiated": attempt.upstream_initiated,
            "status_class": attempt.status_class,
            "error_code": attempt.error_code,
            "terminal_at": attempt.terminal_at.isoformat() if attempt.terminal_at else None,
        }
        for attempt in attempts
    ]


def build_run_readback(run: RunAttempt, *, limit: int) -> dict[str, Any]:
    """Build the one projection used by the API and ``agent_readback`` command."""

    limit = validate_readback_limit(limit)
    outcome = OutcomeSubmission.objects.filter(run=run).first()
    payload = {
        "actor": AgentActorAdminSerializer(run.actor).data,
        "profile": ProfileVersionAdminSerializer(run.profile_version).data,
        "assignment": AssignmentAdminSerializer(run.assignment).data,
        "run": _run_readback(run),
        "input_events": RunInputEventAdminSerializer(
            RunInputEvent.objects.filter(run=run).order_by("sequence", "id")[:limit], many=True
        ).data,
        "invocations": RuntimeInvocationReadbackSerializer(
            RuntimeInvocation.objects.filter(run=run)
            .select_related("runtime_control", "runtime_usage_observation")
            .order_by("ordinal", "id")[:limit],
            many=True,
        ).data,
        "runtime_events": RuntimeEventEvidenceSerializer(
            RuntimeEventIngress.objects.filter(run=run).order_by("sequence", "id")[:limit], many=True
        ).data,
        "runtime_exits": RuntimeExitEvidenceSerializer(
            RuntimeExitEvidence.objects.filter(run=run).order_by("created_at", "id")[:limit], many=True
        ).data,
        "terminal_events": TerminalEventAdminSerializer(
            RunTerminalEvent.objects.filter(run=run).order_by("created_at", "id")[:limit], many=True
        ).data,
        "outcome": OutcomeAdminSerializer(outcome).data if outcome else None,
        "usage": RuntimeUsageObservationAdminSerializer(
            RuntimeUsageObservation.objects.filter(run=run).order_by("created_at", "id")[:limit], many=True
        ).data,
        "provider_attempts": _provider_attempt_readback(run, limit=limit),
        "gateway_readback": _gateway_readback(run, limit=limit),
    }
    redacted = redact_admin_value(payload)
    encoded = json.dumps(redacted, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > MAX_AGENT_READBACK_BYTES:
        raise AgentReadbackTooLarge("readback exceeds the 8KB bounded output ceiling; reduce the limit")
    return redacted

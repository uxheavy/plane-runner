# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared bounded readback projection for the Agent administration surfaces."""

from __future__ import annotations

import json
from typing import Any

from django.db.models import Exists, OuterRef, Q

from plane.agent.administration import redact_admin_value
from plane.agent.lifecycle.runtime_contract import content_digest
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.api.serializers.agent_admin import (
    AgentActorAdminSerializer,
    AssignmentAdminSerializer,
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


class AgentReadbackIntegrityError(ValueError):
    """Raised when persisted runtime evidence is not owned by its requested run."""


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


def _code_mode_gateway_receipts(*, run: RunAttempt, invocation: RuntimeInvocation):
    """Read Code Mode gateway attempts through their trusted host key and receipt."""

    if invocation.run_id != run.id or invocation.workspace_id != run.workspace_id:
        return OperationGatewayIdempotency.objects.none()
    prefix = f"idempotency:code-mode-{invocation.invocation_id}-"
    correlated_audit = OperationGatewayAudit.objects.filter(
        id=OuterRef("audit_receipt"),
        invocation_id=OuterRef("invocation_id"),
        phase=OperationGatewayAudit.Phase.OUTCOME,
        request_id=OuterRef("request_id"),
        operation_id=OuterRef("operation_id"),
        workspace_id=OuterRef("workspace_id"),
        workspace_slug=OuterRef("workspace_slug"),
        caller_id=OuterRef("caller_id"),
        idempotency_key=OuterRef("idempotency_key"),
        correlation_id=OuterRef("correlation_id"),
        request_digest=OuterRef("request_digest"),
    )
    return (
        OperationGatewayIdempotency.objects.filter(
            workspace_id=run.workspace_id,
            workspace_slug=run.workspace.slug,
            caller_id=run.actor.principal_id,
            idempotency_key__startswith=prefix,
        )
        .annotate(_correlated_audit=Exists(correlated_audit))
        .filter(_correlated_audit=True)
    )


def _gateway_readback(run: RunAttempt, *, limit: int) -> list[dict[str, Any]]:
    """Read bounded receipt references emitted for this run's correlation."""

    code_mode_receipt_ids = []
    for invocation in RuntimeInvocation.objects.filter(run=run).order_by("ordinal", "id")[:limit]:
        code_mode_receipt_ids.extend(
            _code_mode_gateway_receipts(
                run=run,
                invocation=invocation,
            ).values_list("id", flat=True)
        )
    receipts = OperationGatewayIdempotency.objects.filter(
        workspace_id=run.workspace_id,
        workspace_slug=run.workspace.slug,
        caller_id=run.actor.principal_id,
    ).filter(
        Q(correlation_id=f"correlation:{run.id}") | Q(id__in=code_mode_receipt_ids)
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
        readback.append(
            {
                "receipt": {
                    "id": str(receipt.id),
                    "request_id": str(receipt.request_id),
                    "operation_id": receipt.operation_id,
                    "workspace_slug": receipt.workspace_slug,
                    "caller_id": str(receipt.caller_id),
                    "invocation_id": str(receipt.invocation_id),
                    "idempotency_key": receipt.idempotency_key,
                    "correlation_id": receipt.correlation_id,
                    "request_digest": receipt.request_digest,
                    "state": receipt.state,
                    "retryable": receipt.retryable,
                    "audit_receipt": str(receipt.audit_receipt) if receipt.audit_receipt else None,
                    "created_at": receipt.created_at.isoformat(),
                    "updated_at": receipt.updated_at.isoformat(),
                },
                "audit": [
                    {
                        "id": str(row.id),
                        "invocation_id": row.invocation_id,
                        "phase": row.phase,
                        "outcome": row.outcome,
                        "request_id": str(row.request_id),
                        "operation_id": row.operation_id,
                        "workspace_slug": row.workspace_slug,
                        "caller_id": str(row.caller_id),
                        "correlation_id": row.correlation_id,
                        "request_digest": row.request_digest,
                        "error_code": row.error_code,
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in audit
                ],
            }
        )
    return readback


def _provider_attempt_readback(run: RunAttempt, *, limit: int) -> list[dict[str, Any]]:
    """Expose only structural provider-attempt reconciliation facts."""

    attempts = (
        RuntimeProviderAttempt.objects.filter(run=run)
        .select_related("invocation")
        .order_by("created_at", "sequence", "id")[:limit]
    )
    readback = []
    for attempt in attempts:
        invocation = attempt.invocation
        if (
            attempt.run_id != run.id
            or invocation.run_id != run.id
            or attempt.workspace_id != run.workspace_id
            or attempt.project_id != run.project_id
            or attempt.actor_id != run.actor_id
            or not invocation.idempotency_key
        ):
            raise AgentReadbackIntegrityError("provider attempt ownership or fingerprint is invalid")
        identity = {
            "invocationRef": invocation.invocation_id,
            "runRef": str(attempt.run_id),
            "leaseId": attempt.lease_id,
            "provider": attempt.provider,
            "model": attempt.model,
            "destinationHost": attempt.destination_host,
            "destinationPath": attempt.destination_path,
            "requestId": attempt.request_id,
            "idempotencyKey": attempt.idempotency_key,
            "sequence": attempt.sequence,
        }
        if attempt.fingerprint != content_digest(identity):
            raise AgentReadbackIntegrityError("provider attempt ownership or fingerprint is invalid")
        readback.append(
            {
                "attempt_id": str(attempt.id),
                "invocation_id": invocation.invocation_id,
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
                "reason_subreason": attempt.reason_subreason,
                "terminal_at": attempt.terminal_at.isoformat() if attempt.terminal_at else None,
            }
        )
    return readback


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

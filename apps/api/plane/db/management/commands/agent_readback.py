"""Bounded, redacted readback for one assigned Plane Agent run."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

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
    RuntimeInvocationAdminSerializer,
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
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


class Command(BaseCommand):
    help = "Print bounded, redacted actor/profile/assignment/run/runtime/gateway readback for one run."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = options["limit"]
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise CommandError("limit must be between 1 and 100")
        run = (
            RunAttempt.objects.select_related("assignment", "actor", "profile_version")
            .filter(workspace__slug=options["workspace_slug"], pk=options["run_id"])
            .first()
        )
        if run is None:
            raise CommandError("run-id does not identify a run in the requested workspace")
        outcome = OutcomeSubmission.objects.filter(run=run).first()
        gateway_readback = []
        receipts = OperationGatewayIdempotency.objects.filter(
            workspace_slug=options["workspace_slug"],
            caller_id=run.actor.principal_id,
            correlation_id=f"correlation:{run.last_invocation_id}",
        ).order_by("-created_at")[:limit]
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
            ).order_by("created_at", "id")
            gateway_readback.append(GatewayReadbackSerializer({"receipt": receipt, "audit": audit}).data)
        payload = {
            "actor": AgentActorAdminSerializer(run.actor).data,
            "profile": ProfileVersionAdminSerializer(run.profile_version).data,
            "assignment": AssignmentAdminSerializer(run.assignment).data,
            "run": RunAdminSerializer(run).data,
            "input_events": RunInputEventAdminSerializer(
                RunInputEvent.objects.filter(run=run).order_by("sequence")[:limit], many=True
            ).data,
            "invocations": RuntimeInvocationAdminSerializer(
                RuntimeInvocation.objects.filter(run=run).order_by("ordinal")[:limit], many=True
            ).data,
            "runtime_events": RuntimeEventEvidenceSerializer(
                RuntimeEventIngress.objects.filter(run=run).order_by("sequence")[:limit], many=True
            ).data,
            "runtime_exits": RuntimeExitEvidenceSerializer(
                RuntimeExitEvidence.objects.filter(run=run)[:limit], many=True
            ).data,
            "terminal_events": TerminalEventAdminSerializer(
                RunTerminalEvent.objects.filter(run=run)[:limit], many=True
            ).data,
            "outcome": OutcomeAdminSerializer(outcome).data if outcome else None,
            "gateway_readback": gateway_readback,
        }
        output = json.dumps(redact_admin_value(payload), sort_keys=True, default=str)
        if len(output.encode("utf-8")) > MAX_AGENT_READBACK_BYTES:
            raise CommandError("readback exceeds the 8KB bounded output ceiling; reduce --limit")
        self.stdout.write(output)

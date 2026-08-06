"""Delegate a targeted Agent safety stop to the runtime-owned seam."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.operations_readback import build_operator_readback, build_safety_stop_command
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.db.models import RunAttempt, RuntimeInvocation, Workspace


class Command(BaseCommand):
    help = "Request one idempotent, targeted runtime safety stop; global stop state is not accepted."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--run-id")
        parser.add_argument("--invocation-id")
        parser.add_argument("--reason", default="Operator safety stop")
        parser.add_argument("--idempotency-key", required=True)

    def handle(self, *args, **options):
        if bool(options.get("run_id")) == bool(options.get("invocation_id")):
            raise CommandError("Provide exactly one of --run-id or --invocation-id")
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        invocation_id = options.get("invocation_id")
        if invocation_id is None:
            run = RunAttempt.objects.filter(workspace=workspace, pk=options["run_id"]).first()
            if run is None or not run.last_invocation_id:
                raise CommandError("run-id does not identify a run with a current invocation")
            invocation_id = run.last_invocation_id
        if not RuntimeInvocation.objects.filter(run__workspace=workspace, invocation_id=invocation_id).exists():
            raise CommandError("invocation-id does not identify an invocation in the requested workspace")
        try:
            result = build_safety_stop_command(
                workspace,
                invocation_id=invocation_id,
                reason=options["reason"],
                idempotency_key=options["idempotency_key"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output = {"control": result}
        if result.get("status") != "external_required":
            output["readback"] = build_operator_readback(workspace, limit=1)
        encoded = json.dumps(output, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > MAX_AGENT_READBACK_BYTES:
            raise CommandError("operator control readback exceeds the 8KB bounded output ceiling")
        self.stdout.write(encoded.decode("utf-8"))

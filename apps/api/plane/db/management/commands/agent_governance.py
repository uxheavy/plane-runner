# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Execute a bounded Plane Agent administration extension command."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.administration import AGENT_ADMIN_L7_ACTIONS, AgentAdminExtensionCommand
from plane.agent.administration_extensions import plane_agent_admin_extension
from plane.agent.lifecycle import AgentDomainError
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.db.models import User, Workspace


class Command(BaseCommand):
    help = "Execute one bounded, redacted Plane Agent governance extension command."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--action", choices=AGENT_ADMIN_L7_ACTIONS, required=True)
        parser.add_argument("--idempotency-key", required=True)
        parser.add_argument("--actor-id")
        parser.add_argument("--run-id")
        parser.add_argument("--invocation-id")
        parser.add_argument(
            "--operator-id",
            help="Authenticated human caller for governance decisions; never provide this in --payload.",
        )
        parser.add_argument("--payload", default="{}")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        try:
            payload = json.loads(options["payload"])
        except ValueError as exc:
            raise CommandError("--payload must contain one JSON object") from exc
        if not isinstance(payload, dict):
            raise CommandError("--payload must contain one JSON object")
        authenticated_user = None
        if options.get("operator_id"):
            authenticated_user = User.objects.filter(pk=options["operator_id"], is_active=True, is_bot=False).first()
            if authenticated_user is None:
                raise CommandError("--operator-id must identify an active human User")
        try:
            command = AgentAdminExtensionCommand(
                action=options["action"],
                workspace_id=str(workspace.id),
                actor_id=options.get("actor_id"),
                run_id=options.get("run_id"),
                invocation_id=options.get("invocation_id"),
                idempotency_key=options["idempotency_key"],
                payload=payload,
                authenticated_user=authenticated_user,
            )
            result = plane_agent_admin_extension().execute(command)
        except (AgentDomainError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        output = json.dumps(result, sort_keys=True, default=str)
        if len(output.encode("utf-8")) > MAX_AGENT_READBACK_BYTES:
            raise CommandError("governance command output exceeds the 8KB bounded output ceiling")
        self.stdout.write(output)

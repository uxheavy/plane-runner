# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fire all due Plane Agent schedules for one workspace."""

from __future__ import annotations

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from plane.agent.schedules import fire_due_schedules
from plane.api.serializers.agent_context_admin import AgentScheduleFireAdminSerializer
from plane.db.models import Workspace


class Command(BaseCommand):
    help = "Fire due Agent schedules into normal, idempotent Plane assignments."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument(
            "--now",
            help="Override the due-time clock with an aware ISO-8601 datetime; defaults to the current UTC time.",
        )

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        now = timezone.now()
        if options.get("now"):
            try:
                now = datetime.fromisoformat(options["now"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise CommandError("--now must be an ISO-8601 datetime") from exc
            if now.tzinfo is None or now.utcoffset() is None:
                raise CommandError("--now must include a timezone offset")
        fires = fire_due_schedules(workspace=workspace, now=now, created_by=workspace.owner)
        self.stdout.write(json.dumps({"fires": AgentScheduleFireAdminSerializer(fires, many=True).data}, default=str))

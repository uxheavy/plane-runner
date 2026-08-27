# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Print the bounded API-equivalent Agent health/readiness projection."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.operations_readback import build_health_readback
from plane.db.models import Workspace


class Command(BaseCommand):
    help = "Print bounded, redacted Agent runtime health, readiness, safety-stop, and exact versions."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--limit", type=int, default=8)

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        try:
            payload = build_health_readback(workspace, limit=options["limit"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(payload, sort_keys=True, default=str))

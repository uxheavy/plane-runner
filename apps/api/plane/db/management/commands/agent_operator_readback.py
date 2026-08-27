# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Print the bounded API-equivalent Plane Agent operator projection."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.operations_readback import build_operator_readback
from plane.db.models import Workspace


class Command(BaseCommand):
    help = "Print bounded, redacted Agent health, runs, correlation, governance, and canary readback."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--limit", type=int, default=8)
        parser.add_argument("--cursor")
        parser.add_argument("--run-id")
        parser.add_argument("--correlation-id")
        parser.add_argument("--canary-mode", choices=("offline", "live"), default="offline")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        try:
            payload = build_operator_readback(
                workspace,
                limit=options["limit"],
                cursor=options.get("cursor"),
                run_id=options.get("run_id"),
                correlation_id=options.get("correlation_id"),
                canary_mode=options["canary_mode"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(payload, sort_keys=True, default=str))

"""Print deterministic Agent canary/evaluation readback."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.operations_readback import build_canary_readback
from plane.db.models import Workspace


class Command(BaseCommand):
    help = "Print deterministic permitted/denied offline canary fixtures or external_required live status."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--mode", choices=("offline", "live"), default="offline")

    def handle(self, *args, **options):
        if not Workspace.objects.filter(slug=options["workspace_slug"]).exists():
            raise CommandError("workspace-slug does not identify a workspace")
        try:
            payload = build_canary_readback(mode=options["mode"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(payload, sort_keys=True))

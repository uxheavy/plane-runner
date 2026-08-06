"""Print the bounded L7 governance projection shared with the admin API."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.administration_extensions import AgentReadbackTooLarge, build_governance_readback
from plane.db.models import Workspace


class Command(BaseCommand):
    help = "Print bounded delegation, HR, chief-of-staff, evaluator, and lifecycle governance readback."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--resource-id")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError("workspace-slug does not identify a workspace")
        try:
            payload = build_governance_readback(
                workspace,
                limit=options["limit"],
                resource_id=options.get("resource_id"),
            )
        except (AgentReadbackTooLarge, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(payload, sort_keys=True, default=str))

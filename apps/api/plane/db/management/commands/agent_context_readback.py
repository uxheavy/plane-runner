"""Print bounded, redacted context administration for one Agent actor."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.context_readback import AgentContextReadbackTooLarge, build_actor_context_readback
from plane.db.models import AgentActor


class Command(BaseCommand):
    help = "Print bounded memory, skills, revisions, proposals, schedules, and fire readback."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--actor-id", required=True)
        parser.add_argument("--limit", type=int, default=1)

    def handle(self, *args, **options):
        actor = (
            AgentActor.objects.filter(workspace__slug=options["workspace_slug"], pk=options["actor_id"])
            .select_related("active_profile")
            .first()
        )
        if actor is None:
            raise CommandError("actor-id does not identify an actor in the requested workspace")
        try:
            payload = build_actor_context_readback(actor, limit=options["limit"])
        except (AgentContextReadbackTooLarge, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(payload, sort_keys=True, default=str))

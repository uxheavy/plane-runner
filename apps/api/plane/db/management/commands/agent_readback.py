# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bounded, redacted readback for one assigned Plane Agent run."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.readback import (
    AgentReadbackIntegrityError,
    AgentReadbackTooLarge,
    build_run_readback,
    validate_readback_limit,
)
from plane.db.models import RunAttempt


class Command(BaseCommand):
    help = "Print bounded, redacted actor/profile/assignment/run/runtime/gateway readback for one run."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = options["limit"]
        try:
            validate_readback_limit(limit)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        run = (
            RunAttempt.objects.select_related("assignment", "actor", "profile_version")
            .filter(workspace__slug=options["workspace_slug"], pk=options["run_id"])
            .first()
        )
        if run is None:
            raise CommandError("run-id does not identify a run in the requested workspace")
        try:
            self.stdout.write(json.dumps(build_run_readback(run, limit=limit), sort_keys=True, default=str))
        except (AgentReadbackIntegrityError, AgentReadbackTooLarge) as exc:
            raise CommandError(str(exc)) from exc

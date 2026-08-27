# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Print a bounded page from Plane's progressive operation catalog."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.catalog_admin import catalog_page
from plane.agent.validation import MAX_AGENT_READBACK_BYTES


class Command(BaseCommand):
    help = "Print a bounded, progressively discoverable Agent operation catalog page."

    def add_arguments(self, parser):
        parser.add_argument("--query", default="")
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--cursor")

    def handle(self, *args, **options):
        try:
            payload = catalog_page(
                query=options["query"],
                limit=options["limit"],
                cursor=options.get("cursor"),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output = json.dumps(payload, sort_keys=True)
        if len(output.encode("utf-8")) > MAX_AGENT_READBACK_BYTES:
            raise CommandError("catalog page exceeds the 8KB bounded output ceiling; reduce --limit")
        self.stdout.write(output)

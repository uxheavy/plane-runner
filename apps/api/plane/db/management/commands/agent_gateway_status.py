# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Print the bounded status of Plane's shared Agent gateway and adapter registry."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.agent.catalog_admin import gateway_status
from plane.agent.validation import MAX_AGENT_READBACK_BYTES


class Command(BaseCommand):
    help = "Print bounded Agent gateway, MCP/SDK registry, and receipt status."

    def handle(self, *args, **options):
        output = json.dumps(gateway_status(), sort_keys=True)
        if len(output.encode("utf-8")) > MAX_AGENT_READBACK_BYTES:
            raise CommandError("gateway status exceeds the 8KB bounded output ceiling")
        self.stdout.write(output)

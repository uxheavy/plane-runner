# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bounded cleanup for inactive, expired Operation Gateway quota buckets."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.operation_gateway.limits import QUOTA_CLEANUP_BATCH_SIZE, QUOTA_RETENTION
from plane.operation_gateway.quota import cleanup_gateway_quota


class Command(BaseCommand):
    help = "Delete inactive Operation Gateway quota buckets older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--retention-hours", type=float, default=QUOTA_RETENTION.total_seconds() / 3600)
        parser.add_argument("--batch-size", type=int, default=QUOTA_CLEANUP_BATCH_SIZE)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            from datetime import timedelta

            retention = timedelta(hours=options["retention_hours"])
            deleted = cleanup_gateway_quota(retention=retention, batch_size=options["batch_size"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise CommandError(str(exc)) from exc
        result = {
            "retentionHours": options["retention_hours"],
            "batchSize": options["batch_size"],
            "deleted": deleted,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
        else:
            self.stdout.write(f"gateway quota cleanup: deleted={deleted}, passes=True")

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

"""Continuously dispatch persisted Plane Agent invocations."""

from __future__ import annotations

import socket
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from plane.db.models import InvocationState, RuntimeControlState, RuntimeInvocation


class Command(BaseCommand):
    help = "Dispatch persisted Plane Agent invocations through the durable supervisor."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=1.0)
        parser.add_argument("--worker-id", default=f"plane-agent-supervisor:{socket.gethostname()}")

    @staticmethod
    def _next_invocation_ref() -> str | None:
        return (
            RuntimeInvocation.objects.filter(
                state__in=(InvocationState.QUEUED, InvocationState.RUNNING),
                runtime_control__state=RuntimeControlState.AVAILABLE,
            )
            .order_by("created_at", "id")
            .values_list("invocation_id", flat=True)
            .first()
        )

    def handle(self, *args, **options):
        interval = options["poll_interval"]
        if interval < 0.1 or interval > 60:
            raise CommandError("poll-interval must be between 0.1 and 60 seconds")
        while True:
            invocation_ref = None
            try:
                invocation_ref = self._next_invocation_ref()
                if invocation_ref is not None:
                    call_command(
                        "agent_supervisor",
                        invocation_ref=invocation_ref,
                        worker_id=options["worker_id"],
                        stdout=self.stdout,
                        stderr=self.stderr,
                    )
            except OperationalError:
                close_old_connections()
            except CommandError:
                pass
            if options["once"]:
                return
            if invocation_ref is None:
                time.sleep(interval)

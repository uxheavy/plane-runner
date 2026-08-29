# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Operator controls for host-side runtime credential lease invalidation."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from plane.agent.runtime import RuntimeCredentialBroker, RuntimeCredentialError


class Command(BaseCommand):
    help = "Rotate or revoke host-side Agent runtime credential leases."

    def add_arguments(self, parser):
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument("--rotate-credential-ref")
        actions.add_argument("--revoke-invocation-ref")
        actions.add_argument("--revoke-lease-id")

    def handle(self, *args, **options):
        state_file = getattr(
            settings,
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE",
            "/tmp/plane-agent-credentials/revocations.json",
        )
        broker = RuntimeCredentialBroker(lambda _credential_ref: {}, state_file=state_file)
        try:
            if options.get("rotate_credential_ref"):
                generation = broker.rotate(options["rotate_credential_ref"])
                self.stdout.write(f"credential_ref={options['rotate_credential_ref']} generation={generation}")
            elif options.get("revoke_invocation_ref"):
                count = broker.revoke_invocation(options["revoke_invocation_ref"])
                self.stdout.write(f"invocation_ref={options['revoke_invocation_ref']} revoked_leases={count}")
            else:
                lease_id = options["revoke_lease_id"]
                self.stdout.write(f"lease_revoked={str(broker.revoke_lease_id(lease_id)).lower()}")
        except RuntimeCredentialError as exc:
            raise CommandError(str(exc)) from exc

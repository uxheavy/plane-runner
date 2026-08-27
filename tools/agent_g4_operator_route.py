# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider-free route evidence for the Operator O04 lease lifecycle."""

from __future__ import annotations

import json
import hashlib
import tempfile
from collections.abc import Callable

from plane.agent.runtime.credentials import (
    RuntimeCredentialBroker,
    RuntimeCredentialError,
    credential_failure_subreason,
    validate_credential_lease_metadata,
)


_O04_FIELDS = (
    "publicMetadataOnly",
    "queuedLeaseObserved",
    "activeLeaseAdmitted",
    "rotateDispatchDenied",
    "rotateCallbackDenied",
    "revokeDispatchDenied",
    "revokeCallbackDenied",
    "expiryDispatchDenied",
    "expiryCallbackDenied",
)


def _denied(call: Callable[[], object], expected_subreason: str) -> bool:
    try:
        call()
    except RuntimeCredentialError as error:
        return credential_failure_subreason(error) == expected_subreason
    return False


def build_operator_route_evidence() -> tuple[dict[str, object], list[str]]:
    """Prove queued-to-active binding and lifecycle denial at both boundaries."""

    now = [100.0]
    invocation_ref = "invocation:o04-lifecycle"
    agent_ref = "agent:o04-lifecycle"
    with tempfile.TemporaryDirectory(prefix="agent-g4-o04-") as directory:
        state_file = f"{directory}/revocations.json"
        broker = RuntimeCredentialBroker(
            {"runtime": {"api_key": "offline-o04-marker"}},
            ttl_seconds=10,
            clock=lambda: now[0],
            state_file=state_file,
        )

        queued, _ = broker.issue(agent_ref=agent_ref, credential_ref="runtime")
        queued_metadata = queued.public_metadata()
        active = broker.bind(queued.lease_id, invocation_ref=invocation_ref)
        active_metadata = active.public_metadata()
        public_fields = {
            "leaseId",
            "agentRef",
            "credentialRef",
            "invocationRef",
            "generation",
            "issuedAt",
            "expiresAt",
            "rotationGeneration",
        }
        public_metadata_only = all(
            set(metadata) == public_fields
            and "offline-o04-marker" not in json.dumps(metadata, sort_keys=True)
            and "credentialDigest" not in metadata
            for metadata in (queued_metadata, active_metadata)
        )
        active_admitted = (
            broker.resolve(queued.lease_id, agent_ref=agent_ref, invocation_ref=invocation_ref)
            == {"api_key": "offline-o04-marker"}
        )
        validate_credential_lease_metadata(
            active_metadata,
            invocation_ref=invocation_ref,
            state_file=state_file,
            clock=lambda: now[0],
        )

        broker.rotate("runtime")
        rotate_dispatch_denied = _denied(
            lambda: broker.resolve(queued.lease_id, agent_ref=agent_ref, invocation_ref=invocation_ref),
            "credential_lease_revoked",
        )
        rotate_callback_denied = _denied(
            lambda: validate_credential_lease_metadata(
                active_metadata,
                invocation_ref=invocation_ref,
                state_file=state_file,
                clock=lambda: now[0],
            ),
            "credential_lease_rotated",
        )

        revoked, revoked_metadata = broker.issue(agent_ref=agent_ref, credential_ref="runtime")
        revoked = broker.bind(revoked.lease_id, invocation_ref=f"{invocation_ref}:revoke")
        revoke_invocation_ref = revoked_metadata["invocationRef"] if revoked_metadata.get("invocationRef") else revoked.invocation_ref
        broker.revoke(revoked.lease_id)
        revoke_dispatch_denied = _denied(
            lambda: broker.resolve(revoked.lease_id, agent_ref=agent_ref, invocation_ref=revoke_invocation_ref),
            "credential_lease_revoked",
        )
        revoke_callback_denied = _denied(
            lambda: validate_credential_lease_metadata(
                revoked.public_metadata(),
                invocation_ref=revoke_invocation_ref,
                state_file=state_file,
                clock=lambda: now[0],
            ),
            "credential_lease_revoked",
        )

        expired, _ = broker.issue(agent_ref=agent_ref, credential_ref="runtime")
        expired = broker.bind(expired.lease_id, invocation_ref=f"{invocation_ref}:expiry")
        expiry_invocation_ref = expired.invocation_ref
        now[0] = expired.expires_at
        expiry_dispatch_denied = _denied(
            lambda: broker.resolve(expired.lease_id, agent_ref=agent_ref, invocation_ref=expiry_invocation_ref),
            "credential_lease_expired",
        )
        expiry_callback_denied = _denied(
            lambda: validate_credential_lease_metadata(
                expired.public_metadata(),
                invocation_ref=expiry_invocation_ref,
                state_file=state_file,
                clock=lambda: now[0],
            ),
            "credential_lease_expired",
        )

    route = {
        "publicMetadataOnly": public_metadata_only,
        "queuedLeaseObserved": queued.invocation_ref is None and queued_metadata["invocationRef"] is None,
        "activeLeaseAdmitted": active_admitted,
        "rotateDispatchDenied": rotate_dispatch_denied,
        "rotateCallbackDenied": rotate_callback_denied,
        "revokeDispatchDenied": revoke_dispatch_denied,
        "revokeCallbackDenied": revoke_callback_denied,
        "expiryDispatchDenied": expiry_dispatch_denied,
        "expiryCallbackDenied": expiry_callback_denied,
    }
    credential_lifecycle_digest = hashlib.sha256(
        json.dumps(route, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    evidence = {
        "routes": {"O04": route, "replay": {"stateMutations": 0}},
        "readback": {
            "credentialLifecycleDigest": credential_lifecycle_digest,
            "source": "provider-free-runtime-lease-harness/v1",
            "rawValuesRetained": False,
        },
    }
    failures = [f"route:O04:{field}" for field in _O04_FIELDS if route[field] is not True]
    return evidence, failures


__all__ = ["build_operator_route_evidence"]

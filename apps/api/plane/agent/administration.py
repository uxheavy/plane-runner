# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Application ports for the non-UI Plane Agent administration surface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from django.db import transaction

from plane.agent.validation import (
    MAX_AGENT_READBACK_BYTES,
    contains_credential_value,
    is_credential_key,
    validate_bounded_json,
)
from plane.agent.lifecycle import create_profile
from plane.db.models import AgentActor, ProfileVersion


_CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,219}$")


AGENT_ADMIN_L7_ACTIONS = (
    "delegation.lineage.read",
    "hr.proposal.read",
    "hr.proposal.decide",
    "chief_of_staff.provision",
    "evaluator.review",
    "outcome.accept",
    "outcome.request_revision",
    "assignment.cancel",
)


class AgentAdminExtensionError(ValueError):
    """Bounded failure for an unavailable or out-of-scope extension object."""


@dataclass(frozen=True)
class AgentAdminExtensionCommand:
    """The only command envelope an L7 adapter may receive from administration."""

    action: str
    workspace_id: str
    actor_id: str | None
    run_id: str | None
    invocation_id: str | None
    idempotency_key: str
    payload: Mapping[str, Any]
    authenticated_user: Any | None = None

    def __post_init__(self) -> None:
        if self.action not in AGENT_ADMIN_L7_ACTIONS:
            raise ValueError("unsupported Agent admin extension action")
        if not self.workspace_id or not self.idempotency_key:
            raise ValueError("workspace_id and idempotency_key are required")
        if not isinstance(self.idempotency_key, str) or len(self.idempotency_key) > 128:
            raise ValueError("idempotency_key must be at most 128 characters")
        if self.invocation_id is not None and (
            not isinstance(self.invocation_id, str) or not self.invocation_id or len(self.invocation_id) > 128
        ):
            raise ValueError("invocation_id must be a bounded identifier")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a JSON object")
        validate_bounded_json(
            dict(self.payload),
            "payload",
            max_bytes=MAX_AGENT_READBACK_BYTES,
            reject_credentials=True,
        )
        if self.action in {
            "hr.proposal.decide",
            "outcome.accept",
            "outcome.request_revision",
            "assignment.cancel",
        }:
            if self.authenticated_user is None or getattr(self.authenticated_user, "is_anonymous", False):
                raise ValueError("governance decisions require the authenticated caller")
            if any(
                key in self.payload
                for key in (
                    "reviewer_id",
                    "reviewerId",
                    "human_reviewer_id",
                    "humanReviewerId",
                    "operator_id",
                    "operatorId",
                )
            ):
                raise ValueError("reviewer and operator identities must come from the authenticated caller")


class AgentAdminExtensionSerializerPort(Protocol):
    """L7 serializer seam: return only typed, redacted operator projections."""

    resource_name: str

    def serialize(self, value: Any) -> Mapping[str, Any]: ...


class AgentAdminExtensionPort(Protocol):
    """Registration contract for later L6/L7 admin resources.

    Extensions contribute read-only, already-authorized projections. They do
    not receive a request, database handle, credential, or permission hook.
    """

    resource_name: str

    def read(self, *, workspace_id: str, resource_id: str) -> Mapping[str, Any] | None: ...


class AgentAdminExtensionServicePort(AgentAdminExtensionPort, Protocol):
    """Service seam for the bounded L7 actions listed above."""

    def execute(self, command: AgentAdminExtensionCommand) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RegisteredAgentAdminExtension:
    resource_name: str
    port: AgentAdminExtensionPort


_extensions: dict[str, RegisteredAgentAdminExtension] = {}
_MISSING = object()


def register_agent_admin_extension(port: AgentAdminExtensionPort) -> RegisteredAgentAdminExtension:
    """Register one replaceable readback port without changing this core."""

    resource_name = port.resource_name.strip()
    if not resource_name or resource_name in _extensions:
        raise ValueError("Agent admin extension names must be unique and non-empty")
    registration = RegisteredAgentAdminExtension(resource_name=resource_name, port=port)
    _extensions[resource_name] = registration
    return registration


def agent_admin_extension(resource_name: str) -> RegisteredAgentAdminExtension | None:
    return _extensions.get(resource_name)


def validate_credential_ref(value: str | None) -> str | None:
    """Accept only opaque namespaced references; never accept credential data."""

    if value is None:
        return None
    if not isinstance(value, str) or not _CREDENTIAL_REF_PATTERN.fullmatch(value):
        raise ValueError("credential_ref must be an opaque namespaced reference")
    return value


def redact_admin_value(value: Any, *, key: str | None = None) -> Any:
    """Redact secret-shaped values before they cross the admin read boundary."""

    if key is not None and is_credential_key(key):
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(item_key): redact_admin_value(item_value, key=str(item_key)) for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_admin_value(item) for item in value]
    if isinstance(value, str) and contains_credential_value(value):
        return "[redacted]"
    return value


@transaction.atomic
def update_actor(
    actor: AgentActor,
    *,
    display_name: str | None = None,
    credential_ref: str | None | object = _MISSING,
    is_active: bool | None = None,
    updated_by=None,
) -> AgentActor:
    """Update identity facts without changing any profile or run snapshot."""

    locked = AgentActor.objects.select_for_update().get(pk=actor.pk)
    changed = False
    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("display_name must not be empty")
        locked.display_name = display_name
        changed = True
    if credential_ref is not _MISSING:
        locked.credential_ref = validate_credential_ref(credential_ref)
        changed = True
    if is_active is not None:
        locked.is_active = is_active
        changed = True
    if not changed:
        return locked
    if updated_by is not None:
        locked.updated_by = updated_by
    locked.save()
    return locked


def profile_matches_input(profile: ProfileVersion, profile_data: dict[str, Any]) -> bool:
    """Return whether a fixture request already resolves to this profile version."""

    return all(getattr(profile, field) == value for field, value in profile_data.items())


@transaction.atomic
def ensure_fixture_profile(actor: AgentActor, *, created_by=None, **profile_data) -> ProfileVersion:
    """Converge a CLI fixture onto one active immutable profile version."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    profile = ProfileVersion.objects.filter(actor=actor, pk=actor.active_profile_id).first()
    if profile is not None and profile_matches_input(profile, profile_data):
        return profile
    return create_profile(actor, created_by=created_by, **profile_data)

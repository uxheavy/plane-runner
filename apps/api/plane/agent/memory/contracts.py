# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Narrow extension ports for Plane context consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from plane.db.models import AgentActor


class ContextAuthorizationPort(Protocol):
    """Live authorization seam for subject-bound context reads."""

    def can_read_user_preferences(self, *, actor: AgentActor, subject_user_id: str) -> bool:
        """Return whether this runtime context may read one subject user."""

    def can_read_shared_skills(self, *, actor: AgentActor, visibility: str, scope_id: str) -> bool:
        """Return whether this runtime context may read one authorized shared scope."""


class DenySubjectContext:
    """Safe default that prevents accidental user-preference leakage."""

    def can_read_user_preferences(self, *, actor: AgentActor, subject_user_id: str) -> bool:
        return False

    def can_read_shared_skills(self, *, actor: AgentActor, visibility: str, scope_id: str) -> bool:
        return False


@dataclass(frozen=True)
class AgentContextProjection:
    """Runtime-facing projections; no field is a Plane persistence authority."""

    memory_markdown: str
    user_markdown: str
    skill_packages: dict[str, dict[str, str]]

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded operator projection for all existing Agent context foundations."""

from __future__ import annotations

import json
from typing import Any

from plane.agent.administration import redact_admin_value
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.api.serializers.agent_admin import AgentActorAdminSerializer
from plane.api.serializers.agent_context_admin import (
    AgentChangeProposalAdminSerializer,
    AgentMemoryAdminSerializer,
    AgentMemoryRevisionAdminSerializer,
    AgentScheduleAdminSerializer,
    AgentScheduleFireAdminSerializer,
    AgentSkillAdminSerializer,
    AgentSkillRevisionAdminSerializer,
)
from plane.db.models import (
    AgentChangeProposal,
    AgentMemoryEntry,
    AgentMemoryRevision,
    AgentSchedule,
    AgentScheduleFire,
    AgentSkillDefinition,
    AgentSkillRevision,
    AgentActor,
)


class AgentContextReadbackTooLarge(ValueError):
    """Raised when context administration cannot fit in the readback bound."""


def build_actor_context_readback(actor: AgentActor, *, limit: int = 1) -> dict[str, Any]:
    if isinstance(limit, bool) or not 1 <= limit <= 10:
        raise ValueError("context readback limit must be between 1 and 10")
    entries = AgentMemoryEntry.all_objects.filter(actor=actor).order_by("key", "id")
    definitions = AgentSkillDefinition.all_objects.filter(actor=actor).order_by("key", "id")
    payload = {
        "actor": AgentActorAdminSerializer(actor).data,
        "memory": AgentMemoryAdminSerializer(entries[:limit], many=True).data,
        "memory_revisions": AgentMemoryRevision.all_objects.filter(entry__actor=actor).order_by(
            "entry_id", "-revision", "-id"
        )[:limit],
        "skills": AgentSkillAdminSerializer(definitions[:limit], many=True).data,
        "skill_revisions": AgentSkillRevision.all_objects.filter(definition__actor=actor).order_by(
            "definition_id", "-revision", "-id"
        )[:limit],
        "proposals": AgentChangeProposal.objects.filter(actor=actor).order_by("-created_at", "-id")[:limit],
        "schedules": AgentSchedule.objects.filter(actor=actor).order_by("next_fire_at", "name", "id")[:limit],
        "schedule_fires": AgentScheduleFire.objects.filter(schedule__actor=actor).order_by("-scheduled_for", "-id")[
            :limit
        ],
    }
    payload["memory_revisions"] = AgentMemoryRevisionAdminSerializer(payload["memory_revisions"], many=True).data
    payload["skill_revisions"] = AgentSkillRevisionAdminSerializer(payload["skill_revisions"], many=True).data
    payload["proposals"] = AgentChangeProposalAdminSerializer(payload["proposals"], many=True).data
    payload["schedules"] = AgentScheduleAdminSerializer(payload["schedules"], many=True).data
    payload["schedule_fires"] = AgentScheduleFireAdminSerializer(payload["schedule_fires"], many=True).data
    redacted = redact_admin_value(payload)
    if len(json.dumps(redacted, sort_keys=True, default=str).encode("utf-8")) > MAX_AGENT_READBACK_BYTES:
        raise AgentContextReadbackTooLarge("context readback exceeds the 8KB bounded output ceiling; reduce the limit")
    return redacted

"""Narrow schedule extension seam for L4/L5/L10 callers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from plane.db.models import AgentSchedule, AgentScheduleFire


class ScheduleFirePort(Protocol):
    """Plane-side trigger port; implementations return the durable fire ledger."""

    def fire(self, schedule: AgentSchedule, *, scheduled_for: datetime) -> AgentScheduleFire:
        """Create or replay the ordinary assignment linked to a schedule fire."""

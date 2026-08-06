"""Dependency-free limits shared by every public operation transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal


MAX_RESULT_BYTES = 8 * 1024

# These are application-boundary budgets, not a permission model.  A quota
# bucket is deliberately small and fixed so every transport observes the same
# race-free ceiling without inheriting provider or workspace policy state.
QUOTA_WINDOW = timedelta(minutes=1)
QUOTA_MAX_WORKSPACE_REQUESTS = 1_024
QUOTA_MAX_WORKSPACE_ACTIVE = 32
QUOTA_MAX_AGENT_REQUESTS = 256
QUOTA_MAX_AGENT_ACTIVE = 8
QUOTA_MAX_INVOCATION_REQUESTS = 64
# A runtime invocation is Hermes' tool-dispatch scope, not one gateway call.
# Reuse the bounded per-Agent fan-out so independent calls can overlap.
QUOTA_MAX_INVOCATION_ACTIVE = QUOTA_MAX_AGENT_ACTIVE
QUOTA_RETENTION = timedelta(hours=24)
QUOTA_CLEANUP_BATCH_SIZE = 500
MAX_QUOTA_IDENTITY_LENGTH = 512

QuotaScope = Literal["workspace", "agent", "invocation"]


@dataclass(frozen=True)
class QuotaLimit:
    scope: QuotaScope
    max_requests: int
    max_active: int


QUOTA_LIMITS = (
    QuotaLimit("workspace", QUOTA_MAX_WORKSPACE_REQUESTS, QUOTA_MAX_WORKSPACE_ACTIVE),
    QuotaLimit("agent", QUOTA_MAX_AGENT_REQUESTS, QUOTA_MAX_AGENT_ACTIVE),
    QuotaLimit("invocation", QUOTA_MAX_INVOCATION_REQUESTS, QUOTA_MAX_INVOCATION_ACTIVE),
)

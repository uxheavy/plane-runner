"""Plane-owned Agent memory and context projections."""

from .contracts import AgentContextProjection, ContextAuthorizationPort, DenySubjectContext, MemoryProjectionPort
from .projections import (
    ProjectedMemory,
    parse_memory_markdown,
    project_memory_markdown,
    project_user_markdown,
    reproject_memory_markdown,
)
from .services import (
    AgentMemoryError,
    apply_memory_retention,
    assemble_agent_context,
    capture_memory_candidate,
    create_memory,
    create_user_preference,
    delete_memory,
    propose_memory_change,
    promote_proposal,
    review_proposal,
    rollback_memory,
)

__all__ = [
    "AgentContextProjection",
    "AgentMemoryError",
    "ContextAuthorizationPort",
    "DenySubjectContext",
    "MemoryProjectionPort",
    "ProjectedMemory",
    "apply_memory_retention",
    "assemble_agent_context",
    "capture_memory_candidate",
    "create_memory",
    "create_user_preference",
    "delete_memory",
    "parse_memory_markdown",
    "project_memory_markdown",
    "project_user_markdown",
    "reproject_memory_markdown",
    "propose_memory_change",
    "promote_proposal",
    "review_proposal",
    "rollback_memory",
]

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Domain services for scoped memory, gardener governance, and context assembly."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from plane.agent.lifecycle.runtime_contract import canonical_json, command_fingerprint, content_digest
from plane.db.models import (
    AgentActor,
    AgentChangeProposal,
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryRevision,
    AgentMemoryVisibility,
    AgentProposalKind,
    AgentProposalState,
    AgentProvenanceKind,
    AgentRevisionState,
    AgentRole,
    WorkspaceMember,
)

from .contracts import AgentContextProjection, ContextAuthorizationPort, DenySubjectContext
from .projections import project_memory_markdown, project_user_markdown


class AgentMemoryError(ValidationError):
    """Base error for memory and governance commands."""


def _text(value: Any, field: str, limit: int = 65_536) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > limit:
        raise AgentMemoryError(f"{field} must be a non-empty string within {limit} UTF-8 bytes")
    return value


def _key(value: Any) -> str:
    return _text(value, "memory key", 255)


def _subject_visibility(visibility: str, subject_user) -> None:
    if visibility == AgentMemoryVisibility.SUBJECT_USER and subject_user is None:
        raise AgentMemoryError("subject-user memory requires subject_user")
    if visibility == AgentMemoryVisibility.AGENT_PRIVATE and subject_user is not None:
        raise AgentMemoryError("Agent-private memory cannot bind a subject user")


def _scope_actor(actor: AgentActor) -> AgentActor:
    actor = AgentActor.objects.select_related("active_profile").get(pk=actor.pk)
    if not actor.is_active:
        raise AgentMemoryError("Inactive Agent actors cannot change memory")
    return actor


def _ensure_gardener(gardener: AgentActor) -> AgentActor:
    gardener = _scope_actor(gardener)
    if gardener.active_profile_id is None or gardener.active_profile.role != AgentRole.GARDENER:
        raise AgentMemoryError("Only an Agent with the current gardener role may propose changes")
    return gardener


def _ensure_human_reviewer(reviewer, *, workspace_id) -> object:
    """Require a live, non-bot workspace member for governance actions."""

    if reviewer is None or getattr(reviewer, "pk", None) is None:
        raise AgentMemoryError("Governance requires a persisted human reviewer")
    if not getattr(reviewer, "is_active", False) or getattr(reviewer, "is_bot", False):
        raise AgentMemoryError("Governance reviewer must be an active human user")
    if not WorkspaceMember.objects.filter(
        workspace_id=workspace_id,
        member_id=reviewer.pk,
        role__gte=15,
        is_active=True,
    ).exists():
        raise AgentMemoryError("Governance reviewer is not authorized for the Agent workspace")
    return reviewer


def _latest_memory_revision(entry: AgentMemoryEntry) -> AgentMemoryRevision | None:
    return (
        AgentMemoryRevision.objects.filter(entry=entry, state=AgentRevisionState.ACTIVE).order_by("-revision").first()
    )


def _next_revision(entry: AgentMemoryEntry) -> int:
    latest = (
        AgentMemoryRevision.objects.filter(entry=entry).order_by("-revision").values_list("revision", flat=True).first()
    )
    return (latest or 0) + 1


def _create_memory_revision(
    entry: AgentMemoryEntry,
    *,
    content: str,
    state: str,
    provenance: str,
    provenance_ref: str = "",
    source_actor: AgentActor | None = None,
    source_run=None,
    rationale: str = "",
    predecessor: AgentMemoryRevision | None = None,
) -> AgentMemoryRevision:
    content = _text(content, "memory content")
    try:
        content_digest_value = content_digest({"content": content})
        canonical_json({"content": content})
    except Exception as exc:
        raise AgentMemoryError("memory content must be canonical JSON-compatible text") from exc
    return AgentMemoryRevision.objects.create(
        workspace=entry.workspace,
        project=entry.project,
        entry=entry,
        revision=_next_revision(entry),
        predecessor=predecessor,
        state=state,
        content=content,
        content_digest=content_digest_value,
        provenance=provenance,
        provenance_ref=provenance_ref,
        source_actor=source_actor,
        source_run=source_run,
        rationale=rationale,
    )


@transaction.atomic
def create_memory(
    actor: AgentActor,
    *,
    key: str,
    content: str,
    kind: str = AgentMemoryKind.FACT,
    visibility: str = AgentMemoryVisibility.AGENT_PRIVATE,
    subject_user=None,
    provenance: str = AgentProvenanceKind.HUMAN,
    provenance_ref: str = "",
    source_run=None,
    retention_expires_at: datetime | None = None,
    created_by=None,
) -> AgentMemoryEntry:
    """Create one active Plane memory entry and its first immutable revision."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    key = _key(key)
    content = _text(content, "memory content")
    if kind not in AgentMemoryKind.values:
        raise AgentMemoryError("Unknown memory kind")
    if visibility not in AgentMemoryVisibility.values:
        raise AgentMemoryError("Unknown memory visibility")
    if provenance not in AgentProvenanceKind.values:
        raise AgentMemoryError("Unknown memory provenance")
    _subject_visibility(visibility, subject_user)
    if visibility == AgentMemoryVisibility.SUBJECT_USER and kind != AgentMemoryKind.PREFERENCE:
        raise AgentMemoryError("Subject-user memory must be a preference")
    entry = AgentMemoryEntry.objects.create(
        workspace=actor.workspace,
        project=actor.project,
        actor=actor,
        key=key,
        kind=kind,
        visibility=visibility,
        subject_user=subject_user,
        retention_expires_at=retention_expires_at,
        created_by=created_by,
    )
    _create_memory_revision(
        entry,
        content=content,
        state=AgentRevisionState.ACTIVE,
        provenance=provenance,
        provenance_ref=provenance_ref,
        source_actor=actor if provenance == AgentProvenanceKind.RUNTIME else None,
        source_run=source_run,
    )
    return entry


def create_user_preference(actor: AgentActor, *, subject_user, key: str, content: str, **kwargs) -> AgentMemoryEntry:
    """Create a subject-bound preference, never an Agent-private memory."""

    return create_memory(
        actor,
        key=key,
        content=content,
        kind=AgentMemoryKind.PREFERENCE,
        visibility=AgentMemoryVisibility.SUBJECT_USER,
        subject_user=subject_user,
        **kwargs,
    )


@transaction.atomic
def capture_memory_candidate(
    actor: AgentActor,
    *,
    key: str,
    content: str,
    source_run=None,
    provenance_ref: str = "",
    rationale: str = "",
    created_by=None,
) -> AgentMemoryRevision:
    """Capture automatic learning as an Agent-scoped candidate only."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    key = _key(key)
    entry = AgentMemoryEntry.objects.filter(
        actor=actor,
        key=key,
        visibility=AgentMemoryVisibility.AGENT_PRIVATE,
        subject_user__isnull=True,
    ).first()
    if entry is None:
        entry = AgentMemoryEntry.objects.create(
            workspace=actor.workspace,
            project=actor.project,
            actor=actor,
            key=key,
            kind=AgentMemoryKind.FACT,
            visibility=AgentMemoryVisibility.AGENT_PRIVATE,
            created_by=created_by,
        )
    return _create_memory_revision(
        entry,
        content=content,
        state=AgentRevisionState.CANDIDATE,
        provenance=AgentProvenanceKind.AGENT_LEARNING,
        provenance_ref=provenance_ref,
        source_actor=actor,
        source_run=source_run,
        rationale=rationale,
    )


@transaction.atomic
def propose_memory_change(
    actor: AgentActor,
    *,
    key: str,
    content: str,
    gardener: AgentActor,
    rationale: str,
    idempotency_key: str | None = None,
    source_run=None,
    created_by=None,
) -> AgentChangeProposal:
    """Create a reviewable Agent-private gardener proposal."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    gardener = _ensure_gardener(gardener)
    if gardener.workspace_id != actor.workspace_id or (
        gardener.project_id is not None and gardener.project_id != actor.project_id
    ):
        raise AgentMemoryError("Gardener is outside the target Agent scope")
    rationale = _text(rationale, "proposal rationale")
    key = _key(key)
    if idempotency_key is not None:
        idempotency_key = _text(idempotency_key, "proposal idempotency_key", 128)
    if idempotency_key:
        binding = {"actor": str(actor.id), "key": key, "content": content, "gardener": str(gardener.id)}
        fingerprint = command_fingerprint("propose_memory_change", binding)
        existing = AgentChangeProposal.all_objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.command_fingerprint != fingerprint:
                raise AgentMemoryError("Proposal idempotency key is bound to another command")
            return existing
    else:
        fingerprint = None
    entry = AgentMemoryEntry.objects.filter(
        actor=actor,
        key=key,
        visibility=AgentMemoryVisibility.AGENT_PRIVATE,
        subject_user__isnull=True,
    ).first()
    if entry is None:
        entry = AgentMemoryEntry.objects.create(
            workspace=actor.workspace,
            project=actor.project,
            actor=actor,
            key=key,
            kind=AgentMemoryKind.FACT,
            visibility=AgentMemoryVisibility.AGENT_PRIVATE,
            created_by=created_by,
        )
    candidate = _create_memory_revision(
        entry,
        content=content,
        state=AgentRevisionState.CANDIDATE,
        provenance=AgentProvenanceKind.GARDENER,
        provenance_ref=f"gardener:{gardener.id}",
        source_actor=gardener,
        source_run=source_run,
        rationale=rationale,
    )
    return AgentChangeProposal.objects.create(
        workspace=actor.workspace,
        project=actor.project,
        kind=AgentProposalKind.MEMORY,
        actor=actor,
        memory_revision=candidate,
        rationale=rationale,
        proposed_by=gardener,
        idempotency_key=idempotency_key,
        command_fingerprint=fingerprint,
        created_by=created_by,
    )


@transaction.atomic
def review_proposal(proposal: AgentChangeProposal, *, reviewer, approve: bool, note: str = "") -> AgentChangeProposal:
    """Record human governance without changing the candidate revision."""

    locked = AgentChangeProposal.objects.select_for_update().get(pk=proposal.pk)
    _ensure_human_reviewer(reviewer, workspace_id=locked.workspace_id)
    if locked.state in {AgentProposalState.APPLIED, AgentProposalState.REJECTED}:
        return locked
    if locked.state != AgentProposalState.PROPOSED:
        raise AgentMemoryError(f"Proposal cannot be reviewed from {locked.state}")
    locked.state = AgentProposalState.APPROVED if approve else AgentProposalState.REJECTED
    locked.reviewed_by = reviewer
    locked.reviewed_at = timezone.now()
    locked.review_note = note
    locked.save()
    return locked


@transaction.atomic
def promote_proposal(proposal: AgentChangeProposal, *, reviewer=None):
    """Promote an approved proposal, dispatching skill proposals lazily."""

    locked = AgentChangeProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.kind == AgentProposalKind.SKILL:
        from plane.agent.skills.services import promote_skill_proposal

        return promote_skill_proposal(locked, reviewer=reviewer)
    if locked.state == AgentProposalState.APPLIED:
        return AgentMemoryRevision.objects.get(pk=locked.applied_revision_ref)
    if locked.state != AgentProposalState.APPROVED or locked.reviewed_by_id is None or locked.reviewed_at is None:
        raise AgentMemoryError("Only a human-approved proposal may be promoted")
    candidate = AgentMemoryRevision.objects.select_related("entry").get(pk=locked.memory_revision_id)
    entry = AgentMemoryEntry.objects.select_for_update().get(pk=candidate.entry_id)
    _ensure_human_reviewer(locked.reviewed_by, workspace_id=entry.workspace_id)
    if candidate.state != AgentRevisionState.CANDIDATE:
        raise AgentMemoryError("Only a candidate memory revision may be promoted")
    predecessor = _latest_memory_revision(entry)
    revision = _create_memory_revision(
        entry,
        content=candidate.content,
        state=AgentRevisionState.ACTIVE,
        provenance=AgentProvenanceKind.GARDENER,
        provenance_ref=f"proposal:{locked.id}",
        source_actor=locked.proposed_by,
        source_run=candidate.source_run,
        rationale=locked.rationale,
        predecessor=predecessor,
    )
    locked.state = AgentProposalState.APPLIED
    locked.applied_revision_ref = str(revision.id)
    locked.save()
    return revision


@transaction.atomic
def rollback_memory(
    entry: AgentMemoryEntry,
    *,
    to_revision: AgentMemoryRevision,
    reviewer,
    rationale: str,
    now: datetime | None = None,
) -> AgentMemoryRevision:
    """Restore an earlier content state by appending a new revision."""

    now = now or timezone.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise AgentMemoryError("Rollback requires an aware timestamp")
    locked_entry = AgentMemoryEntry.all_objects.select_for_update().get(pk=entry.pk)
    _ensure_human_reviewer(reviewer, workspace_id=locked_entry.workspace_id)
    if locked_entry.retention_expires_at is not None and locked_entry.retention_expires_at <= now:
        raise AgentMemoryError("Memory retention has expired; rollback cannot restore this entry")
    target = AgentMemoryRevision.all_objects.select_for_update().get(pk=to_revision.pk)
    if target.entry_id != locked_entry.id:
        raise AgentMemoryError("Rollback revision belongs to another memory entry")
    if target.state != AgentRevisionState.ACTIVE:
        raise AgentMemoryError("Rollback requires an active memory revision")
    predecessor = _latest_memory_revision(locked_entry)
    if predecessor is None:
        raise AgentMemoryError("Memory entry has no active revision")
    provenance_ref = f"memory-revision:{target.id}"
    existing = AgentMemoryRevision.all_objects.filter(
        entry=locked_entry,
        provenance=AgentProvenanceKind.ROLLBACK,
        provenance_ref=provenance_ref,
        state=AgentRevisionState.ACTIVE,
    ).first()
    if existing is not None:
        return existing
    if locked_entry.deleted_at is not None:
        locked_entry.deleted_at = None
        locked_entry.deletion_reason = ""
        locked_entry.deleted_by = None
        locked_entry.save(_allow_governance=True)
    return _create_memory_revision(
        locked_entry,
        content=target.content,
        state=AgentRevisionState.ACTIVE,
        provenance=AgentProvenanceKind.ROLLBACK,
        provenance_ref=provenance_ref,
        rationale=_text(rationale, "rollback rationale"),
        predecessor=predecessor,
    )


@transaction.atomic
def delete_memory(entry: AgentMemoryEntry, *, reviewer=None, reason: str, retention: bool = False) -> AgentMemoryEntry:
    """Tombstone a memory entry; immutable revisions remain for audit and rollback."""

    if reviewer is None and not retention:
        raise AgentMemoryError("Memory deletion requires a human reviewer or retention policy")
    locked = AgentMemoryEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.deleted_at is not None:
        return locked
    locked.deleted_at = timezone.now()
    locked.deletion_reason = _text(reason, "deletion reason", 255)
    locked.deleted_by = reviewer
    locked.save(_allow_governance=True)
    return locked


@transaction.atomic
def apply_memory_retention(*, now: datetime | None = None, actor: AgentActor | None = None) -> int:
    """Apply stored retention deadlines without deleting immutable revisions."""

    now = now or timezone.now()
    queryset = AgentMemoryEntry.objects.filter(retention_expires_at__isnull=False, retention_expires_at__lte=now)
    if actor is not None:
        queryset = queryset.filter(actor=actor)
    count = 0
    for entry in queryset.select_for_update():
        delete_memory(entry, reason="retention policy expired", retention=True)
        count += 1
    return count


def _latest_entry_revision(entry: AgentMemoryEntry) -> AgentMemoryRevision | None:
    return _latest_memory_revision(entry)


def assemble_agent_context(
    actor: AgentActor,
    *,
    subject_user=None,
    authorization: ContextAuthorizationPort | None = None,
) -> AgentContextProjection:
    """Assemble isolated memory/user/skill projections for one runtime context."""

    actor = _scope_actor(actor)
    authorization = authorization or DenySubjectContext()
    now = timezone.now()
    private_entries = list(
        AgentMemoryEntry.objects.filter(
            actor=actor,
            visibility=AgentMemoryVisibility.AGENT_PRIVATE,
            subject_user__isnull=True,
            deleted_at__isnull=True,
        ).filter(Q(retention_expires_at__isnull=True) | Q(retention_expires_at__gt=now))
    )
    private_pairs = [
        (entry, revision) for entry in private_entries if (revision := _latest_entry_revision(entry)) is not None
    ]
    user_pairs: list[tuple[AgentMemoryEntry, AgentMemoryRevision]] = []
    if subject_user is not None and authorization.can_read_user_preferences(
        actor=actor, subject_user_id=str(subject_user.id)
    ):
        user_entries = AgentMemoryEntry.objects.filter(
            actor=actor,
            visibility=AgentMemoryVisibility.SUBJECT_USER,
            subject_user=subject_user,
            kind=AgentMemoryKind.PREFERENCE,
            deleted_at__isnull=True,
        ).filter(Q(retention_expires_at__isnull=True) | Q(retention_expires_at__gt=now))
        user_pairs = [
            (entry, revision) for entry in user_entries if (revision := _latest_entry_revision(entry)) is not None
        ]
    from plane.agent.skills.services import project_visible_skill_packages

    return AgentContextProjection(
        memory_markdown=project_memory_markdown(private_pairs),
        user_markdown=project_user_markdown(user_pairs),
        skill_packages=project_visible_skill_packages(actor, subject_user=subject_user, authorization=authorization),
    )

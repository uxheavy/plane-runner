"""Domain services for Plane-owned skills and gardener proposals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from plane.agent.lifecycle.runtime_contract import command_fingerprint
from plane.db.models import (
    AgentActor,
    AgentChangeProposal,
    AgentProposalKind,
    AgentProposalState,
    AgentProvenanceKind,
    AgentRevisionState,
    AgentSkillDefinition,
    AgentSkillRevision,
    AgentSkillVisibility,
)

from plane.agent.memory.contracts import ContextAuthorizationPort, DenySubjectContext
from plane.agent.memory.services import AgentMemoryError, _ensure_gardener, _scope_actor

from .projections import normalize_skill_files, project_skill_package, skill_package_digest


def _skill_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 255:
        raise AgentMemoryError("skill key must be a non-empty string within 255 UTF-8 bytes")
    return value


def _visibility(visibility: str, subject_user) -> None:
    if visibility not in AgentSkillVisibility.values:
        raise AgentMemoryError("Unknown skill visibility")
    if visibility == AgentSkillVisibility.SUBJECT_USER and subject_user is None:
        raise AgentMemoryError("subject-user skill requires subject_user")
    if visibility != AgentSkillVisibility.SUBJECT_USER and subject_user is not None:
        raise AgentMemoryError("only subject-user skills may bind a subject user")


def _latest_revision(definition: AgentSkillDefinition) -> AgentSkillRevision | None:
    return (
        AgentSkillRevision.objects.filter(definition=definition, state=AgentRevisionState.ACTIVE)
        .order_by("-revision")
        .first()
    )


def _next_revision(definition: AgentSkillDefinition) -> int:
    latest = (
        AgentSkillRevision.objects.filter(definition=definition)
        .order_by("-revision")
        .values_list("revision", flat=True)
        .first()
    )
    return (latest or 0) + 1


def _create_revision(
    definition: AgentSkillDefinition,
    *,
    package_files: dict[str, str],
    state: str,
    provenance: str,
    provenance_ref: str = "",
    source_actor: AgentActor | None = None,
    source_run=None,
    rationale: str = "",
    predecessor: AgentSkillRevision | None = None,
) -> AgentSkillRevision:
    files = normalize_skill_files(package_files)
    return AgentSkillRevision.objects.create(
        workspace=definition.workspace,
        project=definition.project,
        definition=definition,
        revision=_next_revision(definition),
        predecessor=predecessor,
        state=state,
        package_files=files,
        package_digest=skill_package_digest(files),
        provenance=provenance,
        provenance_ref=provenance_ref,
        source_actor=source_actor,
        source_run=source_run,
        rationale=rationale,
    )


@transaction.atomic
def create_skill(
    actor: AgentActor,
    *,
    key: str,
    package_files: dict[str, str],
    display_name: str | None = None,
    description: str = "",
    visibility: str = AgentSkillVisibility.AGENT_PRIVATE,
    subject_user=None,
    provenance: str = AgentProvenanceKind.HUMAN,
    provenance_ref: str = "",
    source_run=None,
    retention_expires_at: datetime | None = None,
    created_by=None,
) -> AgentSkillDefinition:
    """Create one Plane skill definition and its first active revision."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    key = _skill_key(key)
    _visibility(visibility, subject_user)
    if provenance not in AgentProvenanceKind.values:
        raise AgentMemoryError("Unknown skill provenance")
    if (
        visibility
        in {
            AgentSkillVisibility.TEMPLATE,
            AgentSkillVisibility.WORKSPACE,
            AgentSkillVisibility.ORGANIZATION,
        }
        and provenance != AgentProvenanceKind.HUMAN
    ):
        raise AgentMemoryError("Shared skills require human promotion")
    files = normalize_skill_files(package_files)
    definition = AgentSkillDefinition.objects.create(
        workspace=actor.workspace,
        project=actor.project,
        actor=actor,
        key=key,
        display_name=display_name or key,
        description=description,
        visibility=visibility,
        subject_user=subject_user,
        retention_expires_at=retention_expires_at,
        created_by=created_by,
    )
    _create_revision(
        definition,
        package_files=files,
        state=AgentRevisionState.ACTIVE,
        provenance=provenance,
        provenance_ref=provenance_ref,
        source_actor=actor if provenance == AgentProvenanceKind.RUNTIME else None,
        source_run=source_run,
    )
    return definition


@transaction.atomic
def capture_skill_candidate(
    actor: AgentActor,
    *,
    key: str,
    package_files: dict[str, str],
    source_run=None,
    rationale: str = "",
    created_by=None,
) -> AgentSkillRevision:
    """Capture automatic learning as a private candidate only."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    key = _skill_key(key)
    definition = AgentSkillDefinition.objects.filter(
        actor=actor,
        key=key,
        visibility=AgentSkillVisibility.AGENT_PRIVATE,
        subject_user__isnull=True,
    ).first()
    if definition is None:
        definition = AgentSkillDefinition.objects.create(
            workspace=actor.workspace,
            project=actor.project,
            actor=actor,
            key=key,
            display_name=key,
            visibility=AgentSkillVisibility.AGENT_PRIVATE,
            created_by=created_by,
        )
    return _create_revision(
        definition,
        package_files=package_files,
        state=AgentRevisionState.CANDIDATE,
        provenance=AgentProvenanceKind.AGENT_LEARNING,
        provenance_ref=f"agent:{actor.id}",
        source_actor=actor,
        source_run=source_run,
        rationale=rationale,
    )


@transaction.atomic
def propose_skill_change(
    actor: AgentActor,
    *,
    key: str,
    package_files: dict[str, str],
    gardener: AgentActor,
    rationale: str,
    requested_visibility: str = AgentSkillVisibility.AGENT_PRIVATE,
    idempotency_key: str | None = None,
    source_run=None,
    created_by=None,
) -> AgentChangeProposal:
    """Create a candidate skill revision; sharing is only a later human decision."""

    actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
    actor = _scope_actor(actor)
    gardener = _ensure_gardener(gardener)
    if gardener.workspace_id != actor.workspace_id or (
        gardener.project_id is not None and gardener.project_id != actor.project_id
    ):
        raise AgentMemoryError("Gardener is outside the target Agent scope")
    if requested_visibility not in AgentSkillVisibility.values:
        raise AgentMemoryError("Unknown skill visibility")
    if requested_visibility == AgentSkillVisibility.SUBJECT_USER:
        raise AgentMemoryError("Skill proposals require an explicit subject-user API")
    if idempotency_key is not None:
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key.encode("utf-8")) > 128
        ):
            raise AgentMemoryError("proposal idempotency_key must be a non-empty string within 128 UTF-8 bytes")
    if idempotency_key:
        fingerprint = command_fingerprint(
            "propose_skill_change",
            {"actor": str(actor.id), "key": key, "files": package_files, "gardener": str(gardener.id)},
        )
        existing = AgentChangeProposal.all_objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.command_fingerprint != fingerprint:
                raise AgentMemoryError("Proposal idempotency key is bound to another command")
            return existing
    else:
        fingerprint = None
    definition = AgentSkillDefinition.objects.filter(
        actor=actor,
        key=_skill_key(key),
        visibility=AgentSkillVisibility.AGENT_PRIVATE,
        subject_user__isnull=True,
    ).first()
    if definition is None:
        definition = AgentSkillDefinition.objects.create(
            workspace=actor.workspace,
            project=actor.project,
            actor=actor,
            key=key,
            display_name=key,
            visibility=AgentSkillVisibility.AGENT_PRIVATE,
            created_by=created_by,
        )
    candidate = _create_revision(
        definition,
        package_files=package_files,
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
        kind=AgentProposalKind.SKILL,
        actor=actor,
        skill_revision=candidate,
        rationale=rationale,
        requested_visibility=requested_visibility,
        proposed_by=gardener,
        idempotency_key=idempotency_key,
        command_fingerprint=fingerprint,
        created_by=created_by,
    )


@transaction.atomic
def promote_skill_proposal(proposal: AgentChangeProposal, *, reviewer=None) -> AgentSkillRevision:
    locked = AgentChangeProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.state == AgentProposalState.APPLIED:
        return AgentSkillRevision.objects.get(pk=locked.applied_revision_ref)
    if locked.state != AgentProposalState.APPROVED or locked.reviewed_by_id is None:
        raise AgentMemoryError("Only a human-approved skill proposal may be promoted")
    candidate = AgentSkillRevision.objects.select_related("definition").get(pk=locked.skill_revision_id)
    definition = AgentSkillDefinition.objects.select_for_update().get(pk=candidate.definition_id)
    requested_visibility = locked.requested_visibility or definition.visibility
    if requested_visibility != definition.visibility:
        definition.visibility = requested_visibility
        definition.save(_allow_governance=True)
    predecessor = _latest_revision(definition)
    revision = _create_revision(
        definition,
        package_files=candidate.package_files,
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
def rollback_skill(definition: AgentSkillDefinition, *, to_revision: AgentSkillRevision, reviewer, rationale: str):
    if reviewer is None:
        raise AgentMemoryError("Rollback requires a human reviewer")
    locked = AgentSkillDefinition.objects.select_for_update().get(pk=definition.pk)
    target = AgentSkillRevision.objects.get(pk=to_revision.pk)
    if target.definition_id != locked.id:
        raise AgentMemoryError("Rollback revision belongs to another skill")
    predecessor = _latest_revision(locked)
    if predecessor is None:
        raise AgentMemoryError("Skill has no active revision")
    if locked.deleted_at is not None:
        locked.deleted_at = None
        locked.deletion_reason = ""
        locked.deleted_by = None
        locked.save(_allow_governance=True)
    return _create_revision(
        locked,
        package_files=target.package_files,
        state=AgentRevisionState.ACTIVE,
        provenance=AgentProvenanceKind.ROLLBACK,
        provenance_ref=f"skill-revision:{target.id}",
        rationale=rationale,
        predecessor=predecessor,
    )


@transaction.atomic
def delete_skill(definition: AgentSkillDefinition, *, reviewer=None, reason: str, retention: bool = False):
    if reviewer is None and not retention:
        raise AgentMemoryError("Skill deletion requires a human reviewer or retention policy")
    locked = AgentSkillDefinition.objects.select_for_update().get(pk=definition.pk)
    if locked.deleted_at is not None:
        return locked
    locked.deleted_at = timezone.now()
    locked.deletion_reason = reason
    locked.deleted_by = reviewer
    locked.save(_allow_governance=True)
    return locked


@transaction.atomic
def apply_skill_retention(*, now: datetime | None = None, actor: AgentActor | None = None) -> int:
    now = now or timezone.now()
    queryset = AgentSkillDefinition.objects.filter(retention_expires_at__isnull=False, retention_expires_at__lte=now)
    if actor is not None:
        queryset = queryset.filter(actor=actor)
    count = 0
    for definition in queryset.select_for_update():
        delete_skill(definition, reason="retention policy expired", retention=True)
        count += 1
    return count


def project_visible_skill_packages(
    actor: AgentActor,
    *,
    subject_user=None,
    authorization: ContextAuthorizationPort | None = None,
) -> dict[str, dict[str, str]]:
    """Project only skill definitions authorized for this runtime context."""

    actor = _scope_actor(actor)
    authorization = authorization or DenySubjectContext()
    definitions = AgentSkillDefinition.objects.filter(
        Q(actor=actor, visibility__in={AgentSkillVisibility.AGENT_PRIVATE, AgentSkillVisibility.SUBJECT_USER})
        | Q(
            workspace=actor.workspace,
            visibility__in={
                AgentSkillVisibility.TEMPLATE,
                AgentSkillVisibility.WORKSPACE,
                AgentSkillVisibility.ORGANIZATION,
            },
        ),
        deleted_at__isnull=True,
    ).order_by("key", "visibility", "id")
    projected: dict[str, dict[str, str]] = {}
    for definition in definitions:
        visible = definition.visibility == AgentSkillVisibility.AGENT_PRIVATE
        if (
            definition.visibility == AgentSkillVisibility.SUBJECT_USER
            and subject_user is not None
            and definition.subject_user_id == subject_user.id
        ):
            visible = authorization.can_read_user_preferences(actor=actor, subject_user_id=str(subject_user.id))
        if definition.visibility in {
            AgentSkillVisibility.TEMPLATE,
            AgentSkillVisibility.WORKSPACE,
            AgentSkillVisibility.ORGANIZATION,
        }:
            can_read_shared = getattr(authorization, "can_read_shared_skills", None)
            visible = bool(can_read_shared and can_read_shared(actor=actor, visibility=definition.visibility))
        if not visible:
            continue
        revision = _latest_revision(definition)
        if revision is not None:
            projected[definition.key] = project_skill_package(revision)
    return {key: projected[key] for key in sorted(projected)}

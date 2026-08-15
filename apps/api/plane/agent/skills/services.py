"""Domain services for Plane-owned skills and gardener proposals."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

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
from plane.agent.memory.services import AgentMemoryError, _ensure_gardener, _ensure_human_reviewer, _scope_actor

from .projections import normalize_skill_files, project_skill_package, skill_package_digest


_UNSUPPORTED_SHARED_VISIBILITIES = frozenset({AgentSkillVisibility.TEMPLATE, AgentSkillVisibility.ORGANIZATION})


def _skill_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 255:
        raise AgentMemoryError("skill key must be a non-empty string within 255 UTF-8 bytes")
    return value


def _rationale(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 65_536:
        raise AgentMemoryError("rollback rationale must be a non-empty string within 65536 UTF-8 bytes")
    return value


def _visibility(visibility: str, subject_user) -> None:
    if visibility not in AgentSkillVisibility.values:
        raise AgentMemoryError("Unknown skill visibility")
    if visibility == AgentSkillVisibility.SUBJECT_USER and subject_user is None:
        raise AgentMemoryError("subject-user skill requires subject_user")
    if visibility != AgentSkillVisibility.SUBJECT_USER and subject_user is not None:
        raise AgentMemoryError("only subject-user skills may bind a subject user")


def _requested_scope_id(visibility: str, scope_id, *, workspace_id) -> UUID | None:
    """Bind shared promotion to an authoritative Plane scope, or fail closed."""

    if visibility == AgentSkillVisibility.AGENT_PRIVATE:
        if scope_id is not None:
            raise AgentMemoryError("Agent-private skill promotion cannot carry a shared scope")
        return None
    if visibility == AgentSkillVisibility.WORKSPACE:
        if scope_id is None:
            raise AgentMemoryError("Workspace skill promotion requires the target workspace scope id")
        try:
            parsed = UUID(str(scope_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AgentMemoryError("Workspace skill promotion scope id is invalid") from exc
        if parsed != workspace_id:
            raise AgentMemoryError("Workspace skill promotion scope is outside the target Agent workspace")
        return parsed
    if visibility in _UNSUPPORTED_SHARED_VISIBILITIES:
        raise AgentMemoryError(
            f"Unsupported shared skill scope: {visibility}; Plane has no authoritative owner for this scope"
        )
    if visibility == AgentSkillVisibility.SUBJECT_USER:
        raise AgentMemoryError("Subject-user skill promotion requires an explicit subject-user API")
    raise AgentMemoryError("Unknown skill promotion scope")


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
    if visibility not in {AgentSkillVisibility.AGENT_PRIVATE, AgentSkillVisibility.SUBJECT_USER}:
        raise AgentMemoryError("Direct skill creation supports only Agent-private or subject-user visibility")
    if provenance not in AgentProvenanceKind.values:
        raise AgentMemoryError("Unknown skill provenance")
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
    requested_scope_id=None,
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
    requested_scope_id = _requested_scope_id(
        requested_visibility,
        requested_scope_id,
        workspace_id=actor.workspace_id,
    )
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
            {
                "actor": str(actor.id),
                "key": key,
                "files": package_files,
                "gardener": str(gardener.id),
                "requestedVisibility": requested_visibility,
                "requestedScopeId": str(requested_scope_id) if requested_scope_id else None,
            },
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
        requested_scope_id=requested_scope_id,
        proposed_by=gardener,
        idempotency_key=idempotency_key,
        command_fingerprint=fingerprint,
        created_by=created_by,
    )


@transaction.atomic
def promote_skill_proposal(proposal: AgentChangeProposal, *, reviewer=None) -> AgentSkillRevision:
    locked = AgentChangeProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.state == AgentProposalState.APPLIED:
        return AgentSkillRevision.all_objects.get(pk=locked.applied_revision_ref)
    if locked.state != AgentProposalState.APPROVED or locked.reviewed_by_id is None or locked.reviewed_at is None:
        raise AgentMemoryError("Only a human-approved skill proposal may be promoted")
    candidate = AgentSkillRevision.all_objects.select_related("definition").get(pk=locked.skill_revision_id)
    definition = AgentSkillDefinition.objects.select_for_update().get(pk=candidate.definition_id)
    requested_visibility = locked.requested_visibility or definition.visibility
    _ensure_human_reviewer(locked.reviewed_by, workspace_id=definition.workspace_id)
    if candidate.state != AgentRevisionState.CANDIDATE:
        raise AgentMemoryError("Only a candidate skill revision may be promoted")
    requested_scope_id = _requested_scope_id(
        requested_visibility,
        locked.requested_scope_id,
        workspace_id=definition.workspace_id,
    )
    if requested_visibility != definition.visibility or requested_scope_id != definition.shared_scope_id:
        definition.visibility = requested_visibility
        definition.shared_scope_id = requested_scope_id
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
def rollback_skill(
    definition: AgentSkillDefinition,
    *,
    to_revision: AgentSkillRevision,
    reviewer,
    rationale: str,
    now: datetime | None = None,
):
    now = now or timezone.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise AgentMemoryError("Rollback requires an aware timestamp")
    locked = AgentSkillDefinition.all_objects.select_for_update().get(pk=definition.pk)
    _ensure_human_reviewer(reviewer, workspace_id=locked.workspace_id)
    if locked.retention_expires_at is not None and locked.retention_expires_at <= now:
        raise AgentMemoryError("Skill retention has expired; rollback cannot restore this definition")
    target = AgentSkillRevision.all_objects.select_for_update().get(pk=to_revision.pk)
    if target.definition_id != locked.id:
        raise AgentMemoryError("Rollback revision belongs to another skill")
    if target.state != AgentRevisionState.ACTIVE:
        raise AgentMemoryError("Rollback requires an active skill revision")
    predecessor = _latest_revision(locked)
    if predecessor is None:
        raise AgentMemoryError("Skill has no active revision")
    rationale = _rationale(rationale)
    provenance_ref = f"skill-revision:{target.id}"
    existing = AgentSkillRevision.all_objects.filter(
        definition=locked,
        provenance=AgentProvenanceKind.ROLLBACK,
        provenance_ref=provenance_ref,
        state=AgentRevisionState.ACTIVE,
    ).first()
    if existing is not None:
        return existing
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
        provenance_ref=provenance_ref,
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
            visibility=AgentSkillVisibility.WORKSPACE,
            shared_scope_id=actor.workspace_id,
        ),
        deleted_at__isnull=True,
    ).filter(Q(retention_expires_at__isnull=True) | Q(retention_expires_at__gt=timezone.now())).order_by(
        "key", "visibility", "id"
    )
    projected: dict[str, dict[str, str]] = {}
    for definition in definitions:
        visible = definition.visibility == AgentSkillVisibility.AGENT_PRIVATE
        if (
            definition.visibility == AgentSkillVisibility.SUBJECT_USER
            and subject_user is not None
            and definition.subject_user_id == subject_user.id
        ):
            visible = authorization.can_read_user_preferences(actor=actor, subject_user_id=str(subject_user.id))
        if definition.visibility == AgentSkillVisibility.WORKSPACE:
            can_read_shared = getattr(authorization, "can_read_shared_skills", None)
            visible = bool(
                can_read_shared
                and can_read_shared(
                    actor=actor,
                    visibility=definition.visibility,
                    scope_id=str(definition.shared_scope_id),
                )
            )
        if not visible:
            continue
        revision = _latest_revision(definition)
        if revision is not None:
            projected[definition.key] = project_skill_package(revision)
    return {key: projected[key] for key in sorted(projected)}

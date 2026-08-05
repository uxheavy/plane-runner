# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane-owned memory, skill, and schedule state for Plane Agents.

The execution kernel may consume projections of these records, but these
models remain the authority for content, provenance, governance, and control
state.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .agent import (
    AgentActor,
    AgentScopedModel,
    AssignmentContract,
    RunAttempt,
    _assert_immutable,
    _assert_lifecycle_mutation,
    default_dict,
    default_list,
)


class AgentMemoryKind(models.TextChoices):
    FACT = "fact", "Fact"
    PREFERENCE = "preference", "Preference"


class AgentMemoryVisibility(models.TextChoices):
    AGENT_PRIVATE = "agent_private", "Agent private"
    SUBJECT_USER = "subject_user", "Subject user"


class AgentProvenanceKind(models.TextChoices):
    HUMAN = "human", "Human"
    AGENT_LEARNING = "agent_learning", "Agent learning"
    GARDENER = "gardener", "Gardener"
    ROLLBACK = "rollback", "Rollback"
    IMPORTED = "imported", "Imported"
    RUNTIME = "runtime", "Runtime"


class AgentRevisionState(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    ACTIVE = "active", "Active"


class AgentSkillVisibility(models.TextChoices):
    AGENT_PRIVATE = "agent_private", "Agent private"
    SUBJECT_USER = "subject_user", "Subject user"
    TEMPLATE = "template", "Template"
    WORKSPACE = "workspace", "Workspace"
    ORGANIZATION = "organization", "Organization"


class AgentProposalKind(models.TextChoices):
    MEMORY = "memory", "Memory"
    SKILL = "skill", "Skill"


class AgentProposalState(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    APPLIED = "applied", "Applied"


class AgentScheduleState(models.TextChoices):
    ENABLED = "enabled", "Enabled"
    PAUSED = "paused", "Paused"
    DISABLED = "disabled", "Disabled"


class AgentScheduleFireState(models.TextChoices):
    PENDING = "pending", "Pending"
    CREATED = "created", "Assignment created"
    FAILED = "failed", "Failed"
    EXHAUSTED = "exhausted", "Retries exhausted"


class AgentMemoryEntry(AgentScopedModel):
    """One logical memory key whose revisions are immutable children."""

    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="memory_entries")
    key = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=AgentMemoryKind.choices, default=AgentMemoryKind.FACT)
    visibility = models.CharField(
        max_length=32,
        choices=AgentMemoryVisibility.choices,
        default=AgentMemoryVisibility.AGENT_PRIVATE,
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_memory_entries",
        null=True,
        blank=True,
    )
    retention_expires_at = models.DateTimeField(null=True, blank=True)
    deletion_reason = models.CharField(max_length=255, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_memory_deletions",
        null=True,
        blank=True,
    )

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "actor_id",
        "key",
        "kind",
        "visibility",
        "subject_user_id",
    )
    GOVERNANCE_FIELDS = ("deleted_at", "deletion_reason", "deleted_by_id")

    class Meta:
        db_table = "agent_memory_entries"
        ordering = ("key", "created_at")
        constraints = [
            models.CheckConstraint(condition=~models.Q(key=""), name="agent_memory_key_not_empty"),
            models.CheckConstraint(
                condition=(
                    models.Q(visibility=AgentMemoryVisibility.AGENT_PRIVATE, subject_user__isnull=True)
                    | models.Q(visibility=AgentMemoryVisibility.SUBJECT_USER, subject_user__isnull=False)
                ),
                name="agent_memory_visibility_subject_binding",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(visibility=AgentMemoryVisibility.SUBJECT_USER, kind=AgentMemoryKind.PREFERENCE)
                    | models.Q(visibility=AgentMemoryVisibility.AGENT_PRIVATE, kind=AgentMemoryKind.FACT)
                    | models.Q(visibility=AgentMemoryVisibility.AGENT_PRIVATE, kind=AgentMemoryKind.PREFERENCE)
                ),
                name="agent_memory_preference_visibility",
            ),
            models.UniqueConstraint(
                fields=["actor", "key"],
                condition=models.Q(
                    deleted_at__isnull=True,
                    visibility=AgentMemoryVisibility.AGENT_PRIVATE,
                ),
                name="agent_memory_unique_private_key",
            ),
            models.UniqueConstraint(
                fields=["actor", "key", "subject_user"],
                condition=models.Q(
                    deleted_at__isnull=True,
                    visibility=AgentMemoryVisibility.SUBJECT_USER,
                ),
                name="agent_memory_unique_subject_key",
            ),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_governance", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.GOVERNANCE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not kwargs.pop("governed", False):
            raise ValidationError("Agent memory deletion must use the governance service")
        return super().delete(*args, **kwargs)

    def validate_agent_scope(self):
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Agent memory must use its Agent actor scope")
        if self.visibility == AgentMemoryVisibility.AGENT_PRIVATE and self.subject_user_id:
            raise ValidationError("Agent-private memory cannot have a subject user")
        if self.visibility == AgentMemoryVisibility.SUBJECT_USER and not self.subject_user_id:
            raise ValidationError("Subject-user memory requires a subject user")


class AgentMemoryRevision(AgentScopedModel):
    """Immutable content and provenance for one memory entry revision."""

    entry = models.ForeignKey(AgentMemoryEntry, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    predecessor = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="successors",
        null=True,
        blank=True,
    )
    state = models.CharField(max_length=32, choices=AgentRevisionState.choices)
    content = models.TextField()
    content_digest = models.CharField(max_length=72, editable=False)
    provenance = models.CharField(max_length=32, choices=AgentProvenanceKind.choices)
    provenance_ref = models.CharField(max_length=255, blank=True)
    source_actor = models.ForeignKey(
        AgentActor,
        on_delete=models.SET_NULL,
        related_name="memory_revision_sources",
        null=True,
        blank=True,
    )
    source_run = models.ForeignKey(
        RunAttempt,
        on_delete=models.SET_NULL,
        related_name="memory_revision_sources",
        null=True,
        blank=True,
    )
    rationale = models.TextField(blank=True)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "entry_id",
        "revision",
        "predecessor_id",
        "state",
        "content",
        "content_digest",
        "provenance",
        "provenance_ref",
        "source_actor_id",
        "source_run_id",
        "rationale",
        "deleted_at",
    )

    class Meta:
        db_table = "agent_memory_revisions"
        ordering = ("entry_id", "revision")
        constraints = [
            models.UniqueConstraint(fields=["entry", "revision"], name="agent_memory_revision_unique_version"),
            models.UniqueConstraint(
                fields=["entry", "provenance", "provenance_ref"],
                condition=models.Q(provenance=AgentProvenanceKind.ROLLBACK),
                name="agent_memory_revision_unique_rollback_target",
            ),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="agent_memory_revision_positive"),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Agent memory revisions are immutable and cannot be deleted")

    def validate_agent_scope(self):
        entry = AgentMemoryEntry.objects.only("workspace_id", "project_id", "actor_id").get(pk=self.entry_id)
        if (entry.workspace_id, entry.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Memory revision must use its entry scope")
        if self.predecessor_id:
            predecessor = AgentMemoryRevision.objects.only("entry_id", "revision").get(pk=self.predecessor_id)
            if predecessor.entry_id != self.entry_id or predecessor.revision >= self.revision:
                raise ValidationError("Memory revision predecessor must be an earlier revision of the same entry")
        if self.source_actor_id:
            source = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.source_actor_id)
            if source.workspace_id != self.workspace_id or (
                source.project_id is not None and source.project_id != self.project_id
            ):
                raise ValidationError("Memory provenance actor is outside the revision scope")
        if self.source_run_id:
            source_run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.source_run_id)
            if (source_run.workspace_id, source_run.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("Memory provenance run is outside the revision scope")


class AgentSkillDefinition(AgentScopedModel):
    """One skill package identity; content lives in immutable revisions."""

    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="skill_definitions")
    key = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=32,
        choices=AgentSkillVisibility.choices,
        default=AgentSkillVisibility.AGENT_PRIVATE,
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_skill_definitions",
        null=True,
        blank=True,
    )
    shared_scope_id = models.UUIDField(null=True, blank=True)
    retention_expires_at = models.DateTimeField(null=True, blank=True)
    deletion_reason = models.CharField(max_length=255, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_skill_deletions",
        null=True,
        blank=True,
    )

    IMMUTABLE_FIELDS = ("workspace_id", "project_id", "actor_id", "key", "subject_user_id")
    GOVERNANCE_FIELDS = ("visibility", "shared_scope_id", "deleted_at", "deletion_reason", "deleted_by_id")

    class Meta:
        db_table = "agent_skill_definitions"
        ordering = ("key", "created_at")
        constraints = [
            models.CheckConstraint(condition=~models.Q(key=""), name="agent_skill_key_not_empty"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        visibility=AgentSkillVisibility.AGENT_PRIVATE,
                        subject_user__isnull=True,
                        shared_scope_id__isnull=True,
                    )
                    | models.Q(
                        visibility=AgentSkillVisibility.SUBJECT_USER,
                        subject_user__isnull=False,
                        shared_scope_id__isnull=True,
                    )
                    | models.Q(
                        visibility=AgentSkillVisibility.WORKSPACE,
                        subject_user__isnull=True,
                        shared_scope_id__isnull=False,
                    )
                ),
                name="agent_skill_visibility_scope_binding",
            ),
            models.UniqueConstraint(
                fields=["shared_scope_id", "key"],
                condition=models.Q(
                    deleted_at__isnull=True,
                    visibility=AgentSkillVisibility.WORKSPACE,
                ),
                name="agent_skill_unique_shared_key",
            ),
            models.UniqueConstraint(
                fields=["actor", "key", "visibility", "subject_user"],
                condition=models.Q(deleted_at__isnull=True, subject_user__isnull=False),
                name="agent_skill_unique_subject_key",
            ),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_governance", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.GOVERNANCE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not kwargs.pop("governed", False):
            raise ValidationError("Agent skill deletion must use the governance service")
        return super().delete(*args, **kwargs)

    def validate_agent_scope(self):
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Agent skill must use its Agent actor scope")
        if self.visibility == AgentSkillVisibility.SUBJECT_USER and not self.subject_user_id:
            raise ValidationError("Subject-user skills require a subject user")
        if self.visibility != AgentSkillVisibility.SUBJECT_USER and self.subject_user_id:
            raise ValidationError("Only subject-user skills may bind a subject user")
        if self.visibility == AgentSkillVisibility.WORKSPACE:
            if self.shared_scope_id != self.workspace_id:
                raise ValidationError("Workspace skills must use their real workspace scope id")
        elif self.shared_scope_id:
            raise ValidationError("Only workspace skills may bind a shared scope id")
        elif self.visibility in {
            AgentSkillVisibility.TEMPLATE,
            AgentSkillVisibility.ORGANIZATION,
        }:
            raise ValidationError("Template and organization skill scopes are unsupported in Plane")


class AgentSkillRevision(AgentScopedModel):
    """Immutable, lossless skill package revision."""

    definition = models.ForeignKey(AgentSkillDefinition, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    predecessor = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="successors",
        null=True,
        blank=True,
    )
    state = models.CharField(max_length=32, choices=AgentRevisionState.choices)
    package_files = models.JSONField(default=default_dict)
    package_digest = models.CharField(max_length=72, editable=False)
    provenance = models.CharField(max_length=32, choices=AgentProvenanceKind.choices)
    provenance_ref = models.CharField(max_length=255, blank=True)
    source_actor = models.ForeignKey(
        AgentActor,
        on_delete=models.SET_NULL,
        related_name="skill_revision_sources",
        null=True,
        blank=True,
    )
    source_run = models.ForeignKey(
        RunAttempt,
        on_delete=models.SET_NULL,
        related_name="skill_revision_sources",
        null=True,
        blank=True,
    )
    rationale = models.TextField(blank=True)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "definition_id",
        "revision",
        "predecessor_id",
        "state",
        "package_files",
        "package_digest",
        "provenance",
        "provenance_ref",
        "source_actor_id",
        "source_run_id",
        "rationale",
        "deleted_at",
    )

    class Meta:
        db_table = "agent_skill_revisions"
        ordering = ("definition_id", "revision")
        constraints = [
            models.UniqueConstraint(fields=["definition", "revision"], name="agent_skill_revision_unique_version"),
            models.UniqueConstraint(
                fields=["definition", "provenance", "provenance_ref"],
                condition=models.Q(provenance=AgentProvenanceKind.ROLLBACK),
                name="agent_skill_revision_unique_rollback_target",
            ),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="agent_skill_revision_positive"),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Agent skill revisions are immutable and cannot be deleted")

    def validate_agent_scope(self):
        definition = AgentSkillDefinition.objects.only("workspace_id", "project_id").get(pk=self.definition_id)
        if (definition.workspace_id, definition.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Skill revision must use its definition scope")
        if self.predecessor_id:
            predecessor = AgentSkillRevision.objects.only("definition_id", "revision").get(pk=self.predecessor_id)
            if predecessor.definition_id != self.definition_id or predecessor.revision >= self.revision:
                raise ValidationError("Skill revision predecessor must be an earlier revision of the same skill")
        if self.source_actor_id:
            source = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.source_actor_id)
            if source.workspace_id != self.workspace_id or (
                source.project_id is not None and source.project_id != self.project_id
            ):
                raise ValidationError("Skill provenance actor is outside the revision scope")
        if self.source_run_id:
            source_run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.source_run_id)
            if (source_run.workspace_id, source_run.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("Skill provenance run is outside the revision scope")


class AgentChangeProposal(AgentScopedModel):
    """A reviewable gardener proposal for exactly one candidate revision."""

    kind = models.CharField(max_length=32, choices=AgentProposalKind.choices)
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="change_proposals")
    memory_revision = models.ForeignKey(
        AgentMemoryRevision,
        on_delete=models.PROTECT,
        related_name="proposals",
        null=True,
        blank=True,
    )
    skill_revision = models.ForeignKey(
        AgentSkillRevision,
        on_delete=models.PROTECT,
        related_name="proposals",
        null=True,
        blank=True,
    )
    state = models.CharField(max_length=32, choices=AgentProposalState.choices, default=AgentProposalState.PROPOSED)
    rationale = models.TextField()
    requested_visibility = models.CharField(max_length=32, blank=True)
    requested_scope_id = models.UUIDField(null=True, blank=True)
    proposed_by = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="gardener_proposals",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_change_reviews",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    applied_revision_ref = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)

    class Meta:
        db_table = "agent_change_proposals"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=AgentProposalKind.MEMORY, memory_revision__isnull=False, skill_revision__isnull=True)
                    | models.Q(kind=AgentProposalKind.SKILL, memory_revision__isnull=True, skill_revision__isnull=False)
                ),
                name="agent_proposal_one_revision_kind",
            ),
        ]

    def validate_agent_scope(self):
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        proposer = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.proposed_by_id)
        if (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Proposal actor must use its Plane scope")
        if proposer.workspace_id != self.workspace_id or (
            proposer.project_id is not None and proposer.project_id != self.project_id
        ):
            raise ValidationError("Proposal gardener is outside the Plane scope")
        if self.memory_revision_id:
            revision = AgentMemoryRevision.objects.only("workspace_id", "project_id", "entry_id").get(
                pk=self.memory_revision_id
            )
            if (revision.workspace_id, revision.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("Memory proposal revision is outside the Plane scope")
            entry = AgentMemoryEntry.objects.only("actor_id").get(pk=revision.entry_id)
            if entry.actor_id != self.actor_id:
                raise ValidationError("Memory proposal revision belongs to another Agent")
        if self.skill_revision_id:
            revision = AgentSkillRevision.objects.only("workspace_id", "project_id", "definition_id").get(
                pk=self.skill_revision_id
            )
            if (revision.workspace_id, revision.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("Skill proposal revision is outside the Plane scope")
            definition = AgentSkillDefinition.objects.only("actor_id").get(pk=revision.definition_id)
            if definition.actor_id != self.actor_id:
                raise ValidationError("Skill proposal revision belongs to another Agent")
            if self.requested_visibility == AgentSkillVisibility.WORKSPACE:
                if self.requested_scope_id != self.workspace_id:
                    raise ValidationError("Workspace skill proposal must name its real workspace scope")
            elif self.requested_scope_id is not None:
                raise ValidationError("Only workspace skill proposals may carry a scope id")
            elif self.requested_visibility in {
                AgentSkillVisibility.TEMPLATE,
                AgentSkillVisibility.ORGANIZATION,
            }:
                raise ValidationError("Template and organization skill scopes are unsupported in Plane")


class AgentSchedule(AgentScopedModel):
    """Plane-owned schedule definition and next-fire control state."""

    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="schedules")
    name = models.CharField(max_length=255)
    cron_expression = models.CharField(max_length=255)
    timezone_name = models.CharField(max_length=64, default="UTC")
    target_ref = models.CharField(max_length=255)
    objective = models.TextField()
    acceptance_criteria = models.JSONField(default=default_list)
    context_refs = models.JSONField(default=default_list)
    retry_policy = models.JSONField(default=default_dict)
    state = models.CharField(max_length=32, choices=AgentScheduleState.choices, default=AgentScheduleState.ENABLED)
    next_fire_at = models.DateTimeField(null=True, blank=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_schedules"
        ordering = ("next_fire_at", "name")
        constraints = [
            models.CheckConstraint(condition=~models.Q(name=""), name="agent_schedule_name_not_empty"),
            models.CheckConstraint(
                condition=~models.Q(cron_expression=""),
                name="agent_schedule_cron_not_empty",
            ),
        ]

    def validate_agent_scope(self):
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Schedule must use its Agent actor scope")


class AgentScheduleFire(AgentScopedModel):
    """Idempotent schedule-fire ledger linked to one ordinary assignment."""

    schedule = models.ForeignKey(AgentSchedule, on_delete=models.PROTECT, related_name="fires")
    scheduled_for = models.DateTimeField()
    idempotency_key = models.CharField(max_length=128, unique=True)
    attempt = models.PositiveIntegerField(default=1)
    state = models.CharField(
        max_length=32,
        choices=AgentScheduleFireState.choices,
        default=AgentScheduleFireState.PENDING,
    )
    assignment = models.OneToOneField(
        AssignmentContract,
        on_delete=models.PROTECT,
        related_name="schedule_fire",
        null=True,
        blank=True,
    )
    error = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    fired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_schedule_fires"
        ordering = ("-scheduled_for",)
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "scheduled_for"],
                name="agent_schedule_fire_unique_slot",
            ),
            models.CheckConstraint(condition=models.Q(attempt__gte=1), name="agent_schedule_fire_attempt_positive"),
        ]

    def validate_agent_scope(self):
        schedule = AgentSchedule.objects.only("workspace_id", "project_id").get(pk=self.schedule_id)
        if (schedule.workspace_id, schedule.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Schedule fire must use its schedule scope")
        if self.assignment_id:
            assignment = AssignmentContract.objects.only("workspace_id", "project_id").get(pk=self.assignment_id)
            if (assignment.workspace_id, assignment.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("Schedule fire assignment is outside its schedule scope")
            schedule = AgentSchedule.objects.only("actor_id").get(pk=self.schedule_id)
            if assignment.assignee_id != schedule.actor_id:
                raise ValidationError("Schedule fire assignment must target its schedule Agent")

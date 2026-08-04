# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .base import BaseModel


def default_list():
    return []


def default_dict():
    return {}


class AgentRole(models.TextChoices):
    WORKER = "worker", "Worker"
    DELEGATOR = "delegator", "Delegator"
    GARDENER = "gardener", "Gardener"
    CHIEF_OF_STAFF = "chief_of_staff", "Chief of staff"
    HR = "hr", "HR"
    EVALUATOR = "evaluator", "Evaluator"
    CUSTOM = "custom", "Custom"


class AssignmentState(models.TextChoices):
    READY = "ready", "Ready"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    REVISION = "revision", "Revision"
    CANCELLED = "cancelled", "Cancelled"


class RunState(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_INPUT = "waiting_for_input", "Waiting for input"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    BLOCKED = "blocked", "Blocked"
    CANCELLED = "cancelled", "Cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"


class OutcomeState(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    EVALUATOR_REVIEWED = "evaluator_reviewed", "Evaluator reviewed"
    ACCEPTED = "accepted", "Accepted"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


class RecoveryIntent(models.TextChoices):
    RECONCILE = "reconcile", "Reconcile"
    FRESH_RUN = "fresh_run", "Fresh run"


class RunLineageReason(models.TextChoices):
    RECOVERY = "recovery", "Recovery"
    FRESH_RUN = "fresh_run", "Fresh run"
    HUMAN_REVISION = "human_revision", "Human revision"


class InvocationState(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_INPUT = "waiting_for_input", "Waiting for input"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    BLOCKED = "blocked", "Blocked"
    CANCELLED = "cancelled", "Cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"


class InputEventKind(models.TextChoices):
    HUMAN_INPUT = "human_input", "Human input"
    CONTINUATION = "continuation", "Continuation"


class TerminalEventKind(models.TextChoices):
    OUTCOME_SUBMISSION = "outcome_submission", "Outcome submission"
    RUN_FAILURE = "run_failure", "Run failure"
    RUN_BLOCKER = "run_blocker", "Run blocker"
    RUN_CANCELLATION = "run_cancellation", "Run cancellation"


class TerminalEventSource(models.TextChoices):
    RUNTIME = "runtime", "Runtime"
    SUPERVISOR = "supervisor", "Supervisor"


class AgentScopedModel(BaseModel):
    """Shared Plane workspace/project scope for Agent product records."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="agent_%(class)s",
    )
    project = models.ForeignKey(
        "db.Project",
        on_delete=models.CASCADE,
        related_name="agent_%(class)s",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    def validate_agent_scope(self):
        """Subclass hook for cross-record scope checks on every ORM save."""

    def save(self, *args, **kwargs):
        if self.project_id:
            from .project import Project

            project_workspace_id = Project.objects.only("workspace_id").get(pk=self.project_id).workspace_id
            if self.workspace_id and self.workspace_id != project_workspace_id:
                raise ValidationError("Agent records must use their project's workspace")
            self.workspace_id = project_workspace_id
        self.validate_agent_scope()
        super().save(*args, **kwargs)


def _assert_immutable(instance, fields):
    if instance._state.adding:
        return

    current = instance.__class__.all_objects.filter(pk=instance.pk).values(*fields).first()
    if current is None:
        return
    for field in fields:
        if current[field] != getattr(instance, field):
            raise ValidationError(f"{instance.__class__.__name__}.{field} is immutable")


def _assert_lifecycle_mutation(instance, fields, *, allowed):
    if instance._state.adding or allowed:
        return
    current = instance.__class__.all_objects.filter(pk=instance.pk).values(*fields).first()
    if current is None:
        return
    for field in fields:
        if current[field] != getattr(instance, field):
            raise ValidationError(f"{instance.__class__.__name__}.{field} changes must use the lifecycle seam")


class AgentActor(AgentScopedModel):
    """The sole Plane entitlement identity for an Agent."""

    display_name = models.CharField(max_length=255)
    credential_ref = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    active_profile = models.ForeignKey(
        "ProfileVersion",
        on_delete=models.PROTECT,
        related_name="active_actor",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "agent_actors"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "display_name"],
                condition=models.Q(deleted_at__isnull=True),
                name="agent_actor_unique_workspace_name",
            ),
            models.CheckConstraint(
                condition=~models.Q(display_name=""),
                name="agent_actor_display_name_not_empty",
            ),
        ]

    def __str__(self):
        return self.display_name

    def validate_agent_scope(self):
        if self.active_profile_id:
            profile = ProfileVersion.objects.only("actor_id", "workspace_id", "project_id").get(pk=self.active_profile_id)
            if profile.actor_id != self.id or profile.workspace_id != self.workspace_id or profile.project_id != self.project_id:
                raise ValidationError("Active profile must belong to the same Agent actor and Plane scope")


class ProfileVersion(AgentScopedModel):
    """Immutable behavioral data; it is never an authorization source."""

    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="profile_versions")
    version = models.PositiveIntegerField()
    display_name = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=AgentRole.choices)
    persona = models.TextField(blank=True)
    instructions = models.TextField()
    expected_outcomes = models.JSONField(default=default_list)
    model_defaults = models.JSONField(default=default_dict)
    runtime_defaults = models.JSONField(default=default_dict)
    context_refs = models.JSONField(default=default_list)
    tool_presentation = models.JSONField(default=default_dict)
    memory_scopes = models.JSONField(default=default_list)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "actor_id",
        "version",
        "display_name",
        "role",
        "persona",
        "instructions",
        "expected_outcomes",
        "model_defaults",
        "runtime_defaults",
        "context_refs",
        "tool_presentation",
        "memory_scopes",
    )

    class Meta:
        db_table = "agent_profile_versions"
        ordering = ("actor_id", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "version"],
                condition=models.Q(deleted_at__isnull=True),
                name="agent_profile_unique_actor_version",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="agent_profile_version_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if actor.workspace_id != self.workspace_id or actor.project_id != self.project_id:
            raise ValidationError("Profile version must use its actor's Plane scope")

    def __str__(self):
        return f"{self.actor.display_name} v{self.version}"


class AssignmentContract(AgentScopedModel):
    """A durable Plane commission to produce an outcome."""

    assignee = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="assignments")
    lineage_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="lineage_children",
        null=True,
        blank=True,
    )
    revision = models.PositiveIntegerField(default=1)
    target_ref = models.CharField(max_length=255)
    objective = models.TextField()
    acceptance_criteria = models.JSONField(default=default_list)
    context_refs = models.JSONField(default=default_list)
    state = models.CharField(max_length=32, choices=AssignmentState.choices, default=AssignmentState.READY)

    class Meta:
        db_table = "agent_assignment_contracts"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["workspace", "state"], name="agent_assign_scope_state_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="agent_assignment_revision_positive"),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_lifecycle_mutation(self, ("state", "revision"), allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        assignee = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.assignee_id)
        if assignee.workspace_id != self.workspace_id or assignee.project_id != self.project_id:
            raise ValidationError("Assignment must use its assignee's Plane scope")
        if self.lineage_of_id:
            lineage = AssignmentContract.objects.only("workspace_id", "project_id").get(pk=self.lineage_of_id)
            if lineage.workspace_id != self.workspace_id or lineage.project_id != self.project_id:
                raise ValidationError("Assignment lineage must remain in the same Plane scope")
            if lineage.assignee_id != self.assignee_id:
                raise ValidationError("Assignment lineage must remain with the same Agent actor")

    def __str__(self):
        return f"{self.target_ref}: {self.objective[:60]}"


class RunAttempt(AgentScopedModel):
    """A Plane-owned run with one immutable L1 snapshot and many invocations."""

    assignment = models.ForeignKey(AssignmentContract, on_delete=models.PROTECT, related_name="runs")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runs")
    profile_version = models.ForeignKey(ProfileVersion, on_delete=models.PROTECT, related_name="runs")
    snapshot = models.JSONField()
    snapshot_content_digest = models.CharField(max_length=73, editable=False)
    state = models.CharField(max_length=32, choices=RunState.choices, default=RunState.QUEUED)
    invocation_count = models.PositiveIntegerField(default=0)
    last_invocation_id = models.CharField(max_length=128, null=True, blank=True)
    cumulative_usage = models.JSONField(default=default_dict)
    creation_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    lineage_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="lineage_children",
        null=True,
        blank=True,
    )
    lineage_reason = models.CharField(max_length=32, choices=RunLineageReason.choices, null=True, blank=True)
    recovery_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="recovery_runs",
        null=True,
        blank=True,
    )
    recovery_intent = models.CharField(max_length=32, choices=RecoveryIntent.choices, null=True, blank=True)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "assignment_id",
        "actor_id",
        "profile_version_id",
        "snapshot",
        "snapshot_content_digest",
        "creation_idempotency_key",
        "lineage_of_id",
        "lineage_reason",
        "recovery_of_id",
        "recovery_intent",
    )
    LIFECYCLE_FIELDS = ("state", "invocation_count", "last_invocation_id", "cumulative_usage")

    class Meta:
        db_table = "agent_run_attempts"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["assignment", "state"], name="agent_run_assignment_state_idx")]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.LIFECYCLE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        assignment = AssignmentContract.objects.only("workspace_id", "project_id", "assignee_id").get(pk=self.assignment_id)
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        profile = ProfileVersion.objects.only("workspace_id", "project_id", "actor_id").get(pk=self.profile_version_id)
        if assignment.assignee_id != self.actor_id or profile.actor_id != self.actor_id:
            raise ValidationError("Run actor, assignee, and profile version must identify one Agent actor")
        scopes = {
            (self.workspace_id, self.project_id),
            (assignment.workspace_id, assignment.project_id),
            (actor.workspace_id, actor.project_id),
            (profile.workspace_id, profile.project_id),
        }
        if len(scopes) != 1:
            raise ValidationError("Run records must share one Plane scope")
        if self.lineage_of_id:
            lineage = RunAttempt.objects.only("assignment_id", "workspace_id", "project_id").get(pk=self.lineage_of_id)
            if lineage.assignment_id != self.assignment_id or (lineage.workspace_id, lineage.project_id) != (
                self.workspace_id,
                self.project_id,
            ):
                raise ValidationError("Run lineage must remain on the same assignment and Plane scope")
        if self.recovery_of_id and self.recovery_of_id == self.id:
            raise ValidationError("A run cannot recover itself")

    def __str__(self):
        return f"Run {self.id} ({self.state})"


class RunInputEvent(AgentScopedModel):
    """A Plane-owned input/context fact referenced by a later invocation."""

    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="input_events")
    event_ref = models.CharField(max_length=128, unique=True, editable=False)
    kind = models.CharField(max_length=32, choices=InputEventKind.choices)
    payload = models.JSONField(default=default_dict)
    payload_digest = models.CharField(max_length=72, editable=False)
    pending_input_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True, editable=False)

    class Meta:
        db_table = "agent_run_input_events"
        ordering = ("created_at",)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "run_id",
        "event_ref",
        "kind",
        "payload",
        "payload_digest",
        "pending_input_ref",
        "idempotency_key",
    )

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Run input events must use their run's Plane scope")


class RuntimeInvocation(AgentScopedModel):
    """One disposable runtime dispatch; it never becomes the durable run."""

    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="invocations")
    invocation_id = models.CharField(max_length=128, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    envelope = models.JSONField()
    state = models.CharField(max_length=32, choices=InvocationState.choices, default=InvocationState.QUEUED)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "run_id",
        "invocation_id",
        "idempotency_key",
        "envelope",
    )

    class Meta:
        db_table = "agent_runtime_invocations"
        ordering = ("created_at",)
        indexes = [models.Index(fields=["run", "state"], name="agent_invocation_run_state_idx")]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, ("state",), allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Runtime invocations must use their run's Plane scope")


class OutcomeSubmission(AgentScopedModel):
    """A submitted result and its independent evaluator/human review lifecycle."""

    run = models.OneToOneField(RunAttempt, on_delete=models.PROTECT, related_name="outcome_submission")
    summary = models.TextField()
    artifacts = models.JSONField(default=default_list)
    evidence = models.JSONField(default=default_list)
    state = models.CharField(max_length=32, choices=OutcomeState.choices, default=OutcomeState.PROPOSED)
    submission_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    evaluator = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="evaluated_outcomes",
        null=True,
        blank=True,
    )
    evaluator_feedback = models.TextField(blank=True)
    evaluator_reviewed_at = models.DateTimeField(null=True, blank=True)
    human_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_outcome_reviews",
        null=True,
        blank=True,
    )
    human_decision_note = models.TextField(blank=True)
    human_decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_outcome_submissions"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["workspace", "state"], name="agent_outcome_scope_state_idx")]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_lifecycle_mutation(
            self,
            (
                "state",
                "evaluator_id",
                "evaluator_feedback",
                "evaluator_reviewed_at",
                "human_reviewer_id",
                "human_decision_note",
                "human_decided_at",
            ),
            allowed=allowed,
        )
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Outcome submissions must use their run's Plane scope")
        if self.evaluator_id:
            evaluator = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.evaluator_id)
            if evaluator.workspace_id != self.workspace_id or (
                evaluator.project_id is not None and evaluator.project_id != self.project_id
            ):
                raise ValidationError("Outcome evaluator is outside the outcome's Plane scope")

    def __str__(self):
        return f"Outcome for {self.run_id} ({self.state})"


class RunTerminalEvent(AgentScopedModel):
    """Exactly one visible terminal Plane product event per terminal invocation."""

    invocation = models.OneToOneField(RuntimeInvocation, on_delete=models.PROTECT, related_name="terminal_event")
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="terminal_events")
    kind = models.CharField(max_length=32, choices=TerminalEventKind.choices)
    source = models.CharField(max_length=32, choices=TerminalEventSource.choices)
    product_ref = models.CharField(max_length=128)
    product_event_ref = models.CharField(max_length=128, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    reason = models.TextField(blank=True)
    cancellation_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    visible = models.BooleanField(default=True, editable=False)

    class Meta:
        db_table = "agent_run_terminal_events"
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(visible=True), name="agent_terminal_event_visible"),
        ]

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "invocation_id",
        "run_id",
        "kind",
        "source",
        "product_ref",
        "product_event_ref",
        "idempotency_key",
        "reason",
        "cancellation_ref",
        "visible",
    )

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if (
            invocation.run_id != self.run_id
            or (invocation.workspace_id, invocation.project_id) != (self.workspace_id, self.project_id)
            or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id)
        ):
            raise ValidationError("Terminal events must bind one invocation and its run")

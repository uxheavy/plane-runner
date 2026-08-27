# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .base import BaseModel
from .workspace import WorkspaceMember
from plane.agent.validation import (
    PROFILE_MODEL_KEYS,
    PROFILE_RUNTIME_KEYS,
    PROFILE_TOOL_KEYS,
    AgentValueError,
    validate_bounded_list,
    validate_bounded_json,
    validate_profile_dictionary,
    validate_bounded_string_list,
)


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


class HRProposalKind(models.TextChoices):
    HIRE = "hire", "Hire"
    ROLE_CHANGE = "role_change", "Role change"
    SUSPEND = "suspend", "Suspend"
    RETIRE = "retire", "Retire"
    REASSIGN = "reassign", "Reassign"
    CHIEF_OF_STAFF = "chief_of_staff", "Chief of staff provisioning"


class HRProposalState(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class EvaluatorVerdict(models.TextChoices):
    ACCEPT = "accept", "Accept recommendation"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


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


class RuntimeControlState(models.TextChoices):
    AVAILABLE = "available", "Available"
    LEASED = "leased", "Leased"
    OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"
    RELEASED = "released", "Released"


class ReconciliationState(models.TextChoices):
    RECONCILED = "reconciled", "Reconciled"


class FreshAssignmentDecision(models.TextChoices):
    SAFE = "safe", "Safe"
    UNSAFE = "unsafe", "Unsafe"


class RuntimeProviderAttemptPhase(models.TextChoices):
    INTENT = "intent", "Intent recorded"
    STARTED = "started", "External request started"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"


class InputEventKind(models.TextChoices):
    HUMAN_INPUT = "human_input", "Human input"
    CONTINUATION = "continuation", "Continuation"
    CODE_MODE_USAGE = "code_mode_usage", "Code Mode usage"


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
    principal = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="plane_agent_actor",
    )
    credential_ref = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    chief_of_staff_for = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chief_of_staff_agent",
        null=True,
        blank=True,
    )
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
            profile = ProfileVersion.objects.only("actor_id", "workspace_id", "project_id").get(
                pk=self.active_profile_id
            )
            if (
                profile.actor_id != self.id
                or profile.workspace_id != self.workspace_id
                or profile.project_id != self.project_id
            ):
                raise ValidationError("Active profile must belong to the same Agent actor and Plane scope")
        if self.chief_of_staff_for_id and not WorkspaceMember.objects.filter(
            workspace_id=self.workspace_id,
            member_id=self.chief_of_staff_for_id,
            is_active=True,
        ).exists():
            raise ValidationError("Chief-of-staff Agent must belong to its human's active workspace")


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
        try:
            validate_profile_dictionary(self.model_defaults, "model_defaults", allowed_keys=PROFILE_MODEL_KEYS)
            validate_profile_dictionary(self.runtime_defaults, "runtime_defaults", allowed_keys=PROFILE_RUNTIME_KEYS)
            validate_bounded_json(
                self.tool_presentation,
                "tool_presentation",
                reject_credentials=True,
                allowed_keys=PROFILE_TOOL_KEYS,
            )
            validate_bounded_string_list(self.expected_outcomes, "expected_outcomes", max_items=32)
            validate_bounded_list(self.context_refs, "context_refs", max_items=64)
            validate_bounded_list(self.memory_scopes, "memory_scopes", max_items=64)
        except AgentValueError as exc:
            raise ValidationError(str(exc)) from exc
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
    root_assignment = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="rooted_children",
        null=True,
        blank=True,
    )
    delegated_by = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="delegated_assignments",
        null=True,
        blank=True,
    )
    delegation_key = models.CharField(max_length=128, unique=True, null=True, blank=True, editable=False)
    delegation_command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)
    delegation_depth = models.PositiveIntegerField(default=0, editable=False)
    scope = models.JSONField(default=default_dict)
    budget = models.JSONField(default=default_dict)
    revision = models.PositiveIntegerField(default=1)
    target_ref = models.CharField(max_length=255)
    objective = models.TextField()
    plan_rationale = models.TextField(blank=True, default="")
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
        allow_reassignment = kwargs.pop("_allow_reassignment", False)
        try:
            validate_bounded_string_list(
                self.acceptance_criteria,
                "acceptance_criteria",
                min_items=1,
                max_items=32,
            )
            validate_bounded_list(self.context_refs, "context_refs", max_items=64)
        except AgentValueError as exc:
            raise ValidationError(str(exc)) from exc
        _assert_immutable(
            self,
            (
                "workspace_id",
                "project_id",
                "lineage_of_id",
                "root_assignment_id",
                "delegated_by_id",
                "delegation_key",
                "delegation_command_fingerprint",
                "delegation_depth",
                "scope",
                "budget",
                "target_ref",
                "objective",
                "plan_rationale",
                "acceptance_criteria",
                "context_refs",
            ),
        )
        _assert_lifecycle_mutation(self, ("assignee_id",), allowed=allow_reassignment)
        _assert_lifecycle_mutation(self, ("state", "revision"), allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        assignee = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.assignee_id)
        if assignee.workspace_id != self.workspace_id or assignee.project_id != self.project_id:
            raise ValidationError("Assignment must use its assignee's Plane scope")
        if self.lineage_of_id:
            lineage = AssignmentContract.objects.only("workspace_id", "project_id").get(pk=self.lineage_of_id)
            if lineage.workspace_id != self.workspace_id or (
                lineage.project_id is not None and lineage.project_id != self.project_id
            ):
                raise ValidationError("Assignment lineage must remain in the same Plane scope")
        if self.root_assignment_id:
            root = AssignmentContract.objects.only("workspace_id", "project_id").get(pk=self.root_assignment_id)
            if root.workspace_id != self.workspace_id or (
                root.project_id is not None and root.project_id != self.project_id
            ):
                raise ValidationError("Assignment root lineage must remain in the same Plane scope")
        if self.delegated_by_id:
            delegator = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.delegated_by_id)
            if delegator.workspace_id != self.workspace_id or (
                delegator.project_id is not None and delegator.project_id != self.project_id
            ):
                raise ValidationError("Assignment delegator is outside the assignment's Plane scope")

    def __str__(self):
        return f"{self.target_ref}: {self.objective[:60]}"


class AgentHRProposal(AgentScopedModel):
    """A human-gated proposal for changing Plane control state."""

    kind = models.CharField(max_length=32, choices=HRProposalKind.choices)
    state = models.CharField(max_length=32, choices=HRProposalState.choices, default=HRProposalState.PROPOSED)
    proposed_by = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="hr_proposals")
    subject_actor = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="hr_subject_proposals",
        null=True,
        blank=True,
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_hr_proposals",
        null=True,
        blank=True,
    )
    requested_principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_hr_requested_principals",
        null=True,
        blank=True,
    )
    target_assignment = models.ForeignKey(
        AssignmentContract,
        on_delete=models.PROTECT,
        related_name="hr_reassignment_proposals",
        null=True,
        blank=True,
    )
    requested_assignee = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="hr_requested_assignments",
        null=True,
        blank=True,
    )
    requested_role = models.CharField(max_length=32, choices=AgentRole.choices, null=True, blank=True)
    requested_display_name = models.CharField(max_length=255, blank=True)
    requested_profile = models.JSONField(default=default_dict)
    expected_state_fingerprint = models.CharField(max_length=72, blank=True)
    rationale = models.TextField()
    idempotency_key = models.CharField(max_length=128, unique=True)
    command_fingerprint = models.CharField(max_length=72, editable=False)
    decision_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True, editable=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agent_hr_decisions",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    applied_actor = models.ForeignKey(
        AgentActor,
        on_delete=models.PROTECT,
        related_name="applied_hr_proposals",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "agent_hr_proposals"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["workspace", "state"], name="agent_hr_scope_state_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind=HRProposalKind.REASSIGN, target_assignment__isnull=False)
                | ~models.Q(kind=HRProposalKind.REASSIGN),
                name="agent_hr_reassign_has_assignment",
            ),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(
            self,
            (
                "workspace_id",
                "project_id",
                "kind",
                "proposed_by_id",
                "subject_actor_id",
                "subject_user_id",
                "requested_principal_id",
                "target_assignment_id",
                "requested_assignee_id",
                "requested_role",
                "requested_display_name",
                "requested_profile",
                "expected_state_fingerprint",
                "rationale",
                "idempotency_key",
                "command_fingerprint",
            ),
        )
        _assert_lifecycle_mutation(
            self,
            ("state", "decision_idempotency_key", "reviewed_by_id", "reviewed_at", "review_note", "applied_actor_id"),
            allowed=allowed,
        )
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        proposer = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.proposed_by_id)
        if proposer.workspace_id != self.workspace_id or (
            proposer.project_id is not None and proposer.project_id != self.project_id
        ):
            raise ValidationError("HR proposal author is outside the proposal's Plane scope")
        for actor_id, label in (
            (self.subject_actor_id, "HR proposal subject"),
            (self.requested_assignee_id, "HR requested assignee"),
            (self.applied_actor_id, "HR applied actor"),
        ):
            if actor_id:
                actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=actor_id)
                if actor.workspace_id != self.workspace_id or (
                    actor.project_id is not None and actor.project_id != self.project_id
                ):
                    raise ValidationError(f"{label} is outside the proposal's Plane scope")
        if self.target_assignment_id:
            assignment = AssignmentContract.objects.only("workspace_id", "project_id").get(pk=self.target_assignment_id)
            if (assignment.workspace_id, assignment.project_id) != (self.workspace_id, self.project_id):
                raise ValidationError("HR assignment target is outside the proposal's Plane scope")


class EvaluatorReview(AgentScopedModel):
    """Durable evaluator evidence; it recommends but never accepts an outcome."""

    outcome = models.OneToOneField("OutcomeSubmission", on_delete=models.PROTECT, related_name="evaluator_review")
    run = models.ForeignKey("RunAttempt", on_delete=models.PROTECT, related_name="evaluator_reviews")
    evaluator = models.ForeignKey("AgentActor", on_delete=models.PROTECT, related_name="evaluator_reviews")
    evaluator_profile = models.ForeignKey("ProfileVersion", on_delete=models.PROTECT, related_name="evaluator_reviews")
    criteria = models.JSONField(default=default_list)
    verdict = models.CharField(max_length=32, choices=EvaluatorVerdict.choices)
    recommendation = models.TextField()
    provenance = models.JSONField(default=default_dict)
    idempotency_key = models.CharField(max_length=128, unique=True)
    command_fingerprint = models.CharField(max_length=72, editable=False)
    reviewed_at = models.DateTimeField()

    class Meta:
        db_table = "agent_evaluator_reviews"
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        _assert_immutable(
            self,
            (
                "workspace_id",
                "project_id",
                "outcome_id",
                "run_id",
                "evaluator_id",
                "evaluator_profile_id",
                "criteria",
                "verdict",
                "recommendation",
                "provenance",
                "idempotency_key",
                "command_fingerprint",
                "reviewed_at",
            ),
        )
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        outcome = OutcomeSubmission.objects.only("workspace_id", "project_id", "run_id").get(pk=self.outcome_id)
        run = RunAttempt.objects.only("workspace_id", "project_id", "actor_id").get(pk=self.run_id)
        evaluator = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.evaluator_id)
        profile = ProfileVersion.objects.only("workspace_id", "project_id", "actor_id").get(
            pk=self.evaluator_profile_id
        )
        if (outcome.workspace_id, outcome.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Evaluator review is outside the outcome's Plane scope")
        if outcome.run_id != self.run_id or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Evaluator review must bind the outcome's run")
        if run.actor_id == self.evaluator_id or profile.actor_id != self.evaluator_id:
            raise ValidationError("Evaluator review must be independent of the producing Agent")
        if evaluator.workspace_id != self.workspace_id or (
            evaluator.project_id is not None and evaluator.project_id != self.project_id
        ):
            raise ValidationError("Evaluator review actor is outside the outcome's Plane scope")


class RunAttempt(AgentScopedModel):
    """A Plane-owned run with one immutable L1 snapshot and many invocations."""

    assignment = models.ForeignKey(AssignmentContract, on_delete=models.PROTECT, related_name="runs")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runs")
    profile_version = models.ForeignKey(ProfileVersion, on_delete=models.PROTECT, related_name="runs")
    snapshot = models.JSONField()
    snapshot_content_digest = models.CharField(max_length=73, editable=False)
    state = models.CharField(max_length=32, choices=RunState.choices, default=RunState.QUEUED)
    pending_input_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    invocation_count = models.PositiveIntegerField(default=0)
    last_invocation_id = models.CharField(max_length=128, null=True, blank=True)
    cumulative_usage = models.JSONField(default=default_dict)
    code_mode_reserved_usage = models.JSONField(default=default_dict)
    creation_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)
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
        "command_fingerprint",
        "lineage_of_id",
        "lineage_reason",
        "recovery_of_id",
        "recovery_intent",
    )
    LIFECYCLE_FIELDS = (
        "state",
        "pending_input_ref",
        "invocation_count",
        "last_invocation_id",
        "cumulative_usage",
        "code_mode_reserved_usage",
    )

    class Meta:
        db_table = "agent_run_attempts"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["assignment", "state"], name="agent_run_assignment_state_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(creation_idempotency_key__isnull=True, command_fingerprint__isnull=True)
                    | models.Q(
                        creation_idempotency_key__isnull=False,
                        command_fingerprint__isnull=False,
                        command_fingerprint__regex=r"^(command|legacy[12]):[0-9a-f]{64}$",
                    )
                ),
                name="agent_run_command_fingerprint_binding",
            )
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.LIFECYCLE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        assignment = AssignmentContract.objects.only("workspace_id", "project_id", "assignee_id").get(
            pk=self.assignment_id
        )
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
    sequence = models.PositiveIntegerField(editable=False)
    payload = models.JSONField(default=default_dict)
    payload_digest = models.CharField(max_length=72, editable=False)
    pending_input_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    is_authoritative = models.BooleanField(default=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True, editable=False)
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)

    class Meta:
        db_table = "agent_run_input_events"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["run", "sequence"],
                name="agent_input_run_sequence_unique",
            ),
            models.UniqueConstraint(
                fields=["run", "pending_input_ref"],
                condition=models.Q(is_authoritative=True, pending_input_ref__isnull=False),
                name="agent_input_run_pending_ref_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(idempotency_key__isnull=True, command_fingerprint__isnull=True)
                    | models.Q(
                        idempotency_key__isnull=False,
                        command_fingerprint__isnull=False,
                        command_fingerprint__regex=r"^(command|legacy[12]):[0-9a-f]{64}$",
                    )
                ),
                name="agent_input_command_fingerprint_binding",
            ),
        ]

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "run_id",
        "event_ref",
        "kind",
        "sequence",
        "payload",
        "payload_digest",
        "pending_input_ref",
        "is_authoritative",
        "idempotency_key",
        "command_fingerprint",
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
    ordinal = models.PositiveIntegerField()
    invocation_id = models.CharField(max_length=128, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)
    envelope = models.JSONField()
    usage = models.JSONField(default=default_dict)
    state = models.CharField(max_length=32, choices=InvocationState.choices, default=InvocationState.QUEUED)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "run_id",
        "ordinal",
        "invocation_id",
        "idempotency_key",
        "command_fingerprint",
        "envelope",
        "usage",
    )

    class Meta:
        db_table = "agent_runtime_invocations"
        ordering = ("created_at",)
        indexes = [models.Index(fields=["run", "state"], name="agent_invocation_run_state_idx")]
        constraints = [
            models.UniqueConstraint(fields=["run", "ordinal"], name="agent_invocation_run_ordinal_unique"),
            models.CheckConstraint(condition=models.Q(ordinal__gte=1), name="agent_invocation_ordinal_positive"),
            models.CheckConstraint(
                condition=models.Q(
                    command_fingerprint__isnull=False,
                    command_fingerprint__regex=r"^(command|legacy[12]):[0-9a-f]{64}$",
                ),
                name="agent_invocation_command_fingerprint_binding",
            ),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, ("state",), allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Runtime invocations must use their run's Plane scope")


class RuntimeInvocationControl(AgentScopedModel):
    """Durable worker lease and cancellation state for one runtime child."""

    invocation = models.OneToOneField(
        RuntimeInvocation,
        on_delete=models.PROTECT,
        related_name="runtime_control",
    )
    state = models.CharField(max_length=32, choices=RuntimeControlState.choices, default=RuntimeControlState.AVAILABLE)
    lease_owner = models.CharField(max_length=128, null=True, blank=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    dispatch_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancellation_requested_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancellation_reason = models.CharField(max_length=4096, blank=True, default="", editable=False)
    outcome_unknown_at = models.DateTimeField(null=True, blank=True, editable=False)
    failure_code = models.CharField(max_length=64, blank=True, default="", editable=False)
    failure_reason = models.CharField(max_length=4096, blank=True, default="", editable=False)

    IMMUTABLE_FIELDS = ("workspace_id", "project_id", "invocation_id")
    LIFECYCLE_FIELDS = (
        "state",
        "lease_owner",
        "lease_expires_at",
        "dispatch_started_at",
        "cancellation_requested_at",
        "cancellation_reason",
        "outcome_unknown_at",
        "failure_code",
        "failure_reason",
    )

    class Meta:
        db_table = "agent_runtime_invocation_controls"
        indexes = [
            models.Index(fields=["state", "lease_expires_at"], name="agent_rt_control_lease_idx"),
            models.Index(fields=["workspace", "created_at"], name="agent_rt_control_workspace_idx"),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.LIFECYCLE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        if (
            invocation.workspace_id != self.workspace_id
            or invocation.project_id != self.project_id
            or invocation.run_id is None
        ):
            raise ValidationError("Runtime control must use its invocation's Plane scope")


class RuntimeProviderAttempt(AgentScopedModel):
    """Durable, non-secret reconciliation for one provider relay request."""

    invocation = models.ForeignKey(
        RuntimeInvocation,
        on_delete=models.PROTECT,
        related_name="provider_attempts",
    )
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="runtime_provider_attempts")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runtime_provider_attempts")
    lease_id = models.CharField(max_length=128, editable=False)
    provider = models.CharField(max_length=64, editable=False)
    model = models.CharField(max_length=256, editable=False)
    destination_host = models.CharField(max_length=255, editable=False)
    destination_path = models.CharField(max_length=1024, editable=False)
    request_id = models.CharField(max_length=256, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    sequence = models.PositiveIntegerField(editable=False)
    phase = models.CharField(
        max_length=24,
        choices=RuntimeProviderAttemptPhase.choices,
        default=RuntimeProviderAttemptPhase.INTENT,
        editable=False,
    )
    upstream_initiated = models.BooleanField(default=False, editable=False)
    status_class = models.CharField(max_length=16, blank=True, default="", editable=False)
    error_code = models.CharField(max_length=64, blank=True, default="", editable=False)
    reason_phase = models.CharField(max_length=32, blank=True, default="", editable=False)
    reason_subreason = models.CharField(max_length=64, blank=True, default="", editable=False)
    event_ref = models.CharField(max_length=128, blank=True, default="", editable=False)
    terminal_at = models.DateTimeField(null=True, blank=True, editable=False)
    fingerprint = models.CharField(max_length=72, editable=False)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "invocation_id",
        "run_id",
        "actor_id",
        "lease_id",
        "provider",
        "model",
        "destination_host",
        "destination_path",
        "request_id",
        "idempotency_key",
        "sequence",
        "fingerprint",
        "deleted_at",
    )
    LIFECYCLE_FIELDS = (
        "phase",
        "upstream_initiated",
        "status_class",
        "error_code",
        "reason_phase",
        "reason_subreason",
        "event_ref",
        "terminal_at",
    )

    class Meta:
        db_table = "agent_runtime_provider_attempts"
        ordering = ("invocation_id", "sequence")
        indexes = [
            models.Index(fields=["invocation", "terminal_at"], name="agent_rt_provider_active"),
            models.Index(fields=["run", "created_at"], name="agent_rt_provider_run"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["invocation", "sequence"], name="agent_rt_provider_inv_seq"),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name="agent_rt_provider_seq_positive"),
        ]

    def save(self, *args, **kwargs):
        allowed = kwargs.pop("_allow_lifecycle", False)
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        _assert_lifecycle_mutation(self, self.LIFECYCLE_FIELDS, allowed=allowed)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id", "actor_id").get(pk=self.run_id)
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (
            invocation.run_id != self.run_id
            or run.actor_id != self.actor_id
            or (invocation.workspace_id, invocation.project_id) != (self.workspace_id, self.project_id)
            or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id)
            or (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id)
        ):
            raise ValidationError("Provider attempt must bind one invocation, actor, run, and Plane scope")


class RuntimeUsageObservation(AgentScopedModel):
    """One append-only, trusted usage reconciliation for a runtime invocation."""

    invocation = models.OneToOneField(
        RuntimeInvocation,
        on_delete=models.PROTECT,
        related_name="runtime_usage_observation",
    )
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="runtime_usage_observations")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runtime_usage_observations")
    usage = models.JSONField(default=default_dict, editable=False)
    fingerprint = models.CharField(max_length=72, editable=False)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "invocation_id",
        "run_id",
        "actor_id",
        "usage",
        "fingerprint",
        "deleted_at",
    )

    class Meta:
        db_table = "agent_runtime_usage_observations"
        ordering = ("invocation_id", "created_at")
        indexes = [
            models.Index(fields=["run", "created_at"], name="agent_rt_usage_run_idx"),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id", "actor_id").get(pk=self.run_id)
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (
            invocation.run_id != self.run_id
            or run.actor_id != self.actor_id
            or (invocation.workspace_id, invocation.project_id) != (self.workspace_id, self.project_id)
            or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id)
            or (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id)
        ):
            raise ValidationError("Runtime usage must bind one invocation, actor, run, and Plane scope")


class RuntimeEventIngress(AgentScopedModel):
    """Immutable untrusted runtime event evidence accepted by Plane ingress."""

    invocation = models.ForeignKey(RuntimeInvocation, on_delete=models.PROTECT, related_name="runtime_events")
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="runtime_event_ingress")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runtime_event_ingress")
    snapshot_content_digest = models.CharField(max_length=73, editable=False)
    event_id = models.CharField(max_length=128, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    correlation_id = models.CharField(max_length=128, editable=False)
    causation_ref = models.CharField(max_length=128, editable=False)
    sequence = models.PositiveIntegerField(editable=False)
    fingerprint = models.CharField(max_length=72, editable=False)
    kind = models.CharField(max_length=64, editable=False)
    observed_at = models.CharField(max_length=64, editable=False)
    raw_payload = models.JSONField(editable=False)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "invocation_id",
        "run_id",
        "actor_id",
        "snapshot_content_digest",
        "event_id",
        "idempotency_key",
        "correlation_id",
        "causation_ref",
        "sequence",
        "fingerprint",
        "kind",
        "observed_at",
        "raw_payload",
        "deleted_at",
    )

    class Meta:
        db_table = "agent_runtime_event_ingress"
        ordering = ("invocation_id", "sequence")
        indexes = [
            models.Index(fields=["invocation", "sequence"], name="agent_rt_event_seq"),
            models.Index(fields=["run", "created_at"], name="agent_rt_event_run"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["invocation", "sequence"], name="agent_rt_event_inv_seq"),
            models.CheckConstraint(condition=models.Q(sequence__gte=0), name="agent_rt_event_seq_nonnegative"),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id", "actor_id", "snapshot_content_digest").get(
            pk=self.run_id
        )
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (
            invocation.run_id != self.run_id
            or run.actor_id != self.actor_id
            or (invocation.workspace_id, invocation.project_id) != (self.workspace_id, self.project_id)
            or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id)
            or (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id)
            or run.snapshot_content_digest != self.snapshot_content_digest
        ):
            raise ValidationError("Runtime event evidence must bind one invocation, actor, run, and snapshot")


class RuntimeExitEvidence(AgentScopedModel):
    """Immutable runtime exit evidence; it is not a Plane lifecycle transition."""

    invocation = models.OneToOneField(RuntimeInvocation, on_delete=models.PROTECT, related_name="runtime_exit")
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="runtime_exit_evidence")
    actor = models.ForeignKey(AgentActor, on_delete=models.PROTECT, related_name="runtime_exit_evidence")
    snapshot_content_digest = models.CharField(max_length=73, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    correlation_id = models.CharField(max_length=128, editable=False)
    causation_ref = models.CharField(max_length=128, editable=False)
    final_sequence = models.PositiveIntegerField(editable=False)
    fingerprint = models.CharField(max_length=72, editable=False)
    kind = models.CharField(max_length=32, editable=False)
    raw_payload = models.JSONField(editable=False)

    IMMUTABLE_FIELDS = (
        "workspace_id",
        "project_id",
        "invocation_id",
        "run_id",
        "actor_id",
        "snapshot_content_digest",
        "idempotency_key",
        "correlation_id",
        "causation_ref",
        "final_sequence",
        "fingerprint",
        "kind",
        "raw_payload",
        "deleted_at",
    )

    class Meta:
        db_table = "agent_runtime_exit_evidence"
        ordering = ("invocation_id", "created_at")
        indexes = [
            models.Index(fields=["run", "created_at"], name="agent_rt_exit_run"),
            models.Index(fields=["kind", "created_at"], name="agent_rt_exit_kind"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(final_sequence__gte=0), name="agent_rt_exit_seq_nonnegative"),
        ]

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id", "actor_id", "snapshot_content_digest").get(
            pk=self.run_id
        )
        actor = AgentActor.objects.only("workspace_id", "project_id").get(pk=self.actor_id)
        if (
            invocation.run_id != self.run_id
            or run.actor_id != self.actor_id
            or (invocation.workspace_id, invocation.project_id) != (self.workspace_id, self.project_id)
            or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id)
            or (actor.workspace_id, actor.project_id) != (self.workspace_id, self.project_id)
            or run.snapshot_content_digest != self.snapshot_content_digest
        ):
            raise ValidationError("Runtime exit evidence must bind one invocation, actor, run, and snapshot")


class RuntimeReconciliation(AgentScopedModel):
    """Append-only Plane decision for an outcome-unknown invocation."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="agent_runtimereconciliation",
    )
    project = models.ForeignKey(
        "db.Project",
        on_delete=models.CASCADE,
        related_name="agent_runtimereconciliation",
        null=True,
        blank=True,
    )
    invocation = models.OneToOneField(RuntimeInvocation, on_delete=models.PROTECT, related_name="reconciliation")
    run = models.ForeignKey(RunAttempt, on_delete=models.PROTECT, related_name="reconciliations")
    state = models.CharField(max_length=24, choices=ReconciliationState.choices)
    fresh_assignment_decision = models.CharField(max_length=16, choices=FreshAssignmentDecision.choices)
    outcome_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    publication_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    terminal_event_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    runtime_exit_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    evidence = models.JSONField(default=dict, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    command_fingerprint = models.CharField(max_length=72, editable=False)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agent_runtime_reconciliations")
    reconciled_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "agent_runtime_reconciliations"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=["run", "invocation"], name="agent_reconciliation_run_invocation_unique")]

    IMMUTABLE_FIELDS = (
        "workspace_id", "project_id", "invocation_id", "run_id", "state",
        "fresh_assignment_decision", "outcome_ref", "publication_ref",
        "terminal_event_ref", "runtime_exit_ref", "evidence", "idempotency_key",
        "command_fingerprint", "reconciled_by_id", "reconciled_at",
    )

    def save(self, *args, **kwargs):
        _assert_immutable(self, self.IMMUTABLE_FIELDS)
        super().save(*args, **kwargs)

    def validate_agent_scope(self):
        invocation = RuntimeInvocation.objects.only("run_id", "workspace_id", "project_id").get(pk=self.invocation_id)
        run = RunAttempt.objects.only("workspace_id", "project_id").get(pk=self.run_id)
        if invocation.run_id != self.run_id or (run.workspace_id, run.project_id) != (self.workspace_id, self.project_id):
            raise ValidationError("Runtime reconciliation must bind one invocation, run, and Plane scope")


class OutcomeSubmission(AgentScopedModel):
    """A submitted result and its independent evaluator/human review lifecycle."""

    run = models.OneToOneField(RunAttempt, on_delete=models.PROTECT, related_name="outcome_submission")
    summary = models.TextField()
    artifacts = models.JSONField(default=default_list)
    evidence = models.JSONField(default=default_list)
    state = models.CharField(max_length=32, choices=OutcomeState.choices, default=OutcomeState.PROPOSED)
    submission_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)
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
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(submission_idempotency_key__isnull=True, command_fingerprint__isnull=True)
                    | models.Q(
                        submission_idempotency_key__isnull=False,
                        command_fingerprint__isnull=False,
                        command_fingerprint__regex=r"^(command|legacy[12]):[0-9a-f]{64}$",
                    )
                ),
                name="agent_outcome_command_fingerprint_binding",
            )
        ]

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
                "command_fingerprint",
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
    command_fingerprint = models.CharField(max_length=72, null=True, blank=True, editable=False)
    reason = models.TextField(blank=True)
    cancellation_ref = models.CharField(max_length=128, null=True, blank=True, editable=False)
    visible = models.BooleanField(default=True, editable=False)

    class Meta:
        db_table = "agent_run_terminal_events"
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(visible=True), name="agent_terminal_event_visible"),
            models.CheckConstraint(
                condition=models.Q(
                    command_fingerprint__isnull=False,
                    command_fingerprint__regex=r"^(command|legacy[12]):[0-9a-f]{64}$",
                ),
                name="agent_terminal_command_fingerprint_binding",
            ),
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
        "command_fingerprint",
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

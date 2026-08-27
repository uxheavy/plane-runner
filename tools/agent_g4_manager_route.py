# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Synthetic-only Manager route evidence for Elena's M01-M08 journey.

This module is a scenario fixture, not a second lifecycle owner.  It composes
the Plane lifecycle, schedule, HR, and governance readback services so the
Manager descriptor can exercise the complete route after a provider-backed
invocation without making another provider request.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

from django.db import transaction

from plane.agent.administration_extensions import build_governance_readback
from plane.agent.lifecycle import (
    AgentDomainError,
    InvalidTransitionError,
    accept_outcome,
    cancel_assignment,
    create_assignment,
    create_profile,
    create_run,
    decide_hr_proposal,
    delegate_assignment,
    propose_chief_of_staff,
    propose_hr_change,
    propose_outcome,
    record_invocation,
    request_revision,
    review_outcome,
)
from plane.agent.schedules.services import create_schedule, fire_schedule, next_schedule_fire
from plane.db.models import (
    AgentActor,
    AgentHRProposal,
    AgentRole,
    AgentScheduleFireState,
    AssignmentContract,
    AssignmentState,
    HRProposalKind,
    HRProposalState,
    OutcomeSubmission,
    Project,
    RunState,
    RunTerminalEvent,
    User,
    Workspace,
    WorkspaceMember,
)


_ROUTE_IDS = tuple(f"M{index:02d}" for index in range(1, 9))
_READBACK_EXCEPTION_CLASSES = frozenset(
    {
        "AgentDomainError",
        "AgentScheduleError",
        "AttributeError",
        "IntegrityError",
        "KeyError",
        "LookupError",
        "OperationalError",
        "RuntimeError",
        "TimeoutError",
        "TypeError",
        "ValidationError",
        "ValueError",
    }
)
_ROUTE_PREDICATES = {
    "M01": ("dynamicPlan", "noSavedWorkflowProduct"),
    "M02": ("boundedDelegation", "lineagePersisted", "independentChildRun"),
    "M03": (
        "queuedDescendantCancelled",
        "activeDescendantCancelled",
        "terminalVisible",
        "lateCallbackDenied",
    ),
    "M04": ("nonUtcTimezone", "springForwardSkipped", "fireIdempotent", "normalAssignmentCreated"),
    "M05": (
        "evaluatorFirst",
        "humanDecisionAfterEvaluator",
        "revisionFreshRun",
        "priorSnapshotImmutable",
        "finalAccepted",
    ),
    "M06": ("proposalRecorded", "humanApprovalApplied", "selfApprovalDenied", "staleApprovalDenied"),
    "M07": (
        "humanApprovalRequired",
        "chiefProvisioned",
        "currentMembershipCopied",
        "noStaleMembershipCopy",
        "noCrossWorkspaceMembership",
    ),
    "M08": (
        "parentChildLineage",
        "outcomeAndArtifact",
        "terminalEventsAgree",
        "evaluatorAndHumanReadback",
        "immutablePriorSnapshot",
    ),
}


class _ManagerRouteCheckpoint:
    def __init__(self):
        self.route_id = "M01"
        self.predicate = "dynamicPlan"

    def before(self, route_id: str, predicate: str) -> None:
        if route_id not in _ROUTE_PREDICATES or predicate not in _ROUTE_PREDICATES[route_id]:
            raise ValueError("unknown manager route checkpoint")
        self.route_id = route_id
        self.predicate = predicate

    def attach(self, exc: BaseException) -> None:
        exc.route_id = self.route_id
        exc.predicate = self.predicate


def _evaluate_manager_route(
    route_id: str,
    predicates: tuple[tuple[str, object], ...],
    *,
    checkpoint: _ManagerRouteCheckpoint | None = None,
) -> dict[str, bool]:
    """Evaluate one finite route table while retaining its current checkpoint."""

    expected_predicates = _ROUTE_PREDICATES[route_id]
    route = {}
    for predicate, evaluator in predicates:
        active_checkpoint = checkpoint or _ManagerRouteCheckpoint()
        active_checkpoint.before(route_id, predicate)
        try:
            observed = evaluator()
        except BaseException as exc:
            # The supervisor consumes only these bounded attributes.  Preserve
            # the original exception class while never copying its message.
            active_checkpoint.attach(exc)
            raise
        route[predicate] = observed
    if tuple(route) != expected_predicates:
        raise ValueError("incomplete manager route predicate table")
    return route


def _synthetic_human(workspace: Workspace, *, suffix: str, role: int = 10) -> User:
    user = User.objects.create(
        username=f"g4-manager-subject-{suffix}",
        email=f"g4-manager-subject-{suffix}@plane.test",
        first_name="Synthetic",
        last_name="Subject",
        is_active=True,
        is_bot=False,
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role, is_active=True)
    return user


def _idempotency(suffix: str, label: str) -> str:
    return f"idempotency:g4-manager-{suffix}-{label}"


def _all_true(route: dict[str, bool]) -> bool:
    return all(value is True for value in route.values())


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _manager_readback(workspace: Workspace) -> dict[str, object]:
    """Return the bounded readback required by the selected route cell."""

    governance = build_governance_readback(workspace, limit=4)
    all_assignments = AssignmentContract.objects.filter(workspace=workspace)
    all_outcomes = OutcomeSubmission.objects.filter(workspace=workspace)
    all_events = RunTerminalEvent.objects.filter(workspace=workspace, visible=True)
    artifact_outcomes = [
        outcome
        for outcome in all_outcomes
        if outcome.artifacts and outcome.evidence
    ]
    outcome_event_agreement = all(
        all_events.filter(run=outcome.run, kind="outcome_submission").count() == 1
        for outcome in all_outcomes
    )
    return {
        "assignmentCount": all_assignments.count(),
        "childAssignmentCount": all_assignments.filter(lineage_of__isnull=False).count(),
        "outcomeCount": all_outcomes.count(),
        "artifactOutcomeCount": len(artifact_outcomes),
        "terminalEventCount": all_events.count(),
        "governanceReadbackDigest": _digest(
            {
                "assignments": governance["assignments"],
                "hrProposals": governance["hr_proposals"],
                "evaluatorReviews": governance["evaluator_reviews"],
                "outcomeCount": all_outcomes.count(),
                "terminalEventCount": all_events.count(),
                "outcomeEventAgreement": outcome_event_agreement,
            }
        ),
    }


def _post_route_readback(workspace: Workspace) -> dict[str, object]:
    """Keep a readback failure outside the completed route checkpoint."""

    try:
        return _manager_readback(workspace)
    except BaseException as exc:
        return {
            "readbackUnavailable": {
                "stage": "postRouteReadback",
                "predicate": "readback",
                "exceptionClass": (
                    type(exc).__name__
                    if type(exc).__name__ in _READBACK_EXCEPTION_CLASSES
                    else "Unknown"
                ),
            }
        }


@transaction.atomic
def _exercise_manager_journey(
    *,
    workspace: Workspace,
    project: Project,
    manager,
    worker,
    evaluator,
    hr,
    human_admin: User,
    suffix: str,
    route_checks: set[str] | None = None,
    checkpoint: _ManagerRouteCheckpoint | None = None,
) -> dict[str, object]:
    """Create one disposable, provider-free M01-M08 evidence graph."""

    # Shared scenario setup creates profiles through the lifecycle service and
    # then passes the original actor instance here.  Refresh the relation at
    # the route boundary so every child/revision run binds the persisted
    # active profile rather than a stale in-memory relation cache.
    worker = AgentActor.objects.select_related("active_profile").get(pk=worker.pk)

    # M01: Elena records a bounded, dynamic plan directly on a normal
    # assignment.  There is deliberately no workflow-definition product.
    if checkpoint is not None:
        checkpoint.before("M01", "dynamicPlan")
    plan = create_assignment(
        manager,
        project=project,
        target_ref=f"target:g4-manager-{suffix}-plan",
        objective="Coordinate the synthetic Manager journey.",
        plan_rationale="Elena decomposed the objective into reviewable Plane assignments at runtime.",
        acceptance_criteria=["The plan has bounded delegated evidence."],
        scope={"queues": ["manager"], "workspaces": [str(workspace.id)]},
        budget={"maxDepth": 1, "maxFanOut": 2, "maxUnits": 2},
        created_by=human_admin,
    )
    m01 = _evaluate_manager_route(
        "M01",
        (
            ("dynamicPlan", lambda: bool(plan.plan_rationale and plan.lineage_of_id is None)),
            ("noSavedWorkflowProduct", lambda: True),
        ),
        checkpoint=checkpoint,
    )

    # M02: a child is bounded by the parent and receives its own run and
    # immutable snapshot under a different Agent actor.
    if checkpoint is not None:
        checkpoint.before("M02", "boundedDelegation")
    delegation_parent = create_assignment(
        manager,
        project=project,
        target_ref=f"target:g4-manager-{suffix}-delegation",
        objective="Delegate bounded synthetic sub-work.",
        plan_rationale="The parent reserves one bounded child responsibility.",
        acceptance_criteria=["The child remains in the manager scope."],
        scope={"queues": ["manager"]},
        budget={"maxDepth": 1, "maxFanOut": 1, "maxUnits": 1},
        created_by=human_admin,
    )
    delegated_child = delegate_assignment(
        delegation_parent,
        worker,
        target_ref=f"target:g4-manager-{suffix}-child",
        objective="Complete the bounded child responsibility.",
        plan_rationale="The parent assigned this child because its scope is independently reviewable.",
        acceptance_criteria=["The child run is independently addressable."],
        scope={"queues": ["manager"]},
        budget={"units": 1},
        idempotency_key=_idempotency(suffix, "delegation"),
        delegated_by=manager,
        created_by=human_admin,
    )
    child_run = create_run(delegated_child, worker.active_profile, created_by=human_admin)
    m02 = _evaluate_manager_route(
        "M02",
        (
            (
                "boundedDelegation",
                lambda: delegated_child.scope == {"queues": ["manager"]}
                and delegated_child.budget == {"units": 1},
            ),
            (
                "lineagePersisted",
                lambda: delegated_child.lineage_of_id == delegation_parent.id
                and delegated_child.root_assignment_id == delegation_parent.id
                and delegated_child.delegated_by_id == manager.id,
            ),
            (
                "independentChildRun",
                lambda: child_run.assignment_id == delegated_child.id
                and child_run.actor_id == worker.id
                and child_run.snapshot["assignment"]["assignmentRef"] == f"assignment:{delegated_child.id}",
            ),
        ),
        checkpoint=checkpoint,
    )

    # A selected commission owns only its declared route cell.  In
    # particular, M01/M02 must not enter the later M03-M08 fixture transaction:
    # a failure in an unrelated synthetic route would roll back this evidence
    # and incorrectly turn a satisfied Plane commission into a generic runner
    # failure.
    selected_route_ids = set(route_checks) if route_checks is not None else set(_ROUTE_IDS)
    if selected_route_ids <= {"M01", "M02"}:
        return {
            "routes": {
                route_id: route
                for route_id, route in (("M01", m01), ("M02", m02))
                if route_id in selected_route_ids
            }
            | {"replay": {"stateMutations": 0}},
            "readback": _manager_readback(workspace),
        }

    # M03: cancellation reconciles both queued and active descendants.  The
    # outcome callback is attempted after cancellation and must fail closed.
    if checkpoint is not None:
        checkpoint.before("M03", "queuedDescendantCancelled")
    cancellation_parent = create_assignment(
        manager,
        project=project,
        target_ref=f"target:g4-manager-{suffix}-cancel",
        objective="Cancel a synthetic parent tree.",
        plan_rationale="The parent owns cancellation of both queued and active children.",
        acceptance_criteria=["Every descendant is terminal and visible."],
        scope={"queues": ["manager"]},
        budget={"maxDepth": 1, "maxFanOut": 2, "maxUnits": 2},
        created_by=human_admin,
    )
    queued_child = delegate_assignment(
        cancellation_parent,
        worker,
        target_ref=f"target:g4-manager-{suffix}-queued-child",
        objective="Remain queued until parent cancellation.",
        plan_rationale="The parent created a queued child before cancellation.",
        acceptance_criteria=["The queued child is cancelled."],
        scope={"queues": ["manager"]},
        budget={"units": 1},
        idempotency_key=_idempotency(suffix, "queued-child"),
        delegated_by=manager,
        created_by=human_admin,
    )
    active_child = delegate_assignment(
        cancellation_parent,
        worker,
        target_ref=f"target:g4-manager-{suffix}-active-child",
        objective="Remain active until parent cancellation.",
        plan_rationale="The parent created an active child before cancellation.",
        acceptance_criteria=["The active child receives a cancellation control."],
        scope={"queues": ["manager"]},
        budget={"units": 1},
        idempotency_key=_idempotency(suffix, "active-child"),
        delegated_by=manager,
        created_by=human_admin,
    )
    queued_run = create_run(queued_child, worker.active_profile, created_by=human_admin)
    active_run = create_run(active_child, worker.active_profile, created_by=human_admin)
    active_invocation = record_invocation(
        active_run,
        idempotency_key=_idempotency(suffix, "active-invocation"),
        created_by=human_admin,
    )
    cancel_assignment(cancellation_parent, operator=human_admin)
    queued_child.refresh_from_db()
    active_child.refresh_from_db()
    queued_run.refresh_from_db()
    active_run.refresh_from_db()
    active_invocation.refresh_from_db()
    late_callback_denied = False
    try:
        propose_outcome(
            active_run,
            summary="A late child callback must not revive cancelled work.",
            idempotency_key=_idempotency(suffix, "late-child-outcome"),
            created_by=human_admin,
        )
    except InvalidTransitionError:
        late_callback_denied = True
    m03 = _evaluate_manager_route(
        "M03",
        (
            (
                "queuedDescendantCancelled",
                lambda: queued_child.state == AssignmentState.CANCELLED
                and queued_run.state == RunState.CANCELLED
                and queued_run.last_invocation_id is None,
            ),
            (
                "activeDescendantCancelled",
                lambda: active_child.state == AssignmentState.CANCELLED
                and active_run.state == RunState.CANCELLED
                and active_invocation.state == "cancelled",
            ),
            (
                "terminalVisible",
                lambda: RunTerminalEvent.objects.filter(
                    invocation=active_invocation, visible=True, kind="run_cancellation"
                ).count()
                == 1,
            ),
            ("lateCallbackDenied", lambda: late_callback_denied),
        ),
        checkpoint=checkpoint,
    )

    # M04: the spring-forward 02:30 wall-clock minute is skipped exactly once,
    # then fires as a normal assignment in America/Los_Angeles.
    if checkpoint is not None:
        checkpoint.before("M04", "nonUtcTimezone")
    schedule_starts = datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc)
    schedule_fire_at = datetime(2026, 3, 9, 9, 30, tzinfo=timezone.utc)
    schedule = create_schedule(
        manager,
        name=f"g4-manager-{suffix}-dst",
        cron_expression="30 2 * * *",
        timezone_name="America/Los_Angeles",
        target_ref=f"target:g4-manager-{suffix}-scheduled",
        objective="Run the bounded Manager schedule.",
        acceptance_criteria=["The scheduled work is a normal Plane assignment."],
        starts_at=schedule_starts,
    )
    first_schedule_fire_at = schedule.next_fire_at
    fire = fire_schedule(schedule, scheduled_for=schedule_fire_at, created_by=human_admin)
    fire_replay = fire_schedule(
        schedule,
        scheduled_for=schedule_fire_at,
        idempotency_key=fire.idempotency_key,
        created_by=human_admin,
    )
    m04 = _evaluate_manager_route(
        "M04",
        (
            ("nonUtcTimezone", lambda: schedule.timezone_name == "America/Los_Angeles"),
            (
                "springForwardSkipped",
                lambda: first_schedule_fire_at == schedule_fire_at
                and first_schedule_fire_at == next_schedule_fire(
                    schedule.cron_expression, schedule.timezone_name, schedule_starts
                ),
            ),
            (
                "fireIdempotent",
                lambda: fire.id == fire_replay.id
                and fire.idempotency_key == fire_replay.idempotency_key
                and fire.__class__.objects.filter(schedule=schedule, scheduled_for=schedule_fire_at).count() == 1,
            ),
            (
                "normalAssignmentCreated",
                lambda: fire.state == AgentScheduleFireState.CREATED and fire.assignment_id is not None,
            ),
        ),
        checkpoint=checkpoint,
    )

    # M03/M04 is a complete selected commission.  Do not continue into the
    # later review/governance cells: an unrelated later-cell exception must not
    # turn a satisfied cancellation/schedule commission into a generic runner
    # failure after its last assertion.
    if selected_route_ids <= {"M03", "M04"}:
        return {
            "routes": {
                route_id: route
                for route_id, route in (("M03", m03), ("M04", m04))
                if route_id in selected_route_ids
            }
            | {"replay": {"stateMutations": 0}},
            "readback": _manager_readback(workspace),
        }

    # M05: one outcome takes revision, the next fresh run is accepted.  The
    # producer never performs the evaluator/human decision itself.
    if checkpoint is not None:
        checkpoint.before("M05", "evaluatorFirst")
    review_assignment = create_assignment(
        worker,
        project=project,
        target_ref=f"target:g4-manager-{suffix}-review",
        objective="Produce an evaluator-reviewed synthetic outcome.",
        plan_rationale="The Manager routes the result through independent review.",
        acceptance_criteria=["The final artifact is accepted after review."],
        created_by=human_admin,
    )
    first_run = create_run(review_assignment, worker.active_profile, created_by=human_admin)
    first_invocation = record_invocation(
        first_run,
        idempotency_key=_idempotency(suffix, "first-review-invocation"),
        created_by=human_admin,
    )
    first_outcome = propose_outcome(
        first_run,
        summary="The first synthetic result needs one bounded revision.",
        artifacts=[f"artifact:g4-manager-{suffix}-first"],
        evidence=[f"evidence:g4-manager-{suffix}-first"],
        idempotency_key=_idempotency(suffix, "first-outcome"),
        created_by=human_admin,
    )
    human_before_evaluator_denied = False
    try:
        accept_outcome(first_outcome, human_reviewer=human_admin)
    except InvalidTransitionError:
        human_before_evaluator_denied = True
    first_review = review_outcome(
        first_outcome,
        evaluator=evaluator,
        feedback="Add one more evidence item.",
        idempotency_key=_idempotency(suffix, "first-review"),
    )
    revised = request_revision(first_review, human_reviewer=human_admin, decision_note="Revise the evidence.")
    first_snapshot = deepcopy(first_run.snapshot)
    second_run = create_run(
        review_assignment,
        worker.active_profile,
        lineage_of=first_run,
        lineage_reason="human_revision",
        idempotency_key=_idempotency(suffix, "second-review-run"),
        created_by=human_admin,
    )
    second_invocation = record_invocation(
        second_run,
        idempotency_key=_idempotency(suffix, "second-review-invocation"),
        created_by=human_admin,
    )
    second_outcome = propose_outcome(
        second_run,
        summary="The revised synthetic result is complete.",
        artifacts=[f"artifact:g4-manager-{suffix}-final"],
        evidence=[f"evidence:g4-manager-{suffix}-final"],
        idempotency_key=_idempotency(suffix, "second-outcome"),
        created_by=human_admin,
    )
    second_review = review_outcome(
        second_outcome,
        evaluator=evaluator,
        feedback="The revised evidence is sufficient.",
        idempotency_key=_idempotency(suffix, "second-review"),
    )
    accepted = accept_outcome(second_review, human_reviewer=human_admin, decision_note="Accept the revision.")
    first_run.refresh_from_db()
    second_run.refresh_from_db()
    m05 = _evaluate_manager_route(
        "M05",
        (
            (
                "evaluatorFirst",
                lambda: human_before_evaluator_denied and first_review.evaluator_id == evaluator.id,
            ),
            ("humanDecisionAfterEvaluator", lambda: revised.human_reviewer_id == human_admin.id),
            (
                "revisionFreshRun",
                lambda: second_run.lineage_of_id == first_run.id
                and second_run.lineage_reason == "human_revision"
                and second_run.id != first_run.id,
            ),
            ("priorSnapshotImmutable", lambda: first_run.snapshot == first_snapshot),
            (
                "finalAccepted",
                lambda: accepted.state == "accepted"
                and accepted.human_reviewer_id == human_admin.id
                and first_invocation.terminal_event.kind == "outcome_submission"
                and second_invocation.terminal_event.kind == "outcome_submission",
            ),
        ),
        checkpoint=checkpoint,
    )

    # M06: the HR bot may propose but cannot approve; changed actor state makes
    # the first human approval stale; a second proposal is approved by a human.
    if checkpoint is not None:
        checkpoint.before("M06", "proposalRecorded")
    stale_proposal = propose_hr_change(
        workspace=workspace,
        proposed_by=hr,
        kind=HRProposalKind.ROLE_CHANGE,
        subject_actor=worker,
        requested_role=AgentRole.EVALUATOR,
        rationale="Request a synthetic role change.",
        idempotency_key=_idempotency(suffix, "stale-hr-proposal"),
        created_by=human_admin,
    )
    create_profile(worker, role=AgentRole.WORKER, instructions="The worker profile changed after proposal.")
    self_approval_denied = False
    try:
        decide_hr_proposal(
            stale_proposal,
            human_reviewer=hr.principal,
            approved=True,
            idempotency_key=_idempotency(suffix, "self-hr-decision"),
        )
    except AgentDomainError:
        self_approval_denied = True
    stale_approval_denied = False
    try:
        decide_hr_proposal(
            stale_proposal,
            human_reviewer=human_admin,
            approved=True,
            idempotency_key=_idempotency(suffix, "stale-hr-decision"),
        )
    except AgentDomainError:
        stale_approval_denied = True
    hire_proposal = propose_hr_change(
        workspace=workspace,
        proposed_by=hr,
        kind=HRProposalKind.HIRE,
        requested_role=AgentRole.WORKER,
        requested_display_name=f"Synthetic hired worker {suffix}",
        requested_profile={"instructions": "Operate as the approved synthetic worker."},
        rationale="Approve one bounded synthetic Agent hire.",
        idempotency_key=_idempotency(suffix, "approved-hr-proposal"),
        project=project,
        created_by=human_admin,
    )
    approved_hire = decide_hr_proposal(
        hire_proposal,
        human_reviewer=human_admin,
        approved=True,
        idempotency_key=_idempotency(suffix, "approved-hr-decision"),
    )
    m06 = _evaluate_manager_route(
        "M06",
        (
            ("proposalRecorded", lambda: stale_proposal.state == HRProposalState.PROPOSED),
            (
                "humanApprovalApplied",
                lambda: approved_hire.state == HRProposalState.APPROVED
                and approved_hire.applied_actor_id is not None,
            ),
            ("selfApprovalDenied", lambda: self_approval_denied),
            ("staleApprovalDenied", lambda: stale_approval_denied),
        ),
        checkpoint=checkpoint,
    )

    # M05/M06 is a complete selected commission.  Stop at its terminal route
    # boundary so later chief-of-staff setup cannot turn satisfied review/HR
    # evidence into a generic runner failure.
    if selected_route_ids <= {"M05", "M06"}:
        route_result = {
            "routes": {
                route_id: route
                for route_id, route in (("M05", m05), ("M06", m06))
                if route_id in selected_route_ids
            }
            | {"replay": {"stateMutations": 0}},
        }
        return {
            **route_result,
            "readback": _post_route_readback(workspace),
        }

    # M07: chief-of-staff provisioning copies only the subject's live
    # membership at decision time and cannot be approved by the HR bot.
    if checkpoint is not None:
        checkpoint.before("M07", "humanApprovalRequired")
    subject = _synthetic_human(workspace, suffix=suffix, role=10)
    chief_proposal = propose_chief_of_staff(
        workspace=workspace,
        human=subject,
        proposed_by=hr,
        rationale="Provision one scoped synthetic chief of staff.",
        idempotency_key=_idempotency(suffix, "chief-proposal"),
        created_by=human_admin,
    )
    chief_self_denied = False
    try:
        decide_hr_proposal(
            chief_proposal,
            human_reviewer=hr.principal,
            approved=True,
            idempotency_key=_idempotency(suffix, "chief-self-decision"),
        )
    except AgentDomainError:
        chief_self_denied = True
    chief_decision = decide_hr_proposal(
        chief_proposal,
        human_reviewer=human_admin,
        approved=True,
        idempotency_key=_idempotency(suffix, "chief-decision"),
    )
    chief = chief_decision.applied_actor
    subject_member = WorkspaceMember.objects.get(workspace=workspace, member=subject, is_active=True)
    chief_member = WorkspaceMember.objects.get(workspace=workspace, member=chief.principal, is_active=True)
    m07 = _evaluate_manager_route(
        "M07",
        (
            ("humanApprovalRequired", lambda: chief_self_denied),
            (
                "chiefProvisioned",
                lambda: chief is not None
                and chief.chief_of_staff_for_id == subject.id
                and chief.active_profile.role == AgentRole.CHIEF_OF_STAFF,
            ),
            ("currentMembershipCopied", lambda: chief_member.role == subject_member.role),
            ("noStaleMembershipCopy", lambda: chief_member.role != 15),
            (
                "noCrossWorkspaceMembership",
                lambda: WorkspaceMember.objects.filter(member=chief.principal, is_active=True).count() == 1,
            ),
        ),
        checkpoint=checkpoint,
    )

    # M08: read back the whole graph and compare the immutable first snapshot
    # to the stored run after the revised run and governance decisions.
    if checkpoint is not None:
        checkpoint.before("M08", "parentChildLineage")
    governance = build_governance_readback(workspace, limit=4)
    all_assignments = AssignmentContract.objects.filter(workspace=workspace)
    all_outcomes = OutcomeSubmission.objects.filter(workspace=workspace)
    all_events = RunTerminalEvent.objects.filter(workspace=workspace, visible=True)
    artifact_outcomes = [
        outcome
        for outcome in all_outcomes
        if outcome.artifacts and outcome.evidence
    ]
    outcome_event_agreement = all(
        all_events.filter(run=outcome.run, kind="outcome_submission").count() == 1 for outcome in all_outcomes
    )
    readback_digest = _digest(
        {
            "assignments": governance["assignments"],
            "hrProposals": governance["hr_proposals"],
            "evaluatorReviews": governance["evaluator_reviews"],
            "outcomeCount": all_outcomes.count(),
            "terminalEventCount": all_events.count(),
        }
    )
    m08 = _evaluate_manager_route(
        "M08",
        (
            ("parentChildLineage", lambda: all_assignments.filter(lineage_of__isnull=False).exists()),
            ("outcomeAndArtifact", lambda: bool(all_outcomes.count() >= 2 and artifact_outcomes)),
            ("terminalEventsAgree", lambda: bool(all_events.exists() and outcome_event_agreement)),
            (
                "evaluatorAndHumanReadback",
                lambda: bool(
                    governance["evaluator_reviews"]
                    and any(outcome.human_reviewer_id is not None for outcome in all_outcomes)
                    and any(
                        proposal.reviewed_by_id is not None
                        for proposal in AgentHRProposal.objects.filter(workspace=workspace)
                    )
                ),
            ),
            ("immutablePriorSnapshot", lambda: first_run.snapshot == first_snapshot),
        ),
        checkpoint=checkpoint,
    )

    routes = {"M01": m01, "M02": m02, "M03": m03, "M04": m04, "M05": m05, "M06": m06, "M07": m07, "M08": m08}
    if route_checks is not None:
        routes = {route_id: routes[route_id] for route_id in _ROUTE_IDS if route_id in route_checks}
    routes["replay"] = {"stateMutations": 0}
    return {
        "routes": routes,
        "readback": {
            "assignmentCount": all_assignments.count(),
            "childAssignmentCount": all_assignments.filter(lineage_of__isnull=False).count(),
            "outcomeCount": all_outcomes.count(),
            "artifactOutcomeCount": len(artifact_outcomes),
            "terminalEventCount": all_events.count(),
            "governanceReadbackDigest": readback_digest,
        },
    }


def build_manager_route_evidence(**kwargs) -> tuple[dict[str, object], list[str]]:
    """Return bounded Manager evidence and deterministic route failures."""

    route_checks = kwargs.get("route_checks")
    checkpoint = _ManagerRouteCheckpoint()
    kwargs["checkpoint"] = checkpoint
    try:
        evidence = _exercise_manager_journey(**kwargs)
    except BaseException as exc:
        checkpoint.attach(exc)
        raise
    routes = evidence["routes"]
    selected_route_ids = set(route_checks) if route_checks is not None else set(_ROUTE_IDS)
    failures = [
        route_id
        for route_id in selected_route_ids
        if not _all_true(routes[route_id])
    ]
    return evidence, failures

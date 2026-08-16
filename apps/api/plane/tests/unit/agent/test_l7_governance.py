from types import SimpleNamespace
from django.contrib.auth.models import AnonymousUser

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction

from plane.agent.lifecycle import (
    AgentDomainError,
    IdempotencyConflictError,
    accept_outcome,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    delegate_assignment,
    propose_chief_of_staff,
    propose_hr_change,
    propose_outcome,
    record_invocation,
    request_revision,
    review_outcome,
    decide_hr_proposal,
    cancel_assignment,
)
from plane.agent.lifecycle import InvalidTransitionError
from plane.agent.administration_extensions import build_governance_readback
from plane.db.models import (
    AgentHRProposal,
    AgentRole,
    AssignmentState,
    EvaluatorReview,
    EvaluatorVerdict,
    HRProposalKind,
    HRProposalState,
    OperationGatewayAudit,
    OutcomeState,
    Project,
    RunState,
    RunTerminalEvent,
    RuntimeControlState,
    RuntimeInvocation,
    RuntimeInvocationControl,
    Workspace,
    WorkspaceMember,
    AssignmentContract,
    User,
)
from plane.operation_gateway.catalog import get_operation
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.operations import AgentGovernanceOperation, OperationAdapterFailure


@pytest.fixture(scope="session")
def django_db_use_migrations():
    """Exercise the migration-owned governance scope guards in this lane."""

    return True


def _actor(workspace, *, name, role, project=None, created_by=None):
    actor = create_actor(workspace=workspace, project=project, display_name=name, created_by=created_by)
    create_profile(actor, role=role, instructions=f"Operate as {role}.", created_by=created_by)
    actor.refresh_from_db()
    return actor


@pytest.fixture
def project(workspace, create_user):
    return Project.objects.create(
        workspace=workspace,
        name="L7 governance project",
        identifier="L7G",
        created_by=create_user,
    )


@pytest.mark.django_db
def test_delegation_is_replay_safe_bounded_and_lineage_immutable(workspace, project, create_user):
    delegator = _actor(workspace, name="Delegator", role=AgentRole.DELEGATOR, project=project, created_by=create_user)
    worker = _actor(workspace, name="Worker", role=AgentRole.DELEGATOR, project=project, created_by=create_user)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:parent",
        objective="Coordinate the work.",
        acceptance_criteria=["The child result is reviewable."],
        scope={"queues": ["backend"]},
        budget={"maxInputTokens": 5, "maxFanOut": 3, "maxDepth": 1},
        created_by=create_user,
    )

    child = delegate_assignment(
        parent,
        worker,
        target_ref="issue:child",
        objective="Implement the bounded child task.",
        plan_rationale="The delegator isolated the child implementation path.",
        acceptance_criteria=["The child is complete."],
        scope={"queues": ["backend"]},
        budget={"inputTokens": 4},
        idempotency_key="idempotency:delegation-1",
        delegated_by=delegator,
        created_by=create_user,
    )
    replay = delegate_assignment(
        parent,
        worker,
        target_ref="issue:child",
        objective="Implement the bounded child task.",
        plan_rationale="The delegator isolated the child implementation path.",
        acceptance_criteria=["The child is complete."],
        scope={"queues": ["backend"]},
        budget={"inputTokens": 4},
        idempotency_key="idempotency:delegation-1",
        delegated_by=delegator,
        created_by=create_user,
    )
    assert replay.id == child.id
    assert child.lineage_of_id == parent.id
    assert child.root_assignment_id == parent.id
    assert child.delegated_by_id == delegator.id
    assert child.delegation_depth == 1
    assert child.assignee_id != parent.assignee_id

    with pytest.raises(IdempotencyConflictError):
        delegate_assignment(
            parent,
            worker,
            target_ref="issue:another-child",
            objective="A different command.",
            plan_rationale="The delegator attempted a conflicting replay command.",
            acceptance_criteria=["The child is complete."],
            idempotency_key="idempotency:delegation-1",
            delegated_by=delegator,
        )

    with pytest.raises(AgentDomainError, match="scope cannot escalate"):
        delegate_assignment(
            parent,
            worker,
            target_ref="issue:escalated",
            objective="Escape the parent scope.",
            plan_rationale="The delegator attempted an out-of-scope child.",
            acceptance_criteria=["Denied."],
            scope={"queues": ["frontend"]},
            budget={"inputTokens": 1},
            idempotency_key="idempotency:delegation-escalation",
            delegated_by=delegator,
        )
    with pytest.raises(AgentDomainError, match="cumulative budget"):
        delegate_assignment(
            parent,
            worker,
            target_ref="issue:over-budget",
            objective="Exceed the root budget.",
            plan_rationale="The delegator attempted an over-budget child.",
            acceptance_criteria=["Denied."],
            scope={"queues": ["backend"]},
            budget={"inputTokens": 2},
            idempotency_key="idempotency:delegation-over-budget",
            delegated_by=delegator,
        )

    parent.lineage_of_id = child.id
    with pytest.raises(ValidationError):
        parent.save()

    with pytest.raises(AgentDomainError, match="maximum depth"):
        delegate_assignment(
            child,
            delegator,
            target_ref="issue:grandchild",
            objective="The depth bound must hold.",
            plan_rationale="The delegator attempted a depth-bounded child.",
            acceptance_criteria=["Denied."],
            idempotency_key="idempotency:delegation-depth",
            delegated_by=worker,
        )


@pytest.mark.django_db
def test_completed_assignment_cannot_receive_runtime_delegation(workspace, project, create_user):
    delegator = _actor(workspace, name="Completed delegator", role=AgentRole.DELEGATOR, project=project)
    worker = _actor(workspace, name="Completed worker", role=AgentRole.WORKER, project=project)
    evaluator = _actor(workspace, name="Completed evaluator", role=AgentRole.EVALUATOR)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:completed-parent",
        objective="Complete the parent before attempting a child.",
        acceptance_criteria=["The parent has a terminal accepted outcome."],
        budget={"maxDepth": 1},
        created_by=create_user,
    )
    run = create_run(parent, delegator.active_profile, created_by=create_user)
    record_invocation(run, idempotency_key="idempotency:completed-parent-invocation", created_by=create_user)
    outcome = propose_outcome(
        run,
        summary="The parent is complete.",
        idempotency_key="idempotency:completed-parent-outcome",
        created_by=create_user,
    )
    review_outcome(
        outcome,
        evaluator=evaluator,
        idempotency_key="idempotency:completed-parent-review",
    )
    accept_outcome(outcome, human_reviewer=create_user, decision_note="Parent accepted.")
    parent.refresh_from_db()
    assert parent.state == AssignmentState.COMPLETED

    with pytest.raises(InvalidTransitionError, match="Completed assignments"):
        delegate_assignment(
            parent,
            worker,
            target_ref="issue:completed-child",
            objective="This child must not be created after completion.",
            plan_rationale="The completed parent has no remaining runtime delegation authority.",
            acceptance_criteria=["Rejected."],
            idempotency_key="idempotency:completed-child",
            delegated_by=delegator,
            created_by=create_user,
        )
    assert AssignmentContract.objects.filter(lineage_of=parent).count() == 0


@pytest.mark.django_db
def test_dynamic_plan_rationale_is_durable_and_readable(workspace, project, create_user):
    delegator = _actor(workspace, name="Rationale delegator", role=AgentRole.DELEGATOR, project=project)
    worker = _actor(workspace, name="Rationale worker", role=AgentRole.DELEGATOR, project=project)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:rationale-parent",
        objective="Coordinate the rationale test.",
        acceptance_criteria=["The child rationale is durable."],
        budget={"maxDepth": 1},
        created_by=create_user,
    )

    child = delegate_assignment(
        parent,
        worker,
        target_ref="issue:rationale-child",
        objective="Complete the rationale test.",
        acceptance_criteria=["The rationale is returned on readback."],
        plan_rationale="The delegator selected this child to isolate the reviewable evidence path.",
        idempotency_key="idempotency:rationale-child",
        delegated_by=delegator,
        created_by=create_user,
    )
    replay = delegate_assignment(
        parent,
        worker,
        target_ref="issue:rationale-child",
        objective="Complete the rationale test.",
        acceptance_criteria=["The rationale is returned on readback."],
        plan_rationale="The delegator selected this child to isolate the reviewable evidence path.",
        idempotency_key="idempotency:rationale-child",
        delegated_by=delegator,
        created_by=create_user,
    )

    assert replay.id == child.id
    assert child.plan_rationale.startswith("The delegator selected")
    readback = build_governance_readback(workspace, limit=10, resource_id=f"assignment:{child.id}")
    assert readback["assignments"][0]["plan_rationale"] == child.plan_rationale


@pytest.mark.django_db
def test_dynamic_plan_rationale_survives_gateway_replay(workspace, project, create_user):
    delegator = _actor(workspace, name="Gateway rationale delegator", role=AgentRole.DELEGATOR, project=project)
    worker = _actor(workspace, name="Gateway rationale worker", role=AgentRole.WORKER, project=project)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:gateway-rationale-parent",
        objective="Coordinate the gateway rationale test.",
        acceptance_criteria=["The child rationale is returned by the gateway."],
        budget={"maxDepth": 1},
        created_by=create_user,
    )
    request = SimpleNamespace(user=delegator.principal, agent_actor_ref=f"agent-actor:{delegator.id}")
    envelope = {
        "schema_version": "plane.operation/v1",
        "operation_id": "agent.assignment.delegate",
        "workspace_slug": workspace.slug,
        "idempotency_key": "gateway-rationale-delegation",
        "correlation_id": "gateway-rationale-correlation",
        "input": {
            "parent_assignment_ref": f"assignment:{parent.id}",
            "delegator_ref": f"agent-actor:{delegator.id}",
            "assignee_ref": f"agent-actor:{worker.id}",
            "target_ref": "issue:gateway-rationale-child",
            "objective": "Complete the gateway rationale test.",
            "plan_rationale": "The gateway must preserve the delegator's dynamic plan decision.",
            "acceptance_criteria": ["The rationale is durable and replayable."],
        },
    }

    response, status = OperationGateway().execute(request, envelope)
    assert status == 200, response
    assert response["result"]["assignment"]["planRationale"] == envelope["input"]["plan_rationale"]
    child_ref = response["result"]["assignment"]["assignmentRef"]

    replay, replay_status = OperationGateway().execute(request, envelope)
    assert replay_status == 200
    assert replay["idempotency"]["replayed"] is True
    assert replay["result"]["assignment"]["assignmentRef"] == child_ref
    assert AssignmentContract.objects.filter(lineage_of=parent).count() == 1


@pytest.mark.django_db(transaction=True)
def test_delegation_scope_guard_allows_cross_actor_and_rejects_cross_scope_lineage(workspace, project, create_user):
    delegator = _actor(
        workspace, name="Scope delegator", role=AgentRole.DELEGATOR, project=project, created_by=create_user
    )
    worker = _actor(workspace, name="Scope worker", role=AgentRole.WORKER, project=project, created_by=create_user)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:scope-parent",
        objective="Create a scoped child.",
        acceptance_criteria=["The child remains in scope."],
        created_by=create_user,
    )
    child = delegate_assignment(
        parent,
        worker,
        target_ref="issue:scope-child",
        objective="Complete the scoped child.",
        plan_rationale="The delegator assigned the child within the parent scope.",
        acceptance_criteria=["The child is complete."],
        idempotency_key="idempotency:scope-child",
        delegated_by=delegator,
        created_by=create_user,
    )
    assert child.assignee_id == worker.id
    assert child.lineage_of_id == parent.id

    other_workspace = Workspace.objects.create(
        name="Other Scope Workspace",
        owner=create_user,
        slug="other-scope-workspace",
    )
    other_project = Project.objects.create(
        name="Other Scope Project",
        identifier="OSP",
        workspace=other_workspace,
        created_by=create_user,
    )
    other_actor = _actor(
        other_workspace,
        name="Other scope actor",
        role=AgentRole.WORKER,
        project=other_project,
        created_by=create_user,
    )
    other_parent = create_assignment(
        other_actor,
        project=other_project,
        target_ref="issue:other-parent",
        objective="Remain in the other scope.",
        acceptance_criteria=["The scope is isolated."],
        created_by=create_user,
    )

    def forged_assignment(**overrides):
        values = {
            "workspace": workspace,
            "project": project,
            "assignee": worker,
            "lineage_of": parent,
            "root_assignment": parent,
            "delegated_by": delegator,
            "scope": {},
            "budget": {},
            "target_ref": "issue:forged-scope",
            "objective": "Must be rejected by the database guard.",
            "acceptance_criteria": ["Never accepted."],
        }
        values.update(overrides)
        return AssignmentContract.objects.bulk_create([AssignmentContract(**values)])[0]

    with pytest.raises(DatabaseError, match="lineage"):
        with transaction.atomic():
            forged_assignment(lineage_of=other_parent)
    with pytest.raises(DatabaseError, match="root"):
        with transaction.atomic():
            forged_assignment(root_assignment=other_parent)
    with pytest.raises(DatabaseError, match="delegator"):
        with transaction.atomic():
            forged_assignment(delegated_by=other_actor)


@pytest.mark.django_db
def test_assignment_cancellation_reconciles_root_and_descendant_queued_runs(workspace, project, create_user):
    delegator = _actor(workspace, name="Queued cancellation delegator", role=AgentRole.DELEGATOR, project=project)
    worker = _actor(workspace, name="Queued cancellation worker", role=AgentRole.WORKER, project=project)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:queued-cancel-parent",
        objective="Cancel the queued assignment tree.",
        acceptance_criteria=["Every queued run is terminal."],
        created_by=create_user,
    )
    child = delegate_assignment(
        parent,
        worker,
        target_ref="issue:queued-cancel-child",
        objective="Remain queued under the cancelled parent.",
        plan_rationale="The delegator created the queued descendant before cancellation.",
        acceptance_criteria=["The child run is terminal."],
        idempotency_key="idempotency:queued-cancel-child",
        delegated_by=delegator,
        created_by=create_user,
    )
    parent_run = create_run(parent, delegator.active_profile, created_by=create_user)
    child_run = create_run(child, worker.active_profile, created_by=create_user)

    cancel_assignment(parent, operator=create_user)
    parent.refresh_from_db()
    child.refresh_from_db()
    parent_run.refresh_from_db()
    child_run.refresh_from_db()
    assert parent.state == child.state == AssignmentState.CANCELLED
    assert parent_run.state == child_run.state == RunState.CANCELLED
    assert parent_run.last_invocation_id is None
    assert child_run.last_invocation_id is None
    assert RuntimeInvocation.objects.filter(run_id__in=[parent_run.id, child_run.id]).count() == 0
    assert RuntimeInvocationControl.objects.filter(invocation__run_id__in=[parent_run.id, child_run.id]).count() == 0

    with pytest.raises(InvalidTransitionError, match="Cancelled assignments"):
        delegate_assignment(
            parent,
            worker,
            target_ref="issue:queued-cancel-after",
            objective="This must never become dispatchable.",
            plan_rationale="The delegator attempted work after parent cancellation.",
            acceptance_criteria=["Rejected."],
            idempotency_key="idempotency:queued-cancel-after",
            delegated_by=delegator,
            created_by=create_user,
        )
    with pytest.raises(InvalidTransitionError, match="Cancelled assignments"):
        record_invocation(parent_run, idempotency_key="idempotency:queued-cancel-replay", created_by=create_user)

    cancel_assignment(parent, operator=create_user)
    parent_run.refresh_from_db()
    child_run.refresh_from_db()
    assert parent_run.state == child_run.state == RunState.CANCELLED


@pytest.mark.django_db
def test_assignment_cancellation_signals_active_root_and_descendant_runtime_controls(workspace, project, create_user):
    delegator = _actor(workspace, name="Active cancellation delegator", role=AgentRole.DELEGATOR, project=project)
    worker = _actor(workspace, name="Active cancellation worker", role=AgentRole.WORKER, project=project)
    parent = create_assignment(
        delegator,
        project=project,
        target_ref="issue:active-cancel-parent",
        objective="Cancel active runtime work.",
        acceptance_criteria=["Both controls receive cancellation."],
        created_by=create_user,
    )
    child = delegate_assignment(
        parent,
        worker,
        target_ref="issue:active-cancel-child",
        objective="Remain active under the cancelled parent.",
        plan_rationale="The delegator assigned the active descendant for cancellation propagation.",
        acceptance_criteria=["The child runtime is cancelled."],
        idempotency_key="idempotency:active-cancel-child",
        delegated_by=delegator,
        created_by=create_user,
    )
    parent_run = create_run(parent, delegator.active_profile, created_by=create_user)
    child_run = create_run(child, worker.active_profile, created_by=create_user)
    parent_invocation = record_invocation(
        parent_run,
        idempotency_key="idempotency:active-cancel-parent",
        created_by=create_user,
    )
    child_invocation = record_invocation(
        child_run,
        idempotency_key="idempotency:active-cancel-child-run",
        created_by=create_user,
    )

    cancel_assignment(parent, operator=create_user)
    for invocation in (parent_invocation, child_invocation):
        invocation.refresh_from_db()
        control = RuntimeInvocationControl.objects.get(invocation=invocation)
        assert invocation.state == "cancelled"
        assert control.state == RuntimeControlState.RELEASED
        assert control.cancellation_requested_at is not None
        assert RunTerminalEvent.objects.filter(invocation=invocation).count() == 1
    parent_run.refresh_from_db()
    child_run.refresh_from_db()
    assert parent_run.state == child_run.state == RunState.CANCELLED

    cancel_assignment(parent, operator=create_user)
    assert RunTerminalEvent.objects.filter(invocation__in=[parent_invocation, child_invocation]).count() == 2


@pytest.mark.django_db
def test_lifecycle_governance_requires_active_human_role20(workspace, project, create_user):
    worker = _actor(workspace, name="Authorization worker", role=AgentRole.WORKER, project=project)
    assignment = create_assignment(
        worker,
        project=project,
        target_ref="issue:authorization-cancel",
        objective="Remain unchanged when governance is denied.",
        acceptance_criteria=["The assignment remains ready."],
        created_by=create_user,
    )
    role15 = User.objects.create(username="role15-governance", email="role15-governance@plane.so", is_active=True)
    role10 = User.objects.create(username="role10-governance", email="role10-governance@plane.so", is_active=True)
    bot = User.objects.create(
        username="bot-governance",
        email="bot-governance@plane.so",
        is_active=True,
        is_bot=True,
    )
    wrong_workspace = User.objects.create(
        username="wrong-workspace-governance",
        email="wrong-workspace-governance@plane.so",
        is_active=True,
    )
    WorkspaceMember.objects.create(workspace=workspace, member=role15, role=15, is_active=True)
    WorkspaceMember.objects.create(workspace=workspace, member=role10, role=10, is_active=True)
    WorkspaceMember.objects.create(workspace=workspace, member=bot, role=20, is_active=True)
    other_workspace = Workspace.objects.create(
        name="Governance authorization other workspace",
        owner=create_user,
        slug="governance-authorization-other-workspace",
    )
    WorkspaceMember.objects.create(workspace=other_workspace, member=wrong_workspace, role=20, is_active=True)

    for operator in (role15, role10, bot, wrong_workspace, AnonymousUser()):
        with pytest.raises(AgentDomainError, match="workspace administrator"):
            cancel_assignment(assignment, operator=operator)

    assignment.refresh_from_db()
    assert assignment.state == AssignmentState.READY


@pytest.mark.django_db
def test_hr_proposal_requires_human_approval_and_fails_closed_on_stale_state(workspace, project, create_user):
    hr = _actor(workspace, name="HR", role=AgentRole.HR, created_by=create_user)
    subject = _actor(workspace, name="Subject", role=AgentRole.WORKER, created_by=create_user)
    proposal = propose_hr_change(
        workspace=workspace,
        proposed_by=hr,
        kind=HRProposalKind.ROLE_CHANGE,
        subject_actor=subject,
        requested_role=AgentRole.EVALUATOR,
        rationale="The subject will evaluate independent outcomes.",
        idempotency_key="idempotency:hr-role-change",
        created_by=create_user,
    )
    assert proposal.state == HRProposalState.PROPOSED
    subject.refresh_from_db()
    assert subject.active_profile.role == AgentRole.WORKER
    assert (
        propose_hr_change(
            workspace=workspace,
            proposed_by=hr,
            kind=HRProposalKind.ROLE_CHANGE,
            subject_actor=subject,
            requested_role=AgentRole.EVALUATOR,
            rationale="The subject will evaluate independent outcomes.",
            idempotency_key="idempotency:hr-role-change",
        ).id
        == proposal.id
    )

    create_profile(subject, role=AgentRole.WORKER, instructions="A current profile change makes the proposal stale.")
    with pytest.raises(AgentDomainError, match="stale"):
        decide_hr_proposal(
            proposal,
            human_reviewer=create_user,
            approved=True,
            idempotency_key="idempotency:hr-role-decision",
        )
    proposal.refresh_from_db()
    assert proposal.state == HRProposalState.PROPOSED

    demoted = User.objects.create(
        username="demoted-governance-reviewer",
        email="demoted-governance-reviewer@plane.so",
        is_active=True,
        is_bot=False,
    )
    WorkspaceMember.objects.create(workspace=workspace, member=demoted, role=10, is_active=True)
    with pytest.raises(AgentDomainError, match="current workspace administrator"):
        decide_hr_proposal(
            proposal,
            human_reviewer=demoted,
            approved=True,
            idempotency_key="idempotency:hr-demoted-reviewer",
        )
    other_workspace = Workspace.objects.create(
        name="Governance reviewer other workspace",
        owner=create_user,
        slug="governance-reviewer-other-workspace",
    )
    wrong_workspace_admin = User.objects.create(
        username="wrong-workspace-reviewer",
        email="wrong-workspace-reviewer@plane.so",
        is_active=True,
        is_bot=False,
    )
    WorkspaceMember.objects.create(workspace=other_workspace, member=wrong_workspace_admin, role=20, is_active=True)
    with pytest.raises(AgentDomainError, match="current workspace administrator"):
        decide_hr_proposal(
            proposal,
            human_reviewer=wrong_workspace_admin,
            approved=True,
            idempotency_key="idempotency:hr-wrong-workspace-reviewer",
        )

    with pytest.raises(AgentDomainError, match="credential"):
        propose_hr_change(
            workspace=workspace,
            proposed_by=hr,
            kind=HRProposalKind.HIRE,
            requested_profile={"runtime_defaults": {"Authorization": "Bearer secret"}},
            rationale="This must not store credentials.",
            idempotency_key="idempotency:hr-credential",
        )


@pytest.mark.django_db
def test_hr_reassignment_rechecks_requested_assignee_is_active(workspace, create_user):
    hr = _actor(workspace, name="Reassignment HR", role=AgentRole.HR, created_by=create_user)
    current_assignee = _actor(workspace, name="Current assignee", role=AgentRole.WORKER, created_by=create_user)
    requested_assignee = _actor(workspace, name="Requested assignee", role=AgentRole.WORKER, created_by=create_user)
    assignment = create_assignment(
        current_assignee,
        target_ref="issue:hr-reassignment",
        objective="Keep the current assignee until HR approval is safe.",
        acceptance_criteria=["The assignment remains bound to an active Agent."],
        created_by=create_user,
    )
    proposal = propose_hr_change(
        workspace=workspace,
        proposed_by=hr,
        kind=HRProposalKind.REASSIGN,
        target_assignment=assignment,
        requested_assignee=requested_assignee,
        rationale="Move the assignment to the requested worker after approval.",
        idempotency_key="idempotency:hr-reassignment",
        created_by=create_user,
    )
    requested_assignee.is_active = False
    requested_assignee.save(update_fields=["is_active", "updated_at"])

    with pytest.raises(AgentDomainError, match="Inactive Agent"):
        decide_hr_proposal(
            proposal,
            human_reviewer=create_user,
            approved=True,
            idempotency_key="idempotency:hr-reassignment-decision",
        )
    assignment.refresh_from_db()
    proposal.refresh_from_db()
    assert assignment.assignee_id == current_assignee.id
    assert proposal.state == HRProposalState.PROPOSED


@pytest.mark.django_db
def test_governance_terminal_replays_recheck_live_role20_and_preserve_attribution(workspace, project, create_user):
    hr = _actor(workspace, name="Replay HR", role=AgentRole.HR, created_by=create_user)
    subject = _actor(workspace, name="Replay subject", role=AgentRole.WORKER, created_by=create_user)
    proposal = propose_hr_change(
        workspace=workspace,
        proposed_by=hr,
        kind=HRProposalKind.ROLE_CHANGE,
        subject_actor=subject,
        requested_role=AgentRole.EVALUATOR,
        rationale="Record one terminal HR decision.",
        idempotency_key="idempotency:replay-hr-proposal",
        created_by=create_user,
    )
    decided = decide_hr_proposal(
        proposal,
        human_reviewer=create_user,
        approved=True,
        decision_note="Approved by the current administrator.",
        idempotency_key="idempotency:replay-hr-decision",
    )
    with pytest.raises(IdempotencyConflictError):
        decide_hr_proposal(
            decided,
            human_reviewer=create_user,
            approved=True,
            decision_note="Changed decision note.",
            idempotency_key="idempotency:replay-hr-changed-key",
        )
    decided.refresh_from_db()
    hr_state_before = (decided.state, decided.reviewed_by_id, decided.decision_idempotency_key)

    producer = _actor(workspace, name="Replay producer", role=AgentRole.WORKER, project=project)
    evaluator = _actor(workspace, name="Replay evaluator", role=AgentRole.EVALUATOR, created_by=create_user)

    def reviewed_outcome(suffix):
        assignment = create_assignment(
            producer,
            project=project,
            target_ref=f"issue:replay-{suffix}",
            objective=f"Produce the {suffix} replay outcome.",
            acceptance_criteria=["The outcome has independent review."],
            created_by=create_user,
        )
        run = create_run(assignment, producer.active_profile, created_by=create_user)
        record_invocation(run, idempotency_key=f"idempotency:replay-{suffix}-invocation")
        outcome = propose_outcome(
            run,
            summary=f"Replay {suffix} outcome.",
            idempotency_key=f"idempotency:replay-{suffix}-outcome",
            created_by=create_user,
        )
        review_outcome(
            outcome,
            evaluator=evaluator,
            idempotency_key=f"idempotency:replay-{suffix}-review",
        )
        return outcome

    accepted = accept_outcome(
        reviewed_outcome("accepted"),
        human_reviewer=create_user,
        decision_note="Accept the reviewed result.",
    )
    revised = request_revision(
        reviewed_outcome("revision"),
        human_reviewer=create_user,
        decision_note="Request one more bounded revision.",
    )
    outcome_states_before = {
        accepted.id: (accepted.state, accepted.human_reviewer_id, accepted.updated_by_id),
        revised.id: (revised.state, revised.human_reviewer_id, revised.updated_by_id),
    }

    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
    for terminal, decision in ((accepted, accept_outcome), (revised, request_revision)):
        with pytest.raises(AgentDomainError, match="workspace administrator"):
            decision(terminal, human_reviewer=create_user, decision_note="Denied after demotion.")
        terminal.refresh_from_db()
        assert (terminal.state, terminal.human_reviewer_id, terminal.updated_by_id) == outcome_states_before[
            terminal.id
        ]
    decided.refresh_from_db()
    with pytest.raises(AgentDomainError, match="workspace administrator"):
        decide_hr_proposal(
            decided,
            human_reviewer=create_user,
            approved=True,
            idempotency_key="idempotency:replay-hr-decision",
        )
    assert (decided.state, decided.reviewed_by_id, decided.decision_idempotency_key) == hr_state_before


@pytest.mark.django_db
def test_chief_of_staff_uses_human_gate_and_copies_only_live_membership(workspace, create_user):
    hr = _actor(workspace, name="HR", role=AgentRole.HR, created_by=create_user)
    proposal = propose_chief_of_staff(
        workspace=workspace,
        human=create_user,
        proposed_by=hr,
        rationale="Provision a scoped chief of staff.",
        idempotency_key="idempotency:chief-of-staff",
        created_by=create_user,
    )
    assert not AgentHRProposal.objects.filter(applied_actor__isnull=False).exists()
    applied = decide_hr_proposal(
        proposal,
        human_reviewer=create_user,
        approved=True,
        idempotency_key="idempotency:chief-of-staff-decision",
    )
    assert applied.state == HRProposalState.APPROVED
    chief = applied.applied_actor
    assert chief.chief_of_staff_for_id == create_user.id
    assert chief.active_profile.role == AgentRole.CHIEF_OF_STAFF
    assert chief.principal.is_bot is True
    assert chief.principal.is_superuser is False


@pytest.mark.django_db
def test_evaluator_review_precedes_human_acceptance_and_revision(workspace, project, create_user):
    producer = _actor(workspace, name="Producer", role=AgentRole.WORKER, project=project, created_by=create_user)
    evaluator = _actor(workspace, name="Evaluator", role=AgentRole.EVALUATOR, created_by=create_user)
    assignment = create_assignment(
        producer,
        project=project,
        target_ref="issue:review",
        objective="Produce a reviewable result.",
        acceptance_criteria=["The evidence is durable."],
        created_by=create_user,
    )
    run = create_run(assignment, producer.active_profile, created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:evaluator-invocation")
    outcome = propose_outcome(
        run,
        summary="A reviewable result.",
        artifacts=["artifact:review"],
        evidence=["evidence:review"],
        idempotency_key="idempotency:evaluator-outcome",
        created_by=create_user,
    )
    with pytest.raises(InvalidTransitionError, match="evaluator review"):
        accept_outcome(outcome, human_reviewer=create_user)

    create_profile(producer, role=AgentRole.EVALUATOR, instructions="A producer must never evaluate itself.")
    with pytest.raises(AgentDomainError, match="Independent"):
        review_outcome(
            outcome,
            evaluator=producer,
            idempotency_key="idempotency:self-evaluation",
        )

    review = review_outcome(
        outcome,
        evaluator=evaluator,
        criteria=[{"criterion": "evidence", "result": "present"}],
        verdict=EvaluatorVerdict.REVISION_REQUESTED,
        provenance={"source": "assignment-review"},
        idempotency_key="idempotency:evaluator-review",
    )
    assert review.state == OutcomeState.EVALUATOR_REVIEWED
    durable_review = EvaluatorReview.objects.get(outcome=outcome)
    assert durable_review.evaluator_id == evaluator.id
    assert durable_review.provenance["source"] == "assignment-review"
    assert durable_review.provenance["evaluatorActorRef"].startswith("agent-actor:")
    revised = request_revision(outcome, human_reviewer=create_user, decision_note="Please add evidence.")
    assert revised.state == OutcomeState.REVISION_REQUESTED
    assignment.refresh_from_db()
    assert assignment.state == AssignmentState.REVISION
    assert invocation.terminal_event.kind


@pytest.mark.django_db
def test_evaluator_review_replay_rejects_different_reviewer_command(workspace, project, create_user):
    producer = _actor(workspace, name="Replay producer", role=AgentRole.WORKER, project=project, created_by=create_user)
    evaluator_one = _actor(workspace, name="Replay evaluator one", role=AgentRole.EVALUATOR, created_by=create_user)
    evaluator_two = _actor(workspace, name="Replay evaluator two", role=AgentRole.EVALUATOR, created_by=create_user)
    assignment = create_assignment(
        producer,
        project=project,
        target_ref="issue:evaluator-replay",
        objective="Produce one outcome with one immutable evaluator review.",
        acceptance_criteria=["The evaluator command is replay-safe."],
        created_by=create_user,
    )
    run = create_run(assignment, producer.active_profile, created_by=create_user)
    record_invocation(run, idempotency_key="idempotency:evaluator-replay-invocation")
    outcome = propose_outcome(
        run,
        summary="The evaluator replay outcome.",
        idempotency_key="idempotency:evaluator-replay-outcome",
        created_by=create_user,
    )
    review_args = {
        "criteria": [{"criterion": "evidence", "result": "present"}],
        "verdict": EvaluatorVerdict.ACCEPT,
        "provenance": {"source": "replay-test"},
        "idempotency_key": "idempotency:evaluator-replay-review",
    }
    first = review_outcome(outcome, evaluator=evaluator_one, **review_args)
    replay = review_outcome(outcome, evaluator=evaluator_one, **review_args)
    assert replay.id == first.id

    with pytest.raises(IdempotencyConflictError, match="another Plane command"):
        review_outcome(outcome, evaluator=evaluator_two, **review_args)
    durable_review = EvaluatorReview.objects.get(outcome=outcome)
    assert durable_review.evaluator_id == evaluator_one.id


@pytest.mark.django_db
def test_governance_operations_are_catalogued_and_recheck_actor_binding(workspace, create_user):
    expected = {
        "agent.assignment.delegate",
        "agent.assignment.cancel",
        "agent.hr.propose",
        "agent.hr.decide",
        "agent.outcome.evaluate",
        "agent.outcome.accept",
        "agent.outcome.request_revision",
    }
    assert all(get_operation(operation_id) is not None for operation_id in expected)
    hr = _actor(workspace, name="HR", role=AgentRole.HR, created_by=create_user)
    request = SimpleNamespace(user=hr.principal, agent_actor_ref=f"agent-actor:{hr.id}")
    operation = AgentGovernanceOperation("agent.hr.propose")
    assert operation.authorize(request, workspace, {"proposer_ref": f"agent-actor:{hr.id}"}) is True
    envelope = {
        "schema_version": "plane.operation/v1",
        "operation_id": "agent.hr.propose",
        "workspace_slug": workspace.slug,
        "idempotency_key": "gateway-hr-proposal",
        "correlation_id": "gateway-hr-correlation",
        "input": {
            "proposer_ref": f"agent-actor:{hr.id}",
            "kind": HRProposalKind.HIRE,
            "rationale": "Record a human-gated hire proposal.",
        },
    }
    response, status = OperationGateway().execute(request, envelope)
    assert status == 200, response
    assert response["ok"] is True
    assert OperationGatewayAudit.objects.filter(
        operation_id="agent.hr.propose", outcome=OperationGatewayAudit.Outcome.SUCCESS
    ).exists()
    request.agent_actor_ref = f"agent-actor:{create_user.id}"
    assert operation.authorize(request, workspace, {"proposer_ref": f"agent-actor:{hr.id}"}) is False
    with pytest.raises(OperationAdapterFailure, match="CALLBACK_BINDING_INVALID"):
        operation.execute(
            request,
            workspace,
            {
                "proposer_ref": f"agent-actor:{hr.id}",
                "kind": HRProposalKind.HIRE,
                "rationale": "Should fail closed.",
                "_gateway_idempotency_key": "gateway-test",
            },
        )

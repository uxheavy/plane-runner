from types import SimpleNamespace

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
)
from plane.agent.lifecycle import InvalidTransitionError
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
    Workspace,
    AssignmentContract,
)
from plane.operation_gateway.catalog import get_operation
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.operations import AgentGovernanceOperation, OperationAdapterFailure


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
            acceptance_criteria=["Denied."],
            idempotency_key="idempotency:delegation-depth",
            delegated_by=worker,
        )


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

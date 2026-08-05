"""Backend-only evidence for the Plane Agent administration contract."""

import json
import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    AgentActor,
    AgentRole,
    AssignmentContract,
    AssignmentState,
    Issue,
    OutcomeState,
    ProfileVersion,
    Project,
    ProjectMember,
    RunAttempt,
    RunState,
    RuntimeInvocation,
    State,
    User,
    WorkspaceMember,
)


def _admin_url(workspace, suffix):
    return f"/api/v1/workspaces/{workspace.slug}/agent-admin/{suffix}"


def _actor(client, workspace, display_name, *, credential_ref="credential:agent-admin"):
    data = {"display_name": display_name}
    if credential_ref is not None:
        data["credential_ref"] = credential_ref
    response = client.post(
        _admin_url(workspace, "actors/"),
        data,
        format="json",
    )
    assert response.status_code == 201
    return response


@pytest.fixture
def agent_admin_gateway_project(workspace, create_user):
    project = Project.objects.create(
        name="Agent Admin Gateway Project",
        identifier="AAG",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=project,
        workspace=workspace,
        created_by=create_user,
    )
    return project


@pytest.fixture
def agent_admin_gateway_issue(agent_admin_gateway_project, workspace, create_user):
    return Issue.objects.create(
        name="Agent Admin Gateway Issue",
        project=agent_admin_gateway_project,
        workspace=workspace,
        created_by=create_user,
    )


@pytest.mark.contract
@pytest.mark.django_db
def test_admin_api_proves_lifecycle_review_and_redaction(api_key_client, workspace):
    actor_response = _actor(api_key_client, workspace, "Admin worker")
    actor = actor_response.json()
    assert actor["credential_configured"] is True
    assert "credential:agent-admin" not in json.dumps(actor_response.json())

    profile_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor['id']}/profiles/"),
        {"role": AgentRole.WORKER, "instructions": "Complete assigned Plane work."},
        format="json",
    )
    assert profile_response.status_code == 201

    assignment_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor['id']}/assignments/"),
        {
            "target_ref": "issue:admin-readback",
            "objective": "Produce a reviewable result.",
            "acceptance_criteria": ["A human can accept the result."],
        },
        format="json",
    )
    assert assignment_response.status_code == 201
    assignment_id = assignment_response.json()["id"]

    dispatch_response = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:admin-dispatch"},
        format="json",
    )
    assert dispatch_response.status_code == 201
    run_id = dispatch_response.json()["run"]["id"]
    invocation_id = dispatch_response.json()["invocation"]["id"]

    outcome_response = api_key_client.post(
        _admin_url(workspace, f"runs/{run_id}/outcome/"),
        {
            "summary": "The result is ready.",
            "artifacts": [{"artifact_ref": "artifact:admin"}],
            "evidence": [{"evidence_ref": "evidence:admin"}],
            "idempotency_key": "idempotency:admin-outcome",
        },
        format="json",
    )
    assert outcome_response.status_code == 201
    outcome_id = outcome_response.json()["id"]

    evaluator_response = _actor(api_key_client, workspace, "Admin evaluator", credential_ref=None)
    evaluator_id = evaluator_response.json()["id"]
    evaluator_profile_response = api_key_client.post(
        _admin_url(workspace, f"actors/{evaluator_id}/profiles/"),
        {"role": AgentRole.EVALUATOR, "instructions": "Review outcomes."},
        format="json",
    )
    assert evaluator_profile_response.status_code == 201

    review_response = api_key_client.post(
        _admin_url(workspace, f"outcomes/{outcome_id}/review/"),
        {"evaluator_id": evaluator_id, "feedback": "Evidence checked."},
        format="json",
    )
    assert review_response.status_code == 200
    accept_response = api_key_client.post(
        _admin_url(workspace, f"outcomes/{outcome_id}/accept/"),
        {"decision_note": "Accepted by the workspace administrator."},
        format="json",
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["state"] == OutcomeState.ACCEPTED

    run_response = api_key_client.get(_admin_url(workspace, f"runs/{run_id}/"))
    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["run"]["id"] == run_id
    assert run_body["outcome"]["state"] == OutcomeState.ACCEPTED
    assert run_body["invocations"][0]["id"] == invocation_id
    assert "raw_payload" not in json.dumps(run_body)
    assert "envelope" not in json.dumps(run_body)

    assignment = AssignmentContract.objects.get(pk=assignment_id)
    assert assignment.state == AssignmentState.COMPLETED
    assert RunAttempt.objects.get(pk=run_id).profile_version_id == profile_response.json()["id"]


@pytest.mark.contract
@pytest.mark.django_db
def test_admin_api_is_idempotent_paged_and_denies_without_side_effect(api_key_client, workspace):
    actor_response = _actor(api_key_client, workspace, "Idempotent worker")
    actor_id = actor_response.json()["id"]
    api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/profiles/"),
        {"role": AgentRole.WORKER, "instructions": "Run once."},
        format="json",
    )
    assignment_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/assignments/"),
        {"target_ref": "issue:idempotent", "objective": "Run once."},
        format="json",
    )
    assignment_id = assignment_response.json()["id"]
    first = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:repeatable-dispatch"},
        format="json",
    )
    second = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:repeatable-dispatch"},
        format="json",
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    assert first.json()["invocation"]["id"] == second.json()["invocation"]["id"]
    assert RuntimeInvocation.objects.filter(run_id=first.json()["run"]["id"]).count() == 1

    page = api_key_client.get(_admin_url(workspace, "actors/?per_page=1"))
    assert page.status_code == 200
    assert page.json()["count"] == 1
    assert page.json()["next_cursor"]

    denied_user = User.objects.create(email=f"denied-{uuid.uuid4().hex}@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=denied_user, role=15)
    denied_token = APIToken.objects.create(user=denied_user, label="denied", token=f"denied-{uuid.uuid4().hex}")
    denied_client = APIClient()
    denied_client.credentials(HTTP_X_API_KEY=denied_token.token)
    before = AgentActor.objects.filter(workspace=workspace).count()
    denied = denied_client.post(
        _admin_url(workspace, "actors/"),
        {"display_name": "Must not exist", "credential_ref": "credential:denied"},
        format="json",
    )
    assert denied.status_code == 403
    assert AgentActor.objects.filter(workspace=workspace).count() == before


@pytest.mark.contract
@pytest.mark.django_db
def test_agent_admin_command_is_a_redacted_convergent_fixture(workspace, capsys):
    call_command(
        "agent_admin",
        workspace_slug=workspace.slug,
        display_name="Fixture worker",
        role=AgentRole.WORKER,
        instructions="Use the fixture.",
        credential_ref="credential:fixture",
    )
    first_output = capsys.readouterr().out
    call_command(
        "agent_admin",
        workspace_slug=workspace.slug,
        display_name="Fixture worker",
        role=AgentRole.WORKER,
        instructions="Use the fixture.",
        credential_ref="credential:fixture",
    )
    second_output = capsys.readouterr().out
    assert "credential:fixture" not in first_output + second_output
    assert AgentActor.objects.filter(workspace=workspace, display_name="Fixture worker").count() == 1
    assert ProfileVersion.objects.filter(actor__display_name="Fixture worker").count() == 1


@pytest.mark.contract
@pytest.mark.django_db
def test_admin_api_exposes_revision_cancel_and_gateway_readback(
    api_key_client,
    workspace,
    agent_admin_gateway_project,
    agent_admin_gateway_issue,
):
    actor_response = _actor(api_key_client, workspace, "Revision worker")
    actor_id = actor_response.json()["id"]
    profile_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/profiles/"),
        {"role": AgentRole.WORKER, "instructions": "Revise when requested."},
        format="json",
    )
    assert profile_response.status_code == 201
    assignment_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/assignments/"),
        {"target_ref": "issue:revision", "objective": "Produce a revisable result."},
        format="json",
    )
    assignment_id = assignment_response.json()["id"]
    first_run_response = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:revision-first"},
        format="json",
    )
    first_run_id = first_run_response.json()["run"]["id"]
    outcome_response = api_key_client.post(
        _admin_url(workspace, f"runs/{first_run_id}/outcome/"),
        {"summary": "Initial result", "idempotency_key": "idempotency:revision-outcome"},
        format="json",
    )
    evaluator_response = _actor(api_key_client, workspace, "Revision evaluator", credential_ref=None)
    evaluator_id = evaluator_response.json()["id"]
    api_key_client.post(
        _admin_url(workspace, f"actors/{evaluator_id}/profiles/"),
        {"role": AgentRole.EVALUATOR, "instructions": "Evaluate revisions."},
        format="json",
    )
    review_response = api_key_client.post(
        _admin_url(workspace, f"outcomes/{outcome_response.json()['id']}/review/"),
        {"evaluator_id": evaluator_id, "feedback": "Please revise."},
        format="json",
    )
    assert review_response.status_code == 200
    revision_response = api_key_client.post(
        _admin_url(workspace, f"outcomes/{outcome_response.json()['id']}/revise/"),
        {"decision_note": "Human requested a revision."},
        format="json",
    )
    assert revision_response.status_code == 200
    assert revision_response.json()["state"] == OutcomeState.REVISION_REQUESTED
    assert AssignmentContract.objects.get(pk=assignment_id).state == AssignmentState.REVISION

    second_run_response = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {
            "idempotency_key": "idempotency:revision-second",
            "lineage_of_id": first_run_id,
            "lineage_reason": "human_revision",
        },
        format="json",
    )
    assert second_run_response.status_code == 201
    second_run = second_run_response.json()["run"]
    assert second_run["lineage_of_id"] == first_run_id
    cancel_response = api_key_client.post(
        _admin_url(workspace, f"runs/{second_run['id']}/cancel/"),
        {"reason": "Cancelled after revision review.", "idempotency_key": "idempotency:cancel"},
        format="json",
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["state"] == RunState.CANCELLED

    gateway_response = api_key_client.post(
        "/api/v1/operations/",
        {
            "schema_version": "plane.operation/v1",
            "operation_id": "work_item.read",
            "workspace_slug": workspace.slug,
            "idempotency_key": "idempotency:admin-readback",
            "correlation_id": "correlation:admin-readback",
            "input": {
                "project_id": str(agent_admin_gateway_project.id),
                "issue_id": str(agent_admin_gateway_issue.id),
            },
            "tool_exposure": {"operations": ["work_item.read"]},
        },
        format="json",
    )
    assert gateway_response.status_code == 200
    readback_response = api_key_client.get(
        _admin_url(workspace, "gateway/readback/?operation_id=work_item.read&per_page=1")
    )
    assert readback_response.status_code == 200
    readback = readback_response.json()["results"][0]
    readback_json = json.dumps(readback)
    assert readback["receipt"]["idempotency_key"] == "idempotency:admin-readback"
    assert "request_input" not in readback_json
    assert "result" not in readback_json
    assert "error" not in readback_json

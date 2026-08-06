"""Backend-only evidence for the Plane Agent administration contract."""

import json
import uuid

import pytest
from django.core.management import call_command
from django.utils import timezone
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
from plane.agent.runtime.host_rpc import trusted_host_request
from plane.operation_gateway.gateway import OperationGateway


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
def test_admin_api_proves_lifecycle_review_and_redaction(api_key_client, workspace, capsys):
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
    assert set(run_body) >= {
        "actor",
        "profile",
        "assignment",
        "run",
        "invocations",
        "outcome",
        "terminal_events",
        "gateway_readback",
    }
    assert run_body["run"]["id"] == run_id
    assert run_body["outcome"]["state"] == OutcomeState.ACCEPTED
    assert run_body["invocations"][0]["id"] == invocation_id
    run_json = json.dumps(run_body, sort_keys=True)
    assert "control" not in run_body["invocations"][0]
    assert "socket" not in run_json.casefold()
    assert "raw_payload" not in run_json
    assert "envelope" not in run_json
    assert "original_sequence" not in run_json

    assignment = AssignmentContract.objects.get(pk=assignment_id)
    assert assignment.state == AssignmentState.COMPLETED
    assert str(RunAttempt.objects.get(pk=run_id).profile_version_id) == profile_response.json()["id"]

    call_command("agent_readback", workspace_slug=workspace.slug, run_id=run_id, limit=1)
    readback = json.loads(capsys.readouterr().out)
    assert set(readback) >= {
        "actor",
        "profile",
        "assignment",
        "run",
        "invocations",
        "outcome",
        "terminal_events",
        "gateway_readback",
    }
    assert "credential:agent-admin" not in json.dumps(readback)


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
        {
            "target_ref": "issue:idempotent",
            "objective": "Run once.",
            "acceptance_criteria": ["The result is reviewable."],
        },
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
        {
            "target_ref": "issue:revision",
            "objective": "Produce a revisable result.",
            "acceptance_criteria": ["The result is reviewable."],
        },
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
    assert '"request_input":' not in readback_json
    assert '"result":' not in readback_json
    assert '"error":' not in readback_json


@pytest.mark.contract
@pytest.mark.django_db
def test_run_readback_returns_only_run_correlated_gateway_receipts_and_matches_cli(
    api_key_client,
    workspace,
    agent_admin_gateway_project,
    agent_admin_gateway_issue,
    capsys,
):
    actor_response = _actor(api_key_client, workspace, "Correlated worker")
    actor_id = actor_response.json()["id"]
    actor = AgentActor.objects.select_related("principal").get(pk=actor_id)
    ProjectMember.objects.create(project=agent_admin_gateway_project, member=actor.principal, role=15, is_active=True)
    assert (
        api_key_client.post(
            _admin_url(workspace, f"actors/{actor_id}/profiles/"),
            {"role": AgentRole.WORKER, "instructions": "Read correlated work."},
            format="json",
        ).status_code
        == 201
    )
    assignment_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/assignments/"),
        {
            "target_ref": "issue:correlation",
            "objective": "Read only the current run's receipts.",
            "acceptance_criteria": ["No receipt from another run is returned."],
        },
        format="json",
    )
    assignment_id = assignment_response.json()["id"]
    first_dispatch = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:correlation-first"},
        format="json",
    )
    second_dispatch = api_key_client.post(
        _admin_url(workspace, f"assignments/{assignment_id}/dispatch/"),
        {"idempotency_key": "idempotency:correlation-second"},
        format="json",
    )
    assert first_dispatch.status_code == second_dispatch.status_code == 201
    first_run_id = first_dispatch.json()["run"]["id"]
    second_run_id = second_dispatch.json()["run"]["id"]

    for dispatch, run_id, label in (
        (first_dispatch, first_run_id, "first"),
        (second_dispatch, second_run_id, "second"),
    ):
        invocation = RuntimeInvocation.objects.get(pk=dispatch.json()["invocation"]["id"])
        response, response_status = OperationGateway().execute(
            trusted_host_request(invocation),
            {
                "schema_version": "plane.operation/v1",
                "operation_id": "work_item.read",
                "workspace_slug": workspace.slug,
                "idempotency_key": f"idempotency:correlation-{label}",
                "correlation_id": f"correlation:{run_id}",
                "input": {
                    "project_id": str(agent_admin_gateway_project.id),
                    "issue_id": str(agent_admin_gateway_issue.id),
                },
            },
        )
        assert response_status == 200
        assert response["correlation_id"] == f"correlation:{run_id}"

    first_body = api_key_client.get(_admin_url(workspace, f"runs/{first_run_id}/?per_page=1"))
    second_body = api_key_client.get(_admin_url(workspace, f"runs/{second_run_id}/?per_page=1"))
    assert first_body.status_code == second_body.status_code == 200
    first_readback = first_body.json()
    second_readback = second_body.json()
    assert [row["receipt"]["idempotency_key"] for row in first_readback["gateway_readback"]] == [
        "idempotency:correlation-first"
    ]
    assert [row["receipt"]["idempotency_key"] for row in second_readback["gateway_readback"]] == [
        "idempotency:correlation-second"
    ]
    for row, run_id in (
        (first_readback["gateway_readback"][0], first_run_id),
        (second_readback["gateway_readback"][0], second_run_id),
    ):
        assert row["receipt"]["correlation_id"] == f"correlation:{run_id}"
        assert all(item["correlation_id"] == f"correlation:{run_id}" for item in row["audit"])

    first_json = json.dumps(first_readback, sort_keys=True)
    assert len(first_json.encode("utf-8")) <= 8 * 1024
    assert "control" not in first_json
    assert "socket" not in first_json.casefold()

    call_command("agent_readback", workspace_slug=workspace.slug, run_id=first_run_id, limit=1)
    cli_readback = json.loads(capsys.readouterr().out)
    assert cli_readback == first_readback


@pytest.mark.contract
@pytest.mark.django_db
def test_context_admin_reuses_governance_services_and_api_cli_projection(api_key_client, workspace, capsys):
    actor_response = _actor(api_key_client, workspace, "Context worker", credential_ref=None)
    actor_id = actor_response.json()["id"]

    memory_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/memory/"),
        {"key": "operating-preference", "content": "Prefer bounded readback."},
        format="json",
    )
    assert memory_response.status_code == 201
    memory_id = memory_response.json()["id"]
    assert memory_response.json()["active_revision"]["state"] == "active"
    assert (
        api_key_client.get(_admin_url(workspace, f"actors/{actor_id}/memory/{memory_id}/revisions/")).status_code == 200
    )

    skill_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/skills/"),
        {"key": "bounded-readback", "package_files": {"SKILL.md": "Keep evidence bounded."}},
        format="json",
    )
    assert skill_response.status_code == 201
    skill_id = skill_response.json()["id"]
    assert (
        api_key_client.get(_admin_url(workspace, f"actors/{actor_id}/skills/{skill_id}/revisions/")).status_code == 200
    )

    schedule_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/schedules/"),
        {
            "name": "Readback schedule",
            "cron_expression": "* * * * *",
            "target_ref": "issue:scheduled-readback",
            "objective": "Run bounded scheduled work.",
            "starts_at": timezone.now().isoformat(),
        },
        format="json",
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    fire_response = api_key_client.post(
        _admin_url(workspace, f"schedules/{schedule_id}/fires/"),
        {
            "scheduled_for": schedule_response.json()["next_fire_at"],
            "idempotency_key": "idempotency:scheduled-readback",
        },
        format="json",
    )
    assert fire_response.status_code == 201
    replay_response = api_key_client.post(
        _admin_url(workspace, f"schedules/{schedule_id}/fires/"),
        {
            "scheduled_for": schedule_response.json()["next_fire_at"],
            "idempotency_key": "idempotency:scheduled-readback",
        },
        format="json",
    )
    assert replay_response.status_code == 201
    assert replay_response.json()["id"] == fire_response.json()["id"]

    status_response = api_key_client.get(_admin_url(workspace, "gateway/status/"))
    catalog_response = api_key_client.get(_admin_url(workspace, "gateway/catalog/?limit=1"))
    assert status_response.status_code == catalog_response.status_code == 200
    assert status_response.json()["external_adapter_registry"]["tool_count"] == 177
    assert status_response.json()["external_adapter_registry"]["disposition"] == {
        "gateway": 64,
        "blocked": 112,
        "local": 1,
    }
    assert len(json.dumps(catalog_response.json()).encode()) <= 8 * 1024

    context_response = api_key_client.get(_admin_url(workspace, f"actors/{actor_id}/context/?per_page=1"))
    assert context_response.status_code == 200
    call_command("agent_context_readback", workspace_slug=workspace.slug, actor_id=actor_id, limit=1)
    assert json.loads(capsys.readouterr().out) == context_response.json()

"""Backend-only evidence for the Plane Agent administration contract."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.cache import cache
from django.utils import timezone as django_timezone
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    AgentActor,
    AgentRole,
    AgentScheduleFireState,
    AssignmentContract,
    AssignmentState,
    InputEventKind,
    Issue,
    OutcomeState,
    ProfileVersion,
    Project,
    ProjectMember,
    RunAttempt,
    RunState,
    RuntimeInvocation,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
    State,
    User,
    WorkspaceMember,
)
from plane.agent.lifecycle import (
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    delegate_assignment,
    propose_outcome,
    record_input_event,
    record_invocation,
    record_provider_attempt_notice,
    transition_run,
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
            "plan_rationale": "The manager isolated this assignment for durable acceptance evidence.",
            "acceptance_criteria": ["A human can accept the result."],
        },
        format="json",
    )
    assert assignment_response.status_code == 201
    assignment_id = assignment_response.json()["id"]
    assert assignment_response.json()["plan_rationale"].startswith("The manager isolated")

    governance_response = api_key_client.get(
        _admin_url(workspace, f"governance/?resource_id=assignment:{assignment_id}&limit=1")
    )
    assert governance_response.status_code == 200
    assert governance_response.json()["assignments"][0]["plan_rationale"].startswith("The manager isolated")

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
def test_schedule_api_control_and_due_fire_cli_are_real_lifecycle_paths(api_key_client, workspace, capsys):
    actor_response = _actor(api_key_client, workspace, "Scheduled worker")
    actor_id = actor_response.json()["id"]
    schedule_response = api_key_client.post(
        _admin_url(workspace, f"actors/{actor_id}/schedules/"),
        {
            "name": "Due schedule",
            "cron_expression": "*/5 * * * *",
            "timezone_name": "UTC",
            "target_ref": "issue:scheduled",
            "objective": "Create one normal scheduled assignment.",
            "starts_at": "2026-08-05T15:00:00Z",
        },
        format="json",
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    paused_response = api_key_client.post(
        _admin_url(workspace, f"schedules/{schedule_id}/control/"),
        {"state": "paused"},
        format="json",
    )
    assert paused_response.status_code == 200
    assert paused_response.json()["state"] == "paused"
    assert (
        api_key_client.post(
            _admin_url(workspace, f"schedules/{schedule_id}/control/"),
            {"state": "paused"},
            format="json",
        ).json()["state"]
        == "paused"
    )

    resumed_response = api_key_client.post(
        _admin_url(workspace, f"schedules/{schedule_id}/control/"),
        {"state": "enabled"},
        format="json",
    )
    assert resumed_response.status_code == 200

    call_command(
        "agent_schedule_fire_due",
        workspace_slug=workspace.slug,
        now=datetime(2026, 8, 5, 15, 6, tzinfo=timezone.utc).isoformat(),
    )
    fire_output = json.loads(capsys.readouterr().out)
    assert len(fire_output["fires"]) == 1
    assert fire_output["fires"][0]["state"] == AgentScheduleFireState.CREATED


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_run_api_and_cli_readbacks_fail_closed_on_cross_invocation_provider_evidence(
    api_key_client,
    workspace,
    create_user,
    agent_admin_gateway_project,
    capsys,
):
    actor = create_actor(
        workspace=workspace,
        project=agent_admin_gateway_project,
        display_name="Readback integrity worker",
        created_by=create_user,
    )
    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Produce bounded evidence.")
    first_assignment = create_assignment(
        actor,
        project=agent_admin_gateway_project,
        target_ref="issue:readback-a",
        objective="Record invocation A.",
        acceptance_criteria=["Invocation A is structurally bound."],
        created_by=create_user,
    )
    first_run = create_run(
        first_assignment,
        profile,
        idempotency_key="idempotency:readback-run-a",
        created_by=create_user,
    )
    first_invocation = record_invocation(first_run, idempotency_key="idempotency:readback-invocation-a")
    attempt = record_provider_attempt_notice(
        first_invocation,
        {
            "phase": RuntimeProviderAttemptPhase.INTENT,
            "runId": str(first_run.id),
            "invocationId": first_invocation.invocation_id,
            "leaseId": "lease:readback-a",
            "provider": "fixture-provider",
            "model": "fixture-model",
            "destinationHost": "provider.invalid",
            "destinationPath": "/v1/chat/completions",
            "requestId": "request:readback-a",
            "idempotencyKey": "idempotency:provider-readback-a",
            "sequence": 1,
            "upstreamInitiated": False,
            "statusClass": "",
            "errorCode": "",
        },
    )
    transition_run(first_run, RunState.WAITING_FOR_INPUT, pending_input_ref="event:readback-question")
    input_event = record_input_event(
        first_run,
        payload={"answer": "Continue"},
        kind=InputEventKind.HUMAN_INPUT,
        pending_input_ref="event:readback-question",
        idempotency_key="idempotency:readback-answer",
    )
    second_invocation = record_invocation(
        first_run,
        trigger="human_input",
        input_event=input_event,
        idempotency_key="idempotency:readback-invocation-b",
    )

    # QuerySet.update is the intended storage-bypass corruption simulation.
    RuntimeProviderAttempt.objects.filter(pk=attempt.pk).update(invocation_id=second_invocation.id)

    response = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/agent-admin/runs/{first_run.id}/")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "READBACK_INTEGRITY_FAILURE",
            "message": "Run evidence failed integrity checks.",
        }
    }

    with pytest.raises(CommandError, match="provider attempt ownership or fingerprint is invalid"):
        call_command("agent_readback", workspace_slug=workspace.slug, run_id=str(first_run.id), limit=1)
    assert capsys.readouterr().out == ""


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_run_api_and_cli_readbacks_preserve_bounded_provider_reason_subreason(
    api_key_client,
    workspace,
    create_user,
    agent_admin_gateway_project,
    capsys,
):
    actor = create_actor(
        workspace=workspace,
        project=agent_admin_gateway_project,
        display_name="Provider reason worker",
        created_by=create_user,
    )
    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Produce bounded provider evidence.")
    assignment = create_assignment(
        actor,
        project=agent_admin_gateway_project,
        target_ref="issue:provider-reason",
        objective="Record a safe provider rejection family.",
        acceptance_criteria=["Only an allowlisted provider reason is readable."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:provider-reason-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:provider-reason-invocation")
    notice = {
        "phase": RuntimeProviderAttemptPhase.INTENT,
        "runId": str(run.id),
        "invocationId": invocation.invocation_id,
        "leaseId": "lease:provider-reason",
        "provider": "fixture-provider",
        "model": "fixture-model",
        "destinationHost": "provider.invalid",
        "destinationPath": "/v1/chat/completions",
        "requestId": "request:provider-reason",
        "idempotencyKey": "idempotency:provider-reason-attempt",
        "sequence": 1,
        "upstreamInitiated": False,
        "statusClass": "",
        "errorCode": "",
    }
    record_provider_attempt_notice(invocation, notice)
    record_provider_attempt_notice(
        invocation,
        {
            **notice,
            "phase": RuntimeProviderAttemptPhase.STARTED,
            "upstreamInitiated": True,
        },
    )
    record_provider_attempt_notice(
        invocation,
        {
            **notice,
            "phase": RuntimeProviderAttemptPhase.FAILED,
            "upstreamInitiated": True,
            "statusClass": "4xx",
            "errorCode": "provider_error",
            "reasonPhase": "provider_relay",
            "reasonSubreason": "auth",
        },
    )

    api_response = api_key_client.get(_admin_url(workspace, f"runs/{run.id}/"))
    assert api_response.status_code == 200
    api_readback = api_response.json()
    assert api_readback["provider_attempts"][-1]["error_code"] == "provider_error"
    assert api_readback["provider_attempts"][-1]["reason_subreason"] == "auth"

    call_command("agent_readback", workspace_slug=workspace.slug, run_id=str(run.id), limit=1)
    cli_readback = json.loads(capsys.readouterr().out)
    assert cli_readback == api_readback
    assert "provider-code" not in json.dumps(cli_readback)


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
    cache.clear()
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
            "starts_at": django_timezone.now().isoformat(),
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
        "gateway": 86,
        "blocked": 90,
        "unsupported": 90,
        "local": 1,
    }
    assert len(json.dumps(catalog_response.json()).encode()) <= 8 * 1024

    context_response = api_key_client.get(_admin_url(workspace, f"actors/{actor_id}/context/?per_page=1"))
    assert context_response.status_code == 200
    call_command("agent_context_readback", workspace_slug=workspace.slug, actor_id=actor_id, limit=1)
    assert json.loads(capsys.readouterr().out) == context_response.json()


@pytest.mark.contract
@pytest.mark.django_db
def test_governance_extension_api_cli_parity_and_l7_state_adapters(api_key_client, workspace, capsys):
    cache.clear()
    worker_response = _actor(api_key_client, workspace, "Governance worker")
    worker_id = worker_response.json()["id"]
    assert (
        api_key_client.post(
            _admin_url(workspace, f"actors/{worker_id}/profiles/"),
            {"role": AgentRole.WORKER, "instructions": "Produce bounded governance evidence."},
            format="json",
        ).status_code
        == 201
    )
    assignment_response = api_key_client.post(
        _admin_url(workspace, f"actors/{worker_id}/assignments/"),
        {
            "target_ref": "issue:governance-outcome",
            "objective": "Produce one reviewable outcome.",
            "acceptance_criteria": ["The outcome has an independent review."],
        },
        format="json",
    )
    assert assignment_response.status_code == 201
    assignment_id = assignment_response.json()["id"]
    assignment = AssignmentContract.objects.get(pk=assignment_id)
    profile = ProfileVersion.objects.get(actor_id=worker_id, version=1)
    run = create_run(
        assignment,
        profile,
        idempotency_key="idempotency:governance-dispatch",
        created_by=workspace.owner,
    )
    invocation = record_invocation(
        run,
        idempotency_key="idempotency:governance-invocation",
        created_by=workspace.owner,
    )
    outcome = propose_outcome(
        run,
        summary="Governance outcome",
        idempotency_key="idempotency:governance-outcome",
        created_by=workspace.owner,
    )
    run_id = str(run.id)
    outcome_id = str(outcome.id)

    evaluator_response = _actor(api_key_client, workspace, "Governance evaluator", credential_ref=None)
    evaluator_id = evaluator_response.json()["id"]
    assert (
        api_key_client.post(
            _admin_url(workspace, f"actors/{evaluator_id}/profiles/"),
            {"role": AgentRole.EVALUATOR, "instructions": "Review governance outcomes."},
            format="json",
        ).status_code
        == 201
    )
    hr_response = _actor(api_key_client, workspace, "Governance HR", credential_ref=None)
    hr_id = hr_response.json()["id"]
    assert (
        api_key_client.post(
            _admin_url(workspace, f"actors/{hr_id}/profiles/"),
            {"role": AgentRole.HR, "instructions": "Propose bounded HR changes."},
            format="json",
        ).status_code
        == 201
    )

    command_url = _admin_url(workspace, "governance/commands/")
    mismatched_review = api_key_client.post(
        command_url,
        {
            "action": "evaluator.review",
            "actor_id": worker_id,
            "run_id": run_id,
            "idempotency_key": "idempotency:governance-mismatched-review",
            "payload": {"outcome_id": outcome_id, "evaluator_id": evaluator_id},
        },
        format="json",
    )
    assert mismatched_review.status_code == 400
    outcome.refresh_from_db()
    assert outcome.state == OutcomeState.PROPOSED
    review_response = api_key_client.post(
        command_url,
        {
            "action": "evaluator.review",
            "actor_id": evaluator_id,
            "run_id": run_id,
            "invocation_id": invocation.invocation_id,
            "idempotency_key": "idempotency:governance-review",
            "payload": {
                "outcome_id": outcome_id,
                "evaluator_id": evaluator_id,
                "feedback": "Independent evidence is present.",
                "criteria": [{"criterion": "evidence", "result": "pass"}],
                "provenance": {"source": "governance-contract-test"},
            },
        },
        format="json",
    )
    assert review_response.status_code == 200, review_response.json()
    assert review_response.json()["evaluator_reviews"][0]["outcome_state"] == OutcomeState.EVALUATOR_REVIEWED
    revision_response = api_key_client.post(
        command_url,
        {
            "action": "outcome.request_revision",
            "idempotency_key": "idempotency:governance-revision",
            "payload": {"outcome_id": outcome_id},
        },
        format="json",
    )
    assert revision_response.status_code == 200
    assert revision_response.json()["evaluator_reviews"][0]["outcome_state"] == OutcomeState.REVISION_REQUESTED
    outcome.refresh_from_db()
    assert outcome.human_reviewer_id == workspace.owner_id
    call_command(
        "agent_governance",
        workspace_slug=workspace.slug,
        action="outcome.request_revision",
        operator_id=str(workspace.owner_id),
        idempotency_key="idempotency:governance-revision-cli-replay",
        payload=json.dumps({"outcome_id": outcome_id}),
    )
    assert json.loads(capsys.readouterr().out) == revision_response.json()

    accepted_assignment = create_assignment(
        AgentActor.objects.get(pk=worker_id),
        target_ref="issue:governance-accepted-outcome",
        objective="Produce one accepted outcome.",
        acceptance_criteria=["The accepted outcome is reviewed."],
        created_by=workspace.owner,
    )
    accepted_run = create_run(
        accepted_assignment,
        profile,
        idempotency_key="idempotency:governance-accepted-run",
        created_by=workspace.owner,
    )
    accepted_invocation = record_invocation(
        accepted_run,
        idempotency_key="idempotency:governance-accepted-invocation",
        created_by=workspace.owner,
    )
    accepted_outcome = propose_outcome(
        accepted_run,
        summary="Governance accepted outcome",
        idempotency_key="idempotency:governance-accepted-outcome",
        created_by=workspace.owner,
    )
    accept_response = api_key_client.post(
        command_url,
        {
            "action": "outcome.accept",
            "idempotency_key": "idempotency:governance-accept",
            "payload": {"outcome_id": str(accepted_outcome.id)},
        },
        format="json",
    )
    assert accept_response.status_code == 400
    accepted_review_response = api_key_client.post(
        command_url,
        {
            "action": "evaluator.review",
            "actor_id": evaluator_id,
            "run_id": str(accepted_run.id),
            "invocation_id": accepted_invocation.invocation_id,
            "idempotency_key": "idempotency:governance-accepted-review",
            "payload": {"outcome_id": str(accepted_outcome.id), "evaluator_id": evaluator_id},
        },
        format="json",
    )
    assert accepted_review_response.status_code == 200
    accept_response = api_key_client.post(
        command_url,
        {
            "action": "outcome.accept",
            "idempotency_key": "idempotency:governance-accept",
            "payload": {"outcome_id": str(accepted_outcome.id)},
        },
        format="json",
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["evaluator_reviews"][0]["outcome_state"] == OutcomeState.ACCEPTED
    accepted_outcome.refresh_from_db()
    assert accepted_outcome.human_reviewer_id == workspace.owner_id

    chief_response = api_key_client.post(
        command_url,
        {
            "action": "chief_of_staff.provision",
            "actor_id": hr_id,
            "idempotency_key": "idempotency:governance-chief",
            "payload": {
                "human_id": str(workspace.owner_id),
                "proposed_by_id": hr_id,
                "rationale": "Provision a human-gated chief of staff.",
            },
        },
        format="json",
    )
    assert chief_response.status_code == 200
    proposal_id = chief_response.json()["hr_proposals"][0]["id"]
    spoofed_decision = api_key_client.post(
        command_url,
        {
            "action": "hr.proposal.decide",
            "idempotency_key": "idempotency:governance-chief-spoofed-reviewer",
            "payload": {
                "proposal_id": proposal_id,
                "reviewer_id": "user:spoofed-reviewer",
                "approved": True,
            },
        },
        format="json",
    )
    assert spoofed_decision.status_code == 400
    decision_response = api_key_client.post(
        command_url,
        {
            "action": "hr.proposal.decide",
            "idempotency_key": "idempotency:governance-chief-decision",
            "payload": {
                "proposal_id": proposal_id,
                "approved": True,
                "decision_note": "Approved by the workspace owner.",
            },
        },
        format="json",
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["hr_proposals"][0]["state"] == "approved"

    cancel_worker = create_actor(
        workspace=workspace,
        display_name="Governance cancellation worker",
        created_by=workspace.owner,
    )
    create_profile(
        cancel_worker,
        role=AgentRole.WORKER,
        instructions="Remain bounded during cancellation.",
        created_by=workspace.owner,
    )
    delegator = create_actor(
        workspace=workspace,
        display_name="Governance delegator",
        created_by=workspace.owner,
    )
    create_profile(
        delegator,
        role=AgentRole.DELEGATOR,
        instructions="Delegate bounded cancellation tests.",
        created_by=workspace.owner,
    )
    cancel_worker_id = str(cancel_worker.id)
    delegator_id = str(delegator.id)
    parent_response = api_key_client.post(
        _admin_url(workspace, f"actors/{delegator_id}/assignments/"),
        {
            "target_ref": "issue:governance-cancel",
            "objective": "Cancel a delegated tree.",
            "acceptance_criteria": ["Cancellation propagates."],
        },
        format="json",
    )
    parent = AssignmentContract.objects.get(pk=parent_response.json()["id"])
    child = delegate_assignment(
        parent,
        AgentActor.objects.get(pk=cancel_worker_id),
        target_ref="issue:governance-cancel-child",
        objective="Remain unfinished until cancellation.",
        plan_rationale="The delegator isolated the child so parent cancellation can be observed.",
        acceptance_criteria=["The child is cancelled."],
        idempotency_key="idempotency:governance-child",
    )
    cancel_response = api_key_client.post(
        command_url,
        {
            "action": "assignment.cancel",
            "idempotency_key": "idempotency:governance-cancel",
            "payload": {"assignment_id": str(parent.id)},
        },
        format="json",
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["assignments"][0]["state"] == AssignmentState.CANCELLED
    child.refresh_from_db()
    assert child.state == AssignmentState.CANCELLED

    api_response = api_key_client.get(_admin_url(workspace, "governance/?limit=1"))
    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert len(json.dumps(api_payload).encode("utf-8")) <= 8 * 1024
    assert all(len(api_payload[key]) <= 1 for key in ("assignments", "hr_proposals", "evaluator_reviews"))
    output = json.dumps(api_payload)
    for forbidden in (
        "credential:",
        "credential_ref",
        "runtime_control",
        "socket",
        "lease_owner",
        "requested_profile",
    ):
        assert forbidden not in output

    call_command("agent_governance_readback", workspace_slug=workspace.slug, limit=1)
    assert json.loads(capsys.readouterr().out) == api_payload

    resource_response = api_key_client.post(
        command_url,
        {
            "action": "hr.proposal.read",
            "idempotency_key": "idempotency:governance-resource-read",
            "payload": {"resource_id": f"hr-proposal:{proposal_id}"},
        },
        format="json",
    )
    assert resource_response.status_code == 200
    call_command(
        "agent_governance",
        workspace_slug=workspace.slug,
        action="hr.proposal.read",
        idempotency_key="idempotency:governance-resource-read-cli",
        payload=json.dumps({"resource_id": f"hr-proposal:{proposal_id}"}),
    )
    assert json.loads(capsys.readouterr().out) == resource_response.json()

    untyped_resource = api_key_client.get(_admin_url(workspace, f"governance/?resource_id={proposal_id}"))
    assert untyped_resource.status_code == 400
    assert proposal_id not in untyped_resource.content.decode()

    bad_payload = api_key_client.post(
        command_url,
        {
            "action": "hr.proposal.read",
            "idempotency_key": "idempotency:governance-bad-payload",
            "payload": {"api_key": "secret-value"},
        },
        format="json",
    )
    assert bad_payload.status_code == 400

    denied_user = User.objects.create(email=f"governance-denied-{uuid.uuid4().hex}@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=denied_user, role=15, is_active=True)
    denied_token = APIToken.objects.create(
        user=denied_user,
        label="governance denied",
        token=f"governance-denied-{uuid.uuid4().hex}",
    )
    denied_client = APIClient()
    denied_client.credentials(HTTP_X_API_KEY=denied_token.token)
    denied = denied_client.get(_admin_url(workspace, "governance/"))
    assert denied.status_code == 403
    assert str(proposal_id) not in denied.content.decode()
    denied_command = denied_client.post(
        command_url,
        {
            "action": "assignment.cancel",
            "idempotency_key": "idempotency:governance-denied-api-cancel",
            "payload": {"assignment_id": str(parent.id)},
        },
        format="json",
    )
    assert denied_command.status_code == 403
    with pytest.raises(CommandError, match="current workspace administrator"):
        call_command(
            "agent_governance",
            workspace_slug=workspace.slug,
            action="assignment.cancel",
            operator_id=str(denied_user.id),
            idempotency_key="idempotency:governance-denied-cli-cancel",
            payload=json.dumps({"assignment_id": str(parent.id)}),
        )
    parent.refresh_from_db()
    assert parent.state == AssignmentState.CANCELLED

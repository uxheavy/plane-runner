import json
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Issue,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    Project,
    ProjectMember,
    State,
    User,
)
from plane.operation_gateway.contracts import MAX_RESULT_BYTES


@pytest.fixture
def gateway_project(db, workspace, create_user):
    project = Project.objects.create(
        name="Gateway Project",
        identifier="GW",
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
def gateway_issue(db, gateway_project, workspace, create_user):
    return Issue.objects.create(
        name="Gateway Issue",
        project=gateway_project,
        workspace=workspace,
        created_by=create_user,
    )


def gateway_body(workspace, project, issue, *, operation_id, key, input_data, **extra):
    return {
        "schema_version": "plane.operation/v1",
        "operation_id": operation_id,
        "workspace_slug": workspace.slug,
        "idempotency_key": key,
        "correlation_id": f"corr-{key}",
        "input": {"project_id": str(project.id), "issue_id": str(issue.id), **input_data},
        **extra,
    }


def client_for_user(user):
    client = APIClient()
    token = APIToken.objects.create(user=user, label="Gateway test token", token=f"gateway-{user.id}")
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.mark.contract
@pytest.mark.django_db
def test_read_binds_caller_and_bounds_result(api_key_client, create_user, workspace, gateway_project, gateway_issue):
    response = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.read",
            key="read-1",
            input_data={},
            caller={"type": "user", "id": "attacker-controlled"},
            tool_exposure={"operations": ["work_item.read"]},
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["ok"] is True
    assert body["caller"] == {"type": "user", "id": str(create_user.id)}
    assert body["workspace"] == {"slug": workspace.slug, "id": str(workspace.id)}
    assert set(body["result"]) == {"work_item"}
    assert set(body["result"]["work_item"]) <= {
        "id",
        "name",
        "sequence_id",
        "priority",
        "state",
        "project",
        "workspace",
    }
    assert len(json.dumps(body["result"]).encode("utf-8")) <= MAX_RESULT_BYTES
    assert list(OperationGatewayAudit.objects.filter(idempotency_key="read-1").values_list("outcome", flat=True)) == [
        "intent",
        "success",
    ]


@pytest.mark.contract
@pytest.mark.django_db
def test_denied_mutation_has_no_side_effect_and_audits_denial(create_user, workspace, gateway_project, gateway_issue):
    denied_user = User.objects.create(email="gateway-denied@plane.so", username="gateway-denied")
    client = client_for_user(denied_user)

    response = client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.rename",
            key="deny-1",
            input_data={"name": "Should Not Change"},
            tool_exposure={"operations": ["work_item.rename"]},
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"] == {
        "code": "NOT_AUTHORIZED",
        "message": "Operation is not authorized for this caller.",
        "retryable": False,
    }
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Gateway Issue"
    assert OperationGatewayIdempotency.objects.get(idempotency_key="deny-1").state == "denied"
    assert list(OperationGatewayAudit.objects.filter(idempotency_key="deny-1").values_list("outcome", flat=True)) == [
        "intent",
        "denied",
    ]


@pytest.mark.contract
@pytest.mark.django_db
def test_mutation_replay_is_stable_and_does_not_repeat_plane_service(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="replay-1",
        input_data={"name": "Renamed Once"},
    )
    with (
        patch("plane.api.views.issue.issue_activity") as issue_activity,
        patch("plane.api.views.issue.model_activity") as model_activity,
    ):
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["request_id"] == second.json()["request_id"]
    assert first.json()["result"] == second.json()["result"]
    assert second.json()["idempotency"]["replayed"] is True
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 1
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Renamed Once"
    assert OperationGatewayAudit.objects.filter(idempotency_key="replay-1").count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_conflicting_key_denies_without_replaying_mutation(api_key_client, workspace, gateway_project, gateway_issue):
    first_payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="conflict-1",
        input_data={"name": "First Name"},
    )
    second_payload = {**first_payload, "input": {**first_payload["input"], "name": "Second Name"}}
    with (
        patch("plane.api.views.issue.issue_activity") as issue_activity,
        patch("plane.api.views.issue.model_activity") as model_activity,
    ):
        first = api_key_client.post("/api/v1/operations/", first_payload, format="json")
        second = api_key_client.post("/api/v1/operations/", second_payload, format="json")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 1
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "First Name"
    assert OperationGatewayAudit.objects.filter(idempotency_key="conflict-1").count() == 4


@pytest.mark.contract
@pytest.mark.django_db
def test_outcome_unknown_is_never_blindly_replayed(api_key_client, workspace, gateway_project, gateway_issue):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="unknown-1",
        input_data={"name": "Possibly Renamed"},
    )
    with (
        patch("plane.api.views.issue.issue_activity"),
        patch("plane.api.views.issue.model_activity") as model_activity,
    ):
        model_activity.delay.side_effect = RuntimeError("broker unavailable")
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_409_CONFLICT
    assert first.json()["error"]["code"] == "OUTCOME_UNKNOWN"
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "OUTCOME_UNKNOWN"
    assert second.json()["idempotency"]["replayed"] is True
    assert model_activity.delay.call_count == 1
    assert OperationGatewayIdempotency.objects.get(idempotency_key="unknown-1").state == "outcome_unknown"

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections
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
    Workspace,
)
from plane.operation_gateway.contracts import MAX_RESULT_BYTES
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.work_items import WorkItemRenameFailure, WorkItemRenameService


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
@pytest.mark.django_db(transaction=True)
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
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
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
    assert OperationGatewayAudit.objects.filter(idempotency_key="replay-1").count() == 4
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="replay-1")
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "success", "intent", "replay"]


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
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
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
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
@pytest.mark.django_db(transaction=True)
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
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
    ):
        model_activity.delay.side_effect = RuntimeError("broker unavailable")
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_409_CONFLICT
    assert first.json()["error"]["code"] == "OUTCOME_UNKNOWN"
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "OUTCOME_UNKNOWN"
    assert second.json()["idempotency"]["replayed"] is True
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 1
    assert OperationGatewayIdempotency.objects.get(idempotency_key="unknown-1").state == "outcome_unknown"


@pytest.mark.contract
@pytest.mark.django_db
def test_missing_schema_and_unknown_envelope_fields_are_durable_failures(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.read",
        key="missing-schema",
        input_data={},
    )
    payload.pop("schema_version")
    missing_schema = api_key_client.post("/api/v1/operations/", payload, format="json")

    unknown_field_payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.read",
        key="unknown-envelope",
        input_data={},
        unknown_field="must be rejected",
    )
    unknown_field = api_key_client.post("/api/v1/operations/", unknown_field_payload, format="json")

    assert missing_schema.status_code == status.HTTP_400_BAD_REQUEST
    assert unknown_field.status_code == status.HTTP_400_BAD_REQUEST
    assert missing_schema.json()["error"]["code"] == "VALIDATION_ERROR"
    assert unknown_field.json()["error"]["code"] == "VALIDATION_ERROR"
    assert OperationGatewayAudit.objects.filter(idempotency_key="missing-schema").count() == 2
    assert OperationGatewayAudit.objects.filter(idempotency_key="unknown-envelope").count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_unknown_input_and_oversized_input_are_rejected_without_object_leak(
    api_key_client, workspace, gateway_project, gateway_issue
):
    unknown_input = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.rename",
            key="unknown-input",
            input_data={"name": "valid", "unexpected": "reject me"},
        ),
        format="json",
    )
    oversized_input = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.read",
            key="oversized-input",
            input_data={"padding": "x" * (16 * 1024)},
        ),
        format="json",
    )
    oversized_mutation = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.rename",
            key="oversized-mutation",
            input_data={"name": "x" * (16 * 1024)},
        ),
        format="json",
    )

    assert unknown_input.status_code == status.HTTP_400_BAD_REQUEST
    assert oversized_input.status_code == status.HTTP_400_BAD_REQUEST
    assert oversized_mutation.status_code == status.HTTP_400_BAD_REQUEST
    assert unknown_input.json()["error"]["code"] == "VALIDATION_ERROR"
    assert oversized_input.json()["error"]["code"] == "VALIDATION_ERROR"
    assert oversized_mutation.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Gateway Issue" not in json.dumps(unknown_input.json())
    assert OperationGatewayAudit.objects.filter(idempotency_key="unknown-input").count() == 2
    assert OperationGatewayAudit.objects.filter(idempotency_key="oversized-input").count() == 2
    assert OperationGatewayAudit.objects.filter(idempotency_key="oversized-mutation").count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_unauthenticated_request_uses_bounded_gateway_envelope(api_client, workspace, gateway_project, gateway_issue):
    response = api_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.read",
            key="anonymous-1",
            input_data={},
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Authentication is required for this operation.",
        "retryable": False,
    }
    assert body["caller"]["id"] == "anonymous"
    assert "token" not in json.dumps(body).lower()
    assert OperationGatewayAudit.objects.count() == 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_authenticated_throttle_uses_bounded_audit_envelope(
    api_key_client, workspace, gateway_project, gateway_issue
):
    class AlwaysThrottled:
        def allow_request(self, request, view):
            return False

        def wait(self):
            return 30

    with patch(
        "plane.operation_gateway.views.OperationGatewayAPIEndpoint.get_throttles",
        return_value=[AlwaysThrottled()],
    ):
        response = api_key_client.post(
            "/api/v1/operations/",
            gateway_body(
                workspace,
                gateway_project,
                gateway_issue,
                operation_id="work_item.read",
                key="throttled-1",
                input_data={},
            ),
            format="json",
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["error"] == {
        "code": "THROTTLED",
        "message": "Too many operation requests.",
        "retryable": False,
    }
    assert OperationGatewayAudit.objects.filter(idempotency_key="throttled-1").count() == 2


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_retryable_precommit_failure_reopens_only_after_rollback(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="retryable-precommit",
        input_data={"name": "Retry Me"},
    )
    real_service = WorkItemRenameService()
    original_rename = WorkItemRenameService.rename
    attempts = {"count": 0}

    def fail_once(service, *args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise WorkItemRenameFailure("UPSTREAM_FAILURE", 503, True)
        return original_rename(real_service, *args, **kwargs)

    with (
        patch.object(WorkItemRenameService, "rename", autospec=True, side_effect=fail_once),
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
    ):
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        gateway_issue.refresh_from_db()
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert first.json()["error"]["retryable"] is True
    assert second.status_code == status.HTTP_200_OK
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Retry Me"
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 1
    record = OperationGatewayIdempotency.objects.get(idempotency_key="retryable-precommit")
    assert record.state == OperationGatewayIdempotency.State.SUCCEEDED
    assert record.retryable is False
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="retryable-precommit")
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "failure", "intent", "success"]


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_post_commit_publication_failure_is_unknown_and_reconciles_without_republish(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="post-commit-unknown",
        input_data={"name": "Committed Name"},
    )
    with (
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
    ):
        issue_activity.delay.side_effect = RuntimeError("broker secret must not escape")
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        record = OperationGatewayIdempotency.objects.get(idempotency_key="post-commit-unknown")
        reconciled, reconcile_status = OperationGateway().reconcile(record.id)
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_409_CONFLICT
    assert first.json()["error"]["code"] == "OUTCOME_UNKNOWN"
    assert "broker secret" not in json.dumps(first.json())
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Committed Name"
    assert reconcile_status == status.HTTP_200_OK
    assert reconciled["ok"] is True
    assert second.status_code == status.HTTP_200_OK
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 0
    assert OperationGatewayIdempotency.objects.get(id=record.id).state == OperationGatewayIdempotency.State.SUCCEEDED


@pytest.mark.contract
@pytest.mark.django_db
def test_audit_queryset_and_bulk_mutations_are_blocked(api_key_client, workspace, gateway_project, gateway_issue):
    response = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.read",
            key="append-only-1",
            input_data={},
        ),
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    audit = OperationGatewayAudit.objects.get(id=response.json()["audit_receipt"])

    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit.objects.filter(pk=audit.pk).update(error_code="tamper")
    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit.objects.filter(pk=audit.pk).delete()
    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit.objects.bulk_update([audit], ["error_code"])
    with pytest.raises(ValueError, match="append-only"):
        audit.save(update_fields=["error_code"])
    with pytest.raises(ValueError, match="append-only"):
        audit.delete()


@pytest.mark.contract
@pytest.mark.django_db
def test_same_key_isolated_by_stable_workspace_uuid(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    second_workspace = Workspace.objects.create(name="Second Workspace", owner=create_user, slug="second-workspace")
    from plane.db.models import WorkspaceMember

    WorkspaceMember.objects.create(workspace=second_workspace, member=create_user, role=20)
    second_project = Project.objects.create(
        name="Second Gateway Project",
        identifier="GW2",
        workspace=second_workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=second_project, member=create_user, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=second_project,
        workspace=second_workspace,
        created_by=create_user,
    )
    second_issue = Issue.objects.create(
        name="Second Gateway Issue",
        project=second_project,
        workspace=second_workspace,
        created_by=create_user,
    )

    with (
        patch("plane.operation_gateway.work_items.issue_activity"),
        patch("plane.operation_gateway.work_items.model_activity"),
    ):
        first = api_key_client.post(
            "/api/v1/operations/",
            gateway_body(
                workspace,
                gateway_project,
                gateway_issue,
                operation_id="work_item.rename",
                key="same-tenant-key",
                input_data={"name": "First Tenant Name"},
            ),
            format="json",
        )
        second = api_key_client.post(
            "/api/v1/operations/",
            gateway_body(
                second_workspace,
                second_project,
                second_issue,
                operation_id="work_item.rename",
                key="same-tenant-key",
                input_data={"name": "Second Tenant Name"},
            ),
            format="json",
        )

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert OperationGatewayIdempotency.objects.filter(idempotency_key="same-tenant-key").count() == 2
    assert {
        record.workspace_id
        for record in OperationGatewayIdempotency.objects.filter(idempotency_key="same-tenant-key")
    } == {workspace.id, second_workspace.id}
    gateway_issue.refresh_from_db()
    second_issue.refresh_from_db()
    assert gateway_issue.name == "First Tenant Name"
    assert second_issue.name == "Second Tenant Name"


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_concurrent_first_use_applies_and_publishes_once(api_token, workspace, gateway_project, gateway_issue):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="concurrent-first-use",
        input_data={"name": "One Concurrent Rename"},
    )
    entered = threading.Event()
    release = threading.Event()
    original_rename = WorkItemRenameService.rename

    def blocked_rename(service, *args, **kwargs):
        entered.set()
        release.wait(timeout=10)
        return original_rename(service, *args, **kwargs)

    def invoke():
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_X_API_KEY=api_token.token)
            return client.post("/api/v1/operations/", payload, format="json")
        finally:
            close_old_connections()

    with (
        patch.object(WorkItemRenameService, "rename", autospec=True, side_effect=blocked_rename) as rename,
        patch("plane.operation_gateway.work_items.issue_activity") as issue_activity,
        patch("plane.operation_gateway.work_items.model_activity") as model_activity,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first_future = executor.submit(invoke)
        assert entered.wait(timeout=10)
        second_future = executor.submit(invoke)
        release.set()
        first = first_future.result(timeout=20)
        second = second_future.result(timeout=20)

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert {first.json()["idempotency"]["replayed"], second.json()["idempotency"]["replayed"]} == {False, True}
    assert rename.call_count == 1
    assert issue_activity.delay.call_count == 1
    assert model_activity.delay.call_count == 1
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "One Concurrent Rename"

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import (
    APIToken,
    Issue,
    IssueActivity,
    IssueSubscriber,
    Notification,
    EmailNotificationLog,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    OperationGatewayPublication,
    Project,
    ProjectMember,
    State,
    User,
    UserNotificationPreference,
    Webhook,
    WebhookLog,
    Workspace,
)
from plane.operation_gateway.contracts import MAX_RESULT_BYTES
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.publications import dispatch_publication_once
from plane.bgtasks.webhook_task import WebhookDeliveryResult, deliver_webhook_target
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


def drain_publications(record):
    for publication in record.publications.order_by("kind"):
        dispatch_publication_once(str(publication.id))


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
def test_terminal_failure_replay_returns_fresh_receipt(api_key_client, workspace, gateway_project, gateway_issue):
    denied = User.objects.create(email="gateway-replay-denied@plane.so", username="gateway-replay-denied")
    client = client_for_user(denied)
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="failure-replay",
        input_data={"name": "Never Changes"},
    )
    first = client.post("/api/v1/operations/", payload, format="json")
    second = client.post("/api/v1/operations/", payload, format="json")
    assert first.status_code == status.HTTP_403_FORBIDDEN
    assert second.status_code == status.HTTP_403_FORBIDDEN
    assert first.json()["request_id"] != second.json()["request_id"]
    assert first.json()["audit_receipt"] != second.json()["audit_receipt"]
    replay_audit = OperationGatewayAudit.objects.get(id=second.json()["audit_receipt"])
    assert replay_audit.outcome == OperationGatewayAudit.Outcome.REPLAY
    assert replay_audit.request_id == uuid.UUID(second.json()["request_id"])
    assert replay_audit.invocation_id != OperationGatewayAudit.objects.get(id=first.json()["audit_receipt"]).invocation_id


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
    first = api_key_client.post("/api/v1/operations/", payload, format="json")
    record = OperationGatewayIdempotency.objects.get(idempotency_key="replay-1")
    drain_publications(record)
    second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["request_id"] != second.json()["request_id"]
    assert first.json()["result"] == second.json()["result"]
    assert second.json()["idempotency"]["replayed"] is True
    assert record.publications.count() == 2
    assert record.publications.filter(state=OperationGatewayPublication.State.SUCCEEDED).count() == 2
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 1
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Renamed Once"
    assert OperationGatewayAudit.objects.filter(idempotency_key="replay-1").count() == 4
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="replay-1")
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "success", "intent", "replay"]
    replay_audit = OperationGatewayAudit.objects.get(id=second.json()["audit_receipt"])
    assert replay_audit.outcome == OperationGatewayAudit.Outcome.REPLAY
    assert replay_audit.request_id == uuid.UUID(second.json()["request_id"])
    assert replay_audit.request_id != uuid.UUID(first.json()["request_id"])
    assert replay_audit.invocation_id != record.invocation_id


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
    first = api_key_client.post("/api/v1/operations/", first_payload, format="json")
    first_record = OperationGatewayIdempotency.objects.get(idempotency_key="conflict-1")
    drain_publications(first_record)
    second = api_key_client.post("/api/v1/operations/", second_payload, format="json")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "First Name"
    assert OperationGatewayAudit.objects.filter(idempotency_key="conflict-1").count() == 4
    conflict_audits = OperationGatewayAudit.objects.filter(
        idempotency_key="conflict-1",
        outcome=OperationGatewayAudit.Outcome.DENIED,
    )
    assert conflict_audits.count() == 1
    assert conflict_audits.first().request_id == uuid.UUID(second.json()["request_id"])
    assert str(conflict_audits.first().request_id) != first.json()["request_id"]


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_post_commit_dispatch_loss_is_recovered_from_durable_publications(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="unknown-1",
        input_data={"name": "Possibly Renamed"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications") as schedule:
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        schedule.assert_called_once()
    record = OperationGatewayIdempotency.objects.get(idempotency_key="unknown-1")

    assert first.status_code == status.HTTP_200_OK
    assert record.state == OperationGatewayIdempotency.State.SUCCEEDED
    assert record.publications.filter(state=OperationGatewayPublication.State.PENDING).count() == 2
    reconciled, reconcile_status = OperationGateway().reconcile(record.id)
    assert reconcile_status == status.HTTP_200_OK
    assert reconciled["ok"] is True
    assert record.publications.filter(state=OperationGatewayPublication.State.SUCCEEDED).count() == 2


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_webhook_intents_are_per_target_and_partial_success_is_independent(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    first_webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-one.example.com/plane",
        issue=True,
        created_by=create_user,
    )
    second_webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-two.example.com/plane",
        issue=True,
        created_by=create_user,
    )
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="webhook-targets",
        input_data={"name": "Targeted Rename"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications") as schedule:
        response = api_key_client.post("/api/v1/operations/", payload, format="json")
        schedule.assert_called_once()
        assert len(schedule.call_args.args[0]) == 4

    record = OperationGatewayIdempotency.objects.get(idempotency_key="webhook-targets")
    webhook_publications = list(
        record.publications.filter(kind=OperationGatewayPublication.Kind.WEBHOOK).order_by("target_id")
    )
    assert {publication.target_id for publication in webhook_publications} == {
        first_webhook.id,
        second_webhook.id,
    }
    assert len({publication.publication_key for publication in webhook_publications}) == 2

    def result_for_target(**kwargs):
        if kwargs["webhook_id"] == str(first_webhook.id):
            return WebhookDeliveryResult("succeeded", False, response_status=202)
        return WebhookDeliveryResult("failed", False, response_status=400, error="rejected")

    with patch("plane.operation_gateway.publications.deliver_webhook_target", side_effect=result_for_target) as deliver:
        for publication in webhook_publications:
            dispatch_publication_once(str(publication.id))
        assert deliver.call_count == 2
        assert {call.kwargs["delivery_key"] for call in deliver.call_args_list} == {
            publication.publication_key for publication in webhook_publications
        }

    webhook_publications[0].refresh_from_db()
    webhook_publications[1].refresh_from_db()
    assert webhook_publications[0].state == OperationGatewayPublication.State.SUCCEEDED
    assert webhook_publications[1].state == OperationGatewayPublication.State.FAILED
    assert record.publications.filter(state=OperationGatewayPublication.State.SUCCEEDED).count() == 3
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_concurrent_webhook_workers_have_one_durable_claim(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-concurrent.example.com/plane",
        issue=True,
        created_by=create_user,
    )
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="webhook-concurrent-claim",
        input_data={"name": "Concurrent Claim"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications"):
        api_key_client.post("/api/v1/operations/", payload, format="json")
    publication = OperationGatewayPublication.objects.get(
        idempotency__idempotency_key="webhook-concurrent-claim",
        kind=OperationGatewayPublication.Kind.WEBHOOK,
        target_id=webhook.id,
    )
    entered = threading.Event()
    release = threading.Event()

    def deliver(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return WebhookDeliveryResult("succeeded", False, response_status=204)

    def dispatch():
        close_old_connections()
        try:
            return dispatch_publication_once(str(publication.id))
        finally:
            close_old_connections()

    with (
        patch("plane.operation_gateway.publications.deliver_webhook_target", side_effect=deliver) as send,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first_future = executor.submit(dispatch)
        assert entered.wait(timeout=10)
        second_future = executor.submit(dispatch)
        second_future.result(timeout=10)
        release.set()
        first_future.result(timeout=20)

    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.SUCCEEDED
    assert publication.attempts == 1
    assert send.call_count == 1


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_webhook_crash_before_send_is_retryable_but_ambiguous_delivery_is_not(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-crash.example.com/plane",
        issue=True,
        created_by=create_user,
    )
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="webhook-crash",
        input_data={"name": "Crash Rename"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications"):
        api_key_client.post("/api/v1/operations/", payload, format="json")
    publication = OperationGatewayPublication.objects.get(
        idempotency__idempotency_key="webhook-crash",
        kind=OperationGatewayPublication.Kind.WEBHOOK,
        target_id=webhook.id,
    )

    with patch(
        "plane.operation_gateway.publications._mark_dispatch_started",
        side_effect=RuntimeError("crashed before send"),
    ):
        with pytest.raises(RuntimeError):
            dispatch_publication_once(str(publication.id))
    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.RETRYABLE

    with patch(
        "plane.operation_gateway.publications.deliver_webhook_target",
        side_effect=RuntimeError("worker died after request was sent"),
    ):
        with pytest.raises(RuntimeError):
            dispatch_publication_once(str(publication.id))
    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.OUTCOME_UNKNOWN
    attempts = publication.attempts
    dispatch_publication_once(str(publication.id))
    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.OUTCOME_UNKNOWN
    assert publication.attempts == attempts


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_webhook_success_before_worker_death_becomes_unknown_without_replay(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-success-death.example.com/plane",
        issue=True,
        created_by=create_user,
    )
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="webhook-success-death",
        input_data={"name": "Success Death"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications"):
        api_key_client.post("/api/v1/operations/", payload, format="json")
    publication = OperationGatewayPublication.objects.get(
        idempotency__idempotency_key="webhook-success-death",
        kind=OperationGatewayPublication.Kind.WEBHOOK,
        target_id=webhook.id,
    )
    result = WebhookDeliveryResult("succeeded", False, response_status=204)
    with (
        patch("plane.operation_gateway.publications.deliver_webhook_target", return_value=result) as deliver,
        patch(
            "plane.operation_gateway.publications._finalize_external_publication",
            side_effect=RuntimeError("worker died after response"),
        ),
    ):
        with pytest.raises(RuntimeError):
            dispatch_publication_once(str(publication.id))

    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.RUNNING
    publication.lease_until = timezone.now() - timedelta(seconds=1)
    publication.save(update_fields=["lease_until", "updated_at"])
    dispatch_publication_once(str(publication.id))
    publication.refresh_from_db()
    assert publication.state == OperationGatewayPublication.State.OUTCOME_UNKNOWN
    assert deliver.call_count == 1


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_webhook_adapter_records_stable_key_headers_and_definite_failure(
    workspace, create_user
):
    webhook = Webhook.objects.create(
        workspace=workspace,
        url="https://hooks-definite.example.com/plane",
        issue=True,
        created_by=create_user,
    )

    class Response:
        status_code = 404
        headers = {"content-type": "text/plain"}
        text = "not found"

    with patch("plane.bgtasks.webhook_task.pinned_fetch", return_value=Response()) as fetch:
        result = deliver_webhook_target(
            webhook_id=str(webhook.id),
            slug=workspace.slug,
            event="issue",
            event_data={"id": "issue"},
            action="updated",
            current_site=None,
            activity=None,
            delivery_key="gateway:webhook:stable",
        )

    assert result.state == OperationGatewayPublication.State.FAILED
    assert result.retryable is False
    assert fetch.call_args.kwargs["headers"]["X-Plane-Delivery"] == "gateway:webhook:stable"
    assert fetch.call_args.kwargs["headers"]["Idempotency-Key"] == "gateway:webhook:stable"
    log = WebhookLog.all_objects.get(delivery_key="gateway:webhook:stable")
    assert log.delivery_state == OperationGatewayPublication.State.FAILED
    assert log.delivery_result["response_status"] == 404

    class ServerErrorResponse:
        status_code = 503
        headers = {}
        text = "temporarily unavailable"

    with patch("plane.bgtasks.webhook_task.pinned_fetch", return_value=ServerErrorResponse()):
        server_error = deliver_webhook_target(
            webhook_id=str(webhook.id),
            slug=workspace.slug,
            event="issue",
            event_data={"id": "issue"},
            action="updated",
            current_site=None,
            activity=None,
            delivery_key="gateway:webhook:server-error",
        )
    assert server_error.state == OperationGatewayPublication.State.FAILED
    assert server_error.retryable is False


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
    ):
        first = api_key_client.post("/api/v1/operations/", payload, format="json")
        gateway_issue.refresh_from_db()
        second = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert first.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert first.json()["error"]["retryable"] is True
    assert second.status_code == status.HTTP_200_OK
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Retry Me"
    record = OperationGatewayIdempotency.objects.get(idempotency_key="retryable-precommit")
    assert record.state == OperationGatewayIdempotency.State.SUCCEEDED
    assert record.retryable is False
    assert record.publications.count() == 2
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="retryable-precommit")
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "failure", "intent", "success"]


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_publication_worker_crash_rolls_back_effect_and_retry_is_idempotent(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="worker-crash",
        input_data={"name": "Committed Name"},
    )
    first = api_key_client.post("/api/v1/operations/", payload, format="json")
    record = OperationGatewayIdempotency.objects.get(idempotency_key="worker-crash")
    activity = record.publications.get(kind=OperationGatewayPublication.Kind.ACTIVITY)
    real_run = issue_activity.run

    def effect_then_die(**kwargs):
        real_run(**kwargs)
        raise RuntimeError("worker died after effect before receipt")

    with patch("plane.operation_gateway.publications.issue_activity.run", side_effect=effect_then_die):
        with pytest.raises(RuntimeError):
            dispatch_publication_once(str(activity.id))

    activity.refresh_from_db()
    assert activity.state == OperationGatewayPublication.State.RETRYABLE
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 0
    dispatch_publication_once(str(activity.id))
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 1
    dispatch_publication_once(str(activity.id))
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 1
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Committed Name"
    assert first.status_code == status.HTTP_200_OK


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_notification_publication_retries_without_duplicate_notifications(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    receiver = User.objects.create(email="gateway-receiver@plane.so", username="gateway-receiver")
    ProjectMember.objects.create(project=gateway_project, member=receiver, role=20, is_active=True)
    IssueSubscriber.objects.create(
        project=gateway_project,
        workspace=workspace,
        issue=gateway_issue,
        subscriber=receiver,
    )
    UserNotificationPreference.objects.create(user=receiver)
    state = State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=gateway_project,
        workspace=workspace,
        created_by=create_user,
    )
    gateway_issue.state = state
    gateway_issue.save(update_fields=["state"])

    response = api_key_client.post(
        "/api/v1/operations/",
        gateway_body(
            workspace,
            gateway_project,
            gateway_issue,
            operation_id="work_item.rename",
            key="notification-retry",
            input_data={"name": "Notified Rename"},
        ),
        format="json",
    )
    record = OperationGatewayIdempotency.objects.get(idempotency_key="notification-retry")
    drain_publications(record)
    count_after_first = Notification.objects.filter(entity_identifier=gateway_issue.id).count()
    drain_publications(record)

    assert response.status_code == status.HTTP_200_OK
    assert count_after_first == 1
    assert Notification.objects.filter(entity_identifier=gateway_issue.id).count() == 1
    assert Notification.objects.filter(entity_identifier=gateway_issue.id).exclude(idempotency_key__isnull=True).count() == 1
    assert EmailNotificationLog.objects.filter(entity_identifier=gateway_issue.id).exclude(
        idempotency_key__isnull=True
    ).count() == 1
    assert OperationGatewayPublication.objects.get(
        idempotency__idempotency_key="notification-retry",
        kind=OperationGatewayPublication.Kind.NOTIFICATION,
    ).state == OperationGatewayPublication.State.SUCCEEDED


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_notification_adapter_failure_is_visible_and_missing_activity_is_not_success(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = gateway_body(
        workspace,
        gateway_project,
        gateway_issue,
        operation_id="work_item.rename",
        key="notification-failure",
        input_data={"name": "Notification Failure"},
    )
    with patch("plane.operation_gateway.publications.schedule_publications"):
        api_key_client.post("/api/v1/operations/", payload, format="json")
    record = OperationGatewayIdempotency.objects.get(idempotency_key="notification-failure")
    activity_publication = record.publications.get(kind=OperationGatewayPublication.Kind.ACTIVITY)
    notification_publication = record.publications.get(kind=OperationGatewayPublication.Kind.NOTIFICATION)

    with patch(
        "plane.operation_gateway.publications.run_notifications",
        side_effect=RuntimeError("notification downstream failed"),
    ):
        with pytest.raises(Exception):
            dispatch_publication_once(str(notification_publication.id))
    notification_publication.refresh_from_db()
    assert notification_publication.state == OperationGatewayPublication.State.RETRYABLE
    assert Notification.objects.filter(entity_identifier=gateway_issue.id).count() == 0

    activity_publication.state = OperationGatewayPublication.State.SUCCEEDED
    activity_publication.payload = {"activity_id": str(uuid.uuid4())}
    activity_publication.save(update_fields=["state", "payload", "updated_at"])
    notification_publication.payload["activity_id"] = str(uuid.uuid4())
    notification_publication.state = OperationGatewayPublication.State.RETRYABLE
    notification_publication.save(update_fields=["payload", "state", "updated_at"])
    with pytest.raises(Exception):
        dispatch_publication_once(str(notification_publication.id))
    notification_publication.refresh_from_db()
    assert notification_publication.state == OperationGatewayPublication.State.FAILED


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
    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit._base_manager.filter(pk=audit.pk).update(error_code="tamper")
    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit._base_manager.filter(pk=audit.pk).delete()
    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit._base_manager.bulk_update([audit], ["error_code"])

    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE operation_gateway_audit SET error_code = %s WHERE id = %s",
                    ["tamper", str(audit.pk)],
                )
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM operation_gateway_audit WHERE id = %s",
                    [str(audit.pk)],
                )
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE operation_gateway_audit")

    inserted = OperationGatewayAudit.objects.create(
        invocation_id=uuid.uuid4(),
        phase=OperationGatewayAudit.Phase.INTENT,
        outcome=OperationGatewayAudit.Outcome.INTENT,
        request_id=uuid.uuid4(),
        operation_id="work_item.read",
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        caller_id=audit.caller_id,
        idempotency_key="append-only-insert",
        correlation_id="append-only-correlation",
        request_digest="0" * 64,
    )
    assert OperationGatewayAudit._base_manager.get(pk=inserted.pk).pk == inserted.pk


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_postgres_audit_runtime_role_cannot_govern_or_bypass_trigger():
    runtime_role = f"gateway_runtime_{uuid.uuid4().hex[:10]}"
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{runtime_role}" NOLOGIN')
        cursor.execute(
            f'GRANT SELECT, INSERT ON operation_gateway_audit TO "{runtime_role}"'
        )
        cursor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE, TRIGGER ON operation_gateway_audit FROM "{runtime_role}"')
        cursor.execute(
            "SELECT tableowner, has_table_privilege(%s, 'operation_gateway_audit', 'SELECT'), "
            "has_table_privilege(%s, 'operation_gateway_audit', 'INSERT'), "
            "has_table_privilege(%s, 'operation_gateway_audit', 'UPDATE'), "
            "has_table_privilege(%s, 'operation_gateway_audit', 'DELETE'), "
            "has_table_privilege(%s, 'operation_gateway_audit', 'TRUNCATE') "
            "FROM pg_tables WHERE tablename = 'operation_gateway_audit'",
            [runtime_role] * 5,
        )
        owner, can_select, can_insert, can_update, can_delete, can_truncate = cursor.fetchone()
        assert owner == settings.PLANE_AUDIT_GOVERNANCE_ROLE
        assert can_select is True
        assert can_insert is True
        assert can_update is False
        assert can_delete is False
        assert can_truncate is False
        cursor.execute(f'SET ROLE "{runtime_role}"')

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO operation_gateway_audit
                    (id, invocation_id, phase, outcome, request_id, operation_id,
                     workspace_slug, caller_id, idempotency_key, correlation_id,
                     request_digest, created_at)
                VALUES (%s, %s, 'intent', 'intent', %s, 'role-probe',
                        'role-probe', %s, %s, 'role-probe', %s, NOW())
                """,
                [uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "role-probe", "0" * 64],
            )
        for statement in (
            "UPDATE operation_gateway_audit SET error_code = 'x'",
            "DELETE FROM operation_gateway_audit",
            "TRUNCATE operation_gateway_audit",
            "ALTER TABLE operation_gateway_audit DISABLE TRIGGER ALL",
            "DROP TABLE operation_gateway_audit",
        ):
            with pytest.raises(DatabaseError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(statement)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f'DROP ROLE "{runtime_role}"')


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
    first_record = OperationGatewayIdempotency.objects.get(
        idempotency_key="same-tenant-key", workspace_id=workspace.id
    )
    drain_publications(first_record)
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
    second_record = OperationGatewayIdempotency.objects.get(
        idempotency_key="same-tenant-key", workspace_id=second_workspace.id
    )
    drain_publications(second_record)

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
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "One Concurrent Rename"
    record = OperationGatewayIdempotency.objects.get(idempotency_key="concurrent-first-use")
    assert record.publications.count() == 2
    replay_response = first if first.json()["idempotency"]["replayed"] else second
    replay_audit = OperationGatewayAudit.objects.get(id=replay_response.json()["audit_receipt"])
    assert replay_audit.outcome == OperationGatewayAudit.Outcome.REPLAY
    assert replay_audit.request_id == uuid.UUID(replay_response.json()["request_id"])
    assert replay_audit.correlation_id == replay_response.json()["correlation_id"]
    assert replay_audit.invocation_id != record.invocation_id

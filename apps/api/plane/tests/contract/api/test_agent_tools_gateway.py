"""Gateway proof for the L5 universal work core and progressive catalog."""

import json
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Issue,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    Page,
    Project,
    ProjectMember,
    ProjectPage,
    State,
    User,
    WorkspaceMember,
)


@pytest.fixture
def gateway_project(db, workspace, create_user):
    project = Project.objects.create(
        name="Gateway Project",
        identifier="AGW",
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


def _body(workspace, operation_id, key, input_data):
    return {
        "schema_version": "plane.operation/v1",
        "operation_id": operation_id,
        "workspace_slug": workspace.slug,
        "idempotency_key": key,
        "correlation_id": f"correlation:{key}",
        "input": input_data,
    }


@pytest.mark.contract
@pytest.mark.django_db
def test_search_workspace_is_typed_bounded_idempotent_and_audited(
    api_key_client, workspace, gateway_project, gateway_issue
):
    body = _body(
        workspace,
        "search_workspace",
        "search-workspace-1",
        {"query": "Gateway", "limit": 20},
    )
    first = api_key_client.post("/api/v1/operations/", body, format="json")
    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert first_body["ok"] is True
    assert all("ref" in result and "objectType" in result for result in first_body["result"]["results"])
    assert len(json.dumps(first_body["result"]).encode("utf-8")) <= 8 * 1024

    replay = api_key_client.post("/api/v1/operations/", body, format="json")
    assert replay.status_code == status.HTTP_200_OK
    assert replay.json()["idempotency"]["replayed"] is True
    assert replay.json()["result"] == first_body["result"]
    assert OperationGatewayIdempotency.objects.filter(idempotency_key="search-workspace-1").count() == 1
    assert OperationGatewayAudit.objects.filter(idempotency_key="search-workspace-1").count() >= 2


@pytest.mark.contract
@pytest.mark.django_db
def test_catalog_search_is_complete_and_does_not_filter_by_profile_or_identity(api_key_client, workspace):
    response = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "catalog.search", "catalog-search-1", {"query": ""}),
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    operation_ids = {entry["operationId"] for entry in response.json()["result"]["operations"]}
    assert {
        "search_workspace",
        "work_item.read",
        "work_item.rename",
        "catalog.search",
        "catalog.describe",
        "code_mode.spill",
    } <= operation_ids
    assert response.json()["audit_receipt"]


@pytest.mark.contract
@pytest.mark.django_db
def test_catalog_search_progressively_discovers_non_core_operation(api_key_client, workspace):
    default_response = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "catalog.search", "catalog-search-default-page", {"query": ""}),
        format="json",
    )
    assert default_response.status_code == status.HTTP_200_OK
    default_ids = {entry["operationId"] for entry in default_response.json()["result"]["operations"]}
    assert "module.list" not in default_ids

    filtered_response = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "catalog.search", "catalog-search-module-filter", {"query": "module.list"}),
        format="json",
    )
    assert filtered_response.status_code == status.HTTP_200_OK
    filtered_ids = {entry["operationId"] for entry in filtered_response.json()["result"]["operations"]}
    assert "module.list" in filtered_ids


@pytest.mark.contract
@pytest.mark.django_db
def test_catalog_describe_discovery_exposes_its_nested_input_schema(api_key_client, workspace):
    response = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "catalog.search", "catalog-search-describe-schema", {"query": ""}),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    entry = next(
        item for item in response.json()["result"]["operations"] if item["operationId"] == "catalog.describe"
    )
    assert entry["inputSchema"] == {
        "type": "object",
        "additionalProperties": False,
        "required": ["operation_id"],
        "properties": {"operation_id": {"type": "string", "maxLength": 128, "minLength": 1}},
    }


@pytest.mark.contract
@pytest.mark.django_db
def test_search_workspace_binds_visible_work_item_to_canonical_read_input(
    api_key_client, workspace, gateway_project, gateway_issue
):
    search = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "search_workspace", "search-work-item-input", {"query": "Gateway Issue"}),
        format="json",
    )

    assert search.status_code == status.HTTP_200_OK
    result = next(item for item in search.json()["result"]["results"] if item["objectType"] == "work_item")
    assert result["workItemReadInput"] == {
        "project_id": str(gateway_project.id),
        "issue_id": str(gateway_issue.id),
    }
    assert result["workItemReadCall"] == {
        "action": "read",
        "operationRef": "operation:work_item.read",
        "input": result["workItemReadInput"],
    }

    read = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "work_item.read", "read-search-bound-work-item", result["workItemReadCall"]["input"]),
        format="json",
    )
    assert read.status_code == status.HTTP_200_OK
    assert read.json()["ok"] is True

    denied = api_key_client.post(
        "/api/v1/operations/",
        _body(
            workspace,
            "work_item.read",
            "read-out-of-scope-project",
            {"project_id": str(uuid4()), "issue_id": str(gateway_issue.id)},
        ),
        format="json",
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert denied.json()["error"]["code"] == "NOT_AUTHORIZED"


@pytest.mark.contract
@pytest.mark.django_db
def test_search_workspace_does_not_leak_cross_project_pages_or_private_pages(
    api_key_client, workspace, gateway_project, create_user
):
    inaccessible_project = Project.objects.create(
        name="Inaccessible Project",
        identifier="NOPE",
        workspace=workspace,
        created_by=create_user,
    )
    public_cross_project = Page.objects.create(
        workspace=workspace,
        name="Cross Project Public Secret",
        owned_by=create_user,
        access=Page.PUBLIC_ACCESS,
    )
    ProjectPage.objects.create(project=inaccessible_project, page=public_cross_project, workspace=workspace)
    private_page = Page.objects.create(
        workspace=workspace,
        name="Private Linked Page Secret",
        owned_by=User.objects.create(email="page-owner@example.com"),
        access=Page.PRIVATE_ACCESS,
    )
    ProjectPage.objects.create(project=gateway_project, page=private_page, workspace=workspace)

    response = api_key_client.post(
        "/api/v1/operations/",
        _body(workspace, "search_workspace", "search-page-visibility", {"query": "Secret", "limit": 20}),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"]["results"] == []
    assert Page.objects.filter(pk=public_cross_project.pk).exists()
    assert Page.objects.filter(pk=private_page.pk).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_search_workspace_applies_guest_page_and_work_item_visibility(
    workspace, gateway_project, gateway_issue, create_user
):
    guest = User.objects.create(email="search-guest@example.com")
    WorkspaceMember.objects.create(workspace=workspace, member=guest, role=5)
    ProjectMember.objects.create(
        project=gateway_project,
        member=guest,
        role=5,
        is_active=True,
    )
    guest_page = Page.objects.create(
        workspace=workspace,
        name="Guest Hidden Page",
        owned_by=create_user,
        access=Page.PUBLIC_ACCESS,
    )
    ProjectPage.objects.create(project=gateway_project, page=guest_page, workspace=workspace)
    hidden_issue = Issue.objects.create(
        name="Guest Hidden Issue",
        project=gateway_project,
        workspace=workspace,
        created_by=create_user,
    )
    token = APIToken.objects.create(user=guest, label="guest-search", token="guest-search-token")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)

    response = client.post(
        "/api/v1/operations/",
        _body(workspace, "search_workspace", "search-guest-visibility", {"query": "Hidden", "limit": 20}),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"]["results"] == []
    assert Issue.objects.filter(pk=hidden_issue.pk).exists()

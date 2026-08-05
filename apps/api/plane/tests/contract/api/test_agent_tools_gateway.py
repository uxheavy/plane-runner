"""Gateway proof for the L5 universal work core and progressive catalog."""

import json

import pytest
from rest_framework import status

from plane.db.models import OperationGatewayAudit, OperationGatewayIdempotency


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
    } <= operation_ids
    assert response.json()["audit_receipt"]

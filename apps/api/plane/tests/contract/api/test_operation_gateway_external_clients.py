"""Plane-side traces for the pinned external MCP and SDK gateway clients.

These tests load the exact external worktrees selected by the test command and
send their real transport code through Plane's versioned operation endpoint.
The injected HTTP sessions only replace network I/O with DRF's in-process
test client; authentication, gateway dispatch, authorization, idempotency,
result bounding, and audit persistence remain Plane-owned runtime behavior.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from rest_framework.test import APIClient

from plane.agent.tools.workspace_search import WorkspaceSearchService
from plane.db.models import (
    APIToken,
    AgentActor,
    Issue,
    IssueActivity,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    ProjectMember,
    User,
    WorkspaceMember,
)
from plane.operation_gateway.contracts import MAX_RESULT_BYTES
from plane.operation_gateway.publications import dispatch_publication_once

EXPECTED_MCP_TIP = "2dc152e136d7ad952b901e5fe9364a37487297ba"
EXPECTED_MCP_INVENTORY_SOURCE = "96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1"
EXPECTED_SDK_TIP = "7d2faf3b7ef5409e292ba0a3c7015e59f93c5889"
MCP_ROOT_ENV = "PLANE_MCP_EXTERNAL_ROOT"
SDK_ROOT_ENV = "PLANE_SDK_EXTERNAL_ROOT"
MCP_ROOT_DEFAULT = "/private/tmp/plane-mcp-g3-20260806"
SDK_ROOT_DEFAULT = "/private/tmp/plane-sdk-g3-20260806"
SDK_OAUTH_TOKEN = "external-sdk-oauth-token"


def _external_root(env_name: str, default: str, expected_tip: str) -> Path:
    root = Path(os.getenv(env_name, default)).resolve()
    if not root.is_dir():
        pytest.fail(f"{env_name} must point at the checked-out external client: {root}")
    try:
        tip = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.fail(f"{env_name} is not a readable git worktree: {root} ({exc})")
    assert tip == expected_tip, f"event=external_client_pin expected={expected_tip} actual={tip} root={root}"
    return root


def _load_mcp_gateway() -> tuple[Any, Path]:
    root = _external_root(MCP_ROOT_ENV, MCP_ROOT_DEFAULT, EXPECTED_MCP_TIP)
    for name in list(sys.modules):
        if name == "plane_mcp" or name.startswith("plane_mcp."):
            del sys.modules[name]
    sys.path.insert(0, str(root))
    try:
        importlib.invalidate_caches()
        module = importlib.import_module("plane_mcp.gateway")
    finally:
        sys.path.remove(str(root))
    registry = json.loads((root / "plane_mcp" / "gateway_registry.json").read_text(encoding="utf-8"))
    assert registry["source"]["commit"] == EXPECTED_MCP_INVENTORY_SOURCE
    assert registry["manifest_digest"] == "1c9964ff9165b528601fb5cb5e98cb68ae70a88865cfefbbf40a7c25a310be06"
    assert registry["tool_count"] == 177
    assert Counter(action["registration"] for action in registry["actions"].values()) == Counter(
        {"gateway": 86, "unsupported": 90, "local": 1}
    )
    return module, root


def _load_file(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load external SDK module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _empty_package(module_name: str, path: Path) -> types.ModuleType:
    package = types.ModuleType(module_name)
    package.__path__ = [str(path)]
    package.__package__ = module_name
    sys.modules[module_name] = package
    return package


def _load_sdk_contracts() -> tuple[Any, Any, Any, Any, Any]:
    root = _external_root(SDK_ROOT_ENV, SDK_ROOT_DEFAULT, EXPECTED_SDK_TIP)
    prefix = "plane_external_sdk"
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            del sys.modules[name]
    package_root = root / "plane"
    _empty_package(prefix, package_root)
    _empty_package(f"{prefix}.api", package_root / "api")
    errors = _empty_package(f"{prefix}.errors", package_root / "errors")
    _empty_package(f"{prefix}.models", package_root / "models")

    error_module = _load_file(f"{prefix}.errors.errors", package_root / "errors" / "errors.py")
    for name in (
        "ConfigurationError",
        "HttpError",
        "OperationDeniedError",
        "OperationGatewayError",
        "OperationOutcomeUnknownError",
        "OperationUnsupportedError",
    ):
        setattr(errors, name, getattr(error_module, name))
    gateway_models = _load_file(
        f"{prefix}.models.operation_gateway",
        package_root / "models" / "operation_gateway.py",
    )
    config = importlib.import_module(f"{prefix}.config")
    importlib.import_module(f"{prefix}.api.base_resource")
    operations = importlib.import_module(f"{prefix}.api.operations")
    return (
        config.Configuration,
        operations.Operations,
        gateway_models.OperationRequest,
        gateway_models.canonical_json_size,
        errors.OperationGatewayError,
    )


class _MCPResponse:
    def __init__(self, response: Any):
        self.status_code = response.status_code
        self._body = response.json()

    def json(self) -> dict[str, Any]:
        return self._body


class _DjangoMCPTransport:
    def __init__(self, client: APIClient):
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> _MCPResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        request_headers = {
            f"HTTP_{name.upper().replace('-', '_')}": value
            for name, value in headers.items()
            if name.lower() in {"x-api-key", "authorization"}
        }
        response = self.client.post(urlparse(url).path, json, format="json", **request_headers)
        return _MCPResponse(response)


class _SDKResponse:
    def __init__(self, response: Any):
        self.status_code = response.status_code
        self.content = response.content
        self.headers = {"content-type": "application/json"}
        self.reason = getattr(response, "reason_phrase", "")
        self.text = response.content.decode("utf-8")
        self._body = response.json()

    def json(self) -> dict[str, Any]:
        return self._body


class _DjangoSDKSession:
    def __init__(self, client: APIClient):
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        params: Any,
        timeout: Any,
    ) -> _SDKResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "params": params, "timeout": timeout})
        request_headers = {
            f"HTTP_{name.upper().replace('-', '_')}": value
            for name, value in headers.items()
            if name.lower() in {"x-api-key", "authorization"}
        }
        response = self.client.post(urlparse(url).path, json, format="json", **request_headers)
        return _SDKResponse(response)


@pytest.fixture
def sdk_oauth_user(db, workspace, gateway_project):
    user = User.objects.create(
        email="external-sdk-oauth@plane.so",
        username="external-sdk-oauth",
        is_bot=False,
    )
    APIToken.objects.create(user=user, label="External SDK OAuth test", token=SDK_OAUTH_TOKEN)
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
    ProjectMember.objects.create(project=gateway_project, member=user, role=20, is_active=True)
    return user


def _drain_publications(record: OperationGatewayIdempotency) -> None:
    for publication in record.publications.order_by("kind"):
        dispatch_publication_once(str(publication.id))


def _assert_gateway_audit(receipt: Any, *, caller_id: str, correlation_id: str, operation_id: str) -> None:
    assert receipt.caller_id == caller_id
    assert receipt.correlation_id == correlation_id
    audit = OperationGatewayAudit.objects.get(pk=receipt.audit_receipt)
    assert str(audit.caller_id) == caller_id
    assert audit.correlation_id == correlation_id
    assert audit.operation_id == operation_id


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_external_mcp_client_crosses_plane_gateway_for_read_mutation_replay_archive_delete_and_search(
    workspace,
    gateway_project,
    gateway_issue,
    create_user,
    api_token,
):
    mcp_gateway, _root = _load_mcp_gateway()
    transport = _DjangoMCPTransport(APIClient())
    client = mcp_gateway.HttpOperationGateway(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        credential=api_token.token,
        auth_method="api_key",
        http_client=transport,
    )
    caller_id = str(create_user.id)

    read = client.invoke(
        "retrieve_work_item",
        {"project_id": str(gateway_project.id), "work_item_id": str(gateway_issue.id)},
        correlation_id="mcp-read-correlation",
    )
    assert read.value["id"] == str(gateway_issue.id)
    _assert_gateway_audit(
        read,
        caller_id=caller_id,
        correlation_id="mcp-read-correlation",
        operation_id="work_item.retrieve",
    )

    update_arguments = {
        "project_id": str(gateway_project.id),
        "work_item_id": str(gateway_issue.id),
        "name": "MCP Gateway Renamed",
    }
    first = client.invoke(
        "update_work_item", update_arguments, idempotency_key="mcp-replay-key", correlation_id="mcp-replay"
    )
    record = OperationGatewayIdempotency.objects.get(idempotency_key="mcp-replay-key")
    _drain_publications(record)
    replay = client.invoke(
        "update_work_item", update_arguments, idempotency_key="mcp-replay-key", correlation_id="mcp-replay"
    )
    assert first.value == replay.value
    assert first.replayed is False
    assert replay.replayed is True
    _assert_gateway_audit(
        replay,
        caller_id=caller_id,
        correlation_id="mcp-replay",
        operation_id="work_item.update",
    )
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "MCP Gateway Renamed"
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 1

    archived = client.invoke(
        "manage_work_item_archive",
        {"project_id": str(gateway_project.id), "work_item_id": str(gateway_issue.id), "archive": True},
        correlation_id="mcp-archive-correlation",
    )
    assert archived.value is None
    gateway_issue.refresh_from_db()
    assert gateway_issue.archived_at is not None

    deleted = client.invoke(
        "delete_work_item",
        {"project_id": str(gateway_project.id), "work_item_id": str(gateway_issue.id)},
        correlation_id="mcp-delete-correlation",
    )
    assert deleted.value is None
    assert not Issue.objects.filter(pk=gateway_issue.id).exists()

    search = client.invoke(
        "search_work_items",
        {"project_id": str(gateway_project.id), "query": "Gateway"},
        correlation_id="mcp-search-correlation",
    )
    assert isinstance(search.value, list)
    assert transport.calls
    assert all(call["headers"].get("x-api-key") == api_token.token for call in transport.calls)
    assert all("Authorization" not in call["headers"] for call in transport.calls)
    assert all("caller" not in call["json"] for call in transport.calls)


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_external_mcp_client_preserves_denial_and_unsupported_dispositions_without_side_effect(
    workspace,
    gateway_project,
    gateway_issue,
    create_user,
):
    mcp_gateway, _root = _load_mcp_gateway()
    denied_user = User.objects.create(email="external-mcp-denied@plane.so", username="external-mcp-denied")
    token = APIToken.objects.create(user=denied_user, label="External MCP denied test", token="external-mcp-denied")
    transport = _DjangoMCPTransport(APIClient())
    client = mcp_gateway.HttpOperationGateway(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        credential=token.token,
        auth_method="api_key",
        http_client=transport,
    )

    with pytest.raises(mcp_gateway.GatewayCallError) as denied:
        client.invoke(
            "update_work_item",
            {
                "project_id": str(gateway_project.id),
                "work_item_id": str(gateway_issue.id),
                "name": "Must Not Change",
            },
            idempotency_key="mcp-denied-key",
            correlation_id="mcp-denied-correlation",
        )
    assert denied.value.code == "NOT_AUTHORIZED"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Gateway Issue"
    assert OperationGatewayIdempotency.objects.get(idempotency_key="mcp-denied-key").state == "denied"
    assert OperationGatewayAudit.objects.filter(idempotency_key="mcp-denied-key", caller_id=denied_user.id).exists()

    with pytest.raises(mcp_gateway.GatewayUnsupportedError) as unsupported:
        client.invoke("list_customers", {})
    assert unsupported.value.blocker_code
    assert len(transport.calls) == 1
    assert not AgentActor.objects.filter(workspace=workspace, principal=denied_user).exists()
    assert str(create_user.id) != str(denied_user.id)


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_external_sdk_client_uses_bearer_identity_and_real_gateway_result_boundary(
    workspace,
    gateway_project,
    gateway_issue,
    sdk_oauth_user,
):
    Configuration, Operations, OperationRequest, canonical_json_size, GatewayError = _load_sdk_contracts()
    sdk_session = _DjangoSDKSession(APIClient())
    operations = Operations(Configuration(base_path="http://testserver", access_token=SDK_OAUTH_TOKEN))
    operations.session = sdk_session
    caller_id = str(sdk_oauth_user.id)

    read = operations.execute(
        OperationRequest(
            operation_id="work_item.retrieve",
            workspace_slug=workspace.slug,
            idempotency_key="sdk-read-key",
            correlation_id="sdk-read-correlation",
            input={"project_id": str(gateway_project.id), "issue_id": str(gateway_issue.id)},
        )
    )
    assert read.result["work_item"]["id"] == str(gateway_issue.id)
    assert read.caller.id == caller_id
    assert read.correlation_id == "sdk-read-correlation"
    assert OperationGatewayAudit.objects.filter(
        pk=read.audit_receipt,
        caller_id=sdk_oauth_user.id,
        correlation_id="sdk-read-correlation",
    ).exists()
    assert not AgentActor.objects.filter(workspace=workspace, principal=sdk_oauth_user).exists()

    boundary_issues = [
        Issue.objects.create(
            name=f"sdk-boundary-{index}-" + "x" * (190 - len(f"sdk-boundary-{index}-")),
            project=gateway_project,
            workspace=workspace,
            created_by=sdk_oauth_user,
        )
        for index in range(19)
    ]
    target_prefix = "sdk-boundary-target-"
    target = Issue.objects.create(
        name=target_prefix,
        project=gateway_project,
        workspace=workspace,
        created_by=sdk_oauth_user,
    )
    boundary_issues.append(target)

    def set_target_name(length: int) -> dict[str, Any]:
        target.name = target_prefix + "x" * (length - len(target_prefix))
        target.save(update_fields=["name"])
        return WorkspaceSearchService().search(
            workspace=workspace,
            user=sdk_oauth_user,
            query="sdk-boundary",
            limit=20,
        )

    low, high = len(target_prefix), 255
    exact_search = None
    while low <= high:
        length = (low + high) // 2
        candidate = set_target_name(length)
        candidate_size = canonical_json_size(candidate)
        if candidate_size == MAX_RESULT_BYTES:
            exact_search = candidate
            break
        if candidate_size < MAX_RESULT_BYTES:
            low = length + 1
        else:
            high = length - 1
    assert exact_search is not None, f"event=external_sdk_boundary_setup expected=8192 range={low}:{high}"
    assert canonical_json_size(exact_search) == MAX_RESULT_BYTES
    bounded = operations.execute(
        OperationRequest(
            operation_id="search_workspace",
            workspace_slug=workspace.slug,
            idempotency_key="sdk-boundary-8192",
            correlation_id="sdk-boundary-correlation",
            input={"query": "sdk-boundary", "limit": 20},
        )
    )
    assert canonical_json_size(bounded.result) == MAX_RESULT_BYTES

    target.name = target.name + "x"
    target.save(update_fields=["name"])
    with pytest.raises(GatewayError) as oversized:
        operations.execute(
            OperationRequest(
                operation_id="search_workspace",
                workspace_slug=workspace.slug,
                idempotency_key="sdk-boundary-8193",
                correlation_id="sdk-boundary-8193-correlation",
                input={"query": "sdk-boundary", "limit": 20},
            )
        )
    assert oversized.value.code == "RESULT_TOO_LARGE"
    assert sdk_session.calls
    assert all(call["headers"].get("Authorization") == f"Bearer {SDK_OAUTH_TOKEN}" for call in sdk_session.calls)
    assert all("X-Api-Key" not in call["headers"] for call in sdk_session.calls)
    assert all("caller" not in call["json"] for call in sdk_session.calls)

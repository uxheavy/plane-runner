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
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from rest_framework.test import APIClient

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

MANIFEST_ENV = "PLANE_G4_MANIFEST"
MANIFEST_DEFAULT = Path(__file__).resolve().parents[6] / "tools" / "agent-g4-manifest.json"
MCP_ROOT_ENV = "PLANE_MCP_EXTERNAL_ROOT"
SDK_ROOT_ENV = "PLANE_SDK_EXTERNAL_ROOT"
MCP_ROOT_DEFAULT = "/private/tmp/plane-mcp-pf1-current"
SDK_ROOT_DEFAULT = "/private/tmp/plane-sdk-pf1-current"
SDK_OAUTH_TOKEN = "external-sdk-oauth-token"


def _manifest_pins() -> tuple[str, str]:
    manifest = Path(os.getenv(MANIFEST_ENV, MANIFEST_DEFAULT))
    try:
        pins = json.loads(manifest.read_text(encoding="utf-8"))["pins"]
        return pins["mcpGitlink"], pins["sdkGitlink"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        pytest.fail(f"{MANIFEST_ENV} must contain exact external client pins: {manifest} ({exc})")


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
    expected_mcp, expected_sdk = _manifest_pins()
    root = _external_root(MCP_ROOT_ENV, MCP_ROOT_DEFAULT, expected_mcp)
    sdk_root = _external_root(SDK_ROOT_ENV, SDK_ROOT_DEFAULT, expected_sdk)
    errors_package = types.ModuleType("plane.errors")
    errors_package.__path__ = [str(sdk_root / "plane" / "errors")]
    errors_package.__package__ = "plane.errors"
    sys.modules["plane.errors"] = errors_package
    plane_package = sys.modules.get("plane")
    if plane_package is not None:
        setattr(plane_package, "errors", errors_package)
    _load_file("plane.errors.errors", sdk_root / "plane" / "errors" / "errors.py")
    for name in list(sys.modules):
        if name == "plane_mcp" or name.startswith("plane_mcp."):
            del sys.modules[name]
    sys.path.insert(0, str(root))
    try:
        importlib.invalidate_caches()
        module = importlib.import_module("plane_mcp.gateway")
    finally:
        sys.path.remove(str(root))
    assert len({route.operation_id for route in module.GATEWAY_ROUTES} | module.SPECIAL_OPERATION_IDS) == 65
    assert all("*" not in route.template for route in module.GATEWAY_ROUTES)
    return module, root


def _load_file(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load external SDK module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_sdk_client() -> tuple[Any, Any, Any]:
    _expected_mcp, expected_sdk = _manifest_pins()
    root = _external_root(SDK_ROOT_ENV, SDK_ROOT_DEFAULT, expected_sdk)
    prefix = "plane_external_sdk"
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            del sys.modules[name]
    package_root = root / "plane"
    spec = importlib.util.spec_from_file_location(
        prefix,
        package_root / "__init__.py",
        submodule_search_locations=[str(package_root)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load external SDK package {package_root}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[prefix] = module
    # The SDK keeps its published ``plane.*`` absolute imports. Isolate that
    # namespace while loading it so Plane's server package cannot satisfy an
    # SDK import such as ``plane.api.base_resource``.
    server_plane_modules = {
        name: value
        for name, value in sys.modules.items()
        if name == "plane" or name.startswith("plane.")
    }
    for name in server_plane_modules:
        del sys.modules[name]
    sys.modules["plane"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name in list(sys.modules):
            if name == "plane" or name.startswith("plane."):
                del sys.modules[name]
        sys.modules.update(server_plane_modules)
    models = importlib.import_module(f"{prefix}.models.work_items")
    query_params = importlib.import_module(f"{prefix}.models.query_params")
    return module.PlaneClient, models.UpdateWorkItem, query_params.WorkItemQueryParams


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
    read_client = mcp_gateway.PlaneGatewayTransport(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        api_key=api_token.token,
        session=transport,
        call_id="mcp-read",
    )
    caller_id = str(create_user.id)

    read = read_client.request(
        "GET",
        f"/workspaces/{workspace.slug}/projects/{gateway_project.id}/work-items/{gateway_issue.id}",
    )
    assert read["id"] == str(gateway_issue.id)
    assert OperationGatewayAudit.objects.filter(
        caller_id=caller_id,
        operation_id="work_item.retrieve",
        idempotency_key="mcp:mcp-read:1",
    ).exists()

    update_path = f"/workspaces/{workspace.slug}/projects/{gateway_project.id}/work-items/{gateway_issue.id}"
    first_client = mcp_gateway.PlaneGatewayTransport(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        api_key=api_token.token,
        session=transport,
        call_id="mcp-replay",
    )
    first = first_client.request(
        "PATCH",
        update_path,
        data={"name": "MCP Gateway Renamed"},
    )
    record = OperationGatewayIdempotency.objects.get(idempotency_key="mcp:mcp-replay:1")
    _drain_publications(record)
    replay_client = mcp_gateway.PlaneGatewayTransport(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        api_key=api_token.token,
        session=transport,
        call_id="mcp-replay",
    )
    replay = replay_client.request(
        "PATCH",
        update_path,
        data={"name": "MCP Gateway Renamed"},
    )
    assert first == replay
    assert OperationGatewayAudit.objects.filter(
        idempotency_key="mcp:mcp-replay:1",
        outcome=OperationGatewayAudit.Outcome.REPLAY,
    ).exists()
    assert OperationGatewayAudit.objects.filter(
        caller_id=caller_id,
        operation_id="work_item.update",
        idempotency_key="mcp:mcp-replay:1",
    ).exists()
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "MCP Gateway Renamed"
    assert IssueActivity.objects.filter(issue_id=gateway_issue.id, field="name").count() == 1

    archived = first_client.request(
        "POST",
        f"{update_path}/archive",
        data={"archive": True},
    )
    assert archived is None
    gateway_issue.refresh_from_db()
    assert gateway_issue.archived_at is not None

    unarchived = first_client.request(
        "DELETE",
        f"{update_path}/unarchive",
    )
    assert unarchived is None
    gateway_issue.refresh_from_db()
    assert gateway_issue.archived_at is None

    deleted = first_client.request(
        "DELETE",
        update_path,
    )
    assert deleted is None
    assert not Issue.objects.filter(pk=gateway_issue.id).exists()

    search = first_client.request(
        "GET",
        f"/workspaces/{workspace.slug}/work-items/search",
        params={"search": "Gateway"},
    )
    assert isinstance(search, list)
    assert transport.calls
    assert all(
        [value for name, value in call["headers"].items() if name.lower() == "x-api-key"]
        == [api_token.token]
        for call in transport.calls
    )
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
    client = mcp_gateway.PlaneGatewayTransport(
        base_url="http://testserver",
        workspace_slug=workspace.slug,
        api_key=token.token,
        session=transport,
        call_id="mcp-denied",
    )

    with pytest.raises(mcp_gateway.HttpError) as denied:
        client.request(
            "PATCH",
            f"/workspaces/{workspace.slug}/projects/{gateway_project.id}/work-items/{gateway_issue.id}",
            data={"name": "Must Not Change"},
        )
    assert denied.value.response["code"] == "NOT_AUTHORIZED"
    assert "result" not in denied.value.response
    assert "work_item" not in denied.value.response
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Gateway Issue"
    assert OperationGatewayIdempotency.objects.get(idempotency_key="mcp:mcp-denied:1").state == "denied"
    assert OperationGatewayAudit.objects.filter(idempotency_key="mcp:mcp-denied:1", caller_id=denied_user.id).exists()

    with pytest.raises(mcp_gateway.GatewayCompatibilityError) as unsupported:
        client.request("GET", f"/workspaces/{workspace.slug}/customers")
    assert unsupported.value.code == "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE"
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
    mcp_gateway, _root = _load_mcp_gateway()
    PlaneClient, UpdateWorkItem, WorkItemQueryParams = _load_sdk_client()
    transport = _DjangoMCPTransport(APIClient())
    client = PlaneClient(
        base_url="http://testserver",
        access_token=SDK_OAUTH_TOKEN,
        gateway_transport=mcp_gateway.PlaneGatewayTransport(
            base_url="http://testserver",
            workspace_slug=workspace.slug,
            access_token=SDK_OAUTH_TOKEN,
            session=transport,
            call_id="sdk-read",
        ),
    )
    caller_id = str(sdk_oauth_user.id)

    read = client.work_items.retrieve(
        workspace.slug,
        str(gateway_project.id),
        str(gateway_issue.id),
    )
    assert read.id == str(gateway_issue.id)
    assert OperationGatewayAudit.objects.filter(
        caller_id=caller_id,
        operation_id="work_item.retrieve",
        idempotency_key="mcp:sdk-read:1",
    ).exists()
    assert not AgentActor.objects.filter(workspace=workspace, principal=sdk_oauth_user).exists()

    small = client.work_items.list(
        workspace.slug,
        str(gateway_project.id),
        params=WorkItemQueryParams(per_page=1),
    )
    assert len(small.results) == 1
    assert len(json.dumps(small.model_dump(), separators=(",", ":")).encode()) <= MAX_RESULT_BYTES

    for index in range(19):
        Issue.objects.create(
            name=f"sdk-boundary-{index}-" + "x" * (190 - len(f"sdk-boundary-{index}-")),
            project=gateway_project,
            workspace=workspace,
            created_by=sdk_oauth_user,
        )
    Issue.objects.create(
        name="sdk-boundary-target-" + "x" * 235,
        project=gateway_project,
        workspace=workspace,
        created_by=sdk_oauth_user,
    )
    with pytest.raises(mcp_gateway.HttpError) as oversized:
        client.work_items.list(
            workspace.slug,
            str(gateway_project.id),
            params=WorkItemQueryParams(per_page=20),
        )
    assert oversized.value.response["code"] == "RESULT_TOO_LARGE"

    denied_user = User.objects.create(email="external-sdk-denied@plane.so", username="external-sdk-denied")
    denied_token = APIToken.objects.create(
        user=denied_user,
        label="External SDK denied test",
        token="external-sdk-denied",
    )
    denied_transport = _DjangoMCPTransport(APIClient())
    denied_client = PlaneClient(
        base_url="http://testserver",
        access_token=denied_token.token,
        gateway_transport=mcp_gateway.PlaneGatewayTransport(
            base_url="http://testserver",
            workspace_slug=workspace.slug,
            access_token=denied_token.token,
            session=denied_transport,
            call_id="sdk-denied",
        ),
    )
    with pytest.raises(mcp_gateway.HttpError) as denied:
        denied_client.work_items.update(
            workspace.slug,
            str(gateway_project.id),
            str(gateway_issue.id),
            UpdateWorkItem(name="Must Not Change"),
        )
    assert denied.value.response["code"] == "NOT_AUTHORIZED"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Gateway Issue"
    assert OperationGatewayIdempotency.objects.get(idempotency_key="mcp:sdk-denied:1").state == "denied"
    assert OperationGatewayAudit.objects.filter(
        caller_id=denied_user.id,
        operation_id="work_item.update",
        idempotency_key="mcp:sdk-denied:1",
    ).exists()
    assert transport.calls
    assert all(call["headers"].get("Authorization") == f"Bearer {SDK_OAUTH_TOKEN}" for call in transport.calls)
    assert all("X-Api-Key" not in call["headers"] for call in transport.calls)
    assert all("caller" not in call["json"] for call in transport.calls)
    assert not AgentActor.objects.filter(workspace=workspace, principal=sdk_oauth_user).exists()

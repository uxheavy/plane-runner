"""High-signal contracts for the Plane-native tool and Code Mode seams."""

from types import SimpleNamespace

import pytest

from plane.agent.code_mode.host import CodeModeBudget, CodeModeHostRPC, HostBinding
from plane.agent.tools.catalog import (
    CATALOG_DIGEST,
    code_mode_callback_names,
    catalog_search,
    describe_operation,
    operation_catalog_snapshot,
)
from plane.agent.tools.disclosure import compose_tool_catalog
from plane.agent.tools.native import NativeToolAdapter
from plane.operation_gateway.catalog import OPERATION_CATALOG


def _profile(**presentation):
    return SimpleNamespace(
        role="worker",
        tool_presentation=presentation,
    )


def _assignment(objective="Rename the assigned work item"):
    return SimpleNamespace(target_ref="target:issue-1", objective=objective)


def _success(operation_id, *, replayed=False):
    return {
        "ok": True,
        "schema_version": "plane.operation/v1",
        "operation_id": operation_id,
        "request_id": "request:1",
        "caller": {"type": "user", "id": "user-1"},
        "workspace": {"slug": "workspace"},
        "idempotency": {"key": "idempotency:1", "replayed": replayed},
        "correlation_id": "correlation:1",
        "audit_receipt": "audit-receipt:1",
        "result": {"items": []},
    }


class RecordingGateway:
    def __init__(self):
        self.calls = []
        self.invalid_requests = []

    def execute(self, request, envelope):
        self.calls.append((request, envelope))
        return _success(envelope["operation_id"]), 200

    def record_invalid_request(self, request, raw_data, *, code, status_code=None):
        self.invalid_requests.append((request, raw_data, code, status_code))
        response = _success(raw_data["operation_id"])
        response["ok"] = False
        response.pop("result", None)
        response["audit_receipt"] = "audit-receipt:rejection"
        response["error"] = {"code": code, "message": code, "retryable": False}
        return response, status_code or 400


def test_catalog_digest_and_discovery_are_complete_and_stable():
    first = operation_catalog_snapshot()
    second = operation_catalog_snapshot()

    assert first["catalogDigest"] == second["catalogDigest"] == CATALOG_DIGEST
    assert {entry["operationId"] for entry in first["operations"]} == set(OPERATION_CATALOG)
    assert {entry["operationId"] for entry in catalog_search("")["operations"]} == set(OPERATION_CATALOG)
    assert describe_operation("search_workspace")["inputSchema"]["type"] == "object"
    assert code_mode_callback_names() == {
        "search": "search_plane_operations",
        "describe": "describe_plane_operation",
        "operation": "call_plane_operation",
    }


def test_disclosure_is_presentation_only_and_assignment_driven():
    catalog = compose_tool_catalog(
        _profile(eager=["work_item.rename"]),
        _assignment(),
    )
    eager = {entry["operationRef"] for entry in catalog["eagerOperations"]}

    assert "operation:search_workspace" in eager
    assert "operation:work_item.rename" in eager
    assert catalog["catalogDigest"] == CATALOG_DIGEST

    with pytest.raises(ValueError, match="authorization|allowlist"):
        compose_tool_catalog(_profile(allowed_operations=["work_item.rename"]), _assignment())


def test_native_adapter_routes_semantic_operation_through_gateway():
    gateway = RecordingGateway()
    request = SimpleNamespace(
        user=SimpleNamespace(id="user-1"),
        agent_actor_ref="actor:actor-1",
    )
    adapter = NativeToolAdapter(
        request=request,
        workspace_slug="workspace",
        actor_ref="actor:actor-1",
        gateway=gateway,
    )

    receipt, status = adapter.invoke(
        "work_item.rename",
        {"project_id": "project-1", "issue_id": "issue-1", "name": "Renamed"},
        idempotency_key="idempotency:native-1",
        correlation_id="correlation:native-1",
    )

    assert status == 200
    assert receipt["ok"] is True
    assert gateway.calls[0][1]["operation_id"] == "work_item.rename"
    assert gateway.calls[0][1]["workspace_slug"] == "workspace"


def test_code_mode_callbacks_bind_identity_budget_and_cancellation_to_gateway():
    gateway = RecordingGateway()
    request = SimpleNamespace(user=SimpleNamespace(id="user-1"))
    binding = HostBinding(
        actor_ref="actor:actor-1",
        workspace_slug="workspace",
        run_ref="run:run-1",
        invocation_ref="invocation:invocation-1",
        catalog_digest=CATALOG_DIGEST,
    )
    host = CodeModeHostRPC(
        gateway=gateway,
        request=request,
        binding=binding,
        budget=CodeModeBudget(input_bytes=1024, output_bytes=2048, duration_ms=1000, calls=2),
        is_cancelled=lambda: False,
    )

    receipt = host.call_operation(
        "work_item.rename",
        {"project_id": "project-1", "issue_id": "issue-1", "name": "Renamed"},
        idempotency_key="idempotency:callback-1",
        correlation_id="correlation:callback-1",
    )

    assert receipt["gatewayReceipt"] == "audit-receipt:1"
    assert receipt["runRef"] == "run:run-1"
    assert receipt["invocationRef"] == "invocation:invocation-1"
    assert gateway.calls[0][1]["operation_id"] == "work_item.rename"
    assert "credential" not in gateway.calls[0][1]
    assert "authorization" not in gateway.calls[0][1]

    cancelled = CodeModeHostRPC(
        gateway=gateway,
        request=request,
        binding=binding,
        budget=CodeModeBudget(input_bytes=1024, output_bytes=2048, duration_ms=1000, calls=2),
        is_cancelled=lambda: True,
    )
    cancelled_receipt = cancelled.call_operation(
        "work_item.read",
        {"project_id": "project-1", "issue_id": "issue-1"},
        idempotency_key="idempotency:callback-cancelled",
        correlation_id="correlation:callback-cancelled",
    )
    assert cancelled_receipt["error"]["code"] == "CANCELLED"
    assert gateway.invalid_requests[-1][2] == "CANCELLED"


def test_code_mode_rejects_unbound_workspace_without_calling_operation():
    gateway = RecordingGateway()
    request = SimpleNamespace(user=SimpleNamespace(id="user-1"))
    binding = HostBinding(
        actor_ref="actor:actor-1",
        workspace_slug="workspace",
        run_ref="run:run-1",
        invocation_ref="invocation:invocation-1",
        catalog_digest=CATALOG_DIGEST,
    )
    host = CodeModeHostRPC(
        gateway=gateway,
        request=request,
        binding=binding,
        budget=CodeModeBudget(input_bytes=1024, output_bytes=2048, duration_ms=1000, calls=1),
        is_cancelled=lambda: False,
    )

    receipt = host.call_operation(
        "work_item.read",
        {"project_id": "project-1", "issue_id": "issue-1"},
        idempotency_key="idempotency:callback-2",
        correlation_id="correlation:callback-2",
        workspace_slug="other-workspace",
    )
    assert receipt["error"]["code"] == "CALLBACK_BINDING_INVALID"
    assert gateway.calls == []


def test_code_mode_rejects_mismatched_trusted_actor_binding():
    gateway = RecordingGateway()
    request = SimpleNamespace(
        user=SimpleNamespace(id="user-1"),
        agent_actor_ref="actor:other",
    )
    binding = HostBinding(
        actor_ref="actor:actor-1",
        workspace_slug="workspace",
        run_ref="run:run-1",
        invocation_ref="invocation:invocation-1",
        catalog_digest=CATALOG_DIGEST,
    )
    host = CodeModeHostRPC(
        gateway=gateway,
        request=request,
        binding=binding,
        budget=CodeModeBudget(input_bytes=1024, output_bytes=2048, duration_ms=1000, calls=1),
        is_cancelled=lambda: False,
    )

    receipt = host.call_operation(
        "work_item.read",
        {"project_id": "project-1", "issue_id": "issue-1"},
        idempotency_key="idempotency:callback-3",
        correlation_id="correlation:callback-3",
    )

    assert receipt["error"]["code"] == "CALLBACK_BINDING_INVALID"
    assert gateway.calls == []

"""High-signal contracts for the Plane-native tool and Code Mode seams."""

from types import SimpleNamespace

import pytest

from plane.agent.code_mode.contracts import CodeModeBudget
from plane.agent.code_mode.isolate import CodeModeIsolateError, CodeModeIsolateRunner
from plane.agent.tools.catalog import (
    CATALOG_DIGEST,
    code_mode_callback_names,
    catalog_search,
    describe_operation,
    operation_catalog_snapshot,
)
from plane.agent.tools.disclosure import MAX_EAGER_OPERATIONS, compose_tool_catalog, progressive_operation_ids
from plane.agent.tools.native import NativeToolAdapter
from plane.operation_gateway.catalog import OPERATION_CATALOG


def _profile(**presentation):
    return SimpleNamespace(role="worker", tool_presentation=presentation)


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
    assert describe_operation("search_workspace")["operation"]["inputSchema"]["type"] == "object"
    assert code_mode_callback_names() == {
        "search": "search_plane_operations",
        "describe": "describe_plane_operation",
        "operation": "call_plane_operation",
        "spill": "spill_plane_result",
    }


def test_work_item_read_discloses_exact_uuid_input_schema():
    assert describe_operation("work_item.read")["operation"]["inputSchema"] == {
        "type": "object",
        "additionalProperties": False,
        "required": ["project_id", "issue_id"],
        "properties": {
            "project_id": {"type": "string", "format": "uuid"},
            "issue_id": {"type": "string", "format": "uuid"},
        },
    }


def test_catalog_search_discloses_nested_describe_input_schema():
    entry = next(item for item in catalog_search("")["operations"] if item["operationId"] == "catalog.describe")

    assert entry["inputSchema"] == describe_operation("catalog.describe")["operation"]["inputSchema"]


def test_composed_eager_catalog_carries_work_item_read_input_schema():
    catalog = compose_tool_catalog(_profile(eager=["work_item.read"]), _assignment())

    eager = next(item for item in catalog["eagerOperations"] if item["operationRef"] == "operation:work_item.read")
    assert set(eager) == {"operationRef", "schemaDigest", "inputSchema", "disclosure"}
    assert eager["inputSchema"] == describe_operation("work_item.read")["operation"]["inputSchema"]
    assert eager["disclosure"] == "eager"


def test_explicit_eager_operations_precede_universal_work_core():
    catalog = compose_tool_catalog(
        _profile(eager=["catalog.search", "catalog.describe", "agent.context.read"]),
        _assignment("Use private context before reading the assigned work item"),
    )
    eager_refs = [entry["operationRef"] for entry in catalog["eagerOperations"]]

    assert eager_refs[:4] == [
        "operation:catalog.search",
        "operation:catalog.describe",
        "operation:agent.context.read",
        "operation:search_workspace",
    ]


def test_explicit_eager_route_does_not_readd_assignment_matching_operations():
    catalog = compose_tool_catalog(
        _profile(eager=["search_workspace", "work_item.read"]),
        _assignment("Use the assigned issue for a typed Code Mode mutation"),
    )
    eager_refs = [entry["operationRef"] for entry in catalog["eagerOperations"]]

    assert eager_refs == ["operation:search_workspace", "operation:work_item.read"]
    assert "work_item.rename" in progressive_operation_ids(catalog)


def test_progressive_disclosure_excludes_eager_prefixed_operation_refs():
    progressive = progressive_operation_ids({"eagerOperations": [{"operationRef": "operation:work_item.rename"}]})

    assert "work_item.rename" not in progressive
    assert set(progressive) == set(OPERATION_CATALOG) - {"work_item.rename"}


def test_disclosure_is_presentation_only_and_assignment_driven():
    catalog = compose_tool_catalog(_profile(eager=["work_item.rename"]), _assignment())
    eager = {entry["operationRef"] for entry in catalog["eagerOperations"]}

    assert "operation:search_workspace" in eager
    assert "operation:work_item.rename" in eager
    assert catalog["catalogDigest"] == CATALOG_DIGEST

    with pytest.raises(ValueError, match="authorization|allowlist"):
        compose_tool_catalog(_profile(allowed_operations=["work_item.rename"]), _assignment())


def test_assignment_disclosure_is_bounded_and_remaining_operations_stay_progressive():
    catalog = compose_tool_catalog(_profile(), _assignment("Produce one reviewable outcome."))

    assert len(catalog["eagerOperations"]) == MAX_EAGER_OPERATIONS
    assert len(progressive_operation_ids(catalog)) == len(OPERATION_CATALOG) - MAX_EAGER_OPERATIONS


def test_native_adapter_requires_trusted_actor_ref_before_gateway_execution():
    gateway = RecordingGateway()
    request = SimpleNamespace(user=SimpleNamespace(id="user-1"))
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

    assert status == 403
    assert receipt["error"]["code"] == "CALLBACK_BINDING_INVALID"
    assert gateway.calls == []


def test_native_adapter_routes_semantic_operation_through_gateway():
    gateway = RecordingGateway()
    request = SimpleNamespace(user=SimpleNamespace(id="user-1"), agent_actor_ref="actor:actor-1")
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


class FakeIsolateHost:
    def __init__(self, *, duration_ms=1000):
        self.budget = CodeModeBudget(
            input_bytes=4096,
            output_bytes=4096,
            duration_ms=duration_ms,
            calls=4,
            spill_bytes=4096,
            input_tokens=100,
            output_tokens=100,
        )
        self.cancelled = False
        self.callbacks = []

    @staticmethod
    def callback_surface():
        return code_mode_callback_names()

    def is_cancelled(self):
        return self.cancelled

    def call_operation(self, operation_id, input_data, *, idempotency_key, correlation_id):
        self.callbacks.append((operation_id, input_data, idempotency_key, correlation_id))
        return {"ok": True, "operationId": operation_id}

    def search_operations(self, query, *, limit, idempotency_key, correlation_id):
        return {"ok": True, "query": query, "limit": limit}

    def describe_operation(self, operation_id, *, idempotency_key, correlation_id):
        return {"ok": True, "operationId": operation_id}

    def spill_result(self, payload):
        return {"ok": True, "bytes": len(payload)}

    def _record_output(self, size):
        if size > self.budget.output_bytes:
            return False
        self.budget.output_bytes -= size
        return True

    def record_execution_usage(self, *, input_tokens, output_tokens, duration_ms):
        assert duration_ms > 0

    def reserve_execution_budget(self, *, input_tokens, output_tokens):
        return None

    def release_execution_budget(self):
        return None


def test_code_mode_child_isolate_routes_only_typed_host_callbacks():
    host = FakeIsolateHost()
    source = """
      export default async function ({host, input}: {host: any; input: any}) {
        return await host.call_plane_operation(
          "work_item.read", input, "idempotency:child-1", "correlation:child-1"
        );
      }
    """

    result = CodeModeIsolateRunner().run(host, source, {"project_id": "project-1"})

    assert result == {"ok": True, "operationId": "work_item.read"}
    assert host.callbacks[0][0] == "work_item.read"


def test_code_mode_child_denies_capability_escape_and_imports():
    host = FakeIsolateHost()
    result = CodeModeIsolateRunner().run(
        host,
        """
          export default async function () {
            const escape = (() => {
              try { return Function("return process")(); } catch { return "denied"; }
            })();
            return {
              process: typeof process,
              fetch: typeof fetch,
              require: typeof require,
              module: typeof module,
              env: typeof globalThis.process,
              escape,
            };
          }
        """,
        {},
    )
    assert result == {
        "process": "undefined",
        "fetch": "undefined",
        "require": "undefined",
        "module": "undefined",
        "env": "undefined",
        "escape": "denied",
    }

    with pytest.raises(CodeModeIsolateError, match="imports"):
        CodeModeIsolateRunner().run(host, 'import fs from "node:fs"; export default () => fs;', {})


def test_code_mode_child_denies_zero_duration_before_spawn():
    with pytest.raises(CodeModeIsolateError, match="duration"):
        CodeModeIsolateRunner().run(FakeIsolateHost(duration_ms=0), "export default () => 1", {})


def test_code_mode_child_stops_on_cancellation():
    host = FakeIsolateHost()
    host.cancelled = True

    with pytest.raises(CodeModeIsolateError, match="cancelled"):
        CodeModeIsolateRunner().run(host, "export default () => 1", {})

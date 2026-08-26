import json

import pytest

from plane.agent.code_mode.contracts import (
    MAX_DISCOVERY_BYTES,
    MAX_DISCOVERY_METHODS,
    MAX_EXECUTE_INPUT_BYTES,
    MAX_RETURNED_VALUE_BYTES,
)
from plane.agent.code_mode.host import CodeModeHostRPC
from plane.agent.code_mode.isolate import CodeModeIsolateError, CodeModeIsolateRunner
from plane.agent.runtime.host_rpc import PlaneGatewayHostPort


class FakePlaneHost:
    def __init__(self):
        from plane.agent.code_mode.contracts import CodeModeBudget

        self.budget = CodeModeBudget(65_536, 65_536, 10_000, 16, 65_536, 1, 1)
        self.cancelled = False
        self.calls = []
        self.finished = []

    def is_cancelled(self):
        return self.cancelled

    @staticmethod
    def plane_callback_surface():
        return {"resource": "call_plane_resource", "finish": "finish_plane"}

    def invoke_resource(self, path, args):
        self.calls.append((path, args))
        return {"status": "ok", "value": {"name": "before"}}

    def finish_plane(self, value):
        self.finished.append(value)
        return {"__plane_finish__": "completed"}

    def reserve_execution_budget(self, **_kwargs):
        return None

    def _record_output(self, _size):
        return True

    def record_execution_usage(self, **_kwargs):
        return None

    def release_execution_budget(self):
        return None


def test_model_contract_is_exactly_two_tools_and_hides_legacy_protocol():
    tools = PlaneGatewayHostPort.model_tools()

    assert set(tools) == {"Plane:discover", "Plane:execute"}
    assert tools["Plane:discover"]["inputSchema"]["properties"]["query"]["maxLength"] == 500
    assert tools["Plane:execute"]["inputSchema"]["properties"]["code"]["maxLength"] == MAX_EXECUTE_INPUT_BYTES
    encoded = json.dumps(tools, sort_keys=True)
    for hidden in ("modelToolset", "plane_operation", "plane_execute_typescript", "plane_publish", "preparedCallRef"):
        assert hidden not in encoded


def test_discovery_is_bounded_and_replaces_the_declaration_slot():
    host = object.__new__(CodeModeHostRPC)
    host._snapshot = {
        "assignment": {
            "targetRef": "target:issue:1",
            "objective": "rename the work item",
            "acceptanceCriteria": [],
        }
    }
    host._plane_methods = host._initial_plane_methods()

    result = host.discover("rename one work item")
    assert result["status"] == "ok"
    assert len(result["declarations"].encode()) <= MAX_DISCOVERY_BYTES
    assert len(host._plane_methods) <= MAX_DISCOVERY_METHODS
    assert "preparedCallRef" not in result["declarations"]

    broad = host.discover("agent")
    assert broad["status"] == "error"
    assert broad["error"]["recovery"] == "narrow_query"


def test_restricted_child_receives_only_frozen_task_and_plane_and_supports_read_mutation():
    host = FakePlaneHost()
    result = CodeModeIsolateRunner().run_plane(
        host,
        """
        const before = await plane.workItems.retrieve(task.target);
        await plane.workItems.update(task.target, { name: 'after' });
        return { frozenTask: Object.isFrozen(task), frozenPlane: Object.isFrozen(plane), before };
        """,
        {"target": "target:issue:1", "objective": "rename", "acceptanceCriteria": []},
        [
            {"path": "workItems.retrieve", "operationId": "work_item.read"},
            {"path": "workItems.update", "operationId": "work_item.rename"},
        ],
    )

    assert result == {"frozenTask": True, "frozenPlane": True, "before": {"name": "before"}}
    assert [call[0] for call in host.calls] == ["workItems.retrieve", "workItems.update"]


def test_finish_is_non_returning_and_missing_finish_is_actionable():
    host = FakePlaneHost()
    finished = CodeModeIsolateRunner().run_plane(
        host,
        "await plane.finish({ kind: 'completed', summary: 'done' }); return 'unreachable';",
        {"target": "target:issue:1", "objective": "finish", "acceptanceCriteria": []},
        [],
    )
    assert finished == {"__plane_finish__": "completed"}
    assert len(host.finished) == 1

    with pytest.raises(CodeModeIsolateError, match="execution failed") as missing:
        CodeModeIsolateRunner().run_plane(
            host,
            "const value = 1;",
            {"target": "target:issue:1", "objective": "finish", "acceptanceCriteria": []},
            [],
        )
    assert missing.value.code == "MISSING_TERMINAL_PUBLICATION"


def test_execute_bounds_are_explicit():
    assert MAX_EXECUTE_INPUT_BYTES == 8192
    assert MAX_RETURNED_VALUE_BYTES == 8 * 1024
    assert MAX_DISCOVERY_METHODS == 8
    assert MAX_DISCOVERY_BYTES == 16 * 1024

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from plane.agent.code_mode.contracts import (
    MAX_DISCOVERY_BYTES,
    MAX_DISCOVERY_METHODS,
    MAX_EXECUTE_INPUT_BYTES,
    MAX_RETURNED_VALUE_BYTES,
    PLANE_DISCOVERY_OPERATION,
    PLANE_EXECUTION_OPERATION,
    PlaneToolError,
)
from plane.agent.code_mode.host import CodeModeHostRPC
from plane.agent.code_mode.isolate import (
    CodeModeIsolateError,
    CodeModeIsolateRunner,
    _find_typescript_module,
)
from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run, record_invocation
from plane.agent.lifecycle import services as lifecycle_services
from plane.db.models import AgentRole, OperationGatewayIdempotency, OutcomeSubmission, RunTerminalEvent
from plane.agent.runtime.host_rpc import PlaneGatewayHostPort, PlaneHostCall
from plane.operation_gateway.gateway import OperationGateway


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


def test_typescript_lookup_supports_host_and_shallow_container_layouts(tmp_path):
    repo_root = tmp_path / "repo"
    module_path = repo_root / "apps/api/plane/agent/code_mode/isolate.py"
    typescript = repo_root / "node_modules/.pnpm/typescript@5/node_modules/typescript/lib/typescript.js"
    typescript.parent.mkdir(parents=True)
    typescript.touch()

    assert _find_typescript_module(module_path) == typescript
    assert _find_typescript_module(Path("/code/plane/agent/code_mode/isolate.py")) == Path(
        "/usr/share/node_modules/typescript/lib/typescript.js"
    )


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
    kit = host.task_kit()
    assert set(kit) == {"task", "declarations", "example"}
    assert kit["example"] == "const current = await plane.workItems.retrieve(task.target);"

    broad = host.discover("agent")
    assert broad["status"] == "error"
    assert broad["error"]["recovery"] == "discover_capability"


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


def test_hidden_model_handshake_is_exact_and_returns_plane_statuses():
    class Host:
        def discover(self, query):
            assert query == "read the assigned item"
            return {"status": "ok", "declarations": "declare const plane: unknown;"}

        def execute_plane(self, code):
            assert code == "return {ok: true};"
            return {"status": "returned", "value": {"ok": True}}

    port = object.__new__(PlaneGatewayHostPort)
    port._host = Host()
    port._run_ref = "run:1"
    port._invocation_ref = "invocation:1"
    port._prepared_read_auto_depth = 0
    port._provider_attempt_recorder = None
    for call, expected in (
        (
            PlaneHostCall(
                "run:1",
                "invocation:1",
                "corr:1",
                "discover",
                PLANE_DISCOVERY_OPERATION,
                {"query": "read the assigned item"},
                "model",
            ),
            "ok",
        ),
        (
            PlaneHostCall(
                "run:1",
                "invocation:1",
                "corr:2",
                "code",
                PLANE_EXECUTION_OPERATION,
                {"code": "return {ok: true};"},
                "model",
            ),
            "ok",
        ),
    ):
        assert port.invoke(call).status == expected


def test_realm_constructor_chain_cannot_escape_the_restricted_child():
    host = FakePlaneHost()
    result = CodeModeIsolateRunner().run_plane(
        host,
        'try { return plane.workItems.retrieve.constructor("return process")(); } catch { return "denied"; }',
        {"target": "target:issue:1", "objective": "test", "acceptanceCriteria": []},
        [{"path": "workItems.retrieve", "operationId": "work_item.read"}],
    )
    assert result == "denied"


def test_completed_content_reaches_the_single_lifecycle_seam():
    host = object.__new__(CodeModeHostRPC)
    host._plane_finish_applied = False
    host._execution_reservation = None
    host.invocation = SimpleNamespace(id="invocation:1", created_by=None)
    with patch("plane.agent.code_mode.host.finish_code_mode", return_value=object()) as apply:
        host.finish_plane({"kind": "completed", "summary": "done", "content": "details"})
    assert apply.call_args.kwargs["content"] == "details"


def test_completed_finish_uses_discovered_replacement_slice():
    host = object.__new__(CodeModeHostRPC)
    host._snapshot = {
        "assignment": {"targetRef": "target:issue:1", "objective": "Rename the assigned work item."},
        "toolCatalog": {"server": "Plane", "taskKit": {}},
    }
    host._plane_methods = host._initial_plane_methods()
    host.invocation = SimpleNamespace(invocation_id="invocation:replacement")

    with patch("plane.agent.code_mode.host.OperationGatewayIdempotency.objects.filter") as query:
        query.return_value.values_list.return_value = ["work_item.rename"]
        assert host.discover("rename one work item")["status"] == "ok"
        assert [method["operationId"] for method in host._plane_methods] == ["work_item.rename"]
        host._require_completed_finish_route()


@pytest.mark.django_db(transaction=True)
def test_completed_finish_requires_typed_task_route_before_lifecycle_effects(
    workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(workspace=workspace, project=gateway_project, display_name="Finish gate worker")
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the typed task route.",
        tool_presentation={"model_toolset": "code_mode_only"},
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Rename the assigned work item.",
        acceptance_criteria=["The renamed item is durable."],
    )
    run = create_run(assignment, profile, created_by=create_user)
    invocation = record_invocation(run, trigger="initial")
    host = CodeModeHostRPC(
        gateway=OperationGateway(),
        request=SimpleNamespace(user=actor.principal, META={}, agent_actor_ref=run.snapshot["actorRef"]),
        run=run,
        invocation=invocation,
        is_cancelled=lambda: False,
    )

    with pytest.raises(PlaneToolError) as rejected:
        host.finish_plane({"kind": "completed", "summary": "done"})
    assert rejected.value.code == "FINISH_PRECONDITION"
    assert OutcomeSubmission.objects.filter(run=run).count() == 0
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 0
    assert OperationGatewayIdempotency.objects.count() == 0

    target = run.snapshot["assignment"]["targetRef"]
    assert host.invoke_resource("workItems.retrieve", [target])["status"] == "ok"
    assert host.invoke_resource("workItems.update", [target, {"name": "Renamed"}])["status"] == "ok"
    host.finish_plane({"kind": "completed", "summary": "done"})
    assert OutcomeSubmission.objects.filter(run=run).count() == 1
    assert RunTerminalEvent.objects.filter(run=run, kind="outcome_submission", visible=True).count() == 1


def test_lifecycle_seam_forwards_completed_content_to_outcome_application():
    run = object()
    invocation = SimpleNamespace(pk="invocation:1", created_by=None)
    with (
        patch.object(lifecycle_services, "lock_invocation_path", return_value=(None, run, invocation)),
        patch.object(lifecycle_services, "propose_outcome", return_value=object()) as apply,
    ):
        lifecycle_services.finish_code_mode.__wrapped__(
            invocation,
            kind="completed",
            summary="done",
            content="details",
        )
    assert apply.call_args.kwargs["content"] == "details"


def test_current_declaration_slice_is_type_checked_before_execution():
    host = FakePlaneHost()
    with pytest.raises(CodeModeIsolateError) as raised:
        CodeModeIsolateRunner().run_plane(
            host,
            "return plane.not_declared();",
            {"target": "target:issue:1", "objective": "test", "acceptanceCriteria": []},
            [],
            "declare const task: Readonly<{target: string}>; declare const plane: Readonly<{}>;",
        )
    assert raised.value.code == "TYPE_CHECK_FAILED"


@pytest.mark.parametrize(
    "kind,field",
    [("completed", "summary"), ("waiting_for_input", "question"), ("blocked", "reason")],
)
def test_all_plane_finish_kinds_stop_the_child_exactly_once(kind, field):
    host = FakePlaneHost()
    host.finish_plane = lambda value: (host.finished.append(value) or {"__plane_finish__": value["kind"]})
    value = {"kind": kind, field: "bounded"}
    result = CodeModeIsolateRunner().run_plane(
        host,
        f"await plane.finish({json.dumps(value)}); return 'unreachable';",
        {"target": "target:issue:1", "objective": "finish", "acceptanceCriteria": []},
        [],
    )
    assert result == {"__plane_finish__": kind}
    assert host.finished == [value]


def test_execute_bounds_are_explicit():
    assert MAX_EXECUTE_INPUT_BYTES == 8192
    assert MAX_RETURNED_VALUE_BYTES == 8 * 1024
    assert MAX_DISCOVERY_METHODS == 8
    assert MAX_DISCOVERY_BYTES == 16 * 1024

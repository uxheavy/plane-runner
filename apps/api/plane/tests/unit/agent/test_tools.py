# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""High-signal contracts for the Plane-native tool and Code Mode seams."""

from types import SimpleNamespace

import pytest

from plane.agent.code_mode.contracts import CodeModeBudget
from plane.agent.code_mode.isolate import CodeModeIsolateError, CodeModeIsolateRunner
from plane.operation_gateway.catalog import (
    CATALOG_DIGEST,
    OPERATION_CATALOG,
    code_mode_callback_names,
    catalog_search,
    describe_operation,
    operation_catalog_snapshot,
)
from plane.agent.tools.disclosure import MAX_EAGER_OPERATIONS, compose_tool_catalog


def _profile(**presentation):
    return SimpleNamespace(role="worker", tool_presentation=presentation)


def _assignment(objective="Rename the assigned work item"):
    return SimpleNamespace(target_ref="target:issue-1", objective=objective)


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
    assert eager["inputSchema"] == {
        "type": "object",
        "additionalProperties": False,
        "required": ["preparedCallRef"],
        "properties": {
            "preparedCallRef": {
                "type": "string",
                "minLength": len("prepared-call:"),
                "maxLength": 256,
            }
        },
    }
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
    assert "work_item.rename" in set(OPERATION_CATALOG).difference(
        {ref.removeprefix("operation:") for ref in eager_refs}
    )


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
    eager_ids = {entry["operationRef"].removeprefix("operation:") for entry in catalog["eagerOperations"]}
    assert len(set(OPERATION_CATALOG) - eager_ids) == len(OPERATION_CATALOG) - MAX_EAGER_OPERATIONS


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
        self.max_inline_result_bytes = 4096

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

    def record_execution_usage(self, *, input_bytes, input_tokens, output_tokens, duration_ms):
        assert duration_ms > 0

    def reserve_execution_budget(self, *, input_bytes, input_tokens, output_tokens):
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


def test_code_mode_child_resolves_node_before_restricting_child_path(tmp_path, monkeypatch):
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nprintf '%s\\n' --permission\n", encoding="utf-8")
    node.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    runner = CodeModeIsolateRunner()

    assert runner.node_path == str(node)
    assert runner._permission_flag() == "--permission"


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


def test_code_mode_child_spills_results_above_the_inline_ceiling():
    host = FakeIsolateHost()
    host.max_inline_result_bytes = 16

    result = CodeModeIsolateRunner().run(
        host,
        'export default () => "x".repeat(100)',
        {},
    )

    assert result == {"spilled": {"ok": True, "bytes": 102}}, result


def test_code_mode_child_preserves_bounded_callback_error_codes():
    host = FakeIsolateHost()

    class ObservationLimitError(RuntimeError):
        code = "OBSERVATION_LIMIT"

    def fail_callback(*args, **kwargs):
        raise ObservationLimitError("too many observations")

    host.call_operation = fail_callback
    with pytest.raises(CodeModeIsolateError) as raised:
        CodeModeIsolateRunner().run(
            host,
            """
                export default async function ({host}: {host: any}) {
                    return await host.call_plane_operation(
                        "work_item.read", {}, "idempotency:observation-limit", "correlation:observation-limit"
                    );
                }
            """,
            {},
        )

    assert raised.value.code == "OBSERVATION_LIMIT"
    assert raised.value.error_class == "callback_or_protocol"


@pytest.mark.parametrize(
    ("source", "error_class"),
    (
        ("export default (", "module_parse_or_load"),
        ("export const value = 1", "default_export_missing"),
        ("export default () => { throw new Error('private') }", "execution_runtime"),
    ),
)
def test_code_mode_child_reports_only_finite_error_class(source, error_class):
    with pytest.raises(CodeModeIsolateError) as raised:
        CodeModeIsolateRunner().run(FakeIsolateHost(), source, {})

    assert raised.value.code == "CODE_MODE_FAILED"
    assert raised.value.error_class == error_class
    assert "private" not in str(raised.value)


def test_code_mode_child_stops_on_cancellation():
    host = FakeIsolateHost()
    host.cancelled = True

    with pytest.raises(CodeModeIsolateError, match="cancelled"):
        CodeModeIsolateRunner().run(host, "export default () => 1", {})

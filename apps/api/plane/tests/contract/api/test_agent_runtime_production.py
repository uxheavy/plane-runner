from __future__ import annotations

from plane.agent.code_mode.contracts import CodeModeBudget
from plane.agent.code_mode.isolate import CodeModeIsolateRunner
from plane.operation_gateway.catalog import code_mode_callback_names

from .test_production_runtime_configuration import _boot_settings, _settings_environment


class _ProductionCodeModeHost:
    def __init__(self):
        self.budget = CodeModeBudget(
            input_bytes=4096,
            output_bytes=4096,
            duration_ms=1000,
            calls=4,
            spill_bytes=4096,
            input_tokens=100,
            output_tokens=100,
        )
        self.callbacks = []
        self.max_inline_result_bytes = 4096

    @staticmethod
    def callback_surface():
        return code_mode_callback_names()

    @staticmethod
    def is_cancelled():
        return False

    def call_operation(self, operation_id, input_data, *, idempotency_key, correlation_id):
        self.callbacks.append((operation_id, input_data, idempotency_key, correlation_id))
        return {"ok": True, "operationId": operation_id, "input": input_data}

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


def test_agent_runtime_production_executes_structural_typescript_rename():
    host = _ProductionCodeModeHost()
    source = """
        export default async function ({host, input}: {
            host: {
                call_plane_operation: (
                    operationId: string,
                    input: Record<string, unknown>,
                    idempotencyKey: string,
                    correlationId: string
                ) => Promise<Record<string, unknown>>;
            };
            input: Record<string, unknown>;
        }): Promise<Record<string, unknown>> {
            const renameInput = {
                project_id: input.project_id as string,
                issue_id: input.issue_id as string,
                name: "G4 production renamed"
            };
            return await host.call_plane_operation(
                "work_item.rename",
                renameInput,
                "idempotency:g4-production-typescript",
                "correlation:g4-production-typescript"
            );
        }
    """

    result = CodeModeIsolateRunner().run(
        host,
        source,
        {"project_id": "project-g4", "issue_id": "issue-g4"},
    )

    assert result["ok"] is True
    assert result["operationId"] == "work_item.rename"
    assert result["input"] == {
        "project_id": "project-g4",
        "issue_id": "issue-g4",
        "name": "G4 production renamed",
    }
    assert host.callbacks == [
        (
            "work_item.rename",
            {
                "project_id": "project-g4",
                "issue_id": "issue-g4",
                "name": "G4 production renamed",
            },
            "idempotency:g4-production-typescript",
            "correlation:g4-production-typescript",
        )
    ]


def test_agent_runtime_production_accepts_a_bound_url_and_disposable_secret():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            "DATABASE_URL": "postgresql://plane_runtime:runtime@db/plane",
        }
    )
    result = _boot_settings(environment)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


def test_agent_runtime_production_rejects_missing_runtime_url():
    environment = _settings_environment()
    environment.pop("PLANE_AGENT_RUNTIME_URL")
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "PLANE_AGENT_RUNTIME_URL" in result.stderr


def test_agent_runtime_production_rejects_invalid_url_without_silent_none_fallback():
    environment = _settings_environment()
    environment["PLANE_AGENT_RUNTIME_URL"] = "not-a-url"
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "Production Agent runtime configuration is invalid" in result.stderr
    assert "not-a-url" not in result.stderr


def test_agent_runtime_production_rejects_missing_runtime_credential():
    environment = _settings_environment()
    environment.pop("PLANE_AGENT_RUNTIME_SECRET")
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "PLANE_AGENT_RUNTIME_SECRET" in result.stderr


def test_agent_runtime_production_rejects_placeholder_runtime_credential():
    environment = _settings_environment()
    environment["PLANE_AGENT_RUNTIME_SECRET"] = "change-this-runtime-password"
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "Production Agent runtime configuration is invalid" in result.stderr

"""The narrow child-process boundary for generated TypeScript Code Mode."""

from __future__ import annotations

import json
import os
import resource
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any

from plane.agent.lifecycle.runtime_contract import canonical_json


MAX_PROTOCOL_LINE_BYTES = 1_048_576
_RUNNER = Path(__file__).with_name("runner.mjs")


class CodeModeIsolateError(RuntimeError):
    """A child isolate or closed host protocol failed closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CodeModeIsolateRunner:
    """Run generated source in Node's permissioned child and null VM context.

    Node's built-in permission model denies child process, worker, network, and
    filesystem access.  The generated module is evaluated in a null-prototype
    ``vm.SourceTextModule`` context with string/wasm code generation disabled;
    imports are rejected.  The parent is the only owner of host callbacks.
    """

    def __init__(self, *, node_path: str | None = None, runner_path: Path = _RUNNER) -> None:
        self.node_path = node_path or os.environ.get("PLANE_CODE_MODE_NODE", "node")
        self.runner_path = runner_path
        if not self.runner_path.is_file():
            raise CodeModeIsolateError("ISOLATE_UNAVAILABLE", "Code Mode child runner is unavailable")

    def run(
        self,
        host: Any,
        source: str,
        input_data: dict[str, Any],
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> Any:
        if not isinstance(source, str) or not source.strip():
            raise CodeModeIsolateError("VALIDATION_ERROR", "Code Mode source must be non-empty TypeScript")
        if not isinstance(input_data, dict):
            raise CodeModeIsolateError("VALIDATION_ERROR", "Code Mode input must be an object")
        if any(
            getattr(host.budget, field, 0) <= 0
            for field in (
                "input_tokens",
                "output_tokens",
                "duration_ms",
                "input_bytes",
                "output_bytes",
                "calls",
                "spill_bytes",
            )
        ):
            raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode duration or cumulative budget is exhausted")
        try:
            reserve_execution_budget = getattr(host, "reserve_execution_budget", None)
            if reserve_execution_budget is not None:
                reserve_execution_budget(input_tokens=input_tokens, output_tokens=output_tokens)
        except Exception as exc:
            raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode execution budget is exhausted") from exc
        start = time.monotonic()
        env = {"PATH": os.path.dirname(self.node_path) or os.defpath, "NODE_NO_WARNINGS": "1"}
        sandbox = getattr(host, "sandbox", None)
        if sandbox is None:
            from .contracts import SandboxPolicy

            sandbox = SandboxPolicy()
        permission_flag = self._permission_flag()
        command = [
            self.node_path,
            permission_flag,
            "--no-addons",
            "--no-global-search-paths",
            "--experimental-vm-modules",
            "--disable-proto=throw",
            f"--allow-fs-read={self.runner_path}",
            str(self.runner_path),
        ]
        completed = False
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.runner_path.parent),
                env=env,
                start_new_session=True,
                text=False,
                preexec_fn=self._resource_limits(sandbox),
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise CodeModeIsolateError("ISOLATE_UNAVAILABLE", "Code Mode child could not start") from exc

        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            self._write(
                process,
                {
                    "type": "run",
                    "source": source,
                    "input": input_data,
                    "callbacks": host.callback_surface(),
                },
            )
            result = self._read_protocol(process, selector, host, start)
            result_size = len(canonical_json(result).encode("utf-8"))
            if result_size > host.budget.output_bytes:
                spilled = host.spill_result(canonical_json(result))
                if not spilled.get("ok"):
                    raise CodeModeIsolateError("SPILL_EXCEEDED", "Code Mode result spill exceeded its bound")
                result = {"spilled": spilled}
            if not host._record_output(len(canonical_json(result).encode("utf-8"))):
                raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode output budget is exhausted")
            host.record_execution_usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=max(1, int((time.monotonic() - start) * 1000)),
            )
            completed = True
            return result
        finally:
            selector.close()
            self._terminate(process)
            if not completed:
                release_execution_budget = getattr(host, "release_execution_budget", None)
                if release_execution_budget is not None:
                    release_execution_budget()

    def _read_protocol(self, process, selector, host, started: float) -> Any:
        assert process.stdout is not None
        assert process.stdin is not None
        while True:
            if host.is_cancelled():
                raise CodeModeIsolateError("CANCELLED", "Code Mode was cancelled")
            if (time.monotonic() - started) * 1000 >= host.budget.duration_ms:
                raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode duration budget is exhausted")
            events = selector.select(0.05)
            if not events:
                if process.poll() is not None:
                    raise CodeModeIsolateError("CODE_MODE_FAILED", "Code Mode child exited without a result")
                continue
            raw = process.stdout.readline(MAX_PROTOCOL_LINE_BYTES + 1)
            if not raw:
                raise CodeModeIsolateError("CODE_MODE_FAILED", "Code Mode child closed the host protocol")
            if len(raw) > MAX_PROTOCOL_LINE_BYTES or not raw.endswith(b"\n"):
                raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode protocol frame is oversized")
            try:
                frame = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode protocol frame is invalid JSON") from exc
            if not isinstance(frame, dict):
                raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode protocol frame is not an object")
            if frame.get("type") == "result":
                return frame.get("value")
            if frame.get("type") == "error":
                raise CodeModeIsolateError(
                    str(frame.get("code", "CODE_MODE_FAILED")),
                    str(frame.get("message", "Code Mode failed")),
                )
            if frame.get("type") != "callback":
                raise CodeModeIsolateError("PROTOCOL_ERROR", "Unknown Code Mode protocol frame")
            receipt = self._dispatch_callback(host, frame)
            self._write(process, {"type": "callback_result", "id": frame.get("id"), "receipt": receipt})

    @staticmethod
    def _dispatch_callback(host, frame: dict[str, Any]) -> dict[str, Any]:
        callback_id = frame.get("id")
        kind = frame.get("kind")
        args = frame.get("args")
        if not isinstance(callback_id, str) or not isinstance(args, list):
            raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode callback is malformed")
        callback_names = host.callback_surface()
        if frame.get("name") != callback_names.get(kind):
            raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode callback name is not catalog-bound")
        try:
            if kind == "operation" and len(args) == 4:
                operation_id, input_data, idempotency_key, correlation_id = args
                return host.call_operation(
                    operation_id,
                    input_data,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            if kind == "search" and len(args) in {3, 4}:
                query = args[0]
                limit = args[1]
                idempotency_key = args[2]
                correlation_id = args[3] if len(args) == 4 else idempotency_key
                return host.search_operations(
                    query,
                    limit=limit,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            if kind == "describe" and len(args) == 3:
                return host.describe_operation(
                    args[0],
                    idempotency_key=args[1],
                    correlation_id=args[2],
                )
            if kind == "spill" and len(args) == 1:
                return host.spill_result(args[0])
        except (TypeError, ValueError, AgentProtocolError) as exc:
            raise CodeModeIsolateError("CALLBACK_FAILED", "Code Mode callback failed closed") from exc
        raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode callback arguments are invalid")

    @staticmethod
    def _write(process, frame: dict[str, Any]) -> None:
        assert process.stdin is not None
        try:
            encoded = json.dumps(frame, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            if len(encoded) > MAX_PROTOCOL_LINE_BYTES:
                raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode protocol frame is oversized")
            process.stdin.write(encoded)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodeModeIsolateError("PROTOCOL_ERROR", "Code Mode host protocol closed") from exc

    @staticmethod
    def _terminate(process) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)

    def _permission_flag(self) -> str:
        try:
            help_result = subprocess.run(
                [self.node_path, "--help"],
                check=False,
                capture_output=True,
                text=True,
                env={"PATH": os.path.dirname(self.node_path) or os.defpath},
            )
        except OSError as exc:
            raise CodeModeIsolateError("ISOLATE_UNAVAILABLE", "Code Mode Node runtime is unavailable") from exc
        help_text = f"{help_result.stdout}\n{help_result.stderr}"
        if "--permission" in help_text:
            return "--permission"
        if "--experimental-permission" in help_text:
            return "--experimental-permission"
        raise CodeModeIsolateError("ISOLATE_UNAVAILABLE", "Node permission isolation is unavailable")

    @staticmethod
    def _resource_limits(sandbox) -> Any:
        def apply_limits() -> None:
            limits = (
                (getattr(resource, "RLIMIT_CPU", None), sandbox.cpu_seconds),
                (getattr(resource, "RLIMIT_AS", None), sandbox.memory_bytes),
                (getattr(resource, "RLIMIT_NPROC", None), sandbox.pids_limit),
            )
            for resource_kind, limit in limits:
                if resource_kind is not None:
                    resource.setrlimit(resource_kind, (limit, limit))

        return apply_limits


class AgentProtocolError(ValueError):
    """Reserved for typed host protocol validation failures."""

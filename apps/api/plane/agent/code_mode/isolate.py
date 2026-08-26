"""The narrow child-process boundary for generated TypeScript Code Mode."""

from __future__ import annotations

import json
import os
import resource
import selectors
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from plane.agent.lifecycle.runtime_contract import canonical_json

from .contracts import (
    CODE_MODE_ERROR_CLASSES,
    MAX_CODE_MODE_INLINE_RESULT_BYTES,
    MAX_CODE_MODE_SOURCE_BYTES,
    MAX_EXECUTE_INPUT_BYTES,
)


MAX_PROTOCOL_LINE_BYTES = 1_048_576
_RUNNER = Path(__file__).with_name("runner.mjs")


def _find_typescript_module(module_path: Path) -> Path:
    for parent in module_path.resolve().parents:
        typescript = next(parent.glob("node_modules/.pnpm/typescript@*/node_modules/typescript/lib/typescript.js"), None)
        if typescript is not None:
            return typescript
    return Path("/usr/share/node_modules/typescript/lib/typescript.js")


_TYPESCRIPT_MODULE = _find_typescript_module(Path(__file__))
_TYPESCRIPT_MODULE_DIR = str(_TYPESCRIPT_MODULE.parent.parent)


class CodeModeIsolateError(RuntimeError):
    """A child isolate or closed host protocol failed closed."""

    def __init__(self, code: str, message: str, *, error_class: str | None = None, tool_error: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.error_class = error_class if isinstance(error_class, str) and error_class in CODE_MODE_ERROR_CLASSES else None
        self.tool_error = tool_error


class CodeModeIsolateRunner:
    """Run generated source in Node's permissioned child and null VM context.

    Node's built-in permission model denies child process, worker, network, and
    filesystem access.  The generated module is evaluated in a null-prototype
    ``vm.SourceTextModule`` context with string/wasm code generation disabled;
    imports are rejected.  The parent is the only owner of host callbacks.
    """

    def __init__(self, *, node_path: str | None = None, runner_path: Path = _RUNNER) -> None:
        configured_node = node_path or os.environ.get("PLANE_CODE_MODE_NODE", "node")
        self.node_path = (
            shutil.which(configured_node, path=os.environ.get("PATH") or os.defpath) or configured_node
        )
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
        source_limit: int | None = None,
        source_character_limit: int | None = None,
        start_frame: dict[str, Any] | None = None,
    ) -> Any:
        if not isinstance(source, str) or not source.strip():
            raise CodeModeIsolateError("VALIDATION_ERROR", "Code Mode source must be non-empty TypeScript")
        if source_character_limit is not None and len(source) > source_character_limit:
            raise CodeModeIsolateError("SOURCE_TOO_LARGE", "Code Mode source exceeds its character bound")
        if source_character_limit is None and len(source.encode("utf-8")) > (source_limit or MAX_CODE_MODE_SOURCE_BYTES):
            raise CodeModeIsolateError("SOURCE_TOO_LARGE", "Code Mode source exceeds its size bound")
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
        if host.is_cancelled():
            raise CodeModeIsolateError("CANCELLED", "Code Mode was cancelled")
        input_bytes = len(canonical_json({"source": source, "input": input_data}).encode("utf-8"))
        try:
            reserve_execution_budget = getattr(host, "reserve_execution_budget", None)
            if reserve_execution_budget is not None:
                reserve_execution_budget(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    input_bytes=input_bytes,
                )
        except Exception as exc:
            raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode execution budget is exhausted") from exc
        start = time.monotonic()
        env = {
            "PATH": os.path.dirname(self.node_path) or os.defpath,
            "NODE_NO_WARNINGS": "1",
            "PLANE_CODE_MODE_TYPESCRIPT": str(_TYPESCRIPT_MODULE),
        }
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
            f"--allow-fs-read={_TYPESCRIPT_MODULE_DIR}",
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
                    "callbacks": (
                        host.plane_callback_surface()
                        if (start_frame or {}).get("mode") == "plane"
                        else host.callback_surface()
                    ),
                    **(start_frame or {}),
                },
            )
            result = self._read_protocol(process, selector, host, start)
            result_size = len(canonical_json(result).encode("utf-8"))
            is_finish = isinstance(result, dict) and "__plane_finish__" in result
            if not is_finish:
                if (start_frame or {}).get("mode") != "plane":
                    inline_limit = min(
                        host.budget.output_bytes,
                        getattr(host, "max_inline_result_bytes", MAX_CODE_MODE_INLINE_RESULT_BYTES),
                    )
                    if result_size > inline_limit:
                        spilled = host.spill_result(canonical_json(result))
                        if not spilled.get("ok"):
                            error = spilled.get("error") if isinstance(spilled, dict) else None
                            code = error.get("code") if isinstance(error, dict) else None
                            raise CodeModeIsolateError(
                                str(code or "SPILL_EXCEEDED"),
                                "Code Mode result spill exceeded its bound",
                            )
                        result = {"spilled": spilled}
                if not host._record_output(len(canonical_json(result).encode("utf-8"))):
                    raise CodeModeIsolateError("BUDGET_EXCEEDED", "Code Mode output budget is exhausted")
                host.record_execution_usage(
                    input_bytes=input_bytes,
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

    def run_plane(
        self,
        host: Any,
        code: str,
        task: dict[str, Any],
        methods: list[dict[str, str]],
        declarations: str | None = None,
    ) -> Any:
        """Run an async function body with only the frozen Plane facade."""

        return self.run(
            host,
            code,
            {"task": task, "methods": methods, **({"declarations": declarations} if declarations is not None else {})},
            source_character_limit=MAX_EXECUTE_INPUT_BYTES,
            start_frame={"mode": "plane"},
        )

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
                    raise CodeModeIsolateError(
                        "CODE_MODE_FAILED",
                        "Code Mode child exited without a result",
                        error_class="child_exit_no_result",
                    )
                continue
            raw = process.stdout.readline(MAX_PROTOCOL_LINE_BYTES + 1)
            if not raw:
                raise CodeModeIsolateError(
                    "CODE_MODE_FAILED",
                    "Code Mode child closed the host protocol",
                    error_class="child_exit_no_result",
                )
            if len(raw) > MAX_PROTOCOL_LINE_BYTES or not raw.endswith(b"\n"):
                raise CodeModeIsolateError(
                    "PROTOCOL_ERROR",
                    "Code Mode protocol frame is oversized",
                    error_class="callback_or_protocol",
                )
            try:
                frame = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise CodeModeIsolateError(
                    "PROTOCOL_ERROR",
                    "Code Mode protocol frame is invalid JSON",
                    error_class="callback_or_protocol",
                ) from exc
            if not isinstance(frame, dict):
                raise CodeModeIsolateError(
                    "PROTOCOL_ERROR",
                    "Code Mode protocol frame is not an object",
                    error_class="callback_or_protocol",
                )
            if frame.get("type") == "result":
                return frame.get("value")
            if frame.get("type") == "error":
                error_class = frame.get("errorClass")
                if not isinstance(error_class, str) or error_class not in CODE_MODE_ERROR_CLASSES:
                    error_class = "execution_runtime" if frame.get("code") == "CODE_MODE_FAILED" else None
                raise CodeModeIsolateError(
                    str(frame.get("code", "CODE_MODE_FAILED")),
                    str(frame.get("errorMessage", "Code Mode execution failed in the restricted isolate.")),
                    error_class=error_class,
                    tool_error=frame.get("toolError") if isinstance(frame.get("toolError"), dict) else None,
                )
            if frame.get("type") != "callback":
                raise CodeModeIsolateError(
                    "PROTOCOL_ERROR",
                    "Unknown Code Mode protocol frame",
                    error_class="callback_or_protocol",
                )
            try:
                receipt = self._dispatch_callback(host, frame)
            except CodeModeIsolateError:
                raise
            except Exception as exc:
                code = getattr(exc, "code", "CALLBACK_FAILED")
                raise CodeModeIsolateError(
                    str(code),
                    "Code Mode callback failed closed",
                    error_class="callback_or_protocol",
                ) from exc
            self._write(process, {"type": "callback_result", "id": frame.get("id"), "receipt": receipt})
            if isinstance(receipt, dict) and "__plane_finish__" in receipt:
                return receipt

    @staticmethod
    def _dispatch_callback(host, frame: dict[str, Any]) -> dict[str, Any]:
        callback_id = frame.get("id")
        kind = frame.get("kind")
        args = frame.get("args")
        if not isinstance(callback_id, str) or not isinstance(args, list):
            raise CodeModeIsolateError(
                "PROTOCOL_ERROR",
                "Code Mode callback is malformed",
                error_class="callback_or_protocol",
            )
        callback_names = (
            host.plane_callback_surface()
            if kind in {"resource", "finish"}
            else host.callback_surface()
        )
        if frame.get("name") != callback_names.get(kind):
            raise CodeModeIsolateError(
                "PROTOCOL_ERROR",
                "Code Mode callback name is not catalog-bound",
                error_class="callback_or_protocol",
            )
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
            if kind == "resource" and len(args) == 2:
                return host.invoke_resource(args[0], args[1])
            if kind == "finish" and len(args) == 1:
                return host.finish_plane(args[0])
        except (TypeError, ValueError) as exc:
            as_dict = getattr(exc, "as_dict", None)
            if callable(as_dict):
                return {"__plane_error__": as_dict()}
            raise CodeModeIsolateError("CALLBACK_FAILED", "Code Mode callback failed closed") from exc
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code:
                raise CodeModeIsolateError(
                    code,
                    "Code Mode callback failed closed",
                    error_class="callback_or_protocol",
                ) from exc
            raise
        raise CodeModeIsolateError(
            "PROTOCOL_ERROR",
            "Code Mode callback arguments are invalid",
            error_class="callback_or_protocol",
        )

    @staticmethod
    def _write(process, frame: dict[str, Any]) -> None:
        assert process.stdin is not None
        try:
            encoded = json.dumps(frame, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            if len(encoded) > MAX_PROTOCOL_LINE_BYTES:
                raise CodeModeIsolateError(
                    "PROTOCOL_ERROR",
                    "Code Mode protocol frame is oversized",
                    error_class="callback_or_protocol",
                )
            process.stdin.write(encoded)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodeModeIsolateError(
                "PROTOCOL_ERROR",
                "Code Mode host protocol closed",
                error_class="callback_or_protocol",
            ) from exc

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

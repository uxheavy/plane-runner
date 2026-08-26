"""Typed, persisted, credential-free host RPC for Code Mode."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, Callable

from django.core.exceptions import ValidationError

from plane.agent.lifecycle import (
    AgentDomainError,
    code_mode_reserved_totals,
    code_mode_usage_totals,
    reap_code_mode_reservations,
    reconcile_code_mode_usage,
    reserve_code_mode_usage,
    finish_code_mode,
    finalize_invocation,
)
from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    canonical_json,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.agent.runtime.contracts import (
    MAX_PREPARED_CALL_REF_BYTES,
    PREPARED_CALL_PREFIX,
    model_operation_entry,
)
from plane.agent.runtime.dispatch import RuntimeDispatchError, _dispatch_binding
from plane.db.models import (
    InvocationState,
    OperationGatewayIdempotency,
    OutcomeSubmission,
    RunAttempt,
    RunState,
    RunTerminalEvent,
    RuntimeInvocation,
    TerminalEventKind,
    TerminalEventSource,
)
from plane.operation_gateway.catalog import CATALOG_DIGEST, OPERATION_CATALOG, code_mode_callback_names, get_operation
from plane.operation_gateway.gateway import OperationGateway, work_item_target_digest

from .contracts import (
    CODE_MODE_SCHEMA_VERSION,
    MAX_DISCOVERY_BYTES,
    MAX_DISCOVERY_METHODS,
    MAX_EXECUTE_INPUT_BYTES,
    MAX_CODE_MODE_INLINE_RESULT_BYTES,
    MAX_CODE_MODE_OBSERVATIONS,
    MAX_CODE_MODE_OBSERVATIONS_BYTES,
    MAX_CODE_MODE_OBSERVATION_BYTES,
    MAX_RETURNED_VALUE_BYTES,
    PLANE_DISCOVERY_OPERATION,
    PLANE_EXECUTION_OPERATION,
    CodeModeBudget,
    CodeModeExecutionRequest,
    HostBinding,
    SandboxPolicy,
    PlaneToolError,
    tool_error,
)


class CodeModeBindingError(ValueError):
    """The callback was not bound to the immutable Plane runtime records."""


class CodeModeObservationError(AgentDomainError):
    """The bounded callback observation receipt cannot be extended safely."""

    code = "OBSERVATION_LIMIT"


def _plane_method_path(operation_id: str) -> str:
    if operation_id == "search_workspace":
        return "workspace.search"
    if operation_id == "work_item.read":
        return "workItems.retrieve"
    if operation_id == "work_item.rename":
        return "workItems.update"
    segments = operation_id.split(".")
    namespace = "".join(part.replace("_", " ").title().replace(" ", "") for part in segments[:-1])
    method = segments[-1].replace("_", " ").title().replace(" ", "")
    return f"{namespace}.{method}"


def _is_plane_operation(operation_id: str) -> bool:
    return not operation_id.startswith(("agent.", "catalog.", "code_mode.", "runtime."))


def _ts_type(schema: Any, name: str = "JsonValue") -> str:
    if not isinstance(schema, Mapping):
        return name
    schema_type = schema.get("type")
    if schema_type == "string":
        return "string"
    if schema_type == "integer" or schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        return f"readonly {_ts_type(schema.get('items'), name)}[]"
    if schema_type == "object":
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            return name
        required = set(schema.get("required", ()))
        fields = []
        for field, value in properties.items():
            fields.append(f"readonly {field}{'' if field in required else '?'}: {_ts_type(value)}")
        return "{ " + "; ".join(fields) + " }"
    return name


def _plane_declarations(methods: list[dict[str, str]]) -> str:
    lines = [
        "type JsonPrimitive = string | number | boolean | null;",
        "type JsonValue = JsonPrimitive | readonly JsonValue[] | { readonly [key: string]: JsonValue };",
        'type PlaneRef<Kind extends string = string> = string & { readonly __planeKind: Kind };',
        "type FinishInput = { kind: 'completed'; summary: string; content?: string; artifacts?: readonly PlaneRef<'artifact'>[]; evidence?: readonly PlaneRef[] } | { kind: 'waiting_for_input'; question: string; context?: JsonValue } | { kind: 'blocked'; reason: string; evidence?: readonly PlaneRef[] };",
        "declare const task: Readonly<{ target: PlaneRef; objective: string; acceptanceCriteria: readonly string[] }> ;",
    ]
    namespaces: dict[str, list[str]] = {}
    for method in methods:
        path = method["path"]
        namespace, name = path.split(".", 1)
        descriptor = OPERATION_CATALOG[method["operationId"]]
        if path == "workItems.retrieve":
            signature = "retrieve(target: PlaneRef): Promise<JsonValue>"
        elif path == "workItems.update":
            signature = "update(target: PlaneRef, input: { readonly name: string }): Promise<JsonValue>"
        else:
            signature = f"{name}(input: {_ts_type(descriptor.input_schema)}): Promise<JsonValue>"
        namespaces.setdefault(namespace, []).append(signature)
    lines.append("declare const plane: Readonly<{")
    for namespace, signatures in namespaces.items():
        lines.append(f"  readonly {namespace}: Readonly<{{ {'; '.join(signatures)} }}>;")
    lines.append("  readonly finish: (input: FinishInput) => Promise<never>;")
    lines.append("}>;")
    return "\n".join(lines)


def _initial_plane_methods() -> list[dict[str, str]]:
    return [
        {"path": _plane_method_path(operation_id), "operationId": operation_id}
        for operation_id in ("search_workspace", "work_item.read", "work_item.rename")
        if operation_id in OPERATION_CATALOG
    ]


def initial_task_kit(snapshot: Mapping[str, Any], methods: list[dict[str, str]] | None = None) -> dict[str, Any]:
    assignment = snapshot["assignment"]
    selected = methods if methods is not None else _initial_plane_methods()
    return {
        "task": {
            "target": assignment["targetRef"],
            "objective": assignment["objective"],
            "acceptanceCriteria": list(assignment["acceptanceCriteria"]),
        },
        "declarations": _plane_declarations(selected),
    }


def _canonicalize_work_item_read_call(input_data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Canonicalize one typed search result read call before registry resolution."""

    if "preparedCallRef" not in input_data:
        return input_data
    if set(input_data) != {"preparedCallRef"}:
        raise ValueError("prepared work-item read reference is invalid")
    candidate = input_data["preparedCallRef"]
    if isinstance(candidate, str):
        if not candidate.startswith(PREPARED_CALL_PREFIX) or len(candidate.encode("utf-8")) > MAX_PREPARED_CALL_REF_BYTES:
            raise ValueError("prepared work-item read reference is invalid")
        return {"preparedCallRef": candidate}
    if not isinstance(candidate, Mapping):
        raise ValueError("prepared work-item read reference is invalid")
    if set(candidate) == {"preparedCallRef"}:
        prepared_ref = candidate["preparedCallRef"]
        if (
            not isinstance(prepared_ref, str)
            or not prepared_ref.startswith(PREPARED_CALL_PREFIX)
            or len(prepared_ref.encode("utf-8")) > MAX_PREPARED_CALL_REF_BYTES
        ):
            raise ValueError("prepared work-item read reference is invalid")
        return {"preparedCallRef": prepared_ref}
    if set(candidate) != {"action", "operationRef", "input"}:
        raise ValueError("prepared work-item read call is invalid")
    if candidate["action"] != "read" or candidate["operationRef"] != "operation:work_item.read":
        raise ValueError("prepared work-item read call is invalid")
    nested = candidate["input"]
    if not isinstance(nested, Mapping) or set(nested) != {"preparedCallRef"}:
        raise ValueError("prepared work-item read call is invalid")
    prepared_ref = nested["preparedCallRef"]
    if (
        not isinstance(prepared_ref, str)
        or not prepared_ref.startswith(PREPARED_CALL_PREFIX)
        or len(prepared_ref.encode("utf-8")) > MAX_PREPARED_CALL_REF_BYTES
    ):
        raise ValueError("prepared work-item read reference is invalid")
    return {"preparedCallRef": prepared_ref}


class CodeModeHostRPC:
    """Expose only typed callbacks after revalidating the persisted G1 binding."""

    def __init__(
        self,
        *,
        gateway: OperationGateway,
        request: Any,
        run: RunAttempt,
        invocation: RuntimeInvocation,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> None:
        self.gateway = gateway
        self.request = request
        self.is_cancelled = is_cancelled
        self.sandbox = sandbox or SandboxPolicy()
        (
            self.run,
            self.invocation,
            self.binding,
            self._snapshot,
            self.gateway_request,
        ) = self._load_trusted_binding(run, invocation)
        self.run = reap_code_mode_reservations(self.run)
        self.budget = self._remaining_budget(self.run, self._snapshot)
        self.budget.spill_bytes = min(self.budget.spill_bytes, self.sandbox.max_spill_bytes)
        self._local_reserved = {
            "inputTokens": 0,
            "outputTokens": 0,
            "durationMs": 0,
            "codeModeInputBytes": 0,
            "codeModeOutputBytes": 0,
            "codeModeCalls": 0,
            "codeModeSpillBytes": 0,
        }
        self._execution_reservation = None
        self._started_at = time.monotonic()
        self._code_mode_observations: list[dict[str, Any]] = []
        self._code_mode_active = False
        self.max_inline_result_bytes = MAX_CODE_MODE_INLINE_RESULT_BYTES
        self._prepared_call_registry: Any | None = None
        self._catalog_search_receipt: dict[str, Any] | None = None
        self._catalog_search_describe_completed = False
        self._plane_methods = self._initial_plane_methods()
        self._plane_finish_applied = False
        self._missing_finish_recorded = False
        self._plane_call_sequence = 0

    @classmethod
    def from_invocation(
        cls,
        *,
        gateway: OperationGateway,
        request: Any,
        invocation: RuntimeInvocation,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> "CodeModeHostRPC":
        """Construct a host from one persisted invocation, never caller refs."""

        return cls(
            gateway=gateway,
            request=request,
            run=invocation.run,
            invocation=invocation,
            is_cancelled=is_cancelled,
            sandbox=sandbox,
        )

    @staticmethod
    def callback_surface() -> dict[str, str]:
        """Return callback names from the canonical operation catalog."""

        return code_mode_callback_names()

    @staticmethod
    def plane_tool_definitions() -> dict[str, dict[str, Any]]:
        """Return the complete model-facing contract, with no gateway details."""

        return {
            "Plane:discover": {
                "description": "Find Plane Agent SDK methods and TypeScript types for one intended workflow. Use when the current task declarations do not contain a method needed to complete the assignment. Describe the whole workflow, not an API name. Returns one bounded replacement declaration slice. Discovery does not authorize execution.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 500,
                            "description": "The complete intended workflow, for example: list urgent unassigned work items, assign one member, then finish.",
                        }
                    },
                },
            },
            "Plane:execute": {
                "description": "Run one bounded TypeScript function body against the current Plane assignment. `plane` and `task` are injected and frozen. Use ordinary typed resource methods; do not import, export, construct a client, or return large data. Return compact JSON for further reasoning, or call `await plane.finish(...)` exactly once to complete, wait for input, or block. Plane owns identity, authorization, pagination, idempotency, receipts, and recovery.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["code"],
                    "properties": {
                        "code": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_EXECUTE_INPUT_BYTES,
                            "description": "TypeScript statements executed as an async function body with ambient plane and task objects. Imports and exports are forbidden.",
                        }
                    },
                },
            },
        }

    def task_kit(self) -> dict[str, Any]:
        """Build the deterministic initial assignment declarations."""
        return initial_task_kit(self._snapshot, self._plane_methods)

    def _initial_plane_methods(self) -> list[dict[str, str]]:
        return _initial_plane_methods()

    def discover(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str) or not 1 <= len(query) <= 500:
            return {
                "status": "error",
                "error": tool_error(
                    "VALIDATION_ERROR",
                    "The discovery query is invalid.",
                    "Provide one workflow between 1 and 500 characters.",
                    field="query",
                    expected="string with length 1..500",
                    recovery="narrow_query",
                ),
            }
        tokens = {token for token in query.casefold().replace("_", " ").split() if token}
        matches = []
        for operation_id, descriptor in OPERATION_CATALOG.items():
            if not _is_plane_operation(operation_id):
                continue
            searchable = " ".join((operation_id, descriptor.name, descriptor.summary, *descriptor.tags)).casefold()
            if all(token in searchable for token in tokens):
                matches.append({"path": _plane_method_path(operation_id), "operationId": operation_id})
        matches.sort(key=lambda item: (item["path"], item["operationId"]))
        if len(matches) > MAX_DISCOVERY_METHODS:
            return {
                "status": "error",
                "error": tool_error(
                    "DISCOVERY_TOO_BROAD",
                    "The workflow matches too many Plane methods.",
                    "Describe one complete, narrower workflow and try discovery again.",
                    recovery="narrow_query",
                ),
            }
        if not matches:
            return {
                "status": "error",
                "error": tool_error(
                    "CAPABILITY_NOT_FOUND",
                    "No Plane method matched that workflow.",
                    "Describe the intended workflow with its resource and action.",
                    recovery="discover_capability",
                ),
            }
        declarations = _plane_declarations(matches)
        if len(declarations.encode("utf-8")) > MAX_DISCOVERY_BYTES:
            return {
                "status": "error",
                "error": tool_error(
                    "DISCOVERY_TOO_LARGE",
                    "The declaration slice is too large.",
                    "Describe a narrower workflow with fewer related methods.",
                    recovery="narrow_query",
                ),
            }
        self._plane_methods = matches
        return {"status": "ok", "declarations": declarations}

    def execute_plane(self, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            return {
                "status": "error",
                "error": tool_error(
                    "VALIDATION_ERROR",
                    "Plane:execute code must be non-empty.",
                    "Provide TypeScript statements for the current assignment.",
                    field="code",
                    expected=f"string with length 1..{MAX_EXECUTE_INPUT_BYTES}",
                ),
            }
        if len(code.encode("utf-8")) > MAX_EXECUTE_INPUT_BYTES:
            return {
                "status": "error",
                "error": tool_error(
                    "INPUT_TOO_LARGE",
                    "Plane:execute code exceeds 8192 UTF-8 bytes.",
                    "Shorten the function body or use Plane resources to keep intermediate data in the sandbox.",
                    field="code",
                    expected=f"at most {MAX_EXECUTE_INPUT_BYTES} UTF-8 bytes",
                ),
            }
        from .isolate import CodeModeIsolateError, CodeModeIsolateRunner

        self._code_mode_observations = []
        self._code_mode_active = True
        try:
            result = CodeModeIsolateRunner().run_plane(
                self,
                code,
                self.task_kit()["task"],
                self._plane_methods,
                self.task_kit()["declarations"],
            )
        except CodeModeIsolateError as exc:
            if getattr(exc, "code", None) == "MISSING_TERMINAL_PUBLICATION":
                self._record_missing_terminal_publication()
            return {
                "status": "error",
                "error": getattr(exc, "tool_error", None)
                or tool_error(
                    getattr(exc, "code", "EXECUTION_FAILED"),
                    "Plane:execute failed in the restricted runtime.",
                    "Correct the TypeScript body and retry the same assignment.",
                    recovery="fix_code",
                ),
            }
        finally:
            self._code_mode_active = False
        if isinstance(result, Mapping) and result.get("__plane_finish__"):
            return {"status": result["__plane_finish__"]}
        try:
            size = len(canonical_json(result).encode("utf-8"))
        except (TypeError, ValueError):
            return {
                "status": "error",
                "error": tool_error(
                    "RETURN_VALUE_INVALID",
                    "Plane:execute returned a non-JSON value.",
                    "Return only JSON values or call await plane.finish(...).",
                ),
            }
        if size > MAX_RETURNED_VALUE_BYTES:
            return {
                "status": "error",
                "error": tool_error(
                    "RETURN_VALUE_TOO_LARGE",
                    "Plane:execute returned more than 8 KiB of JSON.",
                    "Return a compact summary or keep intermediate data inside the sandbox.",
                    expected=f"at most {MAX_RETURNED_VALUE_BYTES} canonical UTF-8 bytes",
                ),
            }
        return {"status": "returned", "value": result}

    def _record_missing_terminal_publication(self) -> None:
        if self._missing_finish_recorded:
            return
        self._missing_finish_recorded = True
        try:
            finalize_invocation(
                self.invocation,
                kind=TerminalEventKind.RUN_FAILURE,
                reason="MISSING_TERMINAL_PUBLICATION",
                source=TerminalEventSource.RUNTIME,
                idempotency_key=f"idempotency:code-mode-missing-{self.binding.invocation_ref}",
            )
        except Exception:
            # The bounded model error remains authoritative when durable failure
            # recording itself is unavailable; the runtime will reconcile it.
            pass

    def plane_callback_surface(self) -> dict[str, str]:
        return {"resource": "call_plane_resource", "finish": "finish_plane"}

    def invoke_resource(self, path: str, args: list[Any]) -> dict[str, Any]:
        method = next((method for method in self._plane_methods if method["path"] == path), None)
        if method is None:
            return {
                "status": "error",
                "error": tool_error(
                    "CAPABILITY_NOT_FOUND",
                    f"Plane method {path!r} is not in the task declarations.",
                    "Call Plane:discover for the complete intended workflow.",
                    recovery="discover_capability",
                ),
            }
        try:
            input_data = self._resource_input(path, args)
            self._plane_call_sequence += 1
            receipt = self.call_operation(
                method["operationId"],
                input_data,
                idempotency_key=f"idempotency:code-mode-{self.binding.invocation_ref}-{self._plane_call_sequence}",
                correlation_id=f"correlation:code-mode-{self.binding.invocation_ref}-{self._plane_call_sequence}",
            )
        except PlaneToolError:
            raise
        except (TypeError, ValueError) as exc:
            return {"status": "error", "error": tool_error("VALIDATION_ERROR", str(exc), "Correct the typed method input.")}
        if not receipt.get("ok"):
            error = receipt.get("error")
            code = error.get("code", "OPERATION_REJECTED") if isinstance(error, Mapping) else "OPERATION_REJECTED"
            return {
                "status": "error",
                "error": tool_error(
                    str(code),
                    "Plane rejected the resource operation.",
                    "Correct the target or permissions before retrying.",
                    retryable=bool(error.get("retryable")) if isinstance(error, Mapping) else False,
                    recovery="retry_same_call" if isinstance(error, Mapping) and error.get("retryable") else "fix_code",
                ),
            }
        return {"status": "ok", "value": receipt.get("result", {})}

    def _resource_input(self, path: str, args: list[Any]) -> dict[str, Any]:
        if path in {"workItems.retrieve", "workItems.update"}:
            if not args or not isinstance(args[0], str):
                raise PlaneToolError(
                    "VALIDATION_ERROR",
                    "work item methods require a typed target reference",
                    "Use task.target with the typed Plane resource method.",
                    field="target",
                )
            expected = self._snapshot["assignment"]["targetRef"]
            if args[0] != expected:
                raise PlaneToolError(
                    "TARGET_INVALID",
                    "The resource target is outside the current assignment",
                    "Use task.target with the typed Plane resource method.",
                    field="target",
                )
            issue_ref = expected.removeprefix("target:issue:")
            if issue_ref == expected and expected.startswith("target:literal-"):
                try:
                    issue_ref = bytes.fromhex(expected.removeprefix("target:literal-")).decode("utf-8").removeprefix("issue:")
                except (ValueError, UnicodeDecodeError) as exc:
                    raise PlaneToolError(
                        "TARGET_UNSUPPORTED",
                        "The current assignment target is not a work item",
                        "Discover a method for the assigned target type.",
                        recovery="discover_capability",
                    ) from exc
            if not issue_ref:
                raise PlaneToolError(
                    "TARGET_UNSUPPORTED",
                    "The current assignment target is not a work item",
                    "Discover a method for the assigned target type.",
                    recovery="discover_capability",
                )
            value = {"project_id": str(self.run.project_id), "issue_id": issue_ref}
            if path == "workItems.update":
                if len(args) != 2 or not isinstance(args[1], Mapping) or not isinstance(args[1].get("name"), str):
                    raise PlaneToolError(
                        "VALIDATION_ERROR",
                        "update requires one non-empty name",
                        "Pass { name: string } as the update input.",
                        field="input",
                    )
                if not args[1]["name"].strip():
                    raise PlaneToolError(
                        "VALIDATION_ERROR",
                        "update requires one non-empty name",
                        "Pass { name: string } as the update input.",
                        field="input",
                    )
                value["name"] = args[1]["name"]
            return value
        if len(args) != 1 or not isinstance(args[0], Mapping):
            raise ValueError(f"{path} requires one typed input object")
        return dict(args[0])

    def finish_plane(self, value: Any) -> dict[str, Any]:
        if self._plane_finish_applied:
            raise PlaneToolError(
                "FINISH_ALREADY_CALLED",
                "plane.finish may be called only once",
                "Return from the current execution after the first finish call.",
            )
        if not isinstance(value, Mapping) or value.get("kind") not in {"completed", "waiting_for_input", "blocked"}:
            raise PlaneToolError(
                "VALIDATION_ERROR",
                "finish input has an unsupported kind",
                "Use completed, waiting_for_input, or blocked.",
                field="kind",
            )
        kind = value["kind"]
        required = "summary" if kind == "completed" else "question" if kind == "waiting_for_input" else "reason"
        if not isinstance(value.get(required), str) or not value[required].strip():
            raise PlaneToolError(
                "VALIDATION_ERROR", f"{kind} finish requires {required}", f"Provide a non-empty {required}.", field=required
            )
        allowed = {
            "completed": {"kind", "summary", "content", "artifacts", "evidence"},
            "waiting_for_input": {"kind", "question", "context"},
            "blocked": {"kind", "reason", "evidence"},
        }[kind]
        unknown = set(value).difference(allowed)
        if unknown:
            raise PlaneToolError(
                "VALIDATION_ERROR",
                "finish input has unknown fields",
                "Use only the fields declared for this finish kind.",
                field=sorted(unknown)[0],
            )
        for field in ("summary", "content", "question", "reason"):
            if field in value and value[field] is not None and (
                not isinstance(value[field], str) or len(value[field].encode("utf-8")) > 4096
            ):
                raise PlaneToolError(
                    "VALIDATION_ERROR", f"finish {field} is invalid", "Use a bounded UTF-8 string.", field=field
                )
        for field in ("artifacts", "evidence"):
            if field in value:
                refs = value[field]
                if not isinstance(refs, list) or len(refs) > 64 or any(
                    not isinstance(ref, str) or not ref.strip() or len(ref.encode("utf-8")) > 256 for ref in refs
                ):
                    raise PlaneToolError(
                        "VALIDATION_ERROR",
                        f"finish {field} is invalid",
                        "Use at most 64 bounded reference strings.",
                        field=field,
                    )
        if "context" in value:
            try:
                if len(canonical_json(value["context"]).encode("utf-8")) > 4096:
                    raise ValueError
            except (TypeError, ValueError):
                raise PlaneToolError(
                    "VALIDATION_ERROR",
                    "finish context is not bounded JSON",
                    "Use a small JSON context object.",
                    field="context",
                )
        try:
            if self._execution_reservation is not None:
                self.record_execution_usage(
                    duration_ms=max(1, int((time.monotonic() - self._started_at) * 1000))
                )
            result = finish_code_mode(
                self.invocation,
                kind=kind,
                summary=value.get("summary", ""),
                content=value.get("content"),
                artifacts=value.get("artifacts", []),
                evidence=value.get("evidence", []),
                question=value.get("question", ""),
                context=value.get("context"),
                reason=value.get("reason", ""),
                idempotency_key=f"idempotency:code-mode-finish-{self.invocation.id}",
                created_by=self.invocation.created_by,
            )
        except PlaneToolError:
            raise
        except Exception as exc:
            raise PlaneToolError(
                "FINISH_REJECTED",
                "Plane could not apply the requested lifecycle finish",
                "Correct the finish data or retry the same finish call.",
                recovery="retry_same_call",
            ) from exc
        self._plane_finish_applied = True
        return {
            "__plane_finish__": {
                "completed": "completed",
                "waiting_for_input": "waiting_for_input",
                "blocked": "blocked",
            }[kind]
        }

    def set_prepared_call_registry(self, registry: Any) -> None:
        """Bind the invocation-local prepared-call registry owned by the host port."""

        self._prepared_call_registry = registry

    def search_operations(
        self,
        query: str = "",
        *,
        idempotency_key: str,
        correlation_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.call_operation(
            "catalog.search",
            {"query": query, "limit": limit},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def describe_operation(
        self,
        operation_id: str,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return self.call_operation(
            "catalog.describe",
            {"operation_id": operation_id},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def call_operation(
        self,
        operation_id: str,
        input_data: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
        workspace_slug: str | None = None,
    ) -> dict[str, Any]:
        code_mode_active = getattr(self, "_code_mode_active", False)
        normalized_input = input_data
        if (
            operation_id == "work_item.read"
            and self._prepared_call_registry is not None
            and isinstance(input_data, Mapping)
            and "preparedCallRef" in input_data
        ):
            try:
                normalized_input = _canonicalize_work_item_read_call(input_data)
            except ValueError:
                normalized_input = input_data
        cached_search = getattr(self, "_catalog_search_receipt", None)
        if (
            code_mode_active
            and operation_id == "catalog.search"
            and getattr(self, "_catalog_search_describe_completed", False)
        ):
            receipt = self._catalog_search_replay(
                cached_search,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        else:
            receipt = self._call_operation(
                operation_id,
                normalized_input,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                workspace_slug=workspace_slug,
            )
            if code_mode_active and operation_id == "catalog.search" and receipt.get("ok"):
                self._catalog_search_receipt = dict(receipt)
            elif (
                code_mode_active
                and operation_id == "catalog.describe"
                and receipt.get("ok")
                and cached_search is not None
            ):
                self._catalog_search_describe_completed = True
        prepared_read_receipt: Mapping[str, Any] | None = None
        if (
            operation_id == "search_workspace"
            and receipt.get("ok")
            and self._prepared_call_registry is not None
        ):
            receipt = self._prepare_search_receipt(receipt)
            receipt, prepared_read_receipt = self._consume_single_prepared_read(
                receipt,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if (
            operation_id == "work_item.read"
            and isinstance(normalized_input, Mapping)
            and isinstance(normalized_input.get("preparedCallRef"), str)
            and receipt.get("ok")
            and self._prepared_call_registry is not None
        ):
            self._prepared_call_registry.mark_consumed(normalized_input["preparedCallRef"])
        self._record_code_mode_observation(operation_id, receipt)
        if prepared_read_receipt is not None:
            self._record_code_mode_observation("work_item.read", prepared_read_receipt)
        return receipt

    @staticmethod
    def _catalog_search_replay(
        receipt: Mapping[str, Any] | None,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Replay the bounded successful catalog search without another gateway call."""

        if receipt is None:
            raise RuntimeError("catalog search replay is not armed")
        return {
            **receipt,
            "idempotencyKey": idempotency_key,
            "correlationId": correlation_id,
            "replayed": True,
        }

    def _consume_single_prepared_read(
        self,
        receipt: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
        """Consume one trusted direct-search handoff before it crosses Code Mode."""

        prepared_refs = self._prepared_refs_from_search_receipt(receipt)
        if (
            len(prepared_refs) != 1
            or self._prepared_call_registry is None
            or not self._prepared_call_registry.is_unconsumed(prepared_refs[0])
        ):
            return receipt, None
        prepared_ref = prepared_refs[0]
        prepared_read = self._call_operation(
            "work_item.read",
            {"preparedCallRef": prepared_ref},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        if prepared_read.get("ok"):
            self._prepared_call_registry.mark_consumed(prepared_ref)
            receipt = self._without_consumed_prepared_read(receipt, prepared_ref)
        return {**receipt, "preparedReadResult": dict(prepared_read)}, prepared_read

    @staticmethod
    def _prepared_refs_from_search_receipt(receipt: Mapping[str, Any]) -> tuple[str, ...]:
        result = receipt.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
            return ()
        refs: list[str] = []
        for item in result["results"]:
            if not isinstance(item, Mapping) or "workItemReadCall" not in item:
                continue
            prepared_ref = item["workItemReadCall"]
            if (
                not isinstance(prepared_ref, str)
                or not prepared_ref.startswith(PREPARED_CALL_PREFIX)
                or len(prepared_ref.encode("utf-8")) > MAX_PREPARED_CALL_REF_BYTES
            ):
                return ()
            refs.append(prepared_ref)
        return tuple(refs)

    @staticmethod
    def _without_consumed_prepared_read(
        receipt: Mapping[str, Any], prepared_ref: str
    ) -> Mapping[str, Any]:
        result = receipt.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
            return receipt
        results = [
            {
                key: value
                for key, value in item.items()
                if key != "workItemReadCall"
            }
            if isinstance(item, Mapping) and item.get("workItemReadCall") == prepared_ref
            else item
            for item in result["results"]
        ]
        return {**receipt, "result": {**result, "results": results}}

    def _prepare_search_receipt(self, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
        """Bind Code Mode search results to opaque, invocation-local read calls."""

        result = receipt.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
            return receipt
        prepared_results: list[Mapping[str, Any]] = []
        for item in result["results"]:
            if not isinstance(item, Mapping) or item.get("objectType") != "work_item":
                prepared_results.append(item)
                continue
            read_input = item.get("workItemReadInput")
            if not isinstance(read_input, Mapping) or set(read_input) != {"project_id", "issue_id"}:
                prepared_results.append(item)
                continue
            prepared_ref = self._prepared_call_registry.register(read_input)
            prepared_item = {key: value for key, value in item.items() if key != "workItemReadInput"}
            prepared_item["workItemReadCall"] = prepared_ref
            prepared_results.append(prepared_item)
        return {**receipt, "result": {**result, "results": prepared_results}}

    def _call_operation(
        self,
        operation_id: str,
        input_data: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
        workspace_slug: str | None = None,
    ) -> dict[str, Any]:
        raw = {
            "schema_version": "plane.operation/v1",
            "operation_id": operation_id,
            "workspace_slug": workspace_slug or self.binding.workspace_slug,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "input": dict(input_data) if isinstance(input_data, Mapping) else input_data,
        }
        if operation_id in {"agent.outcome.submit", "agent.outcome.publish"} and isinstance(raw["input"], Mapping):
            # The callback envelope is the trusted binding boundary.  A
            # model-supplied run_ref is redundant payload and is normalized
            # rather than allowed to redirect or poison this bound callback.
            raw["input"] = {**raw["input"], "run_ref": self.binding.run_ref}
        if operation_id == "agent.outcome.evaluate" and isinstance(raw["input"], Mapping):
            raw["input"] = {**raw["input"], "evaluator_ref": self.binding.actor_ref}
        if (
            operation_id == "work_item.read"
            and self._prepared_call_registry is not None
            and isinstance(raw["input"], Mapping)
            and "preparedCallRef" in raw["input"]
        ):
            try:
                canonical_input = _canonicalize_work_item_read_call(raw["input"])
                raw["input"] = self._prepared_call_registry.resolve(
                    canonical_input,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                )
            except ValueError:
                return self._reject(raw, "PREPARED_CALL_INVALID", 409)
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        terminal_observation = self._terminal_outcome_observation(raw)
        if terminal_observation is not None:
            return terminal_observation
        terminal_mutation_observation = self._terminal_mutation_observation(raw)
        if terminal_mutation_observation is not None:
            return terminal_mutation_observation
        if operation_id == "agent.outcome.publish":
            self.invocation.refresh_from_db(fields=["state"])
            if self.invocation.state in {
                InvocationState.SUCCEEDED,
                InvocationState.FAILED,
                InvocationState.BLOCKED,
                InvocationState.CANCELLED,
                InvocationState.OUTCOME_UNKNOWN,
            }:
                return self._publish_terminal_outcome(raw)
        descriptor = get_operation(operation_id)
        if descriptor is None:
            return self._reject(raw, "UNKNOWN_OPERATION", 404)
        input_size = self._input_size(raw["input"])
        output_reservation = descriptor.max_result_bytes + 4096
        if output_reservation > self._available("output_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        try:
            reservation = self._reserve(
                input_bytes=self._input_size(raw["input"]),
                output_bytes=output_reservation,
                calls=1,
                duration_ms=self._duration_reservation(),
            )
        except AgentDomainError:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        reconciled = False
        terminalizes_invocation = operation_id in {"agent.outcome.submit", "agent.outcome.publish"}
        try:
            if terminalizes_invocation:
                # Outcome callbacks can transition the current invocation to a
                # terminal state. Commit this callback's bounded usage before
                # entering that lifecycle transition; reconciliation after it
                # would correctly reject usage on a terminal invocation.
                self._reconcile(
                    reservation,
                    input_bytes=input_size,
                    output_bytes=output_reservation,
                    calls=1,
                    duration_ms=max(1, int((time.monotonic() - self._started_at) * 1000)),
                )
                reconciled = True
            response, _status = self.gateway.execute(self.gateway_request, raw)
            response = self._stable_replay_response(raw, response)
            receipt = self._receipt(raw, response)
            encoded_size = len(canonical_json(receipt).encode("utf-8"))
            if encoded_size > output_reservation:
                return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
            if not terminalizes_invocation:
                self._reconcile(
                    reservation,
                    input_bytes=input_size,
                    output_bytes=encoded_size,
                    calls=1,
                    duration_ms=(
                        0
                        if self._execution_reservation is not None
                        else max(1, int((time.monotonic() - self._started_at) * 1000))
                    ),
                )
                reconciled = True
            return receipt
        finally:
            if not reconciled:
                self._release(reservation)

    def _terminal_outcome_observation(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return a stable observation for a duplicate submit after terminalization."""

        if raw.get("operation_id") != "agent.outcome.submit":
            return None
        input_data = raw.get("input")
        if not isinstance(input_data, Mapping):
            return None
        self.invocation.refresh_from_db(fields=["state"])
        self.run.refresh_from_db(fields=["state"])
        if self.run.state not in {
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
        }:
            return None
        outcome = OutcomeSubmission.objects.filter(run_id=self.run.id).order_by("created_at", "id").first()
        if outcome is None:
            return None
        terminal = RunTerminalEvent.objects.filter(invocation_id=self.invocation.pk, visible=True).first()
        outcome_result = {
            "outcomeRef": f"outcome-submission:{outcome.id}",
            "state": outcome.state,
        }
        if terminal is not None:
            outcome_result["productEventRef"] = terminal.product_event_ref
        matches = all(
            input_data.get(field, []) == getattr(outcome, field)
            for field in ("artifacts", "evidence")
        ) and input_data.get("summary") == outcome.summary
        response: dict[str, Any]
        if matches:
            response = {
                "ok": True,
                "replayed": True,
                "correlation_id": raw["correlation_id"],
                "idempotency": {"key": raw["idempotency_key"], "replayed": True},
                "result": {"outcome": outcome_result},
            }
        else:
            response = {
                "ok": False,
                "replayed": False,
                "correlation_id": raw["correlation_id"],
                "idempotency": {"key": raw["idempotency_key"], "replayed": False},
                "error": {
                    "code": "PLANE_CONFLICT",
                    "message": "The current run already has a different terminal outcome.",
                    "retryable": False,
                },
            }
        receipt = self._receipt(raw, response)
        receipt["terminalObservation"] = True
        return receipt

    def _terminal_mutation_observation(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        """Prevent a later same-batch mutation after terminal publication."""

        operation_id = raw.get("operation_id")
        if operation_id in {"agent.outcome.submit", "agent.outcome.publish"}:
            return None
        descriptor = get_operation(operation_id) if isinstance(operation_id, str) else None
        if descriptor is None or descriptor.kind != "mutation":
            return None
        self.run.refresh_from_db(fields=["state"])
        if self.run.state not in {
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
            RunState.OUTCOME_UNKNOWN,
        }:
            return None
        response = {
            "ok": False,
            "replayed": False,
            "correlation_id": raw["correlation_id"],
            "idempotency": {"key": raw["idempotency_key"], "replayed": False},
            "error": {
                "code": "PLANE_CONFLICT",
                "message": "The current run is terminal; no later mutation was applied.",
                "retryable": False,
            },
        }
        receipt = self._receipt(raw, response)
        receipt["terminalObservation"] = True
        return receipt

    def _publish_terminal_outcome(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Publish an existing outcome without adding usage after terminalization."""

        response, _status = self.gateway.execute(self.gateway_request, raw)
        response = self._stable_replay_response(raw, response)
        receipt = self._receipt(raw, response)
        descriptor = get_operation(raw["operation_id"])
        if descriptor is None:
            return self._receipt_error(raw, response, "UNKNOWN_OPERATION", 404)
        if len(canonical_json(receipt).encode("utf-8")) > descriptor.max_result_bytes + 4096:
            return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
        return receipt

    def execute_typescript(self, request: CodeModeExecutionRequest) -> dict[str, Any]:
        """Run one bounded generated module in the existing child isolate."""

        from .isolate import CodeModeIsolateRunner

        self._code_mode_observations = []
        self._code_mode_active = True
        try:
            result = CodeModeIsolateRunner().run(
                self,
                request.source,
                request.input_data,
            )
        finally:
            self._code_mode_active = False
        return {
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "actorRef": self.binding.actor_ref,
            "principalRef": self.binding.principal_ref,
            "workspaceRef": f"workspace:{self.run.workspace_id}",
            "runRef": self.binding.run_ref,
            "invocationRef": self.binding.invocation_ref,
            "result": result,
            "observations": list(self._code_mode_observations),
        }

    def _record_code_mode_observation(self, operation_id: str, receipt: Mapping[str, Any]) -> None:
        if not self._code_mode_active:
            return
        if len(self._code_mode_observations) >= MAX_CODE_MODE_OBSERVATIONS:
            raise CodeModeObservationError("Code Mode observation budget is exhausted")
        error = receipt.get("error")
        observation: dict[str, Any] = {
            "source": "code",
            "action": "code",
            "operationRef": f"operation:{operation_id}",
            "status": "replayed" if receipt.get("replayed") else ("ok" if receipt.get("ok") else "denied"),
            "requestId": receipt.get("requestId"),
            "gatewayReceipt": receipt.get("gatewayReceipt"),
            "auditReceipt": receipt.get("auditReceipt"),
        }
        if isinstance(error, Mapping) and isinstance(error.get("code"), str):
            observation["errorCode"] = error["code"]
        target_digest = receipt.get("targetDigest")
        if isinstance(target_digest, str):
            observation["targetDigest"] = target_digest
        if len(canonical_json(observation).encode("utf-8")) > MAX_CODE_MODE_OBSERVATION_BYTES:
            raise CodeModeObservationError("Code Mode observation exceeds its size bound")
        if (
            len(canonical_json(self._code_mode_observations + [observation]).encode("utf-8"))
            > MAX_CODE_MODE_OBSERVATIONS_BYTES
        ):
            raise CodeModeObservationError("Code Mode observations exceed their size bound")
        self._code_mode_observations.append(observation)

    def spill_result(self, payload: str | bytes) -> dict[str, Any]:
        """Route oversized bytes as bounded metadata through the audited gateway."""

        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        size = len(encoded)
        raw = {
            "schema_version": "plane.operation/v1",
            "operation_id": "code_mode.spill",
            "workspace_slug": self.binding.workspace_slug,
            "idempotency_key": f"spill:{self.binding.invocation_ref}:{hashlib.sha256(encoded).hexdigest()}",
            "correlation_id": f"correlation:{self.binding.invocation_ref}",
            "input": {"size_bytes": size, "content_digest": hashlib.sha256(encoded).hexdigest()},
        }
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        if size > self._available("spill_bytes"):
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        output_reservation = 1024 + 4096
        if output_reservation > self._available("output_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        try:
            reservation = self._reserve(
                input_bytes=self._input_size(raw["input"]),
                output_bytes=output_reservation,
                calls=1,
                spill_bytes=size,
                duration_ms=self._duration_reservation(),
            )
        except AgentDomainError:
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        reconciled = False
        try:
            response, _status = self.gateway.execute(self.gateway_request, raw)
            response = self._stable_replay_response(raw, response)
            receipt = self._receipt(raw, response)
            encoded_size = len(canonical_json(receipt).encode("utf-8"))
            if encoded_size > output_reservation:
                return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
            self._reconcile(
                reservation,
                input_bytes=self._input_size(raw["input"]),
                output_bytes=encoded_size,
                calls=1,
                spill_bytes=size,
                duration_ms=(
                    0
                    if self._execution_reservation is not None
                    else max(1, int((time.monotonic() - self._started_at) * 1000))
                ),
            )
            reconciled = True
            return receipt
        finally:
            if not reconciled:
                self._release(reservation)

    def record_execution_usage(
        self,
        *,
        input_bytes=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms: int | None = None,
    ) -> None:
        """Persist model usage reported by the trusted runner boundary."""

        elapsed = max(1, int((time.monotonic() - self._started_at) * 1000))
        if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms <= 0):
            raise AgentDomainError("Code Mode duration must be positive")
        effective_duration = elapsed if duration_ms is None else duration_ms
        reservation = self._execution_reservation
        if reservation is None:
            reservation = self._reserve(
                input_bytes=input_bytes,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=effective_duration,
            )
        self._reconcile(
            reservation,
            input_bytes=input_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=effective_duration,
        )
        self._execution_reservation = None

    def reserve_execution_budget(self, *, input_bytes=0, input_tokens=0, output_tokens=0) -> None:
        """Reserve trusted runner usage before generated code can invoke Plane."""

        if self._execution_reservation is not None:
            return
        if self.budget.input_tokens <= 0 or self.budget.output_tokens <= 0 or self.budget.duration_ms <= 0:
            raise AgentDomainError("Code Mode execution budget is exhausted")
        self._execution_reservation = self._reserve(
            input_bytes=input_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=self.budget.duration_ms,
        )

    def release_execution_budget(self) -> None:
        if self._execution_reservation is not None:
            self._release(self._execution_reservation)
            self._execution_reservation = None

    def _load_trusted_binding(self, run: RunAttempt, invocation: RuntimeInvocation):
        request_actor_ref = getattr(self.request, "agent_actor_ref", None)
        if not isinstance(request_actor_ref, str) or not request_actor_ref:
            raise CodeModeBindingError("request.agent_actor_ref is required")
        try:
            stored_run = RunAttempt.objects.select_related(
                "actor", "actor__principal", "profile_version", "assignment", "workspace"
            ).get(pk=run.pk)
            stored_invocation = RuntimeInvocation.objects.select_related(
                "run", "run__actor", "run__profile_version", "run__workspace"
            ).get(pk=invocation.pk)
            snapshot = validate_run_snapshot(stored_run.snapshot)
            envelope = validate_invocation_envelope(stored_invocation.envelope)
            stored_run.validate_agent_scope()
            stored_invocation.validate_agent_scope()
            _dispatch_binding(snapshot, envelope, stored_invocation)
        except (
            AgentDomainError,
            ValidationError,
            RuntimeContractError,
            RuntimeDispatchError,
            RunAttempt.DoesNotExist,
            RuntimeInvocation.DoesNotExist,
        ) as exc:
            raise CodeModeBindingError("persisted Code Mode binding is invalid") from exc
        if stored_invocation.run_id != stored_run.id:
            raise CodeModeBindingError("invocation is not bound to the supplied run")
        if not stored_run.actor.is_active:
            raise CodeModeBindingError("AgentActor is inactive")
        principal = stored_run.actor.principal
        if not principal.is_active or not principal.is_bot:
            raise CodeModeBindingError("AgentActor principal is not an active dedicated Plane identity")
        if stored_run.state not in {RunState.QUEUED, RunState.RUNNING, RunState.WAITING_FOR_INPUT}:
            raise CodeModeBindingError("run is not active")
        if stored_invocation.state in {
            InvocationState.SUCCEEDED,
            InvocationState.FAILED,
            InvocationState.BLOCKED,
            InvocationState.CANCELLED,
            InvocationState.OUTCOME_UNKNOWN,
        }:
            raise CodeModeBindingError("invocation is terminal")
        expected_actor_ref = snapshot["actorRef"]
        expected_workspace_ref = snapshot["workspaceRef"]
        if request_actor_ref != expected_actor_ref:
            raise CodeModeBindingError("request actor is not bound to the stored run")
        request_workspace = getattr(self.request, "agent_workspace_ref", None)
        if request_workspace is not None and request_workspace != expected_workspace_ref:
            raise CodeModeBindingError("request workspace is not bound to the stored run")
        if stored_run.snapshot_content_digest != snapshot["contentDigest"]:
            raise CodeModeBindingError("run snapshot digest is not immutable")
        binding = HostBinding(
            actor_ref=expected_actor_ref,
            principal_ref=str(principal.id),
            workspace_slug=stored_run.workspace.slug,
            run_ref=snapshot["runId"],
            invocation_ref=stored_invocation.invocation_id,
            catalog_digest=CATALOG_DIGEST,
            assignment_target_ref=snapshot["assignment"]["targetRef"],
        )
        if expected_workspace_ref != f"workspace:{stored_run.workspace_id}":
            raise CodeModeBindingError("workspace reference is not bound to the stored run")
        gateway_request = SimpleNamespace(
            user=principal,
            META=getattr(self.request, "META", {}),
            agent_actor_ref=expected_actor_ref,
            agent_workspace_ref=expected_workspace_ref,
            agent_run_ref=snapshot["runId"],
            agent_invocation_ref=stored_invocation.invocation_id,
        )
        return stored_run, stored_invocation, binding, snapshot, gateway_request

    @staticmethod
    def _remaining_budget(run: RunAttempt, snapshot: Mapping[str, Any]) -> CodeModeBudget:
        used = run.cumulative_usage or {}
        code_mode_used = code_mode_usage_totals(run)
        code_mode_reserved = code_mode_reserved_totals(run)
        total = snapshot["totalBudget"]
        policy = snapshot["runtimePolicy"]
        limits = {
            "input_bytes": policy.get("maxCodeModeInputBytes"),
            "output_bytes": policy.get("maxCodeModeOutputBytes"),
            "calls": policy.get("maxCodeModeCalls"),
            "spill_bytes": policy.get("maxArtifactBytes"),
        }
        if any(value is None for value in limits.values()):
            raise CodeModeBindingError("Code Mode limits are absent from the immutable run snapshot")
        return CodeModeBudget(
            input_tokens=max(
                0,
                int(total["inputTokens"]) - int(used.get("inputTokens", 0)) - code_mode_reserved["inputTokens"],
            ),
            output_tokens=max(
                0,
                int(total["outputTokens"]) - int(used.get("outputTokens", 0)) - code_mode_reserved["outputTokens"],
            ),
            input_bytes=max(
                0,
                int(limits["input_bytes"])
                - code_mode_used["codeModeInputBytes"]
                - code_mode_reserved["codeModeInputBytes"],
            ),
            output_bytes=max(
                0,
                int(limits["output_bytes"])
                - code_mode_used["codeModeOutputBytes"]
                - code_mode_reserved["codeModeOutputBytes"],
            ),
            duration_ms=max(
                0,
                int(total["durationMs"]) - int(used.get("durationMs", 0)) - code_mode_reserved["durationMs"],
            ),
            calls=max(
                0,
                int(limits["calls"]) - code_mode_used["codeModeCalls"] - code_mode_reserved["codeModeCalls"],
            ),
            spill_bytes=max(
                0,
                int(limits["spill_bytes"])
                - code_mode_used["codeModeSpillBytes"]
                - code_mode_reserved["codeModeSpillBytes"],
            ),
        )

    @staticmethod
    def _input_size(value: Any) -> int:
        return len(canonical_json(value).encode("utf-8"))

    def _available(self, field: str) -> int:
        local_field = {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "duration_ms": "durationMs",
            "input_bytes": "codeModeInputBytes",
            "output_bytes": "codeModeOutputBytes",
            "calls": "codeModeCalls",
            "spill_bytes": "codeModeSpillBytes",
        }[field]
        if field == "duration_ms" and self._execution_reservation is not None:
            return self.budget.duration_ms
        return max(0, getattr(self.budget, field) - self._local_reserved[local_field])

    def _duration_reservation(self) -> int:
        if self._execution_reservation is not None:
            return 0
        return max(1, self.budget.duration_ms)

    def _reserve(
        self,
        *,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
        input_bytes=0,
        output_bytes=0,
        calls=0,
        spill_bytes=0,
    ):
        self.run, reservation = reserve_code_mode_usage(
            self.run,
            self.invocation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            calls=calls,
            spill_bytes=spill_bytes,
        )
        for field, amount in {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "durationMs": duration_ms,
            "codeModeInputBytes": input_bytes,
            "codeModeOutputBytes": output_bytes,
            "codeModeCalls": calls,
            "codeModeSpillBytes": spill_bytes,
        }.items():
            self._local_reserved[field] += amount
        return reservation

    def _reconcile(
        self,
        reservation,
        *,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
        input_bytes=0,
        output_bytes=0,
        calls=0,
        spill_bytes=0,
    ):
        self.run = reconcile_code_mode_usage(
            self.run,
            self.invocation,
            reservation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            calls=calls,
            spill_bytes=spill_bytes,
        )
        for field, reserved_amount, actual_amount in (
            ("inputTokens", reservation["usage"].get("inputTokens", 0), input_tokens),
            ("outputTokens", reservation["usage"].get("outputTokens", 0), output_tokens),
            ("durationMs", reservation["usage"].get("durationMs", 0), duration_ms),
            ("codeModeInputBytes", reservation["usage"].get("codeModeInputBytes", 0), input_bytes),
            ("codeModeOutputBytes", reservation["usage"].get("codeModeOutputBytes", 0), output_bytes),
            ("codeModeCalls", reservation["usage"].get("codeModeCalls", 0), calls),
            ("codeModeSpillBytes", reservation["usage"].get("codeModeSpillBytes", 0), spill_bytes),
        ):
            self._local_reserved[field] -= reserved_amount
            budget_field = {
                "inputTokens": "input_tokens",
                "outputTokens": "output_tokens",
                "durationMs": "duration_ms",
                "codeModeInputBytes": "input_bytes",
                "codeModeOutputBytes": "output_bytes",
                "codeModeCalls": "calls",
                "codeModeSpillBytes": "spill_bytes",
            }[field]
            setattr(self.budget, budget_field, max(0, getattr(self.budget, budget_field) - actual_amount))

    def _release(self, reservation):
        self._reconcile(reservation)

    def _preflight(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if self._code_mode_active:
            try:
                self._load_trusted_binding(self.run, self.invocation)
            except CodeModeBindingError:
                return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if self.binding.catalog_digest != CATALOG_DIGEST:
            return self._reject(raw, "CATALOG_MISMATCH", 409)
        if raw["workspace_slug"] != self.binding.workspace_slug:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if str(getattr(getattr(self.request, "user", None), "id", "")) != self.binding.principal_ref:
            return self._reject(raw, "NOT_AUTHORIZED", 403)
        if getattr(self.request, "agent_actor_ref", None) != self.binding.actor_ref:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if not isinstance(raw["input"], Mapping):
            return self._reject(raw, "VALIDATION_ERROR", 400)
        input_size = self._input_size(raw["input"])
        if input_size > self._available("input_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if (
            self._available("output_bytes") <= 0
            or self._available("spill_bytes") <= 0
            or self._available("calls") <= 0
            or self.budget.input_tokens <= 0
            or self.budget.output_tokens <= 0
            or self.budget.duration_ms <= 0
        ):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if (time.monotonic() - self._started_at) * 1000 >= self.budget.duration_ms:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.is_cancelled():
            return self._reject(raw, "CANCELLED", 409)
        return None

    def _record_output(self, size: int) -> bool:
        if size > self._available("output_bytes"):
            return False
        try:
            reservation = self._reserve(output_bytes=size)
            self._reconcile(reservation, output_bytes=size)
        except AgentDomainError:
            return False
        return True

    def _reject(self, raw: Mapping[str, Any], code: str, status_code: int) -> dict[str, Any]:
        response, _status = self.gateway.record_invalid_request(
            self.gateway_request,
            dict(raw),
            code=code,
            status_code=status_code,
        )
        return self._receipt(raw, response)

    def _receipt(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
        idempotency = response.get("idempotency", {})
        receipt = {
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "callback": self.callback_surface().get(
                "spill" if raw["operation_id"] == "code_mode.spill" else "operation"
            ),
            "operationId": raw["operation_id"],
            "operationRef": f"operation:{raw['operation_id']}",
            "actorRef": self.binding.actor_ref,
            "principalRef": self.binding.principal_ref,
            "workspaceRef": f"workspace:{self.run.workspace_id}",
            "runRef": self.binding.run_ref,
            "invocationRef": self.binding.invocation_ref,
            "idempotencyKey": raw["idempotency_key"],
            "correlationId": response.get("correlation_id", raw["correlation_id"]),
            "requestId": response.get("request_id"),
            "gatewayReceipt": response.get("audit_receipt"),
            "auditReceipt": response.get("audit_receipt"),
            "replayed": bool(idempotency.get("replayed", False)),
            "ok": bool(response.get("ok", False)),
        }
        if response.get("ok"):
            receipt["result"] = response.get("result", {})
            if raw["operation_id"] == "catalog.describe":
                described = receipt["result"]
                if isinstance(described, Mapping) and isinstance(described.get("operation"), Mapping):
                    # Code Mode callbacks consume the receipt directly. Keep
                    # the canonical gateway result intact while projecting the
                    # model-facing operation at the same boundary used by the
                    # separate runtime host, so the next callback can resolve
                    # operationId without reconstructing or guessing it.
                    receipt["operation"] = model_operation_entry(described["operation"])
        else:
            receipt["error"] = response.get("error", {"code": "INTERNAL_ERROR", "retryable": False})
        target_digest = self._target_digest(raw)
        if target_digest is not None:
            receipt["targetDigest"] = target_digest
        return receipt

    @staticmethod
    def _target_digest(raw: Mapping[str, Any]) -> str | None:
        """Expose only a stable discriminator for semantic work-item targets."""

        return work_item_target_digest(raw.get("operation_id"), raw.get("input"))

    def _stable_replay_response(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> Mapping[str, Any]:
        """Keep replay results stable, except where publication needs disposition."""

        if not response.get("idempotency", {}).get("replayed"):
            return response
        record = OperationGatewayIdempotency.objects.filter(
            workspace_slug=raw["workspace_slug"],
            caller_id=self.gateway_request.user.id,
            operation_id=raw["operation_id"],
            idempotency_key=raw["idempotency_key"],
        ).first()
        if record is None:
            return response
        stable = dict(response)
        stable["request_id"] = str(record.request_id)
        stable["correlation_id"] = record.correlation_id
        stable["audit_receipt"] = str(record.audit_receipt) if record.audit_receipt else response.get("audit_receipt")
        stable["idempotency"] = {
            "key": raw["idempotency_key"],
            "replayed": raw["operation_id"] == "agent.outcome.publish",
        }
        return stable

    def _receipt_error(
        self,
        raw: Mapping[str, Any],
        response: Mapping[str, Any],
        code: str,
        status_code: int,
    ) -> dict[str, Any]:
        receipt = self._receipt(raw, response)
        receipt.pop("result", None)
        receipt["ok"] = False
        receipt["error"] = {"code": code, "retryable": False, "status": status_code}
        return receipt

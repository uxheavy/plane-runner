"""One typed execution mechanism for all generated shared-SDK registrations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .adapter_registry import AdapterRegistration, get_registration
from ..contracts import MAX_RESULT_BYTES

# MCP/SDK are public transports for the same gateway result contract.
MAX_PUBLIC_RESULT_BYTES = MAX_RESULT_BYTES
MAX_PAGE_SIZE = 1000


class GatewayInvoker(Protocol):
    """The official SDK transport supplies the caller-bound gateway invocation."""

    def execute(
        self,
        *,
        operation_id: str,
        input: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
    ) -> Mapping[str, Any]: ...


class MCPAdapterError(ValueError):
    """A public-contract-safe error with a machine-readable disposition."""

    def __init__(self, *, tool_name: str, code: str, message: str):
        super().__init__(message)
        self.tool_name = tool_name
        self.code = code
        self.message = message


class MCPGatewayExecutionError(MCPAdapterError):
    """A gateway error projected without replacing its public error code."""

    def __init__(self, *, tool_name: str, code: str, message: str, retryable: bool):
        super().__init__(tool_name=tool_name, code=code, message=message)
        self.retryable = retryable


@dataclass(frozen=True)
class GatewayReceipt:
    operation_id: str
    caller_id: str
    audit_receipt: str
    replayed: bool


class SharedSDKGatewayAdapter:
    """Route every generated supported action through one exact gateway call."""

    def __init__(self, invoker: GatewayInvoker):
        self._invoker = invoker

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> Any:
        registration = get_registration(tool_name)
        if registration is None:
            raise MCPAdapterError(
                tool_name=tool_name,
                code="MCP_ACTION_NOT_INVENTORY",
                message="The public MCP action is not present in the pinned adapter registry.",
            )
        if registration.registration != "gateway":
            blocker = registration.blocker or {}
            code = (
                "MCP_ACTION_UNSUPPORTED"
                if registration.registration == "unsupported"
                else "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE"
            )
            message = blocker.get(
                "code", blocker.get("reason", "The public MCP action has no exact gateway registration.")
            )
            raise MCPAdapterError(tool_name=tool_name, code=code, message=str(message))
        payload = self._translate_input(registration, arguments or {})
        envelope = self._invoker.execute(
            operation_id=registration.gateway_operation_id or "",
            input=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        self._validate_receipt(registration, envelope)
        if not envelope.get("ok"):
            error = envelope.get("error")
            if not isinstance(error, Mapping):
                raise MCPGatewayExecutionError(
                    tool_name=tool_name,
                    code="INTERNAL_ERROR",
                    message="The gateway returned an invalid error envelope.",
                    retryable=False,
                )
            raise MCPGatewayExecutionError(
                tool_name=tool_name,
                code=str(error.get("code", "INTERNAL_ERROR")),
                message=str(error.get("message", "The operation could not be completed.")),
                retryable=bool(error.get("retryable", False)),
            )
        result = envelope.get("result")
        if not isinstance(result, Mapping) or registration.result_key is None:
            raise MCPAdapterError(
                tool_name=tool_name,
                code="MCP_GATEWAY_RESULT_INVALID",
                message="The gateway result does not match the generated public contract adapter.",
            )
        value = result.get(registration.result_key)
        if registration.result_mode == "none":
            return None
        self._validate_public_result(registration, value, payload)
        return value

    @staticmethod
    def _translate_input(registration: AdapterRegistration, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_ARGUMENTS_INVALID",
                message="MCP tool arguments must be an object.",
            )
        return {registration.input_aliases.get(str(key), str(key)): value for key, value in arguments.items()}

    @staticmethod
    def _validate_receipt(registration: AdapterRegistration, envelope: Mapping[str, Any]) -> GatewayReceipt:
        if envelope.get("schema_version") != "plane.operation/v1":
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_GATEWAY_SCHEMA_MISMATCH",
                message="The gateway returned an unsupported schema version.",
            )
        if envelope.get("operation_id") != registration.gateway_operation_id:
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_GATEWAY_OPERATION_MISMATCH",
                message="The gateway returned a different semantic operation.",
            )
        caller = envelope.get("caller")
        audit_receipt = envelope.get("audit_receipt")
        idempotency = envelope.get("idempotency")
        if (
            not isinstance(caller, Mapping)
            or caller.get("type") != "user"
            or not caller.get("id")
            or not isinstance(audit_receipt, str)
            or not isinstance(idempotency, Mapping)
            or not isinstance(idempotency.get("replayed"), bool)
        ):
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_GATEWAY_RECEIPT_INVALID",
                message="The gateway omitted caller, audit, or replay attribution.",
            )
        return GatewayReceipt(
            operation_id=str(envelope["operation_id"]),
            caller_id=str(caller["id"]),
            audit_receipt=audit_receipt,
            replayed=bool(idempotency["replayed"]),
        )

    @staticmethod
    def _validate_public_result(
        registration: AdapterRegistration,
        value: Any,
        arguments: Mapping[str, Any],
    ) -> None:
        try:
            encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_GATEWAY_RESULT_INVALID",
                message="The gateway result is not JSON-compatible.",
            ) from None
        if len(encoded) > MAX_PUBLIC_RESULT_BYTES:
            raise MCPAdapterError(
                tool_name=registration.tool_name,
                code="MCP_GATEWAY_RESULT_TOO_LARGE",
                message="The public MCP result exceeds the bounded response contract.",
            )
        if isinstance(value, Mapping) and "results" in value:
            results = value["results"]
            per_page = arguments.get("per_page")
            if per_page is not None and (
                isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= MAX_PAGE_SIZE
            ):
                raise MCPAdapterError(
                    tool_name=registration.tool_name,
                    code="MCP_PAGE_BOUNDS_INVALID",
                    message="The public MCP page size must be between 1 and 1000.",
                )
            if isinstance(results, list) and per_page is not None and len(results) > per_page:
                raise MCPAdapterError(
                    tool_name=registration.tool_name,
                    code="MCP_PAGE_BOUNDS_INVALID",
                    message="The gateway returned more items than the requested page size.",
                )
            for cursor_name in ("next_cursor", "prev_cursor"):
                cursor = value.get(cursor_name)
                if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 256):
                    raise MCPAdapterError(
                        tool_name=registration.tool_name,
                        code="MCP_PAGE_CURSOR_INVALID",
                        message="The gateway returned an invalid page cursor.",
                    )

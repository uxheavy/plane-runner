"""Dependency-free runtime transport contracts shared by both processes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol


PREPARED_CALL_PREFIX = "prepared-call:"
MAX_PREPARED_CALL_REF_BYTES = 256
_MODEL_PREPARED_READ_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["preparedCallRef"],
    "properties": {
        "preparedCallRef": {
            "type": "string",
            "minLength": len(PREPARED_CALL_PREFIX),
            "maxLength": MAX_PREPARED_CALL_REF_BYTES,
        }
    },
}


def _thaw_contract_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_contract_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_contract_json(item) for item in value]
    if isinstance(value, list):
        return [_thaw_contract_json(item) for item in value]
    return value


def model_operation_entry(operation: Mapping[str, Any]) -> dict[str, Any]:
    """Project a canonical operation entry into the model-facing host contract."""

    projected = _thaw_contract_json(operation)
    if not isinstance(projected, dict):
        raise TypeError("operation catalog entry must be an object")
    if projected.get("operationId") == "work_item.read":
        projected["inputSchema"] = _thaw_contract_json(_MODEL_PREPARED_READ_INPUT)
    if projected.get("operationId") == "search_workspace":
        result_schema = projected.get("resultSchema")
        if isinstance(result_schema, dict):
            results = result_schema.get("properties", {}).get("results")
            if isinstance(results, dict):
                item_schema = results.get("items")
                if isinstance(item_schema, dict):
                    item_properties = item_schema.get("properties")
                    if isinstance(item_properties, dict):
                        item_properties.pop("workItemReadInput", None)
                        read_call = item_properties.get("workItemReadCall")
                        if isinstance(read_call, dict):
                            read_call_properties = read_call.get("properties")
                            if isinstance(read_call_properties, dict):
                                read_call_properties["input"] = _thaw_contract_json(_MODEL_PREPARED_READ_INPUT)
    return projected


RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE = "runtime_transport_pre_dispatch_failure"
RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE = "runtime_configuration_pre_dispatch_failure"
RUNTIME_PROCESS_FAILED = "runtime_process_failed"
RUNTIME_PROCESS_TIMEOUT = "runtime_process_timeout"
RUNTIME_PROCESS_CANCELLED = "runtime_process_cancelled"
RUNTIME_PROCESS_OUTPUT_INVALID = "runtime_process_output_invalid"
RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE = "runtime_supervisor_pre_dispatch_failure"

_FAILURE_CODES = frozenset(
    {
        RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE,
        RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
        RUNTIME_PROCESS_FAILED,
        RUNTIME_PROCESS_TIMEOUT,
        RUNTIME_PROCESS_CANCELLED,
        RUNTIME_PROCESS_OUTPUT_INVALID,
        RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE,
    }
)
_FAILURE_PHASES = frozenset(
    {"runtime_transport", "runtime_configuration", "runtime_process", "launcher", "runtime_supervisor"}
)
_FAILURE_DETAILS = frozenset(
    {
        "dispatch_rejected",
        "process_start_failed",
        "process_exit",
        "bootstrap_argv_rejected",
        "process_timeout",
        "process_cancelled",
        "process_output_invalid",
        "unclassified_exception",
    }
)
_UNCLASSIFIED_FAILURE_DETAIL = "unclassified_exception"
_FAILURE_SUBREASONS = frozenset(
    {
        "credential_reference_not_allowed",
        "credential_source_unavailable",
        "credential_source_invalid",
        "credential_source_oversized",
        "credential_resolver_failed",
        "credential_resolver_output_invalid",
        "credential_lease_binding",
        "credential_lease_expired",
        "credential_lease_revoked",
        "credential_lease_rotated",
        "credential_lease_metadata_invalid",
        "credential_state_unavailable",
        "credential_state_invalid",
        "provider_attempt_evidence_rejected",
        "runtime_configuration_rejected",
    }
)
_CHILD_EXCEPTION_CLASSES = frozenset(
    {
        "ModuleNotFoundError",
        "ImportError",
        "PermissionError",
        "OSError",
        "MemoryError",
        "TimeoutError",
        "PythonException",
        "Signal",
        "Unknown",
    }
)
_CHILD_MODULES = frozenset({"plane", "plane_runtime", "run_agent", "openai", "hermes", "dependency", "unknown"})
_CHILD_FAILURE_CATEGORIES = frozenset(
    {
        "module_not_found",
        "import_error",
        "permission_denied",
        "os_eperm",
        "memory_exhausted",
        "timeout",
        "python_traceback",
        "signal",
        "unknown",
    }
)
_HOST_FAILURE_CLASSES = frozenset({"transport_unavailable", "callback_exception"})
_HOST_SOCKET_PHASES = frozenset({"accept", "read", "invoke", "serialize", "write"})
_HOST_SOCKET_STATES = frozenset({"failed", "closed"})
_HOST_FAILURE_STATUSES = frozenset({"denied", "conflict", "unavailable", "invalid"})
_HOST_FAILURE_REQUIRED_FIELDS = frozenset(
    {"operationId", "attemptRef", "receiptRef", "status", "errorCode", "codeModePhase"}
)
_HOST_FAILURE_OPTIONAL_FIELDS = frozenset({"failureClass", "socketPhase", "socketState"})
_HOST_CODE_MODE_PHASES = frozenset({"host_callback", "unavailable"})
_HOST_SAFE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-@")


def _bounded_host_operation_failure(value: Mapping[str, object] | None) -> dict[str, object] | None:
    """Accept only the finite host diagnostic shape across the runtime seam."""

    if value is None or set(value).difference(_HOST_FAILURE_REQUIRED_FIELDS | _HOST_FAILURE_OPTIONAL_FIELDS):
        return None
    if not _HOST_FAILURE_REQUIRED_FIELDS.issubset(value):
        return None
    for field in _HOST_FAILURE_REQUIRED_FIELDS:
        item = value.get(field)
        if (
            not isinstance(item, str)
            or not item
            or len(item.encode("utf-8")) > 128
            or any(char not in _HOST_SAFE_CHARS for char in item)
        ):
            return None
    if value["status"] not in _HOST_FAILURE_STATUSES:
        return None
    if value["codeModePhase"] not in _HOST_CODE_MODE_PHASES:
        return None
    failure_class = value.get("failureClass")
    if "failureClass" in value and failure_class not in _HOST_FAILURE_CLASSES:
        return None
    socket_phase = value.get("socketPhase")
    socket_state = value.get("socketState")
    if ("socketPhase" in value) != ("socketState" in value):
        return None
    if (socket_phase is None) != (socket_state is None):
        return None
    if socket_phase is not None and (
        socket_phase not in _HOST_SOCKET_PHASES or socket_state not in _HOST_SOCKET_STATES
    ):
        return None
    return dict(value)


class RuntimeDispatchError(ValueError):
    """Raised when a serialized runtime dispatch cannot be completed safely."""

    def __init__(
        self,
        message: str,
        *,
        failure_code: str | None = None,
        failure_phase: str | None = None,
        failure_detail: str | None = None,
        failure_subreason: str | None = None,
        child_diagnostic: Mapping[str, object] | None = None,
        host_operation_failure: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        classification_is_valid = (
            isinstance(failure_code, str)
            and failure_code in _FAILURE_CODES
            and isinstance(failure_phase, str)
            and failure_phase in _FAILURE_PHASES
            and isinstance(failure_detail, str)
            and failure_detail in _FAILURE_DETAILS
            and failure_detail != _UNCLASSIFIED_FAILURE_DETAIL
        )
        self.has_allowlisted_failure = classification_is_valid
        self.failure_code = (
            failure_code
            if classification_is_valid
            else RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE
        )
        self.failure_phase = (
            failure_phase
            if classification_is_valid
            else "runtime_transport"
        )
        self.failure_detail = (
            failure_detail
            if classification_is_valid
            else _UNCLASSIFIED_FAILURE_DETAIL
        )
        self.failure_subreason = (
            failure_subreason
            if isinstance(failure_subreason, str) and failure_subreason in _FAILURE_SUBREASONS
            else None
        )
        self.child_diagnostic = self._bounded_child_diagnostic(child_diagnostic)
        self.host_operation_failure = _bounded_host_operation_failure(host_operation_failure)

    @staticmethod
    def _bounded_child_diagnostic(value: Mapping[str, object] | None) -> dict[str, object] | None:
        if value is None or set(value) != {
            "exceptionClass", "module", "category", "stderrSha256", "stderrBytes", "termination", "exitCode"
        }:
            return None
        if (
            value.get("exceptionClass") not in _CHILD_EXCEPTION_CLASSES
            or value.get("module") not in _CHILD_MODULES
            or value.get("category") not in _CHILD_FAILURE_CATEGORIES
            or not isinstance(value.get("stderrSha256"), str)
            or len(value["stderrSha256"]) != 64
            or any(char not in "0123456789abcdef" for char in value["stderrSha256"])
            or isinstance(value.get("stderrBytes"), bool)
            or not isinstance(value.get("stderrBytes"), int)
            or not 0 <= value["stderrBytes"] <= 64 * 1024
            or value.get("termination") not in {"exit", "signal"}
            or isinstance(value.get("exitCode"), bool)
            or not isinstance(value.get("exitCode"), int)
            or not -255 <= value["exitCode"] <= 255
        ):
            return None
        return dict(value)

    def public_failure(self) -> dict[str, object]:
        """Return only a bounded cross-process classification, never exception text."""

        failure: dict[str, object] = {
            "failureCode": self.failure_code,
            "failurePhase": self.failure_phase,
            "failureDetail": self.failure_detail,
        }
        if self.failure_subreason is not None:
            failure["failureSubreason"] = self.failure_subreason
        if self.child_diagnostic is not None:
            failure["childDiagnostic"] = dict(self.child_diagnostic)
        if self.host_operation_failure is not None:
            failure["hostOperationFailure"] = dict(self.host_operation_failure)
        return failure

    def with_host_operation_failure(self, value: Mapping[str, object]) -> "RuntimeDispatchError":
        """Carry bounded host evidence without changing the dispatch classification."""

        return RuntimeDispatchError(
            str(self),
            failure_code=self.failure_code,
            failure_phase=self.failure_phase,
            failure_detail=self.failure_detail,
            failure_subreason=self.failure_subreason,
            child_diagnostic=self.child_diagnostic,
            host_operation_failure=value,
        )


class RuntimeTransport(Protocol):
    """Logical transport to the separate runtime service."""

    def dispatch(self, snapshot_json: str, envelope_json: str) -> Iterable[str]:
        """Send canonical JSON and return serialized untrusted frames."""


__all__ = [
    "MAX_PREPARED_CALL_REF_BYTES",
    "PREPARED_CALL_PREFIX",
    "RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE",
    "RUNTIME_PROCESS_CANCELLED",
    "RUNTIME_PROCESS_FAILED",
    "RUNTIME_PROCESS_OUTPUT_INVALID",
    "RUNTIME_PROCESS_TIMEOUT",
    "RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE",
    "RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE",
    "RuntimeDispatchError",
    "RuntimeTransport",
    "model_operation_entry",
]

"""Dependency-free runtime transport contracts shared by both processes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
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
_MODEL_PREPARED_READ_REF = {
    "type": "string",
    "minLength": len(PREPARED_CALL_PREFIX),
    "maxLength": MAX_PREPARED_CALL_REF_BYTES,
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
            properties = result_schema.setdefault("properties", {})
            if isinstance(properties, dict):
                properties["assignmentWorkItemReadCall"] = _thaw_contract_json(_MODEL_PREPARED_READ_REF)
            results = result_schema.get("properties", {}).get("results")
            if isinstance(results, dict):
                item_schema = results.get("items")
                if isinstance(item_schema, dict):
                    item_properties = item_schema.get("properties")
                    if isinstance(item_properties, dict):
                        item_properties.pop("workItemReadInput", None)
                        item_properties["workItemReadCall"] = _thaw_contract_json(
                            _MODEL_PREPARED_READ_REF
                        )
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
_HOST_FAILURE_OPTIONAL_FIELDS = frozenset(
    {
        "failureClass",
        "socketPhase",
        "socketState",
        "preparedCallInvalidReason",
        "shapeDiagnostic",
        "preparedHandoff",
    }
)
_HOST_CODE_MODE_PHASES = frozenset({"host_callback", "unavailable"})
_HOST_SAFE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-@")
_PREPARED_CALL_INVALID_REASONS = frozenset(
    {"malformed", "unknown", "digest_mismatch", "binding_mismatch", "consumed"}
)
_PREPARED_DIAGNOSTIC_FAILURES = frozenset(
    {"malformed", "unknown", "digest_mismatch", "binding_mismatch"}
)
_PREPARED_DIAGNOSTIC_FORMS = frozenset({"canonical_ref", "ready_to_call", "unrecognized"})
_PREPARED_DIAGNOSTIC_FIELDS = frozenset(
    {"schemaVersion", "acceptedForm", "failureClass", "shape"}
)
_PREPARED_DIAGNOSTIC_SHAPE_FIELDS = frozenset(
    {"keyNames", "keyNamesTruncated", "valueTypes", "nestingDepth", "sizeClass"}
)
_PREPARED_DIAGNOSTIC_VALUE_TYPES = frozenset(
    {"null", "boolean", "string", "integer", "number", "object", "array", "unknown"}
)
_PREPARED_DIAGNOSTIC_SIZE_CLASSES = frozenset({"small", "medium", "large", "unknown"})
_PREPARED_DIAGNOSTIC_KEY_LIMIT = 16
_PREPARED_DIAGNOSTIC_DEPTH_LIMIT = 8
_PREPARED_DIAGNOSTIC_KEY_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
)
_PREPARED_DIAGNOSTIC_SENSITIVE_PARTS = frozenset(
    {"auth", "credential", "key", "password", "secret", "token"}
)
_PREPARED_HANDOFF_STAGES = frozenset(
    {
        "register",
        "runtime_auto_read",
        "hermes_model_read",
        "host_normalize",
        "registry_resolve",
        "registry_consume",
    }
)
_PREPARED_HANDOFF_FORMS = frozenset(
    {"canonical_ref", "malformed", "nested_wrapper", "json_string", "ready_envelope", "absent"}
)
_PREPARED_HANDOFF_REGISTRY_STATES = frozenset({"absent", "unconsumed", "consumed"})
_PREPARED_HANDOFF_REASONS = frozenset(
    {"none", "unknown", "malformed", "binding_mismatch", "digest_mismatch", "consumed"}
)
_PREPARED_HANDOFF_MAX_EVENTS = 6
_PREPARED_HANDOFF_EVENT_FIELDS = frozenset(
    {"stage", "form", "preparedRefDigest", "registryState", "reason", "operationRefDigest"}
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _bounded_prepared_shape_diagnostic(value: object) -> dict[str, object] | None:
    """Independently validate the value-free prepared-call shape contract."""

    if not isinstance(value, Mapping) or set(value) != _PREPARED_DIAGNOSTIC_FIELDS:
        return None
    if (
        value.get("schemaVersion") != "plane.prepared-call-shape/v1"
        or value.get("acceptedForm") not in _PREPARED_DIAGNOSTIC_FORMS
        or value.get("failureClass") not in _PREPARED_DIAGNOSTIC_FAILURES
    ):
        return None
    shape = value.get("shape")
    if not isinstance(shape, Mapping) or set(shape) != _PREPARED_DIAGNOSTIC_SHAPE_FIELDS:
        return None
    key_names = shape.get("keyNames")
    value_types = shape.get("valueTypes")
    if (
        not isinstance(key_names, list)
        or len(key_names) > _PREPARED_DIAGNOSTIC_KEY_LIMIT
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 64
            or any(char not in _PREPARED_DIAGNOSTIC_KEY_CHARS for char in item)
            or any(part in item.casefold() for part in _PREPARED_DIAGNOSTIC_SENSITIVE_PARTS)
            for item in key_names
        )
        or len(set(key_names)) != len(key_names)
        or type(shape.get("keyNamesTruncated")) is not bool
        or not isinstance(value_types, list)
        or len(value_types) > len(_PREPARED_DIAGNOSTIC_VALUE_TYPES)
        or any(
            not isinstance(item, str) or item not in _PREPARED_DIAGNOSTIC_VALUE_TYPES
            for item in value_types
        )
        or len(set(value_types)) != len(value_types)
        or type(shape.get("nestingDepth")) is not int
        or not 0 <= shape["nestingDepth"] <= _PREPARED_DIAGNOSTIC_DEPTH_LIMIT
        or shape.get("sizeClass") not in _PREPARED_DIAGNOSTIC_SIZE_CLASSES
    ):
        return None
    return {
        "schemaVersion": "plane.prepared-call-shape/v1",
        "acceptedForm": value["acceptedForm"],
        "failureClass": value["failureClass"],
        "shape": {
            "keyNames": list(key_names),
            "keyNamesTruncated": shape["keyNamesTruncated"],
            "valueTypes": list(value_types),
            "nestingDepth": shape["nestingDepth"],
            "sizeClass": shape["sizeClass"],
        },
    }


def _bounded_prepared_handoff(value: object) -> dict[str, object] | None:
    """Accept only the finite digest-and-enum prepared handoff trace."""

    if not isinstance(value, Mapping) or set(value) != {"schemaVersion", "events"}:
        return None
    events = value.get("events")
    if value.get("schemaVersion") != "plane.prepared-handoff/v1" or not isinstance(events, list):
        return None
    if not 1 <= len(events) <= _PREPARED_HANDOFF_MAX_EVENTS:
        return None
    seen: set[str] = set()
    bounded_events: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, Mapping) or set(event) != _PREPARED_HANDOFF_EVENT_FIELDS:
            return None
        prepared_digest = event.get("preparedRefDigest")
        operation_digest = event.get("operationRefDigest")
        if (
            event.get("stage") not in _PREPARED_HANDOFF_STAGES
            or event["stage"] in seen
            or event.get("form") not in _PREPARED_HANDOFF_FORMS
            or event.get("registryState") not in _PREPARED_HANDOFF_REGISTRY_STATES
            or event.get("reason") not in _PREPARED_HANDOFF_REASONS
            or not isinstance(prepared_digest, str)
            or not isinstance(operation_digest, str)
            or len(prepared_digest) != 64
            or len(operation_digest) != 64
            or any(char not in "0123456789abcdef" for char in prepared_digest)
            or any(char not in "0123456789abcdef" for char in operation_digest)
        ):
            return None
        seen.add(event["stage"])
        bounded_events.append(
            {
                "stage": event["stage"],
                "form": event["form"],
                "preparedRefDigest": prepared_digest,
                "registryState": event["registryState"],
                "reason": event["reason"],
                "operationRefDigest": operation_digest,
            }
        )
    bounded = {"schemaVersion": "plane.prepared-handoff/v1", "events": bounded_events}
    try:
        if len(_canonical(bounded)) > 4096:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return bounded


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
    prepared_reason = value.get("preparedCallInvalidReason")
    if "preparedCallInvalidReason" in value and prepared_reason not in _PREPARED_CALL_INVALID_REASONS:
        return None
    shape_diagnostic = value.get("shapeDiagnostic")
    bounded_shape_diagnostic = None
    if "shapeDiagnostic" in value:
        bounded_shape_diagnostic = _bounded_prepared_shape_diagnostic(shape_diagnostic)
        if bounded_shape_diagnostic is None:
            return None
    bounded = dict(value)
    if bounded_shape_diagnostic is not None:
        bounded["shapeDiagnostic"] = bounded_shape_diagnostic
    if "preparedHandoff" in value:
        bounded_prepared_handoff = _bounded_prepared_handoff(value["preparedHandoff"])
        if bounded_prepared_handoff is None:
            return None
        bounded["preparedHandoff"] = bounded_prepared_handoff
    return bounded


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

"""Invocation-scoped Plane host RPC for the separate Hermes process.

The wire contract mirrors the Hermes ``PlaneHostPort`` seam without importing
Hermes.  The endpoint is a one-invocation Unix-domain socket.  It carries
canonical JSON lines only; identity, authorization, idempotency, and product
publication remain Plane-owned.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import socket
import stat
import threading
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from plane.agent.code_mode.contracts import (
    CODE_MODE_EXECUTION_OPERATION,
    CODE_MODE_ERROR_CLASSES,
    CodeModeExecutionError,
    CodeModeExecutionRequest,
)

from .contracts import (
    MAX_PREPARED_CALL_REF_BYTES,
    PREPARED_CALL_PREFIX,
    _bounded_prepared_handoff,
    model_operation_entry,
)

HOST_PROTOCOL = "plane.agent-runtime/v1"
PLANE_DISCOVERY_OPERATION = "plane.operations.discover@1"
MAX_HOST_REQUEST_BYTES = 16 * 1024
# The host carries the public operation result and cannot widen its contract.
# Keep the same 8 KiB result ceiling as the dependency-free gateway limits
# without importing Django/DRF into the separate runtime process.
MAX_HOST_RESULT_BYTES = 8 * 1024
MAX_HOST_INPUT_BYTES = 8 * 1024
MAX_HOST_CALLS = 32
# Provider-attempt evidence has three normal lifecycle notices (intent,
# started, terminal) and may need one terminal fallback when a required
# notice is rejected. Keep that bounded audit channel separate from the
# model/tool callback budget while retaining the provider sequence ceiling.
MAX_PROVIDER_ATTEMPT_SEQUENCE = 256
MAX_PROVIDER_ATTEMPT_NOTICES_PER_SEQUENCE = 4
MAX_HOST_OBSERVATION_CALLS = MAX_PROVIDER_ATTEMPT_SEQUENCE * MAX_PROVIDER_ATTEMPT_NOTICES_PER_SEQUENCE
MAX_HOST_OPERATION_REF_BYTES = 256
MAX_HOST_CONTENT_BYTES = 4 * 1024
MAX_PREPARED_CALLS = MAX_HOST_CALLS * 20
MAX_PREPARED_CALL_WRAPPER_BYTES = 1024
_ACTIONS = {"discover", "read", "mutate", "code", "publish", "observe"}
_SOURCES = {"model", "code", "runtime"}
_RESULT_STATUSES = {"ok", "replayed", "denied", "conflict", "unavailable", "invalid"}
HOST_HTTP_PATH = "/v1/host"
MAX_HOST_HTTP_RESPONSE_BYTES = MAX_HOST_RESULT_BYTES + 1024
_ASSIGNMENT_READ_FAILURES = frozenset({"none", "zero", "multiple", "invalid"})
class PlaneHostRPCError(ValueError):
    """A malformed, unavailable, or rejected Plane host callback."""


_PREPARED_CALL_INVALID_REASONS = frozenset(
    {"unknown", "consumed", "binding_mismatch", "digest_mismatch", "malformed"}
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
_PREPARED_HANDOFF_EVENT_FIELDS = frozenset(
    {"stage", "form", "preparedRefDigest", "registryState", "reason", "operationRefDigest"}
)
_PREPARED_HANDOFF_MAX_EVENTS = len(_PREPARED_HANDOFF_STAGES)


class PreparedCallInvalid(PlaneHostRPCError):
    """Private bounded classification for one rejected prepared call."""

    def __init__(self, reason: str) -> None:
        if reason not in _PREPARED_CALL_INVALID_REASONS:
            raise ValueError("unsupported prepared-call rejection reason")
        self.reason = reason
        super().__init__("prepared work-item read reference is invalid")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prepared_handoff_form(value: Any) -> str:
    """Classify only the finite wrapper shapes used by the prepared handoff."""

    if not isinstance(value, Mapping) or "preparedCallRef" not in value:
        return "absent"
    if set(value) != {"preparedCallRef"}:
        return "malformed"
    candidate = value["preparedCallRef"]
    if isinstance(candidate, str):
        if candidate.startswith(PREPARED_CALL_PREFIX):
            return "canonical_ref"
        try:
            envelope = _canonical_prepared_wrapper(candidate)
        except PlaneHostRPCError:
            return "malformed" if candidate.lstrip().startswith(("{", "[")) else "malformed"
        return (
            "ready_envelope"
            if set(envelope) == {"action", "operationRef", "input"}
            else "json_string"
        )
    if isinstance(candidate, Mapping):
        if set(candidate) == {"preparedCallRef"}:
            return "nested_wrapper"
        if set(candidate) == {"action", "operationRef", "input"}:
            return "ready_envelope"
    return "malformed"


class PreparedHandoffTrace:
    """Bounded, invocation-local observations for one opaque prepared handoff."""

    def __init__(self) -> None:
        self._events: list[dict[str, str]] = []
        self._lock = threading.RLock()

    @staticmethod
    def _digest(value: Any) -> str:
        if not isinstance(value, str):
            return _sha256_text("<absent>")
        return _sha256_text(value)

    @staticmethod
    def _operation_digest(operation_ref: Any) -> str:
        return _sha256_text(operation_ref if isinstance(operation_ref, str) else "<absent>")

    def record(
        self,
        stage: str,
        *,
        form: str,
        prepared_ref: Any = None,
        registry_state: str,
        reason: str = "none",
        operation_ref: Any = "operation:work_item.read",
    ) -> None:
        if stage not in _PREPARED_HANDOFF_STAGES:
            return
        if form not in _PREPARED_HANDOFF_FORMS:
            form = "malformed"
        if registry_state not in _PREPARED_HANDOFF_REGISTRY_STATES:
            registry_state = "absent"
        if reason not in _PREPARED_HANDOFF_REASONS:
            reason = "unknown"
        with self._lock:
            if any(event["stage"] == stage for event in self._events):
                return
            if len(self._events) >= _PREPARED_HANDOFF_MAX_EVENTS:
                return
            self._events.append(
                {
                    "stage": stage,
                    "form": form,
                    "preparedRefDigest": self._digest(prepared_ref),
                    "registryState": registry_state,
                    "reason": reason,
                    "operationRefDigest": self._operation_digest(operation_ref),
                }
            )

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._events:
                return None
            value = {
                "schemaVersion": "plane.prepared-handoff/v1",
                "events": [dict(event) for event in self._events],
            }
        try:
            if len(_canonical(value, "prepared handoff trace")) > 4096:
                return None
        except PlaneHostRPCError:
            return None
        return value

    def is_closed(self) -> bool:
        with self._lock:
            by_stage = {event["stage"]: event for event in self._events}
            required = {"register", "runtime_auto_read", "registry_resolve", "registry_consume"}
            if not required.issubset(by_stage):
                return False
            prepared_digests = {by_stage[stage]["preparedRefDigest"] for stage in required}
            operation_digests = {by_stage[stage]["operationRefDigest"] for stage in required}
            return len(prepared_digests) == 1 and len(operation_digests) == 1


_PUBLICATION_FAILURE_REASONS = frozenset(
    {
        "receipt_not_fresh",
        "operation_mismatch",
        "callback_binding_mismatch",
        "missing_applied_marker",
        "outcome_binding_mismatch",
        "receipt_incomplete",
    }
)
_PUBLICATION_REF_ALLOWED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
)
MAX_PUBLICATION_REF_BYTES = 128


class _PublicationReceiptInvalid(PlaneHostRPCError):
    """Private bounded classification for an unapplied publication receipt."""

    def __init__(self, reason: str) -> None:
        if reason not in _PUBLICATION_FAILURE_REASONS:
            raise ValueError("unsupported publication receipt rejection reason")
        self.reason = reason
        super().__init__("outcome publication receipt did not prove an applied publication")


class PreparedCallRegistry:
    """Invocation-local prepared-call state shared by model and Code Mode callbacks."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.trace = PreparedHandoffTrace()

    def register(self, read_input: Mapping[str, Any]) -> str:
        canonical_input = dict(read_input)
        digest = hashlib.sha256(_canonical(canonical_input, "prepared work-item read input")).hexdigest()
        prepared_ref = f"{PREPARED_CALL_PREFIX}{digest}:{secrets.token_urlsafe(24)}"
        _text(prepared_ref, "host.preparedCallRef", MAX_PREPARED_CALL_REF_BYTES)
        with self.lock:
            if len(self.records) >= MAX_PREPARED_CALLS:
                raise PlaneHostRPCError("prepared work-item read reference budget exhausted")
            self.records[prepared_ref] = {
                "input": canonical_input,
                "correlation_id": None,
                "idempotency_key": None,
                "result": None,
                "consumed": False,
            }
        self.trace.record(
            "register",
            form="canonical_ref",
            prepared_ref=prepared_ref,
            registry_state="unconsumed",
        )
        return prepared_ref

    def mark_consumed(self, prepared_ref: str) -> None:
        with self.lock:
            record = self.records.get(prepared_ref)
            if record is not None:
                record["consumed"] = True
        if record is not None:
            self.trace.record(
                "registry_consume",
                form="canonical_ref",
                prepared_ref=prepared_ref,
                registry_state="consumed",
            )

    def has_unconsumed(self) -> bool:
        with self.lock:
            return any(not record["consumed"] for record in self.records.values())

    def is_unconsumed(self, prepared_ref: str) -> bool:
        with self.lock:
            record = self.records.get(prepared_ref)
            return record is not None and not record["consumed"]

    @staticmethod
    def _normalize(input_data: Mapping[str, Any]) -> Mapping[str, Any]:
        """Accept one canonical opaque ref or its exact serialized read envelope."""

        if "preparedCallRef" not in input_data:
            return input_data
        if set(input_data) != {"preparedCallRef"}:
            raise PreparedCallInvalid("malformed")
        prepared_ref = input_data["preparedCallRef"]
        if isinstance(prepared_ref, Mapping):
            if set(prepared_ref) != {"preparedCallRef"}:
                raise PreparedCallInvalid("malformed")
            prepared_ref = prepared_ref["preparedCallRef"]
        if not isinstance(prepared_ref, str):
            raise PreparedCallInvalid("malformed")
        if not prepared_ref.startswith(PREPARED_CALL_PREFIX):
            try:
                envelope = _canonical_prepared_wrapper(prepared_ref)
            except PlaneHostRPCError as exc:
                raise PreparedCallInvalid("malformed") from exc
            if set(envelope) != {"action", "operationRef", "input"}:
                raise PreparedCallInvalid("malformed")
            if envelope.get("action") != "read" or envelope.get("operationRef") != "operation:work_item.read":
                raise PreparedCallInvalid("malformed")
            nested = envelope.get("input")
            if not isinstance(nested, Mapping) or set(nested) != {"preparedCallRef"}:
                raise PreparedCallInvalid("malformed")
            prepared_ref = nested["preparedCallRef"]
            if not isinstance(prepared_ref, str) or not prepared_ref.startswith(PREPARED_CALL_PREFIX):
                raise PreparedCallInvalid("malformed")
        try:
            _text(prepared_ref, "host.preparedCallRef", MAX_PREPARED_CALL_REF_BYTES)
        except PlaneHostRPCError as exc:
            raise PreparedCallInvalid("malformed") from exc
        return {"preparedCallRef": prepared_ref}

    def normalize(self, input_data: Mapping[str, Any]) -> Mapping[str, Any]:
        form = _prepared_handoff_form(input_data)
        prepared_ref = input_data.get("preparedCallRef") if isinstance(input_data, Mapping) else None
        if isinstance(prepared_ref, str) and prepared_ref.startswith(PREPARED_CALL_PREFIX):
            registry_state = "consumed" if not self.is_unconsumed(prepared_ref) else "unconsumed"
        elif isinstance(prepared_ref, Mapping):
            nested_ref = prepared_ref.get("preparedCallRef")
            registry_state = (
                "consumed"
                if isinstance(nested_ref, str) and not self.is_unconsumed(nested_ref)
                else "unconsumed"
                if isinstance(nested_ref, str)
                else "absent"
            )
        else:
            registry_state = "absent"
        if form != "absent":
            self.trace.record(
                "host_normalize",
                form=form,
                prepared_ref=(
                    prepared_ref
                    if isinstance(prepared_ref, str)
                    else prepared_ref.get("preparedCallRef")
                    if isinstance(prepared_ref, Mapping)
                    else None
                ),
                registry_state=registry_state,
                reason="none",
            )
        return self._normalize(input_data)

    def resolve(
        self,
        input_data: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        normalized_input = self.normalize(input_data)
        if "preparedCallRef" not in normalized_input:
            return normalized_input
        prepared_ref = normalized_input["preparedCallRef"]
        with self.lock:
            record = self.records.get(prepared_ref)
            prepared_input = record.get("input") if record is not None else None
            if prepared_input is None or record is None:
                self.trace.record(
                    "registry_resolve",
                    form="canonical_ref",
                    prepared_ref=prepared_ref,
                    registry_state="absent",
                    reason="unknown",
                    operation_ref="operation:work_item.read",
                )
                raise PreparedCallInvalid("unknown")
            parts = prepared_ref.split(":", 2)
            if len(parts) != 3 or not hmac.compare_digest(
                parts[1], hashlib.sha256(_canonical(prepared_input, "prepared work-item read input")).hexdigest()
            ):
                self.trace.record(
                    "registry_resolve",
                    form="canonical_ref",
                    prepared_ref=prepared_ref,
                    registry_state="consumed" if record["consumed"] else "unconsumed",
                    reason="digest_mismatch",
                    operation_ref="operation:work_item.read",
                )
                raise PreparedCallInvalid("digest_mismatch")
            if correlation_id is not None or idempotency_key is not None:
                if not isinstance(correlation_id, str) or not isinstance(idempotency_key, str):
                    self.trace.record(
                        "registry_resolve",
                        form="canonical_ref",
                        prepared_ref=prepared_ref,
                        registry_state="consumed" if record["consumed"] else "unconsumed",
                        reason="malformed",
                    )
                    raise PreparedCallInvalid("malformed")
                bound_correlation = record["correlation_id"]
                bound_idempotency = record["idempotency_key"]
                if bound_correlation is None:
                    record["correlation_id"] = correlation_id
                    record["idempotency_key"] = idempotency_key
                elif bound_correlation != correlation_id or bound_idempotency != idempotency_key:
                    reason = "consumed" if record["consumed"] else "binding_mismatch"
                    self.trace.record(
                        "registry_resolve",
                        form="canonical_ref",
                        prepared_ref=prepared_ref,
                        registry_state="consumed" if record["consumed"] else "unconsumed",
                        reason=reason,
                    )
                    raise PreparedCallInvalid(reason)
            self.trace.record(
                "registry_resolve",
                form="canonical_ref",
                prepared_ref=prepared_ref,
                registry_state="consumed" if record["consumed"] else "unconsumed",
                reason="consumed" if record["consumed"] else "none",
                operation_ref="operation:work_item.read",
            )
            return prepared_input

    def record_runtime_auto_read(self, prepared_ref: str) -> None:
        self.trace.record(
            "runtime_auto_read",
            form="canonical_ref",
            prepared_ref=prepared_ref,
            registry_state="consumed" if not self.is_unconsumed(prepared_ref) else "unconsumed",
        )

    def record_hermes_model_read(self, input_data: Mapping[str, Any]) -> None:
        prepared_ref = input_data.get("preparedCallRef") if isinstance(input_data, Mapping) else None
        if not isinstance(prepared_ref, str):
            return
        self.trace.record(
            "hermes_model_read",
            form=_prepared_handoff_form(input_data),
            prepared_ref=prepared_ref,
            registry_state="consumed" if not self.is_unconsumed(prepared_ref) else "unconsumed",
            reason="consumed" if not self.is_unconsumed(prepared_ref) else "none",
        )


def _canonical(value: Any, name: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlaneHostRPCError(f"{name} is not JSON-compatible") from exc


def _bounded(value: Any, name: str, maximum: int) -> bytes:
    encoded = _canonical(value, name)
    if len(encoded) > maximum:
        raise PlaneHostRPCError(f"{name} exceeds {maximum} canonical UTF-8 bytes")
    return encoded


def _text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise PlaneHostRPCError(f"{name} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise PlaneHostRPCError(f"{name} exceeds {maximum} UTF-8 bytes")
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise PlaneHostRPCError(f"{name} must be an object")
    return dict(value)


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise PlaneHostRPCError(f"{name} has unknown field(s): {', '.join(unknown)}")


def _model_catalog_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    """Project the host-only prepared-call form of a catalog description.

    The canonical gateway descriptor remains raw-ID compatible for direct API
    callers. The model-facing host boundary instead exposes the bare opaque
    invocation-local reference that the host creates from search results.
    """

    return model_operation_entry(operation)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value, "host request")).hexdigest()


def _duplicate_rejecting_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise json.JSONDecodeError("duplicate object key", "", 0)
        result[key] = value
    return result


def _canonical_prepared_wrapper(value: str) -> Mapping[str, Any]:
    """Decode one bounded, exact JSON string carrying a prepared read envelope."""

    def reject_constant(_constant: str) -> None:
        raise ValueError("non-finite JSON constant")

    try:
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_PREPARED_CALL_WRAPPER_BYTES:
            raise PlaneHostRPCError("prepared work-item read input is oversized")
        decoded = json.loads(
            value,
            object_pairs_hook=_duplicate_rejecting_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, TypeError, ValueError) as exc:
        raise PlaneHostRPCError("prepared work-item read input is not canonical JSON") from exc
    if not isinstance(decoded, Mapping) or _canonical(decoded, "prepared work-item read input") != encoded:
        raise PlaneHostRPCError("prepared work-item read input is not canonical JSON")
    return decoded


def _strict_wire_object(value: Any, name: str, maximum: int) -> dict[str, Any]:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlaneHostRPCError(f"{name} is not UTF-8") from exc
    if isinstance(value, str):
        raw = value.encode("utf-8")
        if len(raw) > maximum or value != value.strip():
            raise PlaneHostRPCError(f"{name} is not canonical")
        try:
            value = json.loads(value, object_pairs_hook=_duplicate_rejecting_pairs)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PlaneHostRPCError(f"{name} is malformed JSON") from exc
        if _canonical(value, name) != raw:
            raise PlaneHostRPCError(f"{name} is not canonical")
    return _object(value, name)


@dataclass(frozen=True)
class PlaneHostCall:
    """Canonical, binding-complete host request shared with Hermes."""

    run_id: str
    invocation_id: str
    correlation_id: str
    action: str
    operation_ref: str
    input: Mapping[str, Any]
    source: str
    request_ref: str = ""
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        run_id = _text(self.run_id, "host.runId", 256)
        invocation_id = _text(self.invocation_id, "host.invocationId", 256)
        correlation_id = _text(self.correlation_id, "host.correlationId", 256)
        action = _text(self.action, "host.action", 32)
        operation_ref = _text(self.operation_ref, "host.operationRef", MAX_HOST_OPERATION_REF_BYTES)
        source = _text(self.source, "host.source", 32)
        payload = _object(self.input, "host.input")
        _bounded(payload, "host.input", MAX_HOST_INPUT_BYTES)
        if action not in _ACTIONS:
            raise PlaneHostRPCError(f"unsupported host action: {action!r}")
        if source not in _SOURCES:
            raise PlaneHostRPCError(f"unsupported host source: {source!r}")
        if action == "code" and source != "code":
            raise PlaneHostRPCError("code action must use the code source")
        if action == "observe" and source != "runtime":
            raise PlaneHostRPCError("observe action must use the runtime source")
        if action not in {"code", "observe"} and source != "model":
            raise PlaneHostRPCError("only code action may use the code source")
        identity = {
            "protocol": HOST_PROTOCOL,
            "runId": run_id,
            "invocationId": invocation_id,
            "action": action,
            "operationRef": operation_ref,
            "input": payload,
        }
        digest = _digest(identity)
        expected_request_ref = f"host-request:{digest}"
        expected_idempotency_key = f"host-idempotency:{digest}"
        request_ref = self.request_ref or expected_request_ref
        idempotency_key = self.idempotency_key or expected_idempotency_key
        if request_ref != expected_request_ref:
            raise PlaneHostRPCError("host requestRef is not bound to the request")
        if idempotency_key != expected_idempotency_key:
            raise PlaneHostRPCError("host idempotencyKey is not bound to the request")
        _bounded(self.to_wire(), "host.request", MAX_HOST_REQUEST_BYTES)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "invocation_id", invocation_id)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "operation_ref", operation_ref)
        object.__setattr__(self, "input", payload)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "request_ref", request_ref)
        object.__setattr__(self, "idempotency_key", idempotency_key)

    @classmethod
    def from_wire(cls, raw: Any) -> "PlaneHostCall":
        data = _strict_wire_object(raw, "host.request", MAX_HOST_REQUEST_BYTES)
        _reject_unknown(
            data,
            {
                "protocol",
                "runId",
                "invocationId",
                "correlationId",
                "action",
                "operationRef",
                "input",
                "source",
                "requestRef",
                "idempotencyKey",
            },
            "host.request",
        )
        required = {
            "protocol",
            "runId",
            "invocationId",
            "correlationId",
            "action",
            "operationRef",
            "input",
            "source",
            "requestRef",
            "idempotencyKey",
        }
        if not required.issubset(data):
            raise PlaneHostRPCError(f"host.request is missing field(s): {', '.join(sorted(required.difference(data)))}")
        if data["protocol"] != HOST_PROTOCOL:
            raise PlaneHostRPCError("host.request protocol is unsupported")
        return cls(
            run_id=_text(data["runId"], "host.runId", 256),
            invocation_id=_text(data["invocationId"], "host.invocationId", 256),
            correlation_id=_text(data["correlationId"], "host.correlationId", 256),
            action=data["action"],
            operation_ref=_text(data["operationRef"], "host.operationRef", MAX_HOST_OPERATION_REF_BYTES),
            input=_object(data["input"], "host.input"),
            source=data["source"],
            request_ref=_text(data["requestRef"], "host.requestRef", 256),
            idempotency_key=_text(data["idempotencyKey"], "host.idempotencyKey", 256),
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "protocol": HOST_PROTOCOL,
            "runId": self.run_id,
            "invocationId": self.invocation_id,
            "correlationId": self.correlation_id,
            "action": self.action,
            "operationRef": self.operation_ref,
            "input": dict(self.input),
            "source": self.source,
            "requestRef": self.request_ref,
            "idempotencyKey": self.idempotency_key,
        }


def _is_provider_attempt_observation(call: PlaneHostCall) -> bool:
    return call.action == "observe" and call.operation_ref == "runtime.provider_attempt"


def _is_prepared_call(call: PlaneHostCall) -> bool:
    return call.operation_ref == "operation:work_item.read" and "preparedCallRef" in call.input


def _prepared_read_refs_from_search_result(output: Any) -> tuple[str, ...]:
    """Extract only the one top-level assignment handoff."""
    if not isinstance(output, Mapping):
        return ()
    result = output.get("result")
    if isinstance(output.get("results"), list):
        result = output
    if not isinstance(result, Mapping):
        return ()
    prepared_ref = result.get("assignmentWorkItemReadCall")
    if (
        not isinstance(prepared_ref, str)
        or not prepared_ref.startswith(PREPARED_CALL_PREFIX)
        or len(prepared_ref.encode("utf-8")) > MAX_PREPARED_CALL_REF_BYTES
    ):
        return ()
    return (prepared_ref,)


def _assignment_read_decision_requires_followup(output: Any) -> bool:
    if not isinstance(output, Mapping):
        return False
    result = output.get("result")
    if isinstance(output.get("results"), list):
        result = output
    if not isinstance(result, Mapping):
        return False
    decision = result.get("assignmentWorkItemReadDecision")
    return (
        isinstance(decision, Mapping)
        and decision.get("schemaVersion") == "plane.assignment-read-handoff/v1"
        and decision.get("recognizedCount") != 1
        and decision.get("failureClass") in _ASSIGNMENT_READ_FAILURES
    )


def _prepared_read_refs_from_code_mode_result(output: Any) -> tuple[str, ...]:
    """Find opaque reads produced by Code Mode search and not read in that turn."""

    if not isinstance(output, Mapping) or "preparedReadResult" in output:
        return ()
    observations = output.get("observations")
    if not isinstance(observations, list):
        return ()
    search_observed = False
    read_observed = False
    for observation in observations:
        if not isinstance(observation, Mapping):
            return ()
        if observation.get("source") != "code" or observation.get("action") != "code":
            return ()
        operation_ref = observation.get("operationRef")
        status = observation.get("status")
        if operation_ref == "operation:search_workspace" and status in {"ok", "replayed"}:
            search_observed = True
        elif operation_ref == "operation:work_item.read" and status in {"ok", "replayed"}:
            read_observed = True
    if not search_observed or read_observed:
        return ()
    return _prepared_read_refs_from_search_result(output.get("result"))


def _without_consumed_prepared_read_from_code_mode_result(
    output: Mapping[str, Any], prepared_ref: str
) -> dict[str, Any]:
    def is_consumed_presented_call(value: Any) -> bool:
        if isinstance(value, str):
            return value == prepared_ref
        if isinstance(value, Mapping) and set(value) == {"preparedCallRef"}:
            return value.get("preparedCallRef") == prepared_ref
        if isinstance(value, Mapping) and set(value) == {
            "action",
            "operationRef",
            "input",
        }:
            nested = value.get("input")
            return (
                value.get("action") == "read"
                and value.get("operationRef") == "operation:work_item.read"
                and isinstance(nested, Mapping)
                and set(nested) == {"preparedCallRef"}
                and nested.get("preparedCallRef") == prepared_ref
            )
        return False

    receipt = output.get("result")
    if not isinstance(receipt, Mapping):
        return dict(output)
    result = receipt.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
        return dict(output)
    results = [
        {
            key: value
            for key, value in item.items()
            if key != "workItemReadCall"
        }
        if isinstance(item, Mapping) and is_consumed_presented_call(item.get("workItemReadCall"))
        else item
        for item in result["results"]
    ]
    return {**output, "result": {**receipt, "result": {**result, "results": results}}}


_HOST_FAILURE_CLASSES = frozenset({"transport_unavailable", "callback_exception"})
_HOST_SOCKET_PHASES = frozenset({"accept", "read", "invoke", "serialize", "write"})
_HOST_SOCKET_STATES = frozenset({"failed", "closed"})
_HOST_SOCKET_ERROR_CODES = frozenset({"HOST_UNAVAILABLE", "HOST_SOCKET_UNAVAILABLE"})
_PREPARED_DIAGNOSTIC_FAILURES = frozenset(
    {"malformed", "unknown", "digest_mismatch", "binding_mismatch"}
)
_PREPARED_DIAGNOSTIC_FORMS = frozenset(
    {"canonical_ref", "ready_to_call", "unrecognized"}
)
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
_SHAPE_KEY_ALLOWED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
)
_SHAPE_KEY_SENSITIVE = frozenset({"auth", "credential", "key", "password", "secret", "token"})
_SHAPE_KEY_LIMIT = 16
_SHAPE_NODE_LIMIT = 64
_SHAPE_DEPTH_LIMIT = 8
_SHAPE_ID_KEY = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def _shape_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def _safe_shape_key(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        return "redacted_key"
    lowered = value.casefold()
    if any(part in lowered for part in _SHAPE_KEY_SENSITIVE):
        return "redacted_key"
    if any(char not in _SHAPE_KEY_ALLOWED for char in value):
        return "redacted_key"
    if _SHAPE_ID_KEY.fullmatch(value) or (
        len(value) >= 32 and all(char in "0123456789abcdefABCDEF" for char in value)
    ):
        return "redacted_key"
    return value


def _prepared_shape_summary(value: Any) -> dict[str, Any]:
    key_names: set[str] = set()
    value_types: set[str] = set()
    node_count = 0
    max_depth = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal node_count, max_depth
        if node_count >= _SHAPE_NODE_LIMIT:
            return
        node_count += 1
        max_depth = max(max_depth, min(depth, _SHAPE_DEPTH_LIMIT))
        value_types.add(_shape_value_type(item))
        if isinstance(item, Mapping):
            for key, child in list(item.items())[:_SHAPE_KEY_LIMIT]:
                key_names.add(_safe_shape_key(key))
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item[:_SHAPE_KEY_LIMIT]:
                visit(child, depth + 1)

    visit(value, 0)
    try:
        size = len(_canonical(value, "prepared-call shape"))
    except (TypeError, ValueError, OverflowError):
        size_class = "unknown"
    else:
        size_class = "small" if size <= 256 else "medium" if size <= 1024 else "large"
    ordered_keys = sorted(key_names)
    return {
        "keyNames": ordered_keys[:_SHAPE_KEY_LIMIT],
        "keyNamesTruncated": len(ordered_keys) > _SHAPE_KEY_LIMIT,
        "valueTypes": sorted(value_types),
        "nestingDepth": max_depth,
        "sizeClass": size_class,
    }


def _prepared_accepted_form(value: Any) -> str:
    def is_prepared_ref_shape(candidate: Any) -> bool:
        if not isinstance(candidate, str) or not candidate.startswith(
            PREPARED_CALL_PREFIX
        ):
            return False
        try:
            _text(candidate, "host.preparedCallRef", MAX_PREPARED_CALL_REF_BYTES)
        except PlaneHostRPCError:
            return False
        return True

    def is_ready_to_call_shape(candidate: Any) -> bool:
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "action",
            "operationRef",
            "input",
        }:
            return False
        if (
            candidate.get("action") != "read"
            or candidate.get("operationRef") != "operation:work_item.read"
        ):
            return False
        nested = candidate.get("input")
        return (
            isinstance(nested, Mapping)
            and set(nested) == {"preparedCallRef"}
            and is_prepared_ref_shape(nested["preparedCallRef"])
        )

    if not isinstance(value, Mapping):
        return "unrecognized"
    if set(value) == {"preparedCallRef"}:
        prepared_ref = value["preparedCallRef"]
        if is_prepared_ref_shape(prepared_ref):
            return "canonical_ref"
        if (
            isinstance(prepared_ref, Mapping)
            and set(prepared_ref) == {"preparedCallRef"}
            and is_prepared_ref_shape(prepared_ref["preparedCallRef"])
        ):
            return "canonical_ref"
        if is_ready_to_call_shape(prepared_ref):
            return "ready_to_call"
        if isinstance(prepared_ref, str):
            try:
                envelope = _canonical_prepared_wrapper(prepared_ref)
            except PlaneHostRPCError:
                return "unrecognized"
            nested = envelope.get("input")
            if (
                set(envelope) == {"action", "operationRef", "input"}
                and envelope.get("action") == "read"
                and envelope.get("operationRef") == "operation:work_item.read"
                and isinstance(nested, Mapping)
                and set(nested) == {"preparedCallRef"}
                and is_prepared_ref_shape(nested["preparedCallRef"])
            ):
                return "ready_to_call"
        return "unrecognized"
    if set(value) != {"action", "operationRef", "input"}:
        return "unrecognized"
    if value.get("action") != "read" or value.get("operationRef") != "operation:work_item.read":
        return "unrecognized"
    nested = value.get("input")
    if (
        isinstance(nested, Mapping)
        and set(nested) == {"preparedCallRef"}
        and is_prepared_ref_shape(nested["preparedCallRef"])
    ):
        return "ready_to_call"
    return "unrecognized"


def _normalize_model_prepared_read_input(input_data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Unwrap exactly one model-facing ready-to-call read envelope.

    The Plane host registry deliberately accepts only its canonical opaque
    reference shape. The model-facing adapter may receive the historical
    ready-to-call envelope nested under ``preparedCallRef``; normalize that
    one shape before handing the input to the strict registry.
    """

    if "preparedCallRef" not in input_data:
        return input_data
    if set(input_data) != {"preparedCallRef"}:
        raise PreparedCallInvalid("malformed")
    prepared_ref = input_data["preparedCallRef"]
    if not isinstance(prepared_ref, Mapping):
        return input_data
    if set(prepared_ref) == {"preparedCallRef"}:
        return input_data
    if set(prepared_ref) != {"action", "operationRef", "input"}:
        raise PreparedCallInvalid("malformed")
    if (
        prepared_ref.get("action") != "read"
        or prepared_ref.get("operationRef") != "operation:work_item.read"
    ):
        raise PreparedCallInvalid("malformed")
    nested = prepared_ref.get("input")
    if not isinstance(nested, Mapping) or set(nested) != {"preparedCallRef"}:
        raise PreparedCallInvalid("malformed")
    canonical_ref = nested["preparedCallRef"]
    if not isinstance(canonical_ref, str) or not canonical_ref.startswith(PREPARED_CALL_PREFIX):
        raise PreparedCallInvalid("malformed")
    try:
        _text(canonical_ref, "host.preparedCallRef", MAX_PREPARED_CALL_REF_BYTES)
    except PlaneHostRPCError as exc:
        raise PreparedCallInvalid("malformed") from exc
    return {"preparedCallRef": canonical_ref}


def _prepared_shape_diagnostic(value: Any, failure_class: str) -> dict[str, Any]:
    if failure_class not in _PREPARED_DIAGNOSTIC_FAILURES:
        failure_class = "malformed"
    accepted_form = _prepared_accepted_form(value)
    if accepted_form not in _PREPARED_DIAGNOSTIC_FORMS:
        accepted_form = "unrecognized"
    return {
        "schemaVersion": "plane.prepared-call-shape/v1",
        "acceptedForm": accepted_form,
        "failureClass": failure_class,
        "shape": _prepared_shape_summary(value),
    }


def _bounded_prepared_shape_diagnostic(value: Any) -> dict[str, Any] | None:
    """Keep only the finite, value-free prepared-call shape contract."""

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
        or len(key_names) > _SHAPE_KEY_LIMIT
        or any(_safe_shape_key(item) != item for item in key_names)
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
        or not 0 <= shape["nestingDepth"] <= _SHAPE_DEPTH_LIMIT
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


def _bounded_code_mode_error_class(value: Any) -> str | None:
    return value if isinstance(value, str) and value in CODE_MODE_ERROR_CLASSES else None


@dataclass(frozen=True)
class PlaneHostResult:
    """Canonical host response returned to Hermes."""

    request_ref: str
    correlation_id: str
    idempotency_key: str
    status: str
    replayed: bool
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    publication: Mapping[str, Any] | None = None
    prepared_call_invalid_reason: str | None = None

    def __post_init__(self) -> None:
        _text(self.request_ref, "host.result.requestRef", 256)
        _text(self.correlation_id, "host.result.correlationId", 256)
        _text(self.idempotency_key, "host.result.idempotencyKey", 256)
        status = _text(self.status, "host.result.status", 32)
        if status not in _RESULT_STATUSES:
            raise PlaneHostRPCError(f"unsupported host result status: {status!r}")
        if not isinstance(self.replayed, bool):
            raise PlaneHostRPCError("host.result.replayed must be boolean")
        if status == "replayed" and not self.replayed:
            raise PlaneHostRPCError("replayed host result must set replayed=true")
        if status in {"denied", "conflict", "unavailable", "invalid"}:
            _text(self.error_code, "host.result.errorCode", 128)
            _text(self.error_message, "host.result.errorMessage", 2048)
        elif self.error_code is not None or self.error_message is not None:
            raise PlaneHostRPCError("successful host result cannot carry an error")
        if self.prepared_call_invalid_reason is not None:
            if (
                self.error_code != "PREPARED_CALL_INVALID"
                or status != "invalid"
                or self.prepared_call_invalid_reason not in _PREPARED_CALL_INVALID_REASONS
            ):
                raise PlaneHostRPCError("prepared-call diagnostic is invalid")
        if self.publication is not None:
            _object(self.publication, "host.result.publication")
        _bounded(self.to_wire(), "host.result", MAX_HOST_RESULT_BYTES)
        object.__setattr__(self, "status", status)

    @classmethod
    def from_wire(cls, raw: Any) -> "PlaneHostResult":
        data = _strict_wire_object(raw, "host.result", MAX_HOST_RESULT_BYTES)
        _reject_unknown(
            data,
            {
                "protocol",
                "requestRef",
                "correlationId",
                "idempotencyKey",
                "status",
                "replayed",
                "output",
                "errorCode",
                "errorMessage",
                "publication",
            },
            "host.result",
        )
        required = {"protocol", "requestRef", "correlationId", "idempotencyKey", "status", "replayed", "output"}
        if not required.issubset(data):
            raise PlaneHostRPCError(f"host.result is missing field(s): {', '.join(sorted(required.difference(data)))}")
        if data["protocol"] != HOST_PROTOCOL:
            raise PlaneHostRPCError("host.result protocol is unsupported")
        return cls(
            request_ref=_text(data["requestRef"], "host.result.requestRef", 256),
            correlation_id=_text(data["correlationId"], "host.result.correlationId", 256),
            idempotency_key=_text(data["idempotencyKey"], "host.result.idempotencyKey", 256),
            status=data["status"],
            replayed=data["replayed"],
            output=data["output"],
            error_code=data.get("errorCode"),
            error_message=data.get("errorMessage"),
            publication=data.get("publication"),
        )

    def to_wire(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "protocol": HOST_PROTOCOL,
            "requestRef": self.request_ref,
            "correlationId": self.correlation_id,
            "idempotencyKey": self.idempotency_key,
            "status": self.status,
            "replayed": self.replayed,
            "output": self.output,
        }
        if self.error_code is not None:
            value["errorCode"] = self.error_code
        if self.error_message is not None:
            value["errorMessage"] = self.error_message
        if self.publication is not None:
            value["publication"] = dict(self.publication)
        return value


def _host_operation_failure_evidence(
    call: PlaneHostCall | None,
    result: PlaneHostResult | None = None,
    *,
    error_code: str | None = None,
    failure_class: str | None = None,
    socket_phase: str | None = None,
    socket_state: str = "failed",
    prepared_handoff: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Project one failed callback into the bounded runner evidence shape."""

    if call is not None and call.action == "observe":
        return None
    if socket_phase is not None and (
        socket_phase not in _HOST_SOCKET_PHASES
        or socket_state not in _HOST_SOCKET_STATES
        or error_code not in _HOST_SOCKET_ERROR_CODES
    ):
        return None
    operation_id = call.operation_ref.removeprefix("operation:") if call is not None else "unavailable"
    output = result.output if result is not None and isinstance(result.output, Mapping) else {}
    resolved_error_code = (
        error_code
        or (result.error_code if result is not None else None)
        or (
            output.get("error", {}).get("code")
            if isinstance(output.get("error"), Mapping)
            else None
        )
    )
    if call is not None and call.action != "publish" and result is not None and (
        (result.status == "denied" and resolved_error_code == "NOT_AUTHORIZED")
        or (result.status == "invalid" and resolved_error_code == "VALIDATION_ERROR")
    ):
        # Generic tool denials and validation failures are expected operation
        # observations. Publication failures remain terminal runtime evidence.
        return None

    request_id = output.get("requestId")
    audit_receipt = output.get("auditReceipt") or output.get("gatewayReceipt")

    def bounded_ref(value: Any, prefix: str) -> str:
        if not isinstance(value, str) or not value:
            return "unavailable"
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        if len(value.encode("utf-8")) > 128 or any(char not in allowed for char in value):
            return "unavailable"
        return f"{prefix}{value}"

    def bounded_code(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return "unavailable"
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        if len(value.encode("utf-8")) > 128 or any(char not in allowed for char in value):
            return "unavailable"
        return value

    def bounded_operation_id(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return "unavailable"
        # Versioned host operations use the canonical ``name@version`` form
        # (for example, plane.code-mode.execute@1). Keep that exact identity
        # in bounded diagnostics while retaining the stricter error-code
        # alphabet above.
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-@"
        if len(value.encode("utf-8")) > 128 or any(char not in allowed for char in value):
            return "unavailable"
        return value

    status = result.status if result is not None else "unavailable"
    if status not in {"denied", "conflict", "unavailable", "invalid"}:
        status = "unavailable"
    evidence = {
        "operationId": bounded_operation_id(operation_id),
        "attemptRef": bounded_ref(request_id, "operation-attempt:")
        if request_id is not None
        else call.request_ref if call is not None else "unavailable",
        "receiptRef": bounded_ref(audit_receipt, "audit-receipt:"),
        "status": status,
        "errorCode": bounded_code(
            resolved_error_code
        ),
        "codeModePhase": (
            "host_callback"
            if call is not None and call.action == "code" and call.source == "code"
            else "unavailable"
        ),
    }
    if failure_class in _HOST_FAILURE_CLASSES:
        evidence["failureClass"] = failure_class
    if socket_phase is not None:
        evidence["socketPhase"] = socket_phase
        evidence["socketState"] = socket_state
    if result is not None and call is not None and result.prepared_call_invalid_reason in _PREPARED_CALL_INVALID_REASONS:
        evidence["preparedCallInvalidReason"] = result.prepared_call_invalid_reason
    if result is not None and call is not None and resolved_error_code == "PREPARED_CALL_INVALID":
        shape_diagnostic = _bounded_prepared_shape_diagnostic(output.get("shapeDiagnostic"))
        if shape_diagnostic is None:
            shape_diagnostic = _prepared_shape_diagnostic(
                call.input,
                result.prepared_call_invalid_reason or "malformed",
            )
        evidence["shapeDiagnostic"] = shape_diagnostic
    if prepared_handoff is not None:
        bounded_handoff = _bounded_prepared_handoff(prepared_handoff)
        if bounded_handoff is not None:
            evidence["preparedHandoff"] = bounded_handoff
    code_mode_error_class = _bounded_code_mode_error_class(output.get("codeModeErrorClass"))
    if code_mode_error_class is not None:
        evidence["codeModeErrorClass"] = code_mode_error_class
    return evidence


class PlaneHostServer:
    """Serve one invocation's host callbacks over a local Unix socket."""

    def __init__(
        self,
        *,
        socket_path: str | os.PathLike[str],
        invoke: Callable[[PlaneHostCall], PlaneHostResult],
        max_calls: int = MAX_HOST_CALLS,
        max_observation_calls: int = MAX_HOST_OBSERVATION_CALLS,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not callable(invoke):
            raise TypeError("invoke must be callable")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
            raise ValueError("max_calls must be a positive integer")
        if (
            isinstance(max_observation_calls, bool)
            or not isinstance(max_observation_calls, int)
            or max_observation_calls <= 0
        ):
            raise ValueError("max_observation_calls must be a positive integer")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute():
            raise ValueError("socket_path must be absolute")
        self._invoke = invoke
        self._max_calls = max_calls
        self._max_observation_calls = max_observation_calls
        self._timeout_seconds = float(timeout_seconds)
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._error: BaseException | None = None
        self._records: dict[str, PlaneHostResult] = {}
        self._failure_evidence: dict[str, Any] | None = None
        self._call_count = 0
        self._observation_count = 0
        self._lock = threading.RLock()

    @property
    def error(self) -> BaseException | None:
        return self._error

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    @property
    def observation_count(self) -> int:
        with self._lock:
            return self._observation_count

    @property
    def failure_evidence(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._failure_evidence) if self._failure_evidence is not None else None

    @property
    def prepared_handoff_trace(self) -> dict[str, Any] | None:
        target = getattr(self._invoke, "__self__", None)
        trace = getattr(target, "prepared_handoff_trace", None)
        return trace if isinstance(trace, Mapping) else None

    def _record_failure(
        self,
        call: PlaneHostCall | None,
        result: PlaneHostResult | None = None,
        *,
        error_code: str | None = None,
        failure_class: str | None = None,
        socket_phase: str | None = None,
        socket_state: str = "failed",
    ):
        evidence = _host_operation_failure_evidence(
            call,
            result,
            error_code=error_code,
            failure_class=failure_class,
            socket_phase=socket_phase,
            socket_state=socket_state,
            prepared_handoff=self.prepared_handoff_trace,
        )
        if evidence is None:
            return
        with self._lock:
            if self._failure_evidence is None:
                self._failure_evidence = evidence

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("host server has already started")
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            existing = self.socket_path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(existing.st_mode):
                raise PlaneHostRPCError("host socket path is not a socket")
            self.socket_path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.settimeout(self._timeout_seconds)
        listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        listener.listen(1)
        self._listener = listener
        self._thread = threading.Thread(target=self._serve, name="plane-agent-host", daemon=True)
        self._thread.start()
        if not self._ready.wait(self._timeout_seconds):
            self.close()
            raise PlaneHostRPCError("host server did not become ready")
        if self._error is not None:
            error = self._error
            self.close()
            raise PlaneHostRPCError("host server could not start") from error

    def close(self) -> None:
        self._closed.set()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._timeout_seconds)
        self._thread = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def __enter__(self) -> "PlaneHostServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _serve(self) -> None:
        listener = self._listener
        if listener is None:
            self._error = PlaneHostRPCError("host listener is unavailable")
            self._ready.set()
            return
        self._ready.set()
        while not self._closed.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self._closed.is_set():
                    self._error = PlaneHostRPCError("host listener became unavailable")
                    self._record_failure(
                        None,
                        error_code="HOST_SOCKET_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase="accept",
                    )
                return
            with connection:
                connection.settimeout(self._timeout_seconds)
                carry = bytearray()
                try:
                    line = self._read_line(connection, carry)
                except (OSError, PlaneHostRPCError):
                    self._record_failure(
                        None,
                        error_code="HOST_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase="read",
                    )
                    continue
                if line is None:
                    self._record_failure(
                        None,
                        error_code="HOST_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase="read",
                        socket_state="closed",
                    )
                    continue
                call: PlaneHostCall | None = None
                try:
                    call = PlaneHostCall.from_wire(line)
                except Exception:
                    self._record_failure(
                        None,
                        error_code="HOST_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase="read",
                    )
                    continue
                phase = "invoke"
                try:
                    result = self._invoke_once(call)
                    phase = "serialize"
                    response = result.to_wire()
                    _bounded(response, "host.result", MAX_HOST_RESULT_BYTES)
                except Exception:
                    # Never expose application/provider diagnostics over the
                    # host socket. The Hermes client observes peer failure.
                    self._record_failure(
                        call,
                        error_code="HOST_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase=phase,
                    )
                    continue
                try:
                    encoded = _canonical(response, "host.result") + b"\n"
                    connection.sendall(encoded)
                except OSError:
                    self._record_failure(
                        call,
                        error_code="HOST_UNAVAILABLE",
                        failure_class="transport_unavailable",
                        socket_phase="write",
                    )
                    continue

    def _invoke_once(self, call: PlaneHostCall) -> PlaneHostResult:
        with self._lock:
            replay = self._records.get(call.request_ref)
            if replay is not None:
                if _is_prepared_call(call) and replay.correlation_id != call.correlation_id:
                    return PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="invalid",
                        replayed=False,
                        output={
                            "shapeDiagnostic": _prepared_shape_diagnostic(
                                call.input, "malformed"
                            )
                        },
                        error_code="PREPARED_CALL_INVALID",
                        error_message="Prepared reference replay identity is invalid",
                        prepared_call_invalid_reason="malformed",
                    )
                replay_status = (
                    replay.status if replay.status in {"denied", "conflict", "unavailable", "invalid"} else "replayed"
                )
                return PlaneHostResult(
                    request_ref=replay.request_ref,
                    correlation_id=replay.correlation_id,
                    idempotency_key=replay.idempotency_key,
                    status=replay_status,
                    replayed=True,
                    output=replay.output,
                    error_code=replay.error_code,
                    error_message=replay.error_message,
                    publication=None,
                    prepared_call_invalid_reason=replay.prepared_call_invalid_reason,
                )
            if _is_provider_attempt_observation(call):
                if self._observation_count >= self._max_observation_calls:
                    result = PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="denied",
                        replayed=False,
                        output=None,
                        error_code="HOST_OBSERVATION_BUDGET_EXCEEDED",
                        error_message="Plane provider-attempt observation budget exhausted",
                    )
                    self._record_failure(call, result)
                    return result
                self._observation_count += 1
            else:
                if self._call_count >= self._max_calls:
                    result = PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="denied",
                        replayed=False,
                        output=None,
                        error_code="HOST_BUDGET_EXCEEDED",
                        error_message="Plane host callback budget exhausted",
                    )
                    self._record_failure(call, result)
                    return result
                self._call_count += 1
        try:
            result = self._invoke(call)
            if not isinstance(result, PlaneHostResult):
                raise PlaneHostRPCError("host callback returned an invalid result")
            if (
                result.request_ref != call.request_ref
                or result.correlation_id != call.correlation_id
                or result.idempotency_key != call.idempotency_key
            ):
                raise PlaneHostRPCError("host callback result is not bound to the request")
        except PlaneHostRPCError:
            self._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="callback_exception",
                socket_phase="invoke",
            )
            raise
        except Exception as exc:
            self._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="callback_exception",
                socket_phase="invoke",
            )
            raise PlaneHostRPCError("host callback is unavailable") from exc
        if result.status not in {"ok", "replayed"}:
            self._record_failure(call, result)
        with self._lock:
            self._records[call.request_ref] = result
        return result

    def _read_line(self, connection: socket.socket, carry: bytearray) -> str | None:
        while True:
            newline = carry.find(b"\n")
            if newline >= 0:
                frame = bytes(carry[:newline])
                del carry[: newline + 1]
                if not frame:
                    raise PlaneHostRPCError("host request is empty")
                try:
                    return frame.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise PlaneHostRPCError("host request is not UTF-8") from exc
            if len(carry) >= MAX_HOST_REQUEST_BYTES + 1:
                raise PlaneHostRPCError("host request exceeds the size limit")
            chunk = connection.recv(min(4096, MAX_HOST_REQUEST_BYTES + 1 - len(carry)))
            if not chunk:
                return None
            carry.extend(chunk)


class PlaneHostHTTPClient:
    """Invoke the Plane host seam from the isolated runtime service."""

    def __init__(self, *, url: str, auth_token: str, timeout_seconds: float = 5.0) -> None:
        self._url = self._validate_url(url)
        self._auth_token = _text(auth_token, "host.authToken", 512)
        self._timeout_seconds = self._validate_timeout(timeout_seconds)

    def invoke(self, call: PlaneHostCall) -> PlaneHostResult:
        if not isinstance(call, PlaneHostCall):
            raise PlaneHostRPCError("host callback request is invalid")
        payload = _canonical(call.to_wire(), "host.request")
        if len(payload) > MAX_HOST_REQUEST_BYTES:
            raise PlaneHostRPCError("host request exceeds the size limit")
        parsed = urllib.parse.urlsplit(self._url)
        connection: http.client.HTTPConnection | http.client.HTTPSConnection
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=self._timeout_seconds)
        path = urllib.parse.urlunsplit(("", "", parsed.path or HOST_HTTP_PATH, parsed.query, ""))
        try:
            connection.request(
                "POST",
                path,
                body=payload,
                headers={
                    "Authorization": f"Bearer {self._auth_token}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_HOST_HTTP_RESPONSE_BYTES + 1)
            if len(body) > MAX_HOST_HTTP_RESPONSE_BYTES or response.status != 200:
                raise PlaneHostRPCError("Plane host callback was rejected")
            result = PlaneHostResult.from_wire(body)
            if (
                result.request_ref != call.request_ref
                or result.correlation_id != call.correlation_id
                or result.idempotency_key != call.idempotency_key
            ):
                raise PlaneHostRPCError("Plane host callback result is not bound to the request")
            return result
        except (OSError, ValueError, http.client.HTTPException, PlaneHostRPCError) as exc:
            if isinstance(exc, PlaneHostRPCError):
                raise
            raise PlaneHostRPCError("Plane host callback is unavailable") from exc
        finally:
            connection.close()

    @staticmethod
    def _validate_url(value: str) -> str:
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 2048:
            raise PlaneHostRPCError("host URL is invalid")
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise PlaneHostRPCError("host URL is invalid")
        if parsed.query or parsed.fragment:
            raise PlaneHostRPCError("host URL is invalid")
        try:
            if parsed.port is not None and not 0 < parsed.port <= 65535:
                raise PlaneHostRPCError("host URL port is invalid")
        except ValueError as exc:
            raise PlaneHostRPCError("host URL port is invalid") from exc
        return value.rstrip("/")

    @staticmethod
    def _validate_timeout(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 or value > 60:
            raise PlaneHostRPCError("host callback timeout is invalid")
        return float(value)


class _PlaneHostHTTPHandler(BaseHTTPRequestHandler):
    server: "_PlaneHostHTTPServer"

    def do_POST(self) -> None:  # noqa: N802
        if self.path != HOST_HTTP_PATH:
            self._write(404, {"error": "not_found"})
            return
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or not self.server.auth_matches(authorization[7:]):
            self._write(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            self._write(400, {"error": "invalid_request"})
            return
        if length < 0 or length > MAX_HOST_REQUEST_BYTES:
            self._write(413, {"error": "request_too_large"})
            return
        call: PlaneHostCall | None = None
        phase = "read"
        try:
            raw = self.rfile.read(length)
            call = PlaneHostCall.from_wire(raw)
            phase = "invoke"
            result = self.server.invoke_once(call)
            phase = "serialize"
            payload = _canonical(result.to_wire(), "host.result")
            if len(payload) > MAX_HOST_RESULT_BYTES:
                raise PlaneHostRPCError("host result exceeds the size limit")
        except Exception:
            self.server.owner._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="callback_exception" if phase == "invoke" else "transport_unavailable",
                socket_phase=phase,
            )
            self._write(503, {"error": "host_unavailable"}, call=call)
            return
        self._write(200, result.to_wire(), call=call)

    def _write(self, status: int, value: Mapping[str, Any], *, call: PlaneHostCall | None = None) -> None:
        try:
            payload = _canonical(value, "host HTTP response")
            if len(payload) > MAX_HOST_HTTP_RESPONSE_BYTES:
                status = 500
                payload = b'{"error":"response_too_large"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            self.server.owner._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="transport_unavailable",
                socket_phase="write",
            )

    def log_message(self, format: str, *args: object) -> None:
        # Request headers, including the per-invocation token, never enter logs.
        message = format % args
        if len(message) > 256:
            message = message[:256]
        sys.stderr.write(f"event=agent.runtime.host_http message={message!r}\n")


class _PlaneHostHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], owner: "PlaneHostHTTPServer") -> None:
        super().__init__(address, _PlaneHostHTTPHandler)
        self.owner = owner

    def auth_matches(self, token: str) -> bool:
        return hmac.compare_digest(token.encode("utf-8"), self.owner.auth_token.encode("utf-8"))

    def invoke_once(self, call: PlaneHostCall) -> PlaneHostResult:
        return self.owner._invoke_once(call)


class PlaneHostHTTPServer:
    """Bounded per-invocation HTTP host seam on the internal Compose network."""

    def __init__(
        self,
        *,
        bind_host: str,
        advertised_host: str,
        port: int,
        auth_token: str,
        invoke: Callable[[PlaneHostCall], PlaneHostResult],
        timeout_seconds: float = 5.0,
        max_calls: int = MAX_HOST_CALLS,
        max_observation_calls: int = MAX_HOST_OBSERVATION_CALLS,
    ) -> None:
        if not bind_host or not isinstance(bind_host, str) or len(bind_host) > 255 or "\x00" in bind_host:
            raise PlaneHostRPCError("host bind address is invalid")
        if not advertised_host or not isinstance(advertised_host, str) or len(advertised_host) > 255:
            raise PlaneHostRPCError("host advertised address is invalid")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
            raise PlaneHostRPCError("host port is invalid")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
            raise PlaneHostRPCError("max_calls must be a positive integer")
        if (
            isinstance(max_observation_calls, bool)
            or not isinstance(max_observation_calls, int)
            or max_observation_calls <= 0
        ):
            raise PlaneHostRPCError("max_observation_calls must be a positive integer")
        self.bind_host = bind_host
        self.advertised_host = advertised_host
        self.port = port
        self.auth_token = _text(auth_token, "host.authToken", 512)
        self._invoke = invoke
        self._timeout_seconds = PlaneHostHTTPClient._validate_timeout(timeout_seconds)
        self._max_calls = max_calls
        self._max_observation_calls = max_observation_calls
        self._records: dict[str, PlaneHostResult] = {}
        self._failure_evidence: dict[str, Any] | None = None
        self._call_count = 0
        self._observation_count = 0
        self._lock = threading.RLock()
        self._server: _PlaneHostHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        server = self._server
        port = self.port if server is None else server.server_address[1]
        return f"http://{self.advertised_host}:{port}{HOST_HTTP_PATH}"

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("host HTTP server has already started")
        server = _PlaneHostHTTPServer((self.bind_host, self.port), self)
        server.timeout = self._timeout_seconds
        self._server = server
        self.port = int(server.server_address[1])
        self._thread = threading.Thread(target=server.serve_forever, name="plane-agent-host-http", daemon=True)
        self._thread.start()

    def close(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=self._timeout_seconds)

    def __enter__(self) -> "PlaneHostHTTPServer":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    @property
    def observation_count(self) -> int:
        with self._lock:
            return self._observation_count

    @property
    def failure_evidence(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._failure_evidence) if self._failure_evidence is not None else None

    @property
    def prepared_handoff_trace(self) -> dict[str, Any] | None:
        target = getattr(self._invoke, "__self__", None)
        trace = getattr(target, "prepared_handoff_trace", None)
        return trace if isinstance(trace, Mapping) else None

    def _record_failure(
        self,
        call: PlaneHostCall | None,
        result: PlaneHostResult | None = None,
        *,
        error_code: str | None = None,
        failure_class: str | None = None,
        socket_phase: str | None = None,
        socket_state: str = "failed",
    ):
        evidence = _host_operation_failure_evidence(
            call,
            result,
            error_code=error_code,
            failure_class=failure_class,
            socket_phase=socket_phase,
            socket_state=socket_state,
            prepared_handoff=self.prepared_handoff_trace,
        )
        if evidence is None:
            return
        with self._lock:
            if self._failure_evidence is None:
                self._failure_evidence = evidence

    def _invoke_once(self, call: PlaneHostCall) -> PlaneHostResult:
        with self._lock:
            replay = self._records.get(call.request_ref)
            if replay is not None:
                if _is_prepared_call(call) and replay.correlation_id != call.correlation_id:
                    return PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="invalid",
                        replayed=False,
                        output={
                            "shapeDiagnostic": _prepared_shape_diagnostic(
                                call.input, "malformed"
                            )
                        },
                        error_code="PREPARED_CALL_INVALID",
                        error_message="Prepared reference replay identity is invalid",
                        prepared_call_invalid_reason="malformed",
                    )
                return PlaneHostResult(
                    request_ref=replay.request_ref,
                    correlation_id=replay.correlation_id,
                    idempotency_key=replay.idempotency_key,
                    status=replay.status if replay.status in _RESULT_STATUSES - {"ok"} else "replayed",
                    replayed=True,
                    output=replay.output,
                    error_code=replay.error_code,
                    error_message=replay.error_message,
                    publication=None,
                    prepared_call_invalid_reason=replay.prepared_call_invalid_reason,
                )
            if _is_provider_attempt_observation(call):
                if self._observation_count >= self._max_observation_calls:
                    result = PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="denied",
                        replayed=False,
                        output=None,
                        error_code="HOST_OBSERVATION_BUDGET_EXCEEDED",
                        error_message="Plane provider-attempt observation budget exhausted",
                    )
                    self._record_failure(call, result)
                    return result
                self._observation_count += 1
            else:
                if self._call_count >= self._max_calls:
                    result = PlaneHostResult(
                        request_ref=call.request_ref,
                        correlation_id=call.correlation_id,
                        idempotency_key=call.idempotency_key,
                        status="denied",
                        replayed=False,
                        output=None,
                        error_code="HOST_BUDGET_EXCEEDED",
                        error_message="Plane host callback budget exhausted",
                    )
                    self._record_failure(call, result)
                    return result
                self._call_count += 1
        try:
            result = self._invoke(call)
            if not isinstance(result, PlaneHostResult):
                raise PlaneHostRPCError("host callback returned an invalid result")
            if (
                result.request_ref != call.request_ref
                or result.correlation_id != call.correlation_id
                or result.idempotency_key != call.idempotency_key
            ):
                raise PlaneHostRPCError("host callback result is not bound to the request")
        except PlaneHostRPCError:
            self._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="callback_exception",
                socket_phase="invoke",
            )
            raise
        except Exception as exc:
            self._record_failure(
                call,
                error_code="HOST_UNAVAILABLE",
                failure_class="callback_exception",
                socket_phase="invoke",
            )
            raise PlaneHostRPCError("host callback is unavailable") from exc
        if result.status not in {"ok", "replayed"}:
            self._record_failure(call, result)
        with self._lock:
            self._records[call.request_ref] = result
        return result


def _publication_ref(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise _PublicationReceiptInvalid("receipt_incomplete")
    if len(value.encode("utf-8")) > MAX_PUBLICATION_REF_BYTES:
        raise _PublicationReceiptInvalid("receipt_incomplete")
    if any(char not in _PUBLICATION_REF_ALLOWED for char in value):
        raise _PublicationReceiptInvalid("receipt_incomplete")
    return value


def _applied_outcome_publication_from_receipt(
    receipt: Mapping[str, Any],
    *,
    resource_ref: Any,
    run_ref: str,
    invocation_ref: str,
) -> dict[str, str]:
    """Project one fresh, complete gateway receipt into an applied publication."""

    if receipt.get("ok") is not True or receipt.get("replayed") is not False:
        raise _PublicationReceiptInvalid("receipt_not_fresh")
    if receipt.get("operationId") != "agent.outcome.publish" or receipt.get(
        "operationRef"
    ) != "operation:agent.outcome.publish":
        raise _PublicationReceiptInvalid("operation_mismatch")
    if receipt.get("runRef") != run_ref or receipt.get("invocationRef") != invocation_ref:
        raise _PublicationReceiptInvalid("callback_binding_mismatch")
    result = receipt.get("result")
    if not isinstance(result, Mapping) or result.get("published") is not True:
        raise _PublicationReceiptInvalid("missing_applied_marker")
    outcome = result.get("outcome")
    if (
        not isinstance(outcome, Mapping)
        or not isinstance(resource_ref, str)
        or outcome.get("outcomeRef") != resource_ref
    ):
        raise _PublicationReceiptInvalid("outcome_binding_mismatch")
    request_id = _publication_ref(receipt.get("requestId"), "requestId")
    gateway_receipt = _publication_ref(receipt.get("gatewayReceipt"), "gatewayReceipt")
    audit_receipt = _publication_ref(receipt.get("auditReceipt"), "auditReceipt")
    product_event_ref = _publication_ref(outcome.get("productEventRef"), "productEventRef")
    if not product_event_ref.startswith("product-event:"):
        raise _PublicationReceiptInvalid("receipt_incomplete")
    return {
        "action": "applied",
        "productKind": "outcome_submission",
        "productRef": resource_ref,
        "operationAttemptRef": f"operation-attempt:{request_id}",
        "operationRef": "operation:agent.outcome.publish",
        "applicationServiceRef": "application-service:agent-lifecycle",
        "gatewayReceiptRef": f"gateway-receipt:{gateway_receipt}",
        "receiptRef": f"receipt:{request_id}",
        "auditReceiptRef": f"audit-receipt:{audit_receipt}",
        "productEventRef": product_event_ref,
    }


class PlaneGatewayHostPort:
    """Bind host callbacks to one trusted invocation and the live gateway."""

    def __init__(
        self,
        host: Any,
        provider_attempt_recorder: Callable[[PlaneHostCall], Mapping[str, Any]] | None = None,
    ) -> None:
        if not callable(getattr(host, "call_operation", None)):
            raise TypeError("host must be a CodeModeHostRPC")
        self._host = host
        self._provider_attempt_recorder = provider_attempt_recorder
        self._run_ref = host.binding.run_ref
        self._invocation_ref = host.binding.invocation_ref
        self._prepared_call_registry = PreparedCallRegistry()
        self._prepared_calls = self._prepared_call_registry.records
        self._prepared_calls_lock = self._prepared_call_registry.lock
        self._prepared_read_auto_depth = 0
        setter = getattr(host, "set_prepared_call_registry", None)
        if callable(setter):
            setter(self._prepared_call_registry)
        self._prepared_read_handoff_pending = False

    @property
    def prepared_handoff_trace(self) -> dict[str, Any] | None:
        return self._prepared_call_registry.trace.snapshot()

    def invoke(self, call: PlaneHostCall) -> PlaneHostResult:
        if call.run_id != self._run_ref or call.invocation_id != self._invocation_ref:
            return self._error(call, "CALLBACK_BINDING_INVALID", "Host callback is not bound to this invocation")
        if (
            call.operation_ref == "operation:work_item.read"
            and call.action == "read"
            and self._prepared_read_auto_depth == 0
            and "preparedCallRef" in call.input
        ):
            self._prepared_call_registry.record_hermes_model_read(call.input)
        if call.action == "observe":
            if call.operation_ref != "runtime.provider_attempt" or self._provider_attempt_recorder is None:
                return self._error(call, "OPERATION_UNAVAILABLE", "Provider attempt observation is unavailable")
            try:
                output = self._provider_attempt_recorder(call)
            except Exception:
                return self._error(call, "PROVIDER_ATTEMPT_REJECTED", "Provider attempt evidence was rejected")
            if not isinstance(output, Mapping):
                return self._error(call, "PROVIDER_ATTEMPT_REJECTED", "Provider attempt evidence was invalid")
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="ok",
                replayed=False,
                output=dict(output),
            )
        if call.action == "code":
            if call.operation_ref != CODE_MODE_EXECUTION_OPERATION:
                return self._error(call, "VALIDATION_ERROR", "Code Mode execution operation is invalid")
            try:
                request = CodeModeExecutionRequest.from_wire(call.input)
                output = self._host.execute_typescript(request)
            except CodeModeExecutionError as exc:
                message = {
                    "SOURCE_TOO_LARGE": "Code Mode source exceeds its size bound.",
                    "VALIDATION_ERROR": "Code Mode execution input is invalid.",
                }.get(exc.code, "Code Mode execution input is invalid.")
                return self._error(call, exc.code, message)
            except ValueError:
                return self._error(call, "VALIDATION_ERROR", "Code Mode execution input is invalid")
            except Exception as exc:
                code = getattr(exc, "code", "CODE_MODE_FAILED")
                code_mode_error_class = _bounded_code_mode_error_class(getattr(exc, "error_class", None))
                message = {
                    "CANCELLED": "Code Mode was cancelled.",
                    "BUDGET_EXCEEDED": "Code Mode budget is exhausted.",
                    "SOURCE_TOO_LARGE": "Code Mode source exceeds its size bound.",
                    "VALIDATION_ERROR": "Code Mode source is invalid.",
                    "PROTOCOL_ERROR": "Code Mode host protocol failed closed.",
                    "ISOLATE_UNAVAILABLE": "Code Mode isolate is unavailable.",
                    "SPILL_EXCEEDED": "Code Mode result spill exceeded its bound.",
                    "CALLBACK_FAILED": "Code Mode callback failed closed.",
                    "OBSERVATION_LIMIT": "Code Mode observation budget is exhausted.",
                    "CODE_MODE_FAILED": "Code Mode execution failed in the restricted isolate.",
                }.get(code, "Code Mode execution failed in the restricted isolate.")
                output = (
                    {"codeModeErrorClass": code_mode_error_class}
                    if code_mode_error_class is not None
                    else None
                )
                return self._error(call, str(code), message, output=output)
            prepared_refs = _prepared_read_refs_from_code_mode_result(output)
            if prepared_refs or _assignment_read_decision_requires_followup(output):
                with self._prepared_calls_lock:
                    self._prepared_read_handoff_pending = True
            if len(prepared_refs) == 1:
                prepared_read_call = PlaneHostCall(
                    run_id=call.run_id,
                    invocation_id=call.invocation_id,
                    correlation_id=call.correlation_id,
                    action="read",
                    operation_ref="operation:work_item.read",
                    input={"preparedCallRef": prepared_refs[0]},
                    source="model",
                )
                self._prepared_call_registry.record_runtime_auto_read(prepared_refs[0])
                self._prepared_read_auto_depth += 1
                try:
                    prepared_read = self.invoke(prepared_read_call)
                finally:
                    self._prepared_read_auto_depth -= 1
                continuation_output = dict(output) if isinstance(output, Mapping) else {}
                if prepared_read.status in {"ok", "replayed"}:
                    continuation_output = _without_consumed_prepared_read_from_code_mode_result(
                        continuation_output, prepared_refs[0]
                    )
                continuation_output["preparedReadResult"] = prepared_read.to_wire()
                if prepared_read.status not in {"ok", "replayed"}:
                    return self._error(
                        call,
                        prepared_read.error_code or "PREPARED_CALL_INVALID",
                        "Prepared work-item read continuation failed",
                        output=continuation_output,
                        prepared_call_invalid_reason=prepared_read.prepared_call_invalid_reason,
                    )
                output = continuation_output
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="ok",
                replayed=False,
                output=output,
            )
        if call.action == "discover":
            if call.operation_ref != PLANE_DISCOVERY_OPERATION:
                return self._error(call, "VALIDATION_ERROR", "Unsupported Plane discovery operation")
            query = call.input.get("query", "")
            limit = call.input.get("limit", 20)
            if not isinstance(query, str) or not isinstance(limit, int) or isinstance(limit, bool):
                return self._error(call, "VALIDATION_ERROR", "Plane discovery input is invalid")
            receipt = self._host.search_operations(
                query,
                idempotency_key=call.idempotency_key,
                correlation_id=call.correlation_id,
                limit=limit,
            )
            if receipt.get("ok"):
                receipt = self._prepare_search_receipt(receipt)
            return self._from_receipt(call, receipt)
        if call.action == "publish":
            return self._publish(call)
        if not call.operation_ref.startswith("operation:"):
            return self._error(call, "VALIDATION_ERROR", "Plane operationRef is invalid")
        operation_id = call.operation_ref.removeprefix("operation:")
        if operation_id == "search_workspace" and self._prepared_read_handoff_is_pending():
            return self._error(
                call,
                "VALIDATION_ERROR",
                "A prepared work-item read is pending; invoke its returned workItemReadCall before another workspace search",
            )
        if operation_id == "work_item.read" and call.action != "read":
            return self._error(call, "VALIDATION_ERROR", "Work-item reads must use the read action")
        # Prepared refs are callable only as the complete read input. Do not
        # recursively inspect mutation payloads; outcome evidence may carry
        # opaque refs as ordinary data.
        if operation_id != "work_item.read" and set(call.input) == {"preparedCallRef"}:
            return self._error(
                call,
                "PREPARED_CALL_INVALID",
                "Prepared reference is only valid for work-item reads",
                output={
                    "shapeDiagnostic": _prepared_shape_diagnostic(
                        call.input, "malformed"
                    )
                },
                prepared_call_invalid_reason="malformed",
            )
        operation_input = call.input
        prepared_ref: str | None = None
        if operation_id == "work_item.read":
            try:
                if set(call.input).intersection({"action", "operationRef", "input", "workItemReadCall"}):
                    raise PreparedCallInvalid("malformed")
                operation_input = _normalize_model_prepared_read_input(call.input)
                operation_input = self._normalize_prepared_read_input(operation_input)
                if "preparedCallRef" in operation_input:
                    prepared_ref = operation_input["preparedCallRef"]
                operation_input = self._resolve_prepared_read_input(operation_input)
                if prepared_ref is not None:
                    replay = self._bind_or_replay_prepared_call(call, prepared_ref)
                    if replay is not None:
                        return replay
            except PreparedCallInvalid as exc:
                return self._error(
                    call,
                    "PREPARED_CALL_INVALID",
                    "Prepared work-item read reference is invalid",
                    output={
                        "shapeDiagnostic": _prepared_shape_diagnostic(
                            call.input, exc.reason
                        )
                    },
                    prepared_call_invalid_reason=exc.reason,
                )
            except PlaneHostRPCError:
                return self._error(
                    call,
                    "PREPARED_CALL_INVALID",
                    "Prepared work-item read reference is invalid",
                    output={
                        "shapeDiagnostic": _prepared_shape_diagnostic(
                            call.input, "malformed"
                        )
                    },
                    prepared_call_invalid_reason="malformed",
                )
        receipt = self._host.call_operation(
            operation_id,
            operation_input,
            idempotency_key=call.idempotency_key,
            correlation_id=call.correlation_id,
        )
        if operation_id == "search_workspace" and receipt.get("ok"):
            receipt = self._prepare_search_receipt(receipt)
        result = self._from_receipt(call, receipt)
        if operation_id == "agent.outcome.publish" and result.status == "ok":
            try:
                publication = _applied_outcome_publication_from_receipt(
                    receipt,
                    resource_ref=operation_input.get("outcome_ref"),
                    run_ref=self._run_ref,
                    invocation_ref=self._invocation_ref,
                )
            except _PublicationReceiptInvalid as exc:
                return self._publication_receipt_error(call, receipt, exc.reason)
            result = PlaneHostResult(
                request_ref=result.request_ref,
                correlation_id=result.correlation_id,
                idempotency_key=result.idempotency_key,
                status=result.status,
                replayed=result.replayed,
                output=result.output,
                publication=publication,
            )
        if prepared_ref is not None:
            with self._prepared_calls_lock:
                record = self._prepared_calls.get(prepared_ref)
                if record is not None and record.get("result") is None:
                    record["result"] = result
                if result.status in {"ok", "replayed"}:
                    self._prepared_call_registry.mark_consumed(prepared_ref)
                    self._prepared_read_handoff_pending = False
        return result

    def _prepare_search_receipt(self, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
        result = receipt.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
            return receipt
        assignment_target_ref = getattr(
            getattr(self._host, "binding", None), "assignment_target_ref", ""
        )
        target_issue_id = _issue_id_from_assignment_target(assignment_target_ref)
        matching_inputs: list[Mapping[str, Any]] = []
        prepared_results: list[Mapping[str, Any]] = []
        matching_result_indexes: list[int] = []
        for item in result["results"]:
            if not isinstance(item, Mapping) or item.get("objectType") != "work_item":
                prepared_results.append(item)
                continue
            read_input = item.get("workItemReadInput")
            if (
                isinstance(read_input, Mapping)
                and set(read_input) == {"project_id", "issue_id"}
                and target_issue_id is not None
                and read_input.get("issue_id") == target_issue_id
            ):
                matching_inputs.append(read_input)
                matching_result_indexes.append(len(prepared_results))
            prepared_item = {
                key: value
                for key, value in item.items()
                if key not in {"workItemReadInput", "workItemReadCall"}
            }
            prepared_results.append(prepared_item)

        recognized_count = min(len(matching_inputs), 2)
        if len(matching_inputs) == 1:
            prepared_ref = self._register_prepared_call(matching_inputs[0])
            prepared_results[matching_result_indexes[0]] = {
                **prepared_results[matching_result_indexes[0]],
                "workItemReadCall": prepared_ref,
            }
            prepared_result = {
                **result,
                "results": prepared_results,
                "assignmentWorkItemReadCall": prepared_ref,
                "assignmentWorkItemReadDecision": {
                    "schemaVersion": "plane.assignment-read-handoff/v1",
                    "recognizedCount": 1,
                    "acceptedForm": "canonical_ref",
                    "failureClass": "none",
                    "shape": {"nestingDepth": 0, "sizeClass": "small"},
                },
            }
        else:
            failure_class = (
                "invalid"
                if target_issue_id is None
                else "multiple"
                if len(matching_inputs) > 1
                else "zero"
            )
            prepared_result = {
                **result,
                "results": prepared_results,
                "assignmentWorkItemReadDecision": {
                    "schemaVersion": "plane.assignment-read-handoff/v1",
                    "recognizedCount": recognized_count,
                    "acceptedForm": "unrecognized",
                    "failureClass": failure_class,
                    "shape": {
                        "nestingDepth": 0,
                        "sizeClass": "large" if failure_class in {"multiple", "invalid"} else "small",
                    },
                },
            }
        if len(matching_inputs) == 1 or _assignment_read_decision_requires_followup(
            {"result": prepared_result}
        ):
            with self._prepared_calls_lock:
                self._prepared_read_handoff_pending = True
        return {**receipt, "result": prepared_result}


    def _prepared_read_handoff_is_pending(self) -> bool:
        with self._prepared_calls_lock:
            return self._prepared_read_handoff_pending and self._prepared_call_registry.has_unconsumed()

    def _register_prepared_call(self, read_input: Mapping[str, Any]) -> str:
        return self._prepared_call_registry.register(read_input)

    def _resolve_prepared_read_input(self, input_data: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._prepared_call_registry.resolve(input_data)

    def _normalize_prepared_read_input(self, input_data: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._prepared_call_registry.normalize(input_data)

    def _bind_or_replay_prepared_call(
        self, call: PlaneHostCall, prepared_ref: str
    ) -> PlaneHostResult | None:
        with self._prepared_calls_lock:
            record = self._prepared_calls.get(prepared_ref)
            if record is None:
                raise PreparedCallInvalid("unknown")
            correlation_id = record["correlation_id"]
            idempotency_key = record["idempotency_key"]
            if correlation_id is None:
                record["correlation_id"] = call.correlation_id
                record["idempotency_key"] = call.idempotency_key
                return None
            if correlation_id != call.correlation_id or idempotency_key != call.idempotency_key:
                raise PreparedCallInvalid("consumed" if record["consumed"] else "binding_mismatch")
            cached = record["result"]
        if cached is None:
            return None
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=cached.status if cached.status != "ok" else "replayed",
            replayed=True,
            output=cached.output,
            error_code=cached.error_code,
            error_message=cached.error_message,
            publication=cached.publication,
            prepared_call_invalid_reason=cached.prepared_call_invalid_reason,
        )

    def _publish(self, call: PlaneHostCall) -> PlaneHostResult:
        if call.input.get("kind") != "outcome":
            return self._error(
                call,
                "OPERATION_UNAVAILABLE",
                "Only explicit outcome publication is available in this Plane runtime",
            )
        if call.operation_ref != "operation:agent.outcome.publish":
            return self._error(call, "VALIDATION_ERROR", "Outcome publication operation is invalid")
        resource_ref = call.input.get("resourceRef")
        content = call.input.get("content")
        if (
            not isinstance(resource_ref, str)
            or not resource_ref.startswith("outcome-submission:")
            or not isinstance(content, str)
            or not content
            or len(content.encode("utf-8")) > MAX_HOST_CONTENT_BYTES
        ):
            return self._error(call, "VALIDATION_ERROR", "Outcome publication input is invalid")
        receipt = self._host.call_operation(
            "agent.outcome.publish",
            {"run_ref": self._run_ref, "outcome_ref": resource_ref, "content": content},
            idempotency_key=call.idempotency_key,
            correlation_id=call.correlation_id,
        )
        result = self._from_receipt(call, receipt)
        if not receipt.get("ok"):
            return result
        try:
            publication = (
                None
                if result.replayed
                else _applied_outcome_publication_from_receipt(
                    receipt,
                    resource_ref=resource_ref,
                    run_ref=self._run_ref,
                    invocation_ref=self._invocation_ref,
                )
            )
        except _PublicationReceiptInvalid as exc:
            return self._publication_receipt_error(call, receipt, exc.reason)
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=result.status,
            replayed=result.replayed,
            output=result.output,
            # A gateway replay carries the original product result for
            # auditability, but it is not a second applied publication.
            publication=None if result.replayed else publication,
        )

    @staticmethod
    def _publication_receipt_diagnostic(receipt: Mapping[str, Any], reason: str) -> dict[str, str]:
        """Keep only bounded receipt metadata when success is not applied proof."""

        def bounded(value: Any) -> str:
            try:
                return _publication_ref(value, "diagnostic")
            except _PublicationReceiptInvalid:
                return "unavailable"

        return {
            "publicationFailure": reason,
            "requestId": bounded(receipt.get("requestId")),
            "gatewayReceipt": bounded(receipt.get("gatewayReceipt")),
            "auditReceipt": bounded(receipt.get("auditReceipt")),
        }

    def _publication_receipt_error(
        self, call: PlaneHostCall, receipt: Mapping[str, Any], reason: str
    ) -> PlaneHostResult:
        return self._error(
            call,
            "OPERATION_UNAVAILABLE",
            "Outcome publication receipt did not prove an applied publication",
            output=self._publication_receipt_diagnostic(receipt, reason),
        )

    @staticmethod
    def _from_receipt(call: PlaneHostCall, receipt: Mapping[str, Any]) -> PlaneHostResult:
        if receipt.get("ok"):
            replayed = bool(receipt.get("replayed", False))
            output = dict(receipt)
            if call.operation_ref == "operation:catalog.describe":
                nested_result = receipt.get("result")
                if isinstance(nested_result, Mapping) and isinstance(nested_result.get("operation"), Mapping):
                    # Hermes' progressive disclosure seam consumes the
                    # described operation from the host output. Preserve the
                    # canonical gateway receipt while projecting that bounded
                    # operation object at the adapter boundary.
                    output["operation"] = _model_catalog_operation(nested_result["operation"])
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="replayed" if replayed else "ok",
                replayed=replayed,
                output=output,
            )
        error = receipt.get("error", {})
        code = error.get("code", "HOST_UNAVAILABLE") if isinstance(error, Mapping) else "HOST_UNAVAILABLE"
        message = (
            error.get("message", "Plane host rejected the callback")
            if isinstance(error, Mapping)
            else "Plane host rejected the callback"
        )
        status = (
            "denied"
            if code in {"NOT_AUTHORIZED", "CALLBACK_BINDING_INVALID", "BUDGET_EXCEEDED", "CANCELLED"}
            else "conflict"
            if code in {"IDEMPOTENCY_CONFLICT", "PLANE_CONFLICT"}
            else "unavailable"
            if code in {"UPSTREAM_FAILURE", "OPERATION_UNAVAILABLE", "OUTCOME_UNKNOWN"}
            else "invalid"
        )
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=status,
            replayed=False,
            output=dict(receipt),
            error_code=str(code),
            error_message=str(message)[:2048],
        )

    @staticmethod
    def _error(
        call: PlaneHostCall,
        code: str,
        message: str,
        *,
        output: Any = None,
        prepared_call_invalid_reason: str | None = None,
    ) -> PlaneHostResult:
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=(
                "invalid"
                if code in {
                    "VALIDATION_ERROR",
                    "SOURCE_TOO_LARGE",
                    "PROTOCOL_ERROR",
                    "PREPARED_CALL_INVALID",
                    # A generated module can fail inside the restricted
                    # isolate. Keep that bounded model correction result
                    # distinct from transport, protocol, and host failures.
                    "CODE_MODE_FAILED",
                }
                else "denied"
                if code in {"BUDGET_EXCEEDED", "CANCELLED", "NOT_AUTHORIZED"}
                else "denied"
                if code == "CALLBACK_BINDING_INVALID"
                else "unavailable"
            ),
            replayed=False,
            output=output,
            error_code=code,
            error_message=message,
            prepared_call_invalid_reason=prepared_call_invalid_reason,
        )


def _issue_id_from_assignment_target(target_ref: Any) -> str | None:
    if not isinstance(target_ref, str) or not target_ref.startswith("target:"):
        return None
    value = target_ref.removeprefix("target:")
    if value.startswith("literal-"):
        try:
            value = bytes.fromhex(value.removeprefix("literal-")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    if not value.startswith("issue:"):
        return None
    issue_id = value.removeprefix("issue:")
    return issue_id or None


def trusted_host_request(invocation: Any) -> Any:
    """Create the host request from the durable actor, never from child input."""

    from plane.db.models import RuntimeInvocation

    stored = RuntimeInvocation.objects.select_related("run__actor__principal").get(pk=invocation.pk)
    snapshot = stored.run.snapshot
    return SimpleNamespace(
        user=stored.run.actor.principal,
        META={},
        agent_actor_ref=snapshot["actorRef"],
        agent_workspace_ref=snapshot["workspaceRef"],
    )


def build_gateway_host_port(
    *,
    invocation: Any,
    gateway: Any,
    is_cancelled: Callable[[], bool] | None = None,
    provider_attempt_recorder: Callable[[PlaneHostCall], Mapping[str, Any]] | None = None,
) -> PlaneGatewayHostPort:
    """Build the trusted gateway-backed port for one persisted invocation."""

    from plane.agent.code_mode.host import CodeModeHostRPC

    if is_cancelled is None:
        from .supervisor import runtime_invocation_cancelled

        def is_cancelled():
            return runtime_invocation_cancelled(invocation.pk)

    host = CodeModeHostRPC.from_invocation(
        gateway=gateway,
        request=trusted_host_request(invocation),
        invocation=invocation,
        is_cancelled=is_cancelled,
    )
    return PlaneGatewayHostPort(host, provider_attempt_recorder=provider_attempt_recorder)


__all__ = [
    "HOST_PROTOCOL",
    "MAX_HOST_CALLS",
    "MAX_HOST_OBSERVATION_CALLS",
    "MAX_HOST_CONTENT_BYTES",
    "MAX_HOST_INPUT_BYTES",
    "MAX_HOST_OPERATION_REF_BYTES",
    "MAX_HOST_REQUEST_BYTES",
    "MAX_HOST_RESULT_BYTES",
    "MAX_PREPARED_CALL_REF_BYTES",
    "MAX_PREPARED_CALLS",
    "MAX_PROVIDER_ATTEMPT_NOTICES_PER_SEQUENCE",
    "MAX_PROVIDER_ATTEMPT_SEQUENCE",
    "HOST_HTTP_PATH",
    "PREPARED_CALL_PREFIX",
    "PlaneHostHTTPClient",
    "PlaneHostHTTPServer",
    "PlaneHostCall",
    "PlaneHostRPCError",
    "PlaneHostResult",
    "PlaneHostServer",
    "PlaneGatewayHostPort",
    "build_gateway_host_port",
    "trusted_host_request",
]

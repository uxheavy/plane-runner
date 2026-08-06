"""Invocation-scoped Plane host RPC for the separate Hermes process.

The wire contract mirrors the Hermes ``PlaneHostPort`` seam without importing
Hermes.  The endpoint is a one-invocation Unix-domain socket.  It carries
canonical JSON lines only; identity, authorization, idempotency, and product
publication remain Plane-owned.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from plane.operation_gateway.contracts import MAX_RESULT_BYTES

HOST_PROTOCOL = "plane.agent-runtime/v1"
PLANE_DISCOVERY_OPERATION = "plane.operations.discover@1"
MAX_HOST_REQUEST_BYTES = 16 * 1024
# The host carries the public operation result and cannot widen its contract.
MAX_HOST_RESULT_BYTES = MAX_RESULT_BYTES
MAX_HOST_INPUT_BYTES = 8 * 1024
MAX_HOST_CALLS = 32
MAX_HOST_OPERATION_REF_BYTES = 256
MAX_HOST_CONTENT_BYTES = 4 * 1024
_ACTIONS = {"discover", "read", "mutate", "code", "publish"}
_SOURCES = {"model", "code"}
_RESULT_STATUSES = {"ok", "replayed", "denied", "conflict", "unavailable", "invalid"}


class PlaneHostRPCError(ValueError):
    """A malformed, unavailable, or rejected Plane host callback."""


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


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value, "host request")).hexdigest()


def _duplicate_rejecting_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise json.JSONDecodeError("duplicate object key", "", 0)
        result[key] = value
    return result


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
        if action != "code" and source != "model":
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


class PlaneHostServer:
    """Serve one invocation's host callbacks over a local Unix socket."""

    def __init__(
        self,
        *,
        socket_path: str | os.PathLike[str],
        invoke: Callable[[PlaneHostCall], PlaneHostResult],
        max_calls: int = MAX_HOST_CALLS,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not callable(invoke):
            raise TypeError("invoke must be callable")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
            raise ValueError("max_calls must be a positive integer")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute():
            raise ValueError("socket_path must be absolute")
        self._invoke = invoke
        self._max_calls = max_calls
        self._timeout_seconds = float(timeout_seconds)
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._error: BaseException | None = None
        self._records: dict[str, PlaneHostResult] = {}
        self._call_count = 0
        self._lock = threading.RLock()

    @property
    def error(self) -> BaseException | None:
        return self._error

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

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
                return
            with connection:
                connection.settimeout(self._timeout_seconds)
                carry = bytearray()
                try:
                    line = self._read_line(connection, carry)
                except (OSError, PlaneHostRPCError):
                    continue
                if line is None:
                    continue
                try:
                    call = PlaneHostCall.from_wire(line)
                    result = self._invoke_once(call)
                    _bounded(result.to_wire(), "host.result", MAX_HOST_RESULT_BYTES)
                    response = result.to_wire()
                except PlaneHostRPCError:
                    continue
                except Exception:
                    # Never expose application/provider diagnostics over the
                    # host socket. The Hermes client observes peer failure.
                    continue
                try:
                    encoded = _canonical(response, "host.result") + b"\n"
                    connection.sendall(encoded)
                except OSError:
                    continue

    def _invoke_once(self, call: PlaneHostCall) -> PlaneHostResult:
        with self._lock:
            replay = self._records.get(call.request_ref)
            if replay is not None:
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
                    publication=replay.publication,
                )
            if self._call_count >= self._max_calls:
                return PlaneHostResult(
                    request_ref=call.request_ref,
                    correlation_id=call.correlation_id,
                    idempotency_key=call.idempotency_key,
                    status="denied",
                    replayed=False,
                    output=None,
                    error_code="HOST_BUDGET_EXCEEDED",
                    error_message="Plane host callback budget exhausted",
                )
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
            raise
        except Exception as exc:
            raise PlaneHostRPCError("host callback is unavailable") from exc
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


class PlaneGatewayHostPort:
    """Bind host callbacks to one trusted invocation and the live gateway."""

    def __init__(self, host: Any) -> None:
        if not callable(getattr(host, "call_operation", None)):
            raise TypeError("host must be a CodeModeHostRPC")
        self._host = host
        self._run_ref = host.binding.run_ref
        self._invocation_ref = host.binding.invocation_ref

    def invoke(self, call: PlaneHostCall) -> PlaneHostResult:
        if call.run_id != self._run_ref or call.invocation_id != self._invocation_ref:
            return self._error(call, "CALLBACK_BINDING_INVALID", "Host callback is not bound to this invocation")
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
            return self._from_receipt(call, receipt)
        if call.action == "publish":
            return self._publish(call)
        if not call.operation_ref.startswith("operation:"):
            return self._error(call, "VALIDATION_ERROR", "Plane operationRef is invalid")
        operation_id = call.operation_ref.removeprefix("operation:")
        receipt = self._host.call_operation(
            operation_id,
            call.input,
            idempotency_key=call.idempotency_key,
            correlation_id=call.correlation_id,
        )
        return self._from_receipt(call, receipt)

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
        outcome = receipt.get("result", {}).get("outcome", {})
        try:
            product_event_ref = outcome["productEventRef"]
            gateway_receipt = receipt["gatewayReceipt"]
            request_id = receipt["requestId"]
            audit_receipt = receipt["auditReceipt"]
            publication = {
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
        except (KeyError, TypeError):
            return self._error(call, "OPERATION_UNAVAILABLE", "Outcome publication receipt is incomplete")
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=result.status,
            replayed=result.replayed,
            output=result.output,
            publication=publication,
        )

    @staticmethod
    def _from_receipt(call: PlaneHostCall, receipt: Mapping[str, Any]) -> PlaneHostResult:
        if receipt.get("ok"):
            replayed = bool(receipt.get("replayed", False))
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="replayed" if replayed else "ok",
                replayed=replayed,
                output=dict(receipt),
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
    def _error(call: PlaneHostCall, code: str, message: str) -> PlaneHostResult:
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status=(
                "invalid"
                if code == "VALIDATION_ERROR"
                else "denied"
                if code == "CALLBACK_BINDING_INVALID"
                else "unavailable"
            ),
            replayed=False,
            output=None,
            error_code=code,
            error_message=message,
        )


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
    *, invocation: Any, gateway: Any, is_cancelled: Callable[[], bool] | None = None
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
    return PlaneGatewayHostPort(host)


__all__ = [
    "HOST_PROTOCOL",
    "MAX_HOST_CALLS",
    "MAX_HOST_CONTENT_BYTES",
    "MAX_HOST_INPUT_BYTES",
    "MAX_HOST_OPERATION_REF_BYTES",
    "MAX_HOST_REQUEST_BYTES",
    "MAX_HOST_RESULT_BYTES",
    "PlaneHostCall",
    "PlaneHostRPCError",
    "PlaneHostResult",
    "PlaneHostServer",
    "PlaneGatewayHostPort",
    "build_gateway_host_port",
    "trusted_host_request",
]

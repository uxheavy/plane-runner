# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Authenticated, bounded HTTP transport to the separate Agent runtime."""

from __future__ import annotations

import hashlib
import http.client
import json
import urllib.parse
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Mapping

from .contracts import RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE, RuntimeDispatchError, RuntimeTransport
from .credentials import RuntimeCredentialBroker, RuntimeCredentialError, credential_failure_subreason


RUNTIME_DISPATCH_PROTOCOL = "plane.agent-runtime/dispatch/v1"
MAX_REMOTE_REQUEST_BYTES = 2 * 1024 * 1024
MAX_REMOTE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REMOTE_FRAMES = 512
MAX_REMOTE_FRAME_BYTES = 512 * 1024


@dataclass(frozen=True)
class RuntimeHostEndpoint:
    """Invocation-scoped endpoint and token for trusted Plane callbacks."""

    url: str
    token: str


def _canonical(value: Any, name: str) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeDispatchError(f"{name} is not JSON-compatible") from exc


def _canonical_object(value: str, name: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise RuntimeDispatchError(f"{name} must be serialized JSON text")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeDispatchError(f"{name} is not valid JSON") from exc
    if not isinstance(parsed, dict) or _canonical(parsed, name) != value.encode("utf-8"):
        raise RuntimeDispatchError(f"{name} must be canonical JSON")
    return parsed


def _request_digest(snapshot_json: str, envelope_json: str) -> str:
    return hashlib.sha256(
        b"plane.agent-runtime/dispatch/v1\n" + snapshot_json.encode("utf-8") + b"\n" + envelope_json.encode("utf-8")
    ).hexdigest()


def _structured_rejection(body: bytes) -> RuntimeDispatchError | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError):
        return None
    required = {
        "error",
        "failureCode",
        "failurePhase",
        "failureDetail",
    }
    optional = {"failureSubreason", "childDiagnostic", "hostOperationFailure"}
    if not isinstance(value, dict) or not required.issubset(value) or set(value).difference(required | optional):
        return None
    if value.get("error") != "runtime_dispatch_failed":
        return None
    fields = {key: value.get(key) for key in ("failureCode", "failurePhase", "failureDetail")}
    if not all(isinstance(item, str) for item in fields.values()):
        return None
    failure_subreason = value.get("failureSubreason")
    if failure_subreason is not None and not isinstance(failure_subreason, str):
        return None
    child_diagnostic = value.get("childDiagnostic")
    if child_diagnostic is not None and not isinstance(child_diagnostic, dict):
        return None
    host_operation_failure = value.get("hostOperationFailure")
    if host_operation_failure is not None and not isinstance(host_operation_failure, dict):
        return None
    if _canonical(value, "runtime rejection") != body:
        return None
    if failure_subreason is None and fields == {
        "failureCode": RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
    }:
        # The pinned runtime service predates failureSubreason propagation.
        # Its redacted response is still safe to classify at this authenticated
        # HTTP seam, so the Plane supervisor can persist a bounded reason.
        failure_subreason = "runtime_configuration_rejected"
    error = RuntimeDispatchError(
        "runtime dispatch was rejected",
        failure_code=fields["failureCode"],
        failure_phase=fields["failurePhase"],
        failure_detail=fields["failureDetail"],
        failure_subreason=failure_subreason,
        child_diagnostic=child_diagnostic,
        host_operation_failure=host_operation_failure,
    )
    if child_diagnostic is not None and error.child_diagnostic is None:
        return None
    if host_operation_failure is not None and error.host_operation_failure is None:
        return None
    return error


class RemoteRuntimeTransport(RuntimeTransport):
    """Send one immutable Plane snapshot/envelope across the runtime seam."""

    def __init__(
        self,
        *,
        runtime_url: str,
        shared_secret: str,
        dispatch_path: str = "/v1/runtime/dispatch",
        timeout_seconds: float = 300.0,
        max_request_bytes: int = MAX_REMOTE_REQUEST_BYTES,
        max_response_bytes: int = MAX_REMOTE_RESPONSE_BYTES,
        host_endpoint_factory: Callable[[str], ContextManager[RuntimeHostEndpoint]] | None = None,
        credential_broker: RuntimeCredentialBroker | None = None,
        credential_ref: str = "runtime",
        model_call_allowance: int | None = None,
    ) -> None:
        self._base_url = self._validate_url(runtime_url, "runtime URL")
        if urllib.parse.urlsplit(self._base_url).path not in {"", "/"}:
            raise ValueError("runtime URL is invalid")
        self._shared_secret = self._text(shared_secret, "runtime shared secret", 4096)
        self._dispatch_path = self._validate_path(dispatch_path)
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("runtime timeout must be positive")
        if (
            isinstance(max_request_bytes, bool)
            or not isinstance(max_request_bytes, int)
            or not 0 < max_request_bytes <= MAX_REMOTE_REQUEST_BYTES
        ):
            raise ValueError("runtime request bound is invalid")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 0 < max_response_bytes <= MAX_REMOTE_RESPONSE_BYTES
        ):
            raise ValueError("runtime response bound is invalid")
        if model_call_allowance is not None and (
            isinstance(model_call_allowance, bool)
            or not isinstance(model_call_allowance, int)
            or not 0 <= model_call_allowance <= 4096
        ):
            raise ValueError("model-call allowance is invalid")
        self._timeout_seconds = float(timeout_seconds)
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes
        self._host_endpoint_factory = host_endpoint_factory
        self._credential_broker = credential_broker
        self._credential_ref = self._text(credential_ref, "credential reference", 256)
        self._model_call_allowance = model_call_allowance

    def dispatch(self, snapshot_json: str, envelope_json: str) -> tuple[str, ...]:
        snapshot = _canonical_object(snapshot_json, "runtime snapshot")
        envelope = _canonical_object(envelope_json, "runtime invocation")
        run_id = snapshot.get("runId")
        invocation_id = envelope.get("invocationId")
        actor_ref = snapshot.get("actorRef")
        if not isinstance(run_id, str) or not run_id or not isinstance(invocation_id, str) or not invocation_id:
            raise RuntimeDispatchError("runtime dispatch identity is invalid")
        if envelope.get("runId") != run_id or not isinstance(actor_ref, str) or not actor_ref:
            raise RuntimeDispatchError("runtime dispatch binding is invalid")
        digest = _request_digest(snapshot_json, envelope_json)
        host_context: ContextManager[RuntimeHostEndpoint]
        if self._host_endpoint_factory is None:
            host_context = nullcontext(None)
        else:
            host_context = self._host_endpoint_factory(invocation_id)
        lease_id: str | None = None
        lease_metadata: dict[str, object] | None = None
        credentials: Mapping[str, str] = {}
        try:
            if self._credential_broker is not None:
                try:
                    lease, values = self._credential_broker.issue(
                        agent_ref=actor_ref,
                        credential_ref=self._credential_ref,
                        invocation_ref=invocation_id,
                    )
                except RuntimeCredentialError as exc:
                    raise RuntimeDispatchError(
                        "runtime credential lease rejected dispatch",
                        failure_code=RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
                        failure_phase="runtime_configuration",
                        failure_detail="dispatch_rejected",
                        failure_subreason=credential_failure_subreason(exc),
                    ) from exc
                lease_id = lease.lease_id
                lease_metadata = lease.public_metadata()
                credentials = values
            with host_context as host:
                if host is not None:
                    if not isinstance(host, RuntimeHostEndpoint):
                        raise RuntimeDispatchError("runtime host endpoint is invalid")
                    host_wire = {
                        "url": self._validate_url(host.url, "host URL"),
                        "token": self._text(host.token, "host token", 4096),
                    }
                else:
                    host_wire = None
                body: dict[str, Any] = {
                    "protocol": RUNTIME_DISPATCH_PROTOCOL,
                    "requestDigest": digest,
                    "runId": run_id,
                    "invocationId": invocation_id,
                    "snapshot": snapshot,
                    "invocation": envelope,
                    "credentials": dict(credentials),
                }
                if lease_metadata is not None:
                    body["credentialLease"] = lease_metadata
                if host_wire is not None:
                    body["host"] = host_wire
                if self._model_call_allowance is not None:
                    body["modelCallAllowance"] = self._model_call_allowance
                payload = _canonical(body, "runtime dispatch request")
                if len(payload) > self._max_request_bytes:
                    raise RuntimeDispatchError("runtime dispatch request exceeds its size bound")
                response = self._post(payload)
                return self._decode_response(response, digest, run_id, invocation_id)
        finally:
            if lease_id is not None and self._credential_broker is not None:
                self._credential_broker.revoke_lease_id(lease_id)

    def _post(self, payload: bytes) -> bytes:
        parsed = urllib.parse.urlsplit(self._base_url)
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=self._timeout_seconds)
        path = self._dispatch_path
        try:
            connection.request(
                "POST",
                path,
                body=payload,
                headers={
                    "Authorization": f"Bearer {self._shared_secret}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            body = response.read(self._max_response_bytes + 1)
            if len(body) > self._max_response_bytes:
                raise RuntimeDispatchError("runtime dispatch response exceeds its size bound")
            if response.status != 200:
                raise (_structured_rejection(body) or RuntimeDispatchError("runtime dispatch was rejected"))
            return body
        except RuntimeDispatchError:
            raise
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise RuntimeDispatchError("runtime dispatch is unavailable") from exc
        finally:
            connection.close()

    def _decode_response(self, raw: bytes, digest: str, run_id: str, invocation_id: str) -> tuple[str, ...]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise RuntimeDispatchError("runtime dispatch response is invalid") from exc
        if _canonical(value, "runtime dispatch response") != raw or not isinstance(value, dict):
            raise RuntimeDispatchError("runtime dispatch response is not canonical")
        if value.get("protocol") != RUNTIME_DISPATCH_PROTOCOL or value.get("requestDigest") != digest:
            raise RuntimeDispatchError("runtime dispatch response is not bound to the request")
        if value.get("runId") != run_id or value.get("invocationId") != invocation_id:
            raise RuntimeDispatchError("runtime dispatch response identity is invalid")
        frames = value.get("frames")
        if (
            not isinstance(frames, list)
            or len(frames) > MAX_REMOTE_FRAMES
            or any(
                not isinstance(frame, str) or not frame or len(frame.encode("utf-8")) > MAX_REMOTE_FRAME_BYTES
                for frame in frames
            )
        ):
            raise RuntimeDispatchError("runtime dispatch response frames are invalid")
        return tuple(frames)

    @staticmethod
    def _text(value: Any, name: str, maximum: int) -> str:
        if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > maximum:
            raise ValueError(f"{name} is invalid")
        return value

    @classmethod
    def _validate_url(cls, value: Any, name: str) -> str:
        raw = cls._text(value, name, 2048).rstrip("/")
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{name} is invalid")
        if parsed.query or parsed.fragment:
            raise ValueError(f"{name} is invalid")
        try:
            if parsed.port is not None and not 0 < parsed.port <= 65535:
                raise ValueError(f"{name} is invalid")
        except ValueError as exc:
            raise ValueError(f"{name} is invalid") from exc
        return raw

    @classmethod
    def _validate_path(cls, value: Any) -> str:
        path = cls._text(value, "runtime dispatch path", 128)
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("runtime dispatch path is invalid")
        return path


__all__ = ["MAX_REMOTE_REQUEST_BYTES", "RemoteRuntimeTransport", "RUNTIME_DISPATCH_PROTOCOL", "RuntimeHostEndpoint"]

"""Invocation-bound provider egress for the isolated Hermes child.

The child owns only an HTTP client whose transport is an invocation-local
AF_UNIX socket.  The trusted runtime owns the provider route, TLS connection,
credential lease, limits, audit outcome, and cleanup. This module is the
trusted-parent relay only; Hermes owns the child HTTP-client construction.
"""

from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import secrets
import socket
import socketserver
import ssl
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


PROVIDER_RELAY_PROTOCOL = "plane.agent-runtime/provider-relay/v1"
PROVIDER_RELAY_HOST = "plane-provider-relay.invalid"
GPT56_MODEL_RE = re.compile(r"^gpt-5\.6-(?:sol|terra|luna)(?:-pro)?$")
_MAX_SOCKET_PATH_BYTES = 103
_MAX_REQUEST_ID_BYTES = 256
_MAX_MODEL_BYTES = 256
_MAX_PROVIDER_BYTES = 64
_MAX_HOST_BYTES = 255
_MAX_PATH_BYTES = 1024
_MAX_HEADER_BYTES = 16 * 1024
_MAX_ERROR_BYTES = 256
_DEFAULT_REQUEST_BYTES = 256 * 1024
_DEFAULT_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_CHUNK_BYTES = 64 * 1024
_DEFAULT_TIMEOUT_SECONDS = 30.0
_RELAY_DRAIN_TIMEOUT_SECONDS = 2.0
_SAFE_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "cache-control",
        "content-type",
        "connection",
        # Hermes' Codex transport uses these non-secret request headers for
        # cache scoping and SDK request correlation.
        "session_id",
        "user-agent",
        "x-client-request-id",
    }
)
_RELAY_IDENTITY_HEADERS = frozenset(
    {
        "x-plane-relay-invocation",
        "x-plane-relay-model",
        "x-plane-relay-provider",
        "x-plane-relay-run",
    }
)
_SENSITIVE_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
    }
)
_PROVIDER_ERROR_STATUS_CLASSES = frozenset({"", "4xx", "5xx", "transport"})
_PROVIDER_ERROR_REASON_SUBREASONS = frozenset(
    {
        "",
        "request_rejected",
        "auth",
        "rate_limited",
        "upstream_unavailable",
        "upstream_exception",
        "upstream_channel_closed",
        "upstream_timeout",
        "channel_closed_after_upstream",
    }
)


class ProviderRelayError(ValueError):
    """A provider relay request cannot be admitted or safely completed."""

    status_class = ""
    reason_subreason = ""

    def __init__(self, message: str, *, status_class: str = "", reason_subreason: str = "") -> None:
        self.status_class = (
            status_class if isinstance(status_class, str) and status_class in _PROVIDER_ERROR_STATUS_CLASSES else ""
        )
        if (
            isinstance(reason_subreason, str)
            and reason_subreason in _PROVIDER_ERROR_REASON_SUBREASONS
            and reason_subreason
        ):
            self.reason_subreason = reason_subreason
        super().__init__(message)


class _ProviderRelayHTTPStatusError(ProviderRelayError):
    """A bounded upstream HTTP family is available without retaining response data."""

    def __init__(self, status_class: str, *, reason_subreason: str = "") -> None:
        super().__init__(
            "provider returned an unsuccessful status",
            status_class=status_class,
            reason_subreason=reason_subreason,
        )


class ProviderRelayOutcomeUnknownError(ProviderRelayError):
    """The provider request started, but its terminal result is ambiguous."""

    error_code = "outcome_unknown"
    retryable = False
    upstream_initiated = True
    status_class = "transport"

    def __init__(self, *, reason_subreason: str = "upstream_exception") -> None:
        if reason_subreason not in {
            "upstream_exception",
            "upstream_channel_closed",
            "upstream_timeout",
        }:
            reason_subreason = "upstream_exception"
        self.reason_phase = "provider_relay"
        self.reason_subreason = reason_subreason
        super().__init__(
            "provider request outcome is unknown",
            status_class="transport",
            reason_subreason=reason_subreason,
        )


@dataclass(frozen=True)
class ProviderWire:
    """The typed provider wire contract shared by runtime config and relay."""

    host: str
    path: str
    credential_name: str = "api_key"


_PROVIDER_WIRES = {
    "openai-codex": ProviderWire(
        host="chatgpt.com",
        path="/backend-api/codex/responses",
    ),
    "xai": ProviderWire(
        host="api.x.ai",
        path="/v1/chat/completions",
    ),
}


def provider_wire(provider: str) -> ProviderWire | None:
    """Return the canonical wire contract for a known provider."""

    return _PROVIDER_WIRES.get(provider)


@dataclass(frozen=True)
class ProviderRelayBinding:
    run_id: str
    invocation_id: str
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderRelayPolicy:
    provider: str
    host: str
    path: str
    models: tuple[str, ...]
    method: str = "POST"
    credential_name: str = "api_key"
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_request_bytes: int = _DEFAULT_REQUEST_BYTES
    max_response_bytes: int = _DEFAULT_RESPONSE_BYTES
    max_chunk_bytes: int = _DEFAULT_CHUNK_BYTES
    max_calls: int = 16
    max_concurrent_requests: int = 2

    def __post_init__(self) -> None:
        _bounded_text(self.provider, "provider", _MAX_PROVIDER_BYTES)
        _bounded_text(self.host, "provider host", _MAX_HOST_BYTES)
        _bounded_text(self.path, "provider path", _MAX_PATH_BYTES)
        if not self.path.startswith("/") or "?" in self.path or "#" in self.path:
            raise ProviderRelayError("provider path is invalid")
        if self.method != "POST":
            raise ProviderRelayError("provider method is not permitted")
        wire = provider_wire(self.provider)
        if wire is not None and (
            self.host != wire.host
            or self.path != wire.path
            or self.credential_name != wire.credential_name
        ):
            raise ProviderRelayError("provider wire contract is not pinned")
        _bounded_text(self.credential_name, "credential name", 128)
        if not self.models or any(not isinstance(model, str) or not model for model in self.models):
            raise ProviderRelayError("provider model allowlist is empty or invalid")
        for model in self.models:
            _bounded_text(model, "provider model", _MAX_MODEL_BYTES)
        if self.provider == "openai-codex" and any(not GPT56_MODEL_RE.fullmatch(model) for model in self.models):
            raise ProviderRelayError("Plane Agent provider models must remain within the GPT-5.6 family")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 300
        ):
            raise ProviderRelayError("provider timeout is invalid")
        for value, name, maximum in (
            (self.max_request_bytes, "provider request bytes", 2 * 1024 * 1024),
            (self.max_response_bytes, "provider response bytes", 16 * 1024 * 1024),
            (self.max_chunk_bytes, "provider chunk bytes", 2 * 1024 * 1024),
            (self.max_calls, "provider model-call budget", 256),
            (self.max_concurrent_requests, "provider concurrency", 32),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
                raise ProviderRelayError(f"{name} is invalid")


@dataclass(frozen=True)
class ProviderRelayDescriptor:
    """The parent-created socket/token descriptor handed to Hermes bootstrap."""

    socket_path: Path
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        path = Path(self.socket_path)
        if not path.is_absolute():
            raise ProviderRelayError("provider relay socket path must be absolute")
        if len(os.fsencode(str(path))) > _MAX_SOCKET_PATH_BYTES:
            raise ProviderRelayError("provider relay socket path is too long")
        if not isinstance(self.token, str) or len(self.token.encode("utf-8")) < 32:
            raise ProviderRelayError("provider relay token is invalid")

    def __repr__(self) -> str:
        return f"ProviderRelayDescriptor(socket_path={self.socket_path!r}, token=<redacted>)"


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    model: str
    method: str
    host: str
    path: str
    headers: Mapping[str, str]
    body: bytes
    request_id: str = ""
    sequence: int = 0


class _ProviderRelayAdmissionError(ProviderRelayError):
    """A bounded request descriptor was available when admission failed."""

    def __init__(self, message: str, request: ProviderRequest) -> None:
        super().__init__(message)
        self.request = request


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    headers: Mapping[str, str]
    body_chunks: Iterable[bytes]


@dataclass(frozen=True)
class ProviderRelayAudit:
    run_id: str
    invocation_id: str
    provider: str
    model: str
    outcome: str
    reason: str
    upstream_called: bool
    phase: str = "terminal"
    request_id: str = ""
    lease_id: str = ""
    destination_host: str = ""
    destination_path: str = ""
    sequence: int = 0
    status_class: str = ""
    error_code: str = ""
    reason_phase: str = ""
    reason_subreason: str = ""
    event_ref: str = ""


@dataclass(frozen=True)
class ProviderRelayAuditFailure:
    """Bounded parent-visible state for a required audit rejection."""

    phase: str
    code: str = "provider_attempt_evidence_rejected"


class ProviderUpstream(Protocol):
    def __call__(
        self,
        request: ProviderRequest,
        credentials: dict[str, str],
        is_cancelled: Callable[[], bool],
    ) -> ProviderResponse: ...


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProviderRelayError(f"{name} is invalid")
    if len(value.encode("utf-8")) > maximum or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ProviderRelayError(f"{name} is invalid")
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(value)


def _safe_reason(value: str) -> str:
    value = value.strip().replace("\n", " ")
    return value[:_MAX_ERROR_BYTES] or "relay_denied"


def _credential_shaped_name(value: str) -> bool:
    normalized = value.casefold().replace("-", "_")
    return (
        normalized in _SENSITIVE_NAMES
        or normalized.endswith("_token")
        or any(part in normalized for part in ("api_key", "secret", "password"))
    )


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _credential_shaped_name(key):
                return True
            if _contains_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _relay_bootstrap_payload(descriptor: ProviderRelayDescriptor, policy: ProviderRelayPolicy) -> dict[str, str]:
    """Create the exact non-secret relay fields consumed by Hermes G1."""

    value: dict[str, str] = {
        "host": policy.host,
        "invocationSocket": str(descriptor.socket_path),
        "path": policy.path,
        "provider": policy.provider,
        "relayToken": descriptor.token,
    }
    if set(value) != {"host", "invocationSocket", "path", "provider", "relayToken"}:
        raise ProviderRelayError("provider relay bootstrap fields are invalid")
    return value


class _RelayHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, socket_path: str, relay: "ProviderRelayServer") -> None:
        self.relay = relay
        super().__init__(socket_path, _ProviderRelayHTTPHandler)


class _ProviderRelayHTTPHandler(socketserver.StreamRequestHandler):
    server: _RelayHTTPServer

    def setup(self) -> None:
        super().setup()
        self.server.relay._register_channel(self.connection)

    def finish(self) -> None:
        self.server.relay._unregister_channel(self.connection)
        super().finish()

    def handle(self) -> None:
        relay = self.server.relay
        request_id = ""
        request: ProviderRequest | None = None
        upstream_called = False
        upstream_result_buffered = False
        acquired = relay._request_slots.acquire(blocking=False)
        if not acquired:
            relay._write_http_error(self.wfile, "", "concurrency")
            return
        try:
            self.connection.settimeout(relay.policy.timeout_seconds)
            method, target, headers, body = self._read_request(relay)
            request_id = headers.get("x-request-id", "")
            relay._validate_request_id(request_id)
            request = relay._admit_http(method, target, headers, body, request_id)
            relay._record_attempt(request, phase="intent", upstream_initiated=False, required=True)
            relay._record_attempt(request, phase="started", upstream_initiated=True, required=True)
            upstream_called = True
            response = relay._call_upstream(request)
            upstream_result_buffered = True
            relay._record_attempt(
                request,
                phase="completed",
                upstream_initiated=True,
                status_class=relay._status_class(response.status_code),
            )
            relay._write_http_response(self.wfile, request_id, response)
        except ProviderRelayError as exc:
            error_for_audit: ProviderRelayError = exc
            if (
                request is not None
                and upstream_called
                and not upstream_result_buffered
                and relay._forced_close.is_set()
                and relay._error_code(exc) == "cancelled"
            ):
                error_for_audit = ProviderRelayOutcomeUnknownError(reason_subreason="upstream_channel_closed")
            code = relay._error_code(error_for_audit)
            if request is None and isinstance(error_for_audit, _ProviderRelayAdmissionError):
                request = error_for_audit.request
                relay._record_attempt(request, phase="intent", upstream_initiated=False, required=True)
            if request is not None and not upstream_result_buffered:
                terminal_phase = (
                    "outcome_unknown"
                    if upstream_called
                    and code == "outcome_unknown"
                    and getattr(error_for_audit, "upstream_initiated", False)
                    else "failed"
                )
                relay._record_attempt(
                    request,
                    phase=terminal_phase,
                    upstream_initiated=upstream_called,
                    status_class=(
                        getattr(error_for_audit, "status_class", "")
                        or (
                            "unknown"
                            if terminal_phase == "outcome_unknown"
                            else "not_sent"
                            if not upstream_called
                            else "error"
                        )
                    ),
                    error_code=code,
                    reason_phase=getattr(error_for_audit, "reason_phase", ""),
                    reason_subreason=getattr(error_for_audit, "reason_subreason", ""),
                )
                if terminal_phase == "outcome_unknown":
                    relay._record_attempt(
                        request,
                        phase="terminal",
                        upstream_initiated=True,
                        status_class=getattr(error_for_audit, "status_class", "transport"),
                        error_code=code,
                        reason_phase=getattr(error_for_audit, "reason_phase", ""),
                        reason_subreason=getattr(error_for_audit, "reason_subreason", ""),
                    )
            elif request is None and code != "replay":
                # A replay is a stable response for the already-recorded
                # attempt, not a new provider-attempt audit.  In particular,
                # do not let the identity fallback's default terminal phase
                # create a second terminal event for the same request.
                relay._record_identity(
                    {},
                    "denied",
                    relay._audit_reason(error_for_audit, code),
                    upstream_called,
                )
            try:
                relay._write_http_error(self.wfile, request_id, code, error=error_for_audit)
            except OSError:
                pass
        except (OSError, TimeoutError):
            if request is not None and not upstream_result_buffered:
                relay._record_attempt(
                    request,
                    phase="outcome_unknown" if upstream_called else "failed",
                    upstream_initiated=upstream_called,
                    status_class="transport" if upstream_called else "not_sent",
                    error_code="outcome_unknown" if upstream_called else "channel_closed",
                    reason_phase="provider_relay" if upstream_called else "",
                    reason_subreason=(
                        "channel_closed_after_upstream" if upstream_called else ""
                    ),
                )
                if upstream_called:
                    relay._record_attempt(
                        request,
                        phase="terminal",
                        upstream_initiated=True,
                        status_class="transport",
                        error_code="outcome_unknown",
                        reason_phase="provider_relay",
                        reason_subreason="channel_closed_after_upstream",
                    )
        finally:
            relay._request_slots.release()

    def _read_request(self, relay: "ProviderRelayServer") -> tuple[str, str, dict[str, str], bytes]:
        source = self.rfile
        request_line = source.readline(_MAX_HEADER_BYTES + 1)
        if not request_line or len(request_line) > _MAX_HEADER_BYTES or not request_line.endswith(b"\r\n"):
            raise ProviderRelayError("HTTP request line is invalid")
        try:
            method, target, version = request_line[:-2].decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProviderRelayError("HTTP request line is invalid") from exc
        if version != "HTTP/1.1":
            raise ProviderRelayError("HTTP version is not permitted")
        headers: dict[str, str] = {}
        header_bytes = len(request_line)
        while True:
            line = source.readline(_MAX_HEADER_BYTES + 1)
            header_bytes += len(line)
            if header_bytes > _MAX_HEADER_BYTES:
                raise ProviderRelayError("provider request headers are oversized")
            if line == b"\r\n":
                break
            if not line or not line.endswith(b"\r\n") or b":" not in line:
                raise ProviderRelayError("provider request headers are invalid")
            key_raw, value_raw = line[:-2].split(b":", 1)
            try:
                key = key_raw.decode("ascii").casefold()
                value = value_raw.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise ProviderRelayError("provider request headers are invalid") from exc
            if not key or key in headers or any(ord(char) < 0x20 for char in value):
                raise ProviderRelayError("provider request headers are invalid")
            headers[key] = value
        content_length = headers.get("content-length")
        if content_length is None:
            raise ProviderRelayError("provider request content length is required")
        try:
            length = int(content_length, 10)
        except ValueError as exc:
            raise ProviderRelayError("provider request content length is invalid") from exc
        if length <= 0 or length > relay._max_request_bytes:
            raise ProviderRelayError("provider request body is oversized")
        body = source.read(length)
        if len(body) != length:
            raise ProviderRelayError("provider request body is incomplete")
        return method, target, headers, body


class ProviderRelayServer:
    """Serve one invocation's provider relay until its parent closes it."""

    def __init__(
        self,
        *,
        socket_path: str | os.PathLike[str],
        binding: ProviderRelayBinding,
        policy: ProviderRelayPolicy,
        credentials: Mapping[str, str],
        upstream: ProviderUpstream,
        lease_validator: Callable[[], object] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        audit: Callable[[ProviderRelayAudit], None] | None = None,
        max_request_bytes: int | None = None,
        lease_id: str = "",
    ) -> None:
        self.binding = binding
        self.policy = policy
        self._socket_path = Path(socket_path)
        self._descriptor = ProviderRelayDescriptor(self._socket_path, secrets.token_urlsafe(32))
        _bounded_text(binding.run_id, "provider relay run", _MAX_REQUEST_ID_BYTES)
        _bounded_text(binding.invocation_id, "provider relay invocation", _MAX_REQUEST_ID_BYTES)
        if binding.provider != policy.provider or binding.model not in policy.models:
            raise ProviderRelayError("provider relay binding is outside the policy")
        if not isinstance(credentials, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, str) or not value for key, value in credentials.items()
        ):
            raise ProviderRelayError("provider relay credentials are invalid")
        if policy.credential_name not in credentials:
            raise ProviderRelayError("provider relay credential is unavailable")
        if len(credentials) > 16:
            raise ProviderRelayError("provider relay credentials are oversized")
        self._credentials = dict(credentials)
        self._upstream = upstream
        self._lease_validator = lease_validator
        self._is_cancelled = is_cancelled or (lambda: False)
        self._audit = audit
        self._lease_id = _bounded_text(lease_id, "provider lease id", 128) if lease_id else ""
        self._max_request_bytes = max_request_bytes if max_request_bytes is not None else policy.max_request_bytes
        if (
            isinstance(self._max_request_bytes, bool)
            or not isinstance(self._max_request_bytes, int)
            or self._max_request_bytes <= 0
            or self._max_request_bytes > policy.max_request_bytes
        ):
            raise ProviderRelayError("provider relay request bound is invalid")
        self._http_server: _RelayHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._forced_close = threading.Event()
        self._active: set[socket.socket] = set()
        self._active_lock = threading.RLock()
        self._seen_requests: set[str] = set()
        self._calls = 0
        self._request_lock = threading.RLock()
        self._required_audit_failure: ProviderRelayAuditFailure | None = None
        self._request_slots = threading.BoundedSemaphore(policy.max_concurrent_requests)

    @property
    def descriptor(self) -> ProviderRelayDescriptor:
        return self._descriptor

    @property
    def required_audit_failure(self) -> ProviderRelayAuditFailure | None:
        with self._request_lock:
            return self._required_audit_failure

    def start(self) -> ProviderRelayDescriptor:
        if self._http_server is not None:
            return self._descriptor
        self._socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(self._socket_path.parent, 0o700)
        except OSError:
            pass
        if self._socket_path.exists():
            if not self._socket_path.is_socket():
                raise ProviderRelayError("provider relay socket path is occupied")
            self._socket_path.unlink()
        try:
            server = _RelayHTTPServer(str(self._socket_path), self)
            os.chmod(self._socket_path, 0o600)
        except OSError as exc:
            raise ProviderRelayError("provider relay socket could not start") from exc
        self._http_server = server
        self._thread = threading.Thread(target=server.serve_forever, name="plane-provider-relay", daemon=True)
        self._thread.start()
        return self._descriptor

    def close(self) -> None:
        server = self._http_server
        self._http_server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=_RELAY_DRAIN_TIMEOUT_SECONDS)
        self._thread = None
        self._wait_for_active_handlers()
        with self._active_lock:
            active = tuple(self._active)
        if active:
            self._forced_close.set()
        self._closed.set()
        for channel in active:
            try:
                channel.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            channel.close()
        if active:
            self._wait_for_active_handlers()
        try:
            if self._socket_path.is_socket():
                self._socket_path.unlink()
        except OSError:
            pass
        self._credentials.clear()

    def _wait_for_active_handlers(self) -> None:
        deadline = time.monotonic() + _RELAY_DRAIN_TIMEOUT_SECONDS
        while True:
            with self._active_lock:
                if not self._active:
                    return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.01, remaining))

    def _register_channel(self, channel: socket.socket) -> None:
        with self._active_lock:
            self._active.add(channel)

    def _unregister_channel(self, channel: socket.socket) -> None:
        with self._active_lock:
            self._active.discard(channel)

    def _validate_request_id(self, request_id: str) -> None:
        _bounded_text(request_id, "request id", _MAX_REQUEST_ID_BYTES)

    def _admit_http(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str],
        raw_body: bytes,
        request_id: str,
    ) -> ProviderRequest:
        if method != self.policy.method:
            raise ProviderRelayError("provider method is invalid")
        if target != self.policy.path:
            raise ProviderRelayError("provider path is invalid")
        if headers.get("host") != PROVIDER_RELAY_HOST:
            raise ProviderRelayError("provider host is invalid")
        authorization = headers.get("authorization") or headers.get("x-api-key")
        expected = f"Bearer {self._descriptor.token}"
        if authorization is None or not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise ProviderRelayError("relay token is invalid")
        identity = {
            "x-plane-relay-run": self.binding.run_id,
            "x-plane-relay-invocation": self.binding.invocation_id,
            "x-plane-relay-provider": self.binding.provider,
            "x-plane-relay-model": self.binding.model,
        }
        for key, expected_value in identity.items():
            if headers.get(key) not in {None, expected_value}:
                label = key.removeprefix("x-plane-relay-")
                raise ProviderRelayError(f"relay {label} is invalid")
        for key, value in headers.items():
            if (
                key in {"host", "content-length", "authorization", "x-api-key", "x-request-id"}
                or key in _RELAY_IDENTITY_HEADERS
            ):
                continue
            if key not in _SAFE_REQUEST_HEADERS and not key.startswith("x-stainless-"):
                raise ProviderRelayError("provider request header is not permitted")
            if _credential_shaped_name(key) or any(ord(char) < 0x20 for char in value):
                raise ProviderRelayError("provider request contains credential-shaped data")
        if headers.get("content-type", "").casefold() != "application/json":
            raise ProviderRelayError("provider request content type is invalid")
        if headers.get("transfer-encoding") is not None:
            raise ProviderRelayError("provider request transfer encoding is not permitted")
        try:
            body = json.loads(raw_body.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise ProviderRelayError("provider request body is invalid") from exc
        if not isinstance(body, dict) or _contains_sensitive_key(body):
            raise ProviderRelayError("provider request contains credential-shaped data")
        if body.get("model") != self.binding.model:
            raise ProviderRelayError("provider request model is invalid")
        self._validate_lease_and_cancellation()
        with self._request_lock:
            request = ProviderRequest(
                provider=self.binding.provider,
                model=self.binding.model,
                method=self.policy.method,
                host=self.policy.host,
                path=self.policy.path,
                headers={key: value for key, value in headers.items() if key in {"accept", "user-agent"}},
                body=raw_body,
                request_id=request_id,
                sequence=self._calls + 1,
            )
            if request_id in self._seen_requests:
                raise ProviderRelayError("relay request replayed")
            if self._calls >= self.policy.max_calls:
                raise _ProviderRelayAdmissionError("provider model-call budget is exhausted", request)
            self._seen_requests.add(request_id)
            self._calls += 1
        return request

    @staticmethod
    def _status_class(status_code: int) -> str:
        if type(status_code) is not int:
            return ""
        family = f"{status_code // 100}xx"
        return family if family in {"2xx", "4xx", "5xx"} else ""

    @staticmethod
    def _status_reason_subreason(status_code: int, status_class: str) -> str:
        if type(status_code) is not int:
            return ""
        if status_code in {400, 422} and status_class == "4xx":
            return "request_rejected"
        if status_code in {401, 403} and status_class == "4xx":
            return "auth"
        if status_code == 429 and status_class == "4xx":
            return "rate_limited"
        if status_class == "5xx":
            return "upstream_unavailable"
        return ""

    def _validate_lease_and_cancellation(self) -> None:
        if self._closed.is_set() or self._is_cancelled():
            raise ProviderRelayError("provider invocation was cancelled")
        if self._lease_validator is None:
            return
        try:
            result = self._lease_validator()
        except Exception as exc:
            raise ProviderRelayError("credential lease is not active") from exc
        if result is False:
            raise ProviderRelayError("credential lease is not active")

    def _call_upstream(self, request: ProviderRequest) -> ProviderResponse:
        self._validate_lease_and_cancellation()
        try:
            response = self._upstream(request, dict(self._credentials), self._is_cancelled)
            if not isinstance(response, ProviderResponse) or isinstance(response.status_code, bool):
                raise ProviderRelayError("provider response is invalid")
            if 300 <= response.status_code < 400:
                raise ProviderRelayError("provider redirect is not permitted")
            if response.status_code != 200:
                status_class = self._status_class(response.status_code)
                if status_class in {"4xx", "5xx"}:
                    raise _ProviderRelayHTTPStatusError(
                        status_class,
                        reason_subreason=self._status_reason_subreason(response.status_code, status_class),
                    )
                raise ProviderRelayError("provider returned an unsuccessful status")
            try:
                body_iterator = iter(response.body_chunks)
            except TypeError as exc:
                raise ProviderRelayError("provider response body is invalid") from exc
            body_chunks: list[bytes] = []
            total = 0
            for chunk in body_iterator:
                self._validate_lease_and_cancellation()
                if not isinstance(chunk, bytes) or len(chunk) > self.policy.max_chunk_bytes:
                    raise ProviderRelayError("provider response chunk is oversized")
                total += len(chunk)
                if total > self.policy.max_response_bytes:
                    raise ProviderRelayError("provider response is oversized")
                body_chunks.append(chunk)
            return ProviderResponse(
                status_code=response.status_code,
                headers=response.headers,
                body_chunks=tuple(body_chunks),
            )
        except ProviderRelayError:
            raise
        except TimeoutError as exc:
            raise ProviderRelayOutcomeUnknownError(reason_subreason="upstream_timeout") from exc
        except OSError as exc:
            raise ProviderRelayOutcomeUnknownError(reason_subreason="upstream_channel_closed") from exc
        except Exception as exc:
            raise ProviderRelayOutcomeUnknownError(reason_subreason="upstream_exception") from exc

    def _write_http_response(self, channel: Any, request_id: str, response: ProviderResponse) -> None:
        headers: dict[str, str] = {}
        for key, value in response.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ProviderRelayError("provider response headers are invalid")
            normalized = key.casefold()
            if normalized in {"content-type", "cache-control"}:
                if any(ord(char) < 0x20 for char in value):
                    raise ProviderRelayError("provider response headers are invalid")
                headers[normalized] = value[:256]
        header_lines = [
            "HTTP/1.1 200 OK",
            "Connection: close",
            "Transfer-Encoding: chunked",
            f"X-Request-ID: {request_id}",
        ]
        header_lines.extend(f"{key.title()}: {value}" for key, value in headers.items())
        channel.write(("\r\n".join(header_lines) + "\r\n\r\n").encode("ascii"))
        channel.flush()
        total = 0
        for chunk in response.body_chunks:
            self._validate_lease_and_cancellation()
            if not isinstance(chunk, bytes) or len(chunk) > self.policy.max_chunk_bytes:
                raise ProviderRelayError("provider response chunk is oversized")
            total += len(chunk)
            if total > self.policy.max_response_bytes:
                raise ProviderRelayError("provider response is oversized")
            for offset in range(0, len(chunk), self.policy.max_chunk_bytes):
                part = chunk[offset : offset + self.policy.max_chunk_bytes]
                channel.write(f"{len(part):x}\r\n".encode("ascii"))
                channel.write(part + b"\r\n")
                channel.flush()
        self._validate_lease_and_cancellation()
        channel.write(b"0\r\n\r\n")
        channel.flush()

    def _write_http_error(
        self,
        channel: Any,
        request_id: str,
        code: str,
        *,
        error: ProviderRelayError | None = None,
    ) -> None:
        payload: dict[str, object] = {"error": code}
        if isinstance(error, ProviderRelayOutcomeUnknownError):
            payload.update(
                {
                    "retryable": False,
                    "upstreamInitiated": True,
                    "reasonCode": error.error_code,
                    "reasonPhase": error.reason_phase,
                    "reasonSubreason": error.reason_subreason,
                }
            )
        body = json.dumps(payload, separators=(",", ":")).encode("ascii")
        headers = (
            "HTTP/1.1 403 Forbidden\r\n"
            "Connection: close\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"X-Request-ID: {request_id}\r\n\r\n"
        ).encode("ascii")
        channel.write(headers + body)
        channel.flush()

    @staticmethod
    def _error_code(error: ProviderRelayError) -> str:
        if getattr(error, "error_code", None) == "outcome_unknown":
            return "outcome_unknown"
        message = str(error).casefold()
        if "model-call budget is exhausted" in message or "model call budget is exhausted" in message:
            return "budget_exhausted"
        if "call failed" in message:
            return "upstream_error"
        if "oversized" in message or "size bound" in message:
            return "oversize"
        if "replayed" in message:
            return "replay"
        if "cancel" in message:
            return "cancelled"
        if "credential-shaped" in message:
            return "credential_payload"
        if "lease" in message or "credential" in message:
            return "lease_invalid"
        if "redirect" in message:
            return "redirect_denied"
        if "provider" in message and "status" in message:
            return "provider_error"
        return "denied"

    @staticmethod
    def _audit_reason(error: ProviderRelayError, code: str) -> str:
        message = str(error).casefold()
        for marker in (
            "credential-shaped",
            "invocation",
            "token",
            "host",
            "path",
            "method",
            "model",
            "provider",
            "redirect",
            "cancel",
            "replay",
            "oversized",
            "lease",
        ):
            if marker in message:
                return marker.replace("-", "_")
        return code

    def _record_attempt(
        self,
        request: ProviderRequest,
        *,
        phase: str,
        upstream_initiated: bool,
        status_class: str = "",
        error_code: str = "",
        reason_phase: str = "",
        reason_subreason: str = "",
        required: bool = False,
    ) -> None:
        if self._audit is None:
            return
        try:
            self._audit(
                ProviderRelayAudit(
                    run_id=self.binding.run_id,
                    invocation_id=self.binding.invocation_id,
                    provider=request.provider,
                    model=request.model,
                    outcome="allowed" if phase in {"intent", "started", "completed"} else "failed",
                    reason=error_code or phase,
                    upstream_called=upstream_initiated,
                    phase=phase,
                    request_id=request.request_id,
                    lease_id=self._lease_id,
                    destination_host=self.policy.host,
                    destination_path=self.policy.path,
                    sequence=request.sequence,
                    status_class=status_class,
                    error_code=error_code,
                    reason_phase=reason_phase,
                    reason_subreason=reason_subreason,
                )
            )
        except Exception as exc:
            if required:
                with self._request_lock:
                    if self._required_audit_failure is None:
                        self._required_audit_failure = ProviderRelayAuditFailure(phase=phase)
                raise ProviderRelayError("provider attempt evidence is unavailable") from exc

    def _record_identity(
        self,
        value: Mapping[str, object],
        outcome: str,
        reason: str,
        upstream_called: bool,
        *,
        request_id: str = "",
    ) -> None:
        del value, request_id
        if self._audit is None:
            return
        try:
            self._audit(
                ProviderRelayAudit(
                    run_id=self.binding.run_id,
                    invocation_id=self.binding.invocation_id,
                    provider=self.binding.provider,
                    model=self.binding.model,
                    outcome=outcome,
                    reason=_safe_reason(reason),
                    upstream_called=upstream_called,
                )
            )
        except Exception:
            pass

class PinnedProviderHTTPSClient:
    """The trusted-parent HTTPS adapter for one exact provider route."""

    def __init__(self, policy: ProviderRelayPolicy) -> None:
        self.policy = policy
        self._context = ssl.create_default_context()

    def __call__(
        self,
        request: ProviderRequest,
        credentials: dict[str, str],
        is_cancelled: Callable[[], bool],
    ) -> ProviderResponse:
        if request.host != self.policy.host or request.path != self.policy.path or request.method != self.policy.method:
            raise ProviderRelayError("provider route is not pinned")
        if is_cancelled():
            raise ProviderRelayError("provider invocation was cancelled")
        api_key = credentials.get(self.policy.credential_name)
        if not isinstance(api_key, str) or not api_key:
            raise ProviderRelayError("provider credential is unavailable")
        connection = http.client.HTTPSConnection(
            self.policy.host,
            timeout=self.policy.timeout_seconds,
            context=self._context,
        )
        try:
            connection.request(
                self.policy.method,
                self.policy.path,
                body=request.body,
                headers={
                    "Accept": request.headers.get("accept", "application/json"),
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            response = connection.getresponse()
            headers = {
                key.casefold(): value
                for key, value in response.getheaders()
                if key.casefold() in {"content-type", "cache-control"}
            }
            if 300 <= response.status < 400:
                connection.close()
                raise ProviderRelayError("provider redirect is not permitted")
            if response.status != 200:
                status_class = ProviderRelayServer._status_class(response.status)
                connection.close()
                if status_class in {"4xx", "5xx"}:
                    raise _ProviderRelayHTTPStatusError(
                        status_class,
                        reason_subreason=ProviderRelayServer._status_reason_subreason(response.status, status_class),
                    )
                raise ProviderRelayError("provider returned an unsuccessful status")

            def chunks() -> Iterable[bytes]:
                total = 0
                try:
                    while True:
                        if is_cancelled():
                            raise ProviderRelayError("provider invocation was cancelled")
                        chunk = response.read(min(self.policy.max_chunk_bytes, 64 * 1024))
                        if not chunk:
                            return
                        total += len(chunk)
                        if total > self.policy.max_response_bytes:
                            raise ProviderRelayError("provider response is oversized")
                        yield chunk
                finally:
                    connection.close()

            return ProviderResponse(status_code=200, headers=headers, body_chunks=chunks())
        except ProviderRelayError:
            raise
        except TimeoutError as exc:
            connection.close()
            raise ProviderRelayOutcomeUnknownError(reason_subreason="upstream_timeout") from exc
        except OSError as exc:
            connection.close()
            raise ProviderRelayOutcomeUnknownError(reason_subreason="upstream_channel_closed") from exc


__all__ = [
    "PROVIDER_RELAY_PROTOCOL",
    "PROVIDER_RELAY_HOST",
    "GPT56_MODEL_RE",
    "PinnedProviderHTTPSClient",
    "ProviderRelayAudit",
    "ProviderRelayAuditFailure",
    "ProviderRelayBinding",
    "ProviderRelayDescriptor",
    "ProviderRelayError",
    "ProviderRelayOutcomeUnknownError",
    "ProviderRelayPolicy",
    "ProviderWire",
    "provider_wire",
    "ProviderRelayServer",
    "ProviderRequest",
    "ProviderResponse",
    "_relay_bootstrap_payload",
]

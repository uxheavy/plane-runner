"""Small, importable runtime health and safety-stop interface.

The supervisor and operator surfaces can depend on this module without
depending on HTTP, Django models, or the runtime kernel.  The state is local to
one runtime process; Plane remains the durable owner of invocation and run
lifecycle state.
"""

from __future__ import annotations

import os
import http.client
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit

from .config import RUNTIME_PROTOCOL


RuntimeHealthState = Literal["configured", "ready", "draining", "stopped", "dependency_failure"]


class RuntimeSafetyStopError(RuntimeError):
    """A new invocation was attempted after the runtime safety stop."""


@dataclass(frozen=True)
class RuntimeHealthStatus:
    """Bounded, non-secret runtime health snapshot.

    ``as_dict`` is the stable read schema consumed by operator/readback code:
    ``protocol``, ``status``, ``configured``, ``ready``, ``draining``,
    ``stopped``, ``dependencyOk``, ``safetyStop``, ``activeInvocations``, and
    ``reason``.
    """

    status: RuntimeHealthState
    configured: bool
    dependency_ok: bool
    safety_stop: bool
    active_invocations: int
    reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def draining(self) -> bool:
        return self.status == "draining"

    @property
    def stopped(self) -> bool:
        return self.status == "stopped"

    def as_dict(self) -> dict[str, object]:
        """Serialize the exact bounded operator/readback schema."""

        return {
            "protocol": RUNTIME_PROTOCOL,
            "status": self.status,
            "configured": self.configured,
            "ready": self.ready,
            "draining": self.draining,
            "stopped": self.stopped,
            "dependencyOk": self.dependency_ok,
            "safetyStop": self.safety_stop,
            "activeInvocations": self.active_invocations,
            "reason": self.reason,
        }


class RuntimeSafetyController:
    """Thread-safe runtime readiness, drain, and one-way safety-stop state."""

    def __init__(
        self,
        *,
        configured: bool,
        stop_file: str | os.PathLike[str],
        dependency_probe: Callable[[], bool] | None = None,
    ) -> None:
        if not isinstance(configured, bool):
            raise TypeError("configured must be boolean")
        path = Path(stop_file)
        if not path.is_absolute():
            raise ValueError("stop_file must be absolute")
        if dependency_probe is not None and not callable(dependency_probe):
            raise TypeError("dependency_probe must be callable")
        self._configured = configured
        self._stop_file = path
        self._dependency_probe = dependency_probe
        self._lock = threading.RLock()
        self._state: RuntimeHealthState = "configured" if configured else "dependency_failure"
        self._dependency_ok = configured
        self._reason: str | None = None if configured else "runtime configuration is invalid"
        self._active_invocations = 0

    def mark_ready(self) -> RuntimeHealthStatus:
        with self._lock:
            self._refresh_dependency_locked()
            if not self._configured:
                return self._snapshot_locked()
            if self._stop_requested_locked():
                self._state = "draining"
                self._reason = "runtime safety stop is active"
            elif self._dependency_ok:
                self._state = "ready"
                self._reason = None
            return self._snapshot_locked()

    def begin_invocation(self) -> RuntimeHealthStatus:
        with self._lock:
            current = self.health()
            if current.status != "ready":
                raise RuntimeSafetyStopError(f"runtime is not accepting invocations: {current.status}")
            self._active_invocations += 1
            return self._snapshot_locked()

    def finish_invocation(self) -> RuntimeHealthStatus:
        with self._lock:
            if self._active_invocations <= 0:
                raise RuntimeSafetyStopError("runtime invocation accounting underflow")
            self._active_invocations -= 1
            return self._snapshot_locked()

    def request_safety_stop(self, reason: str = "operator safety stop") -> RuntimeHealthStatus:
        """Persist a one-way stop marker and reject new work immediately."""

        if not isinstance(reason, str) or not reason.strip() or len(reason.encode("utf-8")) > 512:
            raise ValueError("safety-stop reason must be a bounded non-empty string")
        with self._lock:
            self._write_stop_marker_locked()
            self._state = "draining"
            self._reason = reason.strip()
            return self._snapshot_locked()

    def mark_stopped(self, reason: str | None = None) -> RuntimeHealthStatus:
        with self._lock:
            self._state = "stopped"
            if reason is not None:
                if not isinstance(reason, str) or len(reason.encode("utf-8")) > 512:
                    raise ValueError("stopped reason exceeds its bound")
                self._reason = reason
            return self._snapshot_locked()

    def mark_dependency_failure(self, reason: str = "runtime dependency is unavailable") -> RuntimeHealthStatus:
        if not isinstance(reason, str) or not reason.strip() or len(reason.encode("utf-8")) > 512:
            raise ValueError("dependency failure reason must be bounded and non-empty")
        with self._lock:
            self._dependency_ok = False
            self._state = "dependency_failure"
            self._reason = reason.strip()
            return self._snapshot_locked()

    def health(self) -> RuntimeHealthStatus:
        with self._lock:
            self._refresh_dependency_locked()
            if self._stop_requested_locked() and self._state not in {"stopped", "draining"}:
                self._state = "draining"
                self._reason = self._reason or "runtime safety stop is active"
            return self._snapshot_locked()

    def _refresh_dependency_locked(self) -> None:
        if self._dependency_probe is None or self._state in {"stopped", "draining"}:
            return
        try:
            dependency_ok = bool(self._dependency_probe())
        except Exception:
            dependency_ok = False
        self._dependency_ok = dependency_ok
        if not dependency_ok and self._state != "stopped":
            self._state = "dependency_failure"
            self._reason = "runtime dependency is unavailable"
        elif dependency_ok and self._state == "dependency_failure" and self._configured:
            self._state = "configured"
            self._reason = None

    def _stop_requested_locked(self) -> bool:
        try:
            return self._stop_file.exists()
        except OSError:
            return True

    def _write_stop_marker_locked(self) -> None:
        try:
            self._stop_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._stop_file.with_name(f".{self._stop_file.name}.tmp-{os.getpid()}")
            temporary.write_text("safety-stop\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self._stop_file)
        except OSError as exc:
            raise RuntimeSafetyStopError("runtime safety stop could not be persisted") from exc

    def _snapshot_locked(self) -> RuntimeHealthStatus:
        return RuntimeHealthStatus(
            status=self._state,
            configured=self._configured,
            dependency_ok=self._dependency_ok,
            safety_stop=self._stop_requested_locked(),
            active_invocations=self._active_invocations,
            reason=self._reason,
        )


_OPERATOR_MAX_RESPONSE_BYTES = 64 * 1024
_OPERATOR_MAX_ID_BYTES = 256


def _operator_text(value: object, name: str, maximum: int = _OPERATOR_MAX_ID_BYTES) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} is invalid")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        raise ValueError(f"{name} contains control characters")
    return value


def _operator_credentials() -> tuple[str, str] | None:
    url = os.environ.get("PLANE_AGENT_RUNTIME_URL", "")
    direct = os.environ.get("PLANE_AGENT_RUNTIME_SECRET", "")
    secret_file = os.environ.get("PLANE_AGENT_RUNTIME_SECRET_FILE", "")
    if not url or (direct and secret_file):
        return None
    secret = direct
    if secret_file:
        try:
            secret = Path(secret_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    if not secret or len(secret.encode("utf-8")) < 32:
        return None
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.query or parsed.fragment:
        return None
    return url.rstrip("/"), secret


def _operator_http(method: str, path: str, body: bytes | None = None) -> tuple[int, dict[str, object]]:
    credentials = _operator_credentials()
    if credentials is None:
        return 0, {"status": "external_required", "ready": False, "code": "RUNTIME_NOT_CONFIGURED"}
    base_url, secret = credentials
    parsed = urlsplit(base_url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=5.0)
    try:
        connection.request(
            method,
            path,
            body=body,
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body or b"")),
            },
        )
        response = connection.getresponse()
        raw = response.read(_OPERATOR_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _OPERATOR_MAX_RESPONSE_BYTES:
            raise RuntimeError("runtime operator response exceeds its size bound")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("runtime operator response is not an object")
        return response.status, value
    except (OSError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("runtime operator boundary is unavailable") from exc
    finally:
        connection.close()


def operator_health_readback(workspace_id: str, limit: int) -> dict[str, object]:
    """Read bounded runtime health through the authenticated runtime HTTP seam."""

    workspace_id = _operator_text(workspace_id, "workspace_id")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 12:
        raise ValueError("limit is outside its allowed range")
    status, value = _operator_http("GET", os.environ.get("PLANE_AGENT_RUNTIME_HEALTH_PATH", "/health/ready"))
    if status == 0:
        return {**value, "workspace_id": workspace_id, "limit": limit}
    if status not in {200, 503}:
        raise RuntimeError("runtime health boundary rejected the request")
    safety_stop = bool(value.get("safetyStop", False))
    value["workspace_id"] = workspace_id
    value["limit"] = limit
    value["safety_stop"] = {
        "status": "draining" if safety_stop else value.get("status", "dependency_failure"),
        "requested": safety_stop,
        "control": "runtime_operator_adapter",
    }
    return value


def request_operator_safety_stop(
    workspace_id: str,
    invocation_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, object]:
    """Request an authenticated, targeted, idempotent runtime safety stop."""

    workspace_id = _operator_text(workspace_id, "workspace_id")
    invocation_id = _operator_text(invocation_id, "invocation_id")
    reason = _operator_text(reason, "reason", 512)
    idempotency_key = _operator_text(idempotency_key, "idempotency_key")
    body = json.dumps(
        {
            "workspaceId": workspace_id,
            "invocationId": invocation_id,
            "reason": reason,
            "idempotencyKey": idempotency_key,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    status, value = _operator_http("POST", "/safety-stop", body)
    if status == 0:
        return {**value, "workspace_id": workspace_id, "invocation_id": invocation_id}
    if status not in {200, 202}:
        raise RuntimeError("runtime safety-stop boundary rejected the request")
    return value


__all__ = [
    "RuntimeHealthState",
    "RuntimeHealthStatus",
    "RuntimeSafetyStopError",
    "RuntimeSafetyController",
    "operator_health_readback",
    "request_operator_safety_stop",
]

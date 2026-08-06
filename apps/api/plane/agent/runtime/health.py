"""Small, importable runtime health and safety-stop interface.

The supervisor and operator surfaces can depend on this module without
depending on HTTP, Django models, or the runtime kernel.  The state is local to
one runtime process; Plane remains the durable owner of invocation and run
lifecycle state.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

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


def operator_health_readback(*, controller: RuntimeSafetyController) -> dict[str, object]:
    """Adapter for the operator aggregate's ``operator_health_readback`` hook."""

    return controller.health().as_dict()


def request_operator_safety_stop(*, controller: RuntimeSafetyController, reason: str) -> dict[str, object]:
    """Adapter for the operator aggregate's safety-stop hook."""

    return controller.request_safety_stop(reason).as_dict()


__all__ = [
    "RuntimeHealthState",
    "RuntimeHealthStatus",
    "RuntimeSafetyStopError",
    "RuntimeSafetyController",
    "operator_health_readback",
    "request_operator_safety_stop",
]

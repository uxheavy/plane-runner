"""Bounded health and safety-stop HTTP boundary for the separate runtime."""

from __future__ import annotations

import hmac
import json
import os
import signal
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import AgentRuntimeConfiguration, RuntimeConfigurationError
from .health import RuntimeHealthStatus, RuntimeSafetyController, RuntimeSafetyStopError


def _bounded_reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 512:
        raise ValueError("reason must be a bounded non-empty string")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        raise ValueError("reason contains control characters")
    return value.strip()


def _listen_address(environment: dict[str, str] | os._Environ[str]) -> tuple[str, int]:
    host = environment.get("PLANE_AGENT_RUNTIME_BIND", "0.0.0.0")
    if not isinstance(host, str) or not host or "\x00" in host or len(host) > 255:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_BIND is invalid")
    raw_port = environment.get("PLANE_AGENT_RUNTIME_PORT", "8080")
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_PORT must be a positive integer") from exc
    if port <= 0 or port > 65535:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_PORT is outside its allowed range")
    return host, port


class _RuntimeHTTPHandler(BaseHTTPRequestHandler):
    server: "_RuntimeHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/health", "/health/live", self.server.configuration.health_path}:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        snapshot = self.server.controller.health()
        status = (
            HTTPStatus.OK
            if self.path == "/health/live" and snapshot.status != "stopped"
            else self._health_status(snapshot)
        )
        self._write_json(status, snapshot.as_dict())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/safety-stop":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        length_header = self.headers.get("Content-Length", "0")
        try:
            content_length = int(length_header)
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return
        if content_length < 0 or content_length > self.server.configuration.max_request_bytes:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_too_large"})
            return
        try:
            raw = self.rfile.read(content_length)
            body: Any = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            reason = _bounded_reason(body.get("reason", "operator safety stop"))
            snapshot = self.server.controller.request_safety_stop(reason)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return
        except RuntimeSafetyStopError:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "safety_stop_unavailable"})
            return
        self._write_json(HTTPStatus.ACCEPTED, snapshot.as_dict())

    def _authorized(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            return False
        presented = authorization[len(prefix) :]
        return hmac.compare_digest(presented.encode("utf-8"), self.server.configuration.shared_secret.encode("utf-8"))

    @staticmethod
    def _health_status(snapshot: RuntimeHealthStatus) -> HTTPStatus:
        return HTTPStatus.OK if snapshot.status == "ready" else HTTPStatus.SERVICE_UNAVAILABLE

    def _write_json(self, status: HTTPStatus, value: dict[str, object]) -> None:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > self.server.configuration.max_response_bytes:
            payload = b'{"error":"response_too_large"}'
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        # Never echo request headers or body; status and path are enough for a
        # bounded local diagnostic and are intentionally not credential-bearing.
        message = format % args
        if len(message) > 256:
            message = message[:256]
        sys.stderr.write(f"event=agent.runtime.http message={message!r}\n")


class _RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        controller: RuntimeSafetyController,
        configuration: AgentRuntimeConfiguration,
    ):
        super().__init__(address, _RuntimeHTTPHandler)
        self.controller = controller
        self.configuration = configuration


def run_runtime_service(environment: dict[str, str] | None = None) -> int:
    """Start the runtime boundary and return a process exit code."""

    source = os.environ if environment is None else environment
    try:
        configuration = AgentRuntimeConfiguration.from_environment(source)
        address = _listen_address(source)
    except RuntimeConfigurationError:
        sys.stderr.write("event=agent.runtime.startup status=failed reason=invalid_configuration\n")
        return 78

    controller = RuntimeSafetyController(configured=True, stop_file=configuration.safety_stop_file)
    try:
        controller.mark_ready()
        server = _RuntimeHTTPServer(address, controller, configuration)
    except (OSError, RuntimeSafetyStopError):
        sys.stderr.write("event=agent.runtime.startup status=failed reason=boundary_unavailable\n")
        return 78

    stop_requested = threading.Event()

    def stop_handler(_signum: int, _frame: Any) -> None:
        if stop_requested.is_set():
            return
        stop_requested.set()
        controller.mark_stopped("runtime process is stopping")
        threading.Thread(target=server.shutdown, daemon=True).start()

    previous_handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    sys.stderr.write("event=agent.runtime.startup status=ready\n")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        server.server_close()
        controller.mark_stopped("runtime process stopped")
    return 0


def main() -> int:
    return run_runtime_service()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_runtime_service"]

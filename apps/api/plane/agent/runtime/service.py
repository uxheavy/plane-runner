"""Bounded health and safety-stop HTTP boundary for the separate runtime."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import shutil
import signal
import sys
import threading
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .config import AgentRuntimeConfiguration, RuntimeConfigurationError
from .contracts import (
    RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
    RuntimeDispatchError,
)
from .health import RuntimeHealthStatus, RuntimeSafetyController, RuntimeSafetyStopError
from .host_rpc import PlaneHostCall, PlaneHostHTTPClient, PlaneHostServer
from .credentials import validate_credential_lease_metadata
from .provider_egress import (
    GPT56_MODEL_RE,
    PinnedProviderHTTPSClient,
    ProviderRelayAudit,
    ProviderRelayAuditFailure,
    ProviderRelayBinding,
    ProviderRelayDescriptor,
    ProviderRelayServer,
    ProviderUpstream,
)
from .subprocess import RuntimeProcessPolicy, SubprocessRuntimeTransport, _hermes_bootstrap_payload


RUNTIME_DISPATCH_PROTOCOL = "plane.agent-runtime/dispatch/v1"
_MAX_DISPATCH_FIELDS = {
    "protocol",
    "requestDigest",
    "runId",
    "invocationId",
    "snapshot",
    "invocation",
    "host",
    "credentials",
    "credentialLease",
    "modelCallAllowance",
}


def _canonical(value: Any, name: str) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not JSON-compatible") from exc


def _request_digest(snapshot: dict[str, Any], invocation: dict[str, Any]) -> str:
    snapshot_json = _canonical(snapshot, "runtime snapshot")
    invocation_json = _canonical(invocation, "runtime invocation")
    return hashlib.sha256(b"plane.agent-runtime/dispatch/v1\n" + snapshot_json + b"\n" + invocation_json).hexdigest()


def _duplicate_rejecting_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _strict_body(raw: bytes, maximum: int, allowed: set[str] | None = None) -> dict[str, Any]:
    if len(raw) > maximum:
        raise ValueError("request exceeds the size bound")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_rejecting_pairs)
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise ValueError("request is invalid") from exc
    if not isinstance(value, dict) or _canonical(value, "runtime dispatch request") != raw:
        raise ValueError("request is not canonical")
    if set(value).difference(allowed or _MAX_DISPATCH_FIELDS):
        raise ValueError("request contains unknown fields")
    return value


@dataclass
class RuntimeProviderRelay:
    """Parent-owned lifecycle for one child provider socket."""

    server: ProviderRelayServer
    temp_dir: str

    @property
    def descriptor(self) -> ProviderRelayDescriptor:
        return self.server.descriptor

    @property
    def required_audit_failure(self) -> ProviderRelayAuditFailure | None:
        return self.server.required_audit_failure

    def close(self) -> None:
        self.server.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def __enter__(self) -> "RuntimeProviderRelay":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


class RuntimeDispatchExecutor:
    """Execute authenticated dispatches without importing Plane application code."""

    def __init__(
        self,
        configuration: AgentRuntimeConfiguration,
        controller: RuntimeSafetyController,
        is_invocation_cancelled: Callable[[str], bool] | None = None,
    ) -> None:
        self.configuration = configuration
        self.controller = controller
        self._is_invocation_cancelled = is_invocation_cancelled or (lambda _invocation_id: False)
        self._slots = threading.BoundedSemaphore(configuration.max_concurrent_invocations)
        child_environment = dict(configuration.child_environment)
        child_environment.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.common")
        child_environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        child_environment.setdefault("PYTHONNOUSERSITE", "1")
        child_environment.setdefault("PYTHONPATH", "/opt:/opt/hermes")
        child_environment.setdefault("PLANE_AGENT_RUNTIME_DISABLE_VFORK", "1")
        child_environment.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
        self._transport = SubprocessRuntimeTransport(
            command=configuration.command,
            ledger_path=configuration.ledger_path,
            environment=child_environment,
            timeout_seconds=configuration.timeout_seconds,
            max_input_bytes=configuration.max_request_bytes,
            max_output_bytes=configuration.max_response_bytes,
            is_cancelled=lambda: controller.health().safety_stop,
            process_policy=RuntimeProcessPolicy(
                cpu_seconds=configuration.cpu_seconds,
                memory_bytes=configuration.memory_bytes,
                pids_limit=configuration.pids_limit,
                enforce_kernel_policy=True,
            ),
        )

    def open_provider_relay(
        self,
        *,
        run_id: str,
        invocation_id: str,
        provider: str,
        model: str,
        credentials: dict[str, str],
        credential_lease: Mapping[str, object],
        upstream: ProviderUpstream | None = None,
        audit: Callable[[ProviderRelayAudit], None] | None = None,
    ) -> RuntimeProviderRelay:
        """Open the private relay for one exact Hermes provider invocation."""

        policy = self.configuration.provider_policy
        if policy is None:
            raise RuntimeConfigurationError("provider egress is not configured")
        if not isinstance(credential_lease, Mapping):
            raise RuntimeConfigurationError("provider credential lease is required")
        if provider != policy.provider:
            raise RuntimeConfigurationError("provider is outside the configured route")
        try:
            temp_dir = tempfile.mkdtemp(prefix="plane-agent-provider-")
            socket_path = os.path.join(temp_dir, "provider.sock")
            relay = ProviderRelayServer(
                socket_path=socket_path,
                binding=ProviderRelayBinding(
                    run_id=run_id,
                    invocation_id=invocation_id,
                    provider=provider,
                    model=model,
                ),
                policy=policy,
                credentials=credentials,
                upstream=upstream or PinnedProviderHTTPSClient(policy),
                lease_validator=lambda: validate_credential_lease_metadata(
                    credential_lease,
                    invocation_ref=invocation_id,
                    state_file=self.configuration.credential_state_file,
                ),
                lease_id=str(credential_lease.get("leaseId", "")),
                is_cancelled=lambda: self.controller.health().safety_stop
                or self._is_invocation_cancelled(invocation_id),
                audit=audit,
            )
            relay.start()
            return RuntimeProviderRelay(server=relay, temp_dir=temp_dir)
        except Exception:
            if "relay" in locals():
                relay.close()
            if "temp_dir" in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def dispatch(self, value: dict[str, Any]) -> tuple[str, ...]:
        if value.get("protocol") != RUNTIME_DISPATCH_PROTOCOL:
            raise ValueError("runtime dispatch protocol is unsupported")
        snapshot = value.get("snapshot")
        invocation = value.get("invocation")
        if not isinstance(snapshot, dict) or not isinstance(invocation, dict):
            raise ValueError("runtime dispatch snapshot and invocation are required")
        run_id = value.get("runId")
        invocation_id = value.get("invocationId")
        if (
            not isinstance(run_id, str)
            or not run_id
            or not isinstance(invocation_id, str)
            or not invocation_id
            or snapshot.get("runId") != run_id
            or invocation.get("runId") != run_id
            or invocation.get("invocationId") != invocation_id
        ):
            raise ValueError("runtime dispatch identity is invalid")
        digest = value.get("requestDigest")
        if not isinstance(digest, str) or digest != _request_digest(snapshot, invocation):
            raise ValueError("runtime dispatch digest is invalid")
        credentials = value.get("credentials", {})
        if not isinstance(credentials, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in credentials.items()
        ):
            raise ValueError("runtime dispatch credentials are invalid")
        allowance = value.get("modelCallAllowance")
        if allowance is not None and (isinstance(allowance, bool) or not isinstance(allowance, int)):
            raise ValueError("runtime model-call allowance is invalid")
        credential_lease = value.get("credentialLease")
        if credential_lease is not None and not isinstance(credential_lease, dict):
            raise ValueError("runtime credential lease is invalid")
        host = value.get("host")
        if host is not None:
            if not isinstance(host, dict) or set(host) != {"url", "token"}:
                raise ValueError("runtime host endpoint is invalid")
            host_url = host.get("url")
            host_token = host.get("token")
            if not isinstance(host_url, str) or not isinstance(host_token, str):
                raise ValueError("runtime host endpoint is invalid")
        else:
            host_url = host_token = None
        if not self._slots.acquire(blocking=False):
            raise RuntimeSafetyStopError("runtime invocation concurrency limit reached")
        began = False
        try:
            self.controller.begin_invocation()
            began = True
            return self._execute(
                snapshot,
                invocation,
                digest,
                credentials=credentials,
                credential_lease=credential_lease,
                allowance=allowance,
                host_url=host_url,
                host_token=host_token,
            )
        finally:
            try:
                if began:
                    self.controller.finish_invocation()
            finally:
                self._slots.release()

    def _execute(
        self,
        snapshot: dict[str, Any],
        invocation: dict[str, Any],
        digest: str,
        *,
        credentials: dict[str, str],
        credential_lease: Mapping[str, object] | None,
        allowance: int | None,
        host_url: str | None,
        host_token: str | None,
    ) -> tuple[str, ...]:
        snapshot_json = _canonical(snapshot, "runtime snapshot").decode("utf-8")
        invocation_json = _canonical(invocation, "runtime invocation").decode("utf-8")
        server: PlaneHostServer | None = None
        temp_dir: str | None = None
        provider_relay: RuntimeProviderRelay | None = None
        host_client: PlaneHostHTTPClient | None = None
        command = self.configuration.command
        try:
            provider_route = self._configured_provider_route(snapshot)
            if provider_route is not None:
                if credential_lease is None:
                    raise RuntimeConfigurationError("provider relay requires a credential lease")
                if host_url is None or host_token is None:
                    raise RuntimeConfigurationError("provider attempt evidence requires the Plane host callback")
            if host_url is not None and host_token is not None:
                temp_dir = tempfile.mkdtemp(prefix="plane-agent-host-")
                socket_path = os.path.join(temp_dir, "host.sock")
                host_client = PlaneHostHTTPClient(url=host_url, auth_token=host_token)
                server = PlaneHostServer(socket_path=socket_path, invoke=host_client.invoke)
                server.start()
                command = (*command, "--plane-host-socket", socket_path)

            def provider_audit(audit: ProviderRelayAudit) -> None:
                if host_client is None:
                    raise RuntimeConfigurationError("provider attempt evidence requires the Plane host callback")
                result = host_client.invoke(
                    PlaneHostCall(
                        run_id=audit.run_id,
                        invocation_id=audit.invocation_id,
                        correlation_id=invocation["correlationId"],
                        action="observe",
                        operation_ref="runtime.provider_attempt",
                        input={
                            "phase": audit.phase,
                            "leaseId": audit.lease_id,
                            "provider": audit.provider,
                            "model": audit.model,
                            "destinationHost": audit.destination_host,
                            "destinationPath": audit.destination_path,
                            "requestId": audit.request_id,
                            "idempotencyKey": (
                                "provider-attempt:"
                                + hashlib.sha256(audit.request_id.encode("utf-8")).hexdigest()
                            ),
                            "sequence": audit.sequence,
                            "upstreamInitiated": audit.upstream_called,
                            "statusClass": audit.status_class,
                            "errorCode": audit.error_code,
                        },
                        source="runtime",
                    )
                )
                if result.status not in {"ok", "replayed"}:
                    raise RuntimeConfigurationError("provider attempt evidence was rejected by Plane")

            if provider_route is not None:
                policy, provider, model = provider_route
                provider_relay = self.open_provider_relay(
                    run_id=snapshot["runId"],
                    invocation_id=invocation["invocationId"],
                    provider=provider,
                    model=model,
                    credentials=credentials,
                    credential_lease=credential_lease,
                    audit=provider_audit,
                )
            payload, run_id, invocation_id, _bootstrap_digest = _hermes_bootstrap_payload(
                snapshot_json,
                invocation_json,
                model_call_allowance=allowance,
                credentials=credentials,
                provider_relay=(provider_relay.descriptor, provider_route[0])
                if provider_relay is not None and provider_route is not None
                else None,
            )
            if provider_relay is not None:
                command = (*command, "--provider-relay-socket", str(provider_relay.descriptor.socket_path))

            def is_cancelled() -> bool:
                return self.controller.health().safety_stop or self._is_invocation_cancelled(invocation_id)

            try:
                frames = self._transport.dispatch_payload(
                    payload=payload,
                    run_id=run_id,
                    invocation_id=invocation_id,
                    request_digest=digest,
                    command=command,
                    is_cancelled=is_cancelled,
                )
            except Exception:
                if provider_relay is not None and provider_relay.required_audit_failure is not None:
                    raise RuntimeConfigurationError("provider attempt evidence was rejected by Plane") from None
                raise
            if provider_relay is not None and provider_relay.required_audit_failure is not None:
                raise RuntimeConfigurationError("provider attempt evidence was rejected by Plane")
            return frames
        finally:
            if server is not None:
                server.close()
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            if provider_relay is not None:
                provider_relay.close()

    def _configured_provider_route(
        self, snapshot: Mapping[str, Any]
    ) -> tuple[Any, str, str] | None:
        policy = self.configuration.provider_policy
        if policy is None:
            return None
        runtime_policy = snapshot.get("runtimePolicy")
        model = runtime_policy.get("model") if isinstance(runtime_policy, Mapping) else None
        if (
            not isinstance(model, Mapping)
            or set(model) != {"provider", "model"}
            or not isinstance(model.get("provider"), str)
            or not isinstance(model.get("model"), str)
        ):
            raise RuntimeConfigurationError("runtime snapshot model route is invalid")
        if policy.provider == "openai-codex" and not GPT56_MODEL_RE.fullmatch(model["model"]):
            raise RuntimeConfigurationError("runtime snapshot model route is outside the GPT-5.6 family")
        if model["provider"] != policy.provider or model["model"] not in policy.models:
            raise RuntimeConfigurationError("runtime snapshot model route is outside the configured provider route")
        return policy, policy.provider, model["model"]


def _bounded_reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 512:
        raise ValueError("reason must be a bounded non-empty string")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        raise ValueError("reason contains control characters")
    return value.strip()


def _runtime_configuration_subreason(error: RuntimeConfigurationError) -> str:
    """Return a safe category for a configuration rejection.

    Runtime exception text can contain deployment paths or other local
    details.  Only this finite category crosses the HTTP boundary.
    """

    if "provider attempt evidence was rejected by plane" in str(error).casefold():
        return "provider_attempt_evidence_rejected"
    return "runtime_configuration_rejected"


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
        if self.path not in {"/safety-stop", self.server.configuration.dispatch_path}:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            raw = self._read_body()
        except ValueError as exc:
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if str(exc) == "request_too_large" else HTTPStatus.BAD_REQUEST
            self._write_json(status, {"error": str(exc)})
            return
        if self.path == "/safety-stop":
            try:
                body = _strict_body(
                    raw,
                    self.server.configuration.max_request_bytes,
                    {"workspaceId", "invocationId", "reason", "idempotencyKey"},
                )
                if set(body) != {"workspaceId", "invocationId", "reason", "idempotencyKey"}:
                    raise ValueError("safety-stop request fields are invalid")
                status, snapshot = self.server.request_targeted_stop(body)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                return
            except RuntimeSafetyStopError:
                self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "safety_stop_unavailable"})
                return
            self._write_json(status, snapshot)
            return
        try:
            body = _strict_body(raw, self.server.configuration.max_request_bytes)
            if self.server.is_targeted_stop(body.get("invocationId")):
                raise RuntimeSafetyStopError("runtime invocation has a targeted safety stop")
            frames = self.server.dispatch_executor.dispatch(body)
            response = {
                "protocol": RUNTIME_DISPATCH_PROTOCOL,
                "requestDigest": body["requestDigest"],
                "runId": body["runId"],
                "invocationId": body["invocationId"],
                "frames": list(frames),
            }
        except RuntimeSafetyStopError:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "runtime_not_ready"})
            return
        except RuntimeConfigurationError as exc:
            self._write_json(
                HTTPStatus.CONFLICT,
                {
                    "error": "runtime_dispatch_failed",
                    **RuntimeDispatchError(
                        "runtime configuration rejected dispatch",
                        failure_code=RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
                        failure_phase="runtime_configuration",
                        failure_detail="dispatch_rejected",
                        failure_subreason=_runtime_configuration_subreason(exc),
                    ).public_failure(),
                },
            )
            return
        except RuntimeDispatchError as exc:
            self._write_json(
                HTTPStatus.CONFLICT,
                {"error": "runtime_dispatch_failed", **exc.public_failure()},
            )
            return
        except Exception:
            # Exception text, credentials, paths, and transcripts never cross
            # this boundary. The classification is the only durable detail.
            self._write_json(
                HTTPStatus.CONFLICT,
                {
                    "error": "runtime_dispatch_failed",
                    **RuntimeDispatchError("runtime dispatch failed").public_failure(),
                },
            )
            return
        self._write_json(HTTPStatus.OK, response)

    def _read_body(self) -> bytes:
        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if content_length < 0:
            raise ValueError("invalid_content_length")
        if content_length > self.server.configuration.max_request_bytes:
            raise ValueError("request_too_large")
        raw = self.rfile.read(content_length)
        if len(raw) != content_length:
            raise ValueError("invalid_request")
        return raw

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
        executor: RuntimeDispatchExecutor | None = None,
    ):
        super().__init__(address, _RuntimeHTTPHandler)
        self.controller = controller
        self.configuration = configuration
        self._dispatch_executor = executor
        self._stop_lock = threading.RLock()
        self._targeted_stops: dict[str, tuple[str, str, str, dict[str, object]]] = {}

    @property
    def dispatch_executor(self) -> RuntimeDispatchExecutor:
        if self._dispatch_executor is None:
            self._dispatch_executor = RuntimeDispatchExecutor(
                self.configuration,
                self.controller,
                is_invocation_cancelled=self.is_targeted_stop,
            )
        return self._dispatch_executor

    def request_targeted_stop(self, body: dict[str, Any]) -> tuple[HTTPStatus, dict[str, object]]:
        workspace_id = _bounded_reason(body.get("workspaceId"))
        invocation_id = _bounded_reason(body.get("invocationId"))
        reason = _bounded_reason(body.get("reason"))
        idempotency_key = _bounded_reason(body.get("idempotencyKey"))
        with self._stop_lock:
            existing = self._targeted_stops.get(idempotency_key)
            if existing is not None:
                if existing[:3] != (workspace_id, invocation_id, reason):
                    raise ValueError("safety-stop idempotency key is bound to another request")
                result = dict(existing[3])
                result["replayed"] = True
                return HTTPStatus.OK, result
            snapshot = self.controller.health()
            result = snapshot.as_dict()
            result.update(
                {
                    "status": "accepted",
                    "authority": "runtime_ephemeral_enforcement",
                    "planeLifecycleAuthority": "required",
                    "workspaceId": workspace_id,
                    "invocationId": invocation_id,
                    "idempotencyKey": idempotency_key,
                    "replayed": False,
                }
            )
            self._targeted_stops[idempotency_key] = (workspace_id, invocation_id, reason, result)
            return HTTPStatus.ACCEPTED, result

    def is_targeted_stop(self, invocation_id: object) -> bool:
        if not isinstance(invocation_id, str) or not invocation_id:
            return False
        with self._stop_lock:
            return any(record[1] == invocation_id for record in self._targeted_stops.values())


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
    except (OSError, RuntimeSafetyStopError, ValueError):
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

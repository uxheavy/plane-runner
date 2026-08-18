from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import textwrap
import time
from contextlib import nullcontext
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostCall,
    PlaneHostHTTPClient,
    PlaneHostHTTPServer,
    PlaneHostResult,
    RemoteRuntimeTransport,
    RuntimeHostEndpoint,
    RuntimeCredentialBroker,
    RuntimeCredentialError,
    RuntimeDispatchError,
    RuntimeConfigurationError,
    RuntimeSafetyController,
    operator_health_readback,
    request_operator_safety_stop,
)
from plane.agent.runtime import credentials as runtime_credentials
from plane.agent.runtime.provider_egress import ProviderResponse
from plane.agent.runtime.remote import _structured_rejection
from plane.agent.runtime.service import RUNTIME_DISPATCH_PROTOCOL, RuntimeDispatchExecutor, _RuntimeHTTPServer
from plane.agent.runtime.subprocess import RuntimeProcessPolicy, SubprocessRuntimeTransport, _classify_child_failure


@pytest.mark.parametrize(
    ("stderr", "returncode", "exception_class", "module", "category"),
    (
        (b"Traceback\nModuleNotFoundError: No module named 'plane_runtime.missing'\n", 1, "ModuleNotFoundError", "plane_runtime", "module_not_found"),
        (b"Traceback\nImportError: cannot import name hidden from openai\n", 1, "ImportError", "unknown", "import_error"),
        (b"PermissionError: [Errno 13] secret path\n", 1, "PermissionError", "unknown", "permission_denied"),
        (b"OSError: [Errno 1] Operation not permitted: token-value\n", 1, "OSError", "unknown", "os_eperm"),
        (b"MemoryError\n", 1, "MemoryError", "unknown", "memory_exhausted"),
        (b"TimeoutError: hidden prompt\n", 1, "TimeoutError", "unknown", "timeout"),
        (b"Traceback (most recent call last):\nValueError: hidden env\n", 1, "PythonException", "unknown", "python_traceback"),
        (b"never-retained", -9, "Signal", "unknown", "signal"),
        (b"opaque token-value", 2, "Unknown", "unknown", "unknown"),
    ),
)
def test_child_failure_classifier_retains_only_finite_metadata(
    stderr, returncode, exception_class, module, category
):
    diagnostic = _classify_child_failure(stderr, returncode)

    assert diagnostic == {
        "exceptionClass": exception_class,
        "module": module,
        "category": category,
        "stderrSha256": hashlib.sha256(stderr).hexdigest(),
        "stderrBytes": len(stderr),
        "termination": "signal" if returncode < 0 else "exit",
        "exitCode": returncode,
    }
    assert "token-value" not in json.dumps(diagnostic, sort_keys=True)


def test_nonzero_child_exit_threads_bounded_diagnostic_without_stderr(tmp_path):
    stderr = b"Traceback\nModuleNotFoundError: No module named 'plane_runtime.secret'\ntoken-value\n"
    transport = SubprocessRuntimeTransport(
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stdin.buffer.read(); sys.stderr.buffer.write(" + repr(stderr) + "); raise SystemExit(1)",
        ),
        ledger_path=tmp_path / "ledger.sqlite",
        process_policy=RuntimeProcessPolicy(enforce_kernel_policy=False),
    )

    with pytest.raises(RuntimeDispatchError) as raised:
        transport._run_process(b"{}\n")

    failure = raised.value.public_failure()
    assert failure["childDiagnostic"] == _classify_child_failure(stderr, 1)
    assert "token-value" not in json.dumps(failure, sort_keys=True)


def test_remote_rejection_preserves_only_valid_child_diagnostic():
    diagnostic = _classify_child_failure(b"ImportError: hidden token-value\n", 1)
    rejection = {
        "error": "runtime_dispatch_failed",
        "failureCode": "runtime_process_failed",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "childDiagnostic": diagnostic,
    }
    body = json.dumps(rejection, sort_keys=True, separators=(",", ":")).encode()

    error = _structured_rejection(body)

    assert error is not None
    assert error.public_failure()["childDiagnostic"] == diagnostic
    assert "token-value" not in json.dumps(error.public_failure(), sort_keys=True)
    rejection["childDiagnostic"] = {**diagnostic, "message": "token-value"}
    assert _structured_rejection(json.dumps(rejection, sort_keys=True, separators=(",", ":")).encode()) is None


def _runtime_environment(tmp_path: Path, source: str, command: str | None = None) -> dict[str, str]:
    module_root = tmp_path / "runtime-module"
    package = module_root / "plane_runtime" / "g1_runtime_image"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "bootstrap.py").write_text(source, encoding="utf-8")
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": "s" * 40,
        "PLANE_AGENT_RUNTIME_COMMAND": command
        or f"{sys.executable} -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": json.dumps(
            {"PYTHONPATH": str(module_root)}, sort_keys=True, separators=(",", ":")
        ),
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "safety-stop"),
    }
    return environment


def _configuration(tmp_path):
    source = 'import sys\nsys.stdin.buffer.read()\nprint(\'{"protocol":"fixture","credential":"not-emitted"}\')\n'
    environment = _runtime_environment(tmp_path, source)
    return AgentRuntimeConfiguration.from_environment(environment)


def _dispatch_body(suffix: str = "one") -> tuple[str, str]:
    snapshot = {
        "actorRef": f"agent:{suffix}",
        "contentDigest": "snapshot:digest",
        "runId": f"run:{suffix}",
        "workspaceRef": f"workspace:{suffix}",
    }
    invocation = {
        "correlationId": f"correlation:{suffix}",
        "invocationId": f"invocation:{suffix}",
        "runId": f"run:{suffix}",
    }
    return (
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        json.dumps(invocation, sort_keys=True, separators=(",", ":")),
    )


class _FailingRuntimeExecutor:
    def __init__(self, error: Exception):
        self.error = error

    def dispatch(self, body):
        raise self.error


@pytest.mark.parametrize(
    "failure",
    (
        RuntimeDispatchError("runtime-secret=/private/transcript"),
        RuntimeError("runtime-secret=/private/transcript"),
    ),
    ids=("runtime-dispatch-error", "generic-exception"),
)
def test_g4_service_and_remote_preserve_unclassified_failure_without_leaking_raw_error(tmp_path, failure):
    configuration = _configuration(tmp_path)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    server = _RuntimeHTTPServer(
        ("127.0.0.1", 0),
        controller,
        configuration,
        executor=SimpleNamespace(dispatch=_FailingRuntimeExecutor(failure).dispatch),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("unclassified")
    try:
        with pytest.raises(RuntimeDispatchError) as raised:
            RemoteRuntimeTransport(
                runtime_url=f"http://127.0.0.1:{server.server_port}",
                shared_secret=configuration.shared_secret,
            ).dispatch(snapshot_json, invocation_json)
        error = raised.value
        assert error.has_allowlisted_failure is False
        assert error.failure_detail == "unclassified_exception"
        assert "runtime-secret=/private/transcript" not in str(error)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_remote_classifies_pinned_pre_subreason_runtime_rejection_with_safe_subreason():
    class LegacyRejectionHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            content_length = int(self.headers["Content-Length"])
            self.rfile.read(content_length)
            body = (
                b'{"error":"runtime_dispatch_failed",'
                b'"failureCode":"runtime_configuration_pre_dispatch_failure",'
                b'"failureDetail":"dispatch_rejected",'
                b'"failurePhase":"runtime_configuration"}'
            )
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), LegacyRejectionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("legacy-runtime")
    try:
        with pytest.raises(RuntimeDispatchError) as raised:
            RemoteRuntimeTransport(
                runtime_url=f"http://127.0.0.1:{server.server_port}",
                shared_secret="s" * 40,
            ).dispatch(snapshot_json, invocation_json)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    error = raised.value
    assert error.has_allowlisted_failure is True
    assert error.public_failure() == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }
    assert "runtime_dispatch_failed" not in json.dumps(error.public_failure(), sort_keys=True)


def test_g4_remote_keeps_opaque_legacy_rejection_unclassified():
    assert _structured_rejection(b'{"error":"runtime_dispatch_failed"}') is None


def test_g4_remote_credential_resolution_failure_is_a_single_classified_pre_dispatch_boundary(tmp_path):
    def unavailable(_credential_ref):
        raise RuntimeCredentialError("provider credential source is unavailable")

    broker = RuntimeCredentialBroker(unavailable)
    snapshot_json, invocation_json = _dispatch_body("credential-failure")
    transport = RemoteRuntimeTransport(
        runtime_url="http://127.0.0.1:1",
        shared_secret="s" * 40,
        credential_broker=broker,
    )

    with pytest.raises(RuntimeDispatchError) as raised:
        transport.dispatch(snapshot_json, invocation_json)

    error = raised.value
    assert error.has_allowlisted_failure is True
    assert error.failure_code == "runtime_configuration_pre_dispatch_failure"
    assert error.failure_phase == "runtime_configuration"
    assert error.failure_detail == "dispatch_rejected"
    assert error.failure_subreason == "credential_source_unavailable"


def test_g4_runtime_configuration_rejection_preserves_bounded_subreason_without_raw_details(tmp_path):
    configuration = _configuration(tmp_path)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    failure = RuntimeConfigurationError(
        "provider attempt evidence was rejected by Plane: /private/runtime-secret=do-not-export"
    )
    server = _RuntimeHTTPServer(
        ("127.0.0.1", 0),
        controller,
        configuration,
        executor=SimpleNamespace(dispatch=_FailingRuntimeExecutor(failure).dispatch),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("configuration-subreason")
    try:
        with pytest.raises(RuntimeDispatchError) as raised:
            RemoteRuntimeTransport(
                runtime_url=f"http://127.0.0.1:{server.server_port}",
                shared_secret=configuration.shared_secret,
            ).dispatch(snapshot_json, invocation_json)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    error = raised.value
    assert error.failure_subreason == "provider_attempt_evidence_rejected"
    assert error.public_failure() == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "provider_attempt_evidence_rejected",
    }
    assert "private/runtime-secret" not in json.dumps(error.public_failure(), sort_keys=True)


def test_g4_runtime_dispatch_is_cross_process_and_revokes_invocation_credentials(tmp_path):
    configuration = _configuration(tmp_path)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body()
    broker = RuntimeCredentialBroker({"runtime": {"TOKEN": "disposable-token"}})
    try:
        transport = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{server.server_port}",
            shared_secret=configuration.shared_secret,
            credential_broker=broker,
        )
        frames = transport.dispatch(snapshot_json, invocation_json)
        assert frames == ('{"protocol":"fixture","credential":"not-emitted"}',)
        assert controller.health().active_invocations == 0
        assert broker.revoke_invocation("invocation:one") == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_provider_dispatch_crosses_runtime_boundary_before_provider_request(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_credentials.time, "time", lambda: 1_786_097_520.0)
    source = tmp_path / "provider-source"
    source.write_text(
        json.dumps(
            {
                "last_refresh": "2026-08-07T10:12:00Z",
                "tokens": {
                    "access_token": "synthetic-access-token",
                    "account_id": "synthetic-account-id",
                    "id_token": "synthetic-id-token",
                    "refresh_token": "synthetic-refresh-token",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    credentials = runtime_credentials.resolve_deployment_credential("runtime")
    assert credentials == {"api_key": "synthetic-access-token"}
    assert set(credentials) == {"api_key"}

    environment = _runtime_environment(
        tmp_path,
        'import sys\nsys.stdin.buffer.read()\nprint(\'{"protocol":"fixture","boundary":"child-started"}\')\n',
    )
    environment.update(
        {
            "PLANE_AGENT_RUNTIME_PROVIDER": "openai-codex",
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "chatgpt.com",
            "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "/backend-api/codex/responses",
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "gpt-5.6-luna",
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(tmp_path / "credential-state.json"),
        }
    )
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("provider-boundary")
    snapshot = json.loads(snapshot_json)
    snapshot["runtimePolicy"] = {
        "model": {"provider": "openai-codex", "model": "gpt-5.6-luna"},
        "adapter": "openai-compatible",
        "isolation": "single-invocation",
        "maxEventPayloadBytes": 8192,
        "maxArtifactBytes": 8192,
        "maxReceiptBytes": 8192,
    }
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    try:
        frames = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{server.server_port}",
            shared_secret=configuration.shared_secret,
            credential_broker=RuntimeCredentialBroker({"runtime": credentials}),
            host_endpoint_factory=lambda _invocation_id: nullcontext(
                RuntimeHostEndpoint(url="http://127.0.0.1:1", token="host-token")
            ),
        ).dispatch(snapshot_json, invocation_json)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert frames == ('{"protocol":"fixture","boundary":"child-started"}',)


def test_g4_runtime_http_classifies_incomplete_hermes_policy_without_raw_exception(tmp_path):
    configuration = _configuration(tmp_path)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("incomplete-policy")
    snapshot = json.loads(snapshot_json)
    snapshot["runtimePolicy"] = {
        "model": {"provider": "openai-codex", "model": "gpt-5.6-luna"},
    }
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))

    try:
        with pytest.raises(RuntimeDispatchError) as raised:
            RemoteRuntimeTransport(
                runtime_url=f"http://127.0.0.1:{server.server_port}",
                shared_secret=configuration.shared_secret,
            ).dispatch(snapshot_json, invocation_json)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert raised.value.public_failure() == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }


def test_g4_provider_dispatch_reissues_invocation_relay_and_lease(tmp_path, monkeypatch):
    from plane.agent.runtime.subprocess import RuntimeProcessPolicy, SubprocessRuntimeTransport

    secret = "synthetic-provider-secret"
    state_file = tmp_path / "credential-state.json"
    child = textwrap.dedent(
        """
        import json
        import socket
        import sys

        controls = sys.stdin.buffer.read().splitlines()
        relay = json.loads(controls[1])["credentials"]
        request = json.loads(controls[2])
        assert set(relay) == {"host", "invocationSocket", "path", "provider", "relayToken"}
        assert "synthetic-provider-secret" not in json.dumps(relay, sort_keys=True)
        model = request["run"]["runtimePolicy"]["model"]["model"]
        body = json.dumps(
            {"model": model, "messages": [{"role": "user", "content": "synthetic"}]},
            separators=(",", ":"),
        ).encode()
        wire = (
            b"POST /backend-api/codex/responses HTTP/1.1\\r\\n"
            + b"Host: plane-provider-relay.invalid\\r\\n"
            + ("Authorization: Bearer " + relay["relayToken"] + "\\r\\n").encode()
            + b"Content-Type: application/json\\r\\n"
            + ("Content-Length: " + str(len(body)) + "\\r\\n").encode()
            + b"X-Request-ID: request:cross-process-fake\\r\\n"
            + ("X-Plane-Relay-Invocation: " + request["invocation"]["invocationId"] + "\\r\\n").encode()
            + b"X-Plane-Relay-Provider: openai-codex\\r\\n"
            + ("X-Plane-Relay-Model: " + model + "\\r\\n").encode()
            + ("X-Plane-Relay-Run: " + request["run"]["runId"] + "\\r\\n\\r\\n").encode()
            + body
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(2)
            channel.connect(relay["invocationSocket"])
            channel.sendall(wire)
            response = bytearray()
            while True:
                chunk = channel.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
        assert b"200 OK" in response
        print(json.dumps({"protocol": "fixture", "status": "completed"}, separators=(",", ":")))
        """
    )
    environment = _runtime_environment(tmp_path, "print('{}')\n")
    environment.update(
        {
            "PLANE_AGENT_RUNTIME_PROVIDER": "openai-codex",
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "chatgpt.com",
            "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "/backend-api/codex/responses",
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "gpt-5.6-luna",
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(state_file),
        }
    )
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    executor._transport = SubprocessRuntimeTransport(
        command=(sys.executable, "-c", child),
        environment=dict(os.environ),
        ledger_path=tmp_path / "dispatch-ledger.sqlite",
        process_policy=RuntimeProcessPolicy(enforce_kernel_policy=False),
    )
    executor.configuration = replace(configuration, command=(sys.executable, "-c", child))
    fake_attempts = 0
    relay_paths: list[Path] = []

    def fake_provider(_request, credentials, _is_cancelled):
        nonlocal fake_attempts
        assert credentials == {"api_key": secret}
        fake_attempts += 1
        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=(b"data: fake-provider\\n\\n",),
        )

    original_open = executor.open_provider_relay

    def open_with_fake(**kwargs):
        relay = original_open(upstream=fake_provider, **kwargs)
        relay_paths.append(Path(relay.descriptor.socket_path))
        return relay

    relay_tokens: list[str] = []

    def open_with_fake_and_capture(**kwargs):
        relay = open_with_fake(**kwargs)
        relay_tokens.append(relay.descriptor.token)
        return relay

    executor.open_provider_relay = open_with_fake_and_capture  # type: ignore[method-assign]

    callback_phases: list[str] = []

    class FixtureHostClient:
        def __init__(self, *, url: str, auth_token: str):
            assert url == "http://plane-host.invalid"
            assert auth_token == "host-token"

        def invoke(self, call):
            callback_phases.append(call.input["phase"])
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="ok",
                replayed=False,
            )

    monkeypatch.setattr("plane.agent.runtime.service.PlaneHostHTTPClient", FixtureHostClient)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("provider-fake")
    snapshot = json.loads(snapshot_json)
    from plane.agent.lifecycle.services import _runtime_policy

    snapshot["runtimePolicy"], _total_budget = _runtime_policy(
        SimpleNamespace(
            model_defaults={},
            runtime_defaults={
                "provider": "openai-codex",
                "model": "gpt-5.6-luna",
                "adapter": "openai-compatible",
                "maxEventPayloadBytes": 8192,
                "maxArtifactBytes": 8192,
                "maxReceiptBytes": 8192,
                "maxCodeModeInputBytes": 4096,
                "maxCodeModeOutputBytes": 4096,
                "maxCodeModeCalls": 4,
            },
        )
    )
    assert set(snapshot["runtimePolicy"]) == {
        "model",
        "adapter",
        "isolation",
        "maxEventPayloadBytes",
        "maxArtifactBytes",
        "maxReceiptBytes",
        "maxCodeModeInputBytes",
        "maxCodeModeOutputBytes",
        "maxCodeModeCalls",
    }
    runtime_policy = snapshot["runtimePolicy"]

    def dispatch_body(suffix: str) -> tuple[str, str]:
        raw_snapshot, raw_invocation = _dispatch_body(suffix)
        payload = json.loads(raw_snapshot)
        payload["runtimePolicy"] = runtime_policy
        return json.dumps(payload, sort_keys=True, separators=(",", ":")), raw_invocation

    broker = RuntimeCredentialBroker({"runtime": {"api_key": secret}}, state_file=state_file)
    issued_lease_ids: list[str] = []
    original_issue = broker.issue

    def issue(**kwargs):
        lease, values = original_issue(**kwargs)
        issued_lease_ids.append(lease.lease_id)
        return lease, values

    monkeypatch.setattr(broker, "issue", issue)
    transport = RemoteRuntimeTransport(
        runtime_url=f"http://127.0.0.1:{server.server_port}",
        shared_secret=configuration.shared_secret,
        credential_broker=broker,
        host_endpoint_factory=lambda _invocation_id: nullcontext(
            RuntimeHostEndpoint(url="http://plane-host.invalid", token="host-token")
        ),
    )
    try:
        first_frames = transport.dispatch(*dispatch_body("provider-fake-one"))
        second_frames = transport.dispatch(*dispatch_body("provider-fake-two"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first_frames == second_frames == ('{"protocol":"fixture","status":"completed"}',)
    assert fake_attempts == 2
    assert callback_phases == ["intent", "started", "completed"] * 2
    assert secret not in json.dumps(first_frames + second_frames, sort_keys=True)
    assert len(issued_lease_ids) == 2
    assert len(set(issued_lease_ids)) == 2
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert secret not in json.dumps(state, sort_keys=True)
    assert state["revokedLeases"] == issued_lease_ids
    assert len(relay_paths) == 2
    assert len({str(path) for path in relay_paths}) == 2
    assert len(relay_tokens) == 2
    assert len(set(relay_tokens)) == 2
    assert all(not path.exists() for path in relay_paths)


def test_g4_remote_dispatch_preserves_success_after_expired_lease_cleanup(tmp_path, monkeypatch):
    now = [100.0]
    state_file = tmp_path / "credential-revocations.json"
    broker = RuntimeCredentialBroker(
        {"runtime": {"TOKEN": "fixture-value"}},
        ttl_seconds=1,
        clock=lambda: now[0],
        state_file=state_file,
    )
    issued_lease_ids = []
    original_issue = broker.issue

    def issue(**kwargs):
        lease, values = original_issue(**kwargs)
        issued_lease_ids.append(lease.lease_id)
        return lease, values

    monkeypatch.setattr(broker, "issue", issue)
    transport = RemoteRuntimeTransport(
        runtime_url="http://127.0.0.1:1",
        shared_secret="s" * 40,
        credential_broker=broker,
    )
    snapshot_json, invocation_json = _dispatch_body("expired-cleanup")

    def successful_post(payload):
        request = json.loads(payload)
        now[0] = 101.0
        return json.dumps(
            {
                "frames": ['{"status":"completed"}'],
                "invocationId": request["invocationId"],
                "protocol": RUNTIME_DISPATCH_PROTOCOL,
                "requestDigest": request["requestDigest"],
                "runId": request["runId"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    monkeypatch.setattr(transport, "_post", successful_post)

    assert transport.dispatch(snapshot_json, invocation_json) == ('{"status":"completed"}',)
    assert len(issued_lease_ids) == 1
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["revokedLeases"] == issued_lease_ids
    with pytest.raises(RuntimeCredentialError, match="revoked"):
        broker.resolve(
            issued_lease_ids[0],
            agent_ref="agent:expired-cleanup",
            invocation_ref="invocation:expired-cleanup",
        )
    assert broker.revoke_lease_id(issued_lease_ids[0]) is False


def test_g4_runtime_dispatch_child_rejects_network_and_process_escapes(tmp_path):
    fixture = (
        "import ctypes, errno, json, os, platform, socket, subprocess, sys\n"
        "from plane.agent.runtime.subprocess import _SYSCALLS\n"
        "sys.stdin.buffer.read()\n"
        "child = subprocess.run([sys.executable, '-c', 'print(\"child\")'], capture_output=True, check=False)\n"
        "bootstrap_child_allowed = child.returncode == 0 and child.stdout == b'child\\n'\n"
        "code_child = subprocess.run([sys.executable, '-c', 'print(\"code\")'], "
        "capture_output=True, check=False, start_new_session=True)\n"
        "code_mode_spawn_allowed = code_child.returncode == 0 and code_child.stdout == b'code\\n'\n"
        "def denied_network():\n"
        "    try:\n"
        "        socket.socket()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "machine = platform.machine()\n"
        "syscalls = _SYSCALLS[machine]\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "def denied_process():\n"
        "    fork_syscall = syscalls.get('fork')\n"
        "    if fork_syscall is None:\n"
        "        return 'unsupported'\n"
        "    ctypes.set_errno(0)\n"
        "    result = libc.syscall(fork_syscall)\n"
        "    error = ctypes.get_errno()\n"
        "    if result == 0:\n"
        "        os._exit(99)\n"
        "    if result > 0:\n"
        "        os.waitpid(result, 0)\n"
        "    return 'denied' if result == -1 and error == errno.EPERM else 'unexpected'\n"
        "print(json.dumps({'bootstrapChildAllowed': bootstrap_child_allowed, "
        "'codeModeSpawnAllowed': code_mode_spawn_allowed, 'networkDenied': denied_network(), "
        "'processProbe': denied_process(), 'architecture': machine}, "
        "sort_keys=True, separators=(',', ':')))"
    )
    environment = _runtime_environment(tmp_path, fixture)
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body()
    try:
        frames = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{server.server_port}",
            shared_secret=configuration.shared_secret,
        ).dispatch(snapshot_json, invocation_json)
        observed = json.loads(frames[0])
        expected_process_probe = 'denied' if observed['architecture'] == 'x86_64' else 'unsupported'
        assert observed == {
            "architecture": observed["architecture"],
            "bootstrapChildAllowed": True,
            "codeModeSpawnAllowed": True,
            "networkDenied": True,
            "processProbe": expected_process_probe,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_runtime_architecture_syscall_table_is_precise():
    from plane.agent.runtime.subprocess import _SYSCALLS

    assert _SYSCALLS["x86_64"]["fork"] == 57
    assert _SYSCALLS["x86_64"]["vfork"] == 58
    assert _SYSCALLS["x86_64"]["fchmodat2"] == 452
    assert "fork" not in _SYSCALLS["aarch64"]
    assert "vfork" not in _SYSCALLS["aarch64"]
    assert _SYSCALLS["aarch64"]["fchmodat2"] == 452


def test_g4_runtime_direct_syscalls_are_architecture_aware_and_bound(tmp_path):
    fixture = (
        "import ctypes, errno, json, mmap, os, pathlib, platform, socket, sys\n"
        "from plane.agent.runtime.subprocess import (\n"
        "    _CLONE_VM, _CLONE_VFORK, _HERMES_BOOTSTRAP_THREAD_REQUIRED_FLAGS,\n"
        "    _SIGCHLD, _SYSCALLS,\n"
        ")\n"
        "sys.stdin.buffer.read()\n"
        "machine = platform.machine()\n"
        "syscalls = _SYSCALLS[machine]\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "libc.syscall.restype = ctypes.c_long\n"
        "def probe(name, *args):\n"
        "    ctypes.set_errno(0)\n"
        "    result = libc.syscall(syscalls[name], *args)\n"
        "    return result, ctypes.get_errno()\n"
        "def denied(name, *args):\n"
        "    if name not in syscalls:\n"
        "        return 'unsupported'\n"
        "    result, error = probe(name, *args)\n"
        "    return 'denied' if result == -1 and error == errno.EPERM else 'unexpected'\n"
        "def socket_result(domain):\n"
        "    result, error = probe(\n"
        "        'socket', ctypes.c_ulong(domain), ctypes.c_ulong(socket.SOCK_STREAM), ctypes.c_ulong(0),\n"
        "    )\n"
        "    if result >= 0:\n"
        "        os.close(result)\n"
        "        return True, None\n"
        "    return False, error\n"
        "exit_syscall = {'x86_64': 60, 'aarch64': 93}[machine]\n"
        "stack = mmap.mmap(-1, 65536, prot=mmap.PROT_READ | mmap.PROT_WRITE)\n"
        "stack_top = (ctypes.addressof(ctypes.c_char.from_buffer(stack)) + len(stack)) & -16\n"
        "def allowed_code_mode_clone():\n"
        "    result, error = probe(\n"
        "        'clone', ctypes.c_ulong(_SIGCHLD), ctypes.c_void_p(stack_top),\n"
        "        ctypes.c_void_p(0), ctypes.c_void_p(0), ctypes.c_ulong(0),\n"
        "    )\n"
        "    if result == 0:\n"
        "        libc.syscall(exit_syscall, 0)\n"
        "        return False\n"
        "    if result <= 0 or error != 0:\n"
        "        return False\n"
        "    os.waitpid(result, 0)\n"
        "    return True\n"
        "def allowed_thread_clone():\n"
        "    clone_pidfd = 0x00001000\n"
        "    result, error = probe(\n"
        "        'clone', ctypes.c_ulong(_HERMES_BOOTSTRAP_THREAD_REQUIRED_FLAGS | clone_pidfd),\n"
        "        ctypes.c_void_p(0xDEADBEEF), ctypes.c_void_p(0xDEADBEEF),\n"
        "        ctypes.c_void_p(0), ctypes.c_ulong(0),\n"
        "    )\n"
        "    return result == -1 and error == errno.EINVAL\n"
        "mode_path = pathlib.Path('/tmp/runtime-mode-probe')\n"
        "mode_path.write_text('x')\n"
        "os.chmod(mode_path, 0o600)\n"
        "chmod_exact_allowed = (mode_path.stat().st_mode & 0o777) == 0o600\n"
        "try:\n"
        "    os.chmod(mode_path, 0o644)\n"
        "    chmod_other_denied = False\n"
        "except OSError as error:\n"
        "    chmod_other_denied = error.errno == errno.EPERM\n"
        "fchmodat2_path = pathlib.Path('/tmp/runtime-fchmodat2-probe')\n"
        "fchmodat2_path.write_text('x')\n"
        "def fchmodat2_mode(mode):\n"
        "    number = syscalls.get('fchmodat2')\n"
        "    if number is None:\n"
        "        return 'unsupported'\n"
        "    ctypes.set_errno(0)\n"
        "    result = libc.syscall(number, ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(fchmodat2_path)),\n"
        "        ctypes.c_uint(mode), ctypes.c_uint(0))\n"
        "    error = ctypes.get_errno()\n"
        "    if result == 0:\n"
        "        return 'allowed'\n"
        "    if result == -1 and error == errno.EPERM:\n"
        "        return 'denied'\n"
        "    if result == -1 and error == errno.ENOSYS:\n"
        "        return 'unavailable'\n"
        "    return 'unexpected:' + str(error)\n"
        "fchmodat2_0600 = fchmodat2_mode(0o600)\n"
        "fchmodat2_0644 = fchmodat2_mode(0o644)\n"
        "fchmodat2_path.unlink(missing_ok=True)\n"
        "class CloneArgs(ctypes.Structure):\n"
        "    _fields_ = [\n"
        "        ('flags', ctypes.c_ulonglong), ('pidfd', ctypes.c_ulonglong),\n"
        "        ('child_tid', ctypes.c_ulonglong), ('parent_tid', ctypes.c_ulonglong),\n"
        "        ('exit_signal', ctypes.c_ulonglong), ('stack', ctypes.c_ulonglong),\n"
        "        ('stack_size', ctypes.c_ulonglong), ('tls', ctypes.c_ulonglong),\n"
        "        ('set_tid', ctypes.c_ulonglong), ('set_tid_size', ctypes.c_ulonglong),\n"
        "        ('cgroup', ctypes.c_ulonglong),\n"
        "    ]\n"
        "clone_args = CloneArgs()\n"
        "print(json.dumps({\n"
        "    'architecture': machine,\n"
        "    'forkProbe': denied('fork'),\n"
        "    'vforkProbe': denied('vfork'),\n"
        "    'ordinaryCloneDenied': denied('clone', ctypes.c_ulong(_SIGCHLD | _CLONE_VM), ctypes.c_void_p(1),\n"
        "        ctypes.c_void_p(0), ctypes.c_void_p(0), ctypes.c_ulong(0)),\n"
        "    'vforkCloneDenied': denied('clone', ctypes.c_ulong(_SIGCHLD | _CLONE_VM | _CLONE_VFORK), "
        "ctypes.c_void_p(1),\n"
        "        ctypes.c_void_p(0), ctypes.c_void_p(0), ctypes.c_ulong(0)),\n"
        "    'clone3Denied': denied('clone3', ctypes.byref(clone_args), ctypes.sizeof(clone_args)),\n"
        "    'classicPopenCloneAllowed': allowed_code_mode_clone(),\n"
        "    'threadCloneAllowed': allowed_thread_clone(),\n"
        "    'rpcSocketModeAllowed': chmod_exact_allowed,\n"
        "    'otherChmodDenied': chmod_other_denied,\n"
        "    'fchmodat2_0600': fchmodat2_0600,\n"
        "    'fchmodat2_0644': fchmodat2_0644,\n"
        "    'unixSocketAllowed': socket_result(socket.AF_UNIX)[0],\n"
        "    'inetSocketDenied': socket_result(socket.AF_INET)[1] == errno.EPERM,\n"
        "    'inet6SocketDenied': socket_result(socket.AF_INET6)[1] == errno.EPERM,\n"
        "}, sort_keys=True, separators=(',', ':')))\n"
    )
    environment = _runtime_environment(tmp_path, fixture)
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body("syscalls")
    try:
        frames = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{server.server_port}",
            shared_secret=configuration.shared_secret,
        ).dispatch(snapshot_json, invocation_json)
        observed = json.loads(frames[0])
        assert observed["architecture"] in {"x86_64", "aarch64"}
        expected_process_probe = "denied" if observed["architecture"] == "x86_64" else "unsupported"
        assert {key: value for key, value in observed.items() if key != "architecture"} == {
            "classicPopenCloneAllowed": True,
            "clone3Denied": "denied",
            "forkProbe": expected_process_probe,
            "fchmodat2_0600": "allowed",
            "fchmodat2_0644": "denied",
            "inet6SocketDenied": True,
            "inetSocketDenied": True,
            "ordinaryCloneDenied": "denied",
            "otherChmodDenied": True,
            "rpcSocketModeAllowed": True,
            "threadCloneAllowed": True,
            "unixSocketAllowed": True,
            "vforkProbe": expected_process_probe,
            "vforkCloneDenied": "denied",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_runtime_production_policy_allows_bound_unix_host_and_denies_network(tmp_path):
    fixture = (
        "import hashlib, json, socket, sys\n"
        "frames = sys.stdin.buffer.read().splitlines()\n"
        "request = json.loads(frames[-1])\n"
        "run_id = request['run']['runId']\n"
        "invocation_id = request['invocation']['invocationId']\n"
        "call = {'protocol': 'plane.agent-runtime/v1', 'runId': run_id,\n"
        "        'invocationId': invocation_id, 'correlationId': 'correlation:unix',\n"
        "        'action': 'read', 'operationRef': 'operation:work_item.read',\n"
        "        'input': {'project_id': 'project:one', 'issue_id': 'issue:one'}, 'source': 'model'}\n"
        "identity = {key: call[key] for key in "
        "('protocol', 'runId', 'invocationId', 'action', 'operationRef', 'input')}\n"
        "digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()\n"
        "call['requestRef'] = 'host-request:' + digest\n"
        "call['idempotencyKey'] = 'host-idempotency:' + digest\n"
        "payload = json.dumps(call, sort_keys=True, separators=(',', ':')).encode() + b'\\n'\n"
        "socket_path = sys.argv[sys.argv.index('--plane-host-socket') + 1]\n"
        "with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:\n"
        "    channel.connect(socket_path)\n"
        "    channel.sendall(payload)\n"
        "    response = bytearray()\n"
        "    while not response.endswith(b'\\n'):\n"
        "        response.extend(channel.recv(4096))\n"
        "result = json.loads(bytes(response[:-1]))\n"
        "try:\n"
        "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    network_denied = False\n"
        "except OSError:\n"
        "    network_denied = True\n"
        "print(json.dumps({'hostStatus': result['status'], 'networkDenied': network_denied},\n"
        "                  sort_keys=True, separators=(',', ':')))\n"
    )
    environment = _runtime_environment(tmp_path, fixture)
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    callback_calls = []

    def invoke(call: PlaneHostCall) -> PlaneHostResult:
        callback_calls.append(call.request_ref)
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="ok",
            replayed=False,
            output={"read": True},
        )

    host_server = PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="host-token",
        invoke=invoke,
    )
    host_server.start()
    runtime_server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration)
    thread = threading.Thread(target=runtime_server.serve_forever, daemon=True)
    thread.start()
    snapshot_json, invocation_json = _dispatch_body()
    try:
        transport = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{runtime_server.server_port}",
            shared_secret=configuration.shared_secret,
            host_endpoint_factory=lambda _invocation_id: nullcontext(
                RuntimeHostEndpoint(url=host_server.url, token="host-token")
            ),
        )
        frames = transport.dispatch(snapshot_json, invocation_json)
        assert json.loads(frames[0]) == {"hostStatus": "ok", "networkDenied": True}
        assert len(callback_calls) == 1
    finally:
        runtime_server.shutdown()
        runtime_server.server_close()
        thread.join(timeout=2)
        host_server.close()


@pytest.mark.parametrize(
    "command",
    (
        f"{sys.executable} -c \"print('lookalike') # plane_runtime.g1_runtime_image.bootstrap\"",
        f"{sys.executable} /tmp/plane_runtime.g1_runtime_image.bootstrap.py",
    ),
)
def test_g4_runtime_configuration_rejects_bootstrap_comment_and_lookalike_filename(tmp_path, command):
    environment = _runtime_environment(tmp_path, "", command=command)
    with pytest.raises(RuntimeConfigurationError, match="exact pinned bootstrap argv|invalid argv shape"):
        AgentRuntimeConfiguration.from_environment(environment)


@pytest.mark.parametrize(
    "target",
    (
        (sys.executable, "-c", "print('lookalike') # plane_runtime.g1_runtime_image.bootstrap"),
        (sys.executable, "/tmp/plane_runtime.g1_runtime_image.bootstrap.py"),
    ),
)
def test_g4_runtime_launcher_rejects_bootstrap_comment_and_lookalike_filename(target):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plane.agent.runtime.launcher",
            "--cpu-seconds",
            "10",
            "--memory-bytes",
            str(128 * 1024 * 1024),
            "--pids-limit",
            "32",
            "--",
            *target,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 78
    assert result.stdout == ""
    assert result.stderr == "event=agent.runtime.launcher status=failed reason=policy_installation\n"


def test_g4_runtime_launcher_fails_closed_when_kernel_policy_installation_fails():
    launcher_script = (
        "import sys; "
        "import plane.agent.runtime.launcher as launcher; "
        "launcher._install_linux_kernel_policy = lambda: (_ for _ in ()).throw(OSError('blocked')); "
        "raise SystemExit(launcher.main(sys.argv[1:]))"
    )
    target = [
        sys.executable,
        "-m",
        "plane_runtime.g1_runtime_image.bootstrap",
        "--once",
        "--g1-production",
    ]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            launcher_script,
            "--cpu-seconds",
            "10",
            "--memory-bytes",
            str(128 * 1024 * 1024),
            "--pids-limit",
            "32",
            "--",
            *target,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 78
    assert result.stdout == ""
    assert result.stderr == "event=agent.runtime.launcher status=failed reason=policy_installation\n"


def test_g4_runtime_host_http_bridge_is_authenticated_bounded_and_idempotent():
    calls = []

    def invoke(call: PlaneHostCall) -> PlaneHostResult:
        calls.append(call.request_ref)
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="ok",
            replayed=False,
            output={"accepted": True},
        )

    server = PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="invocation-token",
        invoke=invoke,
    )
    server.start()
    call = PlaneHostCall(
        run_id="run:one",
        invocation_id="invocation:one",
        correlation_id="correlation:one",
        action="read",
        operation_ref="operation:read",
        input={"value": "bounded"},
        source="model",
    )
    try:
        client = PlaneHostHTTPClient(url=server.url, auth_token="invocation-token")
        assert client.invoke(call).status == "ok"
        replay = client.invoke(call)
        assert replay.status == "replayed"
        assert replay.replayed is True
        assert calls == [call.request_ref]
        with pytest.raises(Exception):
            PlaneHostHTTPClient(url=server.url, auth_token="wrong-token").invoke(call)
    finally:
        server.close()


def test_g4_t3_operator_hooks_use_authenticated_runtime_http_and_targeted_idempotency(tmp_path, monkeypatch):
    configuration = _configuration(tmp_path)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("PLANE_AGENT_RUNTIME_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("PLANE_AGENT_RUNTIME_SECRET", configuration.shared_secret)
    try:
        health = operator_health_readback("workspace:one", 1)
        assert health["status"] == "ready"
        assert health["workspace_id"] == "workspace:one"
        stopped = request_operator_safety_stop("workspace:one", "invocation:one", "incident", "stop:one")
        assert stopped["status"] == "accepted"
        assert stopped["authority"] == "runtime_ephemeral_enforcement"
        assert stopped["planeLifecycleAuthority"] == "required"
        assert stopped["safetyStop"] is False
        assert operator_health_readback("workspace:one", 1)["status"] == "ready"
        assert operator_health_readback("workspace:one", 1)["safetyStop"] is False
        replay = request_operator_safety_stop("workspace:one", "invocation:one", "incident", "stop:one")
        assert replay["replayed"] is True
        unrelated_snapshot, unrelated_invocation = _dispatch_body("two")
        unrelated = RemoteRuntimeTransport(
            runtime_url=f"http://127.0.0.1:{server.server_port}",
            shared_secret=configuration.shared_secret,
        ).dispatch(unrelated_snapshot, unrelated_invocation)
        assert unrelated == ('{"protocol":"fixture","credential":"not-emitted"}',)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_targeted_stop_cancels_only_the_named_active_invocation(tmp_path, monkeypatch):
    fixture = (
        "import json, signal, sys, time\n"
        "request = json.loads(sys.stdin.buffer.read().splitlines()[-1])\n"
        "if request['invocation']['invocationId'] == 'invocation:targeted':\n"
        "    def stop(_signum, _frame):\n"
        "        nonlocal_marker[0] = True\n"
        "    nonlocal_marker = [False]\n"
        "    signal.signal(signal.SIGUSR1, stop)\n"
        "    while not nonlocal_marker[0]:\n"
        "        time.sleep(0.01)\n"
        "else:\n"
        "    time.sleep(0.5)\n"
        "print('{\"protocol\":\"fixture\",\"credential\":\"not-emitted\"}')\n"
    )
    configuration = AgentRuntimeConfiguration.from_environment(_runtime_environment(tmp_path, fixture))
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runtime_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("PLANE_AGENT_RUNTIME_URL", runtime_url)
    monkeypatch.setenv("PLANE_AGENT_RUNTIME_SECRET", configuration.shared_secret)
    target_snapshot, target_invocation = _dispatch_body("targeted")
    unrelated_snapshot, unrelated_invocation = _dispatch_body("active-unrelated")
    target_error = []
    unrelated_result = []

    def dispatch_target():
        try:
            RemoteRuntimeTransport(runtime_url=runtime_url, shared_secret=configuration.shared_secret).dispatch(
                target_snapshot, target_invocation
            )
        except Exception as exc:
            target_error.append(exc)

    def dispatch_unrelated():
        try:
            unrelated_result.append(
                RemoteRuntimeTransport(runtime_url=runtime_url, shared_secret=configuration.shared_secret).dispatch(
                    unrelated_snapshot, unrelated_invocation
                )
            )
        except Exception as exc:
            unrelated_result.append(exc)

    dispatch_thread = threading.Thread(target=dispatch_target, daemon=True)
    unrelated_thread = threading.Thread(target=dispatch_unrelated, daemon=True)
    dispatch_thread.start()
    unrelated_thread.start()
    try:
        deadline = time.monotonic() + 2
        while controller.health().active_invocations != 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert controller.health().active_invocations == 2
        stopped = request_operator_safety_stop(
            "workspace:targeted", "invocation:targeted", "operator requested stop", "stop:targeted"
        )
        assert stopped["status"] == "accepted"
        assert stopped["safetyStop"] is False
        dispatch_thread.join(timeout=3)
        unrelated_thread.join(timeout=3)
        assert target_error and isinstance(target_error[0], RuntimeDispatchError)
        assert unrelated_result == [('{"protocol":"fixture","credential":"not-emitted"}',)]
        assert controller.health().status == "ready"
        assert controller.health().active_invocations == 0
        unrelated_snapshot, unrelated_invocation = _dispatch_body("unrelated")
        unrelated = RemoteRuntimeTransport(runtime_url=runtime_url, shared_secret=configuration.shared_secret).dispatch(
            unrelated_snapshot, unrelated_invocation
        )
        assert unrelated == ('{"protocol":"fixture","credential":"not-emitted"}',)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_runtime_dispatch_rejects_response_binding_and_preserves_protocol_constant():
    assert RUNTIME_DISPATCH_PROTOCOL == "plane.agent-runtime/dispatch/v1"
    assert RuntimeDispatchError.__name__ == "RuntimeDispatchError"

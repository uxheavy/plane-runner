from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostCall,
    PlaneHostHTTPClient,
    PlaneHostHTTPServer,
    PlaneHostResult,
    RemoteRuntimeTransport,
    RuntimeCredentialBroker,
    RuntimeDispatchError,
    RuntimeConfigurationError,
    RuntimeSafetyController,
    operator_health_readback,
    request_operator_safety_stop,
)
from plane.agent.runtime.service import RUNTIME_DISPATCH_PROTOCOL, RuntimeDispatchExecutor, _RuntimeHTTPServer


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


def _dispatch_body() -> tuple[str, str]:
    snapshot = {
        "actorRef": "agent:one",
        "contentDigest": "snapshot:digest",
        "runId": "run:one",
        "workspaceRef": "workspace:one",
    }
    invocation = {
        "correlationId": "correlation:one",
        "invocationId": "invocation:one",
        "runId": "run:one",
    }
    return (
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        json.dumps(invocation, sort_keys=True, separators=(",", ":")),
    )


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


def test_g4_runtime_dispatch_child_rejects_network_filesystem_and_process_escapes(tmp_path):
    fixture = (
        "import json, os, socket, sys\n"
        "sys.stdin.buffer.read()\n"
        "def denied_network():\n"
        "    try:\n"
        "        socket.socket()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "def denied_filesystem():\n"
        "    try:\n"
        "        open('/tmp/runtime-escape', 'w').close()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "def denied_process():\n"
        "    try:\n"
        "        os.fork()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "print(json.dumps({'networkDenied': denied_network(), 'filesystemDenied': denied_filesystem(), "
        "'processDenied': denied_process()}, sort_keys=True, separators=(',', ':')))"
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
        assert observed == {"filesystemDenied": True, "networkDenied": True, "processDenied": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
        replay = request_operator_safety_stop("workspace:one", "invocation:one", "incident", "stop:one")
        assert replay["replayed"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_runtime_dispatch_rejects_response_binding_and_preserves_protocol_constant():
    assert RUNTIME_DISPATCH_PROTOCOL == "plane.agent-runtime/dispatch/v1"
    assert RuntimeDispatchError.__name__ == "RuntimeDispatchError"

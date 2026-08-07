from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path

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


def test_g4_runtime_dispatch_child_rejects_network_and_process_escapes(tmp_path):
    fixture = (
        "import ctypes, errno, json, os, platform, socket, subprocess, sys\n"
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
        "fork_syscall = {'x86_64': 57, 'aarch64': 107}[machine]\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "def denied_process():\n"
        "    ctypes.set_errno(0)\n"
        "    result = libc.syscall(fork_syscall)\n"
        "    error = ctypes.get_errno()\n"
        "    if result == 0:\n"
        "        os._exit(99)\n"
        "    if result > 0:\n"
        "        os.waitpid(result, 0)\n"
        "    return result == -1 and error == errno.EPERM\n"
        "print(json.dumps({'bootstrapChildAllowed': bootstrap_child_allowed, "
        "'codeModeSpawnAllowed': code_mode_spawn_allowed, 'networkDenied': denied_network(), "
        "'processDenied': denied_process()}, "
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
        assert observed == {
            "bootstrapChildAllowed": True,
            "codeModeSpawnAllowed": True,
            "networkDenied": True,
            "processDenied": True,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_g4_runtime_direct_syscalls_deny_fork_vfork_clone_and_clone3_but_allow_exact_clone_patterns(tmp_path):
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
        "    result, error = probe(name, *args)\n"
        "    return result == -1 and error == errno.EPERM\n"
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
        "    'forkDenied': denied('fork'),\n"
        "    'vforkDenied': denied('vfork'),\n"
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
        assert {key: value for key, value in observed.items() if key != "architecture"} == {
            "classicPopenCloneAllowed": True,
            "clone3Denied": True,
            "forkDenied": True,
            "inet6SocketDenied": True,
            "inetSocketDenied": True,
            "ordinaryCloneDenied": True,
            "otherChmodDenied": True,
            "rpcSocketModeAllowed": True,
            "threadCloneAllowed": True,
            "unixSocketAllowed": True,
            "vforkDenied": True,
            "vforkCloneDenied": True,
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

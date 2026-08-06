from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def _configured_runtime_image() -> str:
    override = os.environ.get("PLANE_RUNTIME_RED_TEAM_IMAGE")
    if override:
        return override
    root = Path(__file__).resolve().parents[6]
    compose = root / "deployments/cli/community/docker-compose.yml"
    variables = root / "deployments/cli/community/variables.env"
    if not compose.exists() or not variables.exists():
        pytest.fail(
            "external_required: community Compose files are unavailable; actual runtime proof cannot be resolved"
        )
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose), "--env-file", str(variables), "config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail("external_required: Compose could not resolve the configured runtime service")
    try:
        image = json.loads(result.stdout)["services"]["agent-runtime"]["image"]
    except (KeyError, TypeError, ValueError):
        pytest.fail("external_required: resolved Compose config has no agent-runtime image")
    if not isinstance(image, str) or not image:
        pytest.fail("external_required: configured runtime image is empty")
    return image


def _request_body() -> tuple[bytes, str]:
    snapshot = {
        "actorRef": "agent:red-team",
        "contentDigest": "snapshot:red-team",
        "runId": "run:red-team",
        "workspaceRef": "workspace:red-team",
    }
    invocation = {"invocationId": "invocation:red-team", "runId": "run:red-team"}
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    invocation_json = json.dumps(invocation, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        b"plane.agent-runtime/dispatch/v1\n" + snapshot_json.encode() + b"\n" + invocation_json.encode()
    ).hexdigest()
    body = {
        "credentials": {},
        "invocation": invocation,
        "invocationId": invocation["invocationId"],
        "protocol": "plane.agent-runtime/dispatch/v1",
        "requestDigest": digest,
        "runId": snapshot["runId"],
        "snapshot": snapshot,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), digest


def test_g4_runtime_container_red_team_proves_configured_runtime_service_and_child_isolation():
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("external_required: Docker CLI is unavailable; container proof cannot be skipped")
    image = _configured_runtime_image()
    image_result = _docker("image", "inspect", image)
    if image_result.returncode != 0:
        pytest.fail(f"external_required: configured agent-runtime image is unavailable: {image}")

    name = f"plane-agent-runtime-red-team-{uuid.uuid4().hex[:12]}"
    network = f"plane-agent-runtime-red-team-net-{uuid.uuid4().hex[:12]}"
    scratch = Path(tempfile.mkdtemp(prefix=".g4-runtime-red-team-", dir=Path(__file__).resolve().parents[6]))
    secret_path = scratch / "secret"
    module_root = scratch / "runtime-module"
    package = module_root / "plane_runtime" / "g1_runtime_image"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    secret = "disposable-runtime-secret-" + uuid.uuid4().hex
    secret_path.write_text(secret, encoding="utf-8")
    (package / "bootstrap.py").write_text(
        "import json, os, resource, socket, sys\n"
        "sys.stdin.buffer.read()\n"
        "def denied_write():\n"
        "    try:\n"
        "        open('/outside-read-only', 'w').close()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "def denied_network():\n"
        "    try:\n"
        "        socket.create_connection(('1.1.1.1', 80), 0.2).close()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "limits = {name: resource.getrlimit(kind)[0] for name, kind in "
        "(('cpu', resource.RLIMIT_CPU), ('memory', resource.RLIMIT_AS), ('pids', resource.RLIMIT_NPROC))}\n"
        "ambient = any(key.upper().endswith(('SECRET', 'TOKEN', 'PASSWORD', 'API_KEY')) for key in os.environ)\n"
        "print(json.dumps({'codeMode': {'filesystemDenied': denied_write(), 'networkDenied': denied_network()}, "
        "'environmentCredentialsAbsent': not ambient, 'finiteLimits': all(value > 0 for value in limits.values()), "
        "'limits': limits}, sort_keys=True, separators=(',', ':')))\n",
        encoding="utf-8",
    )
    api_root = Path(__file__).resolve().parents[4]
    _docker("network", "create", "--internal", network, check=True)
    peer = f"{name}-host"
    peer_run = _docker(
        "run",
        "-d",
        "--name",
        peer,
        "--network",
        network,
        "--network-alias",
        "plane-host",
        "--read-only",
        "--entrypoint",
        "python3",
        image,
        "-m",
        "http.server",
        "8091",
        "--bind",
        "0.0.0.0",
    )
    if peer_run.returncode != 0:
        _docker("network", "rm", network)
        shutil.rmtree(scratch, ignore_errors=True)
        pytest.fail(f"external_required: internal host fixture could not start: {peer_run.stderr[-512:]}")
    run = _docker(
        "run",
        "-d",
        "--name",
        name,
        "--network",
        network,
        "--network-alias",
        "agent-runtime",
        "--user",
        "65532:65532",
        "--workdir",
        "/code",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "768m",
        "--cpus",
        "1.0",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--tmpfs",
        "/run/plane-agent-runtime:rw,noexec,nosuid,nodev,size=1m",
        "--mount",
        f"type=bind,src={secret_path},dst=/run/secrets/plane_agent_runtime,readonly",
        "--mount",
        f"type=bind,src={module_root},dst=/tmp/plane-runtime-module,readonly",
        "--mount",
        f"type=bind,src={api_root},dst=/code,readonly",
        "-e",
        "PYTHONPATH=/code",
        "-e",
        'PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON={"PYTHONPATH":"/tmp/plane-runtime-module"}',
        "-e",
        "PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080",
        "-e",
        "PLANE_AGENT_RUNTIME_SECRET_FILE=/run/secrets/plane_agent_runtime",
        "-e",
        "PLANE_AGENT_RUNTIME_COMMAND=python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "-e",
        "PLANE_AGENT_RUNTIME_LEDGER_PATH=/run/plane-agent-runtime/dispatch-ledger.sqlite",
        "-e",
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=/run/plane-agent-runtime/safety-stop",
        "-e",
        "PLANE_AGENT_RUNTIME_BIND=0.0.0.0",
        "-e",
        "PLANE_AGENT_RUNTIME_PORT=8080",
        "--entrypoint",
        "python3",
        image,
        "-m",
        "plane.agent.runtime.service",
    )
    if run.returncode != 0:
        _docker("rm", "-f", peer)
        _docker("network", "rm", network)
        shutil.rmtree(scratch, ignore_errors=True)
        pytest.fail(f"external_required: configured runtime service could not start: {run.stderr[-512:]}")
    try:
        inspected = _docker("inspect", name)
        assert inspected.returncode == 0, inspected.stderr
        container = json.loads(inspected.stdout)[0]
        host_config = container["HostConfig"]
        assert host_config["NetworkMode"] == network
        assert host_config["ReadonlyRootfs"] is True
        assert "ALL" in host_config["CapDrop"]
        assert "no-new-privileges:true" in host_config["SecurityOpt"]
        assert host_config["Memory"] == 768 * 1024 * 1024
        assert host_config["NanoCpus"] == 1_000_000_000
        assert host_config["PidsLimit"] == 128
        assert not host_config["PortBindings"]

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            probe = _docker(
                "exec",
                name,
                "python3",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=1)",
            )
            if probe.returncode == 0:
                break
            time.sleep(0.25)
        else:
            logs = _docker("logs", name)
            pytest.fail(f"configured agent-runtime service did not become ready: {logs.stderr[-1024:]}")

        internal = _docker(
            "exec",
            name,
            "python3",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://plane-host:8091', timeout=2)",
        )
        assert internal.returncode == 0, internal.stderr[-512:]
        internet = _docker(
            "exec",
            name,
            "python3",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=1)",
        )
        assert internet.returncode != 0, "internal runtime network unexpectedly reached the public Internet"

        body, digest = _request_body()
        encoded_body = base64.b64encode(body).decode()
        encoded_secret = base64.b64encode(secret.encode()).decode()
        dispatch_code = (
            "import base64,urllib.request; "
            f"body=base64.b64decode('{encoded_body}'); "
            f"token=base64.b64decode('{encoded_secret}').decode(); "
            "request=urllib.request.Request('http://127.0.0.1:8080/v1/runtime/dispatch', data=body, method='POST', "
            "headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}); "
            "print(urllib.request.urlopen(request, timeout=5).read().decode())"
        )
        dispatch = _docker("exec", name, "python3", "-c", dispatch_code)
        assert dispatch.returncode == 0, dispatch.stderr[-512:]
        response = json.loads(dispatch.stdout)
        assert response["requestDigest"] == digest
        assert response["frames"]
        frame = json.loads(response["frames"][0])
        assert frame["codeMode"]["filesystemDenied"] is True
        assert frame["codeMode"]["networkDenied"] is True
        assert frame["environmentCredentialsAbsent"] is True
        assert frame["finiteLimits"] is True
        assert secret not in dispatch.stdout
        assert "plane_agent_runtime" not in dispatch.stdout
    finally:
        _docker("rm", "-f", name)
        _docker("rm", "-f", peer)
        _docker("network", "rm", network)
        shutil.rmtree(scratch, ignore_errors=True)

#!/usr/bin/env python3
"""Run the G4 runtime-container proof from the host Docker boundary."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


EXPECTED_DIGEST = "sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e"


def docker(*args: str, check: bool = False, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def fail(reason: str) -> int:
    print(f"event=agent.g4.runtime-red-team status=failed reason={reason}")
    return 1

def safe_detail(result: subprocess.CompletedProcess[str]) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    detail = lines[-1] if lines else "no_output"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", detail)[:160] or "no_output"


def main() -> int:
    if shutil.which("docker") is None:
        return fail("docker_unavailable")

    image = os.environ.get("PLANE_G4_RUNTIME_IMAGE", "plane-g3-external-client-api-tests:prepared")
    expected_digest = os.environ.get("PLANE_G4_RUNTIME_IMAGE_DIGEST", EXPECTED_DIGEST)
    image_result = docker("image", "inspect", image, "--format", "{{.Id}}")
    if image_result.returncode != 0:
        return fail("prepared_runtime_image_unavailable")
    actual_digest = image_result.stdout.strip()
    if actual_digest != expected_digest:
        return fail("prepared_runtime_image_digest_mismatch")

    name = f"plane-agent-g4-runtime-{uuid.uuid4().hex[:12]}"
    peer = f"{name}-host"
    network = f"plane-agent-g4-runtime-net-{uuid.uuid4().hex[:12]}"
    scratch_parent = Path(os.environ.get("PLANE_G4_RUNTIME_SCRATCH_ROOT", str(Path(__file__).resolve().parents[1])))
    scratch = Path(tempfile.mkdtemp(prefix=".g4-runtime-red-team-", dir=scratch_parent))
    secret_path = scratch / "secret"
    module_root = scratch / "runtime-module"
    api_root = Path(os.environ.get("PLANE_G4_RUNTIME_CODE_ROOT", str(Path(__file__).resolve().parents[1] / "apps" / "api")))
    package = module_root / "plane_runtime" / "g1_runtime_image"
    network_created = False

    try:
        package.mkdir(parents=True)
        (package.parent / "__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "bootstrap.py").write_text(
            "import json, os, socket, sys\n"
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
            "ambient = any(key.upper().endswith(('SECRET', 'TOKEN', 'PASSWORD', 'API_KEY')) for key in os.environ)\n"
            "print(json.dumps({'filesystemDenied': denied_write(), 'networkDenied': denied_network(), "
            "'environmentCredentialsAbsent': not ambient}, sort_keys=True, separators=(',', ':')))\n",
            encoding="utf-8",
        )
        secret = "disposable-runtime-secret-" + uuid.uuid4().hex
        secret_path.write_text(secret, encoding="utf-8")

        created = docker("network", "create", "--internal", network)
        if created.returncode != 0:
            return fail("internal_network_create_failed")
        network_created = True

        peer_result = docker(
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
        if peer_result.returncode != 0:
            return fail("internal_host_fixture_start_failed")

        environment_json = json.dumps(
            {"PYTHONPATH": "/tmp/plane-runtime-module"}, sort_keys=True, separators=(",", ":")
        )
        runtime_result = docker(
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
            f"PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON={environment_json}",
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
        if runtime_result.returncode != 0:
            return fail(f"runtime_service_start_failed_{safe_detail(runtime_result)}")

        inspected = docker("inspect", name)
        if inspected.returncode != 0:
            return fail("runtime_container_inspect_failed")
        host_config = json.loads(inspected.stdout)[0]["HostConfig"]
        if host_config.get("NetworkMode") != network:
            return fail("runtime_network_boundary_mismatch")
        if host_config.get("ReadonlyRootfs") is not True:
            return fail("runtime_rootfs_not_read_only")
        if "ALL" not in host_config.get("CapDrop", []):
            return fail("runtime_capabilities_not_dropped")
        if "no-new-privileges:true" not in host_config.get("SecurityOpt", []):
            return fail("runtime_no_new_privileges_missing")
        if host_config.get("Memory") != 768 * 1024 * 1024:
            return fail("runtime_memory_limit_mismatch")
        if host_config.get("NanoCpus") != 1_000_000_000:
            return fail("runtime_cpu_limit_mismatch")
        if host_config.get("PidsLimit") != 128:
            return fail("runtime_pid_limit_mismatch")
        if host_config.get("PortBindings"):
            return fail("runtime_published_port_detected")

        ready = False
        for _ in range(80):
            probe = docker(
                "exec",
                name,
                "python3",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=1)",
            )
            if probe.returncode == 0:
                ready = True
                break
            time.sleep(0.25)
        if not ready:
            return fail(f"runtime_service_not_ready_{safe_detail(docker('logs', name))}")

        internal = docker(
            "exec",
            name,
            "python3",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://plane-host:8091', timeout=2)",
        )
        if internal.returncode != 0:
            return fail("internal_host_path_unavailable")
        internet = docker(
            "exec",
            name,
            "python3",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=1)",
        )
        if internet.returncode == 0:
            return fail("public_network_escape")

        snapshot_json = json.dumps(
            {
                "actorRef": "agent:red-team",
                "contentDigest": "snapshot:red-team",
                "runId": "run:red-team",
                "workspaceRef": "workspace:red-team",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        invocation_json = json.dumps(
            {"invocationId": "invocation:red-team", "runId": "run:red-team"},
            sort_keys=True,
            separators=(",", ":"),
        )
        request_digest = hashlib.sha256(
            b"plane.agent-runtime/dispatch/v1\n"
            + snapshot_json.encode()
            + b"\n"
            + invocation_json.encode()
        ).hexdigest()
        body = json.dumps(
            {
                "credentials": {},
                "invocation": json.loads(invocation_json),
                "invocationId": "invocation:red-team",
                "protocol": "plane.agent-runtime/dispatch/v1",
                "requestDigest": request_digest,
                "runId": "run:red-team",
                "snapshot": json.loads(snapshot_json),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded_body = base64.b64encode(body).decode()
        encoded_secret = base64.b64encode(secret.encode()).decode()
        dispatch_code = (
            "import base64,json,urllib.request; "
            f"body=base64.b64decode('{encoded_body}'); "
            f"token=base64.b64decode('{encoded_secret}').decode(); "
            "request=urllib.request.Request('http://127.0.0.1:8080/v1/runtime/dispatch', data=body, method='POST', "
            "headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}); "
            "print(urllib.request.urlopen(request, timeout=5).read().decode())"
        )
        dispatch = docker("exec", name, "python3", "-c", dispatch_code, timeout=15)
        if dispatch.returncode != 0:
            return fail("runtime_dispatch_failed")
        if secret in dispatch.stdout or "plane_agent_runtime" in dispatch.stdout:
            return fail("runtime_credential_disclosure")
        response = json.loads(dispatch.stdout)
        if response.get("requestDigest") != request_digest or not response.get("frames"):
            return fail("runtime_dispatch_evidence_incomplete")
        frame = json.loads(response["frames"][0])
        if frame != {
            "environmentCredentialsAbsent": True,
            "filesystemDenied": True,
            "networkDenied": True,
        }:
            return fail("child_isolation_evidence_failed")

        print(
            "event=agent.g4.runtime-red-team status=passed "
            f"image_digest={actual_digest} internal_network=passed child_isolation=passed credential_scan=passed"
        )
        return 0
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return fail("runtime_red_team_probe_error")
    finally:
        docker("rm", "-f", name)
        docker("rm", "-f", peer)
        if network_created:
            docker("network", "rm", network)
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid

import pytest


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def test_g4_runtime_container_red_team_proves_actual_isolation_constraints():
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("external_required: Docker CLI is unavailable; container proof cannot be skipped")
    image = os.environ.get("PLANE_RUNTIME_RED_TEAM_IMAGE", "alpine:3.22")
    image_result = _docker("image", "inspect", image)
    if image_result.returncode != 0:
        pytest.fail(f"external_required: disposable red-team image is unavailable: {image}")
    name = f"plane-agent-runtime-red-team-{uuid.uuid4().hex[:12]}"
    run = _docker(
        "run",
        "-d",
        "--name",
        name,
        "--user",
        "65532:65532",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "128m",
        "--cpus",
        "0.25",
        "--pids-limit",
        "32",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
        image,
        "sh",
        "-c",
        "sleep 60",
    )
    if run.returncode != 0:
        pytest.fail(f"external_required: isolated container could not start: {run.stderr[-512:]}")
    try:
        inspected = _docker("inspect", name)
        assert inspected.returncode == 0, inspected.stderr
        host_config = json.loads(inspected.stdout)[0]["HostConfig"]
        assert host_config["NetworkMode"] == "none"
        assert host_config["ReadonlyRootfs"] is True
        assert "ALL" in host_config["CapDrop"]
        assert "no-new-privileges:true" in host_config["SecurityOpt"]
        assert host_config["Memory"] == 128 * 1024 * 1024
        assert host_config["NanoCpus"] == 250_000_000
        assert host_config["PidsLimit"] == 32

        probes = {
            "filesystem": "! touch /outside-read-only-root",
            "tmpfs": "touch /tmp/allowed && rm /tmp/allowed",
            "network": "! busybox wget -T 1 -O - http://1.1.1.1",
            "environment": (
                "! env | busybox grep -E 'PLANE_AGENT_RUNTIME_SECRET|AWS_SECRET_ACCESS_KEY|DATABASE_URL|PGPASSWORD'"
            ),
            "secret_mount": "! test -e /run/secrets/plane_agent_runtime",
            "capabilities": "busybox grep '^CapEff:[[:space:]]*0000000000000000$' /proc/1/status",
        }
        for probe, command in probes.items():
            result = _docker("exec", name, "sh", "-c", command)
            assert result.returncode == 0, f"{probe} isolation probe failed: {result.stderr[-512:]}"
    finally:
        _docker("rm", "-f", name)

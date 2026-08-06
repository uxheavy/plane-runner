#!/usr/bin/env python3
"""Run the G4 proof against the pinned production runtime image."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


HERMES_COMMIT = "e573a46611e2cb988f1ab43ad34cd8cc3b2cb659"
RESOURCE_LABEL = "com.uxheavy.plane.agent-g4-runtime"


class ProbeFailure(RuntimeError):
    pass


def docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def docker_input(payload: bytes, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], input=payload, capture_output=True, timeout=timeout)
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def require(result: subprocess.CompletedProcess[str], reason: str) -> str:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        sanitized = "_".join(" ".join(detail[-3:] if detail else ["no_output"]).split())[:320]
        raise ProbeFailure(f"{reason}:{sanitized or 'no_output'}")
    return result.stdout.strip()


def request_body() -> tuple[bytes, str]:
    digests = {
        "runSnapshot": "e538fe79ede53e6bb2e307600dbefea507e30b996c002c3dab32d543ca0e36a2",
        "invocationEnvelope": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
        "runtimeEvent": "fcbf67ce71fa90dd9661a8f2a739b8119c59357c8bf01afabf4fe92a13de9425",
        "runtimeExit": "055792eb1bf4931dafe19de456b15037522f0b5e8f6a0d2fedfe0e0d1d1d1c05",
        "runtimeDurableState": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
    }
    # Keep the fixture exactly within the public G1 contract. The deliberate
    # empty credential source makes the real Hermes adapter fail closed after
    # the bootstrap, proving this is not a synthetic child package.
    snapshot = {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": "workspace:red-team",
        "runId": "run:red-team",
        "assignment": {
            "assignmentRef": "assignment:red-team",
            "revision": "1",
            "targetRef": "target:red-team",
            "objective": "exercise the production runtime boundary",
            "acceptanceCriteria": ["the runtime returns bounded evidence"],
        },
        "actorRef": "actor:red-team",
        "profile": {
            "profileRef": "profile-version:red-team",
            "revision": "1",
            "role": "worker",
            "behavioralPrompt": "Return a short final answer.",
        },
        "context": [],
        "toolCatalog": {"catalogDigest": "content:" + "0" * 64, "eagerOperations": []},
        "runtimePolicy": {
            "model": {"provider": "openai", "model": "red-team-model"},
            "adapter": "hermes",
            "isolation": "single-invocation",
            "maxEventPayloadBytes": 16384,
            "maxArtifactBytes": 1048576,
            "maxReceiptBytes": 8192,
        },
        "totalBudget": {"inputTokens": 32, "outputTokens": 32, "durationMs": 30000},
        "contractDigests": digests,
    }
    digest_input = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    snapshot["contentDigest"] = "snapshot:" + hashlib.sha256(digest_input).hexdigest()
    invocation = {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": "invocation:red-team",
        "runSnapshotDigest": snapshot["contentDigest"],
        "trigger": {"kind": "initial"},
        "newContextEventRefs": [],
        "remainingBudget": {"inputTokens": 32, "outputTokens": 32, "durationMs": 30000},
        "lease": {"leaseId": "lease:red-team", "expiresAt": "2099-01-01T00:00:00Z", "renewAfterMs": 1000},
        "cancellationRef": "cancellation:red-team",
        "causationRef": "causation:red-team",
        "correlationId": "correlation:red-team",
        "idempotencyKey": "idempotency:red-team",
    }
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    invocation_json = json.dumps(invocation, sort_keys=True, separators=(",", ":"))
    request_digest = hashlib.sha256(
        b"plane.agent-runtime/dispatch/v1\n" + snapshot_json.encode() + b"\n" + invocation_json.encode()
    ).hexdigest()
    body = {
        "credentials": {},
        "invocation": invocation,
        "invocationId": invocation["invocationId"],
        "protocol": "plane.agent-runtime/dispatch/v1",
        "requestDigest": request_digest,
        "runId": snapshot["runId"],
        "snapshot": snapshot,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), request_digest


def bootstrap_payload(body: bytes) -> bytes:
    value = json.loads(body)
    return (
        json.dumps(
            {"modelCallAllowance": 32, "protocol": "plane.agent-runtime/dispatch-control/v1"},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {"credentials": {}, "protocol": "plane.agent-runtime/credential-control/v1"},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {"invocation": value["invocation"], "run": value["snapshot"]},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def main() -> int:
    if shutil.which("docker") is None:
        print("event=agent.g4.runtime-red-team status=failed reason=docker_unavailable")
        return 1
    image = os.environ.get("PLANE_G4_RUNTIME_IMAGE", "plane-agent-runtime:hermes-e573a466")
    expected_digest = os.environ.get("PLANE_G4_RUNTIME_IMAGE_DIGEST")
    containers: list[str] = []
    network: str | None = None
    scratch: Path | None = None
    cleanup_errors: list[str] = []
    result = 1
    reason = "runtime_red_team_probe_failed"
    try:
        image_data = json.loads(require(docker("image", "inspect", image), "runtime_image_unavailable"))[0]
        actual_digest = image_data["Id"]
        labels = image_data.get("Config", {}).get("Labels", {}) or {}
        if expected_digest and actual_digest != expected_digest:
            raise ProbeFailure("runtime_image_digest_mismatch")
        if labels.get("org.uxheavy.plane.hermes.commit") != HERMES_COMMIT:
            raise ProbeFailure("runtime_image_hermes_provenance_mismatch")
        if labels.get("org.uxheavy.plane.hermes.remote") != "https://github.com/uxheavy/hermes-agent.git":
            raise ProbeFailure("runtime_image_hermes_remote_provenance_mismatch")

        name = f"plane-agent-g4-runtime-{uuid.uuid4().hex[:12]}"
        peer = f"{name}-host"
        network = f"plane-agent-g4-runtime-net-{uuid.uuid4().hex[:12]}"
        label_args = ["--label", f"{RESOURCE_LABEL}=true"]
        role_label = lambda role: ["--label", f"{RESOURCE_LABEL}.role={role}"]
        scratch = Path(
            tempfile.mkdtemp(prefix=".plane-agent-g4-red-team-", dir=Path(__file__).resolve().parents[1])
        )
        secret_path = scratch / "runtime-secret"
        secret = "disposable-runtime-secret-" + uuid.uuid4().hex
        secret_path.write_text(secret, encoding="utf-8")
        require(
            docker("network", "create", "--internal", *label_args, *role_label("network"), network),
            "internal_network_create_failed",
        )
        peer_run = docker(
            "run",
            "-d",
            "--name",
            peer,
            *label_args,
            *role_label("peer"),
            "--network",
            network,
            "--network-alias",
            "plane-host",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--entrypoint",
            "python3",
            image,
            "-m",
            "http.server",
            "8091",
            "--bind",
            "0.0.0.0",
        )
        require(peer_run, "internal_host_fixture_start_failed")
        containers.append(peer)
        runtime_run = docker(
            "run",
            "-d",
            "--name",
            name,
            *label_args,
            *role_label("runtime"),
            "--network",
            network,
            "--network-alias",
            "agent-runtime",
            "--user",
            "65532:65532",
            "--workdir",
            "/opt/hermes",
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
        require(runtime_run, "runtime_service_start_failed")
        containers.append(name)
        inspected = json.loads(require(docker("inspect", name), "runtime_container_inspect_failed"))[0]
        host_config = inspected["HostConfig"]
        mounts = inspected.get("Mounts", [])
        if host_config.get("NetworkMode") != network or host_config.get("ReadonlyRootfs") is not True:
            raise ProbeFailure("runtime_network_or_rootfs_boundary_mismatch")
        if "ALL" not in host_config.get("CapDrop", []) or "no-new-privileges:true" not in host_config.get("SecurityOpt", []):
            raise ProbeFailure("runtime_capability_boundary_mismatch")
        if host_config.get("Memory") != 768 * 1024 * 1024 or host_config.get("NanoCpus") != 1_000_000_000:
            raise ProbeFailure("runtime_resource_boundary_mismatch")
        if host_config.get("PidsLimit") != 128 or host_config.get("PortBindings"):
            raise ProbeFailure("runtime_pid_or_port_boundary_mismatch")
        if any(mount.get("Destination") in {"/code", "/tmp/plane-runtime-module"} for mount in mounts):
            raise ProbeFailure("runtime_source_mount_detected")

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
            raise ProbeFailure("runtime_service_not_ready")
        require(
            docker(
                "exec",
                name,
                "python3",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://plane-host:8091', timeout=2)",
            ),
            "internal_host_path_unavailable",
        )
        if docker(
            "exec", name, "python3", "-c", "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=1)"
        ).returncode == 0:
            raise ProbeFailure("public_network_escape")

        body, _request_digest = request_body()
        dispatch = docker_input(
            bootstrap_payload(body),
            "exec",
            "-i",
            name,
            "python3",
            "-m",
            "plane_runtime.g1_runtime_image.bootstrap",
            "--once",
            "--g1-production",
            timeout=30,
        )
        require(dispatch, "runtime_real_bootstrap_dispatch_failed")
        frames = [json.loads(line) for line in dispatch.stdout.splitlines() if line]
        if not frames or any(frame.get("invocationId") != "invocation:red-team" for frame in frames):
            raise ProbeFailure("runtime_dispatch_evidence_incomplete")
        if secret in dispatch.stdout or "plane_agent_runtime" in dispatch.stdout or secret in (docker("logs", name).stdout):
            raise ProbeFailure("runtime_credential_disclosure")
        result = 0
        reason = "passed"
        print(
            "event=agent.g4.runtime-red-team status=passed "
            f"image_digest={actual_digest} hermes_commit={HERMES_COMMIT} real_bootstrap=passed "
            "internal_network=passed source_mount_scan=passed credential_scan=passed"
        )
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, json.JSONDecodeError, ProbeFailure) as exc:
        reason = str(exc) or reason
    finally:
        for container in reversed(containers):
            removal = docker("rm", "-f", container)
            if removal.returncode != 0:
                cleanup_errors.append(f"container:{container}")
        if network is not None:
            removal = docker("network", "rm", network)
            if removal.returncode != 0:
                cleanup_errors.append(f"network:{network}")
        if scratch is not None:
            try:
                shutil.rmtree(scratch)
            except OSError:
                cleanup_errors.append("scratch")
        leftovers = docker("ps", "-aq", "--filter", f"label={RESOURCE_LABEL}")
        if leftovers.returncode != 0 or leftovers.stdout.strip():
            cleanup_errors.append("labeled_containers_remain")
        leftovers = docker("network", "ls", "-q", "--filter", f"label={RESOURCE_LABEL}")
        if leftovers.returncode != 0 or leftovers.stdout.strip():
            cleanup_errors.append("labeled_networks_remain")
    if cleanup_errors:
        print(
            "event=agent.g4.runtime-red-team status=failed "
            f"reason=cleanup_failed details={','.join(cleanup_errors)}"
        )
        return 1
    if result != 0:
        print(f"event=agent.g4.runtime-red-team status=failed reason={reason}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

import json
import re
import sqlite3
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import plane.agent.runtime.subprocess as runtime_subprocess
from plane.agent.lifecycle import runtime_contract
from plane.agent.runtime import (
    HostBoundSubprocessRuntimeTransport,
    PlaneHostResult,
    RuntimeDispatchError,
    SubprocessRuntimeTransport,
)
from plane.agent.runtime.subprocess import (
    _HERMES_CREDENTIAL_PROTOCOL,
    _HERMES_DISPATCH_PROTOCOL,
    _hermes_bootstrap_payload,
    _hermes_request_payload,
)
from plane.agent.runtime.provider_egress import (
    ProviderRelayDescriptor,
    ProviderRelayPolicy,
)


SNAPSHOT = json.dumps(
    {"actorRef": "actor:test", "runId": "run:test", "workspaceRef": "workspace:test"},
    sort_keys=True,
    separators=(",", ":"),
)
ENVELOPE = json.dumps(
    {"invocationId": "invocation:test", "runId": "run:test"},
    sort_keys=True,
    separators=(",", ":"),
)


def test_hermes_request_projects_verified_plane_contract_digests_without_mutating_plane_records(monkeypatch):
    expected_digests = runtime_contract.contract_digests()
    assert expected_digests["runSnapshot"] == "308101c6a2c9f56e7deb5c6a07c8bc74b59831b92cbbb5b07c5a7eefc21f4947"
    digest_calls = []

    def verified_contract_digests():
        digest_calls.append(True)
        return expected_digests

    monkeypatch.setattr(runtime_contract, "contract_digests", verified_contract_digests)
    snapshot = {
        "actorRef": "actor:test",
        "runId": "run:test",
        "workspaceRef": "workspace:test",
        "runtimePolicy": {
            "model": "deterministic-local",
            "adapter": "openai-compatible",
            "isolation": "process",
            "maxEventPayloadBytes": 8192,
            "maxArtifactBytes": 8192,
            "maxReceiptBytes": 8192,
            "maxCodeModeInputBytes": 4096,
            "maxCodeModeOutputBytes": 4096,
            "maxCodeModeCalls": 4,
        },
        "contractDigests": {"runSnapshot": "plane-authority"},
        "contentDigest": "snapshot:plane-authority",
    }
    envelope = {"invocationId": "invocation:test", "runId": "run:test", "runSnapshotDigest": "snapshot:plane-authority"}

    payload, run_id, invocation_id, _ = _hermes_request_payload(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        json.dumps(envelope, sort_keys=True, separators=(",", ":")),
    )
    projected = json.loads(payload)["run"]
    projected_envelope = json.loads(payload)["invocation"]

    assert (run_id, invocation_id) == ("run:test", "invocation:test")
    assert set(projected["runtimePolicy"]) == {
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
    assert digest_calls == [True]
    assert projected["contractDigests"] == expected_digests
    assert projected_envelope["runSnapshotDigest"] == projected["contentDigest"]
    assert snapshot["runtimePolicy"]["maxCodeModeCalls"] == 4


def test_hermes_request_rejects_unverified_manifest_before_child_launch(monkeypatch):
    def rejected_contract_digests():
        raise runtime_contract.RuntimeContractError("runtime contract manifest digest drifted")

    monkeypatch.setattr(runtime_contract, "contract_digests", rejected_contract_digests)
    snapshot = json.loads(SNAPSHOT)
    snapshot["runtimePolicy"] = {
        "model": "deterministic-local",
        "adapter": "openai-compatible",
        "isolation": "process",
        "maxEventPayloadBytes": 8192,
        "maxArtifactBytes": 8192,
        "maxReceiptBytes": 8192,
    }

    with pytest.raises(RuntimeDispatchError) as raised:
        _hermes_request_payload(json.dumps(snapshot, sort_keys=True, separators=(",", ":")), ENVELOPE)

    assert raised.value.public_failure() == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }


def test_hermes_projection_has_no_handwritten_run_snapshot_digest():
    source = Path(runtime_subprocess.__file__).read_text(encoding="utf-8")

    assert "_HERMES_G1_CONTRACT_DIGESTS" not in source
    assert re.search(r'"runSnapshot"\s*:\s*"[0-9a-f]{64}"', source) is None


def test_hermes_bootstrap_payload_is_bounded_three_frame_private_handoff():
    snapshot = json.dumps(
        {
            "actorRef": "actor:test",
            "contentDigest": "snapshot:test",
            "runId": "run:test",
            "workspaceRef": "workspace:test",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    envelope = json.dumps(
        {
            "correlationId": "correlation:test",
            "invocationId": "invocation:test",
            "remainingBudget": {"outputTokens": 11},
            "runId": "run:test",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    payload, run_id, invocation_id, digest = _hermes_bootstrap_payload(
        snapshot,
        envelope,
        credentials={"api_key": "credential-canary"},
    )
    frames = [json.loads(frame) for frame in payload.decode().splitlines()]

    assert (run_id, invocation_id) == ("run:test", "invocation:test")
    assert len(digest) == 64
    assert len(frames) == 3
    assert frames[0] == {"modelCallAllowance": 11, "protocol": _HERMES_DISPATCH_PROTOCOL}
    assert frames[1] == {"credentials": {"api_key": "credential-canary"}, "protocol": _HERMES_CREDENTIAL_PROTOCOL}
    assert frames[2]["invocation"]["invocationId"] == "invocation:test"
    assert "credential-canary" not in json.dumps(frames[2], sort_keys=True)


def test_hermes_provider_relay_handoff_contains_only_dummy_marker_not_parent_secret(tmp_path):
    descriptor = ProviderRelayDescriptor(tmp_path / "provider.sock", "t" * 40)
    policy = ProviderRelayPolicy(provider="xai", host="api.x.ai", path="/v1/chat/completions", models=("grok-4",))
    payload, _run_id, _invocation_id, _digest = _hermes_bootstrap_payload(
        SNAPSHOT,
        ENVELOPE,
        credentials={"api_key": "parent-provider-secret"},
        provider_relay=(descriptor, policy),
    )
    assert b"parent-provider-secret" not in payload
    assert b'"credentials":{"host":"api.x.ai"' in payload
    assert b'"invocationSocket":"' in payload
    assert b'"path":"/v1/chat/completions"' in payload
    assert b'"provider":"xai"' in payload
    assert b'"relayToken":"' in payload


def _command(source: str, *arguments: str) -> tuple[str, ...]:
    return (sys.executable, "-c", textwrap.dedent(source), *arguments)


def test_subprocess_transport_commits_and_replays_exact_frames(tmp_path):
    counter = tmp_path / "counter"
    command = _command(
        """
        import json
        import pathlib
        import sys

        path = pathlib.Path(sys.argv[1])
        current = int(path.read_text() or "0") if path.exists() else 0
        path.write_text(str(current + 1))
        request = json.load(sys.stdin)
        print(json.dumps({"invocationId": request["invocation"]["invocationId"]}, separators=(",", ":")))
        """,
        str(counter),
    )
    transport = SubprocessRuntimeTransport(command=command, ledger_path=tmp_path / "ledger.sqlite")

    first = transport.dispatch(SNAPSHOT, ENVELOPE)
    replay = transport.dispatch(SNAPSHOT, ENVELOPE)

    assert first == replay == ('{"invocationId":"invocation:test"}',)
    assert counter.read_text() == "1"


def test_host_bound_transport_passes_socket_and_cleans_invocation_endpoint(tmp_path, monkeypatch):
    host_dir = tmp_path / "invocation-host"

    def make_host_dir(*, prefix):
        assert prefix == "plane-host-"
        host_dir.mkdir()
        return str(host_dir)

    monkeypatch.setattr("plane.agent.runtime.subprocess.tempfile.mkdtemp", make_host_dir)

    class FakeRuntimeInvocation:
        objects = SimpleNamespace(get=lambda **kwargs: SimpleNamespace(**kwargs))

    monkeypatch.setattr("plane.db.models.RuntimeInvocation", FakeRuntimeInvocation)

    def fake_host_port(*, invocation, gateway):
        assert gateway == "trusted-gateway"
        assert invocation.invocation_id == "invocation:test"

        def invoke(call):
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="ok",
                replayed=False,
                output={"accepted": True},
            )

        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr("plane.agent.runtime.host_rpc.build_gateway_host_port", fake_host_port)
    command = _command(
        """
        import json
        import hashlib
        import socket
        import sys

        request = json.load(sys.stdin)
        assert sys.argv[1] == "--plane-host-socket"
        call = {
            "protocol": "plane.agent-runtime/v1",
            "runId": request["run"]["runId"],
            "invocationId": request["invocation"]["invocationId"],
            "correlationId": "correlation:transport",
            "action": "read",
            "operationRef": "operation:catalog.describe",
            "input": {"operation_id": "catalog.search"},
            "source": "model",
        }
        identity = {key: call[key] for key in ("protocol", "runId", "invocationId", "action", "operationRef", "input")}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        call["requestRef"] = f"host-request:{digest}"
        call["idempotencyKey"] = f"host-idempotency:{digest}"
        payload = json.dumps({**call}, sort_keys=True, separators=(",", ":")).encode() + b"\\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.connect(sys.argv[2])
            channel.sendall(payload)
            response = bytearray()
            while not response.endswith(b"\\n"):
                response.extend(channel.recv(4096))
        result = json.loads(bytes(response[:-1]))
        print(json.dumps({"hostStatus": result["status"]}, separators=(",", ":")))
        """
    )
    transport = HostBoundSubprocessRuntimeTransport(
        command=command,
        ledger_path=tmp_path / "ledger.sqlite",
        gateway="trusted-gateway",
    )

    assert transport.dispatch(SNAPSHOT, ENVELOPE) == ('{"hostStatus":"ok"}',)
    assert not host_dir.exists()


def test_host_bound_transport_observes_cancellation_before_ledger_claim(tmp_path, monkeypatch):
    class FakeRuntimeInvocation:
        objects = SimpleNamespace(get=lambda **kwargs: SimpleNamespace(**kwargs))

    monkeypatch.setattr("plane.db.models.RuntimeInvocation", FakeRuntimeInvocation)
    transport = HostBoundSubprocessRuntimeTransport(
        command=_command("print('{}')"),
        ledger_path=tmp_path / "ledger.sqlite",
        gateway="trusted-gateway",
        is_cancelled=lambda: True,
    )
    monkeypatch.setattr(
        transport._ledger,
        "claim",
        lambda **kwargs: pytest.fail("a cancelled invocation must not claim the dispatch ledger"),
    )

    with pytest.raises(RuntimeDispatchError, match="cancelled"):
        transport.dispatch(SNAPSHOT, ENVELOPE)


def test_changed_replay_is_denied_without_starting_another_process(tmp_path):
    counter = tmp_path / "counter"
    command = _command(
        """
        import pathlib
        import sys

        path = pathlib.Path(sys.argv[1])
        current = int(path.read_text() or "0") if path.exists() else 0
        path.write_text(str(current + 1))
        print("{}")
        """,
        str(counter),
    )
    transport = SubprocessRuntimeTransport(command=command, ledger_path=tmp_path / "ledger.sqlite")
    transport.dispatch(SNAPSHOT, ENVELOPE)
    changed_snapshot = json.dumps(
        {"actorRef": "actor:changed", "runId": "run:test", "workspaceRef": "workspace:test"},
        sort_keys=True,
        separators=(",", ":"),
    )

    with pytest.raises(RuntimeDispatchError, match="changed runtime replay"):
        transport.dispatch(changed_snapshot, ENVELOPE)
    assert counter.read_text() == "1"


def test_timeout_marks_outcome_unknown_and_never_blindly_replays(tmp_path):
    command = _command(
        """
        import time
        time.sleep(1)
        """
    )
    transport = SubprocessRuntimeTransport(
        command=command,
        ledger_path=tmp_path / "ledger.sqlite",
        timeout_seconds=0.05,
    )

    with pytest.raises(RuntimeDispatchError, match="durable terminal result"):
        transport.dispatch(SNAPSHOT, ENVELOPE)
    with pytest.raises(RuntimeDispatchError, match="outcome is unknown"):
        transport.dispatch(SNAPSHOT, ENVELOPE)


def test_durable_cancellation_sends_sigusr1_before_forced_termination(tmp_path):
    command = _command(
        """
        import signal
        import sys
        import time

        def cancel(_signum, _frame):
            print('{}', flush=True)
            raise SystemExit(0)

        signal.signal(signal.SIGUSR1, cancel)
        time.sleep(5)
        """
    )
    started = time.monotonic()
    transport = SubprocessRuntimeTransport(
        command=command,
        ledger_path=tmp_path / "ledger.sqlite",
        timeout_seconds=5,
        is_cancelled=lambda: time.monotonic() - started > 0.05,
    )

    assert transport.dispatch(SNAPSHOT, ENVELOPE) == ("{}",)
    assert time.monotonic() - started < 1.0


def test_diagnostics_are_bounded_and_never_persisted(tmp_path):
    canary = "runtime-secret-canary"
    command = _command(
        """
        import sys
        sys.stderr.write(sys.argv[1])
        sys.exit(1)
        """,
        canary,
    )
    ledger = tmp_path / "ledger.sqlite"
    transport = SubprocessRuntimeTransport(
        command=command,
        ledger_path=ledger,
        max_diagnostics_bytes=32,
    )

    with pytest.raises(RuntimeDispatchError) as error:
        transport.dispatch(SNAPSHOT, ENVELOPE)
    assert canary not in str(error.value)
    assert canary not in ledger.read_bytes().decode("utf-8", errors="ignore")

    with sqlite3.connect(ledger) as connection:
        assert connection.execute(
            "SELECT state FROM plane_runtime_dispatch_ledger WHERE invocation_id = ?",
            ("invocation:test",),
        ).fetchone() == ("outcome_unknown",)


def test_launcher_accepts_host_and_provider_relay_socket_arguments():
    from plane.agent.runtime.launcher import _validate_target

    command = [
        "python3",
        "-m",
        "plane_runtime.g1_runtime_image.bootstrap",
        "--once",
        "--g1-production",
        "--plane-host-socket",
        "/run/plane-agent-runtime/host.sock",
        "--provider-relay-socket",
        "/run/plane-agent-runtime/provider.sock",
    ]

    assert _validate_target(command) == tuple(command)


def test_runtime_dispatch_failure_diagnostic_is_allowlisted_and_never_echoes_exception():
    secret = "authorization=secret-token transcript=/private/secret"
    error = RuntimeDispatchError(
        secret,
        failure_code="runtime_process_failed",
        failure_phase="launcher",
        failure_detail="bootstrap_argv_rejected",
    )

    assert error.public_failure() == {
        "failureCode": "runtime_process_failed",
        "failurePhase": "launcher",
        "failureDetail": "bootstrap_argv_rejected",
    }
    assert secret not in json.dumps(error.public_failure(), sort_keys=True)


def test_unclassified_runtime_dispatch_failure_is_not_allowlisted_and_is_scrubbed():
    secret = "authorization=secret-token transcript=/private/secret"
    error = RuntimeDispatchError(secret)

    assert error.has_allowlisted_failure is False
    assert error.public_failure() == {
        "failureCode": "runtime_transport_pre_dispatch_failure",
        "failurePhase": "runtime_transport",
        "failureDetail": "unclassified_exception",
    }
    assert secret not in json.dumps(error.public_failure(), sort_keys=True)

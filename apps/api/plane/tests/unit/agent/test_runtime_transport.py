import json
import sqlite3
import sys
import textwrap
from types import SimpleNamespace

import pytest

from plane.agent.runtime import (
    HostBoundSubprocessRuntimeTransport,
    PlaneHostResult,
    RuntimeDispatchError,
    SubprocessRuntimeTransport,
)
from plane.agent.runtime.subprocess import _HERMES_G1_CONTRACT_DIGESTS, _hermes_request_payload


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


def test_hermes_request_projects_plane_code_mode_policy_without_mutating_plane_records():
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
    }
    assert projected["contractDigests"] == _HERMES_G1_CONTRACT_DIGESTS
    assert projected_envelope["runSnapshotDigest"] == projected["contentDigest"]
    assert snapshot["runtimePolicy"]["maxCodeModeCalls"] == 4


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

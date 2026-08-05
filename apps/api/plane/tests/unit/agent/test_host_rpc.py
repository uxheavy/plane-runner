import json
import socket
import threading

import pytest

from plane.agent.runtime.host_rpc import (
    HOST_PROTOCOL,
    PlaneHostCall,
    PlaneHostRPCError,
    PlaneHostResult,
    PlaneHostServer,
)


def _call(**overrides):
    value = {
        "protocol": HOST_PROTOCOL,
        "runId": "run:test",
        "invocationId": "invocation:test",
        "correlationId": "correlation:test",
        "action": "read",
        "operationRef": "operation:catalog.search",
        "input": {"query": "issue"},
        "source": "model",
    }
    value.update(overrides)
    return PlaneHostCall(
        run_id=value["runId"],
        invocation_id=value["invocationId"],
        correlation_id=value["correlationId"],
        action=value["action"],
        operation_ref=value["operationRef"],
        input=value["input"],
        source=value["source"],
        request_ref=value.get("requestRef") or "",
        idempotency_key=value.get("idempotencyKey") or "",
    )


def _request(call):
    return json.dumps(call.to_wire(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _read_line(connection):
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = connection.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data).decode()


def test_host_call_derives_and_validates_binding_complete_identity():
    call = _call()
    assert call.request_ref.startswith("host-request:")
    assert call.idempotency_key.startswith("host-idempotency:")
    assert PlaneHostCall.from_wire(call.to_wire()) == call

    changed = call.to_wire()
    changed["input"] = {"query": "different"}
    with pytest.raises(PlaneHostRPCError, match="requestRef"):
        PlaneHostCall.from_wire(changed)


def test_host_server_replays_exact_calls_without_reinvoking_the_gateway(tmp_path):
    calls = []

    def invoke(call):
        calls.append(call)
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="ok",
            replayed=False,
            output={"accepted": True},
        )

    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=invoke)
    server.start()
    try:
        call = _call()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(server.socket_path))
            request = _request(call)
            connection.sendall(request)
            first = json.loads(_read_line(connection))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(server.socket_path))
            connection.sendall(request)
            replay = json.loads(_read_line(connection))
        assert first["status"] == "ok"
        assert replay["status"] == "replayed"
        assert replay["replayed"] is True
        assert len(calls) == 1
    finally:
        server.close()
    assert not server.socket_path.exists()


def test_host_server_rejects_noncanonical_or_oversized_frames(tmp_path):
    invoked = threading.Event()
    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=lambda _: invoked.set())
    server.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(server.socket_path))
            connection.sendall(b'{"protocol":"plane.agent-runtime/v1", "bad": 1}\n')
            connection.shutdown(socket.SHUT_WR)
            assert connection.recv(1) == b""
        assert not invoked.is_set()
    finally:
        server.close()


def test_host_server_replays_denials_as_denials(tmp_path):
    calls = []

    def invoke(call):
        calls.append(call)
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="denied",
            replayed=False,
            error_code="NOT_AUTHORIZED",
            error_message="not authorized",
        )

    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=invoke)
    server.start()
    try:
        call = _call()
        request = _request(call)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(server.socket_path))
            connection.sendall(request)
            first = PlaneHostResult.from_wire(_read_line(connection).rstrip("\n"))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(server.socket_path))
            connection.sendall(request)
            replay = PlaneHostResult.from_wire(_read_line(connection).rstrip("\n"))
        assert first.status == replay.status == "denied"
        assert replay.replayed is True
        assert replay.error_code == "NOT_AUTHORIZED"
        assert len(calls) == 1
    finally:
        server.close()

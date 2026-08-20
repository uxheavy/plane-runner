import http.client
import json
import socket
import threading
from types import SimpleNamespace

import pytest

import plane.agent.runtime.host_rpc as host_rpc
from plane.agent.runtime.host_rpc import (
    HOST_PROTOCOL,
    MAX_HOST_RESULT_BYTES,
    PlaneHostCall,
    PlaneHostRPCError,
    PlaneHostResult,
    PlaneHostServer,
    PlaneGatewayHostPort,
)
from plane.agent.code_mode.contracts import CODE_MODE_EXECUTION_OPERATION, CODE_MODE_SCHEMA_VERSION
from plane.operation_gateway.contracts import MAX_RESULT_BYTES


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


def test_host_result_uses_the_canonical_public_result_ceiling():
    assert MAX_HOST_RESULT_BYTES == MAX_RESULT_BYTES == 8 * 1024
    base = {
        "protocol": HOST_PROTOCOL,
        "requestRef": "request:test",
        "correlationId": "correlation:test",
        "idempotencyKey": "idempotency:test",
        "status": "ok",
        "replayed": False,
    }
    prefix_size = len(json.dumps({**base, "output": ""}, sort_keys=True, separators=(",", ":")).encode())
    output = "x" * (MAX_HOST_RESULT_BYTES - prefix_size)
    result = PlaneHostResult(
        request_ref=base["requestRef"],
        correlation_id=base["correlationId"],
        idempotency_key=base["idempotencyKey"],
        status=base["status"],
        replayed=base["replayed"],
        output=output,
    )
    assert len(json.dumps(result.to_wire(), sort_keys=True, separators=(",", ":")).encode()) == MAX_RESULT_BYTES
    with pytest.raises(PlaneHostRPCError, match="exceeds"):
        PlaneHostResult(
            request_ref=base["requestRef"],
            correlation_id=base["correlationId"],
            idempotency_key=base["idempotencyKey"],
            status=base["status"],
            replayed=base["replayed"],
            output=output + "x",
        )


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
            publication={"action": "applied", "productRef": "outcome-submission:test"},
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
        assert first["publication"]["action"] == "applied"
        assert replay["status"] == "replayed"
        assert replay["replayed"] is True
        assert "publication" not in replay
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


def test_http_client_reads_one_byte_past_the_response_limit(monkeypatch):
    call = _call()
    result = PlaneHostResult(
        request_ref=call.request_ref,
        correlation_id=call.correlation_id,
        idempotency_key=call.idempotency_key,
        status="ok",
        replayed=False,
        output={"accepted": True},
    )
    prefix = json.dumps(result.to_wire(), sort_keys=True, separators=(",", ":")).encode()
    limit = len(prefix)
    trailing = prefix + b"x"
    reads = []

    class FakeResponse:
        status = 200

        def read(self, size):
            reads.append(size)
            return trailing[:size]

    class FakeConnection:
        def request(self, *_args, **_kwargs):
            return None

        def getresponse(self):
            return FakeResponse()

        def close(self):
            return None

    monkeypatch.setattr(host_rpc, "MAX_HOST_HTTP_RESPONSE_BYTES", limit)
    monkeypatch.setattr(http.client, "HTTPConnection", lambda *_args, **_kwargs: FakeConnection())

    with pytest.raises(PlaneHostRPCError, match="rejected"):
        host_rpc.PlaneHostHTTPClient(url="http://host.test", auth_token="token").invoke(call)
    assert reads == [limit + 1]


def test_code_mode_observation_limit_is_a_bounded_host_error():
    class ObservationLimitError(RuntimeError):
        code = "OBSERVATION_LIMIT"

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *args, **kwargs):
            return {}

        def execute_typescript(self, request):
            raise ObservationLimitError("too many observations")

    call = _call(
        action="code",
        operationRef=CODE_MODE_EXECUTION_OPERATION,
        source="code",
        input={
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "entrypoint": "default",
            "source": "export default () => 1",
            "input": {},
        },
    )

    result = PlaneGatewayHostPort(FakeHost()).invoke(call)

    assert result.status == "unavailable", result
    assert result.error_code == "OBSERVATION_LIMIT"
    assert result.error_message == "Code Mode observation budget is exhausted."


def test_model_code_mode_failure_is_recoverable_before_corrected_module():
    class ModelModuleFailure(RuntimeError):
        code = "CODE_MODE_FAILED"

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def __init__(self):
            self.calls = 0

        def call_operation(self, *args, **kwargs):
            return {}

        def execute_typescript(self, request):
            self.calls += 1
            if request.source == "malformed-generated-module":
                raise ModelModuleFailure("generated module failed")
            return {"result": {"operationId": "work_item.rename"}}

    host = FakeHost()
    port = PlaneGatewayHostPort(host)
    first = port.invoke(
        _call(
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "malformed-generated-module",
                "input": {},
            },
        )
    )
    second = port.invoke(
        _call(
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "export default async function ({host}: {host: any}) { return 1; }",
                "input": {},
            },
        )
    )

    assert first.status == "invalid"
    assert first.error_code == "CODE_MODE_FAILED"
    assert second.status == "ok"
    assert second.output == {"result": {"operationId": "work_item.rename"}}
    assert host.calls == 2

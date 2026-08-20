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
    PreparedCallRegistry,
)
from plane.agent.code_mode.contracts import CODE_MODE_EXECUTION_OPERATION, CODE_MODE_SCHEMA_VERSION
from plane.agent.code_mode.host import CodeModeHostRPC
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


@pytest.mark.parametrize(
    ("input_value", "accepted_form"),
    [
        ({"preparedCallRef": "prepared-call:opaque"}, "canonical_ref"),
        (
            {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
            },
            "ready_to_call",
        ),
    ],
)
def test_prepared_shape_diagnostic_classifies_existing_forms(input_value, accepted_form):
    diagnostic = host_rpc._prepared_shape_diagnostic(input_value, "malformed")

    assert diagnostic["schemaVersion"] == "plane.prepared-call-shape/v1"
    assert diagnostic["acceptedForm"] == accepted_form
    assert diagnostic["failureClass"] == "malformed"
    assert diagnostic["shape"]["valueTypes"]
    assert diagnostic["shape"]["sizeClass"] in {"small", "medium", "large"}
    assert "prepared-call:opaque" not in json.dumps(diagnostic)


def test_prepared_shape_diagnostic_does_not_call_nested_ref_canonical():
    diagnostic = host_rpc._prepared_shape_diagnostic(
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
            }
        },
        "malformed",
    )

    assert diagnostic["acceptedForm"] == "unrecognized"
    assert diagnostic["failureClass"] == "malformed"
    assert "prepared-call:opaque" not in json.dumps(diagnostic)


@pytest.mark.parametrize(
    ("input_value", "failure_class", "accepted_form"),
    [
        ({"preparedCallRef": "prepared-call:unknown"}, "unknown", "canonical_ref"),
        (
            {"preparedCallRef": "prepared-call:opaque", "issue_id": "raw-id"},
            "malformed",
            "unrecognized",
        ),
        ({"preparedCallRef": "prepared-call:opaque"}, "digest_mismatch", "canonical_ref"),
        ({"preparedCallRef": "prepared-call:opaque"}, "binding_mismatch", "canonical_ref"),
    ],
)
def test_prepared_shape_diagnostic_is_finite_and_redacted(
    input_value, failure_class, accepted_form
):
    diagnostic = host_rpc._prepared_shape_diagnostic(input_value, failure_class)
    encoded = json.dumps(diagnostic, sort_keys=True)

    assert diagnostic["failureClass"] == failure_class
    assert diagnostic["acceptedForm"] == accepted_form
    assert "raw-id" not in encoded
    assert "prepared-call:opaque" not in encoded
    assert set(diagnostic) == {"schemaVersion", "acceptedForm", "failureClass", "shape"}
    assert set(diagnostic["shape"]) == {
        "keyNames",
        "keyNamesTruncated",
        "valueTypes",
        "nestingDepth",
        "sizeClass",
    }


def test_prepared_shape_diagnostic_redacts_sensitive_key_names_and_values():
    diagnostic = host_rpc._prepared_shape_diagnostic(
        {
            "api_token": "provider-secret-value",
            "nested": {"password": "another-secret"},
        },
        "malformed",
    )
    encoded = json.dumps(diagnostic, sort_keys=True)

    assert "provider-secret-value" not in encoded
    assert "another-secret" not in encoded
    assert "api_token" not in encoded
    assert "password" not in encoded
    assert diagnostic["shape"]["keyNames"].count("redacted_key") == 1


def test_prepared_shape_diagnostic_redacts_id_shaped_key_names():
    diagnostic = host_rpc._prepared_shape_diagnostic(
        {"550e8400-e29b-41d4-a716-446655440000": "raw-value"},
        "malformed",
    )

    assert diagnostic["shape"]["keyNames"] == ["redacted_key"]
    assert "raw-value" not in json.dumps(diagnostic)


def test_prepared_invalid_host_receipt_carries_only_bounded_diagnostic():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("invalid prepared input must not reach the gateway")

    port = PlaneGatewayHostPort(FakeHost())
    result = port.invoke(
        _call(
            operationRef="operation:work_item.read",
            input={"preparedCallRef": "prepared-call:unknown"},
        )
    )

    assert result.status == "invalid"
    assert result.error_code == "PREPARED_CALL_INVALID"
    assert result.output["shapeDiagnostic"]["failureClass"] == "unknown"
    round_tripped = PlaneHostResult.from_wire(result.to_wire())
    assert round_tripped.output == result.output
    evidence = host_rpc._host_operation_failure_evidence(_call(
        operationRef="operation:work_item.read",
        input={"preparedCallRef": "prepared-call:unknown"},
    ), result)
    assert evidence["preparedCallInvalidReason"] == "unknown"
    assert evidence["shapeDiagnostic"] == result.output["shapeDiagnostic"]
    assert "prepared-call:unknown" not in json.dumps(evidence)


def test_http_host_distinguishes_callback_exception_after_successful_search():
    def invoke(call):
        if call.operation_ref == "operation:work_item.read":
            raise RuntimeError("internal callback details must stay private")
        return PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="ok",
            replayed=False,
            output={"ok": True},
        )

    server = host_rpc.PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="host-token",
        invoke=invoke,
    )
    server.start()
    client = host_rpc.PlaneHostHTTPClient(url=server.url, auth_token="host-token")
    try:
        search = client.invoke(
            _call(
                operationRef="operation:search_workspace",
                input={"query": "assigned", "limit": 1},
            )
        )
        assert search.status == "ok"
        with pytest.raises(PlaneHostRPCError):
            client.invoke(
                _call(
                    operationRef="operation:work_item.read",
                    input={"project_id": "project:test", "issue_id": "issue:test"},
                )
            )
        evidence = server.failure_evidence
        assert evidence is not None
        assert evidence["status"] == "unavailable"
        assert evidence["errorCode"] == "HOST_UNAVAILABLE"
        assert evidence["failureClass"] == "callback_exception"
        assert "internal callback details" not in json.dumps(evidence)
    finally:
        server.close()


def test_http_host_classifies_response_boundary_failure_as_transport(monkeypatch):
    result_holder = {"armed": False}

    def invoke(call):
        result = PlaneHostResult(
            request_ref=call.request_ref,
            correlation_id=call.correlation_id,
            idempotency_key=call.idempotency_key,
            status="ok",
            replayed=False,
            output={"ok": True},
        )
        result_holder["armed"] = True
        return result

    server = host_rpc.PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="host-token",
        invoke=invoke,
    )
    server.start()
    client = host_rpc.PlaneHostHTTPClient(url=server.url, auth_token="host-token")
    original_to_wire = PlaneHostResult.to_wire

    def fail_serialization(self):
        if result_holder["armed"]:
            raise RuntimeError("response details must stay private")
        return original_to_wire(self)

    monkeypatch.setattr(PlaneHostResult, "to_wire", fail_serialization)
    try:
        with pytest.raises(PlaneHostRPCError):
            client.invoke(_call())
        evidence = server.failure_evidence
        assert evidence is not None
        assert evidence["errorCode"] == "HOST_UNAVAILABLE"
        assert evidence["failureClass"] == "transport_unavailable"
        assert "response details" not in json.dumps(evidence)
    finally:
        server.close()


def test_gateway_host_preserves_valid_search_to_prepared_read_handoff():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def set_prepared_call_registry(self, registry):
            self.registry = registry

        def call_operation(self, operation_id, input_data, **_kwargs):
            if operation_id == "search_workspace":
                return {
                    "ok": True,
                    "result": {
                        "results": [
                            {
                                "objectType": "work_item",
                                "workItemReadInput": {
                                    "project_id": "project:test",
                                    "issue_id": "issue:test",
                                },
                            }
                        ]
                    },
                }
            assert operation_id == "work_item.read"
            assert input_data == {
                "project_id": "project:test",
                "issue_id": "issue:test",
            }
            return {"ok": True, "result": {"work_item": {"name": "assigned"}}}

    port = PlaneGatewayHostPort(FakeHost())
    search = port.invoke(
        _call(
            operationRef="operation:search_workspace",
            input={"query": "assigned", "limit": 1},
        )
    )
    read_call = search.output["result"]["results"][0]["workItemReadCall"]
    read = port.invoke(
        _call(
            operationRef=read_call["operationRef"],
            input=read_call["input"],
        )
    )

    assert search.status == "ok"
    assert read.status == "ok"
    assert read.output["result"]["work_item"]["name"] == "assigned"


def test_code_mode_search_projects_opaque_prepared_read_for_typed_callback():
    """Code Mode must consume the exact search handoff without model reserialization."""

    host = object.__new__(CodeModeHostRPC)
    host._prepared_call_registry = PreparedCallRegistry()
    host._code_mode_active = False
    host._record_code_mode_observation = lambda *_args: None

    def fake_call(operation_id, input_data, **_kwargs):
        if operation_id == "search_workspace":
            return {
                "ok": True,
                "result": {
                    "results": [
                        {
                            "objectType": "work_item",
                            "workItemReadInput": {
                                "project_id": "project:test",
                                "issue_id": "issue:test",
                            },
                        }
                    ]
                },
            }
        if operation_id == "work_item.read":
            assert input_data == {
                "preparedCallRef": read_call["input"]["preparedCallRef"]
            }
            assert host._prepared_call_registry.resolve(
                input_data,
                correlation_id="correlation:read",
                idempotency_key="idempotency:read",
            ) == {
                "project_id": "project:test",
                "issue_id": "issue:test",
            }
            return {"ok": True, "result": {"work_item": {"name": "assigned"}}}
        assert operation_id == "work_item.rename"
        assert input_data == {
            "project_id": "project:test",
            "issue_id": "issue:test",
            "name": "renamed",
        }
        return {"ok": True, "result": {"work_item": {"name": "renamed"}}}

    host._call_operation = fake_call
    search = CodeModeHostRPC.call_operation(
        host,
        "search_workspace",
        {"query": "assigned", "limit": 1},
        idempotency_key="idempotency:search",
        correlation_id="correlation:search",
    )
    item = search["result"]["results"][0]
    read_call = item["workItemReadCall"]

    assert set(read_call["input"]) == {"preparedCallRef"}
    assert "workItemReadInput" not in item
    assert host._prepared_call_registry.resolve(read_call["input"]) == {
        "project_id": "project:test",
        "issue_id": "issue:test",
    }

    read = CodeModeHostRPC.call_operation(
        host,
        "work_item.read",
        read_call["input"],
        idempotency_key="idempotency:read",
        correlation_id="correlation:read",
    )
    assert read["ok"] is True

    rename = CodeModeHostRPC.call_operation(
        host,
        "work_item.rename",
        {
            "project_id": "project:test",
            "issue_id": "issue:test",
            "name": "renamed",
        },
        idempotency_key="idempotency:rename",
        correlation_id="correlation:rename",
    )
    assert rename["ok"] is True


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

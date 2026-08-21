import http.client
import json
import socket
import subprocess
import sys
import threading
import time
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
from plane.agent.code_mode.host import CodeModeHostRPC, _canonicalize_work_item_read_call
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


_PREPARED_BOUNDARY_CHILD = r'''
import hashlib
import json
import socket
import sys

def call(path, operation_ref, payload):
    identity = {
        "protocol": "plane.agent-runtime/v1",
        "runId": "run:cross-process",
        "invocationId": "invocation:cross-process",
        "action": "read",
        "operationRef": operation_ref,
        "input": payload,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    request = {
        **identity,
        "correlationId": "correlation:cross-process",
        "source": "model",
        "requestRef": "host-request:" + digest,
        "idempotencyKey": "host-idempotency:" + digest,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(5)
        channel.connect(path)
        channel.sendall(json.dumps(request, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = channel.recv(4096)
            if not chunk:
                raise RuntimeError(f"host response closed for {operation_ref}")
            response.extend(chunk)
    return json.loads(bytes(response[:-1]))

search = call(
    sys.argv[1],
    "operation:search_workspace",
    {"query": "assigned", "limit": 1},
)
assert search["status"] == "ok", search
prepared_ref = search["output"]["result"]["results"][0]["workItemReadCall"]
read = call(
    sys.argv[1],
    "operation:work_item.read",
    {
        "preparedCallRef": {
            "action": "read",
            "operationRef": "operation:work_item.read",
            "input": {"preparedCallRef": prepared_ref},
        }
    },
)
assert read["status"] == "ok", read
submit = call(
    sys.argv[1],
    "operation:agent.outcome.submit",
    {"preparedCallRef": prepared_ref},
)
assert submit["status"] == "invalid", submit
assert submit["errorCode"] == "PREPARED_CALL_INVALID", submit
'''


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
        (
            {
                "preparedCallRef": json.dumps(
                    {
                        "action": "read",
                        "operationRef": "operation:work_item.read",
                        "input": {"preparedCallRef": "prepared-call:opaque"},
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
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

    assert diagnostic["acceptedForm"] == "ready_to_call"
    assert diagnostic["failureClass"] == "malformed"
    assert diagnostic["shape"]["valueTypes"] == ["object", "string"]
    assert diagnostic["shape"]["nestingDepth"] == 3
    assert "prepared-call:opaque" not in json.dumps(diagnostic)


def test_code_mode_canonicalizes_only_the_typed_work_item_read_call():
    assert _canonicalize_work_item_read_call(
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
            }
        }
    ) == {"preparedCallRef": "prepared-call:opaque"}

    for malformed in (
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
                "extra": True,
            }
        },
        {
            "preparedCallRef": {
                "action": "mutate",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
            }
        },
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": {"preparedCallRef": "prepared-call:opaque"}},
            }
        },
        {"preparedCallRef": "prepared-call:" + ("x" * 256)},
    ):
        with pytest.raises(ValueError):
            _canonicalize_work_item_read_call(malformed)


def test_model_ready_to_call_wrapper_is_unwrapped_before_gateway():
    received = {}

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, operation_id, input_data, **_kwargs):
            received["operation_id"] = operation_id
            received["input"] = input_data
            return {"ok": True, "result": {"work_item": {"name": "assigned"}}}

    port = PlaneGatewayHostPort(FakeHost())
    prepared_ref = port._prepared_call_registry.register(
        {"project_id": "project:test", "issue_id": "issue:test"}
    )
    result = port.invoke(
        _call(
            operationRef="operation:work_item.read",
            input={
                "preparedCallRef": {
                    "action": "read",
                    "operationRef": "operation:work_item.read",
                    "input": {"preparedCallRef": prepared_ref},
                }
            },
        )
    )

    assert result.status == "ok"
    assert received == {
        "operation_id": "work_item.read",
        "input": {"project_id": "project:test", "issue_id": "issue:test"},
    }


@pytest.mark.parametrize(
    "prepared_input",
    [
        {
            "preparedCallRef": {
                "action": "mutate",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
            }
        },
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": "prepared-call:opaque"},
                "extra": True,
            }
        },
        {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": {"preparedCallRef": "prepared-call:opaque"}},
            }
        },
    ],
)
def test_model_prepared_wrapper_rejects_wrong_extra_or_deep_shapes_before_gateway(prepared_input):
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("invalid model wrapper must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(operationRef="operation:work_item.read", input=prepared_input)
    )

    assert result.status == "invalid"
    assert result.error_code == "PREPARED_CALL_INVALID"
    assert result.output["shapeDiagnostic"]["acceptedForm"] == "unrecognized"
    assert "prepared-call:opaque" not in json.dumps(result.output)


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


def test_canonical_prepared_ref_is_rejected_on_non_read_operation():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("prepared input must not reach another operation")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            operationRef="operation:work_item.rename",
            input={"preparedCallRef": "prepared-call:unknown"},
        )
    )

    assert result.status == "invalid"
    assert result.error_code == "PREPARED_CALL_INVALID"
    assert result.prepared_call_invalid_reason == "malformed"


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
        assert evidence["socketPhase"] == "invoke"
        assert evidence["socketState"] == "failed"
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
        assert evidence["socketPhase"] == "serialize"
        assert evidence["socketState"] == "failed"
        assert "response details" not in json.dumps(evidence)
    finally:
        server.close()


def test_unix_host_records_call_less_socket_read_failure_without_raw_details(tmp_path):
    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=lambda _call: pytest.fail("not invoked"))
    server.start()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(str(tmp_path / "host.sock"))
        client.sendall(b"not-canonical-json\n")
    finally:
        client.close()
    for _ in range(50):
        if server.failure_evidence is not None:
            break
        time.sleep(0.01)
    try:
        evidence = server.failure_evidence
        assert evidence == {
            "operationId": "unavailable",
            "attemptRef": "unavailable",
            "receiptRef": "unavailable",
            "status": "unavailable",
            "errorCode": "HOST_UNAVAILABLE",
            "codeModePhase": "unavailable",
            "failureClass": "transport_unavailable",
            "socketPhase": "read",
            "socketState": "failed",
        }
        assert "not-canonical-json" not in json.dumps(evidence)
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
    prepared_ref = search.output["result"]["results"][0]["workItemReadCall"]
    read = port.invoke(
        _call(
            operationRef="operation:work_item.read",
            input={"preparedCallRef": prepared_ref},
        )
    )

    assert search.status == "ok"
    assert read.status == "ok"
    assert read.output["result"]["work_item"]["name"] == "assigned"


@pytest.mark.parametrize(
    "presented_call",
    [
        lambda ref: ref,
        lambda ref: {"preparedCallRef": ref},
        lambda ref: {
            "action": "read",
            "operationRef": "operation:work_item.read",
            "input": {"preparedCallRef": ref},
        },
    ],
)
def test_gateway_host_consumes_one_code_mode_search_ref_before_returning(presented_call):
    calls = []

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def set_prepared_call_registry(self, registry):
            self.registry = registry

        def execute_typescript(self, _request):
            prepared_ref = self.registry.register(
                {"project_id": "project:test", "issue_id": "issue:test"}
            )
            return {
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "result": {
                    "ok": True,
                    "result": {
                        "results": [
                            {"workItemReadCall": presented_call(prepared_ref)}
                        ]
                    },
                },
                "observations": [
                    {
                        "source": "code",
                        "action": "code",
                        "operationRef": "operation:search_workspace",
                        "status": "ok",
                    }
                ],
            }

        def call_operation(self, operation_id, input_data, **_kwargs):
            calls.append((operation_id, input_data))
            assert operation_id == "work_item.read"
            assert input_data == {"project_id": "project:test", "issue_id": "issue:test"}
            return {"ok": True, "result": {"work_item": {"name": "assigned"}}}

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "export default async () => ({})",
                "input": {},
            },
        )
    )

    assert result.status == "ok"
    assert [operation_id for operation_id, _input in calls] == ["work_item.read"]
    assert "workItemReadCall" not in result.output["result"]["result"]["results"][0]
    assert result.output["preparedReadResult"]["status"] == "ok"
    assert (
        result.output["preparedReadResult"]["output"]["result"]["work_item"]["name"]
        == "assigned"
    )


def test_gateway_host_keeps_failed_automatic_prepared_read_pending():
    prepared_refs = []

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def set_prepared_call_registry(self, registry):
            self.registry = registry

        def execute_typescript(self, _request):
            prepared_ref = self.registry.register(
                {"project_id": "project:test", "issue_id": "issue:test"}
            )
            prepared_refs.append(prepared_ref)
            return {
                "result": {
                    "ok": True,
                    "result": {
                        "results": [
                            {"objectType": "work_item", "workItemReadCall": prepared_ref}
                        ]
                    },
                },
                "observations": [
                    {
                        "source": "code",
                        "action": "code",
                        "operationRef": "operation:search_workspace",
                        "status": "ok",
                    }
                ],
            }

        def call_operation(self, operation_id, _input_data, **_kwargs):
            assert operation_id == "work_item.read"
            return {"ok": False, "error": {"code": "PREPARED_CALL_INVALID"}}

    port = PlaneGatewayHostPort(FakeHost())
    result = port.invoke(
        _call(
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "export default async () => ({})",
                "input": {},
            },
        )
    )

    assert result.status == "invalid"
    assert result.prepared_call_invalid_reason is None
    assert result.output["preparedReadResult"]["status"] == "invalid"
    assert result.output["result"]["result"]["results"][0]["workItemReadCall"] == prepared_refs[0]
    assert port._prepared_read_handoff_is_pending() is True


def test_gateway_host_does_not_guess_ambiguous_or_tampered_code_mode_reads():
    calls = []

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")
        mode = "ambiguous"

        def set_prepared_call_registry(self, registry):
            self.registry = registry

        def execute_typescript(self, _request):
            first = self.registry.register(
                {"project_id": "project:test", "issue_id": "issue:first"}
            )
            second = self.registry.register(
                {"project_id": "project:test", "issue_id": "issue:second"}
            )
            refs = (
                (first, second)
                if self.mode == "ambiguous"
                else ("prepared-call:tampered",)
            )
            return {
                "result": {
                    "ok": True,
                    "result": {
                        "results": [
                            {"objectType": "work_item", "workItemReadCall": ref}
                            for ref in refs
                        ]
                    },
                },
                "observations": [
                    {
                        "source": "code",
                        "action": "code",
                        "operationRef": "operation:search_workspace",
                        "status": "ok",
                    }
                ],
            }

        def call_operation(self, *_args, **_kwargs):
            calls.append(True)
            raise AssertionError("ambiguous or tampered prepared reads must not be guessed")

    for mode, expected_status in (("ambiguous", "ok"), ("tampered", "invalid")):
        host = FakeHost()
        host.mode = mode
        port = PlaneGatewayHostPort(host)
        result = port.invoke(
            _call(
                action="code",
                operationRef=CODE_MODE_EXECUTION_OPERATION,
                source="code",
                input={
                    "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                    "entrypoint": "default",
                    "source": "export default async () => ({})",
                    "input": {},
                },
            )
        )
        assert result.status == expected_status
        if mode == "tampered":
            assert result.error_code == "PREPARED_CALL_INVALID"
        else:
            blocked = port.invoke(
                _call(
                    action="read",
                    operationRef="operation:search_workspace",
                    input={"query": "next", "limit": 1},
                )
            )
            assert blocked.status == "invalid"
            assert blocked.error_code == "VALIDATION_ERROR"

    assert calls == []


@pytest.mark.parametrize(
    "presented_call",
    [
        {"preparedCallRef": "prepared-call:unknown", "extra": True},
        {
            "action": "write",
            "operationRef": "operation:work_item.read",
            "input": {"preparedCallRef": "prepared-call:unknown"},
        },
        {"input": {"preparedCallRef": "prepared-call:unknown"}},
        "prepared-call:" + ("x" * (host_rpc.MAX_PREPARED_CALL_REF_BYTES + 1)),
    ],
)
def test_gateway_host_rejects_malformed_code_mode_prepared_read_shapes(presented_call):
    calls = []

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def set_prepared_call_registry(self, registry):
            self.registry = registry

        def execute_typescript(self, _request):
            return {
                "result": {
                    "ok": True,
                    "result": {
                        "results": [
                            {"workItemReadCall": presented_call},
                            {"objectType": "project", "workItemReadCall": "prepared-call:ignored"},
                        ]
                    },
                },
                "observations": [
                    {
                        "source": "code",
                        "action": "code",
                        "operationRef": "operation:search_workspace",
                        "status": "ok",
                    }
                ],
            }

        def call_operation(self, *_args, **_kwargs):
            calls.append(True)
            raise AssertionError("malformed prepared reads must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "export default async () => ({})",
                "input": {},
            },
        )
    )

    assert result.status == "ok"
    assert "preparedReadResult" not in result.output
    assert calls == []


def test_gateway_host_rejects_cross_invocation_code_mode_continuation():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:trusted", invocation_ref="invocation:trusted")

        def execute_typescript(self, _request):
            raise AssertionError("cross-invocation code must not execute")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("cross-invocation code must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            runId="run:other",
            invocationId="invocation:other",
            action="code",
            operationRef=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": "export default async () => ({})",
                "input": {},
            },
        )
    )

    assert result.status == "denied"
    assert result.error_code == "CALLBACK_BINDING_INVALID"


def test_prepared_read_wrapper_is_rejected_without_gateway_call():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("malformed prepared input must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            operationRef="operation:work_item.read",
            input={"input": {"preparedCallRef": "prepared-call:unknown"}},
        )
    )

    assert result.status == "invalid"
    assert result.error_code == "PREPARED_CALL_INVALID"


def test_prepared_read_rejects_non_read_action_before_gateway():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("non-read prepared input must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="mutate",
            operationRef="operation:work_item.read",
            input={"preparedCallRef": "prepared-call:opaque"},
        )
    )

    assert result.status == "invalid"
    assert result.error_code == "VALIDATION_ERROR"


def test_deeper_prepared_read_ref_is_rejected_before_gateway():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, *_args, **_kwargs):
            raise AssertionError("nested prepared input must not reach the gateway")

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            operationRef="operation:work_item.read",
            input={
                "preparedCallRef": {
                    "preparedCallRef": {"preparedCallRef": "prepared-call:opaque"}
                }
            },
        )
    )

    assert result.status == "invalid"
    assert result.error_code == "PREPARED_CALL_INVALID"


def test_outcome_submit_nested_prepared_ref_evidence_is_not_interpreted():
    received = {}

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, operation_id, input_data, **_kwargs):
            received["operation_id"] = operation_id
            received["input"] = input_data
            return {"ok": True, "result": {"outcome": {"outcomeRef": "outcome:test"}}}

    evidence = {"preparedCallRef": {"preparedCallRef": "prepared-call:opaque"}}
    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="mutate",
            operationRef="operation:agent.outcome.submit",
            input={
                "summary": "Nested prepared evidence is ordinary data.",
                "artifacts": [],
                "evidence": [evidence],
            },
        )
    )

    assert result.status == "ok"
    assert received["operation_id"] == "agent.outcome.submit"
    assert received["input"]["evidence"] == [evidence]


def test_outcome_submit_allows_prepared_ref_in_bounded_evidence():
    received = {}

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, operation_id, input_data, **_kwargs):
            received["operation_id"] = operation_id
            received["input"] = input_data
            return {"ok": True, "result": {"outcome": {"outcomeRef": "outcome:test"}}}

    result = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="mutate",
            operationRef="operation:agent.outcome.submit",
            input={
                "summary": "Prepared handoff evidence is retained.",
                "artifacts": [],
                "evidence": [{"preparedCallRef": "prepared-call:opaque"}],
            },
        )
    )

    assert result.status == "ok"
    assert received == {
        "operation_id": "agent.outcome.submit",
        "input": {
            "summary": "Prepared handoff evidence is retained.",
            "artifacts": [],
            "evidence": [{"preparedCallRef": "prepared-call:opaque"}],
        },
    }


def _publication_receipt(*, replayed=False, **changes):
    receipt = {
        "ok": True,
        "replayed": replayed,
        "operationId": "agent.outcome.publish",
        "operationRef": "operation:agent.outcome.publish",
        "runRef": "run:test",
        "invocationRef": "invocation:test",
        "requestId": "request:publish",
        "gatewayReceipt": "gateway:publish",
        "auditReceipt": "audit:publish",
        "result": {
            "published": True,
            "outcome": {
                "outcomeRef": "outcome-submission:test",
                "productEventRef": "product-event:publish",
            },
        },
    }
    receipt.update(changes)
    return receipt


def test_outcome_publication_requires_the_same_fresh_bound_receipt_on_both_paths():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, _operation_id, _input_data, **_kwargs):
            return _publication_receipt()

    trusted = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="publish",
            operationRef="operation:agent.outcome.publish",
            input={"kind": "outcome", "resourceRef": "outcome-submission:test", "content": "published"},
        )
    )
    generic = PlaneGatewayHostPort(FakeHost()).invoke(
        _call(
            action="mutate",
            operationRef="operation:agent.outcome.publish",
            input={"outcome_ref": "outcome-submission:test", "content": "published"},
        )
    )

    assert trusted.status == generic.status == "ok"
    assert trusted.publication == generic.publication
    assert trusted.publication["productRef"] == "outcome-submission:test"


@pytest.mark.parametrize(
    "receipt_override",
    [
        {"operationRef": "operation:agent.outcome.submit"},
        {"runRef": "run:other"},
        {"result": {"published": False}},
        {
            "result": {
                "published": True,
                "outcome": {
                    "outcomeRef": "outcome-submission:other",
                    "productEventRef": "product-event:publish",
                },
            }
        },
        {"gatewayReceipt": "x" * 129},
    ],
)
def test_outcome_publication_rejects_tampered_or_oversized_receipts(receipt_override):
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, _operation_id, _input_data, **_kwargs):
            return _publication_receipt(**receipt_override)

    for action, input_data in (
        ("publish", {"kind": "outcome", "resourceRef": "outcome-submission:test", "content": "published"}),
        ("mutate", {"outcome_ref": "outcome-submission:test", "content": "published"}),
    ):
        result = PlaneGatewayHostPort(FakeHost()).invoke(
            _call(action=action, operationRef="operation:agent.outcome.publish", input=input_data)
        )
        assert result.status == "unavailable"
        assert result.error_code == "OPERATION_UNAVAILABLE"
        assert result.publication is None
        assert len(json.dumps(result.output, separators=(",", ":"))) < 1024


def test_outcome_publication_replay_is_idempotent_without_a_second_publication():
    class FakeHost:
        binding = SimpleNamespace(run_ref="run:test", invocation_ref="invocation:test")

        def call_operation(self, _operation_id, _input_data, **_kwargs):
            return _publication_receipt(replayed=True)

    for action, input_data in (
        ("publish", {"kind": "outcome", "resourceRef": "outcome-submission:test", "content": "published"}),
        ("mutate", {"outcome_ref": "outcome-submission:test", "content": "published"}),
    ):
        result = PlaneGatewayHostPort(FakeHost()).invoke(
            _call(action=action, operationRef="operation:agent.outcome.publish", input=input_data)
        )
        assert result.status == "replayed"
        assert result.publication is None


def test_prepared_call_json_wrapper_crosses_process_and_submit_fails_closed(tmp_path):
    calls = []

    class FakeHost:
        binding = SimpleNamespace(run_ref="run:cross-process", invocation_ref="invocation:cross-process")

        def call_operation(self, operation_id, input_data, **_kwargs):
            calls.append((operation_id, input_data))
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
    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=port.invoke)
    server.start()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _PREPARED_BOUNDARY_CHILD, str(server.socket_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.close()

    assert completed.returncode == 0, completed.stderr
    assert [operation_id for operation_id, _input in calls] == [
        "search_workspace",
        "work_item.read",
    ]


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
                "preparedCallRef": prepared_ref
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
    prepared_ref = item["workItemReadCall"]

    assert isinstance(prepared_ref, str)
    assert prepared_ref.startswith("prepared-call:")
    assert "workItemReadInput" not in item
    assert host._prepared_call_registry.resolve({"preparedCallRef": prepared_ref}) == {
        "project_id": "project:test",
        "issue_id": "issue:test",
    }

    read = CodeModeHostRPC.call_operation(
        host,
        "work_item.read",
        {"preparedCallRef": prepared_ref},
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


def test_code_mode_direct_search_consumes_one_prepared_read_before_returning():
    calls = []
    observations = []
    host = object.__new__(CodeModeHostRPC)
    host._prepared_call_registry = PreparedCallRegistry()
    host._code_mode_active = True
    host._record_code_mode_observation = lambda operation_id, _receipt: observations.append(operation_id)

    def fake_call(operation_id, input_data, **kwargs):
        calls.append((operation_id, input_data, kwargs))
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
        prepared_ref = input_data["preparedCallRef"]
        assert host._prepared_call_registry.resolve(
            {"preparedCallRef": prepared_ref},
            correlation_id=kwargs["correlation_id"],
            idempotency_key=kwargs["idempotency_key"],
        ) == {"project_id": "project:test", "issue_id": "issue:test"}
        return {"ok": True, "result": {"work_item": {"name": "assigned"}}}

    host._call_operation = fake_call
    search = CodeModeHostRPC.call_operation(
        host,
        "search_workspace",
        {"query": "assigned", "limit": 1},
        idempotency_key="idempotency:search",
        correlation_id="correlation:search",
    )

    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "search_workspace",
        "work_item.read",
    ]
    assert "workItemReadCall" not in search["result"]["results"][0]
    assert search["preparedReadResult"]["ok"] is True
    assert search["preparedReadResult"]["result"]["work_item"]["name"] == "assigned"
    assert observations == ["search_workspace", "work_item.read"]
    assert all(record["consumed"] for record in host._prepared_call_registry.records.values())


def test_code_mode_direct_search_leaves_multiple_prepared_reads_pending():
    calls = []
    host = object.__new__(CodeModeHostRPC)
    host._prepared_call_registry = PreparedCallRegistry()
    host._code_mode_active = False
    host._record_code_mode_observation = lambda *_args: None

    def fake_call(operation_id, _input_data, **_kwargs):
        calls.append(operation_id)
        assert operation_id == "search_workspace"
        return {
            "ok": True,
            "result": {
                "results": [
                    {
                        "objectType": "work_item",
                        "workItemReadInput": {
                            "project_id": "project:test",
                            "issue_id": "issue:first",
                        },
                    },
                    {
                        "objectType": "work_item",
                        "workItemReadInput": {
                            "project_id": "project:test",
                            "issue_id": "issue:second",
                        },
                    },
                ]
            },
        }

    host._call_operation = fake_call
    search = CodeModeHostRPC.call_operation(
        host,
        "search_workspace",
        {"query": "assigned", "limit": 2},
        idempotency_key="idempotency:search",
        correlation_id="correlation:search",
    )

    assert calls == ["search_workspace"]
    assert "preparedReadResult" not in search
    assert len(host._prepared_call_registry.records) == 2
    assert all(not record["consumed"] for record in host._prepared_call_registry.records.values())


def _catalog_latch_host(calls, *, source="code_mode", describe_ok=True):
    host = object.__new__(CodeModeHostRPC)
    host.request = SimpleNamespace(source=source)
    host._code_mode_active = True
    host._record_code_mode_observation = lambda *_args: None

    def fake_call(operation_id, input_data, **kwargs):
        calls.append((operation_id, input_data, kwargs))
        if operation_id == "catalog.search":
            return {
                "ok": True,
                "result": {"operations": [{"operationId": "catalog.describe"}]},
                "idempotencyKey": kwargs["idempotency_key"],
                "correlationId": kwargs["correlation_id"],
                "replayed": False,
            }
        if operation_id != "catalog.describe":
            return {
                "ok": True,
                "result": {"accepted": True},
                "idempotencyKey": kwargs["idempotency_key"],
                "correlationId": kwargs["correlation_id"],
                "replayed": False,
            }
        return {
            "ok": describe_ok,
            "result": {"operation": {"operationId": "catalog.search"}} if describe_ok else {},
            "idempotencyKey": kwargs["idempotency_key"],
            "correlationId": kwargs["correlation_id"],
            "replayed": False,
        }

    host._call_operation = fake_call
    return host


def test_code_mode_catalog_search_replays_after_successful_search_and_describe():
    calls = []
    host = _catalog_latch_host(calls)
    assert host.request.source == "code_mode"

    first_search = host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:one", correlation_id="correlation:one"
    )
    described = host.call_operation(
        "catalog.describe",
        {"operation_id": "catalog.search"},
        idempotency_key="describe:one",
        correlation_id="correlation:describe",
    )
    repeated_search = host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:two", correlation_id="correlation:two"
    )

    assert described["ok"] is True
    assert repeated_search["replayed"] is True
    assert repeated_search["result"] == first_search["result"]
    assert repeated_search["idempotencyKey"] == "search:two"
    assert repeated_search["correlationId"] == "correlation:two"
    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "catalog.search",
        "catalog.describe",
    ]


def test_code_mode_catalog_search_before_describe_still_calls_gateway():
    calls = []
    host = _catalog_latch_host(calls)

    host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:one", correlation_id="correlation:one"
    )
    repeated_search = host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:two", correlation_id="correlation:two"
    )

    assert repeated_search["replayed"] is False
    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "catalog.search",
        "catalog.search",
    ]


def test_code_mode_catalog_search_does_not_latch_after_failed_describe():
    calls = []
    host = _catalog_latch_host(calls, describe_ok=False)

    host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:one", correlation_id="correlation:one"
    )
    host.call_operation(
        "catalog.describe",
        {"operation_id": "catalog.search"},
        idempotency_key="describe:one",
        correlation_id="correlation:describe",
    )
    repeated_search = host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:two", correlation_id="correlation:two"
    )

    assert repeated_search["replayed"] is False
    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "catalog.search",
        "catalog.describe",
        "catalog.search",
    ]


def test_code_mode_catalog_search_latch_does_not_intercept_other_operations():
    calls = []
    host = _catalog_latch_host(calls)

    host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:one", correlation_id="correlation:one"
    )
    host.call_operation(
        "catalog.describe",
        {"operation_id": "catalog.search"},
        idempotency_key="describe:one",
        correlation_id="correlation:describe",
    )
    host.call_operation(
        "work_item.rename",
        {"project_id": "project:test", "issue_id": "issue:test", "name": "renamed"},
        idempotency_key="rename:one",
        correlation_id="correlation:rename",
    )

    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "catalog.search",
        "catalog.describe",
        "work_item.rename",
    ]


def test_code_mode_catalog_search_latch_is_inactive_outside_code_mode():
    calls = []
    host = _catalog_latch_host(calls)

    host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:one", correlation_id="correlation:one"
    )
    host.call_operation(
        "catalog.describe",
        {"operation_id": "catalog.search"},
        idempotency_key="describe:one",
        correlation_id="correlation:describe",
    )
    host._code_mode_active = False
    repeated_search = host.call_operation(
        "catalog.search", {"query": ""}, idempotency_key="search:two", correlation_id="correlation:two"
    )

    assert repeated_search["replayed"] is False
    assert [operation_id for operation_id, _input, _kwargs in calls] == [
        "catalog.search",
        "catalog.describe",
        "catalog.search",
    ]


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

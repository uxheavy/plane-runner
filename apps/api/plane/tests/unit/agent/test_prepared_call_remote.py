"""Provider-free remote prepared-call lifecycle regression."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext

import pytest

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostHTTPServer,
    RemoteRuntimeTransport,
    RuntimeCredentialBroker,
    RuntimeHostEndpoint,
    build_gateway_host_port,
)
from plane.agent.runtime.host_rpc import PlaneHostCall
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency
from plane.operation_gateway.gateway import OperationGateway
from plane.tests.unit.agent.test_runtime_supervisor import _invocation


_CHILD = r'''
import hashlib
import json
import socket
import sys

def host(path, run_id, invocation_id, correlation_id, operation_ref, payload):
    call = {
        "protocol": "plane.agent-runtime/v1", "runId": run_id,
        "invocationId": invocation_id, "correlationId": correlation_id,
        "action": "read", "operationRef": operation_ref, "input": payload,
        "source": "model",
    }
    identity = {key: call[key] for key in (
        "protocol", "runId", "invocationId", "action", "operationRef", "input"
    )}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    call["requestRef"] = "host-request:" + digest
    call["idempotencyKey"] = "host-idempotency:" + digest
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.connect(path)
        channel.sendall(json.dumps(call, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        response = bytearray()
        while not response.endswith(b"\n"):
            response.extend(channel.recv(4096))
    return json.loads(bytes(response[:-1]))

request = json.loads(sys.stdin.buffer.read().splitlines()[-1])
run_id = request["run"]["runId"]
invocation = request["invocation"]
invocation_id = invocation["invocationId"]
correlation_id = invocation["correlationId"]
socket_path = sys.argv[sys.argv.index("--plane-host-socket") + 1]
search = host(socket_path, run_id, invocation_id, correlation_id, "operation:search_workspace", {"query": "Gateway Issue", "limit": 1})
assert search["status"] == "ok", search
item = next(item for item in search["output"]["result"]["results"] if item["objectType"] == "work_item")
read_call = item["workItemReadCall"]
assert set(read_call) == {"action", "operationRef", "input"}
assert set(read_call["input"]) == {"preparedCallRef"}
assert "workItemReadInput" not in item

def prepared_read(invocation_ref):
    return host(socket_path, run_id, invocation_ref, correlation_id, read_call["operationRef"], read_call["input"])

first = prepared_read(invocation_id)
assert first["status"] == "ok", first
replay = prepared_read(invocation_id)
assert replay["status"] == "replayed", replay
altered = host(
    socket_path, run_id, invocation_id, correlation_id,
    read_call["operationRef"],
    {"preparedCallRef": read_call["input"]["preparedCallRef"] + "-tampered"},
)
assert altered["status"] == "invalid" and altered["errorCode"] == "PREPARED_CALL_INVALID", altered
cross = prepared_read("invocation:cross")
assert cross["status"] == "denied" and cross["errorCode"] == "CALLBACK_BINDING_INVALID", cross
print(json.dumps({"kind": "completed"}, separators=(",", ":")))
'''


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_remote_runtime_preserves_search_prepared_read_envelope(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults={"provider": "openai", "model": "deterministic-local", "adapter": "hermes"},
        suffix="prepared-remote-regression",
    )
    package = tmp_path / "plane_runtime" / "g1_runtime_image"
    package.mkdir(parents=True)
    (tmp_path / "plane_runtime" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "plane_runtime" / "g1_contract.py").write_text("G1_CONTRACT_DIGESTS = {}\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "bootstrap.py").write_text(_CHILD, encoding="utf-8")

    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": "s" * 40,
        "PLANE_AGENT_RUNTIME_COMMAND": "python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": json.dumps(
            {
                "HOME": str(tmp_path / "runtime-home"),
                "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin",
                "PYTHONPATH": str(tmp_path),
                "PYTHONUNBUFFERED": "1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "prepared-remote-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "prepared-remote-safety-stop"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(tmp_path / "credential-state.json"),
    }
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    host_calls = []
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())

    def invoke(call):
        host_calls.append(call)
        return port.invoke(call)

    host_server = PlaneHostHTTPServer(
        bind_host="127.0.0.1", advertised_host="127.0.0.1", port=0,
        auth_token="host-token", invoke=invoke,
    )
    host_server.start()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        runtime_port = probe.getsockname()[1]

    service_environment = os.environ.copy()
    for key in (
        "PLANE_AGENT_RUNTIME_PROVIDER",
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST",
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH",
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS",
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME",
        "PLANE_AGENT_RUNTIME_PROVIDER_TIMEOUT_SECONDS",
        "PLANE_AGENT_RUNTIME_PROVIDER_MAX_CHUNK_BYTES",
        "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER",
    ):
        service_environment.pop(key, None)
    service_environment.update(environment)
    service_environment.update({
        "PLANE_AGENT_RUNTIME_BIND": "127.0.0.1",
        "PLANE_AGENT_RUNTIME_PORT": str(runtime_port),
        "PYTHONPATH": os.pathsep.join((os.getcwd(), str(tmp_path))),
    })
    service = subprocess.Popen(
        [sys.executable, "-m", "plane.agent.runtime.service"],
        cwd=os.getcwd(), env=service_environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    runtime_url = f"http://127.0.0.1:{runtime_port}"
    try:
        ready = False
        for _ in range(100):
            if service.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"{runtime_url}/health/ready", timeout=0.2) as response:
                    ready = response.status == 200
                    if ready:
                        break
            except (OSError, urllib.error.HTTPError):
                pass
            time.sleep(0.05)
        assert ready, service.stderr.read().decode("utf-8", errors="replace")
        frames = RemoteRuntimeTransport(
            runtime_url=runtime_url,
            shared_secret=configuration.shared_secret,
            credential_broker=RuntimeCredentialBroker(
                {"runtime": {"api_key": "provider-free", "base_url": "http://127.0.0.1:9/v1", "api_mode": "chat_completions"}}
            ),
            host_endpoint_factory=lambda _ref: nullcontext(
                RuntimeHostEndpoint(url=host_server.url, token="host-token")
            ),
        ).dispatch(
                json.dumps(run.snapshot, sort_keys=True, separators=(",", ":")),
                json.dumps(invocation.envelope, sort_keys=True, separators=(",", ":")),
            )
    finally:
        host_server.close()
        if service.poll() is None:
            service.terminate()
        _, stderr = service.communicate(timeout=3)

    assert service.returncode == 0, stderr.decode("utf-8", errors="replace")
    assert json.loads(frames[-1])["kind"] == "completed"
    assert [call.operation_ref for call in host_calls] == [
        "operation:search_workspace",
        "operation:work_item.read",
        "operation:work_item.read",
        "operation:work_item.read",
    ]
    assert OperationGatewayIdempotency.objects.filter(
        operation_id="work_item.read", correlation_id=invocation.envelope["correlationId"]
    ).count() == 1
    assert OperationGatewayAudit.objects.filter(
        operation_id="work_item.read", phase="outcome", outcome="success",
        correlation_id=invocation.envelope["correlationId"],
    ).count() == 1


def _port_call(invocation, *, operation_ref, input_data, correlation_id="correlation:prepared-port"):
    return PlaneHostCall(
        run_id=invocation.run.snapshot["runId"],
        invocation_id=invocation.invocation_id,
        correlation_id=correlation_id,
        action="read",
        operation_ref=operation_ref,
        input=input_data,
        source="model",
    )


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_prepared_port_replay_is_cached_before_gateway(
    workspace, gateway_project, gateway_issue, create_user
):
    _, invocation = _invocation(
        workspace, gateway_project, gateway_issue, create_user, suffix="prepared-port-replay"
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    search = port.invoke(_port_call(
        invocation,
        operation_ref="operation:search_workspace",
        input_data={"query": "Gateway Issue", "limit": 1},
    ))
    item = next(item for item in search.output["result"]["results"] if item["objectType"] == "work_item")
    read_call = item["workItemReadCall"]
    read = _port_call(
        invocation,
        operation_ref=read_call["operationRef"],
        input_data=read_call["input"],
    )
    first = port.invoke(read)
    assert first.status == "ok", first
    gateway_count = OperationGatewayIdempotency.objects.filter(operation_id="work_item.read").count()

    replay = port.invoke(read)
    assert replay.status == "replayed", replay
    assert replay.replayed is True
    assert OperationGatewayIdempotency.objects.filter(operation_id="work_item.read").count() == gateway_count

    altered_correlation = port.invoke(_port_call(
        invocation,
        operation_ref=read_call["operationRef"],
        input_data=read_call["input"],
        correlation_id="correlation:altered",
    ))
    assert altered_correlation.status == "invalid"
    assert altered_correlation.error_code == "PREPARED_CALL_INVALID"

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
from plane.agent.code_mode.host import CodeModeBindingError
from plane.db.models import ProjectMember, WorkspaceMember
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency
from plane.operation_gateway.gateway import OperationGateway
from plane.tests.unit.agent.test_runtime_supervisor import _invocation


_CHILD = r'''
import hashlib
import json
import socket
import sys

def host_idempotency(run_id, invocation_id, action, operation_ref, payload):
    identity = {
        "protocol": "plane.agent-runtime/v1", "runId": run_id,
        "invocationId": invocation_id, "action": action,
        "operationRef": operation_ref, "input": payload,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return "host-idempotency:" + digest

def host(path, run_id, invocation_id, correlation_id, operation_ref, payload, action="read", source="model"):
    call = {
        "protocol": "plane.agent-runtime/v1", "runId": run_id,
        "invocationId": invocation_id, "correlationId": correlation_id,
        "action": action, "operationRef": operation_ref, "input": payload,
        "source": source,
    }
    call["idempotencyKey"] = host_idempotency(run_id, invocation_id, action, operation_ref, payload)
    call["requestRef"] = call["idempotencyKey"].replace("host-idempotency:", "host-request:")
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
eager_read = next(
    item for item in request["run"]["toolCatalog"]["eagerOperations"]
    if item["operationRef"] == "operation:work_item.read"
)
assert eager_read["inputSchema"] == {
    "type": "object",
    "additionalProperties": False,
    "required": ["preparedCallRef"],
    "properties": {
        "preparedCallRef": {
            "type": "string",
            "minLength": len("prepared-call:"),
            "maxLength": 256,
        }
    },
}, eager_read
describe = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "operation:catalog.describe",
    {"operation_id": "search_workspace"},
)
assert describe["status"] == "ok", describe
described_schema = describe["output"]["operation"]["resultSchema"]
assert "workItemReadInput" not in described_schema["properties"]["results"]["items"]["properties"], describe
described_read_input = described_schema["properties"]["results"]["items"]["properties"]["workItemReadCall"][
    "properties"
]["input"]
assert described_read_input["required"] == ["preparedCallRef"], describe
assert set(described_read_input["properties"]) == {"preparedCallRef"}, describe
read_describe = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "operation:catalog.describe",
    {"operation_id": "work_item.read"},
)
assert read_describe["status"] == "ok", read_describe
assert read_describe["output"]["operation"]["inputSchema"] == eager_read["inputSchema"], read_describe
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
code = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "plane.code-mode.execute@1",
    {
        "schemaVersion": "plane.code-mode/v1",
        "entrypoint": "default",
        "source": "export default async function ({host, input}) { const result = await host.call_plane_operation('work_item.read', {preparedCallRef: input.preparedCallRef}, input.idempotencyKey, input.correlationId); if (!result.ok) throw new Error('prepared read failed'); return result; }",
            "input": {
                "preparedCallRef": read_call["input"]["preparedCallRef"],
                "correlationId": correlation_id,
                "idempotencyKey": host_idempotency(
                    run_id, invocation_id, "read", read_call["operationRef"], read_call["input"]
                ),
            },
    },
    action="code",
    source="code",
)
assert code["status"] == "ok", code
assert code["output"]["result"]["ok"] is True, code
print(json.dumps({"kind": "completed"}, separators=(",", ":")))
'''


_CATALOG_CODE_MODE_CHILD = r'''
import hashlib
import json
import socket
import sys

def host_idempotency(run_id, invocation_id, action, operation_ref, payload):
    identity = {
        "protocol": "plane.agent-runtime/v1", "runId": run_id,
        "invocationId": invocation_id, "action": action,
        "operationRef": operation_ref, "input": payload,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return "host-idempotency:" + digest

def host(path, run_id, invocation_id, correlation_id, operation_ref, payload, action="read", source="model"):
    call = {
        "protocol": "plane.agent-runtime/v1", "runId": run_id,
        "invocationId": invocation_id, "correlationId": correlation_id,
        "action": action, "operationRef": operation_ref, "input": payload,
        "source": source,
    }
    call["idempotencyKey"] = host_idempotency(run_id, invocation_id, action, operation_ref, payload)
    call["requestRef"] = call["idempotencyKey"].replace("host-idempotency:", "host-request:")
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
catalog = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "operation:catalog.search",
    {"query": "catalog.describe", "limit": 5},
)
assert catalog["status"] == "ok", catalog
describe_id = next(
    entry["operationId"]
    for entry in catalog["output"]["result"]["operations"]
    if entry["operationId"] == "catalog.describe"
)
described = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "operation:" + describe_id,
    {"operation_id": "work_item.read"},
)
assert described["status"] == "ok", described
operation_id = described["output"]["operation"]["operationId"]
search = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "operation:search_workspace",
    {"query": "Gateway Issue", "limit": 1},
)
assert search["status"] == "ok", search
item = next(item for item in search["output"]["result"]["results"] if item["objectType"] == "work_item")
read_input = item["workItemReadCall"]["input"]
code = host(
    socket_path,
    run_id,
    invocation_id,
    correlation_id,
    "plane.code-mode.execute@1",
    {
        "schemaVersion": "plane.code-mode/v1",
        "entrypoint": "default",
        "source": """
            export default async function ({host, input}) {
                const read = await host.call_plane_operation(
                    input.operationId, {preparedCallRef: input.preparedCallRef},
                    "idempotency:v25-work-item-read", "correlation:v25-work-item-read"
                );
                if (!read.ok) throw new Error("semantic read failed");
                throw new Error("forced post-read diagnostic");
            }
        """,
        "input": {"operationId": operation_id, "preparedCallRef": read_input["preparedCallRef"]},
    },
    action="code",
    source="code",
)
assert code["status"] == "unavailable", code
assert code["errorCode"] == "CODE_MODE_FAILED", code
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
        tool_presentation={"eagerOperations": ["work_item.read"]},
        suffix="prepared-remote-regression",
    )
    actor = run.actor
    assert WorkspaceMember.objects.filter(
        workspace=workspace, member_id=actor.principal_id, is_active=True
    ).exists()
    assert ProjectMember.objects.filter(
        project=gateway_project, member_id=actor.principal_id, is_active=True
    ).exists()
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
    host_call_principals = []
    prepared_inputs = []
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())

    def invoke(call):
        host_calls.append(call)
        host_call_principals.append(port._host.request.user.id)
        result = port.invoke(call)
        if call.operation_ref == "operation:search_workspace":
            prepared_inputs.extend(record["input"] for record in port._prepared_calls.values())
        return result

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
    assert host_server.failure_evidence is not None
    assert host_server.failure_evidence["operationId"] == "work_item.read"
    assert host_server.failure_evidence["status"] == "invalid"
    assert host_server.failure_evidence["errorCode"] == "PREPARED_CALL_INVALID"
    assert host_server.failure_evidence["preparedCallInvalidReason"] == "unknown"
    assert "prepared-call:" not in json.dumps(host_server.failure_evidence, sort_keys=True)
    assert [call.operation_ref for call in host_calls] == [
        "operation:catalog.describe",
        "operation:catalog.describe",
        "operation:search_workspace",
        "operation:work_item.read",
        "operation:work_item.read",
        "operation:work_item.read",
        "plane.code-mode.execute@1",
    ]
    assert prepared_inputs == [
        {"project_id": str(gateway_project.id), "issue_id": str(gateway_issue.id)}
    ]
    assert set(host_call_principals) == {actor.principal_id}
    assert all(
        record.caller_id == actor.principal_id
        for record in OperationGatewayIdempotency.objects.filter(
            correlation_id=invocation.envelope["correlationId"]
        )
    )
    actor.is_active = False
    actor.save(update_fields=["is_active"])
    with pytest.raises(CodeModeBindingError, match="AgentActor is inactive"):
        build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    assert OperationGatewayIdempotency.objects.filter(
        operation_id="work_item.read", correlation_id=invocation.envelope["correlationId"]
    ).count() == 1
    assert OperationGatewayAudit.objects.filter(
        operation_id="work_item.read", phase="outcome", outcome="success",
        correlation_id=invocation.envelope["correlationId"],
    ).count() == 1


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_remote_code_mode_catalog_handoff_preserves_versioned_operation_id(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    """One remote process covers the exact V24 discovery-to-callback failure seam."""

    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults={
            "provider": "openai",
            "model": "deterministic-local",
            "adapter": "hermes",
            "maxCodeModeCalls": 4,
        },
        suffix="catalog-code-mode-remote-regression",
    )
    package = tmp_path / "plane_runtime" / "g1_runtime_image"
    package.mkdir(parents=True)
    (tmp_path / "plane_runtime" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "plane_runtime" / "g1_contract.py").write_text("G1_CONTRACT_DIGESTS = {}\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "bootstrap.py").write_text(_CATALOG_CODE_MODE_CHILD, encoding="utf-8")

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
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "catalog-code-mode-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "catalog-code-mode-safety-stop"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(tmp_path / "credential-state.json"),
    }
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    host_calls = []
    outer_results = []

    def invoke(call):
        host_calls.append(call)
        result = port.invoke(call)
        outer_results.append(result)
        return result

    host_server = PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="host-token",
        invoke=invoke,
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
    service_environment.update(
        {
            "PLANE_AGENT_RUNTIME_BIND": "127.0.0.1",
            "PLANE_AGENT_RUNTIME_PORT": str(runtime_port),
            "PYTHONPATH": os.pathsep.join((os.getcwd(), str(tmp_path))),
        }
    )
    service = subprocess.Popen(
        [sys.executable, "-m", "plane.agent.runtime.service"],
        cwd=os.getcwd(),
        env=service_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
                {
                    "runtime": {
                        "api_key": "provider-free",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_mode": "chat_completions",
                    }
                }
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
    assert host_server.call_count == 4
    assert [call.operation_ref for call in host_calls] == [
        "operation:catalog.search",
        "operation:catalog.describe",
        "operation:search_workspace",
        "plane.code-mode.execute@1",
    ]
    assert outer_results[-1].status == "unavailable", outer_results[-1]
    failure_evidence = host_server.failure_evidence
    assert failure_evidence is not None
    assert failure_evidence == {
        "operationId": "plane.code-mode.execute@1",
        "attemptRef": failure_evidence["attemptRef"],
        "receiptRef": "unavailable",
        "status": "unavailable",
        "errorCode": "CODE_MODE_FAILED",
        "codeModePhase": "host_callback",
    }
    receipts = OperationGatewayIdempotency.objects.filter(correlation_id="correlation:v25-work-item-read")
    assert list(receipts.values_list("operation_id", flat=True)) == ["work_item.read"]
    assert OperationGatewayAudit.objects.filter(
        operation_id="work_item.read",
        phase="outcome",
        outcome="success",
        correlation_id="correlation:v25-work-item-read",
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
    assert altered_correlation.prepared_call_invalid_reason == "consumed"


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_search_requires_consuming_prepared_read_before_searching_again(
    workspace, gateway_project, gateway_issue, create_user
):
    _, invocation = _invocation(
        workspace, gateway_project, gateway_issue, create_user, suffix="prepared-port-handoff"
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    search_call = _port_call(
        invocation,
        operation_ref="operation:search_workspace",
        input_data={"query": "Gateway Issue", "limit": 1},
    )
    search = port.invoke(search_call)
    assert search.status == "ok", search
    assert any(item.get("workItemReadCall") for item in search.output["result"]["results"])

    repeated_search = port.invoke(search_call)

    assert repeated_search.status == "invalid"
    assert repeated_search.error_code == "VALIDATION_ERROR"
    assert "prepared work-item read" in repeated_search.error_message.lower()
    assert OperationGatewayIdempotency.objects.filter(operation_id="search_workspace").count() == 1

    read_call = next(
        item["workItemReadCall"]
        for item in search.output["result"]["results"]
        if item.get("workItemReadCall")
    )
    read = port.invoke(
        _port_call(
            invocation,
            operation_ref=read_call["operationRef"],
            input_data=read_call["input"],
        )
    )
    assert read.status == "ok", read
    resumed_search = port.invoke(search_call)
    assert resumed_search.status == "ok", resumed_search
    assert OperationGatewayIdempotency.objects.filter(operation_id="search_workspace").count() == 1

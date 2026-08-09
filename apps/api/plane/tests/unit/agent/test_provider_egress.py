from __future__ import annotations

import json
import os
import socket
import sys
import textwrap
from dataclasses import replace
import time
from dataclasses import dataclass

import pytest

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostResult,
    RuntimeConfigurationError,
    RuntimeCredentialBroker,
    RuntimeSafetyController,
)
from plane.agent.runtime.provider_egress import (
    ProviderRelayAudit,
    ProviderRelayBinding,
    ProviderRelayError,
    PROVIDER_RELAY_HOST,
    ProviderRelayPolicy,
    ProviderRelayServer,
    ProviderRequest,
    ProviderResponse,
    _relay_bootstrap_payload,
)
from plane.agent.runtime.service import RuntimeDispatchExecutor


RUN_ID = "run:relay"
INVOCATION_ID = "invocation:relay"
PROVIDER = "xai"
MODEL = "grok-4"
HOST = "api.x.ai"
PATH = "/v1/chat/completions"


def _body(model: str = MODEL, *, extra: str = "") -> bytes:
    return json.dumps(
        {"model": model, "messages": [{"role": "user", "content": "hello" + extra}], "max_tokens": 32}
    ).encode()


def _round_trip(
    server: ProviderRelayServer,
    *,
    token: str | None = None,
    request_id: str = "request:one",
    body: bytes | None = None,
    method: str = "POST",
    path: str = PATH,
    host: str = PROVIDER_RELAY_HOST,
    invocation_id: str = INVOCATION_ID,
    provider: str = PROVIDER,
    model: str = MODEL,
) -> tuple[int, dict[str, str], bytes]:
    body = body or _body(model)
    token = token or server.descriptor.token
    headers = {
        "Host": host,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Content-Length": str(len(body)),
        "Connection": "close",
        "X-Request-ID": request_id,
        "X-Plane-Relay-Invocation": invocation_id,
        "X-Plane-Relay-Provider": provider,
        "X-Plane-Relay-Model": model,
        "X-Plane-Relay-Run": RUN_ID,
    }
    wire = (
        f"{method} {path} HTTP/1.1\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        + "\r\n"
    ).encode() + body
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(2)
        channel.connect(str(server.descriptor.socket_path))
        channel.sendall(wire)
        chunks = bytearray()
        while True:
            chunk = channel.recv(65536)
            if not chunk:
                break
            chunks.extend(chunk)
    header_raw, response_body = bytes(chunks).split(b"\r\n\r\n", 1)
    header_lines = header_raw.split(b"\r\n")
    status = int(header_lines[0].split(b" ", 2)[1])
    response_headers = {
        key.decode().casefold(): value.decode()
        for key, value in (line.split(b": ", 1) for line in header_lines[1:] if b": " in line)
    }
    if response_headers.get("transfer-encoding") == "chunked":
        decoded = bytearray()
        cursor = 0
        while True:
            end = response_body.index(b"\r\n", cursor)
            size = int(response_body[cursor:end], 16)
            cursor = end + 2
            if size == 0:
                break
            decoded.extend(response_body[cursor : cursor + size])
            cursor += size + 2
        response_body = bytes(decoded)
    return status, response_headers, response_body


@dataclass
class _FixtureUpstream:
    response: ProviderResponse
    calls: list[tuple[ProviderRequest, dict[str, str]]]

    def __call__(self, request: ProviderRequest, credentials: dict[str, str], _cancelled) -> ProviderResponse:
        self.calls.append((request, credentials))
        return self.response


def _server(tmp_path, *, upstream: _FixtureUpstream, **kwargs: object) -> ProviderRelayServer:
    return ProviderRelayServer(
        socket_path=tmp_path / "provider.sock",
        binding=ProviderRelayBinding(
            run_id=RUN_ID,
            invocation_id=INVOCATION_ID,
            provider=PROVIDER,
            model=MODEL,
        ),
        policy=ProviderRelayPolicy(provider=PROVIDER, host=HOST, path=PATH, models=(MODEL,)),
        credentials={"api_key": "provider-secret"},
        upstream=upstream,
        **kwargs,
    )


def test_permitted_provider_request_uses_invocation_af_unix_relay_and_streams_without_child_credential(tmp_path):
    upstream = _FixtureUpstream(
        ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=(b"data: ", b"ok\n\n"),
        ),
        [],
    )
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    try:
        server.start()
        status, headers, body = _round_trip(server, request_id="request:stream")
    finally:
        server.close()

    assert status == 200
    assert headers["transfer-encoding"] == "chunked"
    assert body == b"data: ok\n\n"
    assert len(upstream.calls) == 1
    request, credentials = upstream.calls[0]
    assert request.headers == {"accept": "text/event-stream"}
    assert credentials == {"api_key": "provider-secret"}
    assert audits[-1].outcome == "allowed"
    assert "provider-secret" not in repr(audits)


def test_provider_attempt_intent_precedes_upstream_and_upstream_failure_is_unknown(tmp_path):
    upstream = _FixtureUpstream(
        ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)),
        [],
    )

    def failed_upstream(request, credentials, is_cancelled):
        upstream.calls.append((request, credentials))
        raise RuntimeError("fixture upstream failed")

    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=failed_upstream, audit=audits.append)
    try:
        server.start()
        status, _headers, body = _round_trip(server, request_id="request:unknown")
    finally:
        server.close()

    assert status == 403
    assert json.loads(body) == {"error": "upstream_error"}
    assert [audit.phase for audit in audits] == ["intent", "started", "outcome_unknown"]
    assert audits[0].upstream_called is False
    assert audits[1].upstream_called is True
    assert audits[-1].error_code == "upstream_error"
    assert audits[-1].status_class == "unknown"
    assert len(upstream.calls) == 1


def test_provider_attempt_evidence_failure_blocks_pre_send_upstream(tmp_path):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    attempted_phases: list[str] = []

    def unavailable_evidence(audit: ProviderRelayAudit) -> None:
        attempted_phases.append(audit.phase)
        if audit.phase == "intent":
            raise RuntimeError("evidence unavailable")

    server = _server(tmp_path, upstream=upstream, audit=unavailable_evidence)
    try:
        server.start()
        status, _headers, body = _round_trip(server, request_id="request:not-sent")
    finally:
        server.close()

    assert status == 403
    assert json.loads(body) == {"error": "denied"}
    assert attempted_phases == ["intent", "failed"]
    assert upstream.calls == []


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("token", "wrong-token", "token"),
        ("invocation_id", "invocation:other", "invocation"),
        ("provider", "other-provider", "provider"),
        ("host", "evil.example", "host"),
        ("path", "/v1/other", "path"),
        ("method", "GET", "method"),
        ("model", "other-model", "model"),
    ),
)
def test_provider_relay_denies_wrong_binding_without_upstream_call(tmp_path, field: str, value: str, reason: str):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    try:
        server.start()
        values: dict[str, object] = {field: value}
        status, _headers, response_body = _round_trip(server, **values)
    finally:
        server.close()
    assert status == 403
    assert json.loads(response_body) == {"error": "denied"}
    assert upstream.calls == []
    assert audits[-1].outcome == "denied"
    assert reason in audits[-1].reason


@pytest.mark.parametrize(
    "body",
    (
        b'{"model":"grok-4","api_key":"leaked"}',
        b'{"model":"grok-4","authorization":"Bearer leaked"}',
        b'{"model":"grok-4","nested":{"token":"leaked"}}',
    ),
)
def test_provider_relay_denies_credential_shaped_body_without_upstream_call(tmp_path, body: bytes):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    server = _server(tmp_path, upstream=upstream)
    try:
        server.start()
        status, _headers, response_body = _round_trip(server, body=body)
    finally:
        server.close()
    assert status == 403
    assert json.loads(response_body) == {"error": "credential_payload"}
    assert upstream.calls == []


def test_provider_relay_rejects_oversize_replay_expired_and_cancelled_requests_before_upstream(tmp_path):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    cancelled = {"value": False}
    server = _server(
        tmp_path,
        upstream=upstream,
        is_cancelled=lambda: cancelled["value"],
        lease_validator=lambda: (_ for _ in ()).throw(ProviderRelayError("lease expired")),
        max_request_bytes=512,
    )
    try:
        server.start()
        status, _headers, body = _round_trip(server, request_id="request:expired")
    finally:
        server.close()
    assert status == 403 and json.loads(body) == {"error": "lease_invalid"}

    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    server = _server(tmp_path, upstream=upstream)
    try:
        server.start()
        first = _round_trip(server, request_id="request:replay")
        second = _round_trip(server, request_id="request:replay")
    finally:
        server.close()
    assert first[0] == 200
    assert second[0] == 403 and json.loads(second[2]) == {"error": "replay"}
    assert len(upstream.calls) == 1

    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)), [])
    server = _server(tmp_path, upstream=upstream, is_cancelled=lambda: True)
    try:
        server.start()
        cancelled_response = _round_trip(server, request_id="request:cancelled")
    finally:
        server.close()
    assert cancelled_response[0] == 403 and json.loads(cancelled_response[2]) == {"error": "cancelled"}
    assert upstream.calls == []


def test_provider_relay_rejects_redirects_and_closes_after_process_death(tmp_path):
    upstream = _FixtureUpstream(
        ProviderResponse(status_code=302, headers={"location": "https://evil.example"}, body_chunks=(b"no",)),
        [],
    )
    server = _server(tmp_path, upstream=upstream)
    server.start()
    try:
        status, _headers, body = _round_trip(server, request_id="request:redirect")
    finally:
        server.close()
    assert status == 403
    assert json.loads(body) == {"error": "redirect_denied"}

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        with pytest.raises((ConnectionRefusedError, FileNotFoundError, OSError)):
            channel.connect(str(server.descriptor.socket_path))


def test_relay_bootstrap_fields_match_hermes_contract_without_provider_secret(tmp_path):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"ok",)), [])
    server = _server(tmp_path, upstream=upstream)
    server.start()
    try:
        fields = _relay_bootstrap_payload(server.descriptor, server.policy)
        assert set(fields) == {"host", "invocationSocket", "path", "provider", "relayToken"}
        assert fields["host"] == HOST
        assert fields["invocationSocket"] == str(server.descriptor.socket_path)
        assert fields["path"] == PATH
        assert fields["provider"] == PROVIDER
        assert fields["relayToken"] == server.descriptor.token
        assert "provider-secret" not in json.dumps(fields, sort_keys=True)
    finally:
        server.close()


def test_runtime_service_opens_relay_with_existing_lease_and_closes_it(tmp_path):
    state_file = tmp_path / "revocations.json"
    now = [time.time()]
    broker = RuntimeCredentialBroker(
        {"provider": {"api_key": "parent-provider-secret"}},
        ttl_seconds=60,
        clock=lambda: now[0],
        state_file=state_file,
    )
    lease, credentials = broker.issue(
        agent_ref="agent:relay", credential_ref="provider", invocation_ref=INVOCATION_ID
    )
    configuration = AgentRuntimeConfiguration.from_environment(
        {
            "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
            "PLANE_AGENT_RUNTIME_SECRET": "r" * 40,
            "PLANE_AGENT_RUNTIME_PROVIDER": PROVIDER,
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": HOST,
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": MODEL,
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(state_file),
        }
    )
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"ok",)), [])
    relay = executor.open_provider_relay(
        run_id=RUN_ID,
        invocation_id=INVOCATION_ID,
        provider=PROVIDER,
        model=MODEL,
        credentials=credentials,
        credential_lease=lease.public_metadata(),
        upstream=upstream,
    )
    try:
        response = _round_trip(relay.server, request_id="request:lease")
        assert response[0] == 200
        assert upstream.calls[0][1] == credentials
        broker.revoke_invocation(INVOCATION_ID)
        denied = _round_trip(relay.server, request_id="request:revoked")
        assert denied[0] == 403 and json.loads(denied[2]) == {"error": "lease_invalid"}
    finally:
        relay.close()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        with pytest.raises((ConnectionRefusedError, FileNotFoundError, OSError)):
            channel.connect(str(relay.descriptor.socket_path))
    assert "parent-provider-secret" not in repr(relay)


def test_runtime_service_passes_invocation_relay_to_child_without_provider_secret(tmp_path, monkeypatch):
    state_file = tmp_path / "revocations.json"
    broker = RuntimeCredentialBroker(
        {"provider": {"api_key": "parent-provider-secret"}},
        ttl_seconds=60,
        state_file=state_file,
    )
    lease, credentials = broker.issue(
        agent_ref="agent:relay", credential_ref="provider", invocation_ref=INVOCATION_ID
    )
    configuration = AgentRuntimeConfiguration.from_environment(
        {
            "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
            "PLANE_AGENT_RUNTIME_SECRET": "r" * 40,
            "PLANE_AGENT_RUNTIME_PROVIDER": PROVIDER,
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": HOST,
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": MODEL,
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(state_file),
        }
    )
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    callback_phases: list[str] = []

    class FixtureHostClient:
        def __init__(self, *, url: str, auth_token: str):
            assert url == "http://plane-host.invalid"
            assert auth_token == "host-token"

        def invoke(self, call):
            callback_phases.append(call.input["phase"])
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="ok",
                replayed=False,
            )

    monkeypatch.setattr("plane.agent.runtime.service.PlaneHostHTTPClient", FixtureHostClient)
    child = textwrap.dedent(
        """
        import json
        import socket
        import sys

        socket_path = sys.argv[sys.argv.index('--provider-relay-socket') + 1]
        dispatch = json.loads(sys.stdin.buffer.readline())
        credentials = json.loads(sys.stdin.buffer.readline())['credentials']
        assert set(credentials) == {'host', 'invocationSocket', 'path', 'provider', 'relayToken'}
        assert 'parent-provider-secret' not in json.dumps(credentials)
        request = json.loads(sys.stdin.buffer.readline())
        body = json.dumps({'model': request['run']['runtimePolicy']['model']['model'], 'messages': []}).encode()
        wire = (
            b'POST /v1/chat/completions HTTP/1.1\\r\\n'
            + b'Host: plane-provider-relay.invalid\\r\\n'
            + ('Authorization: Bearer ' + credentials['relayToken'] + '\\r\\n').encode()
            + b'Content-Type: application/json\\r\\n'
            + ('Content-Length: ' + str(len(body)) + '\\r\\n').encode()
            + b'X-Request-ID: request:child\\r\\n\\r\\n'
            + body
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.connect(socket_path)
            channel.sendall(wire)
            response = bytearray()
            while True:
                chunk = channel.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
            assert b'200 OK' in response
        print(json.dumps({'status': 'completed'}, separators=(',', ':')))
        """
    )
    from plane.agent.runtime.subprocess import RuntimeProcessPolicy, SubprocessRuntimeTransport

    executor._transport = SubprocessRuntimeTransport(
        command=(sys.executable, "-c", child),
        environment=dict(os.environ),
        ledger_path=tmp_path / "ledger.sqlite",
        process_policy=RuntimeProcessPolicy(enforce_kernel_policy=False),
    )
    executor.configuration = replace(configuration, command=(sys.executable, "-c", child))
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"ok",)), [])
    snapshot = {
        "actorRef": "actor:relay",
        "runId": RUN_ID,
        "workspaceRef": "workspace:relay",
        "runtimePolicy": {
            "model": {"provider": PROVIDER, "model": MODEL},
            "adapter": "openai-compatible",
            "isolation": "process",
            "maxEventPayloadBytes": 8192,
            "maxArtifactBytes": 8192,
            "maxReceiptBytes": 8192,
            "maxCodeModeInputBytes": 4096,
            "maxCodeModeOutputBytes": 4096,
            "maxCodeModeCalls": 4,
        },
    }
    invocation = {
        "correlationId": "correlation:relay",
        "invocationId": INVOCATION_ID,
        "runId": RUN_ID,
        "remainingBudget": {"outputTokens": 1},
    }
    original_open = executor.open_provider_relay

    def open_with_fixture(**kwargs):
        return original_open(upstream=upstream, **kwargs)

    executor.open_provider_relay = open_with_fixture  # type: ignore[method-assign]
    frames = executor._execute(
        snapshot,
        invocation,
        "test-digest",
        credentials=credentials,
        credential_lease=lease.public_metadata(),
        allowance=1,
        host_url="http://plane-host.invalid",
        host_token="host-token",
    )
    assert frames == ('{"status":"completed"}',)
    assert len(upstream.calls) == 1
    assert upstream.calls[0][1] == credentials
    assert callback_phases == ["intent", "started", "completed"]


def test_runtime_service_fails_closed_before_child_dispatch_without_lease(tmp_path):
    configuration = AgentRuntimeConfiguration.from_environment(
        {
            "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
            "PLANE_AGENT_RUNTIME_SECRET": "r" * 40,
            "PLANE_AGENT_RUNTIME_PROVIDER": PROVIDER,
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": HOST,
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": MODEL,
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(tmp_path / "revocations.json"),
        }
    )
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    snapshot = {
        "runId": RUN_ID,
        "runtimePolicy": {"model": {"provider": PROVIDER, "model": MODEL}},
    }
    invocation = {"runId": RUN_ID, "invocationId": INVOCATION_ID}
    with pytest.raises(RuntimeConfigurationError, match="credential lease"):
        executor._execute(
            snapshot,
            invocation,
            "digest",
            credentials={"api_key": "parent-provider-secret"},
            credential_lease=None,
            allowance=1,
            host_url=None,
            host_token=None,
        )

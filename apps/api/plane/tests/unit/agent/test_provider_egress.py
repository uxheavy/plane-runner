from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import sys
import textwrap
import threading
from http.client import HTTPException
from dataclasses import replace
import time
from dataclasses import dataclass

import pytest
from plane.agent.runtime import provider_egress
from plane.agent.runtime import service as runtime_service

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostResult,
    RuntimeDispatchError,
    RuntimeConfigurationError,
    RuntimeCredentialBroker,
    RuntimeSafetyController,
)
from plane.agent.runtime.provider_egress import (
    PinnedProviderHTTPSClient,
    ProviderRelayAudit,
    ProviderRelayBinding,
    ProviderRelayError,
    ProviderRelayOutcomeUnknownError,
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
    extra_headers: dict[str, str] | None = None,
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
    headers.update(extra_headers or {})
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


class _FixtureHTTPSResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body
        self._read = False

    def getheaders(self) -> list[tuple[str, str]]:
        return [("content-type", "application/json"), ("x-provider-secret", "must not persist")]

    def read(self, _size: int) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._body


class _FixtureHTTPSConnection:
    def __init__(self, response: _FixtureHTTPSResponse | None = None, failure: BaseException | None = None) -> None:
        self.response = response
        self.failure = failure
        self.closed = False
        self.request_headers: dict[str, str] = {}

    def request(self, *_args: object, **kwargs: object) -> None:
        headers = kwargs.get("headers")
        if isinstance(headers, dict):
            self.request_headers = dict(headers)
        if self.failure is not None:
            raise self.failure

    def getresponse(self) -> _FixtureHTTPSResponse:
        if self.failure is not None:
            raise self.failure
        assert self.response is not None
        return self.response

    def close(self) -> None:
        self.closed = True


def _pinned_request() -> tuple[ProviderRelayPolicy, ProviderRequest]:
    policy = ProviderRelayPolicy(provider=PROVIDER, host=HOST, path=PATH, models=(MODEL,))
    return policy, ProviderRequest(
        provider=PROVIDER,
        model=MODEL,
        method="POST",
        host=HOST,
        path=PATH,
        headers={"accept": "application/json"},
        body=_body(),
        request_id="request:pinned",
        sequence=1,
    )


def _server(tmp_path, *, upstream: _FixtureUpstream, **kwargs: object) -> ProviderRelayServer:
    max_calls = int(kwargs.pop("max_calls", 16))
    return ProviderRelayServer(
        socket_path=tmp_path / "provider.sock",
        binding=ProviderRelayBinding(
            run_id=RUN_ID,
            invocation_id=INVOCATION_ID,
            provider=PROVIDER,
            model=MODEL,
        ),
        policy=ProviderRelayPolicy(
            provider=PROVIDER,
            host=HOST,
            path=PATH,
            models=(MODEL,),
            max_calls=max_calls,
        ),
        credentials={"api_key": "provider-secret"},
        upstream=upstream,
        **kwargs,
    )


@pytest.mark.parametrize("status_code, status_class", ((400, "4xx"), (429, "4xx"), (500, "5xx")))
def test_pinned_provider_http_error_preserves_only_bounded_status_family(
    monkeypatch, status_code: int, status_class: str
):
    policy, request = _pinned_request()
    connection = _FixtureHTTPSConnection(
        response=_FixtureHTTPSResponse(status_code, body=b"provider body must not persist"),
    )
    monkeypatch.setattr(provider_egress.http.client, "HTTPSConnection", lambda *_args, **_kwargs: connection)

    with pytest.raises(ProviderRelayError) as caught:
        PinnedProviderHTTPSClient(policy)(request, {"api_key": "provider-secret"}, lambda: False)

    error = caught.value
    assert error.status_class == status_class
    assert str(error) == "provider returned an unsuccessful status"
    assert error.reason_subreason in {"request_rejected", "rate_limited", "upstream_unavailable"}
    assert vars(error)["status_class"] == status_class
    assert str(status_code) not in repr(error)
    assert "provider body must not persist" not in repr(error)
    assert "provider-secret" not in repr(error)
    assert connection.closed is True


@pytest.mark.parametrize(
    "status_code, status_class, reason_subreason",
    (
        (400, "4xx", "request_rejected"),
        (422, "4xx", "request_rejected"),
        (401, "4xx", "auth"),
        (403, "4xx", "auth"),
        (429, "4xx", "rate_limited"),
        (500, "5xx", "upstream_unavailable"),
    ),
)
def test_pinned_provider_http_error_preserves_bounded_reason_subreason(
    monkeypatch, status_code: int, status_class: str, reason_subreason: str
):
    policy, request = _pinned_request()
    connection = _FixtureHTTPSConnection(
        response=_FixtureHTTPSResponse(status_code, body=b"provider body must not persist"),
    )
    monkeypatch.setattr(provider_egress.http.client, "HTTPSConnection", lambda *_args, **_kwargs: connection)

    with pytest.raises(ProviderRelayError) as caught:
        PinnedProviderHTTPSClient(policy)(request, {"api_key": "provider-secret"}, lambda: False)

    error = caught.value
    assert error.status_class == status_class
    assert error.reason_subreason == reason_subreason
    assert str(error) == "provider returned an unsuccessful status"
    assert str(status_code) not in repr(error)
    assert "provider body must not persist" not in repr(error)
    assert "provider-secret" not in repr(error)
    assert connection.closed is True


def test_provider_relay_error_rejects_unbounded_status_class():
    error = ProviderRelayError("provider error", status_class="429", reason_subreason="provider-code-429")

    assert error.status_class == ""
    assert error.reason_subreason == ""
    assert vars(error) == {"status_class": ""}


def test_pinned_provider_transport_failure_remains_bounded_outcome_unknown(monkeypatch):
    policy, request = _pinned_request()
    connection = _FixtureHTTPSConnection(failure=ssl.SSLError("TLS/socket detail must not persist"))
    monkeypatch.setattr(provider_egress.http.client, "HTTPSConnection", lambda *_args, **_kwargs: connection)

    with pytest.raises(ProviderRelayOutcomeUnknownError) as caught:
        PinnedProviderHTTPSClient(policy)(request, {"api_key": "provider-secret"}, lambda: False)

    error = caught.value
    assert error.status_class == "transport"
    assert error.reason_subreason == "upstream_channel_closed"
    assert str(error) == "provider request outcome is unknown"
    assert "TLS/socket detail must not persist" not in repr(error)
    assert "provider-secret" not in repr(error)
    assert connection.closed is True


def test_pinned_codex_provider_forwards_chatgpt_account_header(monkeypatch):
    policy = ProviderRelayPolicy(
        provider="openai-codex",
        host="chatgpt.com",
        path="/backend-api/codex/responses",
        models=("gpt-5.6-luna",),
    )
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": "synthetic-account"}}).encode()
    ).rstrip(b"=")
    token = b".".join((header, payload, b"signature")).decode()
    request = ProviderRequest(
        provider="openai-codex",
        model="gpt-5.6-luna",
        method="POST",
        host="chatgpt.com",
        path="/backend-api/codex/responses",
        headers={"accept": "application/json"},
        body=_body("gpt-5.6-luna"),
        request_id="request:codex-account",
    )
    connection = _FixtureHTTPSConnection(response=_FixtureHTTPSResponse(200, body=b"ok"))
    monkeypatch.setattr(
        provider_egress.http.client,
        "HTTPSConnection",
        lambda *_args, **_kwargs: connection,
    )

    PinnedProviderHTTPSClient(policy)(request, {"api_key": token}, lambda: False)

    assert connection.request_headers["originator"] == "codex_cli_rs"
    assert connection.request_headers["User-Agent"].startswith("codex_cli_rs/")
    assert connection.request_headers["ChatGPT-Account-ID"] == "synthetic-account"


def test_pinned_provider_successful_2xx_response_crosses_client_and_relay(monkeypatch, tmp_path):
    policy, request = _pinned_request()
    monkeypatch.setattr(
        provider_egress.http.client,
        "HTTPSConnection",
        lambda *_args, **_kwargs: _FixtureHTTPSConnection(
            response=_FixtureHTTPSResponse(201, body=b"data: ok\n\n")
        ),
    )

    response = PinnedProviderHTTPSClient(policy)(request, {"api_key": "provider-secret"}, lambda: False)

    assert response.status_code == 201
    assert tuple(response.body_chunks) == (b"data: ok\n\n",)

    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=PinnedProviderHTTPSClient(policy), audit=audits.append)
    try:
        server.start()
        relay_response = _round_trip(server, request_id="request:pinned-relay-2xx")
    finally:
        server.close()

    assert relay_response[0] == 200
    assert relay_response[2] == b"data: ok\n\n"
    assert audits[-1].status_class == "2xx"


@pytest.mark.parametrize(
    ("status_code", "status_class", "reason_subreason"),
    ((400, "4xx", "request_rejected"), (500, "5xx", "upstream_unavailable")),
)
def test_pinned_provider_http_error_reaches_bounded_relay_audit(
    monkeypatch, tmp_path, status_code: int, status_class: str, reason_subreason: str
):
    policy, _request = _pinned_request()
    connection = _FixtureHTTPSConnection(
        response=_FixtureHTTPSResponse(
            status_code,
            body=b"provider body; status text; https://secret.invalid/provider; provider-secret",
        ),
    )
    monkeypatch.setattr(provider_egress.http.client, "HTTPSConnection", lambda *_args, **_kwargs: connection)
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=PinnedProviderHTTPSClient(policy), audit=audits.append)

    try:
        server.start()
        response = _round_trip(server, request_id="request:pinned-relay-status")
    finally:
        server.close()

    assert response[0] == 403
    assert json.loads(response[2]) == {
        "error": "provider_error",
        "reasonSubreason": reason_subreason,
        "statusClass": status_class,
    }
    assert [audit.phase for audit in audits] == ["intent", "started", "failed"]
    assert audits[-1].status_class == status_class
    assert audits[-1].reason_subreason == reason_subreason
    assert audits[-1].error_code == "provider_error"
    secrets = ("provider body", "status text", "https://secret.invalid", "provider-secret")
    assert all(secret.encode() not in response[2] for secret in secrets)
    assert all(secret not in repr(audits) for secret in secrets)


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
    assert audits[-1].status_class == "2xx"
    assert "provider-secret" not in repr(audits)


def test_provider_relay_buffers_complete_upstream_before_child_early_close(tmp_path, monkeypatch):
    response_consumed = threading.Event()
    completed_audit = threading.Event()
    audits: list[ProviderRelayAudit] = []

    def upstream(_request, _credentials, _cancelled):
        def chunks():
            yield b"data: response.completed\n\n"
            response_consumed.set()

        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=chunks(),
        )

    def record_audit(audit: ProviderRelayAudit) -> None:
        audits.append(audit)
        if audit.phase == "completed":
            completed_audit.set()

    def child_closed(_relay, _channel, _request_id, _response):
        assert response_consumed.is_set()
        raise BrokenPipeError("child closed after terminal SSE event")

    monkeypatch.setattr(provider_egress.ProviderRelayServer, "_write_http_response", child_closed)
    server = _server(
        tmp_path,
        upstream=upstream,
        audit=record_audit,
    )
    try:
        server.start()
        with pytest.raises((ValueError, OSError)):
            _round_trip(server, request_id="request:child-early-close")
        assert completed_audit.wait(2)
    finally:
        server.close()

    assert [audit.phase for audit in audits] == ["intent", "started", "completed"]
    assert not any(audit.phase == "outcome_unknown" for audit in audits)


def test_provider_relay_close_drains_handler_before_closing_active_channel(tmp_path):
    audit_started = threading.Event()
    allow_audit = threading.Event()
    audits: list[ProviderRelayAudit] = []

    def upstream(_request, _credentials, _cancelled):
        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=(b"data: response.completed\n\n",),
        )

    def record_audit(audit: ProviderRelayAudit) -> None:
        audits.append(audit)
        if audit.phase == "completed":
            audit_started.set()
            assert allow_audit.wait(2)

    server = _server(tmp_path, upstream=upstream, audit=record_audit)
    request_result: list[object] = []

    def request() -> None:
        try:
            request_result.append(_round_trip(server, request_id="request:drain"))
        except BaseException as exc:
            request_result.append(exc)

    server.start()
    request_thread = threading.Thread(target=request)
    request_thread.start()
    try:
        assert audit_started.wait(2)
        close_done = threading.Event()

        def close() -> None:
            server.close()
            close_done.set()

        close_thread = threading.Thread(target=close)
        close_thread.start()
        assert not close_done.wait(0.1)
        allow_audit.set()
        assert close_done.wait(2)
        close_thread.join()
    finally:
        allow_audit.set()
        server.close()
        request_thread.join()

    assert not any(isinstance(item, BaseException) for item in request_result)
    assert [audit.phase for audit in audits] == ["intent", "started", "completed"]
    assert server.required_audit_failure is None


def test_provider_relay_close_gracefully_drains_delayed_body(tmp_path):
    body_started = threading.Event()
    audits: list[ProviderRelayAudit] = []

    def upstream(_request, _credentials, _cancelled):
        def body_chunks():
            body_started.set()
            time.sleep(0.1)
            yield b"data: response.completed\n\n"

        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=body_chunks(),
        )

    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    request_result: list[object] = []

    def request() -> None:
        try:
            request_result.append(_round_trip(server, request_id="request:delayed-body"))
        except BaseException as exc:
            request_result.append(exc)

    server.start()
    request_thread = threading.Thread(target=request)
    request_thread.start()
    try:
        assert body_started.wait(2)
        server.close()
    finally:
        server.close()
        request_thread.join()

    assert not any(isinstance(item, BaseException) for item in request_result)
    assert [audit.phase for audit in audits] == ["intent", "started", "completed"]
    assert server.required_audit_failure is None


def test_provider_relay_forced_close_marks_unresolved_body_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(provider_egress, "_RELAY_DRAIN_TIMEOUT_SECONDS", 0.05)
    body_started = threading.Event()
    release_body = threading.Event()
    unknown_audit_finished = threading.Event()
    audits: list[ProviderRelayAudit] = []

    def upstream(_request, _credentials, _cancelled):
        def body_chunks():
            body_started.set()
            assert release_body.wait(2)
            yield b"data: response.completed\n\n"

        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=body_chunks(),
        )

    def record_audit(audit: ProviderRelayAudit) -> None:
        audits.append(audit)
        if audit.phase == "outcome_unknown":
            unknown_audit_finished.set()

    server = _server(tmp_path, upstream=upstream, audit=record_audit)
    request_result: list[object] = []

    def request() -> None:
        try:
            request_result.append(_round_trip(server, request_id="request:forced-close"))
        except BaseException as exc:
            request_result.append(exc)

    server.start()
    request_thread = threading.Thread(target=request)
    request_thread.start()
    release_thread = threading.Thread(
        target=lambda: (server._forced_close.wait(2), release_body.set())
    )
    release_thread.start()
    try:
        assert body_started.wait(2)
        server.close()
        release_thread.join()
        request_thread.join(2)
    finally:
        release_body.set()
        server.close()
        request_thread.join()

    assert [audit.phase for audit in audits] == ["intent", "started", "outcome_unknown", "terminal"]
    assert audits[-1].reason_subreason == "upstream_channel_closed"
    assert unknown_audit_finished.is_set()


def test_codex_cache_scope_headers_are_permitted_without_forwarding_credentials(tmp_path):
    upstream = _FixtureUpstream(
        ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=(b"data: ok\n\n",),
        ),
        [],
    )
    server = _server(tmp_path, upstream=upstream)
    try:
        server.start()
        status, _headers, body = _round_trip(
            server,
            request_id="request:codex-cache-scope",
            extra_headers={
                "session_id": "invocation:relay",
                "x-client-request-id": "request:codex-cache-scope",
            },
        )
    finally:
        server.close()

    assert status == 200
    assert body == b"data: ok\n\n"
    assert len(upstream.calls) == 1
    assert upstream.calls[0][1] == {"api_key": "provider-secret"}


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
    assert json.loads(body) == {
        "error": "outcome_unknown",
        "retryable": False,
        "upstreamInitiated": True,
        "reasonCode": "outcome_unknown",
        "reasonPhase": "provider_relay",
        "reasonSubreason": "upstream_exception",
        "statusClass": "transport",
    }
    assert [audit.phase for audit in audits] == ["intent", "started", "outcome_unknown", "terminal"]
    assert audits[0].upstream_called is False
    assert audits[1].upstream_called is True
    assert audits[-1].error_code == "outcome_unknown"
    assert audits[-1].status_class == "transport"
    assert audits[-1].reason_phase == "provider_relay"
    assert audits[-1].reason_subreason == "upstream_exception"
    assert "fixture upstream failed" not in repr(audits)
    assert len(upstream.calls) == 1


@pytest.mark.parametrize("status_code, status_class", ((400, "4xx"), (500, "5xx")))
def test_provider_http_status_family_survives_bounded_relay_audit(tmp_path, status_code: int, status_class: str):
    upstream = _FixtureUpstream(
        ProviderResponse(status_code=status_code, headers={}, body_chunks=(b"provider body must not persist",)),
        [],
    )
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    try:
        server.start()
        response = _round_trip(server, request_id=f"request:status-{status_code}")
    finally:
        server.close()

    assert response[0] == 403
    assert json.loads(response[2]) == {
        "error": "provider_error",
        "reasonSubreason": "upstream_unavailable" if status_code == 500 else "request_rejected",
        "statusClass": status_class,
    }
    assert [audit.phase for audit in audits] == ["intent", "started", "failed"]
    assert audits[-1].status_class == status_class
    assert audits[-1].error_code == "provider_error"
    assert b"provider body must not persist" not in response[2]
    assert "provider body must not persist" not in repr(audits)


@pytest.mark.parametrize(
    "status_code, reason_subreason",
    (
        (400, "request_rejected"),
        (422, "request_rejected"),
        (401, "auth"),
        (403, "auth"),
        (429, "rate_limited"),
        (500, "upstream_unavailable"),
    ),
)
def test_provider_http_reason_subreason_survives_bounded_relay_audit(
    tmp_path, status_code: int, reason_subreason: str
):
    upstream = _FixtureUpstream(
        ProviderResponse(status_code=status_code, headers={}, body_chunks=(b"provider body must not persist",)),
        [],
    )
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    try:
        server.start()
        response = _round_trip(server, request_id=f"request:reason-{status_code}")
    finally:
        server.close()

    assert response[0] == 403
    assert json.loads(response[2]) == {
        "error": "provider_error",
        "reasonSubreason": reason_subreason,
        "statusClass": "5xx" if status_code == 500 else "4xx",
    }
    assert [audit.phase for audit in audits] == ["intent", "started", "failed"]
    assert audits[-1].status_class == ("5xx" if status_code == 500 else "4xx")
    assert audits[-1].reason_subreason == reason_subreason
    assert audits[-1].error_code == "provider_error"
    assert b"provider body must not persist" not in response[2]
    assert "provider body must not persist" not in repr(audits)


def test_provider_timeout_is_bounded_and_repeated_request_is_not_replayed(tmp_path):
    upstream = _FixtureUpstream(
        ProviderResponse(status_code=200, headers={}, body_chunks=(b"never",)),
        [],
    )

    def interrupted_upstream(request, credentials, is_cancelled):
        upstream.calls.append((request, credentials))
        raise TimeoutError("fixture upstream timeout with response body")

    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=interrupted_upstream, audit=audits.append)
    try:
        server.start()
        first = _round_trip(server, request_id="request:interrupted")
        second = _round_trip(server, request_id="request:interrupted")
    finally:
        server.close()

    assert first[0] == 403
    assert json.loads(first[2])["reasonSubreason"] == "upstream_timeout"
    assert second[0] == 403
    assert json.loads(second[2]) == {"error": "replay"}
    assert len(upstream.calls) == 1
    assert [audit.phase for audit in audits] == ["intent", "started", "outcome_unknown", "terminal"]
    assert audits[-1].reason_subreason == "upstream_timeout"


@pytest.mark.parametrize(
    ("error_type", "reason_subreason"),
    (
        (RuntimeError, "upstream_exception"),
        (HTTPException, "upstream_exception"),
        (OSError, "upstream_channel_closed"),
        (TimeoutError, "upstream_timeout"),
    ),
)
def test_provider_response_body_failure_is_terminal_unknown(
    tmp_path, error_type: type[Exception], reason_subreason: str
):
    def upstream(_request, _credentials, _is_cancelled):
        def body_chunks():
            yield b"data: partial\n\n"
            raise error_type("fixture response body failed")

        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=body_chunks(),
        )

    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, audit=audits.append)
    try:
        server.start()
        status, _headers, body = _round_trip(server, request_id="request:body-failure")
    finally:
        server.close()

    assert status == 403
    response = json.loads(body)
    assert response["error"] == "outcome_unknown"
    assert response["reasonSubreason"] == reason_subreason
    assert [audit.phase for audit in audits] == ["intent", "started", "outcome_unknown", "terminal"]
    assert audits[-1].reason_subreason == reason_subreason
    assert audits[-1].status_class == "transport"


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
    assert server.required_audit_failure is not None
    assert server.required_audit_failure.phase == "intent"
    assert server.required_audit_failure.code == "provider_attempt_evidence_rejected"


def test_runtime_service_promotes_provider_audit_rejection_before_provider_call(tmp_path, monkeypatch):
    state_file = tmp_path / "revocations.json"
    broker = RuntimeCredentialBroker(
        {"provider": {"api_key": "provider-secret"}},
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

    class RejectingHostClient:
        def __init__(self, *, url: str, auth_token: str):
            assert url == "http://plane-host.invalid"
            assert auth_token == "host-token"

        def invoke(self, call):
            callback_phases.append(call.input["phase"])
            return PlaneHostResult(
                request_ref=call.request_ref,
                correlation_id=call.correlation_id,
                idempotency_key=call.idempotency_key,
                status="denied",
                replayed=False,
                error_code="PROVIDER_ATTEMPT_REJECTED",
            )

    monkeypatch.setattr("plane.agent.runtime.service.PlaneHostHTTPClient", RejectingHostClient)
    opened: list[object] = []
    original_open = executor.open_provider_relay

    def open_and_capture(**kwargs):
        relay = original_open(**kwargs)
        opened.append(relay)
        return relay

    executor.open_provider_relay = open_and_capture  # type: ignore[method-assign]

    class RelayProbeTransport:
        def dispatch_payload(self, **_kwargs):
            relay = opened[0]
            response = _round_trip(relay.server, request_id="request:dispatch")
            assert response[0] == 403
            assert json.loads(response[2]) == {"error": "denied"}
            return ("child-failure-frame",)

    executor._transport = RelayProbeTransport()
    snapshot = {
        "runId": RUN_ID,
        "runtimePolicy": {
            "model": {"provider": PROVIDER, "model": MODEL},
            "adapter": "openai-compatible",
            "isolation": "single-invocation",
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

    try:
        with pytest.raises(RuntimeConfigurationError, match="provider attempt evidence"):
            executor._execute(
                snapshot,
                invocation,
                "test-digest",
                credentials=credentials,
                credential_lease=lease.public_metadata(),
                allowance=1,
                host_url="http://plane-host.invalid",
                host_token="host-token",
            )
    finally:
        for relay in opened:
            relay.close()

    assert callback_phases == ["intent", "failed"]
    assert opened[0].required_audit_failure.phase == "intent"
    assert opened[0].required_audit_failure.code == "provider_attempt_evidence_rejected"


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


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("provider request headers are oversized", "request_oversize"),
        ("provider request body is oversized", "request_oversize"),
        ("provider relay credentials are oversized", "request_oversize"),
        ("provider response is oversized", "response_oversize"),
        ("provider response chunk is oversized", "response_chunk_oversize"),
        ("provider request payload is oversized", "oversize"),
    ),
)
def test_provider_relay_preserves_bounded_oversize_origin(message: str, expected: str):
    assert ProviderRelayServer._error_code(ProviderRelayError(message)) == expected


def test_provider_relay_surfaces_budget_exhaustion_without_an_upstream_replay(tmp_path):
    upstream = _FixtureUpstream(ProviderResponse(status_code=200, headers={}, body_chunks=(b"ok",)), [])
    audits: list[ProviderRelayAudit] = []
    server = _server(tmp_path, upstream=upstream, max_calls=1, audit=audits.append)
    try:
        server.start()
        first = _round_trip(server, request_id="request:budget-1")
        second = _round_trip(server, request_id="request:budget-2")
    finally:
        server.close()

    assert first[0] == 200
    assert second[0] == 403
    assert json.loads(second[2]) == {"error": "budget_exhausted"}
    assert len(upstream.calls) == 1
    assert len(audits) == 5
    boundary_intent = audits[-2]
    assert boundary_intent.phase == "intent"
    assert boundary_intent.outcome == "allowed"
    assert boundary_intent.reason == "intent"
    assert boundary_intent.request_id == "request:budget-2"
    assert boundary_intent.sequence == 2
    assert boundary_intent.status_class == ""
    assert boundary_intent.error_code == ""
    assert boundary_intent.upstream_called is False
    boundary_audit = audits[-1]
    assert boundary_audit.phase == "failed"
    assert boundary_audit.outcome == "failed"
    assert boundary_audit.reason == "budget_exhausted"
    assert boundary_audit.request_id == "request:budget-2"
    assert boundary_audit.sequence == 2
    assert boundary_audit.status_class == "not_sent"
    assert boundary_audit.error_code == "budget_exhausted"
    assert boundary_audit.upstream_called is False


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
    assert configuration.provider_policy is not None
    assert configuration.provider_policy.max_request_bytes == 2 * 1024 * 1024
    assert configuration.provider_policy.max_response_bytes == 16 * 1024 * 1024
    assert configuration.provider_policy.max_concurrent_requests == 1
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


def test_runtime_budget_keeps_progressing_provider_request_inside_local_deadline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(provider_egress, "_RELAY_DRAIN_TIMEOUT_SECONDS", 0.05)
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

    monkeypatch.setattr(runtime_service, "PlaneHostHTTPClient", FixtureHostClient)
    body_started = threading.Event()
    audits: list[ProviderRelayAudit] = []

    def upstream(_request, _credentials, _cancelled):
        def body_chunks():
            body_started.set()
            time.sleep(0.15)
            yield b"data: response.completed\n\n"

        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=body_chunks(),
        )

    original_open = executor.open_provider_relay

    def open_with_fixture(**kwargs):
        return original_open(upstream=upstream, audit=audits.append, **kwargs)

    executor.open_provider_relay = open_with_fixture  # type: ignore[method-assign]
    child = textwrap.dedent(
        """
        import json
        import socket
        import sys

        socket_path = sys.argv[sys.argv.index('--provider-relay-socket') + 1]
        dispatch = json.loads(sys.stdin.buffer.readline())
        credentials = json.loads(sys.stdin.buffer.readline())['credentials']
        request = json.loads(sys.stdin.buffer.readline())
        body = b'{"model":"grok-4","messages":[]}'
        wire = (
            b'POST /v1/chat/completions HTTP/1.1\\r\\n'
            b'Host: plane-provider-relay.invalid\\r\\n'
            b'Authorization: Bearer ' + credentials['relayToken'].encode() + b'\\r\\n'
            b'Content-Type: application/json\\r\\n'
            + ('Content-Length: ' + str(len(body)) + '\\r\\n').encode()
            + b'Accept: text/event-stream\\r\\n'
            + b'X-Request-ID: request:deadline\\r\\n'
            + b'X-Plane-Relay-Invocation: invocation:relay\\r\\n'
            + b'X-Plane-Relay-Provider: xai\\r\\n'
            + b'X-Plane-Relay-Model: grok-4\\r\\n'
            + b'X-Plane-Relay-Run: run:relay\\r\\n\\r\\n'
            + body
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(2)
            channel.connect(socket_path)
            channel.sendall(wire)
            while channel.recv(4096):
                pass
        print('{"status":"completed"}', flush=True)
        """
    )
    from plane.agent.runtime.subprocess import RuntimeProcessPolicy, SubprocessRuntimeTransport

    executor._transport = SubprocessRuntimeTransport(
        command=(sys.executable, "-c", child),
        environment=dict(os.environ),
        ledger_path=tmp_path / "ledger.sqlite",
        timeout_seconds=0.05,
        process_policy=RuntimeProcessPolicy(enforce_kernel_policy=False),
    )
    executor.configuration = replace(configuration, command=(sys.executable, "-c", child))
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
        "remainingBudget": {"inputTokens": 1, "outputTokens": 1, "durationMs": 300},
    }
    caught: RuntimeDispatchError | None = None
    frames: tuple[str, ...] | None = None
    try:
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
    except RuntimeDispatchError as exc:
        caught = exc

    assert body_started.is_set(), "event=provider_request_started expected=true actual=false"
    assert caught is None, (
        "event=runtime_budget_repro operation=provider_request risk=late_local_kill "
        f"expected=completed actual={caught.public_failure() if caught else 'unknown'}"
    )
    assert frames == ('{"status":"completed"}',)
    assert [audit.phase for audit in audits] == ["intent", "started", "completed"]
    assert callback_phases == ["intent", "started", "completed"]


@pytest.mark.parametrize("dispatch_failure", (False, True), ids=("dispatch-returns", "dispatch-raises"))
def test_runtime_service_drains_relay_before_host_close_and_checks_late_audit(
    tmp_path, monkeypatch, dispatch_failure
):
    state_file = tmp_path / "revocations.json"
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
    events: list[str] = []

    class FixtureHostServer:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            events.append("host.start")

        def close(self):
            events.append("host.close")

    class FixtureRelay:
        def __init__(self):
            self.descriptor = provider_egress.ProviderRelayDescriptor(
                socket_path=tmp_path / "relay.sock",
                token="relay-token-012345678901234567890123456789",
            )
            self._required_audit_failure = None

        @property
        def required_audit_failure(self):
            return self._required_audit_failure

        def close(self):
            events.append("relay.close")
            self._required_audit_failure = provider_egress.ProviderRelayAuditFailure(phase="completed")

    relay = FixtureRelay()
    monkeypatch.setattr(runtime_service, "PlaneHostServer", FixtureHostServer)
    monkeypatch.setattr(
        runtime_service,
        "_hermes_bootstrap_payload",
        lambda *_args, **_kwargs: (b"payload", RUN_ID, INVOCATION_ID, "bootstrap-digest"),
    )
    executor.open_provider_relay = lambda **_kwargs: relay  # type: ignore[method-assign]

    class FixtureTransport:
        def dispatch_payload(self, **_kwargs):
            if dispatch_failure:
                raise ValueError("fixture dispatch failed")
            return ("frame",)

    executor._transport = FixtureTransport()
    snapshot = {
        "runId": RUN_ID,
        "runtimePolicy": {"model": {"provider": PROVIDER, "model": MODEL}},
    }
    invocation = {"runId": RUN_ID, "invocationId": INVOCATION_ID, "correlationId": "correlation:relay"}
    with pytest.raises(RuntimeConfigurationError, match="provider attempt evidence") as raised:
        executor._execute(
            snapshot,
            invocation,
            "test-digest",
            credentials={"api_key": "provider-secret"},
            credential_lease={"leaseId": "lease:relay"},
            allowance=1,
            host_url="http://plane-host.invalid",
            host_token="host-token",
        )

    if dispatch_failure:
        assert isinstance(raised.value.__cause__, ValueError)
    assert events == ["host.start", "relay.close", "host.close"]


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

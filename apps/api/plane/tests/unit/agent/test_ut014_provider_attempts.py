# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider-free UT-014 coverage for multi-exchange provider audit."""

from __future__ import annotations

import hashlib
import json
import socket
import threading

import pytest
from django.core.management import call_command
from django.test import override_settings

from plane.agent.lifecycle import record_provider_attempt_notice
from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostCall,
    PlaneHostHTTPClient,
)
from plane.agent.runtime.health import RuntimeSafetyController
from plane.agent.runtime.provider_egress import ProviderRequest, ProviderResponse
from plane.agent.runtime.service import RuntimeDispatchExecutor, _RuntimeHTTPServer
from plane.db.management.commands import agent_supervisor as supervisor_command
from plane.db.models import (
    InvocationState,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
)


def _provider_request(relay, *, request_id: str, run_id: str, invocation_id: str) -> int:
    body = json.dumps(
        {"input": [], "model": "gpt-5.6-luna"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    headers = {
        "Host": "plane-provider-relay.invalid",
        "Authorization": f"Bearer {relay.descriptor.token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Content-Length": str(len(body)),
        "Connection": "close",
        "X-Request-ID": request_id,
        "X-Plane-Relay-Invocation": invocation_id,
        "X-Plane-Relay-Provider": "openai-codex",
        "X-Plane-Relay-Model": "gpt-5.6-luna",
        "X-Plane-Relay-Run": run_id,
    }
    wire = (
        "POST /backend-api/codex/responses HTTP/1.1\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        + "\r\n"
    ).encode() + body
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(3)
        channel.connect(str(relay.descriptor.socket_path))
        channel.sendall(wire)
        response = bytearray()
        while True:
            chunk = channel.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
    return int(bytes(response).split(b" ", 2)[1])


def _runtime_frames(payload: bytes) -> tuple[str, ...]:
    request = json.loads(payload.splitlines()[-1])
    snapshot = request["run"]
    envelope = request["invocation"]
    event = {
        "protocol": "plane.agent-runtime/v1",
        "trust": "untrusted",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "sequence": 0,
        "eventId": "event:ut014-usage",
        "idempotencyKey": "idempotency:ut014-usage",
        "correlationId": envelope["correlationId"],
        "causationRef": envelope["causationRef"],
        "observedAt": envelope["lease"]["expiresAt"],
        "body": {
            "kind": "usage_observed",
            "usage": {"inputTokens": 1, "outputTokens": 1, "durationMs": 1},
            "publication": {"action": "observation_only"},
        },
    }
    exit_frame = {
        "protocol": "plane.agent-runtime/v1",
        "authority": "runtime_evidence_only",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "finalSequence": 0,
        "idempotencyKey": envelope["idempotencyKey"],
        "correlationId": envelope["correlationId"],
        "causationRef": envelope["causationRef"],
        "kind": "completed",
    }
    return tuple(json.dumps(frame, sort_keys=True, separators=(",", ":")) for frame in (event, exit_frame))


@pytest.mark.django_db(transaction=True)
def test_ut014_multiturn_provider_audit_does_not_consume_host_callback_budget(
    tmp_path, workspace, gateway_project, gateway_issue, create_user, monkeypatch
):
    """Nine model exchanges use required audit callbacks without widening model budgets."""

    from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run, record_invocation
    from plane.agent.runtime import host_rpc, service
    from plane.db.models import AgentRole

    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="UT-014 provider worker",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Exercise bounded provider exchange evidence.",
        runtime_defaults={"provider": "openai-codex", "model": "gpt-5.6-luna", "adapter": "hermes"},
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Persist bounded provider exchanges.",
        acceptance_criteria=["Nine completed provider exchanges remain ordered and replay-safe."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:ut014-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:ut014-invocation", trigger="initial")

    callback_calls: list[tuple[PlaneHostCall, object]] = []
    captured_clients: list[PlaneHostHTTPClient] = []
    captured_servers: list[object] = []
    provider_calls: list[ProviderRequest] = []
    relays: list[object] = []
    product_callback_statuses: list[str] = []
    provider_budget_statuses: list[int] = []
    total_budget_statuses: list[str] = []
    total_budget_error_codes: list[str | None] = []
    invalid_callback_results: dict[str, object] = {}

    class CapturingHostClient(PlaneHostHTTPClient):
        def __init__(self, *, url: str, auth_token: str):
            super().__init__(url=url, auth_token=auth_token)
            captured_clients.append(self)

        def invoke(self, call):
            result = super().invoke(call)
            callback_calls.append((call, result))
            return result

    class CapturingHostHTTPServer(host_rpc.PlaneHostHTTPServer):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured_servers.append(self)

    monkeypatch.setattr(service, "PlaneHostHTTPClient", CapturingHostClient)
    monkeypatch.setattr(supervisor_command, "PlaneHostHTTPServer", CapturingHostHTTPServer)

    def fake_provider(request: ProviderRequest, credentials: dict[str, str], _cancelled) -> ProviderResponse:
        assert credentials == {"api_key": "synthetic-provider-secret"}
        provider_calls.append(request)
        return ProviderResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            body_chunks=(b"data: [DONE]\n\n",),
        )

    class ExchangeTransport:
        def dispatch_payload(self, *, payload, **_kwargs):
            assert captured_clients
            client = captured_clients[0]
            for exchange in range(1, 10):
                status = _provider_request(
                    relays[0],
                    request_id=f"request:ut014-{exchange}",
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                )
                assert status == 200
                if exchange <= 8:
                    result = client.invoke(
                        PlaneHostCall(
                            run_id=run.snapshot["runId"],
                            invocation_id=invocation.invocation_id,
                            correlation_id=f"correlation:{run.id}",
                            action="discover",
                            operation_ref="plane.operations.discover@1",
                            input={"query": f"exchange-{exchange}", "limit": 1},
                            source="model",
                        )
                    )
                    product_callback_statuses.append(result.status)
                    assert result.status == "ok"
                if exchange == 9:
                    provider_budget_statuses.append(
                        _provider_request(
                            relays[0],
                            request_id="request:ut014-10",
                            run_id=run.snapshot["runId"],
                            invocation_id=invocation.invocation_id,
                        )
                    )

            submit = client.invoke(
                PlaneHostCall(
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="mutate",
                    operation_ref="operation:agent.outcome.submit",
                    input={
                        "run_ref": run.snapshot["runId"],
                        "summary": "Nine bounded provider exchanges completed.",
                        "artifacts": ["artifact:ut014-provider-audit"],
                        "evidence": ["evidence:ut014-provider-audit"],
                    },
                    source="model",
                )
            )
            assert submit.status == "ok", submit
            outcome_ref = submit.output["result"]["outcome"]["outcomeRef"]
            publish = client.invoke(
                PlaneHostCall(
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="publish",
                    operation_ref="operation:agent.outcome.publish",
                    input={
                        "kind": "outcome",
                        "resourceRef": outcome_ref,
                        "content": "Explicit UT-014 provider audit publication.",
                    },
                    source="model",
                )
            )
            assert publish.status == "ok", publish

            exact_input = {
                key: value
                for key, value in notices[-1].items()
                if key not in {"runId", "invocationId"}
            }
            exact_call = PlaneHostCall(
                run_id=run.snapshot["runId"],
                invocation_id=invocation.invocation_id,
                correlation_id=f"correlation:{run.id}",
                action="observe",
                operation_ref="runtime.provider_attempt",
                input=exact_input,
                source="runtime",
            )
            invalid_callback_results["replay"] = client.invoke(exact_call)

            mismatched_input = dict(exact_input)
            mismatched_input["statusClass"] = "299"
            invalid_callback_results["mismatched"] = client.invoke(
                PlaneHostCall(
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="observe",
                    operation_ref="runtime.provider_attempt",
                    input=mismatched_input,
                    source="runtime",
                )
            )

            out_of_order_input = dict(exact_input)
            out_of_order_input.update(
                {
                    "phase": "intent",
                    "requestId": "request:ut014-out-of-order",
                    "idempotencyKey": "provider-attempt:ut014-out-of-order",
                    "sequence": 12,
                    "upstreamInitiated": False,
                    "statusClass": "",
                    "errorCode": "",
                }
            )
            invalid_callback_results["outOfOrder"] = client.invoke(
                PlaneHostCall(
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="observe",
                    operation_ref="runtime.provider_attempt",
                    input=out_of_order_input,
                    source="runtime",
                )
            )
            invalid_callback_results["crossBound"] = client.invoke(
                PlaneHostCall(
                    run_id="run:ut014-other",
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="observe",
                    operation_ref="runtime.provider_attempt",
                    input=exact_input,
                    source="runtime",
                )
            )
            for callback in range(22):
                result = client.invoke(
                    PlaneHostCall(
                        run_id=run.snapshot["runId"],
                        invocation_id=invocation.invocation_id,
                        correlation_id=f"correlation:{run.id}",
                        action="read",
                        operation_ref="unsupported:budget",
                        input={"query": f"budget-{callback}"},
                        source="model",
                    )
                )
                total_budget_statuses.append(result.status)
                total_budget_error_codes.append(result.error_code)
            overflow = client.invoke(
                PlaneHostCall(
                    run_id=run.snapshot["runId"],
                    invocation_id=invocation.invocation_id,
                    correlation_id=f"correlation:{run.id}",
                    action="read",
                    operation_ref="unsupported:budget-overflow",
                    input={"query": "budget-overflow"},
                    source="model",
                )
            )
            total_budget_statuses.append(overflow.status)
            total_budget_error_codes.append(overflow.error_code)
            return _runtime_frames(payload)

    class ExactExecutor(RuntimeDispatchExecutor):
        def open_provider_relay(self, **kwargs):
            relay = super().open_provider_relay(upstream=fake_provider, **kwargs)
            relays.append(relay)
            return relay

    shared_secret = "ut014-runtime-secret-0123456789x"
    state_file = tmp_path / "ut014-credential-state.json"
    runtime_environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": shared_secret,
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "runtime-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "runtime-stop"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(state_file),
        "PLANE_AGENT_RUNTIME_PROVIDER": "openai-codex",
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "chatgpt.com",
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "/backend-api/codex/responses",
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "gpt-5.6-luna",
        "PLANE_AGENT_RUNTIME_PROVIDER_MAX_CALLS": "9",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": "{}",
    }
    configuration = AgentRuntimeConfiguration.from_environment(runtime_environment)
    controller = RuntimeSafetyController(configured=True, stop_file=configuration.safety_stop_file)
    controller.mark_ready()
    executor = ExactExecutor(configuration, controller)
    executor._transport = ExchangeTransport()
    runtime = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    runtime_thread = threading.Thread(target=runtime.serve_forever, daemon=True)
    runtime_thread.start()

    real_recorder = supervisor_command.record_provider_attempt_notice
    notices: list[dict[str, object]] = []

    def record_notice(current_invocation, notice):
        attempt = real_recorder(current_invocation, notice)
        notices.append(dict(notice))
        return attempt

    monkeypatch.setattr(supervisor_command, "record_provider_attempt_notice", record_notice)
    try:
        with override_settings(
            PLANE_AGENT_RUNTIME_URL=f"http://127.0.0.1:{runtime.server_port}",
            PLANE_AGENT_RUNTIME_SHARED_SECRET=shared_secret,
            PLANE_AGENT_RUNTIME_HOST_URL="http://127.0.0.1",
            PLANE_AGENT_RUNTIME_HOST_BIND="127.0.0.1",
            PLANE_AGENT_RUNTIME_HOST_PORT=0,
            PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={
                "runtime": {"api_key": "synthetic-provider-secret"},
            },
            PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(state_file),
            PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS=30,
            PLANE_AGENT_RUNTIME_COMMAND="python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        ):
            call_command(
                "agent_supervisor",
                invocation_ref=invocation.invocation_id,
                worker_id="worker:ut014",
                model_call_allowance=9,
                stdout=None,
            )
    finally:
        runtime.shutdown()
        runtime.server_close()
        runtime_thread.join(timeout=2)

    invocation.refresh_from_db()
    attempts = list(RuntimeProviderAttempt.objects.filter(invocation=invocation).order_by("sequence"))
    rejected_callbacks = [
        {
            "phase": call.input.get("phase"),
            "sequence": call.input.get("sequence"),
            "requestId": call.input.get("requestId"),
            "idempotencyKey": call.input.get("idempotencyKey"),
            "status": result.status,
            "errorCode": result.error_code,
        }
        for call, result in callback_calls
        if result.status not in {"ok", "replayed"}
    ]
    assert invocation.state == InvocationState.SUCCEEDED, {
        "state": invocation.state,
        "persistedSequences": [attempt.sequence for attempt in attempts],
        "hostCallCount": captured_servers[0]._call_count if captured_servers else None,
        "firstRejectedCallback": rejected_callbacks[0] if rejected_callbacks else None,
        "noticeCount": len(notices),
    }
    assert len(provider_calls) == 9
    assert product_callback_statuses == ["ok"] * 8
    assert [attempt.sequence for attempt in attempts] == list(range(1, 11))
    assert [attempt.phase for attempt in attempts] == [RuntimeProviderAttemptPhase.COMPLETED] * 9 + [
        RuntimeProviderAttemptPhase.FAILED
    ]
    assert [notice["phase"] for notice in notices] == [
        phase for _ in range(9) for phase in ("intent", "started", "completed")
    ] + ["intent", "failed"]
    assert attempts[-1].error_code == "budget_exhausted"
    assert provider_budget_statuses == [403]
    assert total_budget_statuses == ["invalid"] * 22 + ["denied"]
    assert total_budget_error_codes == ["VALIDATION_ERROR"] * 22 + ["HOST_BUDGET_EXCEEDED"]
    assert invalid_callback_results["replay"].status == "replayed"
    assert invalid_callback_results["mismatched"].status not in {"ok", "replayed"}
    assert invalid_callback_results["mismatched"].error_code == "PROVIDER_ATTEMPT_REJECTED"
    assert invalid_callback_results["outOfOrder"].status not in {"ok", "replayed"}
    assert invalid_callback_results["outOfOrder"].error_code == "PROVIDER_ATTEMPT_REJECTED"
    assert invalid_callback_results["crossBound"].status == "denied"
    assert invalid_callback_results["crossBound"].error_code == "CALLBACK_BINDING_INVALID"
    assert captured_servers[0].call_count == 32
    assert captured_servers[0].observation_count == 32

    exact_replay = dict(notices[-1])
    replayed = record_provider_attempt_notice(invocation, exact_replay)
    assert replayed.id == attempts[-1].id
    assert RuntimeProviderAttempt.objects.filter(invocation=invocation).count() == 10

    out_of_order = dict(exact_replay)
    out_of_order.update(
        {
            "phase": "intent",
            "requestId": "request:ut014-out-of-order",
            "idempotencyKey": "provider-attempt:ut014-out-of-order",
            "sequence": 12,
            "upstreamInitiated": False,
            "statusClass": "",
            "errorCode": "",
        }
    )
    with pytest.raises(Exception, match="sequence"):
        record_provider_attempt_notice(invocation, out_of_order)

        cross_bound = dict(out_of_order)
        with pytest.raises(Exception, match="bound"):
            supervisor_command._provider_attempt_notice_for_plane(invocation, type("Call", (), {
            "run_id": "run:ut014-other",
            "invocation_id": invocation.invocation_id,
            "input": cross_bound,
        })())

    assert hashlib.sha256(b"request:ut014-10").hexdigest() in notices[-1]["idempotencyKey"]

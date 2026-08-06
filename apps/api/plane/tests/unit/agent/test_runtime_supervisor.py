"""Production-entrypoint contracts for the Plane runtime supervisor."""

import json
import os
import re
import subprocess
import sys
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run, record_invocation
from plane.agent.runtime import RuntimeDispatchError
from plane.agent.runtime.supervisor import request_runtime_cancellation, run_runtime_invocation
from plane.db.models import (
    AgentActor,
    AgentRole,
    AssignmentContract,
    InvocationState,
    OutcomeSubmission,
    ProfileVersion,
    RunAttempt,
    RunState,
    RunTerminalEvent,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeUsageObservation,
    RuntimeControlState,
    RuntimeInvocationControl,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


def _runtime_frames(snapshot, envelope):
    event = {
        "protocol": "plane.agent-runtime/v1",
        "trust": "untrusted",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "sequence": 0,
        "eventId": "event:supervisor-usage",
        "idempotencyKey": "idempotency:supervisor-usage",
        "correlationId": envelope["correlationId"],
        "causationRef": envelope["causationRef"],
        "observedAt": envelope["lease"]["expiresAt"],
        "body": {
            "kind": "usage_observed",
            "usage": {"inputTokens": 2, "outputTokens": 3, "durationMs": 4},
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
        "kind": "failed",
        "failure": {
            "code": "runtime_error",
            "message": "child exited before an explicit outcome",
            "retryable": False,
        },
    }
    return tuple(json.dumps(frame, sort_keys=True, separators=(",", ":")) for frame in (event, exit_frame))


class FailingRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        return _runtime_frames(json.loads(snapshot_json), json.loads(envelope_json))


class StaticRuntimeTransport:
    def __init__(self, frames):
        self.frames = tuple(frames)
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        return self.frames


class UnknownRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        raise RuntimeDispatchError("runtime process did not produce a durable terminal result")


def _invocation(workspace, gateway_project, gateway_issue, create_user, *, runtime_defaults=None, suffix="extra"):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name=f"Supervisor worker {suffix}",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Run the assigned work.",
        runtime_defaults=runtime_defaults,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the runtime supervisor.",
        acceptance_criteria=["The result is durable."],
        created_by=create_user,
    )
    run = create_run(
        assignment, profile, idempotency_key=f"idempotency:supervisor-run-{suffix}", created_by=create_user
    )
    return run, record_invocation(run, idempotency_key=f"idempotency:supervisor-invocation-{suffix}", trigger="initial")


@pytest.mark.django_db(transaction=True)
def test_supervisor_entrypoint_ingests_usage_and_creates_one_visible_failure(
    workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Supervisor worker",
        created_by=create_user,
    )
    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Run the assigned work.")
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the real supervisor entrypoint.",
        acceptance_criteria=["One visible terminal failure is durable."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:supervisor-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:supervisor-invocation", trigger="initial")
    transport = FailingRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    assert result.state == InvocationState.FAILED
    assert transport.calls == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert RuntimeUsageObservation.objects.get(invocation=invocation).usage == {
        "inputTokens": 2,
        "outputTokens": 3,
        "durationMs": 4,
    }
    run.refresh_from_db()
    assert run.state == RunState.FAILED


@pytest.mark.django_db(transaction=True)
def test_supervisor_replays_terminal_invocation_without_a_new_child_or_terminal_event(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user)
    transport = FailingRuntimeTransport()

    first = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    second = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    assert first.state == second.state == InvocationState.FAILED
    assert transport.calls == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_cancellation_is_durable_and_prevents_dispatch(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="cancel")
    transport = FailingRuntimeTransport()

    cancelled = request_runtime_cancellation(invocation, reason="operator requested stop")
    result = run_runtime_invocation(cancelled, transport=transport, worker_id="worker:test")

    assert result.state == InvocationState.CANCELLED
    assert transport.calls == 0
    assert RunTerminalEvent.objects.filter(run=run, kind="run_cancellation", visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_malformed_callback_becomes_one_visible_failure(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="malformed")
    result = run_runtime_invocation(
        invocation,
        transport=StaticRuntimeTransport(("not-json",)),
        worker_id="worker:test",
    )

    assert result.state == InvocationState.FAILED
    assert result.terminal_kind == "run_failure"
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_timeout_or_process_death_is_outcome_unknown_and_not_replayed(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="unknown")
    transport = UnknownRuntimeTransport()

    first = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    second = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    assert first.terminal_kind == second.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert control.failure_code == "outcome_unknown"
    assert transport.calls == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_budget_exhaustion_is_reconciled_as_failure(workspace, gateway_project, gateway_issue, create_user):
    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults={"totalBudget": {"inputTokens": 1, "outputTokens": 1, "durationMs": 1}},
        suffix="budget",
    )
    result = run_runtime_invocation(
        invocation,
        transport=FailingRuntimeTransport(),
        worker_id="worker:test",
    )

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    assert result.state == InvocationState.FAILED
    assert control.failure_code == "budget_exhausted"
    assert not RuntimeUsageObservation.objects.filter(invocation=invocation).exists()


@pytest.mark.django_db(transaction=True)
def test_expired_lease_escalates_unknown_without_dispatch(workspace, gateway_project, gateway_issue, create_user):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="lease")
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    control.state = RuntimeControlState.LEASED
    control.lease_expires_at = timezone.now() - timedelta(seconds=1)
    control.save(_allow_lifecycle=True, update_fields=["state", "lease_expires_at", "updated_at"])
    transport = FailingRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control.refresh_from_db()
    assert result.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert transport.calls == 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_configured_hermes_sha_runs_the_real_supervisor_production_path(
    tmp_path, api_key_client, workspace, gateway_project, gateway_issue, create_user, capsys
):
    checkout = os.environ.get("PLANE_G2_HERMES_CHECKOUT", "/hermes")
    expected_sha = "e573a46611e2cb988f1ab43ad34cd8cc3b2cb659"
    assert os.path.isdir(checkout)
    actual_sha = subprocess.run(
        ["git", "-C", checkout, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    assert actual_sha == expected_sha
    command = ("python3", "-m", "plane_runtime.g1_runtime_image.bootstrap", "--once", "--g1-production")
    assert command[1:] == ("-m", "plane_runtime.g1_runtime_image.bootstrap", "--once", "--g1-production")

    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 production worker",
        credential_ref="plane-credential:g2-production",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions=(
            "Discover, read, use restricted Code Mode, rename, submit, and publish one outcome."
        ),
        runtime_defaults={
            "provider": "openai",
            "model": "deterministic-local",
            "adapter": "hermes",
            "maxCodeModeCalls": 16,
            "maxCodeModeOutputBytes": 131_072,
        },
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Change the assigned issue title.",
        acceptance_criteria=["Title changed."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-real-supervisor", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g2-real-invocation", trigger="initial")

    provider_key = "local-g2-provider-secret"
    model_requests = []
    tool_calls = []
    code_callbacks = []
    provider_errors = []
    provider_stream_count = 0
    issue_id = str(gateway_issue.id)
    project_id = str(gateway_project.id)
    run_ref = run.snapshot["runId"]

    class LocalOpenAIHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal provider_stream_count
            size = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(size))
            model_requests.append(request)
            if request.get("stream") is not True:
                body = {
                    "id": "chatcmpl-g2-probe",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "deterministic-local",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "local probe", "tool_calls": None},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                content_type = "application/json"
            else:
                provider_stream_count += 1
                if provider_stream_count == 1:
                    function_name = "tool_search"
                    arguments = {"query": "Plane work item", "limit": 5}
                elif provider_stream_count == 2:
                    function_name = "tool_describe"
                    arguments = {"name": "plane_operation"}
                elif provider_stream_count == 3:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "discover",
                            "operationRef": "plane.operations.discover@1",
                            "input": {"query": "work item", "limit": 32},
                        },
                    }
                elif provider_stream_count == 4:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "read",
                            "operationRef": "operation:work_item.read",
                            "input": {"project_id": project_id, "issue_id": issue_id},
                        },
                    }
                elif provider_stream_count == 5:
                    function_name = "execute_code"
                    arguments = {
                        "code": (
                            "from hermes_tools import plane_operation\n"
                            "print(plane_operation(\"code\", \"operation:catalog.search\", "
                            "{\"query\": \"rename\", \"limit\": 5}))"
                        )
                    }
                    code_callbacks.append(arguments["code"])
                elif provider_stream_count == 6:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "mutate",
                            "operationRef": "operation:work_item.rename",
                            "input": {
                                "project_id": project_id,
                                "issue_id": issue_id,
                                "name": "G2 production renamed",
                            },
                        },
                    }
                elif provider_stream_count == 7:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "mutate",
                            "operationRef": "operation:agent.outcome.submit",
                            "input": {
                                "run_ref": run_ref,
                                "summary": "The assigned issue was renamed through the Plane gateway.",
                                "artifacts": ["artifact:g2-production"],
                                "evidence": ["evidence:g2-production"],
                            },
                        },
                    }
                elif provider_stream_count == 8:
                    function_name = "tool_call"
                    match = re.search(r"outcome-submission:[0-9a-f-]+", json.dumps(request, sort_keys=True))
                    if match is None:
                        provider_errors.append("the publish request did not contain the submitted outcome ref")
                        resource_ref = "outcome-submission:missing"
                    else:
                        resource_ref = match.group(0)
                    arguments = {
                        "name": "plane_publish",
                        "arguments": {
                            "kind": "outcome",
                            "operationRef": "operation:agent.outcome.publish",
                            "resourceRef": resource_ref,
                            "content": "Explicit outcome publication.",
                        },
                    }
                else:
                    function_name = None
                    arguments = None
                if function_name is None:
                    chunk = {
                        "id": "chatcmpl-g2-final",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "deterministic-local",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": "ordinary final text only"},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                else:
                    tool_calls.append(function_name)
                    chunk = {
                        "id": "chatcmpl-g2-tool",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "deterministic-local",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": f"call-g2-{provider_stream_count}",
                                            "type": "function",
                                            "function": {
                                                "name": function_name,
                                                "arguments": json.dumps(
                                                    arguments, sort_keys=True, separators=(",", ":")
                                                ),
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }
                usage_chunk = {
                    "id": "chatcmpl-g2-usage",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "deterministic-local",
                    "choices": [],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                }
                raw = (
                    "data: "
                    + json.dumps(chunk, sort_keys=True, separators=(",", ":"))
                    + "\n\n"
                    + "data: "
                    + json.dumps(usage_chunk, sort_keys=True, separators=(",", ":"))
                    + "\n\ndata: [DONE]\n\n"
                ).encode()
                content_type = "text/event-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            return

    provider = ThreadingHTTPServer(("127.0.0.1", 0), LocalOpenAIHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    dependency_path = os.environ.get("PLANE_G2_HERMES_DEPENDENCY_PATH")
    if dependency_path:
        assert os.path.isdir(dependency_path)
    runtime_pythonpath = os.pathsep.join(path for path in (dependency_path, checkout) if path)
    runtime_environment = {
        "HOME": str(hermes_home),
        "HERMES_HOME": str(hermes_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin",
        "PYTHONPATH": runtime_pythonpath,
        "PYTHONUNBUFFERED": "1",
    }
    try:
        with override_settings(
            PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={
                "runtime": {
                    "api_key": provider_key,
                    "base_url": f"http://127.0.0.1:{provider.server_port}/v1",
                    "api_mode": "chat_completions",
                }
            },
            PLANE_AGENT_RUNTIME_ENVIRONMENT=runtime_environment,
            APP_BASE_URL="http://127.0.0.1",
        ):
            call_command(
                "agent_supervisor",
                invocation_ref=invocation.invocation_id,
                worker_id="worker:g2-real",
                lease_seconds=300,
                runtime_command=list(command),
                runtime_cwd=checkout,
                runtime_checkout=checkout,
                runtime_sha=expected_sha,
                ledger_path=str(tmp_path / "g2-real-ledger.sqlite"),
                model_call_allowance=16,
            )
            supervisor_output = capsys.readouterr().out
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=2)

    assert not provider_thread.is_alive()
    assert not provider_errors
    assert provider_stream_count == 9, {
        "provider_stream_count": provider_stream_count,
        "tool_calls": tool_calls,
        "invocation_state": invocation.state,
        "control": RuntimeInvocationControl.objects.get(invocation=invocation).failure_reason,
        "terminal": list(RunTerminalEvent.objects.filter(run=run).values("kind", "reason")),
        "gateway": list(
            OperationGatewayAudit.objects.filter(caller_id=actor.principal_id).values_list(
                "operation_id", "phase", "outcome", "error_code"
            )
        ),
        "outcomes": OutcomeSubmission.objects.filter(run=run).count(),
    }
    assert tool_calls == [
        "tool_search",
        "tool_describe",
        "tool_call",
        "tool_call",
        "execute_code",
        "tool_call",
        "tool_call",
        "tool_call",
    ]
    assert code_callbacks == [
        'from hermes_tools import plane_operation\n'
        'print(plane_operation("code", "operation:catalog.search", '
        '{"query": "rename", "limit": 5}))'
    ]
    assert "state=succeeded" in supervisor_output
    assert provider_key not in supervisor_output
    assert provider_key not in json.dumps(model_requests, sort_keys=True)

    gateway_issue.refresh_from_db()
    invocation.refresh_from_db()
    run.refresh_from_db()
    assert invocation.state == InvocationState.SUCCEEDED
    assert gateway_issue.name == "G2 production renamed"
    assert OutcomeSubmission.objects.filter(run=run).count() == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert AgentActor.objects.filter(workspace=workspace, project=gateway_project).count() == 1
    assert ProfileVersion.objects.filter(actor=actor).count() == 1
    assert AssignmentContract.objects.filter(assignee=actor).count() == 1
    assert RunAttempt.objects.filter(actor=actor).count() == 1
    assert invocation.run_id == run.id
    assert RuntimeInvocationControl.objects.filter(invocation=invocation).count() == 1
    assert RuntimeEventIngress.objects.filter(invocation=invocation).count() >= 1
    assert RuntimeExitEvidence.objects.filter(invocation=invocation).count() == 1
    assert RuntimeUsageObservation.objects.filter(invocation=invocation).count() == 1

    correlation_id = f"correlation:{run.id}"
    expected_operations = {
        "catalog.search",
        "work_item.read",
        "work_item.rename",
        "agent.outcome.submit",
        "agent.outcome.publish",
    }
    receipts = OperationGatewayIdempotency.objects.filter(
        caller_id=actor.principal_id,
        workspace_slug=workspace.slug,
        correlation_id=correlation_id,
    )
    assert set(receipts.values_list("operation_id", flat=True)) == expected_operations
    assert receipts.count() == len(expected_operations) + 1
    assert receipts.filter(operation_id="catalog.search").count() == 2
    audits = OperationGatewayAudit.objects.filter(
        caller_id=actor.principal_id,
        workspace_slug=workspace.slug,
        correlation_id=correlation_id,
    )
    assert audits.count() == receipts.count() * 2
    assert set(audits.values_list("phase", flat=True)) == {"intent", "outcome"}
    assert all(audits.filter(request_id=receipt.request_id).count() == 2 for receipt in receipts)

    api_response = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/agent-admin/runs/{run.id}/?per_page=1")
    assert api_response.status_code == 200
    api_readback = api_response.json()
    call_command("agent_readback", workspace_slug=workspace.slug, run_id=str(run.id), limit=1)
    cli_readback = json.loads(capsys.readouterr().out)
    assert cli_readback == api_readback
    assert len(json.dumps(cli_readback, sort_keys=True).encode()) <= 8 * 1024
    assert provider_key not in json.dumps(api_readback, sort_keys=True)
    runtime_event_text = json.dumps(
        list(RuntimeEventIngress.objects.filter(invocation=invocation).values_list("raw_payload", flat=True)),
        sort_keys=True,
    )
    assert 'Plane host model read operation:work_item.read -> ok' in runtime_event_text
    assert 'Plane host model mutate operation:work_item.rename -> ok' in runtime_event_text
    assert OperationGatewayAudit.objects.filter(
        caller_id=actor.principal_id,
        operation_id="catalog.search",
        phase="outcome",
        outcome="success",
        correlation_id=correlation_id,
    ).count() == 2
    assert "ordinary final text only" in runtime_event_text
    assert "ordinary final text only" not in json.dumps(
        list(OperationGatewayAudit.objects.filter(caller_id=actor.principal_id).values_list("result", flat=True)),
        sort_keys=True,
    )

    before_replay = {
        "provider_streams": provider_stream_count,
        "receipts": OperationGatewayIdempotency.objects.filter(correlation_id=correlation_id).count(),
        "audits": audits.count(),
        "usage": RuntimeUsageObservation.objects.filter(invocation=invocation).count(),
        "outcomes": OutcomeSubmission.objects.filter(run=run).count(),
        "terminals": RunTerminalEvent.objects.filter(run=run, visible=True).count(),
        "issue_name": gateway_issue.name,
    }
    replay_output = ""
    with override_settings(
        PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={
            "runtime": {
                "api_key": provider_key,
                "base_url": "http://127.0.0.1:1/v1",
                "api_mode": "chat_completions",
            }
        },
        PLANE_AGENT_RUNTIME_ENVIRONMENT=runtime_environment,
    ):
        call_command(
            "agent_supervisor",
            invocation_ref=invocation.invocation_id,
            worker_id="worker:g2-replay",
            runtime_command=list(command),
            runtime_cwd=checkout,
            runtime_checkout=checkout,
            runtime_sha=expected_sha,
            ledger_path=str(tmp_path / "g2-real-ledger.sqlite"),
            model_call_allowance=16,
        )
        replay_output = capsys.readouterr().out
    after_replay = {
        "provider_streams": provider_stream_count,
        "receipts": OperationGatewayIdempotency.objects.filter(correlation_id=correlation_id).count(),
        "audits": audits.count(),
        "usage": RuntimeUsageObservation.objects.filter(invocation=invocation).count(),
        "outcomes": OutcomeSubmission.objects.filter(run=run).count(),
        "terminals": RunTerminalEvent.objects.filter(run=run, visible=True).count(),
        "issue_name": gateway_issue.name,
    }
    assert after_replay == before_replay
    assert "state=succeeded" in replay_output

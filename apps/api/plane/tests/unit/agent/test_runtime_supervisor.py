"""Production-entrypoint contracts for the Plane runtime supervisor."""

import json
import hashlib
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from plane.agent.lifecycle import (
    InvalidTransitionError,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    propose_outcome,
    record_invocation,
    record_provider_attempt_notice,
)
from plane.db.management.commands.agent_supervisor import (
    _SupervisorSetupFailure,
    _provider_attempt_notice_for_plane,
    _supervisor_setup_stage,
    _supervisor_result_output,
)
from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    build_gateway_host_port,
    PlaneHostHTTPServer,
    RemoteRuntimeTransport,
    RuntimeCredentialBroker,
    RuntimeCredentialError,
    RuntimeDispatchError,
    RuntimeHostEndpoint,
)
from plane.agent.runtime.supervisor import (
    request_runtime_cancellation,
    run_runtime_invocation,
    terminalize_pre_dispatch_failure,
)
from plane.operation_gateway.gateway import OperationGateway
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
    RuntimeInvocation,
    RuntimeUsageObservation,
    RuntimeControlState,
    RuntimeInvocationControl,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


def _runtime_frames(snapshot, envelope, *, failure=None):
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
        "failure": failure
        or {
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


class CausalRuntimeTransport:
    def __init__(self, cause="host_operation_failure"):
        self.calls = 0
        self.cause = cause

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        return _runtime_frames(
            json.loads(snapshot_json),
            json.loads(envelope_json),
            failure={
                "code": "runtime_error",
                "message": "raw provider callback secret should not escape the bounded result",
                "retryable": False,
                "cause": self.cause,
            },
        )


class BudgetExhaustedRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        return _runtime_frames(
            json.loads(snapshot_json),
            json.loads(envelope_json),
            failure={
                "code": "budget_exhausted",
                "message": "model-call allowance is exhausted",
                "retryable": False,
            },
        )


class CompletedWithoutOutcomeRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        frames = list(_runtime_frames(json.loads(snapshot_json), json.loads(envelope_json)))
        exit_frame = json.loads(frames[-1])
        exit_frame["kind"] = "completed"
        exit_frame.pop("failure", None)
        frames[-1] = json.dumps(exit_frame, sort_keys=True, separators=(",", ":"))
        return tuple(frames)


class TranscriptOnlyRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        frames = list(_runtime_frames(json.loads(snapshot_json), json.loads(envelope_json)))
        transcript = json.loads(frames[0])
        transcript["eventId"] = "event:ordinary-transcript"
        transcript["idempotencyKey"] = "idempotency:ordinary-transcript"
        transcript["body"] = {
            "kind": "transcript_evidence_observed",
            "payload": {
                "kind": "inline_text",
                "contentType": "text/plain",
                "text": "ordinary final text only",
            },
            "publication": {"action": "observation_only"},
        }
        exit_frame = json.loads(frames[-1])
        exit_frame["kind"] = "completed"
        exit_frame.pop("failure", None)
        return tuple(
            json.dumps(frame, sort_keys=True, separators=(",", ":"))
            for frame in (transcript, exit_frame)
        )


class CompletedExitWithUnknownProviderRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        envelope = json.loads(envelope_json)
        invocation = RuntimeInvocation.objects.get(invocation_id=envelope["invocationId"])
        notice = {
            "runId": str(invocation.run_id),
            "invocationId": invocation.invocation_id,
            "leaseId": "lease:late-provider-unknown",
            "provider": "deterministic-local",
            "model": "test-model",
            "destinationHost": "provider.test",
            "destinationPath": "/v1/test",
            "requestId": "request:late-provider-unknown",
            "idempotencyKey": "provider-attempt:late-provider-unknown",
            "sequence": 1,
        }
        record_provider_attempt_notice(
            invocation,
            {
                **notice,
                "phase": RuntimeProviderAttemptPhase.INTENT,
                "upstreamInitiated": False,
                "statusClass": "",
                "errorCode": "",
            },
        )
        record_provider_attempt_notice(
            invocation,
            {
                **notice,
                "phase": RuntimeProviderAttemptPhase.STARTED,
                "upstreamInitiated": True,
                "statusClass": "",
                "errorCode": "",
            },
        )
        record_provider_attempt_notice(
            invocation,
            {
                **notice,
                "phase": RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN,
                "upstreamInitiated": True,
                "statusClass": "unknown",
                "errorCode": "outcome_unknown",
                "reasonPhase": "provider_relay",
                "reasonSubreason": "upstream_timeout",
                "eventRef": "provider-event:" + "a" * 64,
            },
        )
        with pytest.raises(InvalidTransitionError):
            propose_outcome(
                invocation.run,
                summary="The runtime must not submit after provider ambiguity.",
                idempotency_key="idempotency:late-provider-unknown",
                created_by=invocation.created_by,
            )
        frames = list(_runtime_frames(json.loads(snapshot_json), envelope))
        exit_frame = json.loads(frames[-1])
        exit_frame["kind"] = "completed"
        exit_frame.pop("failure", None)
        frames[-1] = json.dumps(exit_frame, sort_keys=True, separators=(",", ":"))
        return tuple(frames)


class OutcomeBeforeLateBudgetExitRuntimeTransport:
    def __init__(self, *, completed=False):
        self.calls = 0
        self.completed = completed

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        envelope = json.loads(envelope_json)
        invocation = RuntimeInvocation.objects.get(invocation_id=envelope["invocationId"])
        propose_outcome(
            invocation.run,
            summary="The applied outcome must remain authoritative over a late finite exit.",
            idempotency_key="idempotency:late-budget-outcome",
            created_by=invocation.created_by,
        )
        failure = {
            "code": "budget_exhausted",
            "message": "model-call allowance is exhausted after publication",
            "retryable": False,
        }
        frames = list(_runtime_frames(json.loads(snapshot_json), envelope, failure=failure))
        first_event = json.loads(frames[0])
        late_event = dict(first_event)
        late_event["sequence"] = 1
        late_event["eventId"] = "event:late-terminal-usage"
        late_event["idempotencyKey"] = "idempotency:late-terminal-usage"
        exit_frame = json.loads(frames[-1])
        exit_frame["finalSequence"] = 1
        if self.completed:
            exit_frame["kind"] = "completed"
            exit_frame.pop("failure", None)
        return tuple(
            json.dumps(frame, sort_keys=True, separators=(",", ":"))
            for frame in (first_event, late_event, exit_frame)
        )


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


def test_supervisor_normalizes_runtime_run_reference_before_provider_attempt_write():
    invocation = SimpleNamespace(
        run_id="run-uuid",
        invocation_id="invocation:one",
        run=SimpleNamespace(snapshot={"runId": "run:run-uuid"}),
    )
    call = SimpleNamespace(
        run_id="run:run-uuid",
        invocation_id="invocation:one",
        input={
            "phase": "intent",
            "leaseId": "lease:one",
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "destinationHost": "chatgpt.com",
            "destinationPath": "/backend-api/codex/responses",
            "requestId": "request:one",
            "idempotencyKey": "provider-attempt:one",
            "sequence": 1,
            "upstreamInitiated": False,
            "statusClass": "",
            "errorCode": "",
        },
    )

    notice = _provider_attempt_notice_for_plane(invocation, call)

    assert notice["runId"] == "run-uuid"
    assert notice["invocationId"] == "invocation:one"
    assert notice["leaseId"] == "lease:one"

    call.run_id = "run:other"
    with pytest.raises(RuntimeDispatchError, match="binding is invalid"):
        _provider_attempt_notice_for_plane(invocation, call)


class GenericExceptionRuntimeTransport:
    def __init__(self):
        self.calls = 0

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        raise RuntimeError("provider-secret=must-not-leak")


@pytest.mark.parametrize(
    ("stage", "error"),
    (
        ("runtime_provenance", RuntimeError("checkout=/private/secret")),
        ("runtime_command", ValueError("command=secret-token")),
        ("credential_source", RuntimeCredentialError("deployment credential resolver failed")),
        ("credential_state", RuntimeCredentialError("credential state is invalid")),
        ("runtime_environment", TypeError("environment=/private/secret")),
        ("runtime_transport", OSError("runtime secret=must-not-leak")),
    ),
)
def test_supervisor_setup_stage_exposes_only_a_finite_safe_failure(stage, error):
    with pytest.raises(_SupervisorSetupFailure) as raised:
        with _supervisor_setup_stage(stage):
            raise error

    failure = raised.value
    assert failure.stage == stage
    assert failure.failure == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": (
            "credential_resolver_failed"
            if stage == "credential_source"
            else "credential_state_invalid"
            if stage == "credential_state"
            else "runtime_configuration_rejected"
        ),
    }
    assert "secret" not in str(failure).casefold()


class KnownDispatchFailureTransport:
    def __init__(
        self,
        *,
        failure_code="runtime_process_failed",
        failure_phase="launcher",
        failure_detail="bootstrap_argv_rejected",
        failure_subreason=None,
    ):
        self.calls = 0
        self.failure_code = failure_code
        self.failure_phase = failure_phase
        self.failure_detail = failure_detail
        self.failure_subreason = failure_subreason

    def dispatch(self, snapshot_json, envelope_json):
        self.calls += 1
        raise RuntimeDispatchError(
            "runtime process did not produce a durable terminal result",
            failure_code=self.failure_code,
            failure_phase=self.failure_phase,
            failure_detail=self.failure_detail,
            failure_subreason=self.failure_subreason,
        )


def _invocation(
    workspace,
    gateway_project,
    gateway_issue,
    create_user,
    *,
    runtime_defaults=None,
    tool_presentation=None,
    suffix="extra",
):
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
        tool_presentation=tool_presentation,
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


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_pinned_hermes_runs_through_http_service_launcher_and_bound_host_socket(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    checkout = os.environ.get("PLANE_G2_HERMES_CHECKOUT", "/hermes")
    dependency_path = os.environ.get("PLANE_G2_HERMES_DEPENDENCY_PATH") or os.path.join(
        checkout, "plane_runtime", "g1_runtime_image"
    )
    expected_sha = "292e866374ca9e9615473fc9bf5dda1913b672e1"
    assert os.path.isdir(checkout)
    assert (
        subprocess.run(
            ["git", "-C", checkout, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        == expected_sha
    )
    if dependency_path:
        assert os.path.isdir(dependency_path)

    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults={
            "provider": "openai",
            "model": "deterministic-local",
            "adapter": "hermes",
            "maxCodeModeCalls": 16,
            "maxCodeModeOutputBytes": 131_072,
        },
        tool_presentation={
            "eagerOperations": [
                "agent.outcome.evaluate",
                "agent.outcome.submit",
                "agent.outcome.publish",
            ]
        },
        suffix="g2-http-real",
    )
    project_id = str(gateway_project.id)
    issue_id = str(gateway_issue.id)
    actor_ref = run.snapshot["actorRef"]
    run_ref = run.snapshot["runId"]
    fake_openai = tmp_path / "fake-openai"
    fake_openai.mkdir()
    (fake_openai / "sitecustomize.py").write_text(
        """
import json
import re
from types import SimpleNamespace as Namespace

_PROJECT_ID = %r
_ISSUE_ID = %r
_ACTOR_REF = %r
_RUN_REF = %r


def _prepared_read_call(request_json):
    def find(value):
        if isinstance(value, dict):
            if (
                value.get("action") == "read"
                and value.get("operationRef") == "operation:work_item.read"
                and isinstance(value.get("input"), dict)
                and set(value["input"]) == {"preparedCallRef"}
            ):
                return value
            for child in value.values():
                found = find(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find(child)
                if found is not None:
                    return found
        return None

    return find(json.loads(request_json))


def _tool_call(number, request_json):
    if number == 1:
        return "tool_search", {"query": "Plane work item", "limit": 5}
    if number == 2:
        return "tool_describe", {"name": "plane_operation"}
    if number == 3:
        return "tool_call", {"name": "plane_operation", "arguments": {
            "action": "discover", "operationRef": "plane.operations.discover@1",
            "input": {"query": "work item", "limit": 32},
        }}
    if number == 4:
        return "tool_call", {"name": "plane_operation", "arguments": {
            "action": "read", "operationRef": "operation:search_workspace",
            "input": {"query": "Gateway Issue", "limit": 1},
        }}
    if number in {5, 6}:
        read_call = _prepared_read_call(request_json)
        if read_call is None:
            raise AssertionError("remote model request did not preserve workItemReadCall")
        return "tool_call", {"name": "plane_operation", "arguments": {
            **read_call,
        }}
    if number == 7:
        return "tool_call", {"name": "plane_operation", "arguments": {
            "action": "mutate", "operationRef": "operation:agent.outcome.evaluate",
            "input": {"outcome_ref": "outcome-submission:not-authorized",
                       "evaluator_ref": _ACTOR_REF, "verdict": "revision_requested"},
        }}
    if number == 8:
        return "plane_execute_typescript", {"typescript_source": (
            "export default async function ({host, input}: {host: {\\n"
            "    call_plane_operation: (operationId: string, input: Record<string, unknown>, "
            "idempotencyKey: string, correlationId: string) => Promise<Record<string, unknown>>\\n"
            "  }; input: Record<string, unknown>}): Promise<Record<string, unknown>> {\\n"
            "  const renameInput = { project_id: \\"" + _PROJECT_ID + "\\", "
            "issue_id: \\"" + _ISSUE_ID + "\\", name: \\"G2 Hermes renamed\\" };\\n"
            "  return await host.call_plane_operation(\\"work_item.rename\\", "
            "renameInput, \\"idempotency:code-mode-hermes-rename\\", "
            "\\"correlation:code-mode-hermes-rename\\");\\n"
            "}"
        )}
    if number == 9:
        return "tool_call", {"name": "plane_operation", "arguments": {
            "action": "mutate", "operationRef": "operation:agent.outcome.submit",
            "input": {"run_ref": _RUN_REF,
                       "summary": "The assigned issue was renamed through the Plane gateway.",
                       "artifacts": ["artifact:g2-production"],
                       "evidence": ["evidence:g2-production"]},
        }}
    if number == 10:
        match = re.search(r"outcome-submission:[0-9a-f-]+", request_json)
        return "tool_call", {"name": "plane_publish", "arguments": {
            "kind": "outcome", "operationRef": "operation:agent.outcome.publish",
            "resourceRef": match.group(0) if match else "outcome-submission:missing",
            "content": "Explicit outcome publication.",
        }}
    return None, None


class _Completions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        request_json = json.dumps(kwargs, sort_keys=True, default=str)
        if self.calls <= 10:
            name, arguments = _tool_call(self.calls, request_json)
            delta = Namespace(
                role="assistant",
                content=None,
                tool_calls=[Namespace(
                    index=0,
                    id="call-" + str(self.calls),
                    type="function",
                    function=Namespace(
                        name=name,
                        arguments=json.dumps(arguments, sort_keys=True, separators=(",", ":")),
                    ),
                )],
            )
            chunk = Namespace(
                id="chatcmpl-tool",
                object="chat.completion.chunk",
                created=1,
                model="deterministic-local",
                choices=[Namespace(index=0, delta=delta, finish_reason="tool_calls")],
            )
        else:
            delta = Namespace(role="assistant", content="ordinary final text only", tool_calls=None)
            chunk = Namespace(
                id="chatcmpl-final",
                object="chat.completion.chunk",
                created=1,
                model="deterministic-local",
                choices=[Namespace(index=0, delta=delta, finish_reason="stop")],
            )
        usage = Namespace(prompt_tokens=10, completion_tokens=2, total_tokens=12)
        return iter((chunk, Namespace(id="chatcmpl-usage", choices=[], usage=usage)))


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class OpenAI:
    def __init__(self, *, api_key=None, base_url=None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = _Chat()

    def close(self):
        return None


class AsyncOpenAI(OpenAI):
    pass


class APIError(Exception):
    pass


class APITimeoutError(APIError):
    pass


class APIConnectionError(APIError):
    pass


import openai
import hermes_logging
from pathlib import Path

openai.OpenAI = OpenAI
openai.AsyncOpenAI = AsyncOpenAI
hermes_logging.setup_logging = lambda **kwargs: Path(kwargs["hermes_home"]) / "logs"
hermes_logging.setup_verbose_logging = lambda: None
"""
        % (project_id, issue_id, actor_ref, run_ref),
        encoding="utf-8",
    )
    runtime_pythonpath = os.pathsep.join(path for path in (str(fake_openai), dependency_path, checkout) if path)
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": "s" * 40,
        "PLANE_AGENT_RUNTIME_COMMAND": "python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": json.dumps(
            {
                "HOME": str(tmp_path / "hermes-home"),
                "HERMES_HOME": str(tmp_path / "hermes-home"),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin",
                "PYTHONPATH": runtime_pythonpath,
                "PYTHONUNBUFFERED": "1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "http-real-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "http-real-safety-stop"),
    }
    (tmp_path / "hermes-home" / "sessions").mkdir(parents=True)
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    host_calls = []
    host_port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())

    def invoke(call):
        host_calls.append(call)
        return host_port.invoke(call)

    host_server = PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="host-token",
        invoke=invoke,
    )
    host_server.start()
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        runtime_port = port_probe.getsockname()[1]
    service_environment = os.environ.copy()
    service_environment.update(environment)
    service_environment.update(
        {
            "PLANE_AGENT_RUNTIME_BIND": "127.0.0.1",
            "PLANE_AGENT_RUNTIME_PORT": str(runtime_port),
            "PYTHONPATH": os.pathsep.join(
                path
                for path in (
                    os.getcwd(),
                    dependency_path,
                    checkout,
                    service_environment.get("PYTHONPATH"),
                )
                if path
            ),
        }
    )
    service_process = subprocess.Popen(
        [sys.executable, "-m", "plane.agent.runtime.service"],
        cwd=os.getcwd(),
        env=service_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    runtime_url = f"http://127.0.0.1:{runtime_port}"
    service_ready = False
    for _ in range(100):
        if service_process.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"{runtime_url}/health/ready", timeout=0.2) as response:
                if response.status == 200:
                    service_ready = True
                    break
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(0.05)
    assert service_ready, service_process.stderr.read().decode("utf-8", errors="replace")
    snapshot_json = json.dumps(run.snapshot, sort_keys=True, separators=(",", ":"))
    envelope_json = json.dumps(invocation.envelope, sort_keys=True, separators=(",", ":"))
    try:
        frames = RemoteRuntimeTransport(
                runtime_url=runtime_url,
                shared_secret=configuration.shared_secret,
                credential_broker=RuntimeCredentialBroker(
                    {
                        "runtime": {
                            "api_key": "test-provider-key",
                            "base_url": "http://127.0.0.1:9/v1",
                            "api_mode": "chat_completions",
                        }
                    }
                ),
                model_call_allowance=16,
            host_endpoint_factory=lambda _invocation_id: nullcontext(
                RuntimeHostEndpoint(url=host_server.url, token="host-token")
            ),
        ).dispatch(snapshot_json, envelope_json)
    finally:
        host_server.close()
        if service_process.poll() is None:
            service_process.terminate()
        try:
            _, service_stderr = service_process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            service_process.kill()
            _, service_stderr = service_process.communicate(timeout=3)
        assert service_process.returncode == 0, service_stderr.decode("utf-8", errors="replace")

    assert frames
    assert json.loads(frames[-1])["kind"] == "completed"
    assert [call.operation_ref for call in host_calls] == [
        "plane.operations.discover@1",
        "operation:search_workspace",
        "operation:work_item.read",
        "operation:agent.outcome.evaluate",
        "plane.code-mode.execute@1",
        "operation:agent.outcome.submit",
        "operation:agent.outcome.publish",
    ]
    correlation_id = invocation.envelope["correlationId"]
    assert OperationGatewayAudit.objects.filter(
        operation_id="agent.outcome.evaluate",
        phase="outcome",
        outcome="denied",
        error_code="NOT_AUTHORIZED",
        correlation_id=correlation_id,
    ).exists()
    assert OperationGatewayAudit.objects.filter(
        operation_id="agent.outcome.submit",
        phase="outcome",
        outcome="success",
        correlation_id=correlation_id,
    ).exists()
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "G2 Hermes renamed"
    assert OperationGatewayAudit.objects.filter(
        operation_id="work_item.rename",
        phase="outcome",
        outcome="success",
        idempotency_key="idempotency:code-mode-hermes-rename",
        correlation_id="correlation:code-mode-hermes-rename",
    ).exists()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_same_runtime_service_sequential_hermes_invocations_get_fresh_child_state(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    """The one-shot Hermes child must not inherit the prior invocation's home."""

    checkout = os.environ.get("PLANE_G2_HERMES_CHECKOUT", "/workspace/hermes-agent")
    dependency_path = os.environ.get("PLANE_G2_HERMES_DEPENDENCY_PATH") or os.path.join(
        checkout, "plane_runtime", "g1_runtime_image"
    )
    expected_sha = "292e866374ca9e9615473fc9bf5dda1913b672e1"
    assert os.path.isdir(checkout)
    assert (
        subprocess.run(
            ["git", "-C", checkout, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        == expected_sha
    )
    assert os.path.isdir(dependency_path)

    runtime_defaults = {
        "provider": "openai",
        "model": "deterministic-local",
        "adapter": "hermes",
        "maxCodeModeCalls": 1,
        "maxCodeModeOutputBytes": 131_072,
    }
    first_run, first_invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults=runtime_defaults,
        suffix="sequential-first",
    )
    second_run, second_invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        runtime_defaults=runtime_defaults,
        suffix="sequential-second",
    )

    marker = tmp_path / "child-hermes-homes.txt"
    fake_runtime = tmp_path / "fake-runtime"
    fake_runtime.mkdir()
    (fake_runtime / "sitecustomize.py").write_text(
        """
import os
from pathlib import Path

_MARKER = %s


class DeterministicAgent:
    def __init__(self, **kwargs):
        hermes_home = os.environ["HERMES_HOME"]
        Path(hermes_home).mkdir(parents=True, exist_ok=True)
        with Path(_MARKER).open("a", encoding="utf-8") as handle:
            handle.write(hermes_home + "\\n")
        self._step_callback = kwargs.get("step_callback")
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_api_calls = 0

    def interrupt(self, _reason):
        return None

    def run_conversation(self, _objective, system_message=None):
        del system_message
        if self._step_callback is not None:
            self._step_callback()
        return {"final_response": "provider-free deterministic runtime"}


import run_agent

run_agent.AIAgent = DeterministicAgent
"""
        % json.dumps(str(marker)),
        encoding="utf-8",
    )
    runtime_pythonpath = os.pathsep.join(
        path for path in (str(fake_runtime), dependency_path, checkout) if path
    )
    shared_home = tmp_path / "shared-hermes-home"
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": "s" * 40,
        "PLANE_AGENT_RUNTIME_COMMAND": "python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": json.dumps(
            {
                "HOME": str(shared_home),
                "HERMES_HOME": str(shared_home),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin",
                "PLANE_TEST_CHILD_HOME_MARKER": str(marker),
                "PYTHONPATH": runtime_pythonpath,
                "PYTHONUNBUFFERED": "1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "sequential-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "sequential-safety-stop"),
    }
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        runtime_port = port_probe.getsockname()[1]
    service_environment = os.environ.copy()
    service_environment.update(environment)
    service_environment.update(
        {
            "PLANE_AGENT_RUNTIME_BIND": "127.0.0.1",
            "PLANE_AGENT_RUNTIME_PORT": str(runtime_port),
            "PYTHONPATH": os.pathsep.join(
                path
                for path in (
                    os.getcwd(),
                    dependency_path,
                    checkout,
                    service_environment.get("PYTHONPATH"),
                )
                if path
            ),
        }
    )
    service_process = subprocess.Popen(
        [sys.executable, "-m", "plane.agent.runtime.service"],
        cwd=os.getcwd(),
        env=service_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    runtime_url = f"http://127.0.0.1:{runtime_port}"
    service_ready = False
    for _ in range(100):
        if service_process.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"{runtime_url}/health/ready", timeout=0.2) as response:
                if response.status == 200:
                    service_ready = True
                    break
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(0.05)
    if not service_ready and service_process.poll() is None:
        service_process.terminate()
        service_process.wait(timeout=3)
    assert service_ready

    transport = RemoteRuntimeTransport(
        runtime_url=runtime_url,
        shared_secret=configuration.shared_secret,
        credential_broker=RuntimeCredentialBroker(
            {
                "runtime": {
                    "api_key": "provider-free-test-key",
                    "base_url": "http://127.0.0.1:9/v1",
                    "api_mode": "chat_completions",
                }
            }
        ),
        model_call_allowance=1,
    )
    try:
        first_frames = transport.dispatch(
            json.dumps(first_run.snapshot, sort_keys=True, separators=(",", ":")),
            json.dumps(first_invocation.envelope, sort_keys=True, separators=(",", ":")),
        )
        second_frames = transport.dispatch(
            json.dumps(second_run.snapshot, sort_keys=True, separators=(",", ":")),
            json.dumps(second_invocation.envelope, sort_keys=True, separators=(",", ":")),
        )
    finally:
        if service_process.poll() is None:
            service_process.terminate()
        try:
            _, service_stderr = service_process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            service_process.kill()
            _, service_stderr = service_process.communicate(timeout=3)
        del service_stderr
        assert service_process.returncode == 0

    for frames in (first_frames, second_frames):
        assert frames
        assert json.loads(frames[-1])["kind"] == "completed"
        assert any(json.loads(frame).get("body", {}).get("kind") == "progress_observed" for frame in frames)

    child_homes = marker.read_text(encoding="utf-8").splitlines()
    assert len(child_homes) == 2
    assert len(set(child_homes)) == 2
    assert all(not Path(child_home).exists() for child_home in child_homes)


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
def test_supervisor_preserves_finite_runtime_budget_failure_through_terminal_output(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="budget-exhausted")
    transport = BudgetExhaustedRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    expected = {
        "failureCode": "budget_exhausted",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "model_call_budget_exhausted",
    }
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.FAILED
    assert result.failure == expected
    assert control.failure_code == "budget_exhausted"
    assert json.loads(control.failure_reason) == expected
    assert json.loads(terminal.reason) == expected
    assert expected["failureSubreason"] in _supervisor_result_output(result)
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_keeps_applied_outcome_and_late_budget_exit_as_split_truth(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="late-budget")
    transport = OutcomeBeforeLateBudgetExitRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    expected = {
        "failureCode": "budget_exhausted",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "model_call_budget_exhausted",
    }
    invocation.refresh_from_db()
    run.refresh_from_db()
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    exit_evidence = RuntimeExitEvidence.objects.get(invocation=invocation)
    assert result.state == InvocationState.SUCCEEDED
    assert result.terminal_kind == "outcome_submission"
    assert result.failure == expected
    assert run.state == RunState.SUCCEEDED
    assert invocation.state == InvocationState.SUCCEEDED
    assert control.failure_code == "budget_exhausted"
    assert control.state == RuntimeControlState.RELEASED
    assert terminal.kind == "outcome_submission"
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert exit_evidence.kind == "failed"
    assert exit_evidence.final_sequence == 1
    assert exit_evidence.raw_payload["failure"]["code"] == "budget_exhausted"
    late_events = RuntimeEventIngress.objects.filter(invocation=invocation).order_by("sequence")
    assert late_events.count() == 2
    assert all(
        event.raw_payload["planeIngress"] == {
            "disposition": "late_after_terminal",
            "authoritative": False,
            "terminalProductEventRef": terminal.product_event_ref,
        }
        for event in late_events
    )

    replay = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    assert replay.state == InvocationState.SUCCEEDED
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_accepts_completed_exit_after_late_terminal_evidence(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="late-completed")
    transport = OutcomeBeforeLateBudgetExitRuntimeTransport(completed=True)

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    invocation.refresh_from_db()
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    exit_evidence = RuntimeExitEvidence.objects.get(invocation=invocation)
    assert result.state == InvocationState.SUCCEEDED
    assert result.terminal_kind == "outcome_submission"
    assert result.failure is None
    assert terminal.kind == "outcome_submission"
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert exit_evidence.kind == "completed"
    assert exit_evidence.final_sequence == 1
    assert RuntimeEventIngress.objects.filter(invocation=invocation).count() == 2
    assert all(
        event.raw_payload["planeIngress"]["disposition"] == "late_after_terminal"
        for event in RuntimeEventIngress.objects.filter(invocation=invocation)
    )

    replay = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    assert replay.state == InvocationState.SUCCEEDED
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_preserves_finite_runtime_error_failure_through_terminal_output(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="runtime-error")
    transport = FailingRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    expected = {
        "failureCode": "runtime_error",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "runtime_execution_failed",
    }
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.FAILED
    assert result.failure == expected
    assert control.failure_code == "runtime_error"
    assert json.loads(control.failure_reason) == expected
    assert json.loads(terminal.reason) == expected
    assert expected["failureSubreason"] in _supervisor_result_output(result)
    assert transport.calls == 1


@pytest.mark.parametrize(
    "cause",
    [
        "host_operation_failure",
        "dependency_failure",
        "permission_failure",
        "resource_failure",
        "timeout_failure",
        "provider_client_failure",
        "runtime_unknown_failure",
        "provider_auth_failure",
        "provider_entitlement_failure",
        "provider_rate_limit",
        "provider_request_failure",
        "provider_transport_failure",
        "provider_unknown_failure",
    ],
)
@pytest.mark.django_db(transaction=True)
def test_supervisor_preserves_runtime_failure_cause_without_copying_raw_message(
    workspace, gateway_project, gateway_issue, create_user, cause
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="runtime-cause")
    transport = CausalRuntimeTransport(cause)

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    expected = {
        "failureCode": "runtime_error",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "runtime_execution_failed",
        "failureCause": cause,
    }
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    output = _supervisor_result_output(result)
    assert result.failure == expected
    assert json.loads(control.failure_reason) == expected
    assert json.loads(terminal.reason) == expected
    assert cause in output
    assert "raw provider callback secret" not in output
    assert "raw provider callback secret" not in control.failure_reason
    assert "raw provider callback secret" not in terminal.reason
    assert transport.calls == 1
    diagnostic = {
        "operationId": "work_item.rename",
        "attemptRef": "operation-attempt:request:worker",
        "receiptRef": "audit-receipt:audit:worker",
        "status": "unavailable",
        "errorCode": "OPERATION_UNAVAILABLE",
        "codeModePhase": "host_callback",
        "callbackPhase": "host_return",
        "operationRefDigest": expected["operationRefDigest"],
    }
    output_with_diagnostic = _supervisor_result_output(
        result,
        host_operation_failure=diagnostic,
    )
    assert json.loads(output_with_diagnostic.split(" failure=", 1)[1])["hostOperationFailure"] == diagnostic


@pytest.mark.django_db(transaction=True)
def test_supervisor_preserves_missing_outcome_failure_through_terminal_output(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="missing-outcome")
    transport = CompletedWithoutOutcomeRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    expected = {
        "failureCode": "missing_outcome",
        "failurePhase": "runtime_supervisor",
        "failureDetail": "missing_outcome",
        "failureSubreason": "completed_without_explicit_outcome",
    }
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.FAILED
    assert result.failure == expected
    assert control.failure_code == "missing_outcome"
    assert json.loads(control.failure_reason) == expected
    assert json.loads(terminal.reason) == expected
    assert "completed_without_explicit_outcome" in _supervisor_result_output(result)
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_keeps_ordinary_text_as_transcript_without_product_completion(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="transcript-only")
    transport = TranscriptOnlyRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    event = RuntimeEventIngress.objects.get(invocation=invocation, kind="transcript_evidence_observed")
    body = event.raw_payload["body"]
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.FAILED
    assert result.failure["failureCode"] == "missing_outcome"
    assert body["payload"]["text"] == "ordinary final text only"
    assert body["publication"] == {"action": "observation_only"}
    assert OutcomeSubmission.objects.filter(run=run).count() == 0
    assert RunTerminalEvent.objects.filter(run=run, kind="outcome_submission", visible=True).count() == 0
    assert terminal.kind == "run_failure"
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_terminal_provider_outcome_unknown_cannot_succeed_with_completed_exit_and_outcome(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="late-unknown")
    transport = CompletedExitWithUnknownProviderRuntimeTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    invocation.refresh_from_db()
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    attempt = RuntimeProviderAttempt.objects.get(invocation=invocation)
    expected_failure = {
        "failureCode": "outcome_unknown",
        "failurePhase": "provider_relay",
        "failureDetail": "upstream_result_unavailable",
        "failureSubreason": "upstream_timeout",
        "providerAttemptRef": f"provider-attempt:{attempt.id}",
        "providerEventRef": "provider-event:" + "a" * 64,
    }
    assert OutcomeSubmission.objects.filter(run=run).count() == 0
    assert result.state == InvocationState.BLOCKED
    assert result.terminal_kind == "run_blocker"
    assert result.failure == expected_failure
    assert invocation.state == InvocationState.BLOCKED
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert control.failure_code == "outcome_unknown"
    assert terminal.kind == "run_blocker"
    assert json.loads(control.failure_reason) == expected_failure
    assert json.loads(terminal.reason) == expected_failure
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert RuntimeExitEvidence.objects.filter(invocation=invocation, kind="completed").exists()
    assert transport.calls == 1


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
def test_supervisor_generic_exception_is_outcome_unknown_and_not_replayed(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="generic-exception")
    transport = GenericExceptionRuntimeTransport()

    first = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    second = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(run=run, visible=True)
    assert first.terminal_kind == second.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert control.failure_code == "outcome_unknown"
    assert "provider-secret=must-not-leak" not in terminal.reason
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_pre_dispatch_setup_failure_is_terminalized_once_without_provider_attempt(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        suffix="setup-terminal",
    )
    failure = {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }

    first = terminalize_pre_dispatch_failure(invocation, failure)
    second = terminalize_pre_dispatch_failure(invocation, failure)

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert first.state == second.state == InvocationState.BLOCKED
    assert first.failure == failure
    assert second.failure is None
    assert control.state == RuntimeControlState.RELEASED
    assert control.failure_code == failure["failureCode"]
    assert json.loads(control.failure_reason) == failure
    assert json.loads(terminal.reason) == failure
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()


@pytest.mark.django_db(transaction=True)
def test_unclassified_pre_dispatch_setup_failure_remains_outcome_unknown(
    workspace, gateway_project, gateway_issue, create_user
):
    _run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        suffix="setup-unknown",
    )

    result = terminalize_pre_dispatch_failure(
        invocation,
        {
            "failureCode": "runtime_configuration_pre_dispatch_failure",
            "failurePhase": "runtime_configuration",
            "failureDetail": "unclassified_exception",
        },
    )

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.BLOCKED
    assert result.failure is None
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert control.failure_code == "outcome_unknown"
    assert control.outcome_unknown_at is not None
    assert "runtime_configuration_pre_dispatch_failure" not in terminal.reason
    assert "unclassified_exception" not in terminal.reason


@pytest.mark.django_db(transaction=True)
def test_command_error_cannot_bypass_setup_terminal_evidence(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(
        workspace,
        gateway_project,
        gateway_issue,
        create_user,
        suffix="command-error-terminal",
    )
    secret = "synthetic-secret-must-not-appear"
    with override_settings(
        PLANE_AGENT_RUNTIME_URL="http://127.0.0.1:1",
        PLANE_AGENT_RUNTIME_SHARED_SECRET=secret,
        PLANE_AGENT_RUNTIME_HOST_URL="https://invalid-host.example",
        PLANE_AGENT_RUNTIME_COMMAND=(
            "python3",
            "-m",
            "plane_runtime.g1_runtime_image.bootstrap",
            "--once",
            "--g1-production",
        ),
        PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={"runtime": {"api_key": secret}},
        PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(tmp_path / "credential-state.json"),
        PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=str(tmp_path / "safety-stop"),
        PLANE_AGENT_RUNTIME_ENVIRONMENT={},
    ):
        with pytest.raises(CommandError, match="agent supervisor setup was rejected") as raised:
            call_command(
                "agent_supervisor",
                invocation_ref=invocation.invocation_id,
                runtime_command=list(
                    (
                        "python3",
                        "-m",
                        "plane_runtime.g1_runtime_image.bootstrap",
                        "--once",
                        "--g1-production",
                    )
                ),
            )

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert str(raised.value) == "agent supervisor setup was rejected"
    assert control.failure_code == "runtime_configuration_pre_dispatch_failure"
    assert json.loads(control.failure_reason) == {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }
    assert terminal.kind == "run_blocker"
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()
    assert secret not in str(raised.value)
    assert secret not in control.failure_reason


@pytest.mark.parametrize(
    ("failure_code", "failure_phase", "failure_detail"),
    (
        ("runtime_process_failed", "launcher", "bootstrap_argv_rejected"),
        ("runtime_configuration_pre_dispatch_failure", "runtime_configuration", "dispatch_rejected"),
    ),
)
@pytest.mark.django_db(transaction=True)
def test_known_pre_dispatch_failure_with_no_upstream_attempt_is_blocked_and_released(
    workspace, gateway_project, gateway_issue, create_user, failure_code, failure_phase, failure_detail
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="pre-dispatch")
    transport = KnownDispatchFailureTransport(
        failure_code=failure_code,
        failure_phase=failure_phase,
        failure_detail=failure_detail,
    )

    first = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    second = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    assert first.state == second.state == InvocationState.BLOCKED
    assert first.terminal_kind == second.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.RELEASED
    assert control.failure_code == failure_code
    assert control.outcome_unknown_at is None
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_supervisor_persists_bounded_pre_dispatch_subreason(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(
        workspace, gateway_project, gateway_issue, create_user, suffix="pre-dispatch-subreason"
    )
    transport = KnownDispatchFailureTransport(
        failure_code="runtime_configuration_pre_dispatch_failure",
        failure_phase="runtime_configuration",
        failure_detail="dispatch_rejected",
        failure_subreason="runtime_configuration_rejected",
    )

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(run=run, visible=True)
    expected_reason = {
        "failureCode": "runtime_configuration_pre_dispatch_failure",
        "failurePhase": "runtime_configuration",
        "failureDetail": "dispatch_rejected",
        "failureSubreason": "runtime_configuration_rejected",
    }
    assert result.state == InvocationState.BLOCKED
    assert result.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.RELEASED
    assert json.loads(control.failure_reason) == expected_reason
    assert terminal.reason == control.failure_reason
    assert result.failure == expected_reason
    output = _supervisor_result_output(result)
    assert "state=blocked" in output
    assert "failure=" + json.dumps(expected_reason, sort_keys=True, separators=(",", ":")) in output
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()
    assert transport.calls == 1


@pytest.mark.django_db(transaction=True)
def test_known_process_failure_with_initiated_attempt_remains_outcome_unknown(
    workspace, gateway_project, gateway_issue, create_user
):
    run, invocation = _invocation(workspace, gateway_project, gateway_issue, create_user, suffix="initiated")
    provider_attempt = {
        "phase": RuntimeProviderAttemptPhase.INTENT,
        "runId": str(invocation.run_id),
        "invocationId": invocation.invocation_id,
        "leaseId": "lease:supervisor-initiated",
        "provider": "deterministic-local",
        "model": "test-model",
        "destinationHost": "provider.test",
        "destinationPath": "/v1/test",
        "requestId": "request:supervisor-initiated",
        "idempotencyKey": "provider-attempt:supervisor-initiated",
        "sequence": 1,
        "upstreamInitiated": False,
        "statusClass": "",
        "errorCode": "",
    }
    record_provider_attempt_notice(invocation, provider_attempt)
    provider_attempt.update(
        {
            "phase": RuntimeProviderAttemptPhase.STARTED,
            "upstreamInitiated": True,
        }
    )
    record_provider_attempt_notice(invocation, provider_attempt)
    transport = KnownDispatchFailureTransport()

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")
    second = run_runtime_invocation(invocation, transport=transport, worker_id="worker:test")

    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    attempt = RuntimeProviderAttempt.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    assert result.state == InvocationState.BLOCKED
    assert second.state == InvocationState.BLOCKED
    assert result.terminal_kind == "run_blocker"
    assert second.terminal_kind == "run_blocker"
    assert control.state == RuntimeControlState.OUTCOME_UNKNOWN
    assert control.failure_code == "outcome_unknown"
    assert attempt.phase == RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN
    assert attempt.upstream_initiated is True
    assert result.failure == {
        "failureCode": "outcome_unknown",
        "failurePhase": "provider_relay",
        "failureDetail": "upstream_result_unavailable",
        "failureSubreason": "reconciliation_required",
        "providerAttemptRef": f"provider-attempt:{attempt.id}",
    }
    assert json.loads(terminal.reason) == result.failure
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert transport.calls == 1


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
    expected_sha = "292e866374ca9e9615473fc9bf5dda1913b672e1"
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
        tool_presentation={
            "eagerOperations": ["agent.outcome.evaluate", "agent.outcome.submit"]
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
    actor_ref = run.snapshot["actorRef"]
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
                            "action": "read",
                            "operationRef": "operation:work_item.read",
                            "input": {"project_id": project_id, "issue_id": issue_id},
                        },
                    }
                elif provider_stream_count == 4:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "mutate",
                            "operationRef": "operation:agent.outcome.evaluate",
                            "input": {
                                "outcome_ref": "outcome-submission:not-authorized",
                                "evaluator_ref": actor_ref,
                                "verdict": "revision_requested",
                            },
                        },
                    }
                elif provider_stream_count == 5:
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
                elif provider_stream_count == 6:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "read",
                            "operationRef": "operation:catalog.search",
                            "input": {"query": "outcome publish", "limit": 5},
                        },
                    }
                elif provider_stream_count == 7:
                    function_name = "tool_call"
                    arguments = {
                        "name": "plane_operation",
                        "arguments": {
                            "action": "read",
                            "operationRef": "operation:catalog.describe",
                            "input": {"operation_id": "agent.outcome.publish"},
                        },
                    }
                elif provider_stream_count == 8:
                    function_name = "plane_execute_typescript"
                    arguments = {
                        "typescript_source": (
                            "result = 2 + 2\n"
                            "print(result)"
                        )
                    }
                    code_callbacks.append(arguments["typescript_source"])
                elif provider_stream_count == 9:
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
                elif provider_stream_count == 10:
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
    assert provider_stream_count == 10, {
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
        "tool_call",
        "tool_call",
        "tool_call",
        "plane_execute_typescript",
        "tool_call",
        "tool_call",
    ]
    assert code_callbacks == [
        'result = 2 + 2\n'
        'print(result)'
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
        "catalog.describe",
        "work_item.read",
        "work_item.rename",
        "agent.outcome.submit",
        "agent.outcome.publish",
        "agent.outcome.evaluate",
    }
    receipts = OperationGatewayIdempotency.objects.filter(
        caller_id=actor.principal_id,
        workspace_slug=workspace.slug,
        correlation_id=correlation_id,
    )
    assert set(receipts.values_list("operation_id", flat=True)) == expected_operations
    assert receipts.count() == len(expected_operations)
    assert receipts.filter(operation_id="catalog.search").count() == 1
    assert receipts.filter(operation_id="catalog.describe").count() == 1
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
    gateway_projection = api_readback["gateway_readback"][0]
    assert gateway_projection["receipt"]["workspace_slug"] == workspace.slug
    assert gateway_projection["receipt"]["caller_id"] == str(actor.principal_id)
    assert gateway_projection["receipt"]["operation_id"] == "agent.outcome.publish"
    assert gateway_projection["receipt"]["idempotency_key"]
    assert gateway_projection["receipt"]["correlation_id"] == correlation_id
    assert len(gateway_projection["receipt"]["request_digest"]) == 64
    assert gateway_projection["audit"][0]["workspace_slug"] == workspace.slug
    assert gateway_projection["audit"][0]["caller_id"] == str(actor.principal_id)
    assert gateway_projection["receipt"]["invocation_id"]
    assert gateway_projection["audit"][0]["invocation_id"] == gateway_projection["receipt"]["invocation_id"]
    runtime_event_text = json.dumps(
        list(RuntimeEventIngress.objects.filter(invocation=invocation).values_list("raw_payload", flat=True)),
        sort_keys=True,
    )
    assert 'Plane host model read operation:work_item.read -> ok' in runtime_event_text
    assert 'Plane host model mutate operation:work_item.rename -> ok' in runtime_event_text
    assert 'Plane host model mutate operation:agent.outcome.evaluate -> denied' in runtime_event_text
    assert OperationGatewayAudit.objects.filter(
        caller_id=actor.principal_id,
        operation_id="agent.outcome.evaluate",
        phase="outcome",
        outcome="denied",
        error_code="NOT_AUTHORIZED",
        correlation_id=correlation_id,
    ).exists()
    assert OperationGatewayAudit.objects.filter(
        caller_id=actor.principal_id,
        operation_id="catalog.search",
        phase="outcome",
        outcome="success",
        correlation_id=correlation_id,
    ).count() == 1
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

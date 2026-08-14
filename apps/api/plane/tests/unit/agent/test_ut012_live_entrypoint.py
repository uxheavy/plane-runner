"""UT-012: exercise the exact live helper through the supervisor command."""

from __future__ import annotations

import json
import runpy
import socket
import sys
import threading
from pathlib import Path
from uuid import UUID

import pytest
from django.test import override_settings

from plane.agent.lifecycle.services import _runtime_policy
from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    PlaneHostCall,
    PlaneHostHTTPClient,
    RuntimeConfigurationError,
    RuntimeDispatchError,
)
from plane.agent.runtime.health import RuntimeSafetyController
from plane.agent.runtime.service import _RuntimeHTTPServer
from plane.db.models import (
    InvocationState,
    RunAttempt,
    RunTerminalEvent,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeInvocation,
    RuntimeInvocationControl,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
)


# The exact helper is mounted read-only at this path for the focused container
# run, matching tools/agent-g4-live.sh's production mount.
LIVE_HELPER = Path("/workspace/tools/agent-g4-live-invoke.py")


def _binding_environment(monkeypatch):
    revisions = {
        "G4_CANDIDATE": "a" * 40,
        "G4_EXPECTED_CANDIDATE": "a" * 40,
        "G4_G3_BASELINE": "b" * 40,
        "G4_HERMES": "c" * 40,
        "G4_MCP": "d" * 40,
        "G4_SDK": "e" * 40,
        "G4_RUNTIME_IMAGE_TAG": "plane-agent-runtime:test",
        "G4_RUNTIME_IMAGE_DIGEST": "sha256:" + "1" * 64,
        "G4_RUNTIME_IMAGE_REVISION": "f" * 40,
        "G4_RUNTIME_CONTRACT": "plane.agent-runtime/v1",
        "G4_API_IMAGE_TAG": "plane-agent-api:test",
        "G4_API_IMAGE_DIGEST": "sha256:" + "2" * 64,
        "G4_API_SOURCE_REVISION": "a" * 40,
        "G4_API_CONTRACT": "plane.operation/v1",
        "G4_PERMITTED_CANARY": "ut012-permitted",
        "G4_DENIED_CANARY": "ut012-denied",
    }
    provider = {
        "name": "openai-codex",
        "model": "gpt-5.6-luna",
        "baseUrl": "https://chatgpt.com/backend-api/codex/responses",
        "host": "chatgpt.com",
        "path": "/backend-api/codex/responses",
        "credentialSource": "command:/usr/local/bin/plane-agent-runtime-credential-resolver",
        "credentialRef": "runtime",
        "credentialName": "api_key",
    }
    monkeypatch.setenv("G4_PROVIDER_DESCRIPTOR_JSON", json.dumps(provider, sort_keys=True, separators=(",", ":")))
    provider_environment = {
        "PLANE_AGENT_RUNTIME_PROVIDER": provider["name"],
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": provider["model"],
        "PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL": provider["baseUrl"],
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST": provider["host"],
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH": provider["path"],
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE": provider["credentialSource"],
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF": provider["credentialRef"],
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME": provider["credentialName"],
    }
    for key, value in provider_environment.items():
        monkeypatch.setenv(key, value)
    for key, value in revisions.items():
        monkeypatch.setenv(key, value)


def _runtime_environment(tmp_path: Path, shared_secret: str, resolver: str) -> dict[str, str]:
    return {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": shared_secret,
        "PLANE_AGENT_RUNTIME_COMMAND": "python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": "{}",
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(tmp_path / "dispatch-ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(tmp_path / "safety-stop"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(tmp_path / "credential-state.json"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER": resolver,
        "PLANE_AGENT_RUNTIME_PROVIDER": "openai-codex",
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "chatgpt.com",
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "/backend-api/codex/responses",
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "gpt-5.6-luna",
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME": "api_key",
    }


def _host_call(client, snapshot, envelope, *, action, operation_ref, input_value, source="model"):
    return client.invoke(
        PlaneHostCall(
            run_id=snapshot["runId"],
            invocation_id=envelope["invocationId"],
            correlation_id=envelope["correlationId"],
            action=action,
            operation_ref=operation_ref,
            input=input_value,
            source=source,
        )
    )


def _runtime_exit_frames(snapshot, envelope, *, kind="completed", failure=None):
    event = {
        "protocol": "plane.agent-runtime/v1",
        "trust": "untrusted",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "sequence": 0,
        "eventId": "event:ut012-usage",
        "idempotencyKey": "idempotency:ut012-usage",
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
        "kind": kind,
    }
    if failure is not None:
        exit_frame["failure"] = failure
    return tuple(json.dumps(frame, sort_keys=True, separators=(",", ":")) for frame in (event, exit_frame))


def _completed_frames(snapshot, envelope):
    return _runtime_exit_frames(snapshot, envelope)


class _FakeLiveRuntime:
    def __init__(
        self,
        *,
        reject=False,
        provider_free=False,
        failure=None,
        runtime_exit_failure=None,
        completed_without_outcome=False,
    ):
        self.reject = reject
        self.provider_free = provider_free
        self.failure = failure
        self.runtime_exit_failure = runtime_exit_failure
        self.completed_without_outcome = completed_without_outcome
        self.dispatches = []
        self.fake_provider_calls = 0
        self.host_statuses = []

    def dispatch(self, body):
        snapshot = body["snapshot"]
        envelope = body["invocation"]
        self.dispatches.append(
            {
                "requestKeys": sorted(body),
                "snapshot": snapshot,
                "envelope": envelope,
                "snapshotPolicyKeys": sorted(snapshot["runtimePolicy"]),
                "envelopeKeys": sorted(envelope),
                "credentialLeaseKeys": sorted(body["credentialLease"]),
            }
        )
        if self.reject:
            raise RuntimeConfigurationError("synthetic malformed runtime configuration")
        if self.failure is not None:
            raise RuntimeDispatchError(
                "synthetic fake runtime exception at http://fake-runtime.invalid/secret with token=fake-runtime-token",
                failure_code=self.failure["failureCode"],
                failure_phase=self.failure["failurePhase"],
                failure_detail=self.failure["failureDetail"],
                failure_subreason=self.failure.get("failureSubreason"),
            )
        if self.runtime_exit_failure is not None:
            return _runtime_exit_frames(
                snapshot,
                envelope,
                kind="failed",
                failure=self.runtime_exit_failure,
            )
        if self.completed_without_outcome:
            return _completed_frames(snapshot, envelope)

        client = PlaneHostHTTPClient(url=body["host"]["url"], auth_token=body["host"]["token"])
        if not self.provider_free:
            lease_id = body["credentialLease"]["leaseId"]
            provider_attempt_key = "provider-attempt:ut012"
            for phase, initiated, status_class in (
                ("intent", False, ""),
                ("started", True, ""),
                ("completed", True, "2xx"),
            ):
                result = _host_call(
                    client,
                    snapshot,
                    envelope,
                    action="observe",
                    operation_ref="runtime.provider_attempt",
                    source="runtime",
                    input_value={
                        "phase": phase,
                        "leaseId": lease_id,
                        "provider": snapshot["runtimePolicy"]["model"]["provider"],
                        "model": snapshot["runtimePolicy"]["model"]["model"],
                        "destinationHost": "chatgpt.com",
                        "destinationPath": "/backend-api/codex/responses",
                        "requestId": "request:ut012",
                        "idempotencyKey": provider_attempt_key,
                        "sequence": 1,
                        "upstreamInitiated": initiated,
                        "statusClass": status_class,
                        "errorCode": "",
                    },
                )
                self.host_statuses.append((phase, result.status, result.error_code))
                assert result.status == "ok"
                if phase == "started":
                    self.fake_provider_calls += 1

        discovery = _host_call(
            client,
            snapshot,
            envelope,
            action="discover",
            operation_ref="plane.operations.discover@1",
            input_value={"query": "work item", "limit": 5},
        )
        self.host_statuses.append(("discover", discovery.status, discovery.error_code))
        assert discovery.status == "ok"
        denied = _host_call(
            client,
            snapshot,
            envelope,
            action="mutate",
            operation_ref="operation:agent.outcome.evaluate",
            input_value={
                "outcome_ref": "outcome-submission:not-authorized",
                "evaluator_ref": snapshot["actorRef"],
                "verdict": "revision_requested",
            },
        )
        assert denied.status == "denied"
        submitted = _host_call(
            client,
            snapshot,
            envelope,
            action="mutate",
            operation_ref="operation:agent.outcome.submit",
            input_value={
                "run_ref": snapshot["runId"],
                "summary": "UT-012 synthetic provider completion.",
                "artifacts": ["artifact:ut012"],
                "evidence": ["evidence:ut012"],
            },
        )
        assert submitted.status == "ok"
        outcome_ref = submitted.output["result"]["outcome"]["outcomeRef"]
        published = _host_call(
            client,
            snapshot,
            envelope,
            action="publish",
            operation_ref="operation:agent.outcome.publish",
            input_value={
                "kind": "outcome",
                "resourceRef": outcome_ref,
                "content": "UT-012 synthetic publication.",
            },
        )
        assert published.status == "ok"
        return _completed_frames(snapshot, envelope)


def _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port, *, host_url="http://127.0.0.1"):
    _binding_environment(monkeypatch)
    shared_secret = "runtime-boundary-secret-0123456789"
    auth_document = tmp_path / "codex-auth.json"
    auth_document.write_text(
        json.dumps(
            {
                "last_refresh": "2026-08-14T00:00:00Z",
                "tokens": {
                    "access_token": "synthetic-provider-secret",
                    "account_id": "synthetic-account",
                    "id_token": "synthetic-id-token",
                    "refresh_token": "synthetic-refresh-token",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    resolver = tmp_path / "codex-credential-resolver"
    resolver.write_text(
        "#!{python}\n"
        "import json\n"
        "from pathlib import Path\n"
        "document = json.loads(Path({auth!r}).read_text(encoding='utf-8'))\n"
        "print(json.dumps({{'api_key': document['tokens']['access_token']}}))\n".format(
            python=sys.executable,
            auth=str(auth_document),
        ),
        encoding="utf-8",
    )
    resolver.chmod(0o700)
    resolver_configuration = f"command:{resolver}"
    runtime_environment = _runtime_environment(tmp_path, shared_secret, resolver_configuration)
    configuration = AgentRuntimeConfiguration.from_environment(runtime_environment)
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "runtime-stop")
    controller.mark_ready()
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=fake_runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runtime_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with override_settings(
            PLANE_AGENT_RUNTIME_URL=runtime_url,
            PLANE_AGENT_RUNTIME_SHARED_SECRET=shared_secret,
            PLANE_AGENT_RUNTIME_HOST_URL=host_url,
            PLANE_AGENT_RUNTIME_HOST_BIND="127.0.0.1",
            PLANE_AGENT_RUNTIME_HOST_PORT=host_port,
            PLANE_AGENT_RUNTIME_DISPATCH_PATH="/v1/runtime/dispatch",
            PLANE_AGENT_RUNTIME_COMMAND=(
                "python3",
                "-m",
                "plane_runtime.g1_runtime_image.bootstrap",
                "--once",
                "--g1-production",
            ),
            PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER=resolver_configuration,
            PLANE_AGENT_RUNTIME_ENVIRONMENT={},
            PLANE_AGENT_RUNTIME_LEDGER_PATH=str(tmp_path / "plane-ledger.sqlite"),
            PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(tmp_path / "plane-revocations.json"),
            PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=str(tmp_path / "plane-safety-stop"),
            PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS=5,
            PLANE_AGENT_RUNTIME_MAX_REQUEST_BYTES=256 * 1024,
            PLANE_AGENT_RUNTIME_MAX_RESPONSE_BYTES=512 * 1024,
        ):
            module = runpy.run_path(str(LIVE_HELPER), run_name="ut012_live_invoke")
            return module["main"]()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_persists_canonical_contract_and_one_fake_provider_attempt(
    monkeypatch, tmp_path, capsys
):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime()
    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 0, fake_runtime.host_statuses
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "passed"

    assert len(fake_runtime.dispatches) == 1
    dispatch = fake_runtime.dispatches[0]
    invocation = RuntimeInvocation.objects.get(invocation_id=dispatch["envelope"]["invocationId"])
    run = RunAttempt.objects.get(pk=UUID(dispatch["snapshot"]["runId"].removeprefix("run:")))
    expected_policy, expected_budget = _runtime_policy(run.profile_version)

    assert dispatch["snapshot"] == run.snapshot
    assert dispatch["envelope"] == invocation.envelope
    assert run.snapshot["runtimePolicy"] == expected_policy
    assert run.snapshot["totalBudget"] == expected_budget
    assert dispatch["envelope"]["runSnapshotDigest"] == run.snapshot["contentDigest"]
    assert dispatch["snapshotPolicyKeys"] == sorted(expected_policy)
    assert dispatch["envelopeKeys"] == sorted(invocation.envelope)
    assert fake_runtime.fake_provider_calls == 1
    assert RuntimeProviderAttempt.objects.filter(invocation=invocation).count() == 1
    assert RuntimeProviderAttempt.objects.get(invocation=invocation).phase == RuntimeProviderAttemptPhase.COMPLETED
    assert invocation.state == InvocationState.SUCCEEDED
    assert RuntimeEventIngress.objects.filter(invocation=invocation).count() == 1
    assert RuntimeExitEvidence.objects.filter(invocation=invocation).count() == 1
    assert RunTerminalEvent.objects.filter(invocation=invocation, visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_preserves_bounded_runtime_rejection(monkeypatch, tmp_path, capsys):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(reject=True)
    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 1
    evidence = json.loads(capsys.readouterr().out)

    assert evidence["status"] == "failed"
    assert evidence["failure"]["errorClass"] == "RuntimeError"
    assert evidence["failure"]["reasonCode"] == "runtime_configuration_pre_dispatch_failure"
    assert evidence["failure"]["reasonPhase"] == "runtime_configuration"
    assert evidence["failure"]["reasonDetail"] == "dispatch_rejected"
    assert evidence["failure"]["reasonSubreason"] == "runtime_configuration_rejected"
    assert evidence["providerAttempts"] == []
    assert fake_runtime.fake_provider_calls == 0
    assert len(fake_runtime.dispatches) == 1


@pytest.mark.django_db(transaction=True)
def test_ut014_exact_live_helper_preserves_canonical_process_failure_receipt(
    monkeypatch, tmp_path, capsys
):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(
        failure={
            "failureCode": "runtime_process_failed",
            "failurePhase": "runtime_process",
            "failureDetail": "process_exit",
        }
    )

    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 1
    captured = capsys.readouterr()
    evidence = json.loads(captured.out)
    invocation = RuntimeInvocation.objects.get(invocation_id=evidence["invocation"]["id"])
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation, visible=True)
    expected_failure = {
        "failureCode": "runtime_process_failed",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
    }

    assert evidence["status"] == "failed"
    assert evidence["failure"]["reasonCode"] == expected_failure["failureCode"]
    assert evidence["failure"]["reasonPhase"] == expected_failure["failurePhase"]
    assert evidence["failure"]["reasonDetail"] == expected_failure["failureDetail"]
    assert evidence["failure"]["reasonSubreason"] == "unavailable"
    assert evidence["run"]["state"] == "blocked"
    assert evidence["invocation"]["state"] == "blocked"
    assert evidence["providerAttempts"] == []
    assert evidence["terminal"] == {"present": True, "kind": "run_blocker"}

    assert len(fake_runtime.dispatches) == 1
    assert fake_runtime.fake_provider_calls == 0
    assert invocation.state == InvocationState.BLOCKED
    assert control.failure_code == expected_failure["failureCode"]
    assert json.loads(control.failure_reason) == expected_failure
    assert terminal.kind == "run_blocker"
    assert json.loads(terminal.reason) == json.loads(control.failure_reason)
    assert RunTerminalEvent.objects.filter(run=invocation.run, visible=True).count() == 1
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()

    persisted_and_reported = "\n".join((captured.out, captured.err, control.failure_reason, terminal.reason))
    for raw_value in (
        "synthetic fake runtime exception",
        "http://fake-runtime.invalid/secret",
        "fake-runtime-token",
    ):
        assert raw_value not in persisted_and_reported


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_preserves_budget_exit_and_bounded_failure_readback(
    monkeypatch, tmp_path, capsys
):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(
        runtime_exit_failure={
            "code": "budget_exhausted",
            "message": "model output contains provider-secret=must-not-leak",
            "retryable": False,
        }
    )

    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 1
    evidence = json.loads(capsys.readouterr().out)

    assert evidence["failure"]["reasonCode"] == "budget_exhausted"
    assert evidence["runtimeExit"] == {
        "present": True,
        "kind": "failed",
        "failure": {"code": "budget_exhausted", "retryable": False},
    }
    assert evidence["runtimeEventIngress"] == {"kindCounts": {"usage_observed": 1}}
    assert evidence["terminal"] == {
        "present": True,
        "kind": "run_failure",
        "code": "budget_exhausted",
        "reasonCategory": "model_call_budget_exhausted",
    }
    assert evidence["planeHostOperationReceipts"] is False
    assert "provider-secret=must-not-leak" not in json.dumps(evidence)


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_preserves_missing_outcome_readback(
    monkeypatch, tmp_path, capsys
):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(completed_without_outcome=True)

    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 1
    evidence = json.loads(capsys.readouterr().out)

    assert evidence["failure"]["reasonCode"] == "missing_outcome"
    assert evidence["failure"]["reasonSubreason"] == "completed_without_explicit_outcome"
    assert evidence["runtimeExit"] == {
        "present": True,
        "kind": "completed",
        "failure": None,
    }
    assert evidence["runtimeEventIngress"] == {"kindCounts": {"usage_observed": 1}}
    assert evidence["terminal"] == {
        "present": True,
        "kind": "run_failure",
        "code": "missing_outcome",
        "reasonCategory": "completed_without_explicit_outcome",
    }
    assert evidence["planeHostOperationReceipts"] is False


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_proves_setup_reaches_fake_runtime_without_provider_attempt(
    monkeypatch, tmp_path, capsys
):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(provider_free=True)

    assert _run_literal_live_helper(monkeypatch, fake_runtime, tmp_path, host_port) == 0
    evidence = json.loads(capsys.readouterr().out)
    workload = evidence["summary"]["workload"]
    invocation = RuntimeInvocation.objects.get(invocation_id=workload["invocationRef"])
    run = RunAttempt.objects.get(pk=UUID(workload["runRef"]))

    assert evidence["status"] == "passed"
    assert len(fake_runtime.dispatches) == 1
    assert fake_runtime.dispatches[0]["envelope"]["invocationId"] == invocation.invocation_id
    assert fake_runtime.fake_provider_calls == 0
    assert invocation.state == InvocationState.SUCCEEDED
    assert run.state == "succeeded"
    assert workload["invocationRef"] == str(invocation.invocation_id)
    assert workload["runRef"] == str(run.id)
    assert RunTerminalEvent.objects.filter(invocation=invocation, visible=True).count() == 1
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()
    assert RuntimeInvocationControl.objects.get(invocation=invocation).failure_code == ""


@pytest.mark.django_db(transaction=True)
def test_exact_live_helper_reads_durable_setup_failure_when_command_raises(monkeypatch, tmp_path, capsys):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
    fake_runtime = _FakeLiveRuntime(provider_free=True)

    assert (
        _run_literal_live_helper(
            monkeypatch,
            fake_runtime,
            tmp_path,
            host_port,
            host_url="https://invalid-host.example",
        )
        == 1
    )
    evidence = json.loads(capsys.readouterr().out)
    invocation = RuntimeInvocation.objects.get(invocation_id=evidence["invocation"]["id"])
    control = RuntimeInvocationControl.objects.get(invocation=invocation)

    assert evidence["failure"]["errorClass"] == "CommandError"
    assert evidence["failure"]["reasonCode"] == "runtime_configuration_pre_dispatch_failure"
    assert evidence["failure"]["reasonPhase"] == "runtime_configuration"
    assert evidence["failure"]["reasonDetail"] == "dispatch_rejected"
    assert evidence["failure"]["reasonSubreason"] == "runtime_configuration_rejected"
    assert control.failure_reason == json.dumps(
        {
            "failureCode": "runtime_configuration_pre_dispatch_failure",
            "failurePhase": "runtime_configuration",
            "failureDetail": "dispatch_rejected",
            "failureSubreason": "runtime_configuration_rejected",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert fake_runtime.dispatches == []
    assert fake_runtime.fake_provider_calls == 0
    assert not RuntimeProviderAttempt.objects.filter(invocation=invocation).exists()
    assert RunTerminalEvent.objects.filter(invocation=invocation, visible=True).count() == 1

"""Production-entrypoint contracts for the Plane runtime supervisor."""

import json
import os
import shlex
import subprocess
from datetime import timedelta

import pytest
from django.utils import timezone

from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run, record_invocation
from plane.agent.runtime import RuntimeDispatchError
from plane.agent.runtime.supervisor import request_runtime_cancellation, run_runtime_invocation
from plane.db.models import (
    AgentRole,
    InvocationState,
    RunState,
    RunTerminalEvent,
    RuntimeUsageObservation,
    RuntimeControlState,
    RuntimeInvocationControl,
)
from plane.db.models.operation_gateway import OperationGatewayAudit
from plane.operation_gateway.gateway import OperationGateway
from plane.agent.runtime import HostBoundSubprocessRuntimeTransport


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
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    checkout = os.environ.get("PLANE_G2_HERMES_CHECKOUT")
    provider_url = os.environ.get("PLANE_G2_LOCAL_OPENAI_BASE_URL")
    provider_model = os.environ.get("PLANE_G2_LOCAL_OPENAI_MODEL", "deterministic-local")
    provider_key = os.environ.get("PLANE_G2_LOCAL_OPENAI_API_KEY")
    if not checkout or not provider_url or not provider_key:
        pytest.skip("set PLANE_G2_HERMES_CHECKOUT and local OpenAI-compatible provider variables")
    expected_sha = os.environ.get("PLANE_G2_HERMES_SHA", "602164dc7c8c18c09e97e3fa2f202f8891b7117b")
    actual_sha = subprocess.run(
        ["git", "-C", checkout, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert actual_sha == expected_sha
    command = shlex.split(
        os.environ.get(
            "PLANE_G2_HERMES_COMMAND",
            "python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
        )
    )
    assert command[1:4] == ["-m", "plane_runtime.g1_runtime_image.bootstrap", "--once"]
    assert "--g1-production" in command

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
            "Use native discover and read first. Use legitimate restricted Code Mode for one semantic mutation. "
            "Submit and publish exactly one explicit outcome. Do not publish ordinary final text."
        ),
        runtime_defaults={
            "provider": "openai-compatible",
            "model": provider_model,
            "adapter": "openai-compatible",
            "maxCodeModeCalls": 4,
        },
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Rename the assigned issue through the authorized native operation and record evidence.",
        acceptance_criteria=["The issue is renamed and one explicit outcome is published."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-real-supervisor", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g2-real-invocation", trigger="initial")
    transport = HostBoundSubprocessRuntimeTransport(
        command=command,
        cwd=checkout,
        environment={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": checkout},
        ledger_path=tmp_path / "g2-real-ledger.sqlite",
        gateway=OperationGateway(),
        bootstrap_command=True,
        credential_control=lambda _invocation: {"api_key": provider_key, "base_url": provider_url},
    )

    result = run_runtime_invocation(invocation, transport=transport, worker_id="worker:g2-real")

    gateway_operations = set(
        OperationGatewayAudit.objects.filter(caller_id=actor.principal_id).values_list("operation_id", flat=True)
    )
    assert result.state == InvocationState.SUCCEEDED
    assert gateway_issue.name != "G2 Gateway Issue"
    assert "agent.outcome.submit" in gateway_operations
    assert "agent.outcome.publish" in gateway_operations
    assert "ordinary final text" not in json.dumps(gateway_operations).lower()
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert provider_key not in json.dumps(run.snapshot)

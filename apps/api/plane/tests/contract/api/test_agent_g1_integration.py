"""Deterministic backend-only proof for the combined Plane Agent G1 spine.

The evidence contract is intentionally non-visual: this lane has no UI in
scope, so the durable Plane rows, runtime envelope, gateway receipts, audit
rows, and terminal product event are the expected artifacts.
"""

import copy
import json
import uuid
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from rest_framework.test import APIClient

from plane.agent.lifecycle import (
    IdempotencyConflictError,
    code_mode_usage_totals,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    propose_outcome,
    record_invocation,
)
from plane.agent.code_mode import CodeModeHostRPC, CodeModeIsolateRunner
from plane.agent.lifecycle.runtime_contract import validate_invocation_envelope
from plane.agent.runtime import RuntimeIngressError, dispatch_invocation, ingest_runtime_frame
from plane.db.models import (
    APIToken,
    AgentRole,
    AssignmentState,
    InvocationState,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    OutcomeSubmission,
    RunAttempt,
    RunState,
    RunTerminalEvent,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    User,
)
from plane.operation_gateway.contracts import MAX_RESPONSE_BYTES
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.publications import dispatch_publication_once


def _gateway_body(workspace, project, issue, *, key, name):
    return {
        "schema_version": "plane.operation/v1",
        "operation_id": "work_item.rename",
        "workspace_slug": workspace.slug,
        "idempotency_key": key,
        "correlation_id": f"g1-{key}",
        "input": {"project_id": str(project.id), "issue_id": str(issue.id), "name": name},
    }


def _api_client_for_user(user):
    token = APIToken.objects.create(
        user=user,
        label="G1 denial proof",
        token=f"g1-{uuid.uuid4().hex}",
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


class DeterministicRuntimeAdapter:
    """Test-only adapter that exposes the production serialized transport seam."""

    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def dispatch(self, snapshot_json, envelope_json):
        self.calls.append((snapshot_json, envelope_json))
        return tuple(json.dumps(frame, separators=(",", ":")) for frame in self.frames)


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_code_mode_uses_persisted_binding_child_isolate_and_exact_replay(
    workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Code Mode worker",
        created_by=create_user,
    )
    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Use the typed host.")
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the Code Mode host.",
        acceptance_criteria=["The host stays bound and bounded."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:code-mode-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:code-mode-invocation", trigger="initial")
    request = SimpleNamespace(
        user=create_user,
        META={},
        agent_actor_ref=run.snapshot["actorRef"],
    )
    host = CodeModeHostRPC(
        gateway=OperationGateway(),
        request=request,
        run=run,
        invocation=invocation,
        is_cancelled=lambda: False,
    )

    first = host.call_operation(
        "catalog.describe",
        {"operation_id": "search_workspace"},
        idempotency_key="idempotency:code-mode-call",
        correlation_id="correlation:code-mode-call",
    )
    replay = host.call_operation(
        "catalog.describe",
        {"operation_id": "search_workspace"},
        idempotency_key="idempotency:code-mode-call",
        correlation_id="correlation:code-mode-call",
    )
    assert replay == first
    assert first["actorRef"] == run.snapshot["actorRef"]
    assert first["workspaceRef"] == f"workspace:{workspace.id}"
    assert first["gatewayReceipt"] == first["auditReceipt"]

    changed = host.call_operation(
        "catalog.describe",
        {"operation_id": "catalog.search"},
        idempotency_key="idempotency:code-mode-call",
        correlation_id="correlation:code-mode-call",
    )
    assert changed["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    child_result = CodeModeIsolateRunner().run(
        host,
        """
          export default async function ({host}: {host: any}) {
            return await host.call_plane_operation(
              "catalog.search", {query: "", limit: 5},
              "idempotency:code-mode-child", "correlation:code-mode-child"
            );
          }
        """,
        {},
    )
    assert child_result["ok"] is True
    assert child_result["actorRef"] == run.snapshot["actorRef"]
    run.refresh_from_db()
    usage = code_mode_usage_totals(run)
    assert usage["codeModeCalls"] >= 4
    assert usage["codeModeInputBytes"] > 0
    assert usage["codeModeOutputBytes"] > 0
    assert run.cumulative_usage["durationMs"] > 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_combined_g1_plane_lifecycle_and_gateway_contract(
    api_key_client, workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G1 worker",
        credential_ref="plane-credential:g1",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Complete the assigned Plane objective.",
        tool_presentation={"eager": ["work_item.rename"]},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Rename the assigned work item through the authorized Plane gateway.",
        acceptance_criteria=["The renamed work item is reviewable."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g1-run", created_by=create_user)

    assert profile.role == AgentRole.WORKER
    assert run.actor_id == actor.id == assignment.assignee_id
    assert run.profile_version_id == profile.id
    assert run.snapshot["protocol"] == "plane.agent-runtime/v1"
    assert "hermes" not in json.dumps(run.snapshot).lower()
    assert not hasattr(run, "hermes_session_id")
    snapshot_before = copy.deepcopy(run.snapshot)
    snapshot_digest = run.snapshot_content_digest

    run.snapshot["assignment"]["objective"] = "forged"
    with pytest.raises(ValidationError, match="immutable"):
        run.save()
    run.refresh_from_db()
    assert run.snapshot == snapshot_before
    assert run.snapshot_content_digest == snapshot_digest

    invocation = record_invocation(
        run,
        idempotency_key="idempotency:g1-invocation",
        trigger="initial",
        usage={"inputTokens": 3, "outputTokens": 5, "durationMs": 11},
        created_by=create_user,
    )
    validate_invocation_envelope(invocation.envelope)
    assert invocation.state == InvocationState.RUNNING
    assert invocation.envelope["protocol"] == "plane.agent-runtime/v1"
    run.refresh_from_db()
    runtime_event = {
        "protocol": "plane.agent-runtime/v1",
        "trust": "untrusted",
        "workspaceRef": invocation.envelope["workspaceRef"],
        "actorRef": invocation.envelope["actorRef"],
        "runId": invocation.envelope["runId"],
        "invocationId": invocation.envelope["invocationId"],
        "sequence": 0,
        "eventId": "event:g1-runtime-observation",
        "idempotencyKey": "idempotency:g1-runtime-observation",
        "correlationId": invocation.envelope["correlationId"],
        "causationRef": invocation.envelope["causationRef"],
        "observedAt": "2026-08-05T00:00:00Z",
        "body": {
            "kind": "progress_observed",
            "payload": {"kind": "inline_text", "contentType": "text/plain", "text": "Observed."},
            "publication": {"action": "observation_only"},
        },
    }
    runtime_exit = {
        "protocol": "plane.agent-runtime/v1",
        "authority": "runtime_evidence_only",
        "workspaceRef": invocation.envelope["workspaceRef"],
        "actorRef": invocation.envelope["actorRef"],
        "runId": invocation.envelope["runId"],
        "invocationId": invocation.envelope["invocationId"],
        "finalSequence": 0,
        "idempotencyKey": invocation.envelope["idempotencyKey"],
        "correlationId": invocation.envelope["correlationId"],
        "causationRef": invocation.envelope["causationRef"],
        "kind": "completed",
    }
    adapter = DeterministicRuntimeAdapter((runtime_event, runtime_exit))
    frames = dispatch_invocation(invocation, adapter)
    assert len(adapter.calls) == 1
    dispatched_snapshot, dispatched_envelope = adapter.calls[0]
    assert isinstance(dispatched_snapshot, str)
    assert isinstance(dispatched_envelope, str)
    assert json.loads(dispatched_snapshot) == run.snapshot
    assert json.loads(dispatched_envelope) == invocation.envelope

    runtime_state_before_ingress = (
        run.state,
        run.invocation_count,
        run.last_invocation_id,
        copy.deepcopy(run.cumulative_usage),
        OutcomeSubmission.objects.filter(run=run).count(),
        RunTerminalEvent.objects.filter(run=run).count(),
    )
    with pytest.raises(RuntimeIngressError, match="finalSequence"):
        ingest_runtime_frame(invocation, json.dumps({**runtime_exit, "finalSequence": 1}))
    event_record = ingest_runtime_frame(invocation, frames[0])
    assert isinstance(event_record, RuntimeEventIngress)
    assert event_record.raw_payload == runtime_event
    with pytest.raises(RuntimeIngressError, match="already bound"):
        ingest_runtime_frame(
            invocation,
            json.dumps(
                {
                    **runtime_event,
                    "body": {
                        **runtime_event["body"],
                        "payload": {"kind": "inline_text", "contentType": "text/plain", "text": "Changed."},
                    },
                }
            ),
        )
    with pytest.raises(RuntimeIngressError, match="sequence"):
        ingest_runtime_frame(
            invocation,
            json.dumps(
                {
                    **runtime_event,
                    "sequence": 2,
                    "eventId": "event:g1-runtime-gap",
                    "idempotencyKey": "idempotency:g1-runtime-gap",
                }
            ),
        )
    with pytest.raises(RuntimeIngressError, match="actorRef"):
        ingest_runtime_frame(
            invocation,
            json.dumps(
                {
                    **runtime_event,
                    "actorRef": "actor:wrong-runtime-actor",
                    "eventId": "event:g1-runtime-binding",
                    "idempotencyKey": "idempotency:g1-runtime-binding",
                }
            ),
        )
    assert RuntimeEventIngress.objects.filter(invocation=invocation).count() == 1
    replayed_event = ingest_runtime_frame(invocation, frames[0])
    assert replayed_event.pk == event_record.pk

    exit_record = ingest_runtime_frame(invocation, frames[1])
    assert isinstance(exit_record, RuntimeExitEvidence)
    assert exit_record.raw_payload == runtime_exit
    replayed_exit = ingest_runtime_frame(invocation, frames[1])
    assert replayed_exit.pk == exit_record.pk
    with pytest.raises(RuntimeIngressError, match="different evidence"):
        ingest_runtime_frame(
            invocation,
            json.dumps(
                {
                    **runtime_exit,
                    "kind": "failed",
                    "failure": {"code": "runtime_error", "message": "Changed.", "retryable": False},
                }
            ),
        )
    for model, record in ((RuntimeEventIngress, event_record), (RuntimeExitEvidence, exit_record)):
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                model.objects.filter(pk=record.pk).update(raw_payload={"tampered": True})
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                model.objects.filter(pk=record.pk).delete()
    for table_name in ("agent_runtime_event_ingress", "agent_runtime_exit_evidence"):
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"TRUNCATE {table_name}")
    assert RuntimeEventIngress.objects.get(pk=event_record.pk).raw_payload == runtime_event
    assert RuntimeExitEvidence.objects.get(pk=exit_record.pk).raw_payload == runtime_exit
    with pytest.raises(RuntimeIngressError, match="after an exit"):
        ingest_runtime_frame(
            invocation,
            json.dumps(
                {
                    **runtime_event,
                    "sequence": 1,
                    "eventId": "event:g1-runtime-post-exit",
                    "idempotencyKey": "idempotency:g1-runtime-post-exit",
                }
            ),
        )
    run.refresh_from_db()
    invocation.refresh_from_db()
    assert (
        run.state,
        run.invocation_count,
        run.last_invocation_id,
        run.cumulative_usage,
        OutcomeSubmission.objects.filter(run=run).count(),
        RunTerminalEvent.objects.filter(run=run).count(),
    ) == runtime_state_before_ingress
    plane_run_state_before_gateway = (
        run.state,
        run.invocation_count,
        run.last_invocation_id,
        copy.deepcopy(run.cumulative_usage),
    )

    rename_key = "g1-gateway-rename"
    first = api_key_client.post(
        "/api/v1/operations/",
        _gateway_body(workspace, gateway_project, gateway_issue, key=rename_key, name="G1 renamed"),
        format="json",
    )
    assert first.status_code == 200, (
        "event=g1.gateway.authorized_mutation actor=plane_user operation=work_item.rename "
        "risk=runtime_bypasses_live_authorization expected=200 actual="
        f"{first.status_code} suggestion=inspect_gateway_authorize_and_project_membership"
    )
    first_body = first.json()
    assert first_body["ok"] is True
    assert set(first_body["result"]) == {"work_item"}
    assert len(json.dumps(first_body, separators=(",", ":")).encode()) <= MAX_RESPONSE_BYTES

    gateway_record = OperationGatewayIdempotency.objects.get(idempotency_key=rename_key)
    gateway_row_refs = (
        gateway_record.pk,
        gateway_record.invocation_id,
        tuple(gateway_record.publications.order_by("publication_key").values_list("pk", "publication_key")),
    )
    for publication in gateway_record.publications.order_by("publication_key"):
        dispatch_publication_once(str(publication.id))

    second = api_key_client.post(
        "/api/v1/operations/",
        _gateway_body(workspace, gateway_project, gateway_issue, key=rename_key, name="G1 renamed"),
        format="json",
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["idempotency"]["replayed"] is True
    assert second_body["result"] == first_body["result"]
    assert second_body["audit_receipt"] != first_body["audit_receipt"]

    reconciled, reconcile_status = OperationGateway().reconcile(gateway_record.pk)
    assert reconcile_status == 200
    assert reconciled["ok"] is True
    assert reconciled["result"] == first_body["result"]
    gateway_record.refresh_from_db()
    assert (
        gateway_record.pk,
        gateway_record.invocation_id,
        tuple(gateway_record.publications.order_by("publication_key").values_list("pk", "publication_key")),
    ) == gateway_row_refs
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key=rename_key)
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "success", "intent", "replay"]

    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "G1 renamed"
    run.refresh_from_db()
    assert (
        run.state,
        run.invocation_count,
        run.last_invocation_id,
        run.cumulative_usage,
    ) == plane_run_state_before_gateway

    changed_gateway_request = api_key_client.post(
        "/api/v1/operations/",
        _gateway_body(workspace, gateway_project, gateway_issue, key=rename_key, name="Conflicting rename"),
        format="json",
    )
    assert changed_gateway_request.status_code == 409
    assert changed_gateway_request.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "G1 renamed"

    with pytest.raises(ValueError, match="append-only"):
        OperationGatewayAudit.objects.filter(pk=first_body["audit_receipt"]).update(outcome="failure")
    assert OperationGatewayAudit.objects.get(pk=first_body["audit_receipt"]).outcome == "success"

    denied_user = User.objects.create(email="g1-denied@plane.so", username="g1-denied")
    denied_client = _api_client_for_user(denied_user)
    denied = denied_client.post(
        "/api/v1/operations/",
        _gateway_body(workspace, gateway_project, gateway_issue, key="g1-denied", name="Denied rename"),
        format="json",
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "NOT_AUTHORIZED"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "G1 renamed"
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="g1-denied")
        .order_by("created_at", "id")
        .values_list("outcome", flat=True)
    ) == ["intent", "denied"]

    outcome = propose_outcome(
        run,
        summary="The assigned work item was renamed through the shared gateway.",
        artifacts=["artifact:g1-rename-result"],
        evidence=["evidence:g1-gateway-audit", "evidence:g1-runtime-envelope"],
        idempotency_key="idempotency:g1-outcome",
        created_by=create_user,
    )
    run.refresh_from_db()
    invocation.refresh_from_db()
    assignment.refresh_from_db()
    terminal = RunTerminalEvent.objects.get(run=run)
    assert run.__class__ is RunAttempt
    assert OutcomeSubmission.objects.filter(run=run).count() == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    terminal_refs = (terminal.pk, terminal.product_event_ref, terminal.product_ref)
    outcome_refs = (outcome.pk, outcome.submission_idempotency_key)
    assert run.state == RunState.SUCCEEDED
    assert invocation.state == InvocationState.SUCCEEDED
    assert assignment.state == AssignmentState.ACTIVE
    assert outcome.artifacts == ["artifact:g1-rename-result"]
    assert outcome.evidence == ["evidence:g1-gateway-audit", "evidence:g1-runtime-envelope"]

    replayed_outcome = propose_outcome(
        run,
        summary="The assigned work item was renamed through the shared gateway.",
        artifacts=["artifact:g1-rename-result"],
        evidence=["evidence:g1-gateway-audit", "evidence:g1-runtime-envelope"],
        idempotency_key="idempotency:g1-outcome",
        created_by=create_user,
    )
    replayed_terminal = RunTerminalEvent.objects.get(run=run)
    assert (replayed_outcome.pk, replayed_outcome.submission_idempotency_key) == outcome_refs
    assert (replayed_terminal.pk, replayed_terminal.product_event_ref, replayed_terminal.product_ref) == terminal_refs
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1

    with pytest.raises(IdempotencyConflictError, match="Outcome idempotency"):
        propose_outcome(
            run,
            summary="Changed material must conflict.",
            artifacts=["artifact:g1-conflict"],
            evidence=["evidence:g1-conflict"],
            idempotency_key="idempotency:g1-outcome",
            created_by=create_user,
        )

    run.refresh_from_db()
    assert run.state == RunState.SUCCEEDED
    assert run.invocation_count == 1
    assert run.cumulative_usage == plane_run_state_before_gateway[3]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM agent_run_terminal_events WHERE run_id = %s AND visible = TRUE",
            [run.id],
        )
        assert cursor.fetchone()[0] == 1

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""G4 backend-only evidence for bounded operator health and diagnosis."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from plane.agent import runtime
from plane.agent.lifecycle import (
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    record_invocation,
    transition_run,
)
from plane.agent.operations_readback import MAX_OPERATOR_ITEMS
from plane.db.models import AgentRole, OutcomeSubmission, RunState, RuntimeReconciliation
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency


def _url(workspace, suffix):
    return f"/api/v1/workspaces/{workspace.slug}/agent-admin/operator/{suffix}"


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_health_api_cli_parity_and_explicit_runtime_authority_boundary(
    api_key_client,
    workspace,
    capsys,
):
    api_response = api_key_client.get(_url(workspace, "health/"), {"limit": 1})
    assert api_response.status_code == 200
    api_body = api_response.json()
    assert api_body["schema_version"] == "plane.agent.operator/v1"
    assert api_body["health"]["readiness"]["ready"] is False
    assert api_body["health"]["runtime"]["status"] == "external_required"
    assert api_body["safety_stop"]["status"] == "external_required"
    assert api_body["versions"]["catalog_digest"].startswith("content:")

    call_command("agent_operator_health", workspace_slug=workspace.slug, limit=1)
    cli_body = json.loads(capsys.readouterr().out)
    assert cli_body == api_body
    encoded = json.dumps(api_body, sort_keys=True).encode("utf-8")
    assert len(encoded) <= 8 * 1024
    assert "password" not in encoded.decode("utf-8").casefold()
    assert "token" not in encoded.decode("utf-8").casefold()


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_health_does_not_expose_runtime_exception_text(api_key_client, workspace, monkeypatch):
    def failed_health(**_kwargs):
        raise RuntimeError("secret deployment path /srv/private/runtime")

    monkeypatch.setattr(runtime, "operator_health_readback", failed_health, raising=False)
    response = api_key_client.get(_url(workspace, "health/"), {"limit": 1})

    assert response.status_code == 200
    assert response.json()["health"]["runtime"]["reason"] == "The runtime operator adapter failed."
    assert "/srv/private/runtime" not in response.content.decode("utf-8")


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_readback_has_stable_pagination_and_correlation_gaps(
    api_key_client,
    workspace,
    create_user,
    capsys,
):
    actor = create_actor(workspace=workspace, display_name="G4 operator worker", created_by=create_user)
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Produce a bounded operator proof.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        target_ref="issue:g4-operator",
        objective="Produce a bounded operator proof.",
        acceptance_criteria=["The operator can diagnose this run."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, created_by=create_user)
    record_invocation(run, idempotency_key="idempotency:g4-operator-readback")

    api_response = api_key_client.get(_url(workspace, "readback/"), {"limit": 1})
    assert api_response.status_code == 200
    api_body = api_response.json()
    assert api_body["runs"]["page"]["limit"] == 1
    assert api_body["runs"]["active"][0]["run_id"] == str(run.id)
    assert api_body["runs"]["page"]["ordering"] == ["created_at:desc", "id:desc"]
    assert len(json.dumps(api_body, sort_keys=True).encode("utf-8")) <= 8 * 1024
    assert "raw_payload" not in json.dumps(api_body, sort_keys=True)

    call_command("agent_operator_readback", workspace_slug=workspace.slug, limit=1)
    assert json.loads(capsys.readouterr().out) == api_body

    correlation = api_key_client.get(_url(workspace, "readback/"), {"limit": 1, "run_id": str(run.id)})
    assert correlation.status_code == 200
    linkage = correlation.json()["correlation"]["linkage"]
    assert linkage["complete"] is False
    assert set(linkage["missing"]) >= {"runtime_event", "runtime_exit", "gateway_receipt", "outcome", "terminal_event"}

    denied = api_key_client.get(
        "/api/v1/workspaces/not-a-real-workspace/agent-admin/operator/readback/",
        {"limit": MAX_OPERATOR_ITEMS},
    )
    assert denied.status_code == 403
    assert "G4 operator worker" not in denied.content.decode("utf-8")


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_reconciliation_api_is_idempotent_and_conflict_bound(api_key_client, workspace, create_user):
    actor = create_actor(workspace=workspace, display_name="G4 reconciliation worker", created_by=create_user)
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Reconcile one unknown run.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        target_ref="issue:g4-reconciliation-api",
        objective="Reconcile one unknown run.",
        acceptance_criteria=["No replay occurs."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:api-reconcile-invocation")
    transition_run(run, RunState.OUTCOME_UNKNOWN)
    outcome = OutcomeSubmission.objects.create(
        workspace=workspace, project=run.project, run=run, summary="Submitted", artifacts=[], evidence=[]
    )
    receipt = OperationGatewayIdempotency.objects.create(
        invocation_id=invocation.pk,
        operation_id="agent.outcome.submit",
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        caller_id=create_user.id,
        idempotency_key="gateway:api-reconcile-submit",
        correlation_id="correlation:api-reconcile",
        request_digest="d" * 64,
        state=OperationGatewayIdempotency.State.SUCCEEDED,
        request_input={},
        result={"outcome": {"outcomeRef": f"outcome-submission:{outcome.id}"}},
    )
    OperationGatewayAudit.objects.create(
        invocation_id=invocation.pk,
        phase=OperationGatewayAudit.Phase.OUTCOME,
        outcome=OperationGatewayAudit.Outcome.SUCCESS,
        request_id=receipt.request_id,
        operation_id=receipt.operation_id,
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        caller_id=create_user.id,
        idempotency_key=receipt.idempotency_key,
        correlation_id=receipt.correlation_id,
        request_digest=receipt.request_digest,
    )
    payload = {"run_id": str(run.id), "idempotency_key": "idempotency:api-reconcile-decision"}
    first = api_key_client.post(_url(workspace, "reconcile/"), payload, format="json")
    second = api_key_client.post(_url(workspace, "reconcile/"), payload, format="json")
    conflict = api_key_client.post(
        _url(workspace, "reconcile/"),
        {**payload, "idempotency_key": "idempotency:api-reconcile-other"},
        format="json",
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["reconciliation"]["id"] == first.json()["reconciliation"]["id"]
    assert first.json()["reconciliation"]["fresh_assignment_decision"] == "unsafe"
    assert conflict.status_code == 409
    reconciliation = RuntimeReconciliation.objects.get(pk=first.json()["reconciliation"]["id"])
    assert reconciliation.created_by_id == create_user.id
    assert reconciliation.updated_by_id is None
    assert RuntimeReconciliation.objects.filter(invocation=invocation).count() == 1


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_canary_is_deterministic_and_live_mode_is_external_required(api_key_client, workspace, capsys):
    offline = api_key_client.get(_url(workspace, "canary/"), {"mode": "offline"})
    assert offline.status_code == 200
    first = offline.json()
    assert first["schema_version"] == "plane.agent.canary/v1"
    assert first["status"] == "pass"
    assert [row["observed"] for row in first["results"]] == ["permitted", "denied", "denied"]
    call_command("agent_canary", workspace_slug=workspace.slug, mode="offline")
    assert json.loads(capsys.readouterr().out) == first

    live = api_key_client.get(_url(workspace, "canary/"), {"mode": "live"})
    assert live.status_code == 200
    assert live.json()["status"] == "external_required"
    assert live.json()["fixtures"] == []


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_safety_stop_never_falls_back_without_runtime_hook(
    api_key_client,
    workspace,
    create_user,
    capsys,
):
    actor = create_actor(workspace=workspace, display_name="G4 stop worker", created_by=create_user)
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Wait for the operator.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        target_ref="issue:g4-stop",
        objective="Wait for a stop request.",
        acceptance_criteria=["The stop request is explicit."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g4-stop")

    response = api_key_client.post(
        _url(workspace, "safety-stop/"),
        {
            "invocation_id": invocation.invocation_id,
            "reason": "Stop canary",
            "idempotency_key": "idempotency:stop-g4",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["control"]["status"] == "accepted"
    assert response.json()["control"]["runtime_enforcement"]["status"] == "external_required"
    invocation.refresh_from_db()
    assert invocation.state == "cancelled"
    assert invocation.terminal_event.kind == "run_cancellation"
    assert invocation.terminal_event.idempotency_key == "idempotency:stop-g4"

    call_command(
        "agent_operator_control",
        workspace_slug=workspace.slug,
        invocation_id=invocation.invocation_id,
        reason="Stop canary",
        idempotency_key="idempotency:stop-g4",
    )
    cli_body = json.loads(capsys.readouterr().out)
    assert cli_body["control"]["status"] == "accepted"
    assert cli_body["control"]["runtime_enforcement"]["status"] == "external_required"

    conflict = api_key_client.post(
        _url(workspace, "safety-stop/"),
        {
            "invocation_id": invocation.invocation_id,
            "reason": "Stop canary",
            "idempotency_key": "idempotency:stop-g4-conflict",
        },
        format="json",
    )
    assert conflict.status_code == 409
    assert invocation.run.terminal_events.count() == 1

    changed_reason = api_key_client.post(
        _url(workspace, "safety-stop/"),
        {
            "invocation_id": invocation.invocation_id,
            "reason": "A different stop command",
            "idempotency_key": "idempotency:stop-g4",
        },
        format="json",
    )
    assert changed_reason.status_code == 409
    assert invocation.run.terminal_events.count() == 1


@pytest.mark.contract
@pytest.mark.django_db
def test_operator_runtime_adapter_drives_health_and_control_parity(
    api_key_client,
    workspace,
    create_user,
    capsys,
    monkeypatch,
):
    actor = create_actor(workspace=workspace, display_name="G4 adapter worker", created_by=create_user)
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Exercise the runtime adapter.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        target_ref="issue:g4-adapter",
        objective="Exercise the runtime adapter.",
        acceptance_criteria=["Plane records the stop before runtime enforcement."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g4-adapter")

    def health(*, workspace_id, limit):
        assert workspace_id == str(workspace.id)
        assert limit == 1
        return {
            "status": "degraded",
            "ready": False,
            "code": "RUNTIME_DRAINING",
            "safety_stop": {"status": "draining", "requested": True},
        }

    def safety_stop(*, workspace_id, invocation_id, reason, idempotency_key):
        assert workspace_id == str(workspace.id)
        assert invocation_id == invocation.invocation_id
        assert reason == "Drain this invocation"
        assert idempotency_key == "idempotency:stop-g4-adapter"
        return {"status": "accepted", "idempotency_key": idempotency_key, "invocation_id": invocation_id}

    monkeypatch.setattr(runtime, "operator_health_readback", health, raising=False)
    monkeypatch.setattr(runtime, "request_operator_safety_stop", safety_stop, raising=False)

    health_response = api_key_client.get(_url(workspace, "health/"), {"limit": 1})
    assert health_response.status_code == 200
    health_body = health_response.json()
    assert health_body["health"]["runtime"]["status"] == "degraded"
    assert health_body["safety_stop"]["status"] == "draining"
    call_command("agent_operator_health", workspace_slug=workspace.slug, limit=1)
    assert json.loads(capsys.readouterr().out) == health_body

    control_response = api_key_client.post(
        _url(workspace, "safety-stop/"),
        {
            "invocation_id": invocation.invocation_id,
            "reason": "Drain this invocation",
            "idempotency_key": "idempotency:stop-g4-adapter",
        },
        format="json",
    )
    assert control_response.status_code == 200, control_response.content
    control_body = control_response.json()
    assert control_body["control"]["plane_control"]["state"] == "cancelled"
    assert control_body["control"]["runtime_enforcement"]["status"] == "accepted"
    call_command(
        "agent_operator_control",
        workspace_slug=workspace.slug,
        invocation_id=invocation.invocation_id,
        reason="Drain this invocation",
        idempotency_key="idempotency:stop-g4-adapter",
    )
    assert json.loads(capsys.readouterr().out) == control_body

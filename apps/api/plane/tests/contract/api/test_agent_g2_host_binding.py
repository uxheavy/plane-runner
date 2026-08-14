"""Plane-side host socket proof for the Hermes production callback seam."""

import json
import socket

import pytest

from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run, record_invocation
from plane.agent.runtime.host_rpc import (
    PlaneHostCall,
    PlaneHostResult,
    PlaneHostServer,
    build_gateway_host_port,
)
from plane.db.models import (
    AgentRole,
    Issue,
    OperationGatewayAudit,
    OutcomeSubmission,
    Project,
    ProjectMember,
    RunTerminalEvent,
    State,
)
from plane.operation_gateway.gateway import OperationGateway


def _call(*, run_id, invocation_id, action, operation_ref, input, source="model"):
    return PlaneHostCall(
        run_id=run_id,
        invocation_id=invocation_id,
        correlation_id="correlation:g2-host",
        action=action,
        operation_ref=operation_ref,
        input=input,
        source=source,
        request_ref="",
        idempotency_key="",
    )


def _round_trip(path, call):
    payload = json.dumps(call.to_wire(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(path))
        connection.sendall(payload)
        data = bytearray()
        while not data.endswith(b"\n"):
            chunk = connection.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
    return PlaneHostResult.from_wire(bytes(data[:-1]))


@pytest.fixture
def gateway_project(db, workspace, create_user):
    project = Project.objects.create(
        name="G2 Gateway Project",
        identifier="G2H",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=project,
        workspace=workspace,
        created_by=create_user,
    )
    return project


@pytest.fixture
def gateway_issue(db, gateway_project, workspace, create_user):
    return Issue.objects.create(
        name="G2 Gateway Issue",
        project=gateway_project,
        workspace=workspace,
        created_by=create_user,
    )


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_invocation_scoped_socket_routes_gateway_and_explicit_outcome(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 socket worker",
        credential_ref="plane-credential:g2-socket",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the trusted Plane host.",
        runtime_defaults={"maxCodeModeCalls": 16},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the G2 host callback.",
        acceptance_criteria=["One explicit outcome is published."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-host-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g2-host-invocation", trigger="initial")
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-host.sock", invoke=port.invoke)
    server.start()
    try:
        common = {"run_id": run.snapshot["runId"], "invocation_id": invocation.invocation_id}
        discovered = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="discover",
                operation_ref="plane.operations.discover@1",
                input={"query": "outcome", "limit": 50},
            ),
        )
        assert discovered.status == "ok"
        assert any(item["operationId"] == "agent.outcome.submit" for item in discovered.output["result"]["operations"])

        read = _call(
            **common,
            action="read",
            operation_ref="operation:work_item.read",
            input={"project_id": str(gateway_project.id), "issue_id": str(gateway_issue.id)},
        )
        read_result = _round_trip(server.socket_path, read)
        assert read_result.status == "ok"
        assert read_result.output["result"]["work_item"]["id"] == str(gateway_issue.id)

        mutate = _call(
            **common,
            action="mutate",
            operation_ref="operation:work_item.rename",
            input={
                "project_id": str(gateway_project.id),
                "issue_id": str(gateway_issue.id),
                "name": "G2 renamed",
            },
        )
        mutation_result = _round_trip(server.socket_path, mutate)
        assert mutation_result.status == "ok"
        gateway_issue.refresh_from_db()
        assert gateway_issue.name == "G2 renamed"

        submit = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={
                    "run_ref": run.snapshot["runId"],
                    "summary": "The work item was renamed through the Plane gateway.",
                    "artifacts": ["artifact:g2-rename"],
                    "evidence": ["evidence:g2-gateway-audit"],
                },
            ),
        )
        assert submit.status == "ok", submit
        outcome_ref = submit.output["result"]["outcome"]["outcomeRef"]
        publish = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="publish",
                operation_ref="operation:agent.outcome.publish",
                input={
                    "kind": "outcome",
                    "resourceRef": outcome_ref,
                    "content": "Explicit outcome publication.",
                },
            ),
        )
        assert publish.status == "ok", publish
        assert publish.publication["productRef"] == outcome_ref
        assert publish.publication["productKind"] == "outcome_submission"
        assert publish.publication["productEventRef"].startswith("product-event:")

        replay = _round_trip(server.socket_path, mutate)
        assert replay.status == "replayed"
        assert replay.replayed is True
        gateway_issue.refresh_from_db()
        assert gateway_issue.name == "G2 renamed"
    finally:
        server.close()

    run.refresh_from_db()
    invocation.refresh_from_db()
    assert OutcomeSubmission.objects.filter(run=run).count() == 1
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert OperationGatewayAudit.objects.filter(operation_id="work_item.rename").count() == 2
    assert OperationGatewayAudit.objects.filter(operation_id="agent.outcome.submit").count() >= 2
    assert OperationGatewayAudit.objects.filter(operation_id="agent.outcome.publish").count() >= 2
    assert not server.socket_path.exists()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_replayed_outcome_publication_is_audit_only(
    workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 replay publication worker",
        credential_ref="plane-credential:g2-replay-publication",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the trusted Plane host.",
        runtime_defaults={"maxCodeModeCalls": 16},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise publication replay accounting.",
        acceptance_criteria=["One applied outcome publication is retained."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-replay-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g2-replay-invocation", trigger="initial")
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    common = {"run_id": run.snapshot["runId"], "invocation_id": invocation.invocation_id}

    submit = port.invoke(
        _call(
            **common,
            action="mutate",
            operation_ref="operation:agent.outcome.submit",
            input={"run_ref": run.snapshot["runId"], "summary": "One submitted outcome."},
        )
    )
    assert submit.status == "ok"
    outcome_ref = submit.output["result"]["outcome"]["outcomeRef"]
    publish_call = _call(
        **common,
        action="publish",
        operation_ref="operation:agent.outcome.publish",
        input={"kind": "outcome", "resourceRef": outcome_ref, "content": "One publication."},
    )

    applied = port.invoke(publish_call)
    replay = port.invoke(publish_call)

    assert applied.status == "ok"
    assert applied.publication["action"] == "applied"
    assert replay.status == "replayed"
    assert replay.replayed is True
    assert replay.publication is None
    publish_audits = OperationGatewayAudit.objects.filter(
        correlation_id="correlation:g2-host",
        operation_id="agent.outcome.publish",
        phase="outcome",
    ).order_by("created_at", "id")
    assert list(publish_audits.values_list("outcome", flat=True)) == ["success", "replay"]
    assert OutcomeSubmission.objects.filter(run=run).count() == 1
    assert RunTerminalEvent.objects.filter(invocation=invocation, visible=True).count() == 1

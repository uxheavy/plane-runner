"""Plane-side host socket proof for the Hermes production callback seam."""

import hashlib
import json
import socket
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone
import pytest

from plane.agent.code_mode.contracts import CODE_MODE_EXECUTION_OPERATION, CODE_MODE_SCHEMA_VERSION
from plane.agent.lifecycle import (
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    record_invocation,
    transition_run,
)
from plane.agent.runtime.host_rpc import (
    MAX_HOST_RESULT_BYTES,
    PlaneHostCall,
    PlaneHostResult,
    PlaneHostServer,
    build_gateway_host_port,
)
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import (
    AgentRole,
    Issue,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    OutcomeSubmission,
    Project,
    ProjectMember,
    RunState,
    RunTerminalEvent,
    RuntimeInvocationControl,
    State,
)
from plane.operation_gateway.gateway import OperationGateway
from plane.operation_gateway.operations import OperationRequest


def _call(*, run_id, invocation_id, action, operation_ref, input, source="model", correlation_id="correlation:g2-host"):
    return PlaneHostCall(
        run_id=run_id,
        invocation_id=invocation_id,
        correlation_id=correlation_id,
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


def _code_call(*, run_id, invocation_id, source, input_data=None):
    return _call(
        run_id=run_id,
        invocation_id=invocation_id,
        action="code",
        operation_ref=CODE_MODE_EXECUTION_OPERATION,
        source="code",
        input={
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "entrypoint": "default",
            "source": source,
            "input": input_data or {},
        },
    )


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
                input={"query": "rename work item"},
            ),
        )
        assert discovered.status == "ok"
        assert discovered.output["status"] == "ok"
        assert "workItems" in discovered.output["declarations"]

        read = _call(
            **common,
            action="read",
            operation_ref="operation:work_item.read",
            input={"project_id": str(gateway_project.id), "issue_id": str(gateway_issue.id)},
        )
        read_result = _round_trip(server.socket_path, read)
        assert read_result.status == "ok"
        assert read_result.output["result"]["work_item"]["id"] == str(gateway_issue.id)

        evaluate = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.evaluate",
                input={
                    "outcome_ref": "outcome-submission:not-authorized",
                    "evaluator_ref": "agent-actor:spoofed",
                    "verdict": "revision_requested",
                },
            ),
        )
        assert evaluate.status == "denied"
        assert evaluate.error_code == "NOT_AUTHORIZED"

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

        large_summary = "s" * 4096
        large_evidence = ["e" * 60 for _ in range(62)]
        submit = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={
                    "run_ref": "run:substitution",
                    "summary": large_summary,
                    "artifacts": ["artifact:g2-rename"],
                    "evidence": large_evidence,
                },
            ),
        )
        assert submit.status == "ok", submit
        assert len(json.dumps(submit.to_wire(), separators=(",", ":")).encode()) <= MAX_HOST_RESULT_BYTES
        assert set(submit.output["result"]["outcome"]) == {"outcomeRef", "state", "productEventRef"}
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

        trusted_actor_ref = port._host.binding.actor_ref
        port._host.request.agent_actor_ref = "actor:substitution"
        mismatched_binding = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={"summary": "Must not disclose the terminal outcome."},
            ),
        )
        assert mismatched_binding.status == "denied"
        assert mismatched_binding.error_code == "CALLBACK_BINDING_INVALID"
        assert "outcome" not in mismatched_binding.output.get("result", {})
        port._host.request.agent_actor_ref = trusted_actor_ref

        exact_duplicate_submit = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={
                    "summary": large_summary,
                    "artifacts": ["artifact:g2-rename"],
                    "evidence": large_evidence,
                },
            ),
        )
        assert exact_duplicate_submit.status == "replayed"
        assert exact_duplicate_submit.replayed is True
        assert exact_duplicate_submit.error_code is None
        assert (
            len(json.dumps(exact_duplicate_submit.to_wire(), separators=(",", ":")).encode())
            <= MAX_HOST_RESULT_BYTES
        )
        assert exact_duplicate_submit.output["result"]["outcome"] == submit.output["result"]["outcome"]

        duplicate_submit = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={
                    "summary": "A conflicting duplicate terminal outcome.",
                    "artifacts": ["artifact:g2-conflict"],
                    "evidence": ["evidence:g2-conflict"],
                },
            )
        )
        assert duplicate_submit.status == "conflict"
        assert duplicate_submit.error_code == "PLANE_CONFLICT"
        assert duplicate_submit.replayed is False

        wrong_binding = _round_trip(
            server.socket_path,
            _call(
                run_id="run:substitution",
                invocation_id=common["invocation_id"],
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={
                    "run_ref": "run:substitution",
                    "summary": "A substituted terminal outcome.",
                },
            )
        )
        assert wrong_binding.status == "denied"
        assert wrong_binding.error_code == "CALLBACK_BINDING_INVALID"
        assert wrong_binding.output is None

        wrong_invocation = _round_trip(
            server.socket_path,
            _call(
                run_id=common["run_id"],
                invocation_id="invocation:substitution",
                action="mutate",
                operation_ref="operation:agent.outcome.submit",
                input={"run_ref": "run:substitution", "summary": "Must not disclose."},
            ),
        )
        assert wrong_invocation.status == "denied"
        assert wrong_invocation.error_code == "CALLBACK_BINDING_INVALID"
        assert wrong_invocation.output is None

        late_mutation = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="mutate",
                operation_ref="operation:work_item.rename",
                input={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "G2 must not mutate after publication",
                },
            ),
        )
        assert late_mutation.status == "conflict"
        assert late_mutation.error_code == "PLANE_CONFLICT"
        assert late_mutation.replayed is False
        gateway_issue.refresh_from_db()
        assert gateway_issue.name == "G2 renamed"

        unknown_run = create_run(
            assignment,
            profile,
            idempotency_key="idempotency:g2-unknown-run",
            created_by=create_user,
        )
        unknown_invocation = record_invocation(
            unknown_run,
            idempotency_key="idempotency:g2-unknown-invocation",
            trigger="initial",
        )
        unknown_port = build_gateway_host_port(invocation=unknown_invocation, gateway=OperationGateway())
        transition_run(unknown_run, RunState.OUTCOME_UNKNOWN)
        unknown_mutation = unknown_port.invoke(
            _call(
                run_id=unknown_run.snapshot["runId"],
                invocation_id=unknown_invocation.invocation_id,
                action="mutate",
                operation_ref="operation:work_item.rename",
                input={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "G2 must not mutate after unknown outcome",
                },
            )
        )
        assert unknown_mutation.status == "conflict"
        assert unknown_mutation.error_code == "PLANE_CONFLICT"
        assert unknown_mutation.replayed is False
        gateway_issue.refresh_from_db()
        assert gateway_issue.name == "G2 renamed"

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
    outcome = OutcomeSubmission.objects.get(run=run)
    assert outcome.run_id == run.id
    assert outcome.summary == large_summary
    assert outcome.evidence == large_evidence
    assert RunTerminalEvent.objects.filter(run=run, visible=True).count() == 1
    assert OperationGatewayAudit.objects.filter(operation_id="work_item.rename").count() == 2
    assert OperationGatewayAudit.objects.filter(operation_id="agent.outcome.submit").count() >= 2
    assert OperationGatewayAudit.objects.filter(operation_id="agent.outcome.publish").count() >= 2
    assert not server.socket_path.exists()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_code_mode_catalog_describe_projects_operation_id_for_next_callback(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    """Code Mode can use catalog.describe output to resolve its next operation."""

    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 Code Mode catalog worker",
        credential_ref="plane-credential:g2-code-catalog",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the typed TypeScript host.",
        runtime_defaults={"maxCodeModeCalls": 4},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Resolve a catalog operation and rename the assigned work item.",
        acceptance_criteria=["The described operation is callable by its exact operationId."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-code-catalog-run", created_by=create_user)
    invocation = record_invocation(
        run,
        idempotency_key="idempotency:g2-code-catalog-invocation",
        trigger="initial",
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-code-catalog.sock", invoke=port.invoke)
    server.start()
    try:
        result = _round_trip(
            server.socket_path,
            _code_call(
                run_id=run.snapshot["runId"],
                invocation_id=invocation.invocation_id,
                source="""
                    export default async function ({host, input}: {host: any; input: any}) {
                        const described = await host.call_plane_operation(
                            "catalog.describe", {operation_id: "work_item.rename"},
                            "idempotency:g2-code-catalog-describe",
                            "correlation:g2-code-catalog-describe"
                        );
                        const operationId = described.result?.operation?.operationId;
                        if (typeof operationId !== "string") throw new Error("operationId unavailable");
                        return await host.call_plane_operation(
                            operationId, input,
                            "idempotency:g2-code-catalog-rename",
                            "correlation:g2-code-catalog-rename"
                        );
                    }
                """,
                input_data={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "G2 catalog-resolved rename",
                },
            ),
        )
        assert result.status == "ok", result
        assert result.output["result"]["ok"] is True
    finally:
        server.close()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_invocation_scoped_socket_executes_typescript_through_the_bound_host(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 TypeScript worker",
        credential_ref="plane-credential:g2-typescript",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the typed TypeScript host.",
        runtime_defaults={"maxCodeModeCalls": 1},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the live TypeScript Code Mode bridge.",
        acceptance_criteria=["One code callback renames the assigned work item."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-typescript-run", created_by=create_user)
    invocation = record_invocation(run, idempotency_key="idempotency:g2-typescript-invocation", trigger="initial")
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-typescript-host.sock", invoke=port.invoke)
    server.start()
    try:
        code_call = _call(
            run_id=run.snapshot["runId"],
            invocation_id=invocation.invocation_id,
            action="code",
            operation_ref=CODE_MODE_EXECUTION_OPERATION,
            source="code",
            input={
                "schemaVersion": CODE_MODE_SCHEMA_VERSION,
                "entrypoint": "default",
                "source": """
                    export default async function ({host, input}: {
                        host: {
                            call_plane_operation: (
                                operationId: string,
                                input: Record<string, unknown>,
                                idempotencyKey: string,
                                correlationId: string
                            ) => Promise<Record<string, unknown>>;
                        };
                        input: Record<string, unknown>;
                    }): Promise<Record<string, unknown>> {
                        return await host.call_plane_operation(
                            "work_item.rename", input,
                            "idempotency:g2-typescript-rename",
                            "correlation:g2-typescript-rename"
                        );
                    }
                """,
                "input": {
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "G2 TypeScript renamed",
                },
            },
        )
        result = _round_trip(server.socket_path, code_call)
        assert result.status == "ok", result
        assert result.output["schemaVersion"] == CODE_MODE_SCHEMA_VERSION
        assert result.output["result"]["ok"] is True
        assert result.output["observations"] == [
            {
                "source": "code",
                "action": "code",
                "operationRef": "operation:work_item.rename",
                "status": "ok",
                "requestId": result.output["observations"][0]["requestId"],
                "gatewayReceipt": result.output["observations"][0]["gatewayReceipt"],
                "auditReceipt": result.output["observations"][0]["auditReceipt"],
                "targetDigest": hashlib.sha256(
                    json.dumps(
                        {
                            "project_id": str(gateway_project.id),
                            "issue_id": str(gateway_issue.id),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            }
        ]
        gateway_issue.refresh_from_db()
        assert gateway_issue.name == "G2 TypeScript renamed"
        assert (
            OperationGatewayIdempotency.objects.filter(idempotency_key="idempotency:g2-typescript-rename").count()
            == 1
        )
        assert OperationGatewayAudit.objects.filter(operation_id="work_item.rename").count() == 2

        budget_exhausted = _round_trip(
            server.socket_path,
            _code_call(
                **{"run_id": run.snapshot["runId"], "invocation_id": invocation.invocation_id},
                source="""
                    export default async function ({host}: {host: any}) {
                        return await host.call_plane_operation(
                            "work_item.read", {},
                            "idempotency:g2-typescript-budget",
                            "correlation:g2-typescript-budget"
                        );
                    }
                """,
            ),
        )
        assert budget_exhausted.status == "denied"
        assert budget_exhausted.error_code == "BUDGET_EXCEEDED"

        replay = _round_trip(server.socket_path, code_call)
        assert replay.status == "replayed"
        assert replay.replayed is True
        assert replay.output == result.output
        assert (
            OperationGatewayIdempotency.objects.filter(idempotency_key="idempotency:g2-typescript-rename").count()
            == 1
        )
        assert OperationGatewayAudit.objects.filter(operation_id="work_item.rename").count() == 2
    finally:
        server.close()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_code_mode_search_to_read_preserves_target_and_denies_cross_project(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    """The real host callback keeps the search target and live auth distinguishes its denial."""

    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 search-bound worker",
        credential_ref="plane-credential:g2-search-bound",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the invocation-bound TypeScript host.",
        runtime_defaults={"maxCodeModeCalls": 16},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Exercise the search-to-read callback binding.",
        acceptance_criteria=["Read the searched item and deny an unprivileged item."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g2-search-bound-run", created_by=create_user)
    invocation = record_invocation(
        run,
        idempotency_key="idempotency:g2-search-bound-invocation",
        trigger="initial",
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-search-bound.sock", invoke=port.invoke)
    server.start()
    common = {"run_id": run.snapshot["runId"], "invocation_id": invocation.invocation_id}
    assert port._host.request.user.id == actor.principal_id
    assert port._host.request.agent_actor_ref == f"actor:{actor.id}"
    read_source = """
        export default async function ({host, input}: {host: any; input: any}) {
            return await host.call_plane_operation(
                "work_item.read", input,
                "idempotency:g2-search-bound-read",
                "correlation:g2-search-bound-read"
            );
        }
    """
    try:
        read_input = {
            "project_id": str(gateway_project.id),
            "issue_id": str(gateway_issue.id),
        }

        code_mode_search_read = _round_trip(
            server.socket_path,
            _code_call(
                **common,
                source="""
                    export default async function ({host}: {host: any}) {
                        return await host.call_plane_operation(
                            "search_workspace",
                            {query: "G2 Gateway Issue", limit: 1},
                            "idempotency:g2-code-search",
                            "correlation:g2-code-search"
                        );
                    }
                """,
            ),
        )
        assert code_mode_search_read.status == "ok", code_mode_search_read
        assert code_mode_search_read.output["result"]["spilled"]["result"]["spill"]["sizeBytes"] > 0
        assert [item["operationRef"] for item in code_mode_search_read.output["observations"]] == [
            "operation:search_workspace",
            "operation:work_item.read",
        ]

        authorized = _round_trip(
            server.socket_path,
            _code_call(**common, source=read_source, input_data=read_input),
        )
        assert authorized.status == "ok", authorized
        assert authorized.output["result"]["result"]["work_item"]["id"] == str(gateway_issue.id)
        expected_target_digest = hashlib.sha256(
            json.dumps(read_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        authorized_audit = OperationGatewayAudit.objects.get(
            request_id=authorized.output["result"]["requestId"],
            phase=OperationGatewayAudit.Phase.OUTCOME,
        )
        assert authorized_audit.result["targetDigest"] == expected_target_digest
        assert authorized_audit.result["work_item"]["id"] == str(gateway_issue.id)
        assert authorized.output["observations"] == [
            {
                "source": "code",
                "action": "code",
                "operationRef": "operation:work_item.read",
                "status": "ok",
                "requestId": authorized.output["observations"][0]["requestId"],
                "gatewayReceipt": authorized.output["observations"][0]["gatewayReceipt"],
                "auditReceipt": authorized.output["observations"][0]["auditReceipt"],
                "targetDigest": expected_target_digest,
            }
        ]

        ProjectMember.objects.filter(project=gateway_project, member=actor.principal).update(is_active=False)
        live_auth_denial = _round_trip(
            server.socket_path,
            _call(
                **common,
                action="read",
                operation_ref="operation:work_item.read",
                input=read_input,
            ),
        )
        assert live_auth_denial.status == "denied"
        assert live_auth_denial.error_code == "NOT_AUTHORIZED"
        live_auth_record = OperationGatewayIdempotency.objects.get(idempotency_key=live_auth_denial.idempotency_key)
        assert live_auth_record.state == OperationGatewayIdempotency.State.DENIED

        other_project = Project.objects.create(
            name="G2 Unprivileged Project",
            identifier="G2U",
            workspace=workspace,
            created_by=create_user,
        )
        other_issue = Issue.objects.create(
            name="G2 Unprivileged Issue",
            project=other_project,
            workspace=workspace,
            created_by=create_user,
        )
        assert not ProjectMember.objects.filter(project=other_project, member=actor.principal).exists()
        assert not ProjectEntityPermission().has_permission(
            OperationRequest(port._host.request, method="GET"),
            SimpleNamespace(workspace_slug=workspace.slug, project_id=str(other_project.id)),
        )
        denied_input = {"project_id": str(other_project.id), "issue_id": str(other_issue.id)}
        denied = _round_trip(
            server.socket_path,
            _code_call(
                **common,
                source=read_source.replace("g2-search-bound-read", "g2-search-bound-denied"),
                input_data=denied_input,
            ),
        )
        denied_record = OperationGatewayIdempotency.objects.get(idempotency_key="idempotency:g2-search-bound-denied")
        assert denied_record.request_input == denied_input
        assert denied_record.caller_id == actor.principal_id
        denied_audit = OperationGatewayAudit.objects.get(
            request_id=denied_record.request_id,
            phase=OperationGatewayAudit.Phase.OUTCOME,
        )
        assert denied_audit.result == {"targetDigest": hashlib.sha256(
            json.dumps(denied_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()}
        assert denied.status == "ok", denied
        assert denied.output["result"]["ok"] is False
        assert denied.output["result"]["error"]["code"] == "NOT_AUTHORIZED"
        assert denied.output["result"]["targetDigest"] == denied.output["observations"][0]["targetDigest"]
        assert denied.output["observations"][0]["status"] == "denied"
        assert denied.output["observations"][0]["errorCode"] == "NOT_AUTHORIZED"
        assert denied.output["observations"][0]["targetDigest"] == hashlib.sha256(
            json.dumps(denied_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        denied_wire = json.dumps(denied.output, sort_keys=True, separators=(",", ":"))
        assert str(other_project.id) not in denied_wire
        assert str(other_issue.id) not in denied_wire
    finally:
        server.close()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_invocation_scoped_socket_rejects_unversioned_typescript_capsule(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    """The execution capsule is versioned and does not accept the legacy unversioned shape."""
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 TypeScript validation worker",
        credential_ref="plane-credential:g2-typescript-validation",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the typed TypeScript host.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Reject an unversioned Code Mode capsule.",
        acceptance_criteria=["No child process or mutation is started."],
        created_by=create_user,
    )
    run = create_run(
        assignment,
        profile,
        idempotency_key="idempotency:g2-typescript-validation-run",
        created_by=create_user,
    )
    invocation = record_invocation(
        run,
        idempotency_key="idempotency:g2-typescript-validation-invocation",
        trigger="initial",
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-typescript-validation.sock", invoke=port.invoke)
    server.start()
    try:
        result = _round_trip(
            server.socket_path,
            _call(
                run_id=run.snapshot["runId"],
                invocation_id=invocation.invocation_id,
                action="code",
                operation_ref=CODE_MODE_EXECUTION_OPERATION,
                source="code",
                input={"source": "export default () => null", "input": {}},
            ),
        )
        assert result.status == "invalid"
        assert result.error_code == "VALIDATION_ERROR"
        assert OperationGatewayAudit.objects.filter(operation_id="work_item.rename").count() == 0
    finally:
        server.close()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_typescript_host_rejects_substitution_expiry_and_capability_escapes(
    tmp_path, workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="G2 TypeScript boundary worker",
        credential_ref="plane-credential:g2-typescript-boundary",
        created_by=create_user,
    )
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Use the invocation-bound TypeScript host.",
        runtime_defaults={"maxCodeModeCalls": 4},
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Reject Code Mode boundary violations.",
        acceptance_criteria=["No unbound or privileged callback can mutate the issue."],
        created_by=create_user,
    )
    run = create_run(
        assignment,
        profile,
        idempotency_key="idempotency:g2-typescript-boundary-run",
        created_by=create_user,
    )
    invocation = record_invocation(
        run,
        idempotency_key="idempotency:g2-typescript-boundary-invocation",
        trigger="initial",
    )
    port = build_gateway_host_port(invocation=invocation, gateway=OperationGateway())
    server = PlaneHostServer(socket_path=tmp_path / "g2-typescript-boundary.sock", invoke=port.invoke)
    server.start()
    common = {"run_id": run.snapshot["runId"], "invocation_id": invocation.invocation_id}
    mutation_source = """
        export default async function ({host, input}: {host: any; input: any}) {
            return await host.call_plane_operation(
                "work_item.rename", input,
                "idempotency:g2-typescript-boundary-rename",
                "correlation:g2-typescript-boundary-rename"
            );
        }
    """
    try:
        wrong_run = _round_trip(
            server.socket_path,
            _code_call(
                run_id="run:substitution",
                invocation_id=common["invocation_id"],
                source=mutation_source,
                input_data={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "must not apply",
                },
            ),
        )
        assert wrong_run.status == "denied"
        assert wrong_run.error_code == "CALLBACK_BINDING_INVALID"

        wrong_invocation = _round_trip(
            server.socket_path,
            _code_call(
                run_id=common["run_id"],
                invocation_id="invocation:substitution",
                source=mutation_source,
                input_data={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "must not apply",
                },
            ),
        )
        assert wrong_invocation.status == "denied"
        assert wrong_invocation.error_code == "CALLBACK_BINDING_INVALID"

        trusted_actor_ref = port._host.request.agent_actor_ref
        port._host.request.agent_actor_ref = "actor:substitution"
        substituted_actor = _round_trip(
            server.socket_path,
            _code_call(
                **common,
                source=mutation_source,
                input_data={
                    "project_id": str(gateway_project.id),
                    "issue_id": str(gateway_issue.id),
                    "name": "must not apply",
                },
            ),
        )
        port._host.request.agent_actor_ref = trusted_actor_ref
        assert substituted_actor.status == "ok"
        assert substituted_actor.output["result"]["ok"] is False
        assert substituted_actor.output["result"]["error"]["code"] == "CALLBACK_BINDING_INVALID"
        assert substituted_actor.output["observations"][0]["errorCode"] == "CALLBACK_BINDING_INVALID"

        oversized = _round_trip(
            server.socket_path,
            _code_call(
                **common,
                source="export default () => 1\n" + ("x" * 4096),
            ),
        )
        assert oversized.status == "invalid"
        assert oversized.error_code == "SOURCE_TOO_LARGE"

        malformed = _round_trip(
            server.socket_path,
            _code_call(**common, source="export default function ("),
        )
        assert malformed.status == "invalid"
        assert malformed.error_code == "CODE_MODE_FAILED"

        sandbox = _round_trip(
            server.socket_path,
            _code_call(
                **common,
                source="""
                    export default async function () {
                        let dynamicImport = "denied";
                        try { await import("node:fs"); dynamicImport = "allowed"; } catch {}
                        let escape = "denied";
                        try { Function("return process")(); escape = "allowed"; } catch {}
                        return {
                            process: typeof process,
                            filesystem: typeof globalThis.require,
                            network: typeof fetch,
                            dynamicImport,
                            escape,
                        };
                    }
                """,
            ),
        )
        assert sandbox.status == "ok", sandbox
        assert sandbox.output["result"] == {
            "process": "undefined",
            "filesystem": "undefined",
            "network": "undefined",
            "dynamicImport": "denied",
            "escape": "denied",
        }

        control = RuntimeInvocationControl.objects.get(invocation=invocation)
        control.cancellation_requested_at = timezone.now()
        control.save(_allow_lifecycle=True, update_fields=["cancellation_requested_at", "updated_at"])
        cancelled = _round_trip(
            server.socket_path,
            _code_call(**common, source="export default () => 1"),
        )
        assert cancelled.status == "denied"
        assert cancelled.error_code == "CANCELLED"

        control.cancellation_requested_at = None
        control.lease_expires_at = timezone.now() - timedelta(seconds=1)
        control.save(
            _allow_lifecycle=True,
            update_fields=["cancellation_requested_at", "lease_expires_at", "updated_at"],
        )
        expired = _round_trip(
            server.socket_path,
            _code_call(**common, source="export default () => 1"),
        )
        assert expired.status == "denied"
        assert expired.error_code == "CANCELLED"
    finally:
        server.close()
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "G2 Gateway Issue"
    assert not OperationGatewayIdempotency.objects.filter(
        idempotency_key="idempotency:g2-typescript-boundary-rename"
    ).exists()


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

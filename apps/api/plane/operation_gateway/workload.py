"""Deterministic PostgreSQL workload for the shared Operation Gateway."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.db import close_old_connections, connection

from plane.db.models import (
    Issue,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    OperationGatewayQuotaBucket,
    Project,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)

from .catalog import operation_reconciliation_matrix
from .gateway import OperationGateway
from .limits import (
    QUOTA_MAX_AGENT_ACTIVE,
    QUOTA_MAX_AGENT_REQUESTS,
    QUOTA_MAX_INVOCATION_ACTIVE,
    QUOTA_MAX_INVOCATION_REQUESTS,
    QUOTA_MAX_WORKSPACE_ACTIVE,
    QUOTA_MAX_WORKSPACE_REQUESTS,
)


GATEWAY_WORKLOAD_MANIFEST = {
    "version": "plane-operation-gateway-load/v2",
    "database": "disposable-postgresql-test-database",
    "workload": (
        {
            "operationId": "project.archive",
            "weight": 1,
            "purpose": "concurrent first-use, replay, and product mutation effect",
        },
        {
            "operationId": "catalog.search",
            "weight": 1,
            "purpose": "real gateway request quota saturation with bounded results",
        },
    ),
    "thresholds": {
        "maxErrorRate": 0.0,
        "minCorrelationCoverage": 1.0,
        "minAuditCoverage": 1.0,
        "maxDuplicateEffects": 0,
        "requireQuotaSaturation": True,
        "requireActualGateway": True,
        "requireAgentDistribution": True,
    },
}


def run_gateway_workload(*, requests: int = 128, workers: int = 8, agent_count: int = 16) -> dict[str, Any]:
    """Exercise the real transactional gateway on a disposable test database.

    The management command intentionally refuses a normal runtime database.
    Product operations and audit/idempotency/quota rows are real; only the
    post-commit task scheduler is patched to keep this offline workload free
    of brokers, providers, and external writes.
    """

    _validate_arguments(requests=requests, workers=workers, agent_count=agent_count)
    _require_disposable_database()
    matrix = operation_reconciliation_matrix()
    matrix_by_id = {row["operationId"]: row for row in matrix["operations"]}
    for row in GATEWAY_WORKLOAD_MANIFEST["workload"]:
        if row["operationId"] not in matrix_by_id and row["operationId"] not in {"catalog.search"}:
            raise RuntimeError(f"Gateway workload operation is not cataloged: {row['operationId']}")

    run_ref = uuid.uuid4().hex[:12]
    actor = User.objects.create(
        username=f"gateway-load-{run_ref}",
        email=f"gateway-load-{run_ref}@example.invalid",
        first_name="Gateway",
        last_name="Load",
    )
    workspace = Workspace.objects.create(
        name=f"Gateway Load {run_ref}",
        owner=actor,
        slug=f"gateway-load-{run_ref}",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=actor, role=20)
    project = Project.objects.create(
        name=f"Gateway Load {run_ref}",
        identifier=f"GL{run_ref[:8].upper()}",
        workspace=workspace,
        created_by=actor,
    )
    ProjectMember.objects.create(project=project, member=actor, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=project,
        workspace=workspace,
        created_by=actor,
    )
    duplicate_key = f"gateway-load-archive-{run_ref}"
    duplicate_correlation_prefix = f"gateway-load:{run_ref}:archive"
    invocation_ref = f"invocation:gateway-load:{run_ref}"
    agent_refs = tuple(f"agent-actor:gateway-load:{run_ref}:{index}" for index in range(agent_count))

    started = time.perf_counter()
    responses: list[tuple[dict[str, Any], int]] = []
    failures = 0
    try:
        request_factory = _request_factory(actor, agent_refs=agent_refs, invocation_ref=invocation_ref)
        with patch("plane.operation_gateway.gateway.schedule_publications_on_commit", lambda record: None):
            duplicate_barrier = __import__("threading").Barrier(4)

            def duplicate_call(index: int) -> tuple[dict[str, Any], int]:
                return _invoke(
                    request_factory,
                    {
                        "schema_version": "plane.operation/v1",
                        "operation_id": "project.archive",
                        "workspace_slug": workspace.slug,
                        "idempotency_key": duplicate_key,
                        "correlation_id": f"{duplicate_correlation_prefix}:{index}",
                        "input": {"project_id": str(project.id), "archive": True},
                    },
                    barrier=duplicate_barrier,
                    agent_index=index,
                )

            with ThreadPoolExecutor(max_workers=max(workers, 4)) as executor:
                duplicate_results = list(executor.map(duplicate_call, range(4)))
            responses.extend(duplicate_results)

            conflict_response = _invoke(
                request_factory,
                {
                    "schema_version": "plane.operation/v1",
                    "operation_id": "project.archive",
                    "workspace_slug": workspace.slug,
                    "idempotency_key": duplicate_key,
                    "correlation_id": f"{duplicate_correlation_prefix}:conflict",
                    "input": {"project_id": str(project.id), "archive": False},
                },
                agent_index=0,
            )
            responses.append(conflict_response)

            remaining = requests - 5

            def read_call(index: int) -> tuple[dict[str, Any], int]:
                return _invoke(
                    request_factory,
                    {
                        "schema_version": "plane.operation/v1",
                        "operation_id": "catalog.search",
                        "workspace_slug": workspace.slug,
                        "idempotency_key": f"gateway-load-read-{run_ref}-{index}",
                        "correlation_id": f"gateway-load:{run_ref}:read:{index}",
                        "input": {"query": "", "limit": 1},
                    },
                    agent_index=index,
                )

            warmup_count = min(agent_count, remaining)
            responses.extend(read_call(index) for index in range(warmup_count))
            remaining -= warmup_count
            with ThreadPoolExecutor(max_workers=workers) as executor:
                responses.extend(executor.map(read_call, range(warmup_count, warmup_count + remaining)))
    finally:
        project_id = project.id
        workspace_id = workspace.id
        # Leave durable gateway evidence in the disposable database for
        # diagnosis, while removing the local product seed records.
        Issue.all_objects.filter(project_id=project_id).delete()
        Project.objects.filter(pk=project_id).delete()
        Workspace.objects.filter(pk=workspace_id).delete()
        User.objects.filter(pk=actor.id).delete()
        close_old_connections()

    elapsed_ms = (time.perf_counter() - started) * 1000
    response_count = len(responses)
    statuses = [status for _, status in responses]
    expected_statuses = {200, 409, 429}
    failures += sum(status not in expected_statuses for status in statuses)
    error_rate = failures / response_count
    throttled = statuses.count(429)
    accepted = response_count - throttled
    correlations = {envelope.get("correlation_id") for envelope, _ in responses if envelope.get("correlation_id")}
    receipts = {envelope.get("audit_receipt") for envelope, _ in responses if envelope.get("audit_receipt")}
    audit_rows = OperationGatewayAudit.objects.filter(
        workspace_slug=workspace.slug,
        correlation_id__in=correlations,
    )
    audit_receipt_ids = {str(value) for value in audit_rows.values_list("id", flat=True)}
    audited_correlations = set(audit_rows.values_list("correlation_id", flat=True))
    duplicate_successes = OperationGatewayAudit.objects.filter(
        workspace_slug=workspace.slug,
        operation_id="project.archive",
        idempotency_key=duplicate_key,
        phase=OperationGatewayAudit.Phase.OUTCOME,
        outcome=OperationGatewayAudit.Outcome.SUCCESS,
    ).count()
    duplicate_records = OperationGatewayIdempotency.objects.filter(
        workspace_slug=workspace.slug,
        operation_id="project.archive",
        idempotency_key=duplicate_key,
    ).count()
    measured_agent_identities = (
        OperationGatewayQuotaBucket.objects.filter(workspace_id=workspace.id, scope="agent")
        .values("subject_key")
        .distinct()
        .count()
    )

    thresholds = dict(GATEWAY_WORKLOAD_MANIFEST["thresholds"])
    correlation_coverage = len(correlations) / response_count
    audit_coverage = len(receipts.intersection(audit_receipt_ids)) / response_count
    correlation_audit_coverage = len(audited_correlations) / len(correlations)
    duplicate_effects = max(duplicate_successes - 1, 0)
    elapsed_seconds = max(elapsed_ms / 1000, 0.000001)
    passes = (
        thresholds["requireActualGateway"]
        and failures == 0
        and error_rate <= thresholds["maxErrorRate"]
        and correlation_coverage >= thresholds["minCorrelationCoverage"]
        and audit_coverage >= thresholds["minAuditCoverage"]
        and correlation_audit_coverage >= thresholds["minAuditCoverage"]
        and duplicate_effects <= thresholds["maxDuplicateEffects"]
        and duplicate_records == 1
        and (not thresholds["requireAgentDistribution"] or measured_agent_identities == agent_count)
        and (not thresholds["requireQuotaSaturation"] or throttled > 0)
    )
    return {
        "manifestVersion": GATEWAY_WORKLOAD_MANIFEST["version"],
        "actualGateway": True,
        "simulation": False,
        "database": str(connection.settings_dict.get("NAME", "")),
        "requests": requests,
        "workers": workers,
        "agents": agent_count,
        "configuredAgentIdentities": agent_count,
        "measuredAgentIdentities": measured_agent_identities,
        "elapsedMs": round(elapsed_ms, 3),
        "throughputPerSecond": round(response_count / elapsed_seconds, 3),
        "accepted": accepted,
        "throttled": throttled,
        "errors": failures,
        "errorRate": round(error_rate, 6),
        "saturation": round(throttled / response_count, 6),
        "correlationCoverage": round(correlation_coverage, 6),
        "auditCoverage": round(audit_coverage, 6),
        "correlationAuditCoverage": round(correlation_audit_coverage, 6),
        "duplicateEffects": duplicate_effects,
        "duplicateCommittedEffects": duplicate_successes,
        "duplicateIdempotencyRows": duplicate_records,
        "productionLimits": {
            "workspaceRequests": QUOTA_MAX_WORKSPACE_REQUESTS,
            "workspaceActive": QUOTA_MAX_WORKSPACE_ACTIVE,
            "agentRequests": QUOTA_MAX_AGENT_REQUESTS,
            "agentActive": QUOTA_MAX_AGENT_ACTIVE,
            "invocationRequests": QUOTA_MAX_INVOCATION_REQUESTS,
            "invocationActive": QUOTA_MAX_INVOCATION_ACTIVE,
        },
        "thresholds": thresholds,
        "passes": passes,
    }


def _invoke(
    request_factory,
    envelope: dict[str, Any],
    *,
    barrier=None,
    agent_index: int = 0,
) -> tuple[dict[str, Any], int]:
    close_old_connections()
    try:
        if barrier is not None:
            barrier.wait(timeout=10)
        return OperationGateway().execute(request_factory(agent_index), envelope)
    finally:
        close_old_connections()


def _request_factory(actor: User, *, agent_refs: tuple[str, ...], invocation_ref: str):
    def factory(agent_index: int):
        return SimpleNamespace(
            user=actor,
            META={"HTTP_HOST": "localhost"},
            method="POST",
            agent_actor_ref=agent_refs[agent_index % len(agent_refs)],
            agent_invocation_ref=invocation_ref,
        )

    return factory


def _require_disposable_database() -> None:
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    database_name = str(connection.settings_dict.get("NAME", ""))
    if settings_module != "plane.settings.test" or not database_name.startswith("test_"):
        raise RuntimeError(
            "The actual gateway workload requires DJANGO_SETTINGS_MODULE=plane.settings.test "
            "and a disposable test database named test_*; simulation is not accepted"
        )


def _validate_arguments(*, requests: int, workers: int, agent_count: int) -> None:
    if not isinstance(requests, int) or isinstance(requests, bool) or not 80 <= requests <= 512:
        raise ValueError("requests must be between 80 and 512 to exercise the production quota")
    if not isinstance(workers, int) or isinstance(workers, bool) or not 2 <= workers <= min(64, requests):
        raise ValueError("workers must be between 2 and the request count")
    if not isinstance(agent_count, int) or isinstance(agent_count, bool) or not 1 <= agent_count <= 64:
        raise ValueError("agent_count must be between 1 and 64")

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import close_old_connections, transaction
from django.utils import timezone

from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run
from plane.agent.memory import create_memory, create_user_preference
from plane.db.models import AgentRole, User, WorkspaceMember
from plane.db.models import OperationGatewayAudit, OperationGatewayIdempotency, OperationGatewayQuotaBucket
from plane.operation_gateway.catalog import (
    MUTATION_RECONCILIATION_POLICIES,
    OperationDescriptor,
    RECONCILIATION_POLICY_VERSION,
    all_operations,
    operation_catalog_snapshot,
    operation_reconciliation_matrix,
)
from plane.operation_gateway.contracts import SCHEMA_VERSION
from plane.operation_gateway.gateway import GatewayFailure, OperationGateway
from plane.operation_gateway.limits import MAX_QUOTA_IDENTITY_LENGTH, QUOTA_MAX_INVOCATION_ACTIVE
from plane.operation_gateway.quota import (
    GatewayQuotaExceeded,
    _bucket_start,
    build_quota_identity,
    cleanup_gateway_quota,
    release_gateway_quota,
    reserve_gateway_quota,
)
from plane.operation_gateway.workload import run_gateway_workload


@pytest.fixture(autouse=True)
def reset_operation_gateway_api_key_throttle_cache():
    """Keep the contract suite focused on the gateway's shared quotas."""

    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern("api_key:*")


@pytest.mark.contract
def test_g4_reconciliation_matrix_is_exact_and_catalog_derived():
    matrix = operation_reconciliation_matrix()
    mutations = {
        descriptor.operation_id: descriptor for descriptor in all_operations() if descriptor.kind == "mutation"
    }
    rows = {row["operationId"]: row for row in matrix["operations"]}

    assert set(rows) == set(mutations)
    assert all(
        rows[operation_id]["strategy"] == descriptor.reconciliation for operation_id, descriptor in mutations.items()
    )
    assert all(
        sum(row[name] for name in ("readAfterWrite", "safeReplay", "outcomeUnknownEscalation")) == 1
        for row in rows.values()
    )
    assert {row["publicationKind"] for row in matrix["publications"]} == {
        "activity",
        "model_activity",
        "notification",
        "webhook",
    }
    assert operation_catalog_snapshot()["reconciliationMatrix"] == matrix
    assert matrix["policyVersion"] == RECONCILIATION_POLICY_VERSION
    assert set(MUTATION_RECONCILIATION_POLICIES) == set(mutations)


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_agent_context_read_binds_subject_actor_and_run_snapshot(
    workspace, gateway_project, gateway_issue, create_user
):
    actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Context gateway worker",
        created_by=create_user,
    )
    create_memory(actor, key="private-fact", content="Private worker fact.")
    create_user_preference(actor, subject_user=create_user, key="user-style", content="Short report.")
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Read the bound context.",
        context_refs=[f"context:user-{create_user.id}"],
    )
    assignment = create_assignment(
        actor,
        project=gateway_project,
        target_ref=f"issue:{gateway_issue.id}",
        objective="Read context through the gateway.",
        acceptance_criteria=["The projection is bounded and subject-bound."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:g4-context-run", created_by=create_user)
    request = SimpleNamespace(
        user=actor.principal,
        META={},
        agent_actor_ref=run.snapshot["actorRef"],
        agent_workspace_ref=run.snapshot["workspaceRef"],
        agent_run_ref=run.snapshot["runId"],
    )
    raw = {
        "schema_version": "plane.operation/v1",
        "operation_id": "agent.context.read",
        "workspace_slug": workspace.slug,
        "idempotency_key": "idempotency:g4-context-read",
        "correlation_id": "correlation:g4-context-read",
        "input": {"subject_user_ref": f"user:{create_user.id}"},
    }

    response, response_status = OperationGateway().execute(request, raw)

    assert response_status == 200, response
    context = response["result"]["context"]
    assert "private-fact" in context["memoryMarkdown"]
    assert "user-style" in context["userMarkdown"]
    assert len(context["projectionDigest"]) == 64
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="idempotency:g4-context-read").values_list(
            "phase", "outcome"
        )
    ) == [("intent", "intent"), ("outcome", "success")]

    other_actor = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Other context gateway worker",
        created_by=create_user,
    )
    request.agent_actor_ref = f"actor:{other_actor.id}"
    denied, denied_status = OperationGateway().execute(
        request,
        {
            **raw,
            "idempotency_key": "idempotency:g4-context-substitution",
            "correlation_id": "correlation:g4-context-substitution",
        },
    )
    assert denied_status == 403
    assert denied["error"]["code"] == "NOT_AUTHORIZED"
    assert OperationGatewayIdempotency.objects.get(
        idempotency_key="idempotency:g4-context-substitution"
    ).state == OperationGatewayIdempotency.State.DENIED

    other_user = User.objects.create(username="context-other", email="context-other@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=15)
    request.agent_actor_ref = run.snapshot["actorRef"]
    denied_subject, denied_subject_status = OperationGateway().execute(
        request,
        {
            **raw,
            "idempotency_key": "idempotency:g4-context-subject",
            "correlation_id": "correlation:g4-context-subject",
            "input": {"subject_user_ref": f"user:{other_user.id}"},
        },
    )
    assert denied_subject_status == 403
    assert denied_subject["error"]["code"] == "NOT_AUTHORIZED"


@pytest.mark.contract
def test_new_mutation_without_reconciliation_policy_fails_closed():
    with pytest.raises(ValueError, match="explicit reconciliation policy"):
        OperationDescriptor(
            operation_id="future.mutation",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            result_key="result",
        )


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_changed_authorization_between_intent_and_dispatch_has_no_effect_or_quota_leak(
    api_key_client, workspace, gateway_project, gateway_issue
):
    payload = {
        "schema_version": "plane.operation/v1",
        "operation_id": "work_item.rename",
        "workspace_slug": workspace.slug,
        "idempotency_key": "g4-auth-race",
        "correlation_id": "g4-auth-race-correlation",
        "input": {
            "project_id": str(gateway_project.id),
            "issue_id": str(gateway_issue.id),
            "name": "Must Not Commit",
        },
    }
    with patch.object(OperationGateway, "_authorize", return_value=GatewayFailure("NOT_AUTHORIZED", 403, False)):
        response = api_key_client.post("/api/v1/operations/", payload, format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHORIZED"
    gateway_issue.refresh_from_db()
    assert gateway_issue.name == "Gateway Issue"
    record = OperationGatewayIdempotency.objects.get(idempotency_key="g4-auth-race")
    assert record.state == OperationGatewayIdempotency.State.DENIED
    assert record.quota_reserved is False
    assert OperationGatewayQuotaBucket.objects.filter(workspace_id=workspace.id, active_count__gt=0).count() == 0
    assert list(
        OperationGatewayAudit.objects.filter(idempotency_key="g4-auth-race")
        .order_by("created_at", "id")
        .values_list("phase", "outcome", "error_code")
    ) == [("intent", "intent", None), ("outcome", "denied", "NOT_AUTHORIZED")]


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_quota_reservation_allows_bounded_overlap_and_rejects_next(workspace):
    def identity_for(index: int):
        return build_quota_identity(
            workspace_id=workspace.id,
            caller_id="quota-user",
            agent_ref=f"agent-actor:g4-quota-agent-{index}",
            invocation_ref="invocation:g4-quota-invocation",
        )

    limit = QUOTA_MAX_INVOCATION_ACTIVE
    identity = identity_for(0)
    agent_keys = {identity_for(index).agent_key for index in range(limit + 1)}
    ready = threading.Event()
    release = threading.Event()
    ready_count = 0
    ready_lock = threading.Lock()
    idempotency_prefix = "g4-quota-overlap-"

    def release_record(record_id):
        if record_id is None:
            return
        with transaction.atomic():
            record = OperationGatewayIdempotency.objects.select_for_update().filter(pk=record_id).first()
            if record is not None and record.quota_reserved:
                release_gateway_quota(record)

    def reserve_one(index: int, *, hold: bool):
        nonlocal ready_count
        close_old_connections()
        record_id = None
        released = False
        try:
            with transaction.atomic():
                record = OperationGatewayIdempotency.objects.create(
                    request_id=uuid.uuid4(),
                    invocation_id=uuid.uuid4(),
                    operation_id="catalog.search",
                    workspace_id=workspace.id,
                    workspace_slug=workspace.slug,
                    caller_id=workspace.owner_id,
                    idempotency_key=f"{idempotency_prefix}{index}",
                    correlation_id=f"{idempotency_prefix}{index}",
                    request_digest=f"{index:064x}",
                    state=OperationGatewayIdempotency.State.RUNNING,
                    request_input={},
                )
                record_id = record.pk
                try:
                    reservation = reserve_gateway_quota(identity_for(index))
                except GatewayQuotaExceeded as exc:
                    record.delete()
                    record_id = None
                    return exc.scope
                record.quota_bucket_start = reservation.bucket_start
                record.quota_agent_key = reservation.agent_key
                record.quota_invocation_key = reservation.invocation_key
                record.quota_reserved = True
                record.save(
                    update_fields=[
                        "quota_bucket_start",
                        "quota_agent_key",
                        "quota_invocation_key",
                        "quota_reserved",
                        "updated_at",
                    ]
                )
            if hold:
                with ready_lock:
                    ready_count += 1
                    if ready_count == limit:
                        ready.set()
                if not release.wait(timeout=10):
                    raise AssertionError("quota overlap workers did not receive release")
            release_record(record_id)
            released = True
            return "accepted"
        finally:
            if record_id is not None and not released:
                release_record(record_id)
            close_old_connections()

    accepted_futures = []
    try:
        with ThreadPoolExecutor(max_workers=limit + 1) as executor:
            accepted_futures = [executor.submit(reserve_one, index, hold=True) for index in range(limit)]
            assert ready.wait(timeout=10)
            bucket = OperationGatewayQuotaBucket.objects.get(
                workspace_id=workspace.id,
                scope="invocation",
                subject_key=identity.invocation_key,
                bucket_start=_bucket_start(timezone.now()),
            )
            assert bucket.active_count == limit

            contender = executor.submit(reserve_one, limit, hold=False)
            assert contender.result(timeout=10) == "invocation"
            release.set()
            assert [future.result(timeout=10) for future in accepted_futures] == ["accepted"] * limit
    finally:
        release.set()
        for future in accepted_futures:
            if future.done() and not future.cancelled():
                future.result()

    records = OperationGatewayIdempotency.objects.filter(
        workspace_id=workspace.id,
        idempotency_key__startswith=idempotency_prefix,
    )
    assert records.count() == limit
    assert records.filter(quota_reserved=True).count() == 0
    bucket_filter = {
        "workspace_id": workspace.id,
        "bucket_start": _bucket_start(timezone.now()),
        "subject_key__in": (identity.workspace_id, identity.invocation_key, *agent_keys),
    }
    assert not OperationGatewayQuotaBucket.objects.filter(**bucket_filter, active_count__gt=0).exists()
    workspace_bucket = OperationGatewayQuotaBucket.objects.get(
        **bucket_filter,
        scope="workspace",
    )
    assert workspace_bucket.active_count == 0
    assert workspace_bucket.request_count == limit
    invocation_bucket = OperationGatewayQuotaBucket.objects.get(
        **bucket_filter,
        scope="invocation",
    )
    assert invocation_bucket.active_count == 0
    assert invocation_bucket.request_count == limit
    agent_buckets = OperationGatewayQuotaBucket.objects.filter(
        **bucket_filter,
        scope="agent",
    )
    assert agent_buckets.count() == limit
    assert set(agent_buckets.values_list("active_count", flat=True)) == {0}
    assert set(agent_buckets.values_list("request_count", flat=True)) == {1}
    OperationGatewayIdempotency.objects.filter(
        workspace_id=workspace.id,
        idempotency_key__startswith=idempotency_prefix,
    ).delete()
    OperationGatewayQuotaBucket.objects.filter(
        **bucket_filter,
    ).delete()


@pytest.mark.contract
def test_quota_identity_hashes_full_bounded_references_and_rejects_unbounded_values(workspace):
    prefix = "x" * 128
    first = build_quota_identity(
        workspace_id=workspace.id,
        caller_id="quota-user",
        agent_ref=f"{prefix}a",
        invocation_ref="invocation:first",
    )
    second = build_quota_identity(
        workspace_id=workspace.id,
        caller_id="quota-user",
        agent_ref=f"{prefix}b",
        invocation_ref="invocation:first",
    )

    assert first.agent_key != second.agent_key
    assert prefix not in first.agent_key
    with pytest.raises(ValueError, match="exceeds"):
        build_quota_identity(
            workspace_id=workspace.id,
            caller_id="quota-user",
            agent_ref="a" * (MAX_QUOTA_IDENTITY_LENGTH + 1),
            invocation_ref="invocation:first",
        )


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_quota_cleanup_is_bounded_idempotent_and_concurrency_safe(workspace):
    now = timezone.now()
    current = _bucket_start(now)
    cutoff = _bucket_start(now - timedelta(hours=24))
    expired = cutoff - timedelta(minutes=1)
    subjects = {
        "expired": "expired-subject",
        "cutoff": "cutoff-subject",
        "current": "current-subject",
        "active": "active-subject",
        "reserved": "reserved-subject",
    }
    for subject_key, bucket_start, active_count in (
        (subjects["expired"], expired, 0),
        (subjects["cutoff"], cutoff, 0),
        (subjects["current"], current, 0),
        (subjects["active"], expired, 1),
        (subjects["reserved"], expired, 0),
    ):
        OperationGatewayQuotaBucket.objects.create(
            workspace_id=workspace.id,
            scope="invocation",
            subject_key=subject_key,
            bucket_start=bucket_start,
            active_count=active_count,
            request_count=active_count,
        )

    active_idempotency = OperationGatewayIdempotency.objects.create(
        invocation_id=uuid.uuid4(),
        operation_id="catalog.search",
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        caller_id=workspace.owner_id,
        idempotency_key="cleanup-active-reservation",
        correlation_id="cleanup-active-reservation",
        request_digest="a" * 64,
        state=OperationGatewayIdempotency.State.RUNNING,
        request_input={},
        quota_bucket_start=expired,
        quota_invocation_key=subjects["reserved"],
        quota_reserved=True,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        deleted = list(
            executor.map(
                lambda _: cleanup_gateway_quota(now=now, retention=timedelta(hours=24), batch_size=20),
                range(2),
            )
        )

    assert sum(deleted) == 1
    assert cleanup_gateway_quota(now=now, retention=timedelta(hours=24), batch_size=20) == 0
    assert (
        OperationGatewayQuotaBucket.objects.filter(
            workspace_id=workspace.id,
            subject_key__in=[subjects["cutoff"], subjects["current"], subjects["active"], subjects["reserved"]],
        ).count()
        == 4
    )
    assert OperationGatewayIdempotency.objects.filter(pk=active_idempotency.pk, quota_reserved=True).exists()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_postgresql_gateway_workload_measures_real_quota_and_audit_evidence():
    result = run_gateway_workload(requests=128, workers=8, agent_count=16)
    if os.environ.get("PLANE_G4_LOAD_JSON") == "1":
        print(json.dumps({"event": "agent.g4.gateway.load", **result}, sort_keys=True))

    assert result["manifestVersion"] == "plane-operation-gateway-load/v3"
    assert result["actualGateway"] is True
    assert result["simulation"] is False
    assert result["configuredAgentIdentities"] == 16
    assert result["measuredAgentIdentities"] == 16
    evidence = json.dumps(result, sort_keys=True)
    assert result["throughputPerSecond"] >= result["thresholds"]["minimumThroughputPerSecond"], evidence
    assert result["latencyMs"]["p95"] <= result["thresholds"]["maximumP95LatencyMs"], evidence
    assert result["latencyMs"]["p99"] <= result["thresholds"]["maximumP99LatencyMs"], evidence
    assert result["errors"] == 0
    assert result["errorRate"] == 0
    assert result["saturation"] >= result["thresholds"]["minimumSaturationRate"], evidence
    assert result["queueingMs"]["p95"] <= result["thresholds"]["maximumQueueingP95Ms"], evidence
    assert result["resources"]["maxDatabaseConnections"] <= result["thresholds"]["maximumDatabaseConnections"], evidence
    assert result["resources"]["maxResidentSetMb"] <= result["thresholds"]["maximumResidentSetMb"], evidence
    assert result["resources"]["cpuSeconds"] <= result["thresholds"]["maximumCpuSeconds"], evidence
    assert result["sustainedDurationSeconds"] >= result["thresholds"]["minimumSustainedDurationSeconds"], evidence
    assert result["correlationCoverage"] == 1
    assert result["auditCoverage"] == 1
    assert result["correlationAuditCoverage"] == 1
    assert result["duplicateEffects"] == 0
    assert result["duplicateCommittedEffects"] == 1
    assert result["duplicateIdempotencyRows"] == 1
    assert result["productionLimits"]["invocationRequests"] == 64
    assert result["productionLimits"]["invocationActive"] == QUOTA_MAX_INVOCATION_ACTIVE
    assert result["throttled"] > 0
    assert result["passes"] is True, evidence

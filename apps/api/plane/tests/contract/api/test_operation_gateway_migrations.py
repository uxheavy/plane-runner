import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


BASE_MIGRATION = ("db", "0123_operationgatewayaudit_operationgatewayidempotency")
PRE_HEAD_MIGRATION = ("db", "0125_operationgateway_publications_and_audit_trigger")
HEAD_MIGRATION = ("db", "0126_operationgateway_delivery_and_audit_roles")


def _migrate_and_reload(target):
    """Migrate, then rebuild both executor and historical app registry."""

    executor = MigrationExecutor(connection)
    executor.migrate([target])
    executor = MigrationExecutor(connection)
    return executor, executor.loader.project_state([target]).apps


def _audit_kwargs(*, request_id, operation_id, workspace_slug, caller_id, key, correlation, digest):
    return {
        "request_id": request_id,
        "operation_id": operation_id,
        "workspace_slug": workspace_slug,
        "caller_id": caller_id,
        "idempotency_key": key,
        "correlation_id": correlation,
        "request_digest": digest,
    }


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_historical_invocation_backfill_is_deterministic_across_directions():
    _, old_apps = _migrate_and_reload(BASE_MIGRATION)
    User = old_apps.get_model("db", "User")
    Workspace = old_apps.get_model("db", "Workspace")
    Idempotency = old_apps.get_model("db", "OperationGatewayIdempotency")
    Audit = old_apps.get_model("db", "OperationGatewayAudit")

    caller_a = User.objects.create(email="migration-gateway-a@plane.so", username="migration-gateway-a")
    caller_b = User.objects.create(email="migration-gateway-b@plane.so", username="migration-gateway-b")
    workspace_a = Workspace.objects.create(
        name="Migration Gateway A",
        slug="migration-gateway-a",
        owner=caller_a,
    )
    workspace_b = Workspace.objects.create(
        name="Migration Gateway B",
        slug="migration-gateway-b",
        owner=caller_b,
    )

    shared_request_id = uuid.uuid4()
    records = []
    identities = [
        (workspace_a, caller_a, "migration-a", "corr-a", "a" * 64),
        (workspace_b, caller_b, "migration-b", "corr-b", "b" * 64),
    ]
    for index, (workspace, caller, key, correlation, digest) in enumerate(identities):
        records.append(
            Idempotency.objects.create(
                request_id=shared_request_id,
                operation_id="work_item.rename",
                workspace_slug=workspace.slug,
                caller_id=caller.pk,
                idempotency_key=key,
                correlation_id=correlation,
                request_digest=digest,
                state="succeeded",
                result={"work_item": {"name": f"Name {index}"}},
            )
        )
        common = _audit_kwargs(
            request_id=shared_request_id,
            operation_id="work_item.rename",
            workspace_slug=workspace.slug,
            caller_id=caller.pk,
            key=key,
            correlation=correlation,
            digest=digest,
        )
        Audit.objects.create(phase="intent", outcome="intent", **common)
        Audit.objects.create(
            phase="outcome",
            outcome="success",
            result={"work_item": {"name": f"Name {index}"}},
            **common,
        )

    # Same request_id, but no full identity match: it must not be linked to
    # either record. The second row exercises a collision-shaped unmatched
    # case and must get a distinct deterministic UUID as well.
    unmatched = Audit.objects.create(
        phase="outcome",
        outcome="failure",
        **_audit_kwargs(
            request_id=shared_request_id,
            operation_id="work_item.rename",
            workspace_slug=workspace_a.slug,
            caller_id=caller_a.pk,
            key="unmatched",
            correlation="unmatched",
            digest="f" * 64,
        ),
    )
    collision_shaped = Audit.objects.create(
        phase="outcome",
        outcome="failure",
        **_audit_kwargs(
            request_id=shared_request_id,
            operation_id="work_item.rename",
            workspace_slug=workspace_b.slug,
            caller_id=caller_b.pk,
            key="collision",
            correlation="collision",
            digest="e" * 64,
        ),
    )

    _, pre_head_apps = _migrate_and_reload(PRE_HEAD_MIGRATION)
    PreIdempotency = pre_head_apps.get_model("db", "OperationGatewayIdempotency")
    PrePublication = pre_head_apps.get_model("db", "OperationGatewayPublication")
    PreWebhook = pre_head_apps.get_model("db", "Webhook")
    legacy_record = PreIdempotency.objects.get(pk=records[0].pk)
    webhook_one = PreWebhook.objects.create(
        workspace_id=workspace_a.pk,
        url="https://migration-webhook-one.example.com",
        is_active=True,
        issue=True,
        created_by_id=caller_a.pk,
    )
    webhook_two = PreWebhook.objects.create(
        workspace_id=workspace_a.pk,
        url="https://migration-webhook-two.example.com",
        is_active=True,
        issue=True,
        created_by_id=caller_a.pk,
    )
    PrePublication.objects.create(
        idempotency_id=legacy_record.pk,
        invocation_id=legacy_record.invocation_id,
        kind="webhook",
        publication_key=f"{legacy_record.pk}:webhook",
        payload={"slug": workspace_a.slug},
        state="succeeded",
        attempts=1,
    )

    _, head_apps = _migrate_and_reload(HEAD_MIGRATION)
    NewIdempotency = head_apps.get_model("db", "OperationGatewayIdempotency")
    NewAudit = head_apps.get_model("db", "OperationGatewayAudit")
    NewPublication = head_apps.get_model("db", "OperationGatewayPublication")
    first_ids = dict(NewIdempotency.objects.values_list("id", "invocation_id"))
    assert len(first_ids) == len(set(first_ids.values())) == len(records)

    for record in NewIdempotency.objects.all():
        linked = NewAudit.objects.filter(
            request_id=record.request_id,
            operation_id=record.operation_id,
            workspace_slug=record.workspace_slug,
            caller_id=record.caller_id,
            idempotency_key=record.idempotency_key,
            correlation_id=record.correlation_id,
            request_digest=record.request_digest,
        )
        assert linked.exists()
        assert set(linked.values_list("invocation_id", flat=True)) == {record.invocation_id}

    unmatched_id = NewAudit.objects.get(id=unmatched.pk).invocation_id
    collision_id = NewAudit.objects.get(id=collision_shaped.pk).invocation_id
    assert unmatched_id not in set(first_ids.values())
    assert collision_id not in set(first_ids.values())
    assert unmatched_id != collision_id
    legacy_publications = list(
        NewPublication.objects.filter(idempotency_id=legacy_record.pk, kind="webhook").order_by("target_id")
    )
    assert {publication.target_id for publication in legacy_publications} == {webhook_one.pk, webhook_two.pk}
    assert all(publication.state == "outcome_unknown" for publication in legacy_publications)
    assert all(publication.payload["webhook_id"] for publication in legacy_publications)
    assert set(MigrationExecutor(connection).loader.graph.leaf_nodes("db")) == {HEAD_MIGRATION}

    # Exercise every 0126 publication state, including the states that 0125
    # cannot name. The reverse marker must preserve all durable identity and
    # dispatch facts, while the visible 0125 row must remain non-runnable when
    # any target has ambiguous or already-started delivery history.
    roundtrip_record = NewIdempotency.objects.get(pk=records[1].pk)
    now = timezone.now()
    state_rows = [
        ("pending", False, None, None),
        ("running", False, None, now),
        ("succeeded", True, {"state": "succeeded", "receipt": "known"}, None),
        ("failed", False, {"state": "failed"}, None),
        ("retryable", False, {"state": "retryable"}, None),
        ("outcome_unknown", True, {"state": "outcome_unknown"}, None),
    ]
    for index, (state, dispatch_started, delivery_result, lease_until) in enumerate(state_rows):
        NewPublication.objects.create(
            id=uuid.uuid4(),
            idempotency=roundtrip_record,
            invocation_id=roundtrip_record.invocation_id,
            kind="webhook",
            target_id=uuid.uuid4(),
            publication_key=f"roundtrip:{index}",
            payload={"webhook_id": f"target-{index}", "index": index},
            state=state,
            attempts=index,
            last_error=f"error-{index}",
            delivery_result=delivery_result,
            dispatch_started=dispatch_started,
            lease_until=lease_until,
            published_at=now if state == "succeeded" else None,
        )

    def publication_snapshot(model, record_id):
        return [
            (
                str(row.id),
                str(row.idempotency_id),
                str(row.invocation_id),
                str(row.target_id),
                row.publication_key,
                row.payload,
                row.state,
                row.attempts,
                row.last_error,
                row.delivery_result,
                row.dispatch_started,
                row.lease_until.isoformat() if row.lease_until else None,
                row.published_at.isoformat() if row.published_at else None,
            )
            for row in model.objects.filter(idempotency_id=record_id, kind="webhook").order_by("id")
        ]

    before_roundtrip = publication_snapshot(NewPublication, roundtrip_record.pk)
    _, reverse_apps = _migrate_and_reload(PRE_HEAD_MIGRATION)
    ReversePublication = reverse_apps.get_model("db", "OperationGatewayPublication")
    reverse_row = ReversePublication.objects.get(idempotency_id=roundtrip_record.pk, kind="webhook")
    assert reverse_row.state == "failed"
    assert reverse_row.payload["__plane_0126_reverse__"]["version"] == 1
    assert len(reverse_row.payload["__plane_0126_reverse__"]["rows"]) == len(state_rows)
    _, roundtrip_apps = _migrate_and_reload(HEAD_MIGRATION)
    RoundtripPublication = roundtrip_apps.get_model("db", "OperationGatewayPublication")
    assert publication_snapshot(RoundtripPublication, roundtrip_record.pk) == before_roundtrip
    assert set(MigrationExecutor(connection).loader.graph.leaf_nodes("db")) == {HEAD_MIGRATION}

    _, base_again_apps = _migrate_and_reload(BASE_MIGRATION)
    # Recreating the historical registry after the backward direction proves
    # the test is not querying stale model state.
    assert base_again_apps.get_model("db", "OperationGatewayAudit")
    _, head_again_apps = _migrate_and_reload(HEAD_MIGRATION)
    AgainIdempotency = head_again_apps.get_model("db", "OperationGatewayIdempotency")
    AgainAudit = head_again_apps.get_model("db", "OperationGatewayAudit")
    second_ids = dict(AgainIdempotency.objects.values_list("id", "invocation_id"))
    assert second_ids == first_ids
    assert AgainAudit.objects.get(id=unmatched.pk).invocation_id == unmatched_id
    assert AgainAudit.objects.get(id=collision_shaped.pk).invocation_id == collision_id
    assert set(MigrationExecutor(connection).loader.graph.leaf_nodes("db")) == {HEAD_MIGRATION}

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


BASE_MIGRATION = ("db", "0123_operationgatewayaudit_operationgatewayidempotency")
HEAD_MIGRATION = ("db", "0125_operationgateway_publications_and_audit_trigger")


def _state_apps(executor, target):
    return executor.loader.project_state([target]).apps


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_historical_invocation_backfill_is_unique_linked_and_repeatable():
    executor = MigrationExecutor(connection)
    executor.migrate([BASE_MIGRATION])
    old_apps = _state_apps(executor, BASE_MIGRATION)
    User = old_apps.get_model("db", "User")
    Workspace = old_apps.get_model("db", "Workspace")
    Idempotency = old_apps.get_model("db", "OperationGatewayIdempotency")
    Audit = old_apps.get_model("db", "OperationGatewayAudit")

    caller = User.objects.create(email="migration-gateway@plane.so", username="migration-gateway")
    workspace = Workspace.objects.create(
        name="Migration Gateway Workspace",
        slug="migration-gateway",
        owner=caller,
    )

    request_ids = [uuid.uuid4(), uuid.uuid4()]
    idempotencies = []
    for index, request_id in enumerate(request_ids):
        idempotencies.append(
            Idempotency.objects.create(
                request_id=request_id,
                operation_id="work_item.rename",
                workspace_slug=workspace.slug,
                caller_id=caller.pk,
                idempotency_key=f"migration-{index}",
                correlation_id=f"migration-correlation-{index}",
                request_digest=f"{index}" * 64,
                state="succeeded",
                result={"work_item": {"name": f"Name {index}"}},
            )
        )
        for phase, outcome in (("intent", "intent"), ("outcome", "success")):
            Audit.objects.create(
                phase=phase,
                outcome=outcome,
                request_id=request_id,
                operation_id="work_item.rename",
                workspace_slug=workspace.slug,
                caller_id=caller.pk,
                idempotency_key=f"migration-{index}",
                correlation_id=f"migration-correlation-{index}",
                request_digest=f"{index}" * 64,
                result={"work_item": {"name": f"Name {index}"}} if outcome == "success" else None,
            )

    unmatched = Audit.objects.create(
        phase="outcome",
        outcome="failure",
        request_id=request_ids[0],
        operation_id="work_item.rename",
        workspace_slug=workspace.slug,
        caller_id=caller.pk,
        idempotency_key="unmatched-audit",
        correlation_id="unmatched-correlation",
        request_digest="f" * 64,
    )

    executor.migrate([HEAD_MIGRATION])
    new_apps = _state_apps(executor, HEAD_MIGRATION)
    NewIdempotency = new_apps.get_model("db", "OperationGatewayIdempotency")
    NewAudit = new_apps.get_model("db", "OperationGatewayAudit")
    migrated_ids = list(NewIdempotency.objects.values_list("invocation_id", flat=True))
    assert len(migrated_ids) == len(set(migrated_ids)) == len(idempotencies)
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
    assert unmatched_id not in set(migrated_ids)
    first_unmatched_id = unmatched_id

    first_pass = dict(NewIdempotency.objects.values_list("id", "invocation_id"))
    executor.migrate([BASE_MIGRATION])
    executor.migrate([HEAD_MIGRATION])
    NewIdempotency = _state_apps(executor, HEAD_MIGRATION).get_model("db", "OperationGatewayIdempotency")
    NewAudit = _state_apps(executor, HEAD_MIGRATION).get_model("db", "OperationGatewayAudit")
    second_pass = dict(NewIdempotency.objects.values_list("id", "invocation_id"))
    assert second_pass == first_pass
    assert NewAudit.objects.get(id=unmatched.pk).invocation_id == first_unmatched_id

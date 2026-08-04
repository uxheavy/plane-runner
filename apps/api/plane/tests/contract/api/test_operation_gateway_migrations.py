import uuid
from datetime import timedelta

import pytest
from django.conf import settings
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


def _safe_catalog_snapshot():
    """Capture the 0125 audit catalog contract, excluding PUBLIC entries."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_owner.rolname, function_owner.rolname,
                   schema_owner.rolname, audit_function.prosecdef,
                   audit_function.proconfig
            FROM pg_class AS audit_table
            JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_table.relnamespace
            JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner
            JOIN pg_proc AS audit_function
              ON audit_function.oid = to_regprocedure('operation_gateway_audit_append_only()')
            JOIN pg_roles AS function_owner ON function_owner.oid = audit_function.proowner
            JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
            WHERE audit_schema.nspname = current_schema()
              AND audit_table.relname = 'operation_gateway_audit'
            """
        )
        owners = cursor.fetchone()

        def acl(query):
            cursor.execute(query)
            return tuple(cursor.fetchall())

        table_acl = acl(
            """
            SELECT grantor.rolname, grantee.rolname, exploded.privilege_type,
                   exploded.is_grantable
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN LATERAL aclexplode(
                COALESCE(object_info.relacl, acldefault('r', object_info.relowner))
            ) AS exploded ON exploded.grantee <> 0
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = current_schema()
              AND object_info.relname = 'operation_gateway_audit'
            ORDER BY 1, 2, 3, 4
            """
        )
        function_acl = acl(
            """
            SELECT grantor.rolname, grantee.rolname, exploded.privilege_type,
                   exploded.is_grantable
            FROM pg_proc AS object_info
            JOIN LATERAL aclexplode(
                COALESCE(object_info.proacl, acldefault('f', object_info.proowner))
            ) AS exploded ON exploded.grantee <> 0
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_info.oid = to_regprocedure('operation_gateway_audit_append_only()')
            ORDER BY 1, 2, 3, 4
            """
        )
        schema_acl = acl(
            """
            SELECT grantor.rolname, grantee.rolname, exploded.privilege_type,
                   exploded.is_grantable
            FROM pg_namespace AS object_info
            JOIN LATERAL aclexplode(
                COALESCE(object_info.nspacl, acldefault('n', object_info.nspowner))
            ) AS exploded ON exploded.grantee <> 0
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_info.nspname = current_schema()
            ORDER BY 1, 2, 3, 4
            """
        )
        sequence_acl = acl(
            """
            SELECT object_info.relname, object_owner.rolname, grantor.rolname,
                   grantee.rolname, exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
            JOIN LATERAL aclexplode(
                COALESCE(object_info.relacl, acldefault('S', object_info.relowner))
            ) AS exploded ON exploded.grantee <> 0
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = current_schema()
              AND object_info.relkind = 'S'
              AND object_info.relname LIKE 'operation_gateway_audit%'
            ORDER BY 1, 2, 3, 4, 5, 6
            """
        )
        cursor.execute(
            """
            SELECT default_owner.rolname, defaults.defaclnamespace,
                   defaults.defaclobjtype, grantor.rolname, grantee.rolname,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_default_acl AS defaults
            JOIN pg_roles AS default_owner ON default_owner.oid = defaults.defaclrole
            JOIN LATERAL aclexplode(defaults.defaclacl) AS exploded ON exploded.grantee <> 0
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE defaults.defaclobjtype IN ('r', 'S', 'f')
              AND (
                  defaults.defaclnamespace = 0
                  OR defaults.defaclnamespace = (
                      SELECT oid FROM pg_namespace WHERE nspname = current_schema()
                  )
              )
            ORDER BY 1, 2, 3, 4, 5, 6, 7
            """
        )
        default_acl = tuple(cursor.fetchall())
        cursor.execute(
            """
            SELECT role_name.rolname, member_name.rolname, memberships.admin_option
            FROM pg_auth_members AS memberships
            JOIN pg_roles AS role_name ON role_name.oid = memberships.roleid
            JOIN pg_roles AS member_name ON member_name.oid = memberships.member
            WHERE role_name.rolname IN (%s, %s, %s)
               OR member_name.rolname IN (%s, %s, %s)
            ORDER BY 1, 2, 3
            """,
            [
                settings.PLANE_AUDIT_RUNTIME_ROLE,
                settings.PLANE_AUDIT_MIGRATION_ROLE,
                settings.PLANE_AUDIT_GOVERNANCE_ROLE,
                settings.PLANE_AUDIT_RUNTIME_ROLE,
                settings.PLANE_AUDIT_MIGRATION_ROLE,
                settings.PLANE_AUDIT_GOVERNANCE_ROLE,
            ],
        )
        role_grants = tuple(cursor.fetchall())
    return owners, table_acl, function_acl, schema_acl, sequence_acl, default_acl, role_grants


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
    pre_safe_catalog = _safe_catalog_snapshot()

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
        publication = NewPublication.objects.create(
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
        created_at = now - timedelta(days=index + 1)
        updated_at = now - timedelta(hours=index + 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE operation_gateway_publication SET created_at = %s, updated_at = %s WHERE id = %s",
                [created_at, updated_at, publication.id],
            )

    def publication_snapshot(model, record_id):
        return [
            (
                str(row.id),
                str(row.idempotency_id),
                str(row.invocation_id),
                row.kind,
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
                row.created_at.isoformat(),
                row.updated_at.isoformat(),
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
    assert {
        "id",
        "idempotency_id",
        "invocation_id",
        "kind",
        "target_id",
        "publication_key",
        "payload",
        "state",
        "attempts",
        "last_error",
        "delivery_result",
        "dispatch_started",
        "lease_until",
        "published_at",
        "created_at",
        "updated_at",
    } <= set(reverse_row.payload["__plane_0126_reverse__"]["rows"][0])
    assert _safe_catalog_snapshot() == pre_safe_catalog
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_namespace AS schema_info
                JOIN LATERAL aclexplode(
                    COALESCE(schema_info.nspacl, acldefault('n', schema_info.nspowner))
                ) AS exploded ON exploded.grantee = 0
                WHERE schema_info.nspname = current_schema()
                  AND exploded.privilege_type IN ('CREATE', 'USAGE')
            ),
            has_schema_privilege('public', current_schema(), 'CREATE'),
            has_schema_privilege('public', current_schema(), 'USAGE')
            """
        )
        public_acl, public_can_create, public_can_use = cursor.fetchone()
    assert public_acl is False
    assert public_can_create is False
    assert public_can_use is False
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

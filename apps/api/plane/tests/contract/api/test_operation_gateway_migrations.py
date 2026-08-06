import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


BASE_MIGRATION = ("db", "0126_operationgatewayaudit_operationgatewayidempotency")
PRE_HEAD_MIGRATION = ("db", "0128_operationgateway_publications_and_audit_trigger")
HEAD_MIGRATION = ("db", "0137_runtime_supervisor_state")
COMBINED_MIGRATION_CHAIN = (
    (
        ("db", "0123_agent_lifecycle_foundation"),
        ("db", "0122_alter_draftissue_assignees_alter_issue_assignees_and_more"),
    ),
    (("db", "0124_agent_lifecycle_database_integrity"), ("db", "0123_agent_lifecycle_foundation")),
    (("db", "0125_agent_lifecycle_append_only_integrity"), ("db", "0124_agent_lifecycle_database_integrity")),
    (
        ("db", "0126_operationgatewayaudit_operationgatewayidempotency"),
        ("db", "0125_agent_lifecycle_append_only_integrity"),
    ),
    (("db", "0127_operationgateway_hardening"), ("db", "0126_operationgatewayaudit_operationgatewayidempotency")),
    (
        ("db", "0128_operationgateway_publications_and_audit_trigger"),
        ("db", "0127_operationgateway_hardening"),
    ),
    (
        ("db", "0129_operationgateway_delivery_and_audit_roles"),
        ("db", "0128_operationgateway_publications_and_audit_trigger"),
    ),
    (("db", "0130_agent_runtime_ingress_evidence"), ("db", "0129_operationgateway_delivery_and_audit_roles")),
    (
        ("db", "0131_agentmemoryentry_agentmemoryrevision_agentschedule_and_more"),
        ("db", "0130_agent_runtime_ingress_evidence"),
    ),
    (
        ("db", "0132_governed_context_scope_and_rollback_guards"),
        ("db", "0131_agentmemoryentry_agentmemoryrevision_agentschedule_and_more"),
    ),
    (("db", "0133_run_pending_input_reference"), ("db", "0132_governed_context_scope_and_rollback_guards")),
    (("db", "0134_agent_input_event_sequence"), ("db", "0133_run_pending_input_reference")),
    (("db", "0135_agent_input_durability"), ("db", "0134_agent_input_event_sequence")),
    (("db", "0136_agent_principal_and_code_mode_reservations"), ("db", "0135_agent_input_durability")),
    (("db", "0137_runtime_supervisor_state"), ("db", "0136_agent_principal_and_code_mode_reservations")),
)


@pytest.mark.contract
@pytest.mark.django_db
def test_combined_agent_migration_chain_has_one_linear_leaf():
    graph = MigrationExecutor(connection).loader.graph

    assert set(graph.leaf_nodes("db")) == {HEAD_MIGRATION}
    assert all(node in graph.node_map and dependency in graph.node_map for node, dependency in COMBINED_MIGRATION_CHAIN)
    for node, dependency in COMBINED_MIGRATION_CHAIN:
        assert graph.node_map[node].parents == {dependency}

    assert not any(
        node[1]
        in {
            "0123_operationgatewayaudit_operationgatewayidempotency",
            "0124_operationgateway_hardening",
            "0125_operationgateway_publications_and_audit_trigger",
            "0126_operationgateway_delivery_and_audit_roles",
        }
        for node in graph.node_map
    )


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
    """Capture the complete safe 0128 catalog, including PUBLIC entries."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT object_kind, object_name, object_owner
            FROM (
                SELECT 'table' AS object_kind, object_info.relname AS object_name,
                       object_owner.rolname AS object_owner
                FROM pg_class AS object_info
                JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
                JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
                WHERE object_schema.nspname = current_schema()
                  AND object_info.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                UNION ALL
                SELECT 'function', object_info.proname || '(' ||
                       pg_get_function_identity_arguments(object_info.oid) || ')',
                       function_owner.rolname
                FROM pg_proc AS object_info
                JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
                JOIN pg_roles AS function_owner ON function_owner.oid = object_info.proowner
                WHERE object_schema.nspname = current_schema()
                UNION ALL
                SELECT 'schema', current_schema(), schema_owner.rolname
                FROM pg_namespace AS object_schema
                JOIN pg_roles AS schema_owner ON schema_owner.oid = object_schema.nspowner
                WHERE object_schema.nspname = current_schema()
            ) AS all_owners
            ORDER BY 1, 2, 3
            """
        )
        owners = tuple(cursor.fetchall())

        def acl(query):
            cursor.execute(query)
            return tuple(cursor.fetchall())

        table_acl = acl(
            """
            SELECT object_info.relkind, object_info.relname, grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN LATERAL aclexplode(
                COALESCE(object_info.relacl, acldefault('r', object_info.relowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = current_schema()
              AND object_info.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
            ORDER BY 1, 2, 3, 4, 5, 6
            """
        )
        function_acl = acl(
            """
            SELECT object_info.proname,
                   pg_get_function_identity_arguments(object_info.oid),
                   grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_proc AS object_info
            JOIN LATERAL aclexplode(
                COALESCE(object_info.proacl, acldefault('f', object_info.proowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
            WHERE object_schema.nspname = current_schema()
            ORDER BY 1, 2, 3, 4, 5, 6
            """
        )
        schema_acl = acl(
            """
            SELECT grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_namespace AS object_info
            JOIN LATERAL aclexplode(
                COALESCE(object_info.nspacl, acldefault('n', object_info.nspowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_info.nspname = current_schema()
            ORDER BY 1, 2, 3, 4
            """
        )
        sequence_acl = acl(
            """
            SELECT object_info.relname, object_owner.rolname, grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
            JOIN LATERAL aclexplode(
                COALESCE(object_info.relacl, acldefault('S', object_info.relowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = current_schema()
              AND object_info.relkind = 'S'
            ORDER BY 1, 2, 3, 4, 5, 6
            """
        )
        cursor.execute(
            """
            SELECT default_owner.rolname, defaults.defaclnamespace,
                   defaults.defaclobjtype, grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_default_acl AS defaults
            JOIN pg_roles AS default_owner ON default_owner.oid = defaults.defaclrole
            JOIN LATERAL aclexplode(defaults.defaclacl) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
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
        cursor.execute(
            """
            SELECT 1
            FROM pg_class AS marker
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker.relnamespace
            WHERE marker_schema.nspname = current_schema()
              AND marker.relname = 'plane_operation_gateway_authority_marker'
              AND marker.relkind = 'r'
            """
        )
        if cursor.fetchone() is None:
            authority_marker = ()
        else:
            cursor.execute(
                """
                SELECT version, database_owner_oid, database_owner_role,
                       schema_name, schema_owner_oid, schema_owner_role
                FROM plane_operation_gateway_authority_marker
                WHERE marker_id = TRUE
                """
            )
            authority_marker = tuple(cursor.fetchone() or ())
    return owners, table_acl, function_acl, schema_acl, sequence_acl, default_acl, role_grants, authority_marker


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_historical_invocation_backfill_is_deterministic_across_directions():
    call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)
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
    with connection.cursor() as cursor:
        cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        cursor.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")
        cursor.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC")
        cursor.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
        cursor.execute(
            f'GRANT USAGE ON SCHEMA public TO "{settings.PLANE_AUDIT_RUNTIME_ROLE}", '
            f'"{settings.PLANE_AUDIT_GOVERNANCE_ROLE}"'
        )
        cursor.execute(f'GRANT SELECT ON TABLE operation_gateway_audit TO "{settings.PLANE_AUDIT_RUNTIME_ROLE}"')
        cursor.execute(
            f'GRANT EXECUTE ON FUNCTION operation_gateway_audit_append_only() TO "{settings.PLANE_AUDIT_RUNTIME_ROLE}"'
        )
        for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{settings.PLANE_AUDIT_MIGRATION_ROLE}" '
                f"IN SCHEMA public REVOKE ALL ON {object_type} FROM PUBLIC"
            )
    call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    pre_safe_catalog = _safe_catalog_snapshot()

    _, head_apps = _migrate_and_reload(HEAD_MIGRATION)
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)
    NewIdempotency = head_apps.get_model("db", "OperationGatewayIdempotency")
    NewAudit = head_apps.get_model("db", "OperationGatewayAudit")
    NewPublication = head_apps.get_model("db", "OperationGatewayPublication")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(
                       array_agg(DISTINCT exploded.privilege_type ORDER BY exploded.privilege_type),
                       ARRAY[]::text[]
                   ),
                   EXISTS (
                       SELECT 1
                       FROM aclexplode(
                           (SELECT relacl FROM pg_class WHERE relname = 'plane_operation_gateway_authority_marker')
                       ) AS public_acl
                       WHERE public_acl.grantee = 0
                   )
            FROM pg_class AS marker
            JOIN LATERAL aclexplode(marker.relacl) AS exploded ON TRUE
            WHERE marker.relname = 'plane_operation_gateway_authority_marker'
              AND exploded.grantee = (SELECT oid FROM pg_roles WHERE rolname = %s)
            """,
            [settings.PLANE_AUDIT_RUNTIME_ROLE],
        )
        assert cursor.fetchone() == (["SELECT"], False)
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

    # Exercise every 0129 publication state, including the states that 0128
    # cannot name. The reverse marker must preserve all durable identity and
    # dispatch facts, while the visible 0128 row must remain non-runnable when
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
    call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)
    # Exercise PostgreSQL's default PUBLIC function privilege after the
    # provisioner has restored the safe 0128 snapshot. The reverse migration
    # must make the recreated trigger function safe at its creation boundary.
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{settings.PLANE_AUDIT_MIGRATION_ROLE}" '
                "IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
            )
        _, reverse_apps = _migrate_and_reload(PRE_HEAD_MIGRATION)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{settings.PLANE_AUDIT_MIGRATION_ROLE}" '
                "IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
            )
    ReversePublication = reverse_apps.get_model("db", "OperationGatewayPublication")
    reverse_row = ReversePublication.objects.get(idempotency_id=roundtrip_record.pk, kind="webhook")
    assert reverse_row.state == "failed"
    assert reverse_row.payload["__plane_0129_reverse__"]["version"] == 1
    assert len(reverse_row.payload["__plane_0129_reverse__"]["rows"]) == len(state_rows)
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
    } <= set(reverse_row.payload["__plane_0129_reverse__"]["rows"][0])
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
    function_regprocedure = f"{settings.PLANE_AUDIT_SCHEMA}.operation_gateway_audit_append_only()"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_function_privilege('public', %s::regprocedure, 'EXECUTE'), "
            "has_function_privilege(%s, %s::regprocedure, 'EXECUTE'), "
            "has_function_privilege(%s, %s::regprocedure, 'EXECUTE'), "
            "has_function_privilege(%s, %s::regprocedure, 'EXECUTE')",
            [
                function_regprocedure,
                settings.PLANE_AUDIT_RUNTIME_ROLE,
                function_regprocedure,
                settings.PLANE_AUDIT_MIGRATION_ROLE,
                function_regprocedure,
                settings.PLANE_AUDIT_GOVERNANCE_ROLE,
                function_regprocedure,
            ],
        )
        final_0128_acl = cursor.fetchone()
    assert final_0128_acl == (False, True, True, False)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM (
                SELECT exploded.privilege_type
                FROM pg_namespace AS object_info
                JOIN LATERAL aclexplode(
                    COALESCE(object_info.nspacl, acldefault('n'::\"char\", object_info.nspowner))
                ) AS exploded ON exploded.grantee = 0
                WHERE object_info.nspname = current_schema()
                UNION ALL
                SELECT exploded.privilege_type
                FROM pg_class AS object_info
                JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
                JOIN LATERAL aclexplode(
                    COALESCE(
                        object_info.relacl,
                        acldefault(
                            CASE WHEN object_info.relkind = 'S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,
                            object_info.relowner
                        )
                    )
                ) AS exploded ON exploded.grantee = 0
                WHERE object_schema.nspname = current_schema()
                  AND object_info.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                UNION ALL
                SELECT exploded.privilege_type
                FROM pg_proc AS object_info
                JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
                JOIN LATERAL aclexplode(
                    COALESCE(object_info.proacl, acldefault('f'::\"char\", object_info.proowner))
                ) AS exploded ON exploded.grantee = 0
                WHERE object_schema.nspname = current_schema()
                UNION ALL
                SELECT exploded.privilege_type
                FROM pg_default_acl AS defaults
                JOIN LATERAL aclexplode(defaults.defaclacl) AS exploded ON exploded.grantee = 0
                WHERE defaults.defaclnamespace = (
                    SELECT oid FROM pg_namespace WHERE nspname = current_schema()
                )
                  AND defaults.defaclobjtype IN ('r', 'S', 'f')
            ) AS public_privileges
            """
        )
        assert cursor.fetchone()[0] == 0
    call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    _, roundtrip_apps = _migrate_and_reload(HEAD_MIGRATION)
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)
    RoundtripPublication = roundtrip_apps.get_model("db", "OperationGatewayPublication")
    assert publication_snapshot(RoundtripPublication, roundtrip_record.pk) == before_roundtrip
    assert set(MigrationExecutor(connection).loader.graph.leaf_nodes("db")) == {HEAD_MIGRATION}

    call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)
    _, base_again_apps = _migrate_and_reload(BASE_MIGRATION)
    # Recreating the historical registry after the backward direction proves
    # the test is not querying stale model state.
    assert base_again_apps.get_model("db", "OperationGatewayAudit")
    call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    _, head_again_apps = _migrate_and_reload(HEAD_MIGRATION)
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)
    AgainIdempotency = head_again_apps.get_model("db", "OperationGatewayIdempotency")
    AgainAudit = head_again_apps.get_model("db", "OperationGatewayAudit")
    second_ids = dict(AgainIdempotency.objects.values_list("id", "invocation_id"))
    assert second_ids == first_ids
    assert AgainAudit.objects.get(id=unmatched.pk).invocation_id == unmatched_id
    assert AgainAudit.objects.get(id=collision_shaped.pk).invocation_id == collision_id
    assert set(MigrationExecutor(connection).loader.graph.leaf_nodes("db")) == {HEAD_MIGRATION}

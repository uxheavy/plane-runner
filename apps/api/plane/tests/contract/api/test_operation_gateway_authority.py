import copy
import json
import uuid

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from plane.db.management.commands.verify_operation_gateway_migration_boundary import _assert_no_protected_membership


def _quote(identifier):
    return connection.ops.quote_name(identifier)


def _connect_as_role(role, password):
    database = connection.settings_dict
    kwargs = {
        "dbname": database["NAME"],
        "user": role,
        "password": password,
        "host": database.get("HOST") or None,
        "port": database.get("PORT") or None,
        "autocommit": True,
    }
    return psycopg.connect(**{key: value for key, value in kwargs.items() if value is not None})


def _require_head_audit_snapshot():
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)
    with connection.cursor() as cursor:
        schema = settings.PLANE_AUDIT_SCHEMA
        cursor.execute(
            "SELECT to_regclass(%s), to_regclass(%s)",
            [
                f"{schema}.plane_0126_audit_catalog_snapshot",
                f"{schema}.plane_0126_audit_catalog_snapshot_binding",
            ],
        )
        if any(value is None for value in cursor.fetchone()):
            pytest.skip("requires the migration-enabled PostgreSQL harness")


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_limited_migration_role_cannot_mutate_or_replace_authority_marker():
    schema = settings.PLANE_AUDIT_SCHEMA
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    marker = f"{_quote(schema)}.{_quote('plane_operation_gateway_authority_marker')}"
    database_name = connection.settings_dict["NAME"]
    migration_probe = f"gateway_migrator_{uuid.uuid4().hex[:12]}"
    migration_password = f"probe_{uuid.uuid4().hex}"
    unrelated_owner = f"gateway_unrelated_owner_{uuid.uuid4().hex[:12]}"

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {_quote(migration_probe)} LOGIN NOINHERIT PASSWORD %s", [migration_password])
            cursor.execute(f"CREATE ROLE {_quote(unrelated_owner)} NOLOGIN NOINHERIT")
            cursor.execute(f"GRANT CONNECT ON DATABASE {_quote(database_name)} TO {_quote(migration_probe)}")
            cursor.execute(f"GRANT USAGE ON SCHEMA {_quote(schema)} TO {_quote(migration_probe)}")
        with override_settings(PLANE_AUDIT_MIGRATION_ROLE=migration_probe):
            call_command("bootstrap_operation_gateway_audit", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT governance.rolcanlogin, governance.rolinherit,
                       marker_owner.rolname,
                       pg_has_role(%s, %s, 'USAGE'),
                       has_table_privilege(%s, %s::regclass, 'SELECT'),
                       has_table_privilege(%s, %s::regclass, 'UPDATE'),
                       has_table_privilege(%s, %s::regclass, 'DELETE'),
                       has_table_privilege(%s, %s::regclass, 'TRUNCATE')
                FROM pg_roles AS governance
                JOIN pg_class AS marker_table ON marker_table.oid = to_regclass(%s)
                JOIN pg_roles AS marker_owner ON marker_owner.oid = marker_table.relowner
                WHERE governance.rolname = %s
                """,
                [
                    migration_probe,
                    governance_role,
                    migration_probe,
                    marker,
                    migration_probe,
                    marker,
                    migration_probe,
                    marker,
                    migration_probe,
                    marker,
                    marker,
                    governance_role,
                ],
            )
            assert cursor.fetchone() == (False, False, governance_role, False, True, False, False, False)
        with _connect_as_role(migration_probe, migration_password) as migrator:
            mutation_statements = (
                f"UPDATE {marker} SET schema_owner_role = 'tampered' WHERE marker_id = TRUE",
                f"INSERT INTO {marker} (marker_id, version, database_owner_oid, database_owner_role, "
                "schema_name, schema_owner_oid, schema_owner_role) "
                "VALUES (FALSE, 1, 0, 'tampered', 'public', 0, 'tampered')",
                f"DELETE FROM {marker}",
                f"TRUNCATE {marker}",
                f"ALTER TABLE {marker} ADD COLUMN tampered integer",
                f"ALTER TABLE {marker} OWNER TO {_quote(unrelated_owner)}",
                f"ALTER TABLE {marker} RENAME TO plane_operation_gateway_authority_marker_replacement",
                f"DROP TABLE {marker}",
                f"CREATE TABLE {marker} (marker_id boolean PRIMARY KEY)",
                f"ALTER DATABASE {_quote(database_name)} OWNER TO {_quote(unrelated_owner)}",
                f"ALTER SCHEMA {_quote(schema)} OWNER TO {_quote(unrelated_owner)}",
            )
            for statement in mutation_statements:
                with pytest.raises(psycopg.Error):
                    migrator.execute(statement)
            with migrator.cursor() as cursor:
                cursor.execute(f"SELECT version, schema_name, schema_owner_role FROM {marker} WHERE marker_id = TRUE")
                assert cursor.fetchone()[0] == 1
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP OWNED BY {_quote(migration_probe)}")
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(migration_probe)}")
            cursor.execute(f"DROP OWNED BY {_quote(unrelated_owner)}")
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(unrelated_owner)}")


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_migration_boundary_rejects_direct_noinherit_governance_membership():
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    migration_probe = f"gateway_membership_probe_{uuid.uuid4().hex[:12]}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {_quote(migration_probe)} LOGIN NOINHERIT PASSWORD 'probe'")
            cursor.execute(f"GRANT {_quote(governance_role)} TO {_quote(migration_probe)}")
            cursor.execute(
                "SELECT pg_has_role(%s, %s, 'USAGE'), EXISTS ("
                "SELECT 1 FROM pg_auth_members membership "
                "JOIN pg_roles granted_role ON granted_role.oid = membership.roleid "
                "JOIN pg_roles member_role ON member_role.oid = membership.member "
                "WHERE granted_role.rolname = %s AND member_role.rolname = %s)",
                [migration_probe, governance_role, governance_role, migration_probe],
            )
            inherited_usage, direct_membership = cursor.fetchone()
            assert inherited_usage is False
            assert direct_membership is True
            with pytest.raises(CommandError, match="governance membership"):
                _assert_no_protected_membership(cursor, migration_probe, governance_role)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP OWNED BY {_quote(migration_probe)}")
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(migration_probe)}")


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_provisioner_owned_authority_marker_residue_converges_on_retry():
    schema = settings.PLANE_AUDIT_SCHEMA
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    marker = f"{_quote(schema)}.{_quote('plane_operation_gateway_authority_marker')}"
    provisioner_probe = f"gateway_provisioner_probe_{uuid.uuid4().hex[:12]}"

    try:
        call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {_quote(provisioner_probe)} NOLOGIN NOINHERIT")
            cursor.execute(f"ALTER TABLE {marker} OWNER TO {_quote(provisioner_probe)}")
        with override_settings(
            PLANE_AUDIT_ENFORCE_ROLE_SEPARATION=False,
            PLANE_AUDIT_PROVISIONER_ROLE=provisioner_probe,
        ):
            call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT owner.rolname FROM pg_class marker "
                "JOIN pg_namespace namespace ON namespace.oid = marker.relnamespace "
                "JOIN pg_roles owner ON owner.oid = marker.relowner "
                "WHERE namespace.nspname = %s AND marker.relname = %s",
                [schema, "plane_operation_gateway_authority_marker"],
            )
            assert cursor.fetchone() == (governance_role,)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {marker} OWNER TO {_quote(governance_role)}")
            cursor.execute(f"DROP OWNED BY {_quote(provisioner_probe)}")
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(provisioner_probe)}")


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_non_superuser_noinherit_migrator_cannot_mutate_catalog_snapshot_binding():
    schema = settings.PLANE_AUDIT_SCHEMA
    snapshot = f"{_quote(schema)}.{_quote('plane_0126_audit_catalog_snapshot')}"
    binding = f"{_quote(schema)}.{_quote('plane_0126_audit_catalog_snapshot_binding')}"
    migration_probe = f"gateway_snapshot_probe_{uuid.uuid4().hex[:12]}"
    migration_password = f"probe_{uuid.uuid4().hex}"

    try:
        _require_head_audit_snapshot()
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE ROLE {_quote(migration_probe)} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                f"NOCREATEROLE NOBYPASSRLS PASSWORD %s",
                [migration_password],
            )
            cursor.execute(
                f"GRANT CONNECT ON DATABASE {_quote(connection.settings_dict['NAME'])} TO {_quote(migration_probe)}"
            )
            cursor.execute(f"GRANT USAGE ON SCHEMA {_quote(schema)} TO {_quote(migration_probe)}")
            cursor.execute(f"GRANT SELECT ON TABLE {snapshot}, {binding} TO {_quote(migration_probe)}")
            cursor.execute(
                "SELECT owner.rolname, binding_owner.rolname "
                "FROM pg_class AS snapshot_info "
                "JOIN pg_namespace AS snapshot_schema ON snapshot_schema.oid = snapshot_info.relnamespace "
                "JOIN pg_roles AS owner ON owner.oid = snapshot_info.relowner "
                "JOIN pg_class AS binding_info ON binding_info.relname = %s "
                "JOIN pg_namespace AS binding_schema ON binding_schema.oid = binding_info.relnamespace "
                "JOIN pg_roles AS binding_owner ON binding_owner.oid = binding_info.relowner "
                "WHERE snapshot_schema.nspname = %s AND snapshot_info.relname = %s "
                "AND binding_schema.nspname = %s",
                [
                    "plane_0126_audit_catalog_snapshot_binding",
                    schema,
                    "plane_0126_audit_catalog_snapshot",
                    schema,
                ],
            )
            snapshot_owner, binding_owner = cursor.fetchone()
            cursor.execute("SELECT current_user")
            current_user = cursor.fetchone()[0]
            expected_owner = settings.PLANE_AUDIT_PROVISIONER_ROLE or current_user
            assert snapshot_owner == binding_owner == expected_owner

        with _connect_as_role(migration_probe, migration_password) as migrator:
            for statement in (
                f"UPDATE {snapshot} SET snapshot = '{{}}'::jsonb WHERE snapshot_id = TRUE",
                f"UPDATE {binding} SET snapshot_digest = repeat('0', 64) WHERE binding_id = TRUE",
                f"INSERT INTO {snapshot} (snapshot_id, snapshot) VALUES (FALSE, '{{}}'::jsonb)",
                f"DELETE FROM {binding}",
                f"TRUNCATE {snapshot}",
                f"ALTER TABLE {binding} ADD COLUMN tampered integer",
                f"ALTER TABLE {snapshot} OWNER TO {_quote(migration_probe)}",
                f"DROP TABLE {binding}",
            ):
                with pytest.raises(psycopg.Error):
                    migrator.execute(statement)

        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {snapshot}")
            assert cursor.fetchone()[0] == 1
            cursor.execute(f"SELECT count(*) FROM {binding}")
            assert cursor.fetchone()[0] == 1
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [migration_probe])
            if cursor.fetchone() is not None:
                cursor.execute(f"DROP OWNED BY {_quote(migration_probe)}")
                cursor.execute(f"DROP ROLE IF EXISTS {_quote(migration_probe)}")


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tamper_kind", ["content", "topology"])
def test_reverse_rejects_snapshot_content_or_topology_tampering_before_catalog_changes(tamper_kind):
    schema = settings.PLANE_AUDIT_SCHEMA
    snapshot = f"{_quote(schema)}.{_quote('plane_0126_audit_catalog_snapshot')}"
    binding = f"{_quote(schema)}.{_quote('plane_0126_audit_catalog_snapshot_binding')}"

    _require_head_audit_snapshot()
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT snapshot FROM {snapshot} WHERE snapshot_id = TRUE")
        original_snapshot = cursor.fetchone()[0]
        if isinstance(original_snapshot, str):
            original_snapshot = json.loads(original_snapshot)
        cursor.execute(f"SELECT version, snapshot_digest, topology FROM {binding} WHERE binding_id = TRUE")
        original_version, original_digest, original_topology = cursor.fetchone()
        original_snapshot = copy.deepcopy(original_snapshot)
        if isinstance(original_topology, str):
            original_topology = json.loads(original_topology)
        original_topology = copy.deepcopy(original_topology)
        cursor.execute(
            "SELECT proc.proconfig, table_owner.rolname "
            "FROM pg_proc AS proc "
            "JOIN pg_namespace AS proc_schema ON proc_schema.oid = proc.pronamespace "
            "JOIN pg_class AS audit_table ON audit_table.relname = %s "
            "JOIN pg_namespace AS audit_table_schema ON audit_table_schema.oid = audit_table.relnamespace "
            "JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner "
            "WHERE proc_schema.nspname = %s AND proc.proname = %s "
            "AND audit_table_schema.nspname = %s "
            "AND pg_get_function_identity_arguments(proc.oid) = ''",
            ["operation_gateway_audit", schema, "operation_gateway_audit_append_only", schema],
        )
        original_function_config, original_table_owner = cursor.fetchone()

    try:
        if tamper_kind == "content":
            tampered_snapshot = copy.deepcopy(original_snapshot)
            function_info = next(
                item
                for item in tampered_snapshot["objects"]
                if item["kind"] == "function" and item["name"] == "operation_gateway_audit_append_only"
            )
            function_info["config"] = ["search_path=pg_temp"]
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {snapshot} SET snapshot = %s::jsonb WHERE snapshot_id = TRUE",
                    [json.dumps(tampered_snapshot)],
                )
            expected_error = "digest"
        else:
            tampered_topology = copy.deepcopy(original_topology)
            tampered_topology["objects"]["audit_function"]["oid"] += 1
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {binding} SET topology = %s::jsonb WHERE binding_id = TRUE",
                    [json.dumps(tampered_topology)],
                )
            expected_error = "topology"

        with pytest.raises(RuntimeError, match=expected_error):
            call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proc.proconfig, table_owner.rolname "
                "FROM pg_proc AS proc "
                "JOIN pg_namespace AS proc_schema ON proc_schema.oid = proc.pronamespace "
                "JOIN pg_class AS audit_table ON audit_table.relname = %s "
                "JOIN pg_namespace AS audit_table_schema ON audit_table_schema.oid = audit_table.relnamespace "
                "JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner "
                "WHERE proc_schema.nspname = %s AND proc.proname = %s "
                "AND audit_table_schema.nspname = %s "
                "AND pg_get_function_identity_arguments(proc.oid) = ''",
                ["operation_gateway_audit", schema, "operation_gateway_audit_append_only", schema],
            )
            assert cursor.fetchone() == (original_function_config, original_table_owner)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {snapshot} SET snapshot = %s::jsonb WHERE snapshot_id = TRUE",
                [json.dumps(original_snapshot)],
            )
            cursor.execute(
                f"UPDATE {binding} SET version = %s, snapshot_digest = %s, topology = %s::jsonb "
                "WHERE binding_id = TRUE",
                [original_version, original_digest, json.dumps(original_topology)],
            )

import uuid

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import override_settings


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
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(migration_probe)}")
            cursor.execute(f"DROP ROLE IF EXISTS {_quote(unrelated_owner)}")

"""Apply the privileged Operation Gateway audit boundary as the provisioner."""

from __future__ import annotations

import re

from django.conf import settings


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
CATALOG_SNAPSHOT_TABLE = "plane_0126_audit_catalog_snapshot"


def _role_identifier(connection, value: str) -> str:
    if not isinstance(value, str) or not ROLE_NAME.fullmatch(value):
        raise RuntimeError("Operation Gateway audit role names must be simple PostgreSQL identifiers")
    return connection.ops.quote_name(value)


def configure_audit_role_boundary(connection, *, runtime_role, governance_role, migration_role):
    schema_name = settings.PLANE_AUDIT_SCHEMA
    if not runtime_role or not governance_role or not migration_role:
        raise RuntimeError("Operation Gateway audit runtime and governance roles must be distinct")
    if runtime_role == governance_role or (
        settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION and runtime_role == migration_role
    ):
        raise RuntimeError("Operation Gateway audit runtime, migration, and governance roles must be distinct")
    runtime_ident = _role_identifier(connection, runtime_role)
    governance_ident = _role_identifier(connection, governance_role)
    migration_ident = _role_identifier(connection, migration_role)
    schema_ident = _role_identifier(connection, schema_name)

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema, search_path = cursor.fetchone()
        if current_schema != schema_name or search_path != [schema_name]:
            raise RuntimeError("Operation Gateway audit uses an unapproved schema/search_path")
        cursor.execute(
            "SELECT rolname, rolcanlogin, rolinherit FROM pg_roles WHERE rolname = %s",
            [governance_role],
        )
        if cursor.fetchone() != (governance_role, False, False):
            raise RuntimeError("The Operation Gateway governance role must be NOLOGIN NOINHERIT")
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = %s", [migration_role])
        migration_is_superuser = bool(cursor.fetchone()[0])
        if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION or not migration_is_superuser:
            cursor.execute("SELECT pg_has_role(%s, %s, 'USAGE')", [migration_role, governance_role])
            if cursor.fetchone()[0]:
                raise RuntimeError("The migration role retains governance membership")
        marker_regclass = f"{schema_name}.plane_operation_gateway_authority_marker"
        cursor.execute(
            """
            SELECT marker_owner.rolname
            FROM pg_class AS marker
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker.relnamespace
            JOIN pg_roles AS marker_owner ON marker_owner.oid = marker.relowner
            WHERE marker.oid = to_regclass(%s)
              AND marker_schema.nspname = %s
            """,
            [marker_regclass, schema_name],
        )
        if cursor.fetchone() != (governance_role,):
            raise RuntimeError("The authority marker must be owned by the governance role")
        if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
            cursor.execute(
                """
                SELECT database_owner.rolname, schema_owner.rolname
                FROM pg_database AS database_info
                JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
                JOIN pg_namespace AS audit_schema ON audit_schema.nspname = %s
                JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
                WHERE database_info.datname = current_database()
                """,
                [schema_name],
            )
            owner_roles = cursor.fetchone()
            provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE
            if not ROLE_NAME.fullmatch(provisioner_role or ""):
                raise RuntimeError("PLANE_AUDIT_PROVISIONER_ROLE is required for enforced migrations")
            if (
                owner_roles is None
                or owner_roles[0] != provisioner_role
                or owner_roles[1]
                not in {
                    provisioner_role,
                    "pg_database_owner",
                }
            ):
                raise RuntimeError("The database and audit schema owners do not match the provisioned topology")

        # The provisioner may use a transient membership to transfer ownership;
        # the final role graph is checked again below and contains no edge.
        cursor.execute(f"GRANT {governance_ident} TO {migration_ident}")
        cursor.execute(f"REVOKE {governance_ident} FROM {runtime_ident}")
        cursor.execute(f"REVOKE {migration_ident} FROM {runtime_ident}")

        # PostgreSQL requires the target owner to have CREATE on the schema
        # during an ownership transfer. Keep this capability scoped to the
        # transfer; the governance role is otherwise NOLOGIN and has no
        # schema-creation responsibility.
        cursor.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_ident} TO {governance_ident}")
        cursor.execute(f"ALTER TABLE {schema_ident}.operation_gateway_audit OWNER TO {governance_ident}")
        cursor.execute(
            f"ALTER FUNCTION {schema_ident}.operation_gateway_audit_append_only() OWNER TO {governance_ident}"
        )
        cursor.execute(f"REVOKE CREATE ON SCHEMA {schema_ident} FROM {governance_ident}")
        cursor.execute(f"ALTER FUNCTION {schema_ident}.operation_gateway_audit_append_only() SECURITY DEFINER")
        cursor.execute(
            f"ALTER FUNCTION {schema_ident}.operation_gateway_audit_append_only() SET search_path = pg_catalog"
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(f"REVOKE CREATE ON SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(f"REVOKE ALL ON SCHEMA {schema_ident} FROM PUBLIC")
        cursor.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_ident} TO {migration_ident}")
        cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {governance_ident}")

        # The runtime role needs ordinary Plane ORM access to the application
        # schema. Keep this grant explicit rather than using ALL so it cannot
        # acquire DDL, TRUNCATE, or role-governance powers through the schema.
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_ident} TO {runtime_ident}"
        )
        cursor.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT EXECUTE ON FUNCTIONS TO {runtime_ident}"
        )
        for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
                f"REVOKE ALL ON {object_type} FROM PUBLIC"
            )

        snapshot_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_TABLE)
        cursor.execute(
            f"REVOKE ALL ON TABLE {schema_ident}.{snapshot_ident} FROM PUBLIC, {runtime_ident}, {governance_ident}"
        )

        marker_ident = connection.ops.quote_name("plane_operation_gateway_authority_marker")
        cursor.execute(
            f"REVOKE ALL ON TABLE {schema_ident}.{marker_ident} FROM PUBLIC, "
            f"{runtime_ident}, {migration_ident}, {governance_ident}"
        )
        cursor.execute(f"GRANT SELECT ON TABLE {schema_ident}.{marker_ident} TO {runtime_ident}, {migration_ident}")

        # Audit storage is stricter than the ordinary application schema.
        cursor.execute(f"REVOKE ALL ON TABLE {schema_ident}.operation_gateway_audit FROM PUBLIC")
        cursor.execute(f"GRANT SELECT, INSERT ON TABLE {schema_ident}.operation_gateway_audit TO {runtime_ident}")
        # The one-shot migrator still needs to inspect and append audit rows
        # while running later migrations, but it does not receive mutation or
        # trigger-control privileges through this grant.
        cursor.execute(f"GRANT SELECT, INSERT ON TABLE {schema_ident}.operation_gateway_audit TO {migration_ident}")
        cursor.execute(
            f"REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE {schema_ident}.operation_gateway_audit "
            f"FROM {runtime_ident}"
        )
        cursor.execute(
            f"REVOKE ALL ON FUNCTION {schema_ident}.operation_gateway_audit_append_only() FROM PUBLIC, {runtime_ident}"
        )
        cursor.execute(
            f"GRANT EXECUTE ON FUNCTION {schema_ident}.operation_gateway_audit_append_only() TO {governance_ident}"
        )
        cursor.execute(
            f"GRANT EXECUTE ON FUNCTION {schema_ident}.operation_gateway_audit_append_only() TO {migration_ident}"
        )

        cursor.execute(
            """
            SELECT c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relkind = 'S'
              AND c.relname LIKE 'operation_gateway_audit%%'
        """,
            [schema_name],
        )
        for (sequence_name,) in cursor.fetchall():
            sequence_ident = _role_identifier(connection, sequence_name)
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE {schema_ident}.{sequence_ident} TO {runtime_ident}")

        cursor.execute(f"REVOKE {governance_ident} FROM {migration_ident}")

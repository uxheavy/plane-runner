"""Verify that the authenticated provisioner prepared the migration boundary."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
AUTHORITY_MARKER_TABLE = "plane_operation_gateway_authority_marker"


def _role_reachable(cursor, member_role: str, target_role: str) -> bool:
    """Check direct and transitive membership independently of NOINHERIT."""

    cursor.execute(
        """
        WITH RECURSIVE role_graph(member_oid, role_oid, path) AS (
            SELECT member, roleid, ARRAY[member, roleid]::oid[]
            FROM pg_auth_members
            UNION ALL
            SELECT graph.member_oid, membership.roleid, graph.path || membership.roleid
            FROM role_graph AS graph
            JOIN pg_auth_members AS membership ON membership.member = graph.role_oid
            WHERE NOT membership.roleid = ANY(graph.path)
        )
        SELECT EXISTS (
            SELECT 1
            FROM role_graph
            JOIN pg_roles AS member ON member.oid = role_graph.member_oid
            JOIN pg_roles AS target ON target.oid = role_graph.role_oid
            WHERE member.rolname = %s AND target.rolname = %s
        )
        """,
        [member_role, target_role],
    )
    return bool(cursor.fetchone()[0])


def _assert_no_protected_membership(cursor, member_role: str, target_role: str) -> None:
    if _role_reachable(cursor, member_role, target_role):
        raise CommandError("The migration role retains governance membership")


class Command(BaseCommand):
    help = "Verify the provisioned boundary before running ordinary migrations."

    def handle(self, *args, **options):
        if not settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
            return

        runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
        governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
        migration_role = settings.PLANE_AUDIT_MIGRATION_ROLE
        provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE
        if not all(
            ROLE_NAME.fullmatch(role or "")
            for role in (runtime_role, governance_role, migration_role, provisioner_role)
        ):
            raise CommandError("The provisioned audit role names are invalid")
        if len({runtime_role, governance_role, migration_role, provisioner_role}) != 4:
            raise CommandError("The provisioned audit roles must be distinct")

        schema_name = settings.PLANE_AUDIT_SCHEMA
        if not ROLE_NAME.fullmatch(schema_name or ""):
            raise CommandError("PLANE_AUDIT_SCHEMA must be a simple PostgreSQL identifier")
        schema_ident = connection.ops.quote_name(schema_name)
        marker_ident = f"{schema_ident}.{connection.ops.quote_name(AUTHORITY_MARKER_TABLE)}"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit "
                "FROM pg_roles WHERE rolname = current_user"
            )
            current_role = cursor.fetchone()
            if current_role != (migration_role, False, False, False, False, True, False):
                raise CommandError("The ordinary migration must run as the limited configured migration role")

            role_placeholders = ", ".join(["%s"] * 4)
            cursor.execute(
                f"SELECT rolname FROM pg_roles WHERE rolname IN ({role_placeholders})",
                [runtime_role, governance_role, migration_role, provisioner_role],
            )
            if {row[0] for row in cursor.fetchall()} != {
                runtime_role,
                governance_role,
                migration_role,
                provisioner_role,
            }:
                raise CommandError("The provisioner did not create all configured audit roles")

            cursor.execute(
                "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit "
                "FROM pg_roles WHERE rolname IN (%s, %s)",
                [runtime_role, governance_role],
            )
            protected_roles = {row[0]: row[1:] for row in cursor.fetchall()}
            if protected_roles.get(runtime_role) != (False, False, False, False, True, False):
                raise CommandError("The runtime role has governance powers or the wrong login boundary")
            if protected_roles.get(governance_role) != (False, False, False, False, False, False):
                raise CommandError("The governance role must be NOLOGIN NOINHERIT without role powers")

            _assert_no_protected_membership(cursor, migration_role, governance_role)
            cursor.execute(
                "SELECT has_schema_privilege(%s, %s, 'USAGE'), has_schema_privilege(%s, %s, 'CREATE')",
                [migration_role, schema_name, migration_role, schema_name],
            )
            can_use_schema, can_create_in_schema = cursor.fetchone()
            if not can_use_schema or not can_create_in_schema:
                raise CommandError("The migration role is missing its provisioned schema boundary")

            cursor.execute(
                """
                SELECT database_info.datdba, database_owner.rolname,
                       schema_owner.oid, schema_owner.rolname
                FROM pg_database AS database_info
                JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
                JOIN pg_namespace AS schema_info ON schema_info.nspname = %s
                JOIN pg_roles AS schema_owner ON schema_owner.oid = schema_info.nspowner
                WHERE database_info.datname = current_database()
                """,
                [schema_name],
            )
            topology = cursor.fetchone()
            if topology is None:
                raise CommandError("The provisioned database/schema topology is missing")
            database_owner_oid, database_owner, schema_owner_oid, schema_owner = topology
            if database_owner != provisioner_role or schema_owner not in {provisioner_role, "pg_database_owner"}:
                raise CommandError("The provisioner did not establish the required database/schema ownership")

            cursor.execute("SELECT current_schema(), current_schemas(false)")
            current_schema, search_path = cursor.fetchone()
            if current_schema != schema_name or search_path != [schema_name]:
                raise CommandError("The migration session uses an unapproved schema/search_path")

            cursor.execute(
                f"""
                SELECT marker_owner.rolname, marker.relacl,
                       marker_data.version, marker_data.database_owner_oid,
                       marker_data.database_owner_role, marker_data.schema_name,
                       marker_data.schema_owner_oid, marker_data.schema_owner_role
                FROM pg_class AS marker
                JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker.relnamespace
                JOIN pg_roles AS marker_owner ON marker_owner.oid = marker.relowner
                LEFT JOIN LATERAL (
                    SELECT version, database_owner_oid, database_owner_role,
                           schema_name, schema_owner_oid, schema_owner_role
                    FROM {marker_ident}
                    WHERE marker_id = TRUE
                ) AS marker_data ON TRUE
                WHERE marker.oid = to_regclass(%s)
                  AND marker_schema.nspname = %s
                  AND marker.relkind = 'r'
                """,
                [marker_ident, schema_name],
            )
            marker = cursor.fetchone()
            if marker is None:
                raise CommandError("The provisioner authority marker is missing")
            marker_owner, marker_acl, *marker_data = marker
            if marker_owner != governance_role:
                raise CommandError("The provisioner authority marker is not governance-owned")
            if marker_data != [1, database_owner_oid, database_owner, schema_name, schema_owner_oid, schema_owner]:
                raise CommandError("The provisioner authority marker does not match the database topology")

            cursor.execute(
                """
                SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                       exploded.privilege_type, exploded.is_grantable
                FROM aclexplode(%s) AS exploded
                LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
                """,
                [marker_acl],
            )
            marker_privileges = {
                (grantee, privilege, bool(is_grantable)) for grantee, privilege, is_grantable in cursor.fetchall()
            }
            if marker_privileges != {
                (runtime_role, "SELECT", False),
                (migration_role, "SELECT", False),
            }:
                raise CommandError("The authority marker ACL is not limited to runtime and migrator reads")

        self.stdout.write(self.style.SUCCESS("Provisioned migration boundary verified"))

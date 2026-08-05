"""Provision the Operation Gateway audit roles before application migrations."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
AUTHORITY_MARKER_TABLE = "plane_operation_gateway_authority_marker"


class Command(BaseCommand):
    help = "Provision and verify the Operation Gateway runtime, migration, and audit roles."

    def handle(self, *args, **options):
        runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
        governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
        migration_role = settings.PLANE_AUDIT_MIGRATION_ROLE
        provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE
        if not all(ROLE_NAME.fullmatch(role or "") for role in (runtime_role, governance_role, migration_role)):
            raise CommandError("Operation Gateway role names must be simple PostgreSQL identifiers")

        with connection.cursor() as cursor:
            current_user, can_create_roles = self._current_role(cursor)
            if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
                if not ROLE_NAME.fullmatch(provisioner_role or ""):
                    raise CommandError("PLANE_AUDIT_PROVISIONER_ROLE is required for enforced bootstrap")
                if provisioner_role in {runtime_role, governance_role, migration_role}:
                    raise CommandError(
                        "The bootstrap provisioner must be separate from runtime, migration, and governance roles"
                    )
                if current_user != provisioner_role or not can_create_roles:
                    raise CommandError("Enforced audit bootstrap requires the configured provisioner/admin credential")

            self._ensure_role(
                cursor,
                role=governance_role,
                create_sql=f"CREATE ROLE {self._quote(governance_role)} NOLOGIN NOINHERIT",
                current_user=current_user,
                can_create_roles=can_create_roles,
            )
            cursor.execute(f"ALTER ROLE {self._quote(governance_role)} NOLOGIN NOINHERIT")
            self._ensure_runtime_role(
                cursor,
                role=runtime_role,
                current_user=current_user,
                can_create_roles=can_create_roles,
            )

            if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
                if runtime_role in {governance_role, migration_role}:
                    raise CommandError("Runtime, migration, and governance roles must be distinct")
                cursor.execute(
                    "SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = %s",
                    [governance_role],
                )
                governance_attributes = cursor.fetchone()
                if governance_attributes != (False, False):
                    raise CommandError("The governance role must be NOLOGIN NOINHERIT")
                self._assert_migration_role_safety(cursor, migration_role)
                self._assert_role_safety(cursor, runtime_role, governance_role, migration_role)

            self._ensure_authority_marker(
                cursor,
                runtime_role=runtime_role,
                governance_role=governance_role,
                migration_role=migration_role,
            )

        self.stdout.write(self.style.SUCCESS("Operation Gateway audit roles are provisioned and separated"))

    @staticmethod
    def _quote(role: str) -> str:
        return connection.ops.quote_name(role)

    @staticmethod
    def _current_role(cursor):
        cursor.execute("SELECT current_user, rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
        row = cursor.fetchone()
        if row is None:
            raise CommandError("The current PostgreSQL role does not exist")
        return row

    def _ensure_role(self, cursor, *, role, create_sql, current_user, can_create_roles):
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        if cursor.fetchone() is not None:
            return
        if not can_create_roles:
            raise CommandError(f"Missing {role} role and migration authority cannot create roles")
        cursor.execute(create_sql)

    def _ensure_runtime_role(self, cursor, *, role, current_user, can_create_roles):
        cursor.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit "
            "FROM pg_roles WHERE rolname = %s",
            [role],
        )
        row = cursor.fetchone()
        if row is None:
            if not can_create_roles:
                raise CommandError(f"Missing {role} role and migration authority cannot create roles")
            password = settings.PLANE_AUDIT_RUNTIME_PASSWORD
            if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION and not password:
                raise CommandError("PLANE_AUDIT_RUNTIME_PASSWORD is required to provision the runtime role")
            cursor.execute(
                f"CREATE ROLE {self._quote(role)} LOGIN NOINHERIT PASSWORD %s",
                [password or None],
            )
            row = (False, False, False, False, True, False)
        if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
            if any(row[:4]):
                raise CommandError("The Operation Gateway runtime role has governance powers")
            if not row[4] or row[5]:
                raise CommandError("The Operation Gateway runtime role must be LOGIN NOINHERIT")

    def _ensure_authority_marker(self, cursor, *, runtime_role, governance_role, migration_role):
        schema_name = settings.PLANE_AUDIT_SCHEMA
        if not ROLE_NAME.fullmatch(schema_name or ""):
            raise CommandError("PLANE_AUDIT_SCHEMA must be a simple PostgreSQL identifier")
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [migration_role])
        if cursor.fetchone() is None:
            raise CommandError("The configured migration role is missing; provision it separately")
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema_name, search_path = cursor.fetchone()
        if current_schema_name != schema_name or search_path != [schema_name]:
            raise CommandError("Audit bootstrap uses an unapproved audit schema/search_path")

        schema_ident = self._quote(schema_name)
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
            raise CommandError("The configured audit schema is not provisioned")
        database_owner_oid, database_owner_role, schema_owner_oid, schema_owner_role = topology
        if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
            provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE
            if database_owner_role != provisioner_role or schema_owner_role not in {
                provisioner_role,
                "pg_database_owner",
            }:
                raise CommandError("The database and audit schema owners do not match the provisioned topology")
        marker_ident = f"{schema_ident}.{self._quote(AUTHORITY_MARKER_TABLE)}"
        cursor.execute(
            """
            SELECT marker_owner.rolname
            FROM pg_class AS marker
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker.relnamespace
            JOIN pg_roles AS marker_owner ON marker_owner.oid = marker.relowner
            WHERE marker_schema.nspname = %s
              AND marker.relname = %s
              AND marker.relkind = 'r'
            """,
            [schema_name, AUTHORITY_MARKER_TABLE],
        )
        marker_owner = cursor.fetchone()
        if marker_owner is None:
            cursor.execute(
                f"""
                CREATE TABLE {marker_ident} (
                    marker_id boolean PRIMARY KEY CHECK (marker_id),
                    version integer NOT NULL CHECK (version = 1),
                    database_owner_oid oid NOT NULL,
                    database_owner_role name NOT NULL,
                    schema_name name NOT NULL,
                    schema_owner_oid oid NOT NULL,
                    schema_owner_role name NOT NULL
                )
                """
            )
            cursor.execute(
                f"""
                INSERT INTO {marker_ident} (
                    marker_id, version, database_owner_oid, database_owner_role,
                    schema_name, schema_owner_oid, schema_owner_role
                ) VALUES (TRUE, 1, %s, %s, %s, %s, %s)
                """,
                [database_owner_oid, database_owner_role, schema_name, schema_owner_oid, schema_owner_role],
            )
        else:
            cursor.execute(
                f"""
                SELECT version, database_owner_oid, database_owner_role,
                       schema_name, schema_owner_oid, schema_owner_role
                FROM {marker_ident}
                WHERE marker_id = TRUE
                """
            )
            marker = cursor.fetchone()
            if marker is None or marker != (
                1,
                database_owner_oid,
                database_owner_role,
                schema_name,
                schema_owner_oid,
                schema_owner_role,
            ):
                raise CommandError(
                    "The Operation Gateway authority marker does not match the provisioned database topology"
                )

        marker_owner = marker_owner[0] if marker_owner else migration_role
        if marker_owner not in {governance_role, migration_role}:
            raise CommandError("The authority marker has an unapproved owner")
        if self._role_reachable(cursor, migration_role, governance_role):
            raise CommandError("The migration role retains governance membership")
        granted_transient_membership = False
        try:
            cursor.execute(f"GRANT {self._quote(governance_role)} TO {self._quote(migration_role)}")
            granted_transient_membership = True
            if marker_owner == migration_role:
                cursor.execute(f"ALTER TABLE {marker_ident} OWNER TO {self._quote(governance_role)}")
            cursor.execute(
                f"REVOKE ALL ON TABLE {marker_ident} FROM PUBLIC, {self._quote(runtime_role)}, "
                f"{self._quote(migration_role)}, {self._quote(governance_role)}"
            )
            cursor.execute(
                f"GRANT SELECT ON TABLE {marker_ident} TO {self._quote(runtime_role)}, {self._quote(migration_role)}"
            )
        finally:
            if granted_transient_membership:
                cursor.execute(f"REVOKE {self._quote(governance_role)} FROM {self._quote(migration_role)}")
        self._assert_authority_marker(
            cursor,
            marker_ident=marker_ident,
            schema_name=schema_name,
            runtime_role=runtime_role,
            governance_role=governance_role,
            migration_role=migration_role,
        )

    @staticmethod
    def _role_reachable(cursor, member_role, target_role):
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

    @staticmethod
    def _assert_authority_marker(cursor, *, marker_ident, schema_name, runtime_role, governance_role, migration_role):
        cursor.execute(
            """
            SELECT marker_owner.rolname
            FROM pg_class AS marker
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker.relnamespace
            JOIN pg_roles AS marker_owner ON marker_owner.oid = marker.relowner
            WHERE marker.oid = to_regclass(%s)
              AND marker_schema.nspname = %s
              AND marker.relkind = 'r'
            """,
            [marker_ident, schema_name],
        )
        marker_owner = cursor.fetchone()
        if marker_owner != (governance_role,):
            raise CommandError("The authority marker must be owned by the governance role")
        cursor.execute(
            """
            SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS marker
            JOIN LATERAL aclexplode(marker.relacl) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE marker.oid = to_regclass(%s)
            """,
            [marker_ident],
        )
        marker_acl = {
            (grantee, privilege, bool(is_grantable)) for grantee, privilege, is_grantable in cursor.fetchall()
        }
        if marker_acl != {
            (runtime_role, "SELECT", False),
            (migration_role, "SELECT", False),
        }:
            raise CommandError("The authority marker ACL is not limited to runtime and migrator reads")
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = %s", [migration_role])
        migration_is_superuser = bool(cursor.fetchone()[0])
        if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION or not migration_is_superuser:
            cursor.execute(
                """
                SELECT has_table_privilege(%s, %s::regclass, 'SELECT'),
                       has_table_privilege(%s, %s::regclass, 'INSERT'),
                       has_table_privilege(%s, %s::regclass, 'UPDATE'),
                       has_table_privilege(%s, %s::regclass, 'DELETE'),
                       has_table_privilege(%s, %s::regclass, 'TRUNCATE'),
                       has_table_privilege(%s, %s::regclass, 'REFERENCES'),
                       has_table_privilege(%s, %s::regclass, 'TRIGGER')
                """,
                [migration_role, marker_ident] * 7,
            )
            if cursor.fetchone() != (True, False, False, False, False, False, False):
                raise CommandError("The migration role has more than read access to the authority marker")
        if Command._role_reachable(cursor, migration_role, governance_role):
            raise CommandError("The migration role retains governance membership")

    @staticmethod
    def _assert_migration_role_safety(cursor, migration_role):
        cursor.execute(
            """
            SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit
            FROM pg_roles
            WHERE rolname = %s
            """,
            [migration_role],
        )
        role_attributes = cursor.fetchone()
        if role_attributes is None:
            raise CommandError("The configured migration role is missing; provision it separately")
        if any(role_attributes[:4]):
            raise CommandError("The migration role has governance powers")
        if not role_attributes[4] or role_attributes[5]:
            raise CommandError("The migration role must be LOGIN NOINHERIT")

    @staticmethod
    def _assert_role_safety(cursor, runtime_role, governance_role, migration_role):
        for target_role in (governance_role, migration_role):
            cursor.execute(
                "SELECT pg_has_role(%s, %s, 'USAGE')",
                [runtime_role, target_role],
            )
            if cursor.fetchone()[0]:
                raise CommandError(f"Runtime role can SET ROLE to protected role {target_role}")
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
                JOIN pg_roles AS member_role ON member_role.oid = role_graph.member_oid
                JOIN pg_roles AS target_role ON target_role.oid = role_graph.role_oid
                WHERE member_role.rolname = %s
                  AND target_role.rolname IN (%s, %s)
            )
            """,
            [runtime_role, governance_role, migration_role],
        )
        if cursor.fetchone()[0]:
            raise CommandError("Runtime role has direct or transitive membership in a protected role")

"""Provision the Operation Gateway audit roles before application migrations."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")


class Command(BaseCommand):
    help = "Provision and verify the Operation Gateway runtime, migration, and audit roles."

    def handle(self, *args, **options):
        runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
        governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
        migration_role = settings.PLANE_AUDIT_MIGRATION_ROLE
        if not all(ROLE_NAME.fullmatch(role or "") for role in (runtime_role, governance_role, migration_role)):
            raise CommandError("Operation Gateway role names must be simple PostgreSQL identifiers")

        with connection.cursor() as cursor:
            current_user, can_create_roles = self._current_role(cursor)
            if settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION and current_user != migration_role:
                raise CommandError(
                    "Audit bootstrap must run with the configured migration database credential"
                )

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
                self._assert_role_safety(cursor, runtime_role, governance_role, migration_role)

        self.stdout.write(self.style.SUCCESS("Operation Gateway audit roles are provisioned and separated"))

    @staticmethod
    def _quote(role: str) -> str:
        return connection.ops.quote_name(role)

    @staticmethod
    def _current_role(cursor):
        cursor.execute(
            "SELECT current_user, rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
        )
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

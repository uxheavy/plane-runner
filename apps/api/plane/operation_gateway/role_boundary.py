"""Fail-closed checks for the database boundary around gateway audit rows."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.db import connection


class AuditRoleBoundaryError(RuntimeError):
    """The configured runtime role cannot safely use the audit table."""


def audited_gateway_boundary(method: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the same fail-closed database check to every public gateway path."""

    @wraps(method)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        verify_audit_role_boundary()
        return method(*args, **kwargs)

    return guarded


def _role_reachable(cursor: Any, member: str, target: str) -> bool:
    """Return whether ``member`` can reach ``target`` through any membership edge."""

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
              AND target_role.rolname = %s
        )
        """,
        [member, target],
    )
    return bool(cursor.fetchone()[0])


def verify_audit_role_boundary() -> None:
    """Verify production's complete non-owner, non-superuser audit contract."""

    if not settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
        return

    runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    migration_role = settings.PLANE_AUDIT_MIGRATION_ROLE
    if (
        not runtime_role
        or not governance_role
        or not migration_role
        or runtime_role in {governance_role, migration_role}
    ):
        raise AuditRoleBoundaryError("Operation Gateway audit roles are not distinct and configured")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user, runtime.rolsuper, runtime.rolcreaterole,
                   runtime.rolcreatedb, runtime.rolbypassrls,
                   runtime.rolcanlogin, runtime.rolinherit,
                   table_info.tableowner, table_info.function_owner,
                   table_info.schema_owner,
                   table_info.function_security_definer,
                   table_info.function_config,
                   has_schema_privilege(current_user, current_schema(), 'USAGE'),
                   has_schema_privilege(current_user, current_schema(), 'CREATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'SELECT'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'INSERT'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'UPDATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'DELETE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'TRUNCATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'REFERENCES'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'TRIGGER'),
                   has_function_privilege(
                       current_user,
                       'operation_gateway_audit_append_only()'::regprocedure,
                       'EXECUTE'
                   ),
                   has_database_privilege(current_user, current_database(), 'CREATE')
            FROM pg_roles AS runtime
            JOIN (
                SELECT table_owner.rolname AS tableowner,
                       function_owner.rolname AS function_owner,
                       schema_owner.rolname AS schema_owner,
                       audit_function.prosecdef AS function_security_definer,
                       audit_function.proconfig AS function_config
                FROM pg_class AS audit_table
                JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_table.relnamespace
                JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner
                JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
                JOIN pg_proc AS audit_function
                  ON audit_function.oid = to_regprocedure('operation_gateway_audit_append_only()')
                JOIN pg_roles AS function_owner ON function_owner.oid = audit_function.proowner
                WHERE audit_schema.nspname = current_schema()
                  AND audit_table.relname = 'operation_gateway_audit'
            ) AS table_info ON TRUE
            WHERE runtime.rolname = current_user
            """
        )
        row = cursor.fetchone()

    if row is None:
        raise AuditRoleBoundaryError("The configured audit runtime role does not exist")

    (
        current_user,
        is_superuser,
        can_create_roles,
        can_create_databases,
        bypasses_rls,
        can_login,
        inherits_roles,
        table_owner,
        function_owner,
        schema_owner,
        function_security_definer,
        function_config,
        can_use_schema,
        can_create_in_schema,
        can_select,
        can_insert,
        can_update,
        can_delete,
        can_truncate,
        can_reference,
        can_trigger,
        can_execute_trigger_function,
        can_create_in_database,
    ) = row
    if current_user != runtime_role:
        raise AuditRoleBoundaryError("The database session role is not the configured audit runtime role")
    if is_superuser or can_create_roles or can_create_databases or bypasses_rls:
        raise AuditRoleBoundaryError("The audit runtime role has governance privileges")
    if not can_login or inherits_roles:
        raise AuditRoleBoundaryError("The audit runtime role must be LOGIN NOINHERIT")
    if table_owner != governance_role:
        raise AuditRoleBoundaryError("The audit table is not owned by the governed audit role")
    if function_owner != governance_role:
        raise AuditRoleBoundaryError("The append-only trigger function is not owned by the governed audit role")
    if not function_security_definer or function_config != ["search_path=pg_catalog"]:
        raise AuditRoleBoundaryError("The append-only trigger function has an unsafe execution context")
    if schema_owner == runtime_role:
        raise AuditRoleBoundaryError("The audit schema is owned by the runtime role")
    if (
        not can_use_schema
        or can_create_in_schema
        or not can_select
        or not can_insert
        or can_update
        or can_delete
        or can_truncate
        or can_reference
        or can_trigger
        or can_execute_trigger_function
        or can_create_in_database
    ):
        raise AuditRoleBoundaryError("The audit runtime role has an invalid table privilege set")

    with connection.cursor() as cursor:
        for target_role in (governance_role, migration_role):
            if _role_reachable(cursor, runtime_role, target_role):
                raise AuditRoleBoundaryError(
                    f"The audit runtime role can reach the protected role {target_role}"
                )
            # PostgreSQL 15 exposes SET ROLE reachability through the USAGE
            # role privilege; newer versions also document it as SET.
            cursor.execute("SELECT pg_has_role(%s, %s, 'USAGE')", [runtime_role, target_role])
            if cursor.fetchone()[0]:
                raise AuditRoleBoundaryError(
                    f"The audit runtime role can SET ROLE to the protected role {target_role}"
                )

        cursor.execute(
            """
            SELECT tgname, tgenabled, tgisinternal, pg_get_triggerdef(pg_trigger.oid)
            FROM pg_trigger
            JOIN pg_class ON pg_class.oid = pg_trigger.tgrelid
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE pg_namespace.nspname = current_schema()
              AND pg_class.relname = 'operation_gateway_audit'
              AND NOT pg_trigger.tgisinternal
            ORDER BY tgname
            """
        )
        trigger_rows = cursor.fetchall()
    trigger_names = {row[0] for row in trigger_rows}
    expected_trigger_names = {
        "operation_gateway_audit_append_only_row_trigger",
        "operation_gateway_audit_append_only_truncate_trigger",
    }
    trigger_definitions = {row[0]: row[3].lower() for row in trigger_rows}
    row_trigger_def = trigger_definitions.get("operation_gateway_audit_append_only_row_trigger", "")
    truncate_trigger_def = trigger_definitions.get("operation_gateway_audit_append_only_truncate_trigger", "")
    if (
        trigger_names != expected_trigger_names
        or any(row[1] != "O" for row in trigger_rows)
        or not (
            "before update or delete" in row_trigger_def
            or "before delete or update" in row_trigger_def
        )
        or "for each row" not in row_trigger_def
        or "before truncate" not in truncate_trigger_def
        or "for each statement" not in truncate_trigger_def
        or "operation_gateway_audit_append_only()" not in row_trigger_def
        or "operation_gateway_audit_append_only()" not in truncate_trigger_def
    ):
        raise AuditRoleBoundaryError("The audit append-only triggers are missing or disabled")

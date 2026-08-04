"""Fail-closed checks for the database boundary around gateway audit rows."""

from __future__ import annotations

from django.conf import settings
from django.db import connection


class AuditRoleBoundaryError(RuntimeError):
    """The configured runtime role cannot safely use the audit table."""


def verify_audit_role_boundary() -> None:
    """Verify production's non-owner, non-superuser audit access contract.

    Local and test environments intentionally leave this check disabled while
    they use the repository's single bootstrap database credential. Production
    enables it explicitly; a bad role configuration then fails closed before
    an authenticated gateway operation can be audited or executed.
    """

    if not settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:
        return

    runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    if not runtime_role or not governance_role or runtime_role == governance_role:
        raise AuditRoleBoundaryError("Operation Gateway audit roles are not distinct and configured")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user, runtime.rolsuper, runtime.rolcreaterole,
                   table_info.tableowner,
                   has_schema_privilege(current_user, current_schema(), 'USAGE'),
                   has_schema_privilege(current_user, current_schema(), 'CREATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'SELECT'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'INSERT'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'UPDATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'DELETE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'TRUNCATE'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'REFERENCES'),
                   has_table_privilege(current_user, 'operation_gateway_audit', 'TRIGGER')
            FROM pg_roles AS runtime
            JOIN (
                SELECT tableowner
                FROM pg_tables
                WHERE schemaname = current_schema()
                  AND tablename = 'operation_gateway_audit'
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
        table_owner,
        can_use_schema,
        can_create_in_schema,
        can_select,
        can_insert,
        can_update,
        can_delete,
        can_truncate,
        can_reference,
        can_trigger,
    ) = row
    if current_user != runtime_role:
        raise AuditRoleBoundaryError("The database session role is not the configured audit runtime role")
    if is_superuser or can_create_roles:
        raise AuditRoleBoundaryError("The audit runtime role has governance privileges")
    if table_owner != governance_role:
        raise AuditRoleBoundaryError("The audit table is not owned by the governed audit role")
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
    ):
        raise AuditRoleBoundaryError("The audit runtime role has an invalid table privilege set")

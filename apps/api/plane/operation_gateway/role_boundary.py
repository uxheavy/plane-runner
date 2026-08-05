"""Fail-closed checks for the database boundary around gateway audit rows."""

from __future__ import annotations

import hashlib
import re
from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.db import connection


class AuditRoleBoundaryError(RuntimeError):
    """The configured runtime role cannot safely use the audit table."""


EXPECTED_APPEND_ONLY_FUNCTION_SOURCE = """
BEGIN
    RAISE EXCEPTION 'operation gateway audit records are append-only'
        USING ERRCODE = '55000';
END;
"""


def _normalized_function_source(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip().lower()


EXPECTED_APPEND_ONLY_FUNCTION_DIGEST = hashlib.sha256(
    _normalized_function_source(EXPECTED_APPEND_ONLY_FUNCTION_SOURCE).encode("utf-8")
).hexdigest()


def audited_gateway_boundary(method: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the shared fail-closed check to every externally callable path."""

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


_TABLE_PRIVILEGES = frozenset({"DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE"})
_SEQUENCE_PRIVILEGES = frozenset({"SELECT", "UPDATE", "USAGE"})
_POSTGRES_DATABASE_OWNER_ROLE = "pg_database_owner"
_AUTHORITY_MARKER_TABLE = "plane_operation_gateway_authority_marker"


def _fetch_acl_entries(cursor: Any, query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    cursor.execute(query, params or [])
    return cursor.fetchall()


def _validate_acl_allowlist(
    label: str,
    entries: list[tuple[Any, ...]],
    allowed_privileges: dict[str, frozenset[str]],
    owner_roles: frozenset[str] = frozenset(),
) -> None:
    for grantee, privilege, is_grantable in entries:
        if grantee == "PUBLIC":
            raise AuditRoleBoundaryError(f"The {label} grants {privilege} to PUBLIC")
        if (
            grantee not in allowed_privileges
            or privilege not in allowed_privileges[grantee]
            or (is_grantable and grantee not in owner_roles)
        ):
            raise AuditRoleBoundaryError(f"The {label} has an invalid ACL")


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
        cursor.execute("SELECT current_schema()")
        current_schema_name = cursor.fetchone()[0]
    if not current_schema_name:
        raise AuditRoleBoundaryError("The audit session has no usable schema")
    function_regprocedure = f"{current_schema_name}.operation_gateway_audit_append_only()"

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user, runtime.rolsuper, runtime.rolcreaterole,
                   runtime.rolcreatedb, runtime.rolbypassrls,
                   runtime.rolcanlogin, runtime.rolinherit,
                       table_info.tableowner, table_info.function_owner,
                       table_info.schema_owner,
                       (
                           SELECT schema_owner_role.rolname
                           FROM pg_database AS database_info
                           JOIN pg_roles AS schema_owner_role ON schema_owner_role.oid = database_info.datdba
                           WHERE database_info.datname = current_database()
                       ) AS database_owner,
                       table_info.function_security_definer,
                   table_info.function_config,
                   table_info.function_source,
                   has_function_privilege('public', %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
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
                       %s::regprocedure,
                       'EXECUTE'
                   ),
                   has_database_privilege(current_user, current_database(), 'CREATE')
            FROM pg_roles AS runtime
            JOIN (
                SELECT table_owner.rolname AS tableowner,
                       function_owner.rolname AS function_owner,
                       schema_owner.rolname AS schema_owner,
                       audit_function.prosecdef AS function_security_definer,
                       audit_function.proconfig AS function_config,
                       audit_function.prosrc AS function_source
                FROM pg_class AS audit_table
                JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_table.relnamespace
                JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner
                JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
                JOIN pg_proc AS audit_function
                  ON audit_function.oid = to_regprocedure(%s)
                JOIN pg_roles AS function_owner ON function_owner.oid = audit_function.proowner
                WHERE audit_schema.nspname = current_schema()
                  AND audit_table.relname = 'operation_gateway_audit'
            ) AS table_info ON TRUE
            WHERE runtime.rolname = current_user
            """,
            [
                function_regprocedure,
                runtime_role,
                function_regprocedure,
                migration_role,
                function_regprocedure,
                governance_role,
                function_regprocedure,
                function_regprocedure,
                function_regprocedure,
            ],
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
        database_owner,
        function_security_definer,
        function_config,
        function_source,
        public_can_execute,
        runtime_can_execute,
        migration_can_execute,
        governance_can_execute,
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
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema()")
        current_schema_name = cursor.fetchone()[0]
        schema_ident = connection.ops.quote_name(current_schema_name)
        marker_ident = connection.ops.quote_name(_AUTHORITY_MARKER_TABLE)
        cursor.execute(
            f"""
            SELECT marker.version, marker.database_owner_oid, marker.database_owner_role,
                   marker.schema_name, marker.schema_owner_oid, marker.schema_owner_role,
                   marker_owner.rolname,
                   database_info.datdba, database_owner.rolname
            FROM {schema_ident}.{marker_ident} AS marker
            JOIN pg_class AS marker_table
              ON marker_table.relname = %s
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker_table.relnamespace
            JOIN pg_roles AS marker_owner ON marker_owner.oid = marker_table.relowner
            JOIN pg_database AS database_info ON database_info.datname = current_database()
            JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
            WHERE marker_schema.nspname = %s
              AND marker_table.relkind = 'r'
              AND marker.marker_id = TRUE
            """,
            [_AUTHORITY_MARKER_TABLE, current_schema_name],
        )
        marker_row = cursor.fetchone()
    if marker_row is None:
        raise AuditRoleBoundaryError("The provisioned audit authority marker is missing")
    (
        marker_version,
        marker_database_owner_oid,
        marker_database_owner_role,
        marker_schema_name,
        marker_schema_owner_oid,
        marker_schema_owner_role,
        marker_owner,
        current_database_owner_oid,
        current_database_owner_role,
    ) = marker_row
    if (
        marker_version != 1
        or marker_owner != migration_role
        or marker_schema_name != current_schema_name
        or marker_database_owner_oid != current_database_owner_oid
        or marker_database_owner_role != current_database_owner_role
        or not marker_schema_owner_oid
        or not marker_schema_owner_role
    ):
        raise AuditRoleBoundaryError("The provisioned audit authority marker does not match the database topology")
    with connection.cursor() as cursor:
        marker_regclass = f"{current_schema_name}.{_AUTHORITY_MARKER_TABLE}"
        cursor.execute(
            """
            SELECT has_table_privilege(current_user, %s::regclass, 'SELECT'),
                   has_table_privilege(current_user, %s::regclass, 'INSERT'),
                   has_table_privilege(current_user, %s::regclass, 'UPDATE'),
                   has_table_privilege(current_user, %s::regclass, 'DELETE'),
                   has_table_privilege(current_user, %s::regclass, 'TRUNCATE'),
                   has_table_privilege(current_user, %s::regclass, 'REFERENCES'),
                   has_table_privilege(current_user, %s::regclass, 'TRIGGER'),
                   has_table_privilege('public', %s::regclass, 'SELECT'),
                   has_table_privilege('public', %s::regclass, 'INSERT'),
                   has_table_privilege('public', %s::regclass, 'UPDATE'),
                   has_table_privilege('public', %s::regclass, 'DELETE'),
                   has_table_privilege('public', %s::regclass, 'TRUNCATE'),
                   has_table_privilege('public', %s::regclass, 'REFERENCES'),
                   has_table_privilege('public', %s::regclass, 'TRIGGER')
            """,
            [marker_regclass] * 14,
        )
        marker_privileges = cursor.fetchone()
    if marker_privileges != (True,) + (False,) * 13:
        raise AuditRoleBoundaryError("The provisioned audit authority marker is not immutable to the runtime role")

    # PostgreSQL 15+ owns a fresh public schema by pg_database_owner. An
    # upgraded database may retain the immutable bootstrap database owner or
    # one of the explicit Plane migration/governance owners. The current
    # pg_database.datdba is only compared with the marker; it never enlarges
    # this allowlist.
    approved_schema_owners = frozenset(
        role
        for role in (
            _POSTGRES_DATABASE_OWNER_ROLE,
            marker_database_owner_role,
            marker_schema_owner_role,
            migration_role,
            governance_role,
        )
        if role
    )
    if schema_owner not in approved_schema_owners or schema_owner == runtime_role:
        raise AuditRoleBoundaryError("The audit schema has an unapproved owner topology")
    if not function_security_definer or function_config != ["search_path=pg_catalog"]:
        raise AuditRoleBoundaryError("The append-only trigger function has an unsafe execution context")
    if (
        hashlib.sha256(_normalized_function_source(function_source).encode("utf-8")).hexdigest()
        != EXPECTED_APPEND_ONLY_FUNCTION_DIGEST
    ):
        raise AuditRoleBoundaryError("The append-only trigger function body is not the protected implementation")
    if public_can_execute or runtime_can_execute or not migration_can_execute or not governance_can_execute:
        raise AuditRoleBoundaryError("The append-only trigger function has an invalid ACL")
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
        table_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS audit_table
            JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_table.relnamespace
            JOIN LATERAL aclexplode(
                COALESCE(audit_table.relacl, acldefault('r', audit_table.relowner))
            ) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE audit_schema.nspname = current_schema()
              AND audit_table.relname = 'operation_gateway_audit'
              AND audit_table.relkind = 'r'
            """,
        )
        _validate_acl_allowlist(
            "audit table",
            table_acl_entries,
            {
                table_owner: _TABLE_PRIVILEGES,
                runtime_role: frozenset({"INSERT", "SELECT"}),
                migration_role: frozenset({"INSERT", "SELECT"}),
            },
            frozenset({table_owner}),
        )

        function_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_proc AS audit_function
            JOIN LATERAL aclexplode(
                COALESCE(audit_function.proacl, acldefault('f', audit_function.proowner))
            ) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE audit_function.oid = to_regprocedure(%s)
            """,
            [function_regprocedure],
        )
        _validate_acl_allowlist(
            "append-only trigger function",
            function_acl_entries,
            {
                function_owner: frozenset({"EXECUTE"}),
                migration_role: frozenset({"EXECUTE"}),
                governance_role: frozenset({"EXECUTE"}),
            },
            frozenset({function_owner}),
        )

        schema_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_namespace AS audit_schema
            JOIN LATERAL aclexplode(
                COALESCE(audit_schema.nspacl, acldefault('n', audit_schema.nspowner))
            ) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE audit_schema.nspname = current_schema()
            """,
        )
        schema_acl_allowlist = {
            runtime_role: frozenset({"USAGE"}),
            migration_role: frozenset({"CREATE", "USAGE"}),
            governance_role: frozenset({"USAGE"}),
            _POSTGRES_DATABASE_OWNER_ROLE: frozenset({"CREATE", "USAGE"}),
            marker_database_owner_role: frozenset({"CREATE", "USAGE"}),
        }
        # This only supplies owner privileges after schema_owner has passed the
        # explicit catalog-topology check above; it does not approve the value.
        schema_acl_allowlist[schema_owner] = frozenset({"CREATE", "USAGE"})
        _validate_acl_allowlist(
            "audit schema",
            schema_acl_entries,
            schema_acl_allowlist,
            frozenset({schema_owner}),
        )

        sequence_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT audit_sequence.relname,
                   sequence_owner.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS audit_sequence
            JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_sequence.relnamespace
            JOIN pg_roles AS sequence_owner ON sequence_owner.oid = audit_sequence.relowner
            JOIN LATERAL aclexplode(
                COALESCE(audit_sequence.relacl, acldefault('S', audit_sequence.relowner))
            ) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE audit_schema.nspname = current_schema()
              AND audit_sequence.relkind = 'S'
              AND audit_sequence.relname LIKE 'operation_gateway_audit%%'
            """,
        )
        sequence_entries_by_name: dict[str, list[tuple[Any, ...]]] = {}
        for sequence_name, sequence_owner, grantee, privilege, is_grantable in sequence_acl_entries:
            sequence_entries_by_name.setdefault(sequence_name, []).append(
                (sequence_owner, grantee, privilege, is_grantable)
            )
        for sequence_name, entries in sequence_entries_by_name.items():
            sequence_owner = entries[0][0]
            if sequence_owner not in {marker_database_owner_role, migration_role, governance_role}:
                raise AuditRoleBoundaryError(f"The audit sequence {sequence_name} has an invalid owner")
            _validate_acl_allowlist(
                f"audit sequence {sequence_name}",
                [(grantee, privilege, is_grantable) for _, grantee, privilege, is_grantable in entries],
                {
                    sequence_owner: _SEQUENCE_PRIVILEGES,
                    marker_database_owner_role: _SEQUENCE_PRIVILEGES,
                    runtime_role: _SEQUENCE_PRIVILEGES,
                    migration_role: _SEQUENCE_PRIVILEGES,
                    governance_role: _SEQUENCE_PRIVILEGES,
                },
                frozenset({sequence_owner}),
            )

        default_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT defaults.defaclobjtype,
                   default_owner.rolname,
                   CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_default_acl AS defaults
            JOIN pg_roles AS default_owner ON default_owner.oid = defaults.defaclrole
            JOIN LATERAL aclexplode(defaults.defaclacl) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE defaults.defaclobjtype IN ('r', 'S', 'f')
              AND (
                  defaults.defaclnamespace = 0
                  OR defaults.defaclnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
              )
            """,
        )
        default_privileges = {
            "r": frozenset({"DELETE", "INSERT", "SELECT", "UPDATE"}),
            "S": _SEQUENCE_PRIVILEGES,
            "f": frozenset({"EXECUTE"}),
        }
        for object_type, default_owner, grantee, privilege, is_grantable in default_acl_entries:
            if default_owner not in {migration_role, governance_role}:
                raise AuditRoleBoundaryError("The audit default privileges have an unapproved owner")
            _validate_acl_allowlist(
                f"audit default privileges for {object_type}",
                [(grantee, privilege, is_grantable)],
                {runtime_role: default_privileges[object_type]},
            )

        for target_role in (governance_role, migration_role):
            if _role_reachable(cursor, runtime_role, target_role):
                raise AuditRoleBoundaryError(f"The audit runtime role can reach the protected role {target_role}")
            # PostgreSQL 15 exposes SET ROLE reachability through the USAGE
            # role privilege; newer versions also document it as SET.
            cursor.execute("SELECT pg_has_role(%s, %s, 'USAGE')", [runtime_role, target_role])
            if cursor.fetchone()[0]:
                raise AuditRoleBoundaryError(f"The audit runtime role can SET ROLE to the protected role {target_role}")
        if schema_owner != _POSTGRES_DATABASE_OWNER_ROLE and _role_reachable(cursor, runtime_role, schema_owner):
            raise AuditRoleBoundaryError("The audit runtime role can reach the audit schema owner")
        if schema_owner != _POSTGRES_DATABASE_OWNER_ROLE:
            cursor.execute("SELECT pg_has_role(%s, %s, 'USAGE')", [runtime_role, schema_owner])
            if cursor.fetchone()[0]:
                raise AuditRoleBoundaryError("The audit runtime role can SET ROLE to the audit schema owner")

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
        or not ("before update or delete" in row_trigger_def or "before delete or update" in row_trigger_def)
        or "for each row" not in row_trigger_def
        or "before truncate" not in truncate_trigger_def
        or "for each statement" not in truncate_trigger_def
        or "operation_gateway_audit_append_only()" not in row_trigger_def
        or "operation_gateway_audit_append_only()" not in truncate_trigger_def
    ):
        raise AuditRoleBoundaryError("The audit append-only triggers are missing or disabled")

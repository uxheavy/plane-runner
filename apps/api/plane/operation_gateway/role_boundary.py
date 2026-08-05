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
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
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

    if not _IDENTIFIER.fullmatch(settings.PLANE_AUDIT_SCHEMA or ""):
        raise AuditRoleBoundaryError("The configured audit schema is not a valid provisioned identifier")
    schema_name = settings.PLANE_AUDIT_SCHEMA
    schema_ident = connection.ops.quote_name(schema_name)
    function_regprocedure = f"{schema_name}.operation_gateway_audit_append_only()"
    audit_table_regclass = f"{schema_name}.operation_gateway_audit"
    marker_regclass = f"{schema_name}.{_AUTHORITY_MARKER_TABLE}"

    # Validate the session role independently. A missing protected object must
    # never be reported as a missing runtime role.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user, rolsuper, rolcreaterole, rolcreatedb,
                   rolbypassrls, rolcanlogin, rolinherit
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
        role_row = cursor.fetchone()
    if role_row is None:
        raise AuditRoleBoundaryError("The current database session role does not exist")
    current_user, is_superuser, can_create_roles, can_create_databases, bypasses_rls, can_login, inherits_roles = (
        role_row
    )
    if current_user != runtime_role:
        raise AuditRoleBoundaryError("The database session role is not the configured audit runtime role")
    if is_superuser or can_create_roles or can_create_databases or bypasses_rls:
        raise AuditRoleBoundaryError("The audit runtime role has governance privileges")
    if not can_login or inherits_roles:
        raise AuditRoleBoundaryError("The audit runtime role must be LOGIN NOINHERIT")

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema_name, search_path = cursor.fetchone()
    if current_schema_name != schema_name or search_path != [schema_name]:
        raise AuditRoleBoundaryError("The audit session uses an unapproved schema/search_path")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT rolname, rolcanlogin, rolinherit
            FROM pg_roles
            WHERE rolname = %s
            """,
            [governance_role],
        )
        governance_attributes = cursor.fetchone()
    if governance_attributes != (governance_role, False, False):
        raise AuditRoleBoundaryError("The governance role must be NOLOGIN NOINHERIT")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit
            FROM pg_roles
            WHERE rolname = %s
            """,
            [migration_role],
        )
        migration_attributes = cursor.fetchone()
    if migration_attributes is None:
        raise AuditRoleBoundaryError("The configured migration role does not exist")
    if any(migration_attributes[:4]):
        raise AuditRoleBoundaryError("The migration role has governance privileges")
    if not migration_attributes[4] or migration_attributes[5]:
        raise AuditRoleBoundaryError("The migration role must be LOGIN NOINHERIT")
    provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE
    if not _IDENTIFIER.fullmatch(provisioner_role or ""):
        raise AuditRoleBoundaryError("The provisioned database-owner role is not configured")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_owner.rolname, function_owner.rolname,
                   schema_owner.rolname, schema_owner.oid, database_owner.rolname,
                   audit_function.prosecdef, audit_function.proconfig,
                   audit_function.prosrc,
                   has_function_privilege('public', %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
                   has_function_privilege(%s, %s::regprocedure, 'EXECUTE'),
                   has_schema_privilege(current_user, %s, 'USAGE'),
                   has_schema_privilege(current_user, %s, 'CREATE'),
                   has_table_privilege(current_user, %s::regclass, 'SELECT'),
                   has_table_privilege(current_user, %s::regclass, 'INSERT'),
                   has_table_privilege(current_user, %s::regclass, 'UPDATE'),
                   has_table_privilege(current_user, %s::regclass, 'DELETE'),
                   has_table_privilege(current_user, %s::regclass, 'TRUNCATE'),
                   has_table_privilege(current_user, %s::regclass, 'REFERENCES'),
                   has_table_privilege(current_user, %s::regclass, 'TRIGGER'),
                   has_function_privilege(current_user, %s::regprocedure, 'EXECUTE'),
                   has_database_privilege(current_user, current_database(), 'CREATE')
            FROM pg_class AS audit_table
            JOIN pg_namespace AS audit_schema ON audit_schema.oid = audit_table.relnamespace
            JOIN pg_roles AS table_owner ON table_owner.oid = audit_table.relowner
            JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
            JOIN pg_database AS database_info ON database_info.datname = current_database()
            JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
            JOIN pg_proc AS audit_function
              ON audit_function.oid = to_regprocedure(%s)
            JOIN pg_roles AS function_owner ON function_owner.oid = audit_function.proowner
            WHERE audit_table.oid = to_regclass(%s)
              AND audit_table.relkind = 'r'
            """,
            [
                function_regprocedure,
                runtime_role,
                function_regprocedure,
                migration_role,
                function_regprocedure,
                governance_role,
                function_regprocedure,
                schema_name,
                schema_name,
                *([audit_table_regclass] * 7),
                function_regprocedure,
                function_regprocedure,
                audit_table_regclass,
            ],
        )
        row = cursor.fetchone()

    if row is None:
        raise AuditRoleBoundaryError("The protected audit table/function identity is missing or unapproved")

    (
        table_owner,
        function_owner,
        schema_owner,
        current_schema_owner_oid,
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
    if table_owner != governance_role:
        raise AuditRoleBoundaryError("The audit table is not owned by the governed audit role")
    if function_owner != governance_role:
        raise AuditRoleBoundaryError("The append-only trigger function is not owned by the governed audit role")
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [marker_regclass])
        marker_oid = cursor.fetchone()[0]
    if marker_oid is None:
        raise AuditRoleBoundaryError("The provisioned audit authority marker has an unapproved object identity")

    marker_ident = connection.ops.quote_name(_AUTHORITY_MARKER_TABLE)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT marker.version, marker.database_owner_oid, marker.database_owner_role,
                   marker.schema_name, marker.schema_owner_oid, marker.schema_owner_role,
                   marker_owner.rolname,
                   database_info.datdba, database_owner.rolname
            FROM {schema_ident}.{marker_ident} AS marker
            JOIN pg_class AS marker_table
              ON marker_table.oid = to_regclass(%s)
            JOIN pg_namespace AS marker_schema ON marker_schema.oid = marker_table.relnamespace
            JOIN pg_roles AS marker_owner ON marker_owner.oid = marker_table.relowner
            JOIN pg_database AS database_info ON database_info.datname = current_database()
            JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
            WHERE marker_schema.nspname = %s
              AND marker_table.relkind = 'r'
              AND marker.marker_id = TRUE
            """,
            [marker_regclass, schema_name],
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
        or marker_owner != governance_role
        or marker_schema_name != schema_name
        or marker_schema_owner_oid != current_schema_owner_oid
        or marker_schema_owner_role != schema_owner
        or marker_database_owner_oid != current_database_owner_oid
        or marker_database_owner_role != current_database_owner_role
        or not marker_schema_owner_oid
        or not marker_schema_owner_role
    ):
        raise AuditRoleBoundaryError("The provisioned audit authority marker does not match the database topology")
    if database_owner != provisioner_role or schema_owner not in {provisioner_role, _POSTGRES_DATABASE_OWNER_ROLE}:
        raise AuditRoleBoundaryError("The database and audit schema owners do not match the provisioned topology")
    with connection.cursor() as cursor:
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
    with connection.cursor() as cursor:
        marker_acl_entries = _fetch_acl_entries(
            cursor,
            """
            SELECT CASE WHEN exploded.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS marker_table
            JOIN LATERAL aclexplode(marker_table.relacl) AS exploded ON TRUE
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE marker_table.oid = to_regclass(%s)
            """,
            [marker_regclass],
        )
        _validate_acl_allowlist(
            "authority marker",
            marker_acl_entries,
            {
                runtime_role: frozenset({"SELECT"}),
                migration_role: frozenset({"SELECT"}),
            },
        )
        if _role_reachable(cursor, migration_role, governance_role):
            raise AuditRoleBoundaryError("The migration role can reach the governance role")

    # PostgreSQL 15+ owns a fresh public schema by pg_database_owner. The
    # database owner is separately provisioned and explicitly configured; the
    # marker can record it but cannot enlarge this allowlist after tampering.
    approved_schema_owners = frozenset({provisioner_role, _POSTGRES_DATABASE_OWNER_ROLE})
    if marker_database_owner_role in {runtime_role, migration_role, governance_role} or marker_schema_owner_role in {
        runtime_role,
        migration_role,
        governance_role,
    }:
        raise AuditRoleBoundaryError(
            "The database and audit schema owners must be separate from runtime and migration roles"
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
            WHERE audit_table.oid = to_regclass(%s)
              AND audit_table.relkind = 'r'
            """,
            [audit_table_regclass],
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
            WHERE audit_schema.nspname = %s
            """,
            [schema_name],
        )
        schema_acl_allowlist = {
            runtime_role: frozenset({"USAGE"}),
            migration_role: frozenset({"CREATE", "USAGE"}),
            governance_role: frozenset({"USAGE"}),
            _POSTGRES_DATABASE_OWNER_ROLE: frozenset({"CREATE", "USAGE"}),
            provisioner_role: frozenset({"CREATE", "USAGE"}),
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
            WHERE audit_schema.nspname = %s
              AND audit_sequence.relkind = 'S'
              AND audit_sequence.relname LIKE 'operation_gateway_audit%%'
            """,
            [schema_name],
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
                  OR defaults.defaclnamespace = (SELECT oid FROM pg_namespace WHERE nspname = %s)
              )
            """,
            [schema_name],
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
              WHERE pg_class.oid = to_regclass(%s)
              AND NOT pg_trigger.tgisinternal
            ORDER BY tgname
            """,
            [audit_table_regclass],
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

"""Restore a 0126 catalog snapshot using the authenticated provisioner."""

from __future__ import annotations

import json
import re

from django.conf import settings


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
CATALOG_SNAPSHOT_TABLE = "plane_0126_audit_catalog_snapshot"
CATALOG_SNAPSHOT_VERSION = 1


def _snapshot_object_sql(connection, schema_name, object_info):
    schema_ident = connection.ops.quote_name(schema_name)
    name_ident = connection.ops.quote_name(object_info["name"])
    qualified = f"{schema_ident}.{name_ident}"
    if object_info["kind"] == "function":
        return f"{qualified}({object_info['identity_arguments']})"
    return qualified


def _sql_grantee(connection, grantee):
    return "PUBLIC" if grantee == "PUBLIC" else connection.ops.quote_name(grantee)


def _restore_acl_entries(cursor, connection, target_type, target_sql, entries, known_grantees):
    # PUBLIC is never restored by a downgrade. The 0125 predecessor contract
    # is deliberately safe for every protected object kind, even when an
    # older database carried PostgreSQL's broad default ACLs.
    entries = [entry for entry in entries if entry["grantee"] != "PUBLIC"]
    grantees = set(known_grantees)
    grantees.update(entry["grantee"] for entry in entries)
    for grantee in sorted(grantees):
        cursor.execute(f"REVOKE ALL PRIVILEGES ON {target_type} {target_sql} FROM {_sql_grantee(connection, grantee)}")
    grouped = {}
    for entry in entries:
        grouped.setdefault((entry["grantee"], entry["is_grantable"]), set()).add(entry["privilege"])
    for (grantee, is_grantable), privileges in sorted(grouped.items()):
        grant_option = " WITH GRANT OPTION" if is_grantable else ""
        cursor.execute(
            f"GRANT {', '.join(sorted(privileges))} ON {target_type} {target_sql} "
            f"TO {_sql_grantee(connection, grantee)}{grant_option}"
        )


def _restore_default_privileges(cursor, connection, schema_name, snapshot, migration_role, runtime_role):
    object_types = {"r": "TABLES", "S": "SEQUENCES", "f": "FUNCTIONS"}
    defaults = {
        default_acl["object_type"]: default_acl
        for default_acl in snapshot["default_privileges"]
        if default_acl["owner"] == migration_role
    }
    schema_ident = connection.ops.quote_name(schema_name)
    owner_ident = connection.ops.quote_name(migration_role)
    for object_type, sql_object_type in object_types.items():
        entries = [entry for entry in defaults.get(object_type, {}).get("acl", []) if entry["grantee"] != "PUBLIC"]
        grantees = {"PUBLIC", runtime_role}
        grantees.update(entry["grantee"] for entry in entries)
        for grantee in sorted(grantees):
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner_ident} IN SCHEMA {schema_ident} "
                f"REVOKE ALL ON {sql_object_type} FROM {_sql_grantee(connection, grantee)}"
            )
        grouped = {}
        for entry in entries:
            grouped.setdefault((entry["grantee"], entry["is_grantable"]), set()).add(entry["privilege"])
        for (grantee, is_grantable), privileges in sorted(grouped.items()):
            grant_option = " WITH GRANT OPTION" if is_grantable else ""
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner_ident} IN SCHEMA {schema_ident} "
                f"GRANT {', '.join(sorted(privileges))} ON {sql_object_type} "
                f"TO {_sql_grantee(connection, grantee)}{grant_option}"
            )


def _restore_function_configuration(cursor, connection, schema_name, object_info):
    function_sql = _snapshot_object_sql(connection, schema_name, object_info)
    security = "SECURITY DEFINER" if object_info.get("security_definer") else "SECURITY INVOKER"
    cursor.execute(f"ALTER FUNCTION {function_sql} {security}")
    cursor.execute(f"ALTER FUNCTION {function_sql} RESET ALL")
    for config in object_info.get("config") or []:
        key, separator, value = config.partition("=")
        if not separator or not re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            raise RuntimeError("Invalid 0126 function configuration snapshot")
        cursor.execute("SELECT quote_literal(%s)", [value])
        quoted_value = cursor.fetchone()[0]
        cursor.execute(f"ALTER FUNCTION {function_sql} SET {key} = {quoted_value}")


def restore_audit_catalog_snapshot(connection, *, runtime_role, governance_role, migration_role, provisioner_role):
    with connection.cursor() as cursor:
        schema_name = settings.PLANE_AUDIT_SCHEMA
        if not ROLE_NAME.fullmatch(schema_name or ""):
            raise RuntimeError("PLANE_AUDIT_SCHEMA must be a simple PostgreSQL identifier")
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema, search_path = cursor.fetchone()
        if current_schema != schema_name or search_path != [schema_name]:
            raise RuntimeError("Operation Gateway audit uses an unapproved schema/search_path")
        schema_ident = connection.ops.quote_name(schema_name)
        snapshot_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_TABLE)
        cursor.execute(f"SELECT snapshot FROM {schema_ident}.{snapshot_ident}")
        row = cursor.fetchone()
        snapshot = row[0] if row is not None else None
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        if not isinstance(snapshot, dict) or snapshot.get("version") != CATALOG_SNAPSHOT_VERSION:
            raise RuntimeError("Missing or invalid 0126 audit catalog snapshot")
        if snapshot.get("schema", {}).get("name") != schema_name:
            raise RuntimeError("0126 audit catalog snapshot belongs to another schema")

        owner_roles = {
            object_info["owner"]
            for object_info in snapshot["objects"]
            if object_info["kind"] in {"table", "function"} and object_info["name"] == "operation_gateway_audit"
        }
        owner_roles.update(
            object_info["owner"]
            for object_info in snapshot["objects"]
            if object_info["kind"] == "function" and object_info["name"] == "operation_gateway_audit_append_only"
        )
        temporary_owner_memberships = set()
        for owner_role in sorted(owner_roles - {provisioner_role}):
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_auth_members AS memberships
                    JOIN pg_roles AS granted_role ON granted_role.oid = memberships.roleid
                    JOIN pg_roles AS member_role ON member_role.oid = memberships.member
                    WHERE granted_role.rolname = %s
                      AND member_role.rolname = %s
                )
                """,
                [owner_role, provisioner_role],
            )
            if not cursor.fetchone()[0]:
                temporary_owner_memberships.add(owner_role)
                cursor.execute(
                    f"GRANT {connection.ops.quote_name(owner_role)} TO {connection.ops.quote_name(provisioner_role)}"
                )

        for object_info in snapshot["objects"]:
            if object_info["kind"] == "table" and object_info["name"] == "operation_gateway_audit":
                target_sql = _snapshot_object_sql(connection, schema_name, object_info)
                cursor.execute(f"ALTER TABLE {target_sql} OWNER TO {connection.ops.quote_name(object_info['owner'])}")
            elif object_info["kind"] == "function" and object_info["name"] == "operation_gateway_audit_append_only":
                target_sql = _snapshot_object_sql(connection, schema_name, object_info)
                cursor.execute(
                    f"ALTER FUNCTION {target_sql} OWNER TO {connection.ops.quote_name(object_info['owner'])}"
                )
                _restore_function_configuration(cursor, connection, schema_name, object_info)

        _restore_acl_entries(
            cursor,
            connection,
            "SCHEMA",
            schema_ident,
            snapshot["schema"]["acl"],
            {"PUBLIC", runtime_role, migration_role, governance_role},
        )
        for object_info in snapshot["objects"]:
            target_type = {
                "table": "TABLE",
                "sequence": "SEQUENCE",
                "function": "FUNCTION",
            }[object_info["kind"]]
            _restore_acl_entries(
                cursor,
                connection,
                target_type,
                _snapshot_object_sql(connection, schema_name, object_info),
                object_info["acl"],
                {"PUBLIC", runtime_role, migration_role, governance_role},
            )
        _restore_default_privileges(cursor, connection, schema_name, snapshot, migration_role, runtime_role)

        affected_memberships = {
            (governance_role, migration_role),
            (governance_role, runtime_role),
            (migration_role, runtime_role),
        }
        for role, member in affected_memberships:
            cursor.execute(f"REVOKE {connection.ops.quote_name(role)} FROM {connection.ops.quote_name(member)}")
        for membership in snapshot["memberships"]:
            role = membership["role"]
            member = membership["member"]
            if (role, member) not in affected_memberships:
                continue
            admin_option = " WITH ADMIN OPTION" if membership["admin_option"] else ""
            cursor.execute(
                f"GRANT {connection.ops.quote_name(role)} TO {connection.ops.quote_name(member)}{admin_option}"
            )

        for owner_role in sorted(temporary_owner_memberships):
            cursor.execute(
                f"REVOKE {connection.ops.quote_name(owner_role)} FROM {connection.ops.quote_name(provisioner_role)}"
            )

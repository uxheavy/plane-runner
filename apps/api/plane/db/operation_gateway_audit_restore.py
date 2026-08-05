"""Restore a 0129 catalog snapshot using the authenticated provisioner."""

from __future__ import annotations

import hashlib
import hmac
import json
import re

from django.conf import settings


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
CATALOG_SNAPSHOT_TABLE = "plane_0129_audit_catalog_snapshot"
CATALOG_SNAPSHOT_BINDING_TABLE = "plane_0129_audit_catalog_snapshot_binding"
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


def _canonical_snapshot_digest(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _role_identity(cursor, role_name):
    cursor.execute("SELECT oid::bigint, rolname FROM pg_roles WHERE rolname = %s", [role_name])
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Missing role in the 0129 audit catalog binding: {role_name}")
    return {"oid": int(row[0]), "name": row[1]}


def _relation_identity(cursor, schema_name, object_name):
    cursor.execute(
        """
        SELECT object_info.oid::bigint, object_info.relname,
               object_owner.oid::bigint, object_owner.rolname
        FROM pg_class AS object_info
        JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
        JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
        WHERE object_info.oid = to_regclass(%s)
          AND object_schema.nspname = %s
        """,
        [f"{schema_name}.{object_name}", schema_name],
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Missing object in the 0129 audit catalog binding: {schema_name}.{object_name}")
    oid, name, owner_oid, owner_name = row
    return {"oid": int(oid), "name": name, "owner": {"oid": int(owner_oid), "name": owner_name}}


def _function_identity(cursor, schema_name, function_name):
    cursor.execute(
        """
        SELECT object_info.oid::bigint, object_info.proname,
               pg_get_function_identity_arguments(object_info.oid),
               function_owner.oid::bigint, function_owner.rolname
        FROM pg_proc AS object_info
        JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
        JOIN pg_roles AS function_owner ON function_owner.oid = object_info.proowner
        WHERE object_info.oid = to_regprocedure(%s)
          AND object_schema.nspname = %s
        """,
        [f"{schema_name}.{function_name}()", schema_name],
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Missing function in the 0129 audit catalog binding: {schema_name}.{function_name}")
    oid, name, identity_arguments, owner_oid, owner_name = row
    return {
        "oid": int(oid),
        "name": name,
        "identity_arguments": identity_arguments,
        "owner": {"oid": int(owner_oid), "name": owner_name},
    }


def _live_topology(cursor, schema_name, *, runtime_role, governance_role, migration_role, provisioner_role):
    cursor.execute(
        """
        SELECT database_info.oid::bigint, database_info.datname,
               database_owner.oid::bigint, database_owner.rolname
        FROM pg_database AS database_info
        JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
        WHERE database_info.datname = current_database()
        """
    )
    database = cursor.fetchone()
    cursor.execute(
        """
        SELECT schema_info.oid::bigint, schema_info.nspname,
               schema_owner.oid::bigint, schema_owner.rolname
        FROM pg_namespace AS schema_info
        JOIN pg_roles AS schema_owner ON schema_owner.oid = schema_info.nspowner
        WHERE schema_info.nspname = %s
        """,
        [schema_name],
    )
    schema = cursor.fetchone()
    if database is None or schema is None:
        raise RuntimeError("The 0129 audit catalog topology is missing")
    database_oid, database_name, database_owner_oid, database_owner_name = database
    schema_oid, actual_schema_name, schema_owner_oid, schema_owner_name = schema
    roles = {
        "runtime": _role_identity(cursor, runtime_role),
        "governance": _role_identity(cursor, governance_role),
        "migration": _role_identity(cursor, migration_role),
        "provisioner": _role_identity(cursor, provisioner_role),
    }
    return {
        "database": {
            "oid": int(database_oid),
            "name": database_name,
            "owner": {"oid": int(database_owner_oid), "name": database_owner_name},
        },
        "schema": {
            "oid": int(schema_oid),
            "name": actual_schema_name,
            "owner": {"oid": int(schema_owner_oid), "name": schema_owner_name},
        },
        "roles": roles,
        "objects": {
            "snapshot": _relation_identity(cursor, schema_name, CATALOG_SNAPSHOT_TABLE),
            "binding": _relation_identity(cursor, schema_name, CATALOG_SNAPSHOT_BINDING_TABLE),
            "audit_table": _relation_identity(cursor, schema_name, "operation_gateway_audit"),
            "audit_function": _function_identity(cursor, schema_name, "operation_gateway_audit_append_only"),
        },
    }


def _assert_snapshot_payload(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "version",
        "schema",
        "objects",
        "default_privileges",
        "memberships",
    }:
        raise RuntimeError("Missing or invalid 0129 audit catalog snapshot")
    if snapshot["version"] != CATALOG_SNAPSHOT_VERSION:
        raise RuntimeError("Missing or invalid 0129 audit catalog snapshot")
    schema = snapshot["schema"]
    if not isinstance(schema, dict) or set(schema) != {"name", "owner", "acl"} or not isinstance(schema["acl"], list):
        raise RuntimeError("Invalid 0129 audit catalog schema snapshot")
    if not isinstance(snapshot["objects"], list):
        raise RuntimeError("Invalid 0129 audit catalog object snapshot")
    seen_objects = set()
    for object_info in snapshot["objects"]:
        if not isinstance(object_info, dict) or object_info.get("kind") not in {"table", "sequence", "function"}:
            raise RuntimeError("Invalid 0129 audit catalog object snapshot")
        key = (object_info["kind"], object_info.get("name"), object_info.get("identity_arguments"))
        if key in seen_objects:
            raise RuntimeError("Duplicate 0129 audit catalog object snapshot")
        seen_objects.add(key)
        required = {"kind", "name", "owner", "acl"}
        if object_info["kind"] == "function":
            required.update({"identity_arguments", "security_definer", "config"})
            if not isinstance(object_info.get("security_definer"), bool):
                raise RuntimeError("Invalid 0129 audit catalog function snapshot")
            if object_info.get("config") is not None and not isinstance(object_info["config"], list):
                raise RuntimeError("Invalid 0129 audit catalog function snapshot")
            for config in object_info.get("config") or []:
                key_name, separator, _ = config.partition("=") if isinstance(config, str) else ("", "", "")
                if not separator or not re.fullmatch(r"[a-z_][a-z0-9_]*", key_name):
                    raise RuntimeError("Invalid 0129 function configuration snapshot")
        if not required <= object_info.keys() or not isinstance(object_info["acl"], list):
            raise RuntimeError("Invalid 0129 audit catalog object snapshot")
    if not isinstance(snapshot["default_privileges"], list) or not isinstance(snapshot["memberships"], list):
        raise RuntimeError("Invalid 0129 audit catalog snapshot")
    for membership in snapshot["memberships"]:
        if (
            not isinstance(membership, dict)
            or set(membership) != {"role", "member", "admin_option"}
            or not isinstance(membership["admin_option"], bool)
        ):
            raise RuntimeError("Invalid 0129 audit catalog membership snapshot")


def _snapshot_membership_reaches(memberships, member_role, target_role):
    graph = {}
    for membership in memberships:
        graph.setdefault(membership["member"], set()).add(membership["role"])
    pending = [member_role]
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target_role:
            return True
        pending.extend(graph.get(current, ()))
    return False


def _assert_no_governance_membership(cursor, migration_role, governance_role):
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
        [migration_role, governance_role],
    )
    if cursor.fetchone()[0]:
        raise RuntimeError("The migration role retains governance membership")


def verify_audit_catalog_snapshot(
    connection,
    *,
    runtime_role,
    governance_role,
    migration_role,
    provisioner_role,
):
    """Verify the provisioner-owned snapshot and topology before any restore SQL."""

    with connection.cursor() as cursor:
        schema_name = settings.PLANE_AUDIT_SCHEMA
        if not ROLE_NAME.fullmatch(schema_name or ""):
            raise RuntimeError("PLANE_AUDIT_SCHEMA must be a simple PostgreSQL identifier")
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema, search_path = cursor.fetchone()
        if current_schema != schema_name or search_path != [schema_name]:
            raise RuntimeError("Operation Gateway audit uses an unapproved schema/search_path")
        cursor.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
        current_user, is_superuser = cursor.fetchone()
        if current_user != provisioner_role and not is_superuser:
            raise RuntimeError("The 0129 audit catalog can only be verified by the provisioner")
        schema_ident = connection.ops.quote_name(schema_name)
        snapshot_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_TABLE)
        binding_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_BINDING_TABLE)
        cursor.execute(f"SELECT snapshot FROM {schema_ident}.{snapshot_ident} WHERE snapshot_id = TRUE")
        snapshot_row = cursor.fetchone()
        cursor.execute(
            f"SELECT version, snapshot_digest, topology FROM {schema_ident}.{binding_ident} WHERE binding_id = TRUE"
        )
        binding_row = cursor.fetchone()
        if snapshot_row is None or binding_row is None:
            raise RuntimeError("Missing 0129 audit catalog snapshot binding")
        snapshot = snapshot_row[0]
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError as error:
                raise RuntimeError("Invalid 0129 audit catalog snapshot JSON") from error
        _assert_snapshot_payload(snapshot)
        binding_version, snapshot_digest, expected_topology = binding_row
        if isinstance(expected_topology, str):
            try:
                expected_topology = json.loads(expected_topology)
            except json.JSONDecodeError as error:
                raise RuntimeError("Invalid 0129 audit catalog snapshot binding") from error
        if (
            binding_version != CATALOG_SNAPSHOT_VERSION
            or not isinstance(snapshot_digest, str)
            or not isinstance(expected_topology, dict)
        ):
            raise RuntimeError("Invalid 0129 audit catalog snapshot binding")
        if snapshot["schema"]["name"] != schema_name:
            raise RuntimeError("0129 audit catalog snapshot belongs to another schema")
        if not hmac.compare_digest(snapshot_digest, _canonical_snapshot_digest(snapshot)):
            raise RuntimeError("The 0129 audit catalog snapshot digest does not match its binding")
        live_topology = _live_topology(
            cursor,
            schema_name,
            runtime_role=runtime_role,
            governance_role=governance_role,
            migration_role=migration_role,
            provisioner_role=provisioner_role,
        )
        if expected_topology != live_topology:
            raise RuntimeError("The 0129 audit catalog topology does not match its binding")
        if any(
            (
                live_topology["database"]["owner"] != live_topology["roles"]["provisioner"],
                live_topology["schema"]["owner"]["name"] not in {provisioner_role, "pg_database_owner"},
                live_topology["objects"]["snapshot"]["owner"] != live_topology["roles"]["provisioner"],
                live_topology["objects"]["binding"]["owner"] != live_topology["roles"]["provisioner"],
                live_topology["objects"]["audit_table"]["owner"] != live_topology["roles"]["governance"],
                live_topology["objects"]["audit_function"]["owner"] != live_topology["roles"]["governance"],
            )
        ):
            raise RuntimeError("The 0129 audit catalog binding does not describe the provisioned authority")
        _assert_no_governance_membership(cursor, migration_role, governance_role)
        if _snapshot_membership_reaches(snapshot["memberships"], migration_role, governance_role):
            raise RuntimeError("The snapshot would restore migration governance membership")
        return snapshot


def _restore_acl_entries(cursor, connection, target_type, target_sql, entries, known_grantees):
    # PUBLIC is never restored by a downgrade. The 0128 predecessor contract
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
            raise RuntimeError("Invalid 0129 function configuration snapshot")
        cursor.execute("SELECT quote_literal(%s)", [value])
        quoted_value = cursor.fetchone()[0]
        cursor.execute(f"ALTER FUNCTION {function_sql} SET {key} = {quoted_value}")


def restore_audit_catalog_snapshot(connection, *, runtime_role, governance_role, migration_role, provisioner_role):
    with connection.cursor() as cursor:
        schema_name = settings.PLANE_AUDIT_SCHEMA
        snapshot = verify_audit_catalog_snapshot(
            connection,
            runtime_role=runtime_role,
            governance_role=governance_role,
            migration_role=migration_role,
            provisioner_role=provisioner_role,
        )
        schema_ident = connection.ops.quote_name(schema_name)

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

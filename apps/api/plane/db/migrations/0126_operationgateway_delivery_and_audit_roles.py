"""Close durable publication, effect-idempotency, trigger, and role gaps."""

import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.db import migrations, models


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
PUBLICATION_NAMESPACE = uuid.UUID("8a1b4fd8-49a5-54ad-a49e-7f2e0c1a3f1c")
REVERSE_MARKER = "__plane_0126_reverse__"
CATALOG_SNAPSHOT_TABLE = "plane_0126_audit_catalog_snapshot"
CATALOG_SNAPSHOT_BINDING_TABLE = "plane_0126_audit_catalog_snapshot_binding"
CATALOG_SNAPSHOT_VERSION = 1

CREATE_APPEND_ONLY_TRIGGERS = """
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_trigger ON operation_gateway_audit;
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_row_trigger ON operation_gateway_audit;
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_truncate_trigger ON operation_gateway_audit;

CREATE OR REPLACE FUNCTION operation_gateway_audit_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'operation gateway audit records are append-only'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER operation_gateway_audit_append_only_row_trigger
BEFORE UPDATE OR DELETE ON operation_gateway_audit
FOR EACH ROW
EXECUTE FUNCTION operation_gateway_audit_append_only();

CREATE TRIGGER operation_gateway_audit_append_only_truncate_trigger
BEFORE TRUNCATE ON operation_gateway_audit
FOR EACH STATEMENT
EXECUTE FUNCTION operation_gateway_audit_append_only();
"""

DROP_APPEND_ONLY_TRIGGERS = """
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_row_trigger ON operation_gateway_audit;
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_truncate_trigger ON operation_gateway_audit;
DROP TRIGGER IF EXISTS operation_gateway_audit_append_only_trigger ON operation_gateway_audit;
DROP FUNCTION IF EXISTS operation_gateway_audit_append_only();
"""

RESTORE_APPEND_ONLY_TRIGGER = """
CREATE OR REPLACE FUNCTION operation_gateway_audit_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'operation gateway audit records are append-only'
        USING ERRCODE = '55000';
END;
$$;

REVOKE EXECUTE ON FUNCTION operation_gateway_audit_append_only() FROM PUBLIC;

CREATE TRIGGER operation_gateway_audit_append_only_trigger
BEFORE UPDATE OR DELETE ON operation_gateway_audit
FOR EACH ROW
EXECUTE FUNCTION operation_gateway_audit_append_only();
"""


def split_legacy_webhook_intents(apps, schema_editor):
    """Convert pre-0126 fan-out rows without claiming delivery.

    The reverse migration stores a lossless marker in the old JSON payload. It
    is consumed here before looking at current active webhooks, so a
    0125 -> 0126 -> 0125 -> 0126 round trip restores the original target set,
    durable keys, results, ambiguity, and dispatch markers.
    """

    Publication = apps.get_model("db", "OperationGatewayPublication")
    Webhook = apps.get_model("db", "Webhook")
    table_name = schema_editor.quote_name(Publication._meta.db_table)
    legacy_publications = Publication.objects.filter(kind="webhook", target_id__isnull=True).order_by("id")
    for publication in legacy_publications:
        payload = publication.payload if isinstance(publication.payload, dict) else {}
        marker = payload.get(REVERSE_MARKER)
        if isinstance(marker, dict) and marker.get("version") == 1:
            _restore_reversed_webhook_rows(Publication, publication, marker, schema_editor)
            continue
        targets = list(
            Webhook.objects.filter(
                workspace_id=publication.idempotency.workspace_id,
                is_active=True,
                issue=True,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        was_ambiguous = publication.state in ("running", "succeeded")
        state = "outcome_unknown" if was_ambiguous else publication.state
        delivery_result = (
            {
                "state": "outcome_unknown",
                "reason": "Legacy fan-out publication had no per-target delivery receipt",
            }
            if was_ambiguous
            else publication.delivery_result
        )
        if not targets:
            new_id = _stable_publication_id(publication.idempotency_id, "none")
            _rewrite_publication_primary_key(schema_editor, table_name, publication.id, new_id)
            publication.id = new_id
            payload.pop(REVERSE_MARKER, None)
            publication.payload = payload
            publication.state = state
            publication.dispatch_started = was_ambiguous
            publication.lease_until = None
            publication.published_at = None
            publication.delivery_result = delivery_result
            publication.save(
                update_fields=[
                    "state",
                    "dispatch_started",
                    "lease_until",
                    "published_at",
                    "delivery_result",
                    "updated_at",
                ]
            )
            continue

        for index, target_id in enumerate(targets):
            target_payload = {**payload, "webhook_id": str(target_id)}
            publication_key = f"{publication.idempotency_id}:webhook:{target_id}"
            target_publication_id = _stable_publication_id(publication.idempotency_id, str(target_id))
            if index == 0:
                _rewrite_publication_primary_key(schema_editor, table_name, publication.id, target_publication_id)
                publication.id = target_publication_id
                publication.target_id = target_id
                publication.publication_key = publication_key
                publication.payload = target_payload
                publication.state = state
                publication.dispatch_started = was_ambiguous
                publication.lease_until = None
                publication.published_at = None
                publication.delivery_result = delivery_result
                publication.save(
                    update_fields=[
                        "target_id",
                        "publication_key",
                        "payload",
                        "state",
                        "dispatch_started",
                        "lease_until",
                        "published_at",
                        "delivery_result",
                        "updated_at",
                    ]
                )
            else:
                Publication.objects.create(
                    id=target_publication_id,
                    idempotency_id=publication.idempotency_id,
                    invocation_id=publication.invocation_id,
                    kind="webhook",
                    target_id=target_id,
                    publication_key=publication_key,
                    payload=target_payload,
                    state=state,
                    attempts=publication.attempts,
                    last_error=publication.last_error,
                    delivery_result=delivery_result,
                    dispatch_started=was_ambiguous,
                    lease_until=None,
                    published_at=None,
                )


def merge_webhook_intents_for_reverse(apps, schema_editor):
    """Restore one legacy row with a lossless target/state marker."""

    Publication = apps.get_model("db", "OperationGatewayPublication")
    groups = {}
    for publication in Publication.objects.filter(kind="webhook").order_by("id"):
        groups.setdefault(publication.idempotency_id, []).append(publication)

    for idempotency_id, publications in groups.items():
        first = publications[0]
        payload = copy.deepcopy(first.payload) if isinstance(first.payload, dict) else {}
        reverse_rows = [_serialize_webhook_publication(publication) for publication in publications]
        payload.pop("webhook_id", None)
        payload[REVERSE_MARKER] = {"version": 1, "rows": reverse_rows}
        first.target_id = None
        first.publication_key = f"{idempotency_id}:webhook"
        first.payload = payload
        first.state = (
            "failed"
            if any(_legacy_state(publication) == "failed" for publication in publications)
            else _legacy_state(first)
        )
        first.dispatch_started = False
        first.lease_until = None
        first.published_at = None
        first.delivery_result = None
        first.save(
            update_fields=[
                "target_id",
                "publication_key",
                "payload",
                "state",
                "dispatch_started",
                "lease_until",
                "published_at",
                "delivery_result",
                "updated_at",
            ]
        )
        for publication in publications[1:]:
            publication.delete()


def _rewrite_publication_primary_key(schema_editor, table_name: str, old_id, new_id) -> None:
    """Rewrite a legacy PK in-place without Django's update_fields PK guard."""

    if old_id == new_id:
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT 1 FROM {table_name} WHERE id = %s FOR UPDATE", [old_id])
        if cursor.fetchone() is None:
            raise RuntimeError(f"Legacy publication {old_id} disappeared during migration")
        cursor.execute(f"SELECT 1 FROM {table_name} WHERE id = %s", [new_id])
        if cursor.fetchone() is not None:
            raise RuntimeError(f"Deterministic publication id {new_id} already exists")
        cursor.execute(f"UPDATE {table_name} SET id = %s WHERE id = %s", [new_id, old_id])
        if cursor.rowcount != 1:
            raise RuntimeError(f"Legacy publication {old_id} was not rewritten")


def _stable_publication_id(idempotency_id, target_id: str) -> uuid.UUID:
    return uuid.uuid5(PUBLICATION_NAMESPACE, f"{idempotency_id}:webhook:{target_id}")


def _legacy_state(publication) -> str:
    """Map to 0125 without making an ambiguous dispatch runnable."""

    if publication.state == "succeeded" and not publication.dispatch_started:
        return "succeeded"
    if publication.state == "pending" and not publication.dispatch_started:
        return "pending"
    if publication.state == "running" and not publication.dispatch_started:
        return "running"
    # 0125 has no outcome_unknown/retryable state. ``failed`` is the only
    # non-runnable representation; the marker restores the exact 0126 state
    # when the migration is applied forward again.
    return "failed"


def _serialize_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _serialize_webhook_publication(publication) -> dict:
    return {
        "id": str(publication.id),
        "idempotency_id": str(publication.idempotency_id),
        "invocation_id": str(publication.invocation_id),
        "kind": publication.kind,
        "target_id": str(publication.target_id) if publication.target_id else None,
        "publication_key": publication.publication_key,
        "payload": copy.deepcopy(publication.payload) if isinstance(publication.payload, dict) else {},
        "state": publication.state,
        "attempts": publication.attempts,
        "last_error": publication.last_error,
        "delivery_result": publication.delivery_result,
        "dispatch_started": publication.dispatch_started,
        "lease_until": _serialize_datetime(publication.lease_until),
        "published_at": _serialize_datetime(publication.published_at),
        "created_at": _serialize_datetime(publication.created_at),
        "updated_at": _serialize_datetime(publication.updated_at),
    }


def _parse_datetime(value):
    if not isinstance(value, str):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _restore_reversed_webhook_rows(Publication, legacy_publication, marker: dict, schema_editor) -> None:
    rows = marker.get("rows")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Invalid 0126 reverse marker for webhook publication")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RuntimeError("Invalid 0126 reverse marker row")
        target_id = row.get("target_id")
        created_at = _parse_datetime(row.get("created_at"))
        updated_at = _parse_datetime(row.get("updated_at"))
        if created_at is None or updated_at is None:
            raise RuntimeError("Invalid 0126 reverse marker row timestamps")
        defaults = {
            "idempotency_id": uuid.UUID(row["idempotency_id"]),
            "invocation_id": uuid.UUID(row["invocation_id"]),
            "kind": row.get("kind", "webhook"),
            "target_id": uuid.UUID(target_id) if target_id else None,
            "publication_key": row["publication_key"],
            "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
            "state": row.get("state", "pending"),
            "attempts": row.get("attempts", 0),
            "last_error": row.get("last_error", ""),
            "delivery_result": row.get("delivery_result"),
            "dispatch_started": bool(row.get("dispatch_started", False)),
            "lease_until": _parse_datetime(row.get("lease_until")),
            "published_at": _parse_datetime(row.get("published_at")),
        }
        if index == 0:
            restored = legacy_publication
            restored.id = uuid.UUID(row["id"])
            for field, value in defaults.items():
                setattr(restored, field, value)
            restored.save()
            restored_id = restored.id
        else:
            restored_id = Publication.objects.create(id=uuid.UUID(row["id"]), **defaults).id
        _restore_publication_timestamps(
            schema_editor,
            restored_id,
            created_at,
            updated_at,
        )


def _restore_publication_timestamps(schema_editor, publication_id, created_at, updated_at) -> None:
    table_name = schema_editor.quote_name("operation_gateway_publication")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table_name} SET created_at = %s, updated_at = %s WHERE id = %s",
            [created_at, updated_at, publication_id],
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Publication {publication_id} was not restored")


def _acl_entry(grantor, grantee, privilege, is_grantable):
    return {
        "grantor": grantor,
        "grantee": "PUBLIC" if grantee is None else grantee,
        "privilege": privilege,
        "is_grantable": bool(is_grantable),
    }


def _canonical_snapshot_digest(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _role_identity(cursor, role_name):
    cursor.execute("SELECT oid::bigint, rolname FROM pg_roles WHERE rolname = %s", [role_name])
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Missing role in the 0126 audit catalog binding: {role_name}")
    return {"oid": int(row[0]), "name": row[1]}


def _object_identity(cursor, schema_name, object_name, *, kind, identity_arguments=None):
    if kind == "table":
        cursor.execute(
            """
            SELECT object_info.oid::bigint, object_info.relname,
                   object_owner.oid::bigint, object_owner.rolname
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
            WHERE object_schema.nspname = %s
              AND object_info.relname = %s
              AND object_info.relkind = 'r'
            """,
            [schema_name, object_name],
        )
    else:
        cursor.execute(
            """
            SELECT object_info.oid::bigint, object_info.proname,
                   pg_get_function_identity_arguments(object_info.oid),
                   function_owner.oid::bigint, function_owner.rolname
            FROM pg_proc AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
            JOIN pg_roles AS function_owner ON function_owner.oid = object_info.proowner
            WHERE object_schema.nspname = %s
              AND object_info.proname = %s
              AND pg_get_function_identity_arguments(object_info.oid) = %s
            """,
            [schema_name, object_name, identity_arguments or ""],
        )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Missing object in the 0126 audit catalog binding: {schema_name}.{object_name}")
    if kind == "table":
        oid, name, owner_oid, owner_name = row
        return {"oid": int(oid), "name": name, "owner": {"oid": int(owner_oid), "name": owner_name}}
    oid, name, actual_arguments, owner_oid, owner_name = row
    return {
        "oid": int(oid),
        "name": name,
        "identity_arguments": actual_arguments,
        "owner": {"oid": int(owner_oid), "name": owner_name},
    }


def _capture_audit_catalog_binding(
    cursor,
    *,
    schema_name,
    runtime_role,
    governance_role,
    migration_role,
    provisioner_role,
):
    cursor.execute(
        """
        SELECT database_info.oid::bigint, database_info.datname,
               database_owner.oid::bigint, database_owner.rolname
        FROM pg_database AS database_info
        JOIN pg_roles AS database_owner ON database_owner.oid = database_info.datdba
        WHERE database_info.datname = current_database()
        """
    )
    database_oid, database_name, database_owner_oid, database_owner_name = cursor.fetchone()
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
    schema_oid, actual_schema_name, schema_owner_oid, schema_owner_name = cursor.fetchone()
    roles = {
        "runtime": _role_identity(cursor, runtime_role),
        "governance": _role_identity(cursor, governance_role),
        "migration": _role_identity(cursor, migration_role),
        "provisioner": _role_identity(cursor, provisioner_role),
    }
    cursor.execute(
        """
        SELECT object_info.oid::bigint, object_info.relname,
               object_owner.oid::bigint, object_owner.rolname
        FROM pg_class AS object_info
        JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
        JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
        WHERE object_info.oid = to_regclass(%s)
        """,
        [f"{schema_name}.{CATALOG_SNAPSHOT_TABLE}"],
    )
    snapshot_row = cursor.fetchone()
    cursor.execute(
        """
        SELECT object_info.oid::bigint, object_info.relname,
               object_owner.oid::bigint, object_owner.rolname
        FROM pg_class AS object_info
        JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
        JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
        WHERE object_info.oid = to_regclass(%s)
        """,
        [f"{schema_name}.{CATALOG_SNAPSHOT_BINDING_TABLE}"],
    )
    binding_row = cursor.fetchone()
    if snapshot_row is None or binding_row is None:
        raise RuntimeError("The 0126 audit snapshot binding objects are missing")

    def relation_identity(row):
        oid, name, owner_oid, owner_name = row
        return {"oid": int(oid), "name": name, "owner": {"oid": int(owner_oid), "name": owner_name}}

    topology = {
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
            "snapshot": relation_identity(snapshot_row),
            "binding": relation_identity(binding_row),
            "audit_table": _object_identity(cursor, schema_name, "operation_gateway_audit", kind="table"),
            "audit_function": _object_identity(
                cursor,
                schema_name,
                "operation_gateway_audit_append_only",
                kind="function",
                identity_arguments="",
            ),
        },
    }
    topology["objects"]["snapshot"]["owner"] = roles["provisioner"]
    topology["objects"]["binding"]["owner"] = roles["provisioner"]
    topology["objects"]["audit_table"]["owner"] = roles["governance"]
    topology["objects"]["audit_function"]["owner"] = roles["governance"]
    return topology


def _capture_audit_catalog_snapshot(connection, *, runtime_role, governance_role, migration_role):
    """Capture the effective 0125 catalog before 0126 mutates any ACL.

    PostgreSQL exposes ACLs as catalog arrays, but replaying those arrays is a
    privileged catalog write. Store the effective grant rows instead; the
    separately authenticated provisioner restores them before a reverse.
    The snapshot is durable in a migration-owned table, so a later provisioner
    phase can restore the migration without relying on test state.
    """

    with connection.cursor() as cursor:
        schema_name = settings.PLANE_AUDIT_SCHEMA
        if not ROLE_NAME.fullmatch(schema_name or ""):
            raise RuntimeError("PLANE_AUDIT_SCHEMA must be a simple PostgreSQL identifier")
        cursor.execute("SELECT current_schema(), current_schemas(false)")
        current_schema, search_path = cursor.fetchone()
        if current_schema != schema_name or search_path != [schema_name]:
            raise RuntimeError("Operation Gateway audit uses an unapproved schema/search_path")
        schema_ident = connection.ops.quote_name(schema_name)

        cursor.execute(
            """
            SELECT schema_owner.rolname
            FROM pg_namespace AS audit_schema
            JOIN pg_roles AS schema_owner ON schema_owner.oid = audit_schema.nspowner
            WHERE audit_schema.nspname = %s
            """,
            [schema_name],
        )
        schema_owner = cursor.fetchone()[0]
        cursor.execute("SELECT current_user")
        current_user = cursor.fetchone()[0]
        provisioner_role = settings.PLANE_AUDIT_PROVISIONER_ROLE or current_user
        if not ROLE_NAME.fullmatch(provisioner_role or ""):
            raise RuntimeError("PLANE_AUDIT_PROVISIONER_ROLE must be a simple PostgreSQL identifier")
        snapshot = {
            "version": CATALOG_SNAPSHOT_VERSION,
            "schema": {"name": schema_name, "owner": schema_owner, "acl": []},
            "objects": [],
            "default_privileges": [],
            "memberships": [],
        }

        cursor.execute(
            """
            SELECT grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN NULL ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_namespace AS audit_schema
            JOIN LATERAL aclexplode(
                COALESCE(audit_schema.nspacl, acldefault('n'::\"char\", audit_schema.nspowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE audit_schema.nspname = %s
            ORDER BY 1, 2, 3, 4
            """,
            [schema_name],
        )
        snapshot["schema"]["acl"] = [
            _acl_entry(grantor, grantee, privilege, is_grantable)
            for grantor, grantee, privilege, is_grantable in cursor.fetchall()
        ]

        objects = {}
        cursor.execute(
            """
            SELECT object_info.relkind, object_info.relname, object_owner.rolname,
                   grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN NULL ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN pg_roles AS object_owner ON object_owner.oid = object_info.relowner
            JOIN LATERAL aclexplode(
                COALESCE(
                    object_info.relacl,
                    acldefault(
                        CASE WHEN object_info.relkind = 'S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,
                        object_info.relowner
                    )
                )
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = %s
              AND object_info.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
            ORDER BY 1, 2, 4, 5, 6, 7
            """,
            [schema_name],
        )
        for relkind, name, owner, grantor, grantee, privilege, is_grantable in cursor.fetchall():
            kind = "sequence" if relkind == "S" else "table"
            key = (kind, name)
            objects.setdefault(key, {"kind": kind, "name": name, "owner": owner, "acl": []})["acl"].append(
                _acl_entry(grantor, grantee, privilege, is_grantable)
            )

        cursor.execute(
            """
            SELECT object_info.proname, pg_get_function_identity_arguments(object_info.oid),
                   function_owner.rolname, object_info.prosecdef, object_info.proconfig,
                   grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN NULL ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_proc AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.pronamespace
            JOIN pg_roles AS function_owner ON function_owner.oid = object_info.proowner
            JOIN LATERAL aclexplode(
                COALESCE(object_info.proacl, acldefault('f'::\"char\", object_info.proowner))
            ) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE object_schema.nspname = %s
            ORDER BY 1, 2, 6, 7, 8, 9
            """,
            [schema_name],
        )
        for (
            name,
            identity_arguments,
            owner,
            security_definer,
            config,
            grantor,
            grantee,
            privilege,
            is_grantable,
        ) in cursor.fetchall():
            key = ("function", name, identity_arguments)
            objects.setdefault(
                key,
                {
                    "kind": "function",
                    "name": name,
                    "identity_arguments": identity_arguments,
                    "owner": owner,
                    "security_definer": bool(security_definer),
                    "config": list(config) if config is not None else None,
                    "acl": [],
                },
            )["acl"].append(_acl_entry(grantor, grantee, privilege, is_grantable))

        cursor.execute(
            """
            SELECT default_owner.rolname, defaults.defaclobjtype,
                   grantor.rolname,
                   CASE WHEN exploded.grantee = 0 THEN NULL ELSE grantee.rolname END,
                   exploded.privilege_type, exploded.is_grantable
            FROM pg_default_acl AS defaults
            JOIN pg_roles AS default_owner ON default_owner.oid = defaults.defaclrole
            JOIN LATERAL aclexplode(defaults.defaclacl) AS exploded ON TRUE
            JOIN pg_roles AS grantor ON grantor.oid = exploded.grantor
            LEFT JOIN pg_roles AS grantee ON grantee.oid = exploded.grantee
            WHERE defaults.defaclnamespace = (
                SELECT oid FROM pg_namespace WHERE nspname = %s
            )
              AND defaults.defaclobjtype IN ('r', 'S', 'f')
            ORDER BY 1, 2, 3, 4, 5, 6
            """,
            [schema_name],
        )
        defaults = {}
        for default_owner, object_type, grantor, grantee, privilege, is_grantable in cursor.fetchall():
            key = (default_owner, object_type)
            defaults.setdefault(
                key,
                {"owner": default_owner, "object_type": object_type, "acl": []},
            )["acl"].append(_acl_entry(grantor, grantee, privilege, is_grantable))
        snapshot["default_privileges"] = list(defaults.values())

        role_names = (runtime_role, migration_role, governance_role)
        cursor.execute(
            """
            SELECT role_name.rolname, member_name.rolname, memberships.admin_option
            FROM pg_auth_members AS memberships
            JOIN pg_roles AS role_name ON role_name.oid = memberships.roleid
            JOIN pg_roles AS member_name ON member_name.oid = memberships.member
            WHERE role_name.rolname IN (%s, %s, %s)
               OR member_name.rolname IN (%s, %s, %s)
            ORDER BY 1, 2
            """,
            [*role_names, *role_names],
        )
        snapshot["memberships"] = [
            {"role": role, "member": member, "admin_option": bool(admin_option)}
            for role, member, admin_option in cursor.fetchall()
        ]

        snapshot["objects"] = list(objects.values())
        snapshot_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_TABLE)
        cursor.execute(
            f"""
            CREATE TABLE {schema_ident}.{snapshot_ident} (
                snapshot_id boolean PRIMARY KEY CHECK (snapshot_id),
                snapshot jsonb NOT NULL,
                CHECK (jsonb_typeof(snapshot) = 'object')
            )
            """
        )
        cursor.execute(
            f"INSERT INTO {schema_ident}.{snapshot_ident} (snapshot_id, snapshot) VALUES (TRUE, %s::jsonb)",
            [json.dumps(snapshot, sort_keys=True)],
        )
        cursor.execute(
            f"""
            CREATE TABLE {schema_ident}.{connection.ops.quote_name(CATALOG_SNAPSHOT_BINDING_TABLE)} (
                binding_id boolean PRIMARY KEY CHECK (binding_id),
                version integer NOT NULL CHECK (version = %s),
                snapshot_digest text NOT NULL CHECK (snapshot_digest ~ '^[0-9a-f]{{64}}$'),
                topology jsonb NOT NULL,
                CHECK (jsonb_typeof(topology) = 'object')
            )
            """,
            [CATALOG_SNAPSHOT_VERSION],
        )
        topology = _capture_audit_catalog_binding(
            cursor,
            schema_name=schema_name,
            runtime_role=runtime_role,
            governance_role=governance_role,
            migration_role=migration_role,
            provisioner_role=provisioner_role,
        )
        cursor.execute(
            f"INSERT INTO {schema_ident}.{connection.ops.quote_name(CATALOG_SNAPSHOT_BINDING_TABLE)} "
            "(binding_id, version, snapshot_digest, topology) VALUES (TRUE, %s, %s, %s::jsonb)",
            [
                CATALOG_SNAPSHOT_VERSION,
                _canonical_snapshot_digest(snapshot),
                json.dumps(topology, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            ],
        )


def capture_audit_catalog_snapshot(apps, schema_editor):
    connection = schema_editor.connection
    _capture_audit_catalog_snapshot(
        connection,
        runtime_role=settings.PLANE_AUDIT_RUNTIME_ROLE,
        governance_role=settings.PLANE_AUDIT_GOVERNANCE_ROLE,
        migration_role=settings.PLANE_AUDIT_MIGRATION_ROLE,
    )


def drop_audit_catalog_snapshot(apps, schema_editor):
    schema_ident = schema_editor.quote_name(settings.PLANE_AUDIT_SCHEMA)
    snapshot_ident = schema_editor.quote_name(CATALOG_SNAPSHOT_TABLE)
    binding_ident = schema_editor.quote_name(CATALOG_SNAPSHOT_BINDING_TABLE)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
        current_user, is_superuser = cursor.fetchone()
        cursor.execute(
            """
            SELECT owner.rolname
            FROM pg_class AS object_info
            JOIN pg_namespace AS object_schema ON object_schema.oid = object_info.relnamespace
            JOIN pg_roles AS owner ON owner.oid = object_info.relowner
            WHERE object_schema.nspname = %s AND object_info.relname = %s
            """,
            [settings.PLANE_AUDIT_SCHEMA, CATALOG_SNAPSHOT_TABLE],
        )
        owner = cursor.fetchone()
        if is_superuser or (owner is not None and owner[0] == current_user):
            cursor.execute(f"DROP TABLE IF EXISTS {schema_ident}.{binding_ident}")
            cursor.execute(f"DROP TABLE IF EXISTS {schema_ident}.{snapshot_ident}")


def require_provisioned_reverse_state(apps, schema_editor):
    """Reject a downgrade until the provisioner has restored the 0125 catalog."""

    connection = schema_editor.connection
    schema_ident = connection.ops.quote_name(settings.PLANE_AUDIT_SCHEMA)
    snapshot_ident = connection.ops.quote_name(CATALOG_SNAPSHOT_TABLE)
    audit_ident = f"{schema_ident}.operation_gateway_audit"
    function_ident = f"{schema_ident}.operation_gateway_audit_append_only()"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT snapshot FROM {schema_ident}.{snapshot_ident}")
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("The provisioner must restore the 0125 audit catalog before reverse migration")
        snapshot = row[0]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        if not isinstance(snapshot, dict) or snapshot.get("version") != CATALOG_SNAPSHOT_VERSION:
            raise RuntimeError("The provisioner must restore the 0125 audit catalog before reverse migration")
        expected_objects = {
            (item["kind"], item["name"], item.get("identity_arguments")): item["owner"]
            for item in snapshot.get("objects", [])
            if isinstance(item, dict) and {"kind", "name", "owner"} <= item.keys()
        }
        cursor.execute(
            """
            SELECT 'table', class.relname, NULL, owner.rolname
            FROM pg_class AS class
            JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
            JOIN pg_roles AS owner ON owner.oid = class.relowner
            WHERE class.oid = to_regclass(%s)
            UNION ALL
            SELECT 'function', proc.proname, pg_get_function_identity_arguments(proc.oid), owner.rolname
            FROM pg_proc AS proc
            JOIN pg_namespace AS namespace ON namespace.oid = proc.pronamespace
            JOIN pg_roles AS owner ON owner.oid = proc.proowner
            WHERE proc.oid = to_regprocedure(%s)
            """,
            [audit_ident, function_ident],
        )
        current_objects = {
            (kind, name, identity_arguments): owner for kind, name, identity_arguments, owner in cursor.fetchall()
        }
        expected_audit = {
            key: value
            for key, value in expected_objects.items()
            if key[1] in {"operation_gateway_audit", "operation_gateway_audit_append_only"}
        }
        if not expected_audit or set(expected_audit) - set(current_objects):
            raise RuntimeError("The provisioner must restore the 0125 audit catalog before reverse migration")
        if any(current_objects.get(key) != owner for key, owner in expected_audit.items()):
            raise RuntimeError("The provisioner must restore the 0125 audit catalog before reverse migration")


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0125_operationgateway_publications_and_audit_trigger"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationgatewaypublication",
            name="target_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="operationgatewaypublication",
            name="delivery_result",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operationgatewaypublication",
            name="dispatch_started",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="operationgatewaypublication",
            name="state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("retryable", "Retryable"),
                    ("outcome_unknown", "Outcome unknown"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="operationgatewaypublication",
            name="operation_gateway_publication_kind",
        ),
        migrations.AddConstraint(
            model_name="operationgatewaypublication",
            constraint=models.UniqueConstraint(
                condition=models.Q(target_id__isnull=True),
                fields=("idempotency", "kind"),
                name="operation_gateway_publication_kind_without_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="operationgatewaypublication",
            constraint=models.UniqueConstraint(
                condition=models.Q(target_id__isnull=False),
                fields=("idempotency", "kind", "target_id"),
                name="operation_gateway_publication_target",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="idempotency_key",
            field=models.CharField(blank=True, editable=False, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="emailnotificationlog",
            name="idempotency_key",
            field=models.CharField(blank=True, editable=False, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="delivery_key",
            field=models.CharField(blank=True, max_length=160, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="delivery_state",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="delivery_result",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="response_body_size",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="response_body_size_known",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="response_body_truncated",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="webhooklog",
            name="response_body_sha256",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RunPython(capture_audit_catalog_snapshot, drop_audit_catalog_snapshot),
        migrations.RunSQL(
            CREATE_APPEND_ONLY_TRIGGERS,
            DROP_APPEND_ONLY_TRIGGERS + RESTORE_APPEND_ONLY_TRIGGER,
        ),
        migrations.RunPython(split_legacy_webhook_intents, merge_webhook_intents_for_reverse),
        migrations.RunPython(migrations.RunPython.noop, require_provisioned_reverse_state),
    ]

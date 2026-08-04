"""Close durable publication, effect-idempotency, trigger, and role gaps."""

import copy
import re
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.db import migrations, models


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")
PUBLICATION_NAMESPACE = uuid.UUID("8a1b4fd8-49a5-54ad-a49e-7f2e0c1a3f1c")
REVERSE_MARKER = "__plane_0126_reverse__"

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


def _role_identifier(connection, value: str) -> str:
    if not isinstance(value, str) or not ROLE_NAME.fullmatch(value):
        raise RuntimeError("Operation Gateway audit role names must be simple PostgreSQL identifiers")
    return connection.ops.quote_name(value)


def configure_audit_role_boundary(apps, schema_editor):
    connection = schema_editor.connection
    runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    migration_role = settings.PLANE_AUDIT_MIGRATION_ROLE
    if not runtime_role or not governance_role or not migration_role:
        raise RuntimeError("Operation Gateway audit runtime and governance roles must be distinct")
    if runtime_role == governance_role or (
        settings.PLANE_AUDIT_ENFORCE_ROLE_SEPARATION and runtime_role == migration_role
    ):
        raise RuntimeError("Operation Gateway audit runtime, migration, and governance roles must be distinct")
    runtime_ident = _role_identifier(connection, runtime_role)
    governance_ident = _role_identifier(connection, governance_role)
    migration_ident = _role_identifier(connection, migration_role)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, current_user = %s, current_user = %s, current_user = %s",
            [runtime_role, governance_role, migration_role],
        )
        current_user, is_runtime, is_governance, is_migration = cursor.fetchone()
        if not is_migration:
            raise RuntimeError("Operation Gateway audit migration must use the migration database credential")
        cursor.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s, %s)",
            [runtime_role, governance_role, migration_role],
        )
        existing_roles = {row[0] for row in cursor.fetchall()}
        missing_roles = {runtime_role, governance_role, migration_role} - existing_roles
        if missing_roles:
            raise RuntimeError("Operation Gateway audit roles are missing; run bootstrap_operation_gateway_audit first")
        cursor.execute("SELECT current_schema()")
        schema_ident = connection.ops.quote_name(cursor.fetchone()[0])

        # The explicit bootstrap command provisions the owner. This migration
        # temporarily grants the migration authority membership in it so DDL
        # can transfer ownership, but it never creates the governed role.
        cursor.execute(f"GRANT {governance_ident} TO {migration_ident}")
        cursor.execute(f"REVOKE {governance_ident} FROM {runtime_ident}")
        cursor.execute(f"REVOKE {migration_ident} FROM {runtime_ident}")

        # PostgreSQL requires the target owner to have CREATE on the schema
        # during an ownership transfer. Keep this capability scoped to the
        # transfer; the governance role is otherwise NOLOGIN and has no
        # schema-creation responsibility.
        cursor.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_ident} TO {governance_ident}")
        cursor.execute(f"ALTER TABLE operation_gateway_audit OWNER TO {governance_ident}")
        cursor.execute(f"ALTER FUNCTION operation_gateway_audit_append_only() OWNER TO {governance_ident}")
        cursor.execute(f"REVOKE CREATE ON SCHEMA {schema_ident} FROM {governance_ident}")
        cursor.execute("ALTER FUNCTION operation_gateway_audit_append_only() SECURITY DEFINER")
        cursor.execute("ALTER FUNCTION operation_gateway_audit_append_only() SET search_path = pg_catalog")
        cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(f"REVOKE CREATE ON SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(f"REVOKE ALL ON SCHEMA {schema_ident} FROM PUBLIC")
        cursor.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_ident} TO {migration_ident}")
        cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {governance_ident}")

        # The runtime role needs ordinary Plane ORM access to the application
        # schema. Keep this grant explicit rather than using ALL so it cannot
        # acquire DDL, TRUNCATE, or role-governance powers through the schema.
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_ident} TO {runtime_ident}"
        )
        cursor.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"GRANT EXECUTE ON FUNCTIONS TO {runtime_ident}"
        )
        for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
                f"REVOKE ALL ON {object_type} FROM PUBLIC"
            )

        # Audit storage is stricter than the ordinary application schema.
        cursor.execute("REVOKE ALL ON TABLE operation_gateway_audit FROM PUBLIC")
        cursor.execute(f"GRANT SELECT, INSERT ON TABLE operation_gateway_audit TO {runtime_ident}")
        # The one-shot migrator still needs to inspect and append audit rows
        # while running later migrations, but it does not receive mutation or
        # trigger-control privileges through this grant.
        cursor.execute(f"GRANT SELECT, INSERT ON TABLE operation_gateway_audit TO {migration_ident}")
        cursor.execute(
            f"REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE operation_gateway_audit "
            f"FROM {runtime_ident}"
        )
        cursor.execute(f"REVOKE ALL ON FUNCTION operation_gateway_audit_append_only() FROM PUBLIC, {runtime_ident}")
        cursor.execute(f"GRANT EXECUTE ON FUNCTION operation_gateway_audit_append_only() TO {governance_ident}")

        cursor.execute(
            """
            SELECT c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relkind = 'S'
              AND c.relname LIKE 'operation_gateway_audit%'
            """
        )
        for (sequence_name,) in cursor.fetchall():
            sequence_ident = _role_identifier(connection, sequence_name)
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence_ident} TO {runtime_ident}")

        cursor.execute(f"REVOKE {governance_ident} FROM {migration_ident}")


def unconfigure_audit_role_boundary(apps, schema_editor):
    connection = schema_editor.connection
    runtime_ident = _role_identifier(connection, settings.PLANE_AUDIT_RUNTIME_ROLE)
    governance_ident = _role_identifier(connection, settings.PLANE_AUDIT_GOVERNANCE_ROLE)
    migration_ident = _role_identifier(connection, settings.PLANE_AUDIT_MIGRATION_ROLE)
    with connection.cursor() as cursor:
        cursor.execute(f"GRANT {governance_ident} TO {migration_ident}")
        cursor.execute(f"ALTER FUNCTION operation_gateway_audit_append_only() OWNER TO {migration_ident}")
        cursor.execute(f"ALTER TABLE operation_gateway_audit OWNER TO {migration_ident}")
        cursor.execute(f"REVOKE {governance_ident} FROM {migration_ident}")
        cursor.execute("SELECT current_schema()")
        schema_ident = connection.ops.quote_name(cursor.fetchone()[0])
        cursor.execute(
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_ident} FROM {runtime_ident}"
        )
        cursor.execute(f"REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(f"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM {runtime_ident}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_ident} IN SCHEMA {schema_ident} "
            f"REVOKE EXECUTE ON FUNCTIONS FROM {runtime_ident}"
        )
        cursor.execute(f"REVOKE ALL ON TABLE operation_gateway_audit FROM {runtime_ident}")
        cursor.execute(f"REVOKE USAGE, CREATE ON SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_ident} TO PUBLIC")
        cursor.execute(
            """
            SELECT c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relkind = 'S'
              AND c.relname LIKE 'operation_gateway_audit%'
            """
        )
        for (sequence_name,) in cursor.fetchall():
            sequence_ident = _role_identifier(connection, sequence_name)
            cursor.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {sequence_ident} FROM {runtime_ident}")


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
        migrations.RunSQL(
            CREATE_APPEND_ONLY_TRIGGERS,
            DROP_APPEND_ONLY_TRIGGERS + RESTORE_APPEND_ONLY_TRIGGER,
        ),
        migrations.RunPython(split_legacy_webhook_intents, merge_webhook_intents_for_reverse),
        migrations.RunPython(configure_audit_role_boundary, unconfigure_audit_role_boundary),
    ]

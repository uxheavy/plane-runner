"""Close durable publication, effect-idempotency, trigger, and role gaps."""

import re
import uuid

from django.conf import settings
from django.db import migrations, models


ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_$]{0,62}$")

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
    """Convert pre-0126 workspace fan-out rows without claiming delivery."""

    Publication = apps.get_model("db", "OperationGatewayPublication")
    Webhook = apps.get_model("db", "Webhook")
    legacy_publications = Publication.objects.filter(kind="webhook", target_id__isnull=True)
    for publication in legacy_publications:
        payload = publication.payload if isinstance(publication.payload, dict) else {}
        targets = list(
            Webhook.objects.filter(
                workspace_id=publication.idempotency.workspace_id,
                is_active=True,
                issue=True,
            ).values_list("id", flat=True)
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
            if index == 0:
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
                    id=uuid.uuid4(),
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
    """Restore the pre-0126 single fan-out row when this migration is reversed."""

    Publication = apps.get_model("db", "OperationGatewayPublication")
    groups = {}
    for publication in Publication.objects.filter(kind="webhook", target_id__isnull=False).order_by("created_at", "id"):
        groups.setdefault(publication.idempotency_id, []).append(publication)

    for idempotency_id, publications in groups.items():
        first = publications[0]
        payload = first.payload if isinstance(first.payload, dict) else {}
        payload.pop("webhook_id", None)
        first.target_id = None
        first.publication_key = f"{idempotency_id}:webhook"
        first.payload = payload
        first.state = "pending" if first.state in ("running", "succeeded", "outcome_unknown") else first.state
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


def _role_identifier(connection, value: str) -> str:
    if not isinstance(value, str) or not ROLE_NAME.fullmatch(value):
        raise RuntimeError("Operation Gateway audit role names must be simple PostgreSQL identifiers")
    return connection.ops.quote_name(value)


def configure_audit_role_boundary(apps, schema_editor):
    connection = schema_editor.connection
    runtime_role = settings.PLANE_AUDIT_RUNTIME_ROLE
    governance_role = settings.PLANE_AUDIT_GOVERNANCE_ROLE
    if not runtime_role or runtime_role == governance_role:
        raise RuntimeError("Operation Gateway audit runtime and governance roles must be distinct")
    runtime_ident = _role_identifier(connection, runtime_role)
    governance_ident = _role_identifier(connection, governance_role)

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [governance_role])
        if cursor.fetchone() is None:
            cursor.execute(f"CREATE ROLE {governance_ident} NOLOGIN")
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [runtime_role])
        if cursor.fetchone() is None:
            raise RuntimeError("Configured Operation Gateway audit runtime role does not exist")

        # A migration authority can transfer the table to the governed owner
        # without granting the runtime role any role-management capability.
        cursor.execute(f"GRANT {governance_ident} TO CURRENT_USER")
        cursor.execute(f"ALTER TABLE operation_gateway_audit OWNER TO {governance_ident}")
        cursor.execute(f"REVOKE {governance_ident} FROM CURRENT_USER")
        cursor.execute(f"REVOKE ALL ON TABLE operation_gateway_audit FROM PUBLIC")
        cursor.execute("SELECT current_schema()")
        schema_ident = connection.ops.quote_name(cursor.fetchone()[0])
        cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {runtime_ident}")
        cursor.execute(f"REVOKE CREATE ON SCHEMA {schema_ident} FROM {runtime_ident}")
        cursor.execute(f"GRANT SELECT, INSERT ON TABLE operation_gateway_audit TO {runtime_ident}")
        cursor.execute(f"REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE operation_gateway_audit FROM {runtime_ident}")

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


def unconfigure_audit_role_boundary(apps, schema_editor):
    connection = schema_editor.connection
    runtime_ident = _role_identifier(connection, settings.PLANE_AUDIT_RUNTIME_ROLE)
    governance_ident = _role_identifier(connection, settings.PLANE_AUDIT_GOVERNANCE_ROLE)
    with connection.cursor() as cursor:
        cursor.execute(f"GRANT {governance_ident} TO CURRENT_USER")
        cursor.execute("ALTER TABLE operation_gateway_audit OWNER TO CURRENT_USER")
        cursor.execute(f"REVOKE {governance_ident} FROM CURRENT_USER")
        cursor.execute(f"REVOKE ALL ON TABLE operation_gateway_audit FROM {runtime_ident}")
        cursor.execute("SELECT current_schema()")
        schema_ident = connection.ops.quote_name(cursor.fetchone()[0])
        cursor.execute(f"REVOKE USAGE, CREATE ON SCHEMA {schema_ident} FROM {runtime_ident}")
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
        migrations.RunSQL(
            CREATE_APPEND_ONLY_TRIGGERS,
            DROP_APPEND_ONLY_TRIGGERS + RESTORE_APPEND_ONLY_TRIGGER,
        ),
        migrations.RunPython(split_legacy_webhook_intents, merge_webhook_intents_for_reverse),
        migrations.RunPython(configure_audit_role_boundary, unconfigure_audit_role_boundary),
    ]

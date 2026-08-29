import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0140_invocation_free_cancellation_integrity"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationgatewayidempotency",
            name="quota_agent_key",
            field=models.CharField(blank=True, default="", editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="operationgatewayidempotency",
            name="quota_bucket_start",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="operationgatewayidempotency",
            name="quota_invocation_key",
            field=models.CharField(blank=True, default="", editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="operationgatewayidempotency",
            name="quota_reserved",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddIndex(
            model_name="operationgatewayidempotency",
            index=models.Index(fields=["quota_bucket_start", "quota_reserved"], name="op_gateway_quota_active"),
        ),
        migrations.CreateModel(
            name="OperationGatewayQuotaBucket",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("workspace_id", models.UUIDField(editable=False)),
                (
                    "scope",
                    models.CharField(
                        choices=[("workspace", "Workspace"), ("agent", "Agent"), ("invocation", "Invocation")],
                        max_length=16,
                    ),
                ),
                ("subject_key", models.CharField(editable=False, max_length=128)),
                ("bucket_start", models.DateTimeField(editable=False)),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("active_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "operation_gateway_quota_bucket",
                "indexes": [
                    models.Index(fields=["workspace_id", "bucket_start"], name="op_gateway_quota_window"),
                    models.Index(fields=["scope", "subject_key", "bucket_start"], name="op_gateway_quota_subject"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="operationgatewayquotabucket",
            constraint=models.UniqueConstraint(
                fields=("workspace_id", "scope", "subject_key", "bucket_start"),
                name="operation_gateway_quota_bucket_key",
            ),
        ),
    ]

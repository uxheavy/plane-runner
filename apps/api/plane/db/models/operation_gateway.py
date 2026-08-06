"""Durable gateway receipts and append-only audit records."""

import uuid

from django.db import models


def _verify_gateway_write_boundary() -> None:
    # Keep the import local: role_boundary is an application seam, while this
    # module is imported during Django model discovery and migrations.
    from plane.operation_gateway.role_boundary import verify_audit_role_boundary

    verify_audit_role_boundary()


class OperationGatewayWriteQuerySet(models.QuerySet):
    """Make every public ORM write enter the shared gateway boundary."""

    def create(self, **kwargs):
        _verify_gateway_write_boundary()
        return super().create(**kwargs)

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        _verify_gateway_write_boundary()
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    def update(self, **kwargs):
        _verify_gateway_write_boundary()
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        _verify_gateway_write_boundary()
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def delete(self):
        _verify_gateway_write_boundary()
        return super().delete()

    def get_or_create(self, defaults=None, **kwargs):
        _verify_gateway_write_boundary()
        return super().get_or_create(defaults=defaults, **kwargs)

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        _verify_gateway_write_boundary()
        return super().update_or_create(defaults=defaults, create_defaults=create_defaults, **kwargs)


class OperationGatewayWriteManager(models.Manager.from_queryset(OperationGatewayWriteQuerySet)):
    """Manager whose public mutation methods cannot bypass the gateway guard."""


class AppendOnlyAuditQuerySet(models.QuerySet):
    """Prevent every ORM mutation path, not only instance mutation methods."""

    def update(self, **kwargs):
        _verify_gateway_write_boundary()
        raise ValueError("Operation gateway audit records are append-only")

    def delete(self):
        _verify_gateway_write_boundary()
        raise ValueError("Operation gateway audit records are append-only")

    def bulk_update(self, objs, fields, batch_size=None):
        _verify_gateway_write_boundary()
        raise ValueError("Operation gateway audit records are append-only")

    def create(self, **kwargs):
        _verify_gateway_write_boundary()
        return super().create(**kwargs)

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        _verify_gateway_write_boundary()
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    def get_or_create(self, defaults=None, **kwargs):
        _verify_gateway_write_boundary()
        return super().get_or_create(defaults=defaults, **kwargs)

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        _verify_gateway_write_boundary()
        return super().update_or_create(defaults=defaults, create_defaults=create_defaults, **kwargs)


class AppendOnlyAuditManager(models.Manager.from_queryset(AppendOnlyAuditQuerySet)):
    """Append-only manager with explicit guard coverage for public writes."""


class OperationGatewayIdempotency(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        DENIED = "denied", "Denied"
        FAILED_PRECOMMIT = "failed_precommit", "Failed before commit"
        OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    invocation_id = models.UUIDField(editable=False)
    operation_id = models.CharField(max_length=128)
    workspace_id = models.UUIDField(null=True, editable=False)
    workspace_slug = models.CharField(max_length=255)
    caller_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=128)
    correlation_id = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    state = models.CharField(max_length=32, choices=State.choices)
    request_input = models.JSONField(default=dict)
    retryable = models.BooleanField(default=False)
    result = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    audit_receipt = models.UUIDField(null=True, blank=True)
    quota_bucket_start = models.DateTimeField(null=True, blank=True, editable=False)
    quota_agent_key = models.CharField(max_length=128, blank=True, default="", editable=False)
    quota_invocation_key = models.CharField(max_length=128, blank=True, default="", editable=False)
    quota_reserved = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationGatewayWriteManager()

    def save(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().delete(*args, **kwargs)

    class Meta:
        db_table = "operation_gateway_idempotency"
        constraints = [
            models.UniqueConstraint(
                fields=("workspace_id", "caller_id", "operation_id", "idempotency_key"),
                name="operation_gateway_idempotency_key",
            )
        ]
        indexes = [
            models.Index(fields=("workspace_id", "created_at"), name="op_gateway_workspace_created"),
            models.Index(fields=("caller_id", "created_at"), name="op_gateway_caller_created"),
            models.Index(fields=("quota_bucket_start", "quota_reserved"), name="op_gateway_quota_active"),
        ]


class OperationGatewayQuotaBucket(models.Model):
    """One locked, durable quota bucket shared by every gateway transport."""

    class Scope(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        AGENT = "agent", "Agent"
        INVOCATION = "invocation", "Invocation"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace_id = models.UUIDField(editable=False)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    subject_key = models.CharField(max_length=128, editable=False)
    bucket_start = models.DateTimeField(editable=False)
    request_count = models.PositiveIntegerField(default=0)
    active_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationGatewayWriteManager()

    def save(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().delete(*args, **kwargs)

    class Meta:
        db_table = "operation_gateway_quota_bucket"
        constraints = [
            models.UniqueConstraint(
                fields=("workspace_id", "scope", "subject_key", "bucket_start"),
                name="operation_gateway_quota_bucket_key",
            )
        ]
        indexes = [
            models.Index(fields=("workspace_id", "bucket_start"), name="op_gateway_quota_window"),
            models.Index(fields=("scope", "subject_key", "bucket_start"), name="op_gateway_quota_subject"),
        ]


class OperationGatewayAudit(models.Model):
    class Phase(models.TextChoices):
        INTENT = "intent", "Intent"
        OUTCOME = "outcome", "Outcome"

    class Outcome(models.TextChoices):
        INTENT = "intent", "Intent"
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        FAILURE = "failure", "Failure"
        OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"
        REPLAY = "replay", "Replay"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    invocation_id = models.UUIDField(editable=False)
    phase = models.CharField(max_length=16, choices=Phase.choices)
    outcome = models.CharField(max_length=32, choices=Outcome.choices)
    request_id = models.UUIDField()
    operation_id = models.CharField(max_length=128)
    workspace_id = models.UUIDField(null=True)
    workspace_slug = models.CharField(max_length=255)
    caller_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=128)
    correlation_id = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "operation_gateway_audit"
        ordering = ("created_at", "id")
        base_manager_name = "objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=("workspace_id", "created_at"), name="op_gateway_audit_workspace_id"),
            models.Index(fields=("workspace_slug", "created_at"), name="op_gateway_audit_workspace"),
            models.Index(fields=("caller_id", "created_at"), name="op_gateway_audit_caller"),
        ]

    objects = AppendOnlyAuditManager()

    def save(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        if not self._state.adding:
            raise ValueError("Operation gateway audit records are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        raise ValueError("Operation gateway audit records are append-only")


class OperationGatewayPublication(models.Model):
    """One durable, independently retryable product publication intent."""

    class Kind(models.TextChoices):
        ACTIVITY = "activity", "Activity"
        NOTIFICATION = "notification", "Notification"
        WEBHOOK = "webhook", "Webhook"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        RETRYABLE = "retryable", "Retryable"
        OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    idempotency = models.ForeignKey(
        OperationGatewayIdempotency,
        on_delete=models.PROTECT,
        related_name="publications",
    )
    invocation_id = models.UUIDField(editable=False)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    # Non-null for a concrete webhook target. Activity and notification
    # publications intentionally keep this null and are unique per kind.
    target_id = models.UUIDField(null=True, blank=True, editable=False)
    publication_key = models.CharField(max_length=160, unique=True, editable=False)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=32, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default="")
    delivery_result = models.JSONField(null=True, blank=True)
    # This marker is committed before an external request is attempted. An
    # expired row with this marker is outcome_unknown and must not be replayed.
    dispatch_started = models.BooleanField(default=False)
    lease_until = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationGatewayWriteManager()

    def save(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _verify_gateway_write_boundary()
        return super().delete(*args, **kwargs)

    class Meta:
        db_table = "operation_gateway_publication"
        constraints = [
            models.UniqueConstraint(
                fields=("idempotency", "kind"),
                condition=models.Q(target_id__isnull=True),
                name="operation_gateway_publication_kind_without_target",
            ),
            models.UniqueConstraint(
                fields=("idempotency", "kind", "target_id"),
                condition=models.Q(target_id__isnull=False),
                name="operation_gateway_publication_target",
            ),
        ]
        indexes = [
            models.Index(fields=("state", "lease_until"), name="op_gateway_pub_dispatch"),
            models.Index(fields=("idempotency", "created_at"), name="op_gateway_pub_attempt"),
        ]

    def __str__(self):
        return self.publication_key

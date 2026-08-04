"""Durable gateway receipts and append-only audit records."""

import uuid

from django.db import models


class AppendOnlyAuditQuerySet(models.QuerySet):
    """Prevent every ORM mutation path, not only instance mutation methods."""

    def update(self, **kwargs):
        raise ValueError("Operation gateway audit records are append-only")

    def delete(self):
        raise ValueError("Operation gateway audit records are append-only")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError("Operation gateway audit records are append-only")


class AppendOnlyAuditManager(models.Manager.from_queryset(AppendOnlyAuditQuerySet)):
    pass


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        if not self._state.adding:
            raise ValueError("Operation gateway audit records are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
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
            )
        ]
        indexes = [
            models.Index(fields=("state", "lease_until"), name="op_gateway_pub_dispatch"),
            models.Index(fields=("idempotency", "created_at"), name="op_gateway_pub_attempt"),
        ]

    def __str__(self):
        return self.publication_key

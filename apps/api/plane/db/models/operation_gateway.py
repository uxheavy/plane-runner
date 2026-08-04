"""Durable gateway receipts and append-only audit records."""

import uuid

from django.db import models


class OperationGatewayIdempotency(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        DENIED = "denied", "Denied"
        FAILED_PRECOMMIT = "failed_precommit", "Failed before commit"
        OUTCOME_UNKNOWN = "outcome_unknown", "Outcome unknown"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    operation_id = models.CharField(max_length=128)
    workspace_slug = models.CharField(max_length=255)
    caller_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=128)
    correlation_id = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    state = models.CharField(max_length=32, choices=State.choices)
    result = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    audit_receipt = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operation_gateway_idempotency"
        constraints = [
            models.UniqueConstraint(
                fields=("workspace_slug", "caller_id", "idempotency_key"),
                name="operation_gateway_idempotency_key",
            )
        ]
        indexes = [
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

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    phase = models.CharField(max_length=16, choices=Phase.choices)
    outcome = models.CharField(max_length=32, choices=Outcome.choices)
    request_id = models.UUIDField()
    operation_id = models.CharField(max_length=128)
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
        indexes = [
            models.Index(fields=("workspace_slug", "created_at"), name="op_gateway_audit_workspace"),
            models.Index(fields=("caller_id", "created_at"), name="op_gateway_audit_caller"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Operation gateway audit records are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Operation gateway audit records are append-only")

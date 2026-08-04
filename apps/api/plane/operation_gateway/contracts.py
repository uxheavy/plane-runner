"""Versioned transport contracts for the Plane Operation Gateway."""

from __future__ import annotations

import json
from typing import Any, Literal, NotRequired, TypedDict

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import serializers

SCHEMA_VERSION = "plane.operation/v1"
MAX_INPUT_BYTES = 16 * 1024
MAX_RESULT_BYTES = 8 * 1024


class CallerBinding(TypedDict):
    type: Literal["user"]
    id: str


class WorkspaceBinding(TypedDict):
    slug: str
    id: NotRequired[str | None]


class IdempotencyBinding(TypedDict):
    key: str
    replayed: bool


class GatewayError(TypedDict):
    code: str
    message: str
    retryable: bool


class GatewaySuccessEnvelope(TypedDict):
    ok: Literal[True]
    schema_version: str
    operation_id: str
    request_id: str
    caller: CallerBinding
    workspace: WorkspaceBinding
    idempotency: IdempotencyBinding
    correlation_id: str
    audit_receipt: str
    result: dict[str, Any]


class GatewayFailureEnvelope(TypedDict):
    ok: Literal[False]
    schema_version: str
    operation_id: str
    request_id: str
    caller: CallerBinding
    workspace: WorkspaceBinding
    idempotency: IdempotencyBinding
    correlation_id: str
    audit_receipt: str | None
    error: GatewayError


GatewayEnvelope = GatewaySuccessEnvelope | GatewayFailureEnvelope


class OperationGatewayRequestSerializer(serializers.Serializer):
    """Parse the wire envelope; caller identity is deliberately not a field."""

    schema_version = serializers.CharField(max_length=64, default=SCHEMA_VERSION)
    operation_id = serializers.CharField(max_length=128)
    workspace_slug = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=128)
    correlation_id = serializers.CharField(max_length=128)
    input = serializers.JSONField()

    # These are presentation/model metadata only. The gateway accepts them so
    # host callers can forward model envelopes, but never uses them for auth.
    caller = serializers.JSONField(required=False, write_only=True)
    tool_exposure = serializers.JSONField(required=False, write_only=True)

    def validate_schema_version(self, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise serializers.ValidationError("Unsupported schema version")
        return value

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Operation input must be an object")

        encoded = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_INPUT_BYTES:
            raise serializers.ValidationError("Operation input exceeds the size limit")
        return value


class WorkItemReadInputSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    issue_id = serializers.UUIDField()


class WorkItemRenameInputSerializer(WorkItemReadInputSerializer):
    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)


def canonical_json(value: Any) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))

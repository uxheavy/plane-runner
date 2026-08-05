"""Versioned transport contracts for the Plane Operation Gateway."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, NotRequired, TypedDict

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import serializers

SCHEMA_VERSION = "plane.operation/v1"
MAX_INPUT_BYTES = 16 * 1024
MAX_RESULT_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 16 * 1024
MAX_METADATA_BYTES = 1024


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


class StrictSerializer(serializers.Serializer):
    """Reject fields that are not part of the versioned contract."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError("Unknown contract fields")
        return super().to_internal_value(data)


class OperationGatewayRequestSerializer(StrictSerializer):
    """Parse the wire envelope; caller identity is deliberately not a field."""

    schema_version = serializers.CharField(max_length=64, required=True, allow_blank=False)
    operation_id = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
    workspace_slug = serializers.SlugField(max_length=48, allow_blank=False)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
    correlation_id = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
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

    def validate_caller(self, value: Any) -> dict[str, Any]:
        return self._validate_metadata(value)

    def validate_tool_exposure(self, value: Any) -> dict[str, Any]:
        return self._validate_metadata(value)

    @staticmethod
    def _validate_metadata(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be an object")
        encoded = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
            raise serializers.ValidationError("Metadata exceeds the size limit")
        return value


class WorkItemReadInputSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    issue_id = serializers.UUIDField()


class WorkItemRenameInputSerializer(WorkItemReadInputSerializer):
    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)


class EmptyOperationInputSerializer(StrictSerializer):
    """The caller cannot smuggle identity or workspace fields into a read."""


class AttachmentReadInputSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    issue_id = serializers.UUIDField()
    attachment_id = serializers.UUIDField()


class AttachmentListInputSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    issue_id = serializers.UUIDField()


class AttachmentUploadFromUrlInputSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    issue_id = serializers.UUIDField()
    url = serializers.URLField(max_length=2048, allow_blank=False)
    name = serializers.CharField(max_length=255, allow_blank=False, required=False, allow_null=True)


def canonical_json(value: Any) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))

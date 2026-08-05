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


class WorkspaceSearchInputSerializer(StrictSerializer):
    query = serializers.CharField(max_length=255, required=True, allow_blank=True, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=50, required=False, default=20)
    cursor = serializers.CharField(max_length=32, required=False, allow_blank=False, trim_whitespace=True)

    def validate_cursor(self, value: str) -> str:
        if not value.startswith("cursor:"):
            raise serializers.ValidationError("Invalid cursor")
        try:
            offset = int(value.removeprefix("cursor:"))
        except ValueError as exc:
            raise serializers.ValidationError("Invalid cursor") from exc
        if offset < 0:
            raise serializers.ValidationError("Invalid cursor")
        return value


class CatalogSearchInputSerializer(WorkspaceSearchInputSerializer):
    pass


class CatalogDescribeInputSerializer(StrictSerializer):
    operation_id = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)


class CodeModeSpillInputSerializer(StrictSerializer):
    size_bytes = serializers.IntegerField(min_value=1, max_value=1_048_576)
    content_digest = serializers.CharField(max_length=128, min_length=8, allow_blank=False, trim_whitespace=True)
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


class GatewayOperationInputSerializer(StrictSerializer):
    """Typed envelope for the catalog's semantic operation families.

    The serializer declares the complete vocabulary once, then each catalog
    descriptor narrows it at the gateway edge.  This keeps validation at the
    external boundary while allowing canonical Plane serializers to retain
    ownership of domain-specific rules.
    """

    project_id = serializers.UUIDField(required=False)
    issue_id = serializers.UUIDField(required=False)
    attachment_id = serializers.UUIDField(required=False)
    cycle_id = serializers.UUIDField(required=False)
    new_cycle_id = serializers.UUIDField(required=False)
    module_id = serializers.UUIDField(required=False)
    page_id = serializers.UUIDField(required=False)
    work_item_id = serializers.UUIDField(required=False)
    comment_id = serializers.UUIDField(required=False)
    label_id = serializers.UUIDField(required=False)
    link_id = serializers.UUIDField(required=False)
    state_id = serializers.UUIDField(required=False)
    activity_id = serializers.UUIDField(required=False)
    relation_definition_id = serializers.UUIDField(required=False, allow_null=True)
    owned_by = serializers.UUIDField(required=False, allow_null=True)
    project_lead = serializers.UUIDField(required=False, allow_null=True)
    default_assignee = serializers.UUIDField(required=False, allow_null=True)
    lead = serializers.UUIDField(required=False, allow_null=True)
    parent = serializers.UUIDField(required=False, allow_null=True)
    add_user_id = serializers.UUIDField(required=False, allow_null=True)
    remove_user_id = serializers.UUIDField(required=False, allow_null=True)
    add_label_id = serializers.UUIDField(required=False, allow_null=True)
    remove_label_id = serializers.UUIDField(required=False, allow_null=True)

    name = serializers.CharField(max_length=255, allow_blank=False, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description_html = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description_stripped = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    comment_html = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    url = serializers.URLField(max_length=2048, required=False, allow_blank=False)
    external_source = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    external_id = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    identifier = serializers.CharField(max_length=32, required=False, allow_blank=False)
    color = serializers.CharField(max_length=32, required=False, allow_blank=False)
    emoji = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    cover_image = serializers.CharField(max_length=2048, required=False, allow_blank=True, allow_null=True)
    icon_prop = serializers.JSONField(required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    order_by = serializers.CharField(max_length=128, required=False, allow_blank=False)
    fields = serializers.CharField(max_length=2048, required=False, allow_blank=False)
    expand = serializers.CharField(max_length=2048, required=False, allow_blank=False)
    cursor = serializers.CharField(max_length=256, required=False, allow_blank=False)
    pql = serializers.CharField(max_length=4096, required=False, allow_blank=True, allow_null=True)
    query = serializers.CharField(max_length=255, required=False, allow_blank=False)
    relation_type = serializers.CharField(max_length=64, required=False, allow_blank=False)
    relation_definition_label = serializers.CharField(max_length=255, required=False, allow_blank=False)

    description_json = serializers.JSONField(required=False, allow_null=True)
    comment_json = serializers.JSONField(required=False, allow_null=True)
    view_props = serializers.JSONField(required=False, allow_null=True)
    logo_props = serializers.JSONField(required=False, allow_null=True)
    params = serializers.JSONField(required=False, allow_null=True)
    data = serializers.JSONField(required=False, allow_null=True)

    assignees = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)
    labels = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)
    work_item_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)
    members = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)
    per_page = serializers.IntegerField(required=False, min_value=1, max_value=1000)
    point = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    archive_in = serializers.IntegerField(required=False, allow_null=True)
    close_in = serializers.IntegerField(required=False, allow_null=True)
    network = serializers.IntegerField(required=False, allow_null=True)
    access = serializers.JSONField(required=False, allow_null=True)
    status = serializers.JSONField(required=False, allow_null=True)
    sequence = serializers.FloatField(required=False, allow_null=True)
    sort_order = serializers.FloatField(required=False, allow_null=True)
    start_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    end_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    target_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    archived_at = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    snoozed_till = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    duplicate_to = serializers.UUIDField(required=False, allow_null=True)
    source = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    source_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    role_slug = serializers.CharField(max_length=64, required=False, allow_blank=True)
    group = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    priority = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    type_id = serializers.UUIDField(required=False, allow_null=True)
    estimate_point = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    type = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    default_state = serializers.UUIDField(required=False, allow_null=True)
    estimate = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    state = serializers.UUIDField(required=False, allow_null=True)
    is_draft = serializers.BooleanField(required=False, allow_null=True)
    archived = serializers.BooleanField(required=False, allow_null=True)
    is_locked = serializers.BooleanField(required=False, allow_null=True)
    archive = serializers.BooleanField(required=False)
    track_visit = serializers.BooleanField(required=False)
    module_view = serializers.BooleanField(required=False, allow_null=True)
    cycle_view = serializers.BooleanField(required=False, allow_null=True)
    issue_views_view = serializers.BooleanField(required=False, allow_null=True)
    page_view = serializers.BooleanField(required=False, allow_null=True)
    intake_view = serializers.BooleanField(required=False, allow_null=True)
    guest_view_all_features = serializers.BooleanField(required=False, allow_null=True)
    is_issue_type_enabled = serializers.BooleanField(required=False, allow_null=True)
    is_time_tracking_enabled = serializers.BooleanField(required=False, allow_null=True)
    default = serializers.BooleanField(required=False, allow_null=True)
    is_triage = serializers.BooleanField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, allow_null=True)
    is_bot = serializers.BooleanField(required=False, allow_null=True)
    last_used = serializers.BooleanField(required=False, allow_null=True)

    def __init__(self, *args, allowed_fields: tuple[str, ...] = (), required_fields: tuple[str, ...] = (), **kwargs):
        self.allowed_fields = set(allowed_fields)
        self.required_fields = set(required_fields)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Operation input must be an object")
        unknown_fields = set(data) - self.allowed_fields
        if unknown_fields:
            raise serializers.ValidationError("Unknown operation input fields")
        missing_fields = self.required_fields - set(data)
        if missing_fields:
            raise serializers.ValidationError("Required operation input is missing")
        return super().to_internal_value(data)


def canonical_json(value: Any) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))

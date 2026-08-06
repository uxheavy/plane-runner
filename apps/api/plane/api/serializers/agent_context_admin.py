# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed, redacted serializers for Agent context and trigger administration."""

from rest_framework import serializers

from plane.agent.administration import redact_admin_value
from plane.db.models import (
    AgentChangeProposal,
    AgentMemoryEntry,
    AgentMemoryRevision,
    AgentSchedule,
    AgentScheduleFire,
    AgentSkillDefinition,
    AgentSkillRevision,
)


class _RedactedModelSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class AgentMemoryRevisionAdminSerializer(_RedactedModelSerializer):
    class Meta:
        model = AgentMemoryRevision
        fields = [
            "id",
            "entry",
            "revision",
            "predecessor",
            "state",
            "content",
            "content_digest",
            "provenance",
            "provenance_ref",
            "source_actor",
            "source_run",
            "rationale",
            "created_at",
        ]
        read_only_fields = fields


class AgentMemoryAdminSerializer(_RedactedModelSerializer):
    active_revision = serializers.SerializerMethodField()

    def get_active_revision(self, instance):
        revision = instance.revisions.filter(state="active").order_by("-revision").first()
        return AgentMemoryRevisionAdminSerializer(revision).data if revision else None

    class Meta:
        model = AgentMemoryEntry
        fields = [
            "id",
            "actor",
            "key",
            "kind",
            "visibility",
            "subject_user",
            "retention_expires_at",
            "deletion_reason",
            "deleted_at",
            "active_revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentSkillRevisionAdminSerializer(_RedactedModelSerializer):
    class Meta:
        model = AgentSkillRevision
        fields = [
            "id",
            "definition",
            "revision",
            "predecessor",
            "state",
            "package_files",
            "package_digest",
            "provenance",
            "provenance_ref",
            "source_actor",
            "source_run",
            "rationale",
            "created_at",
        ]
        read_only_fields = fields


class AgentSkillAdminSerializer(_RedactedModelSerializer):
    active_revision = serializers.SerializerMethodField()

    def get_active_revision(self, instance):
        revision = instance.revisions.filter(state="active").order_by("-revision").first()
        return AgentSkillRevisionAdminSerializer(revision).data if revision else None

    class Meta:
        model = AgentSkillDefinition
        fields = [
            "id",
            "actor",
            "key",
            "display_name",
            "description",
            "visibility",
            "subject_user",
            "shared_scope_id",
            "retention_expires_at",
            "deletion_reason",
            "deleted_at",
            "active_revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentChangeProposalAdminSerializer(_RedactedModelSerializer):
    class Meta:
        model = AgentChangeProposal
        fields = [
            "id",
            "kind",
            "actor",
            "memory_revision",
            "skill_revision",
            "state",
            "rationale",
            "requested_visibility",
            "requested_scope_id",
            "proposed_by",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "applied_revision_ref",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentScheduleAdminSerializer(_RedactedModelSerializer):
    class Meta:
        model = AgentSchedule
        fields = [
            "id",
            "actor",
            "name",
            "cron_expression",
            "timezone_name",
            "target_ref",
            "objective",
            "acceptance_criteria",
            "context_refs",
            "retry_policy",
            "state",
            "next_fire_at",
            "last_fired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentScheduleFireAdminSerializer(_RedactedModelSerializer):
    class Meta:
        model = AgentScheduleFire
        fields = [
            "id",
            "schedule",
            "scheduled_for",
            "idempotency_key",
            "attempt",
            "state",
            "assignment",
            "error",
            "next_retry_at",
            "fired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentMemoryCreateSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=255, allow_blank=False)
    content = serializers.CharField(max_length=65_536, allow_blank=False)
    kind = serializers.CharField(max_length=32, required=False, default="fact")
    visibility = serializers.CharField(max_length=32, required=False, default="agent_private")
    subject_user_id = serializers.UUIDField(required=False, allow_null=True)
    provenance = serializers.CharField(max_length=32, required=False, default="human")
    provenance_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    retention_expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AgentSkillCreateSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=255, allow_blank=False)
    package_files = serializers.DictField(
        child=serializers.CharField(max_length=65_536, allow_blank=False),
    )
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=False)
    description = serializers.CharField(max_length=65_536, required=False, allow_blank=True, default="")
    visibility = serializers.CharField(max_length=32, required=False, default="agent_private")
    subject_user_id = serializers.UUIDField(required=False, allow_null=True)
    provenance = serializers.CharField(max_length=32, required=False, default="human")
    provenance_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    retention_expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_package_files(self, value):
        if len(value) > 64:
            raise serializers.ValidationError("package_files contains more than 64 files")
        return value


class AgentProposalReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=4_096, required=False, allow_blank=True, default="")


class AgentRollbackSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    rationale = serializers.CharField(max_length=4_096, allow_blank=False)


class AgentScheduleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, allow_blank=False)
    cron_expression = serializers.CharField(max_length=255, allow_blank=False)
    timezone_name = serializers.CharField(max_length=64, required=False, default="UTC")
    target_ref = serializers.CharField(max_length=255, allow_blank=False)
    objective = serializers.CharField(max_length=65_536, allow_blank=False)
    acceptance_criteria = serializers.ListField(
        child=serializers.CharField(max_length=4_096), required=False, max_length=32
    )
    context_refs = serializers.ListField(child=serializers.CharField(max_length=255), required=False, max_length=64)
    retry_policy = serializers.DictField(required=False)
    starts_at = serializers.DateTimeField(required=False)


class AgentScheduleFireSerializer(serializers.Serializer):
    scheduled_for = serializers.DateTimeField()
    idempotency_key = serializers.CharField(max_length=128, required=False, allow_blank=False)

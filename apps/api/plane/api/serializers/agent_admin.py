# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable, redacted serializers for Plane Agent administration."""

from rest_framework import serializers

from plane.agent.administration import AGENT_ADMIN_L7_ACTIONS, redact_admin_value, validate_credential_ref
from plane.agent.validation import (
    MAX_AGENT_READBACK_BYTES,
    MAX_BOUNDED_TEXT_BYTES,
    AgentValueError,
    validate_bounded_json,
)
from plane.db.models import (
    AgentActor,
    AgentRole,
    AssignmentContract,
    InputEventKind,
    OutcomeSubmission,
    ProfileVersion,
    RunAttempt,
    RunInputEvent,
    RunTerminalEvent,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeInvocation,
    RuntimeInvocationControl,
    RuntimeUsageObservation,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency

from .base import BaseSerializer


class AgentActorAdminSerializer(BaseSerializer):
    credential_configured = serializers.SerializerMethodField()

    def get_credential_configured(self, instance):
        return bool(instance.credential_ref)

    class Meta:
        model = AgentActor
        fields = ["id", "display_name", "is_active", "active_profile", "project", "credential_configured"]
        read_only_fields = fields


class AgentActorCreateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    credential_ref = serializers.CharField(max_length=255, required=False, allow_blank=False, write_only=True)

    def validate_credential_ref(self, value):
        try:
            return validate_credential_ref(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AgentActorPatchSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=False, trim_whitespace=True)
    is_active = serializers.BooleanField(required=False)
    credential_ref = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=False,
        allow_null=True,
        write_only=True,
    )

    def validate_credential_ref(self, value):
        try:
            return validate_credential_ref(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class ProfileVersionCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=AgentRole.choices)
    instructions = serializers.CharField(max_length=32768, allow_blank=False, trim_whitespace=True)
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=False, trim_whitespace=True)
    persona = serializers.CharField(max_length=32768, required=False, allow_blank=True)
    expected_outcomes = serializers.ListField(
        required=False,
        child=serializers.CharField(max_length=4096),
        max_length=32,
        default=list,
    )
    model_defaults = serializers.DictField(required=False, default=dict)
    runtime_defaults = serializers.DictField(required=False, default=dict)
    context_refs = serializers.ListField(required=False, max_length=64, default=list)
    tool_presentation = serializers.DictField(required=False, default=dict)
    memory_scopes = serializers.ListField(required=False, max_length=64, default=list)


class ProfileVersionAdminSerializer(BaseSerializer):
    class Meta:
        model = ProfileVersion
        fields = [
            "id",
            "actor",
            "version",
            "display_name",
            "role",
            "persona",
            "instructions",
            "expected_outcomes",
            "model_defaults",
            "runtime_defaults",
            "context_refs",
            "tool_presentation",
            "memory_scopes",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class AssignmentCreateSerializer(serializers.Serializer):
    target_ref = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    objective = serializers.CharField(max_length=4096, allow_blank=False, trim_whitespace=True)
    acceptance_criteria = serializers.ListField(
        required=True,
        min_length=1,
        max_length=32,
        child=serializers.CharField(max_length=4096),
    )
    context_refs = serializers.ListField(required=False, max_length=64, default=list)


class AssignmentAdminSerializer(BaseSerializer):
    assignee_id = serializers.UUIDField(source="assignee.id", read_only=True)
    lineage_of_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = AssignmentContract
        fields = [
            "id",
            "assignee_id",
            "lineage_of_id",
            "revision",
            "target_ref",
            "objective",
            "acceptance_criteria",
            "context_refs",
            "state",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DispatchSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
    profile_version_id = serializers.UUIDField(required=False)
    trigger = serializers.ChoiceField(
        choices=("initial", "human_input", "recoverable_restart", "continuation"),
        required=False,
    )
    input_event_id = serializers.UUIDField(required=False)
    usage = serializers.DictField(required=False, default=dict)
    lineage_of_id = serializers.UUIDField(required=False)
    lineage_reason = serializers.CharField(max_length=32, required=False)
    recovery_of_id = serializers.UUIDField(required=False)
    recovery_intent = serializers.CharField(max_length=32, required=False)


class InputEventCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
    payload = serializers.DictField()
    kind = serializers.ChoiceField(choices=InputEventKind.choices, required=False, default=InputEventKind.HUMAN_INPUT)
    pending_input_ref = serializers.CharField(max_length=128, required=True, allow_blank=False)

    def validate_payload(self, value):
        try:
            return validate_bounded_json(value, "payload", max_items=64)
        except AgentValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class RunAdminSerializer(BaseSerializer):
    assignment_id = serializers.UUIDField(read_only=True)
    actor_id = serializers.UUIDField(read_only=True)
    profile_version_id = serializers.UUIDField(read_only=True)
    lineage_of_id = serializers.UUIDField(read_only=True, allow_null=True)
    recovery_of_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RunAttempt
        fields = [
            "id",
            "assignment_id",
            "actor_id",
            "profile_version_id",
            "snapshot",
            "snapshot_content_digest",
            "state",
            "invocation_count",
            "last_invocation_id",
            "cumulative_usage",
            "lineage_of_id",
            "lineage_reason",
            "recovery_of_id",
            "recovery_intent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class RunInputEventAdminSerializer(BaseSerializer):
    class Meta:
        model = RunInputEvent
        fields = [
            "id",
            "event_ref",
            "sequence",
            "kind",
            "payload_digest",
            "pending_input_ref",
            "is_authoritative",
            "created_at",
        ]
        read_only_fields = fields


class RuntimeInvocationAdminSerializer(BaseSerializer):
    control = serializers.SerializerMethodField()
    usage_observation = serializers.SerializerMethodField()

    def get_control(self, instance):
        control = getattr(instance, "runtime_control", None)
        if control is None:
            return None
        return RuntimeInvocationControlAdminSerializer(control).data

    def get_usage_observation(self, instance):
        observation = getattr(instance, "runtime_usage_observation", None)
        if observation is None:
            return None
        return RuntimeUsageObservationAdminSerializer(observation).data

    class Meta:
        model = RuntimeInvocation
        fields = [
            "id",
            "ordinal",
            "invocation_id",
            "idempotency_key",
            "usage",
            "state",
            "control",
            "usage_observation",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class RuntimeInvocationReadbackSerializer(BaseSerializer):
    """Safe invocation evidence for the bounded combined readback."""

    usage_observation = serializers.SerializerMethodField()

    def get_usage_observation(self, instance):
        observation = getattr(instance, "runtime_usage_observation", None)
        if observation is None:
            return None
        return RuntimeUsageObservationAdminSerializer(observation).data

    class Meta:
        model = RuntimeInvocation
        fields = [
            "id",
            "ordinal",
            "invocation_id",
            "idempotency_key",
            "usage",
            "state",
            "usage_observation",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class RuntimeInvocationControlAdminSerializer(BaseSerializer):
    class Meta:
        model = RuntimeInvocationControl
        fields = [
            "id",
            "state",
            "lease_owner",
            "lease_expires_at",
            "dispatch_started_at",
            "cancellation_requested_at",
            "cancellation_reason",
            "outcome_unknown_at",
            "failure_code",
            "failure_reason",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class RuntimeUsageObservationAdminSerializer(BaseSerializer):
    class Meta:
        model = RuntimeUsageObservation
        fields = ["id", "invocation", "run", "usage", "fingerprint", "created_at"]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class RuntimeEventEvidenceSerializer(BaseSerializer):
    class Meta:
        model = RuntimeEventIngress
        fields = [
            "id",
            "event_id",
            "invocation",
            "run",
            "sequence",
            "fingerprint",
            "kind",
            "observed_at",
            "created_at",
        ]
        read_only_fields = fields


class RuntimeExitEvidenceSerializer(BaseSerializer):
    class Meta:
        model = RuntimeExitEvidence
        fields = [
            "id",
            "invocation",
            "run",
            "final_sequence",
            "fingerprint",
            "kind",
            "created_at",
        ]
        read_only_fields = fields


class OutcomeAdminSerializer(BaseSerializer):
    class Meta:
        model = OutcomeSubmission
        fields = [
            "id",
            "run",
            "summary",
            "artifacts",
            "evidence",
            "state",
            "evaluator",
            "evaluator_feedback",
            "evaluator_reviewed_at",
            "human_reviewer",
            "human_decision_note",
            "human_decided_at",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class OutcomeCreateSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=32768, allow_blank=False, trim_whitespace=True)
    artifacts = serializers.ListField(required=False, max_length=64, default=list)
    evidence = serializers.ListField(required=False, max_length=64, default=list)
    idempotency_key = serializers.CharField(max_length=128, required=False, allow_blank=False, trim_whitespace=True)


class OutcomeReviewSerializer(serializers.Serializer):
    evaluator_id = serializers.UUIDField()
    feedback = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_BOUNDED_TEXT_BYTES,
    )


class OutcomeDecisionSerializer(serializers.Serializer):
    decision_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_BOUNDED_TEXT_BYTES,
    )


class AgentGovernanceCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=AGENT_ADMIN_L7_ACTIONS)
    actor_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField(required=False, allow_null=True)
    invocation_id = serializers.CharField(required=False, allow_null=True, max_length=128, trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, trim_whitespace=True)
    payload = serializers.DictField(required=False, default=dict)

    def validate_payload(self, value):
        try:
            return validate_bounded_json(
                value,
                "payload",
                max_bytes=MAX_AGENT_READBACK_BYTES,
                reject_credentials=True,
            )
        except AgentValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class GatewayReceiptAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationGatewayIdempotency
        fields = [
            "id",
            "request_id",
            "operation_id",
            "workspace_slug",
            "caller_id",
            "idempotency_key",
            "correlation_id",
            "request_digest",
            "state",
            "retryable",
            "audit_receipt",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class GatewayAuditAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationGatewayAudit
        fields = [
            "id",
            "invocation_id",
            "phase",
            "outcome",
            "request_id",
            "operation_id",
            "workspace_slug",
            "caller_id",
            "idempotency_key",
            "correlation_id",
            "request_digest",
            "error_code",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class GatewayReadbackSerializer(serializers.Serializer):
    receipt = GatewayReceiptAdminSerializer()
    audit = GatewayAuditAdminSerializer(many=True)

    def to_representation(self, instance):
        return redact_admin_value(super().to_representation(instance))


class TerminalEventAdminSerializer(BaseSerializer):
    class Meta:
        model = RunTerminalEvent
        fields = [
            "id",
            "invocation",
            "run",
            "kind",
            "source",
            "product_ref",
            "product_event_ref",
            "reason",
            "cancellation_ref",
            "visible",
            "created_at",
        ]
        read_only_fields = fields

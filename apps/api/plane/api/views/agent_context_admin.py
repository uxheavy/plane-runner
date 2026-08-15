# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Operator API adapters for existing Agent memory, skill, and schedule services."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.agent.memory import (
    create_memory,
    promote_proposal,
    propose_memory_change,
    review_proposal,
    rollback_memory,
)
from plane.agent.schedules import create_schedule, fire_schedule, retry_schedule_fire, transition_schedule
from plane.agent.skills import create_skill, propose_skill_change, rollback_skill
from plane.api.serializers.agent_context_admin import (
    AgentChangeProposalAdminSerializer,
    AgentMemoryAdminSerializer,
    AgentMemoryCreateSerializer,
    AgentMemoryRevisionAdminSerializer,
    AgentProposalReviewSerializer,
    AgentRollbackSerializer,
    AgentScheduleAdminSerializer,
    AgentScheduleCreateSerializer,
    AgentScheduleControlSerializer,
    AgentScheduleFireAdminSerializer,
    AgentScheduleFireSerializer,
    AgentSkillAdminSerializer,
    AgentSkillCreateSerializer,
    AgentSkillRevisionAdminSerializer,
)
from plane.api.views.agent_admin import AgentAdminAPIView
from plane.db.models import (
    AgentActor,
    AgentChangeProposal,
    AgentMemoryEntry,
    AgentMemoryRevision,
    AgentSchedule,
    AgentScheduleFire,
    AgentSkillDefinition,
    AgentSkillRevision,
    WorkspaceMember,
)


def _validation_error(exc: Exception) -> Response:
    return Response(
        {"error": {"code": "AGENT_ADMIN_VALIDATION", "message": str(exc)}},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _actor(view: AgentAdminAPIView, actor_id: str) -> AgentActor:
    return get_object_or_404(
        AgentActor.objects.select_related("active_profile"),
        workspace__slug=view.workspace_slug,
        pk=actor_id,
    )


def _workspace_user(view: AgentAdminAPIView, user_id):
    member = get_object_or_404(
        WorkspaceMember.objects.select_related("member"),
        workspace__slug=view.workspace_slug,
        member_id=user_id,
        is_active=True,
    )
    return member.member


class AgentMemoryAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        queryset = AgentMemoryEntry.objects.filter(actor=actor, deleted_at__isnull=True).order_by("key", "id")
        return self.paginate_admin(request, queryset, AgentMemoryAdminSerializer)

    def post(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        serializer = AgentMemoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        subject_user = values.pop("subject_user_id", None)
        if subject_user is not None:
            subject_user = _workspace_user(self, subject_user)
        try:
            entry = create_memory(actor, subject_user=subject_user, created_by=request.user, **values)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentMemoryAdminSerializer(entry).data, status=status.HTTP_201_CREATED)


class AgentMemoryRevisionAdminListAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id, memory_id):
        entry = get_object_or_404(
            AgentMemoryEntry.all_objects,
            workspace__slug=slug,
            actor_id=actor_id,
            pk=memory_id,
        )
        queryset = AgentMemoryRevision.all_objects.filter(entry=entry).order_by("-revision", "-id")
        return self.paginate_admin(request, queryset, AgentMemoryRevisionAdminSerializer)


class AgentMemoryProposalAdminCreateAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, actor_id, memory_id):
        actor = _actor(self, actor_id)
        entry = get_object_or_404(
            AgentMemoryEntry.objects,
            workspace__slug=slug,
            actor=actor,
            pk=memory_id,
        )
        serializer = AgentMemoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if values["key"] != entry.key:
            return _validation_error(ValueError("proposal key must match the addressed memory entry"))
        gardener_id = request.data.get("gardener_id")
        if not gardener_id:
            return _validation_error(ValueError("gardener_id is required"))
        gardener = _actor(self, gardener_id)
        values.pop("subject_user_id", None)
        for field in ("kind", "visibility", "provenance", "provenance_ref", "retention_expires_at"):
            values.pop(field, None)
        try:
            proposal = propose_memory_change(
                actor,
                gardener=gardener,
                idempotency_key=request.data.get("idempotency_key"),
                created_by=request.user,
                **values,
                rationale=request.data.get("rationale", "Gardener proposal"),
            )
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentChangeProposalAdminSerializer(proposal).data, status=status.HTTP_201_CREATED)


class AgentMemoryRollbackAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, actor_id, memory_id):
        entry = get_object_or_404(
            AgentMemoryEntry.all_objects,
            workspace__slug=slug,
            actor_id=actor_id,
            pk=memory_id,
        )
        serializer = AgentRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revision = get_object_or_404(
            AgentMemoryRevision.all_objects,
            workspace__slug=slug,
            entry=entry,
            pk=serializer.validated_data["revision_id"],
        )
        try:
            restored = rollback_memory(
                entry,
                to_revision=revision,
                reviewer=request.user,
                rationale=serializer.validated_data["rationale"],
            )
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentMemoryRevisionAdminSerializer(restored).data)


class AgentSkillAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        queryset = AgentSkillDefinition.objects.filter(actor=actor, deleted_at__isnull=True).order_by("key", "id")
        return self.paginate_admin(request, queryset, AgentSkillAdminSerializer)

    def post(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        serializer = AgentSkillCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        subject_user = values.pop("subject_user_id", None)
        if subject_user is not None:
            subject_user = _workspace_user(self, subject_user)
        try:
            definition = create_skill(actor, subject_user=subject_user, created_by=request.user, **values)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentSkillAdminSerializer(definition).data, status=status.HTTP_201_CREATED)


class AgentSkillRevisionAdminListAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id, skill_id):
        definition = get_object_or_404(
            AgentSkillDefinition.all_objects,
            workspace__slug=slug,
            actor_id=actor_id,
            pk=skill_id,
        )
        queryset = AgentSkillRevision.all_objects.filter(definition=definition).order_by("-revision", "-id")
        return self.paginate_admin(request, queryset, AgentSkillRevisionAdminSerializer)


class AgentSkillProposalAdminCreateAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, actor_id, skill_id):
        actor = _actor(self, actor_id)
        definition = get_object_or_404(
            AgentSkillDefinition.objects,
            workspace__slug=slug,
            actor=actor,
            pk=skill_id,
        )
        serializer = AgentSkillCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if values["key"] != definition.key:
            return _validation_error(ValueError("proposal key must match the addressed skill definition"))
        gardener_id = request.data.get("gardener_id")
        if not gardener_id:
            return _validation_error(ValueError("gardener_id is required"))
        gardener = _actor(self, gardener_id)
        for field in (
            "display_name",
            "description",
            "subject_user_id",
            "provenance",
            "provenance_ref",
            "retention_expires_at",
        ):
            values.pop(field, None)
        try:
            proposal = propose_skill_change(
                actor,
                gardener=gardener,
                requested_visibility=values.pop("visibility"),
                idempotency_key=request.data.get("idempotency_key"),
                created_by=request.user,
                **values,
                rationale=request.data.get("rationale", "Gardener proposal"),
            )
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentChangeProposalAdminSerializer(proposal).data, status=status.HTTP_201_CREATED)


class AgentSkillRollbackAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, actor_id, skill_id):
        definition = get_object_or_404(
            AgentSkillDefinition.all_objects,
            workspace__slug=slug,
            actor_id=actor_id,
            pk=skill_id,
        )
        serializer = AgentRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revision = get_object_or_404(
            AgentSkillRevision.all_objects,
            workspace__slug=slug,
            definition=definition,
            pk=serializer.validated_data["revision_id"],
        )
        try:
            restored = rollback_skill(
                definition,
                to_revision=revision,
                reviewer=request.user,
                rationale=serializer.validated_data["rationale"],
            )
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentSkillRevisionAdminSerializer(restored).data)


class AgentProposalAdminListAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        queryset = AgentChangeProposal.objects.filter(workspace__slug=slug).order_by("-created_at", "-id")
        return self.paginate_admin(request, queryset, AgentChangeProposalAdminSerializer)


class AgentProposalReviewAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        proposal = get_object_or_404(AgentChangeProposal, workspace__slug=slug, pk=pk)
        serializer = AgentProposalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reviewed = review_proposal(
                proposal,
                reviewer=request.user,
                approve=serializer.validated_data["approve"],
                note=serializer.validated_data["note"],
            )
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentChangeProposalAdminSerializer(reviewed).data)


class AgentProposalPromoteAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        proposal = get_object_or_404(AgentChangeProposal, workspace__slug=slug, pk=pk)
        try:
            promoted = promote_proposal(proposal, reviewer=request.user)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        serializer = (
            AgentSkillRevisionAdminSerializer
            if isinstance(promoted, AgentSkillRevision)
            else AgentMemoryRevisionAdminSerializer
        )
        return Response(serializer(promoted).data)


class AgentScheduleAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        queryset = AgentSchedule.objects.filter(actor=actor).order_by("next_fire_at", "name", "id")
        return self.paginate_admin(request, queryset, AgentScheduleAdminSerializer)

    def post(self, request, slug, actor_id):
        actor = _actor(self, actor_id)
        serializer = AgentScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            schedule = create_schedule(actor, **serializer.validated_data)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentScheduleAdminSerializer(schedule).data, status=status.HTTP_201_CREATED)


class AgentScheduleFireListAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, schedule_id):
        schedule = get_object_or_404(AgentSchedule, workspace__slug=slug, pk=schedule_id)
        return self.paginate_admin(
            request,
            AgentScheduleFire.objects.filter(schedule=schedule).order_by("-scheduled_for", "-id"),
            AgentScheduleFireAdminSerializer,
        )

    def post(self, request, slug, schedule_id):
        schedule = get_object_or_404(AgentSchedule, workspace__slug=slug, pk=schedule_id)
        serializer = AgentScheduleFireSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fire = fire_schedule(schedule, created_by=request.user, **serializer.validated_data)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentScheduleFireAdminSerializer(fire).data, status=status.HTTP_201_CREATED)


class AgentScheduleControlAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, schedule_id):
        schedule = get_object_or_404(AgentSchedule, workspace__slug=slug, pk=schedule_id)
        serializer = AgentScheduleControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            schedule = transition_schedule(schedule, serializer.validated_data["state"])
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentScheduleAdminSerializer(schedule).data)


class AgentScheduleFireRetryAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        fire = get_object_or_404(AgentScheduleFire, workspace__slug=slug, pk=pk)
        try:
            retried = retry_schedule_fire(fire, created_by=request.user)
        except (ValidationError, ValueError) as exc:
            return _validation_error(exc)
        return Response(AgentScheduleFireAdminSerializer(retried).data)

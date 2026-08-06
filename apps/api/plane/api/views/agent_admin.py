# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""API-first administration for the Plane-owned Agent records."""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.agent.administration import AgentAdminExtensionCommand, AgentAdminExtensionError, update_actor
from plane.agent.administration_extensions import build_governance_readback, plane_agent_admin_extension
from plane.agent.operations_readback import (
    build_canary_readback,
    build_health_readback,
    build_operator_readback,
    build_safety_stop_command,
)
from plane.agent.readback import AgentReadbackTooLarge, build_run_readback, validate_readback_limit
from plane.agent.validation import MAX_AGENT_READBACK_BYTES
from plane.agent.lifecycle import (
    AgentDomainError,
    IdempotencyConflictError,
    accept_outcome,
    cancel_assignment,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    propose_outcome,
    record_input_event,
    record_invocation,
    request_revision,
    review_outcome,
)
from plane.api.serializers import (
    AgentActorAdminSerializer,
    AgentActorCreateSerializer,
    AgentActorPatchSerializer,
    AssignmentAdminSerializer,
    AssignmentCreateSerializer,
    DispatchSerializer,
    GatewayReadbackSerializer,
    InputEventCreateSerializer,
    OutcomeAdminSerializer,
    OutcomeCreateSerializer,
    OutcomeDecisionSerializer,
    OutcomeReviewSerializer,
    ProfileVersionAdminSerializer,
    ProfileVersionCreateSerializer,
    RunAdminSerializer,
    RunInputEventAdminSerializer,
    RuntimeInvocationAdminSerializer,
    AgentGovernanceCommandSerializer,
)
from plane.api.serializers.agent_admin import AgentOperatorReadbackSerializer, AgentSafetyStopSerializer
from plane.api.views.base import BaseAPIView
from plane.db.models import (
    AgentActor,
    AssignmentContract,
    OutcomeSubmission,
    ProfileVersion,
    Project,
    RunAttempt,
    RunInputEvent,
    RuntimeInvocation,
    Workspace,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency
from plane.utils.permissions import WorkspaceOwnerPermission


class AgentAdminAPIView(BaseAPIView):
    permission_classes = [WorkspaceOwnerPermission]
    use_read_replica = False

    @property
    def workspace_slug(self):
        return self.kwargs["slug"]

    def handle_exception(self, exc):
        if isinstance(exc, IdempotencyConflictError):
            return Response(
                {"error": {"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)}},
                status=status.HTTP_409_CONFLICT,
            )
        if isinstance(exc, AgentReadbackTooLarge):
            return Response(
                {"error": {"code": "READBACK_TOO_LARGE", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, AgentAdminExtensionError):
            return Response(
                {"error": {"code": "GOVERNANCE_UNAVAILABLE", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        try:
            response_size = len(response.rendered_content)
        except Exception:
            response_size = MAX_AGENT_READBACK_BYTES + 1
        if response_size > MAX_AGENT_READBACK_BYTES:
            response = Response(
                {"error": {"code": "READBACK_TOO_LARGE", "message": "The Agent readback exceeds its bound."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
            response = super().finalize_response(request, response, *args, **kwargs)
        return response

    def workspace(self):
        return get_object_or_404(Workspace, slug=self.kwargs["slug"])

    def actor(self):
        return get_object_or_404(
            AgentActor.objects.select_related("active_profile", "project"),
            workspace__slug=self.kwargs["slug"],
            pk=self.kwargs["pk"],
        )

    def assignment(self, *, key="pk"):
        return get_object_or_404(
            AssignmentContract.objects.select_related("assignee"),
            workspace__slug=self.kwargs["slug"],
            pk=self.kwargs[key],
        )

    def run(self):
        return get_object_or_404(
            RunAttempt.objects.select_related("assignment", "actor", "profile_version"),
            workspace__slug=self.kwargs["slug"],
            pk=self.kwargs["pk"],
        )

    def outcome(self):
        return get_object_or_404(
            OutcomeSubmission.objects.select_related("run"),
            workspace__slug=self.kwargs["slug"],
            pk=self.kwargs["pk"],
        )

    def paginate_admin(self, request, queryset, serializer):
        return self.paginate(
            request=request,
            queryset=queryset,
            default_per_page=50,
            max_per_page=100,
            on_results=lambda rows: serializer(rows, many=True).data,
        )


class AgentActorAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        queryset = AgentActor.objects.filter(workspace__slug=slug).select_related("active_profile", "project")
        project_id = request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return self.paginate_admin(request, queryset, AgentActorAdminSerializer)

    def post(self, request, slug):
        serializer = AgentActorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = self.workspace()
        project = None
        if serializer.validated_data.get("project_id") is not None:
            project = get_object_or_404(
                Project,
                pk=serializer.validated_data["project_id"],
                workspace=workspace,
            )
        actor = create_actor(
            workspace=workspace,
            project=project,
            display_name=serializer.validated_data["display_name"],
            credential_ref=serializer.validated_data.get("credential_ref"),
            created_by=request.user,
        )
        return Response(AgentActorAdminSerializer(actor).data, status=status.HTTP_201_CREATED)


class AgentActorAdminDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, pk):
        return Response(AgentActorAdminSerializer(self.actor()).data)

    def patch(self, request, slug, pk):
        serializer = AgentActorPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        actor = update_actor(self.actor(), updated_by=request.user, **values)
        return Response(AgentActorAdminSerializer(actor).data)


class AgentProfileVersionAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = get_object_or_404(AgentActor, workspace__slug=slug, pk=actor_id)
        queryset = ProfileVersion.objects.filter(actor=actor).order_by("-version")
        return self.paginate_admin(request, queryset, ProfileVersionAdminSerializer)

    def post(self, request, slug, actor_id):
        actor = get_object_or_404(AgentActor, workspace__slug=slug, pk=actor_id)
        serializer = ProfileVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = create_profile(actor, created_by=request.user, **serializer.validated_data)
        return Response(ProfileVersionAdminSerializer(profile).data, status=status.HTTP_201_CREATED)


class AgentProfileVersionAdminDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id, pk):
        profile = get_object_or_404(ProfileVersion, workspace__slug=slug, actor_id=actor_id, pk=pk)
        return Response(ProfileVersionAdminSerializer(profile).data)


class AgentAssignmentAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = get_object_or_404(AgentActor, workspace__slug=slug, pk=actor_id)
        queryset = AssignmentContract.objects.filter(assignee=actor).select_related("assignee")
        return self.paginate_admin(request, queryset, AssignmentAdminSerializer)

    def post(self, request, slug, actor_id):
        actor = get_object_or_404(AgentActor, workspace__slug=slug, pk=actor_id)
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = create_assignment(actor, created_by=request.user, **serializer.validated_data)
        return Response(AssignmentAdminSerializer(assignment).data, status=status.HTTP_201_CREATED)


class AgentAssignmentAdminDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, pk):
        return Response(AssignmentAdminSerializer(self.assignment()).data)


class AgentAssignmentCancelAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, assignment_id):
        assignment = self.assignment(key="assignment_id")
        cancelled = cancel_assignment(assignment, operator=request.user)
        return Response(AssignmentAdminSerializer(cancelled).data)


class AgentAssignmentDispatchAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, assignment_id):
        serializer = DispatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = self.assignment(key="assignment_id")
        values = serializer.validated_data
        profile = assignment.assignee.active_profile
        if values.get("profile_version_id"):
            profile = get_object_or_404(
                ProfileVersion,
                pk=values["profile_version_id"],
                actor=assignment.assignee,
                workspace__slug=slug,
            )
        if profile is None:
            raise AgentDomainError("The Agent actor must have an active profile before dispatch")
        input_event = None
        if values.get("input_event_id"):
            raise AgentDomainError("Dispatch input events require an existing run invocation")
        with transaction.atomic():
            run = create_run(
                assignment,
                profile,
                idempotency_key=values["idempotency_key"],
                lineage_of=self._run_or_none(values.get("lineage_of_id"), slug),
                lineage_reason=values.get("lineage_reason"),
                recovery_of=self._run_or_none(values.get("recovery_of_id"), slug),
                recovery_intent=values.get("recovery_intent"),
                created_by=request.user,
            )
            invocation = record_invocation(
                run,
                idempotency_key=values["idempotency_key"],
                trigger=values.get("trigger"),
                input_event=input_event,
                usage=values.get("usage"),
                created_by=request.user,
            )
        return Response(
            {
                "run": RunAdminSerializer(run).data,
                "invocation": RuntimeInvocationAdminSerializer(invocation).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _run_or_none(self, value, slug):
        if value is None:
            return None
        return get_object_or_404(RunAttempt, pk=value, workspace__slug=slug)


class AgentRunAdminDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, pk):
        run = self.run()
        limit = self.get_per_page(request, default_per_page=50, max_per_page=100)
        return Response(build_run_readback(run, limit=limit))


class AgentRunInputEventAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        return self.paginate_admin(
            request,
            RunInputEvent.objects.filter(run=run),
            RunInputEventAdminSerializer,
        )

    def post(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        serializer = InputEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = record_input_event(run, created_by=request.user, **serializer.validated_data)
        return Response(RunInputEventAdminSerializer(event).data, status=status.HTTP_201_CREATED)


class AgentRunInvocationAdminListCreateAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        return self.paginate_admin(
            request,
            RuntimeInvocation.objects.filter(run=run),
            RuntimeInvocationAdminSerializer,
        )

    def post(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        serializer = DispatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        input_event = None
        if values.get("input_event_id"):
            input_event = get_object_or_404(
                RunInputEvent,
                pk=values["input_event_id"],
                run=run,
            )
        invocation = record_invocation(
            run,
            idempotency_key=values["idempotency_key"],
            trigger=values.get("trigger"),
            input_event=input_event,
            usage=values.get("usage"),
            created_by=request.user,
        )
        return Response(RuntimeInvocationAdminSerializer(invocation).data, status=status.HTTP_201_CREATED)


class AgentRunCancelAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        reason = request.data.get("reason", "Cancelled by an administrator")
        if not run.last_invocation_id:
            raise AgentDomainError("A run can be cancelled only after an invocation exists")
        invocation = get_object_or_404(RuntimeInvocation, run=run, invocation_id=run.last_invocation_id)
        from plane.agent.runtime import request_runtime_cancellation

        request_runtime_cancellation(invocation, reason=reason, operator=request.user)
        run.refresh_from_db()
        return Response(RunAdminSerializer(run).data)


class AgentOutcomeAdminCreateAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, run_id):
        run = get_object_or_404(RunAttempt, workspace__slug=slug, pk=run_id)
        serializer = OutcomeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        outcome = propose_outcome(run, created_by=request.user, **serializer.validated_data)
        return Response(OutcomeAdminSerializer(outcome).data, status=status.HTTP_201_CREATED)


class AgentOutcomeAdminDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, pk):
        return Response(OutcomeAdminSerializer(self.outcome()).data)


class AgentOutcomeReviewAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        outcome = self.outcome()
        serializer = OutcomeReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evaluator = get_object_or_404(
            AgentActor,
            workspace__slug=slug,
            pk=serializer.validated_data["evaluator_id"],
        )
        reviewed = review_outcome(
            outcome,
            evaluator=evaluator,
            feedback=serializer.validated_data["feedback"],
        )
        return Response(OutcomeAdminSerializer(reviewed).data)


class AgentOutcomeAcceptAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        outcome = self.outcome()
        serializer = OutcomeDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accepted = accept_outcome(
            outcome,
            human_reviewer=request.user,
            decision_note=serializer.validated_data["decision_note"],
        )
        return Response(OutcomeAdminSerializer(accepted).data)


class AgentOutcomeRevisionAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug, pk):
        outcome = self.outcome()
        serializer = OutcomeDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revised = request_revision(
            outcome,
            human_reviewer=request.user,
            decision_note=serializer.validated_data["decision_note"],
        )
        return Response(OutcomeAdminSerializer(revised).data)


class AgentGatewayReadbackListAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        limit = self.get_per_page(request, default_per_page=50, max_per_page=100)
        queryset = OperationGatewayIdempotency.objects.filter(workspace_slug=slug).order_by("-created_at")
        for field in ("operation_id", "idempotency_key", "caller_id", "state"):
            if request.query_params.get(field):
                queryset = queryset.filter(**{field: request.query_params[field]})
        return self.paginate(
            request=request,
            queryset=queryset,
            default_per_page=50,
            max_per_page=100,
            on_results=lambda receipts: [self._readback(receipt, limit=limit) for receipt in receipts],
        )

    def _readback(self, receipt, *, limit=100):
        audit = OperationGatewayAudit.objects.filter(
            workspace_id=receipt.workspace_id,
            workspace_slug=receipt.workspace_slug,
            request_id=receipt.request_id,
            invocation_id=receipt.invocation_id,
            caller_id=receipt.caller_id,
            operation_id=receipt.operation_id,
            idempotency_key=receipt.idempotency_key,
            correlation_id=receipt.correlation_id,
            request_digest=receipt.request_digest,
        ).order_by("created_at", "id")[:limit]
        return GatewayReadbackSerializer({"receipt": receipt, "audit": audit}).data


class AgentGatewayReadbackDetailAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, pk):
        limit = self.get_per_page(request, default_per_page=50, max_per_page=100)
        receipt = get_object_or_404(OperationGatewayIdempotency, workspace_slug=slug, pk=pk)
        audit = OperationGatewayAudit.objects.filter(
            workspace_id=receipt.workspace_id,
            workspace_slug=receipt.workspace_slug,
            request_id=receipt.request_id,
            invocation_id=receipt.invocation_id,
            caller_id=receipt.caller_id,
            operation_id=receipt.operation_id,
            idempotency_key=receipt.idempotency_key,
            correlation_id=receipt.correlation_id,
            request_digest=receipt.request_digest,
        ).order_by("created_at", "id")[:limit]
        return Response(GatewayReadbackSerializer({"receipt": receipt, "audit": audit}).data)


class AgentGovernanceReadbackAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        workspace = self.workspace()
        raw_limit = request.query_params.get("limit") or request.query_params.get("per_page")
        if raw_limit is None:
            limit = 50
        else:
            try:
                limit = validate_readback_limit(int(raw_limit))
            except (TypeError, ValueError) as exc:
                raise AgentAdminExtensionError(str(exc)) from exc
        return Response(
            build_governance_readback(
                workspace,
                limit=limit,
                resource_id=request.query_params.get("resource_id"),
            )
        )


class AgentGovernanceCommandAPIEndpoint(AgentAdminAPIView):
    def post(self, request, slug):
        serializer = AgentGovernanceCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            command = AgentAdminExtensionCommand(
                action=values["action"],
                workspace_id=str(self.workspace().id),
                actor_id=str(values["actor_id"]) if values.get("actor_id") else None,
                run_id=str(values["run_id"]) if values.get("run_id") else None,
                invocation_id=str(values["invocation_id"]) if values.get("invocation_id") else None,
                idempotency_key=values["idempotency_key"],
                payload=values.get("payload", {}),
                authenticated_user=request.user,
            )
        except ValueError as exc:
            raise AgentAdminExtensionError(str(exc)) from exc
        return Response(plane_agent_admin_extension().execute(command))


class AgentOperatorReadbackAPIEndpoint(AgentAdminAPIView):
    """API projection shared with ``agent_operator_readback``."""

    def get(self, request, slug):
        serializer = AgentOperatorReadbackSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        return Response(
            build_operator_readback(
                self.workspace(),
                limit=values["limit"],
                cursor=values.get("cursor"),
                run_id=str(values["run_id"]) if values.get("run_id") else None,
                correlation_id=values.get("correlation_id"),
                canary_mode=values["canary_mode"],
            )
        )


class AgentOperatorHealthAPIEndpoint(AgentAdminAPIView):
    """Small production-readiness projection using the runtime-owned adapter."""

    def get(self, request, slug):
        serializer = AgentOperatorReadbackSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(build_health_readback(self.workspace(), limit=serializer.validated_data["limit"]))


class AgentOperatorCanaryAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        mode = request.query_params.get("mode", "offline")
        try:
            return Response(build_canary_readback(mode=mode))
        except ValueError as exc:
            return Response({"error": {"code": "CANARY_INVALID", "message": str(exc)}}, status=400)


class AgentOperatorSafetyStopAPIEndpoint(AgentAdminAPIView):
    """Delegate one targeted stop; no global or local stop state is stored here."""

    def post(self, request, slug):
        serializer = AgentSafetyStopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        workspace = self.workspace()
        invocation_id = values.get("invocation_id")
        if invocation_id is None:
            run = get_object_or_404(RunAttempt, workspace=workspace, pk=values["run_id"])
            invocation_id = run.last_invocation_id
            if not invocation_id:
                return Response(
                    {"error": {"code": "SAFETY_STOP_UNAVAILABLE", "message": "The run has no active invocation."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if not RuntimeInvocation.objects.filter(run__workspace=workspace, invocation_id=invocation_id).exists():
            return Response(
                {"error": {"code": "SAFETY_STOP_UNAVAILABLE", "message": "The invocation is unavailable."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = build_safety_stop_command(
            workspace,
            invocation_id=invocation_id,
            reason=values["reason"],
            idempotency_key=values["idempotency_key"],
        )
        if result.get("status") == "external_required":
            return Response({"control": result}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"control": result, "readback": build_operator_readback(workspace, limit=1)})

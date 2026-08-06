"""Typed application adapters for the Plane operation gateway.

These adapters intentionally stop below the HTTP layer.  They call Plane's
serializers, models, permission classes, and small domain helpers directly;
they never invoke a DRF view, construct a loopback request, or dispatch a
generic endpoint path.  The gateway remains responsible for caller binding,
idempotency, result bounds, and durable audit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import serializers

from plane.api.serializers import (
    CycleCreateSerializer,
    CycleSerializer,
    CycleUpdateSerializer,
    IntakeIssueSerializer,
    IntakeIssueUpdateSerializer,
    IssueCommentCreateSerializer,
    IssueCommentSerializer,
    IssueActivitySerializer,
    IssueRelationCreateSerializer,
    IssueRelationSerializer,
    RelatedIssueSerializer,
    IssueLinkCreateSerializer,
    IssueLinkSerializer,
    IssueLinkUpdateSerializer,
    IssueSerializer,
    LabelCreateUpdateSerializer,
    LabelSerializer,
    ModuleCreateSerializer,
    ModuleSerializer,
    ModuleUpdateSerializer,
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
    ProjectMemberLiteAPISerializer,
    StateSerializer,
    WorkspaceMemberLiteAPISerializer,
)
from plane.app.permissions import ProjectEntityPermission, ProjectLitePermission, ProjectPagePermission
from plane.app.permissions.project import ProjectBasePermission, ProjectMemberPermission
from plane.app.permissions.workspace import WorkSpaceAdminPermission, WorkspaceUserPermission
from plane.app.serializers.page import PageDetailSerializer, PageSerializer
from plane.db.models import (
    AgentActor,
    AgentHRProposal,
    AgentRole,
    AssignmentContract,
    Cycle,
    DEFAULT_STATES,
    Intake,
    IntakeIssue,
    Issue,
    IssueComment,
    IssueLink,
    Label,
    Module,
    Page,
    Project,
    ProjectMember,
    State,
    Workspace,
    WorkspaceMember,
    OutcomeSubmission,
    User,
    CycleIssue,
    ModuleIssue,
    IssueRelation,
    IssueActivity,
    UserFavorite,
)
from plane.db.models.intake import SourceType
from plane.utils.content_validator import validate_html_content
from plane.utils.order_queryset import (
    CYCLE_ORDER_BY_ALLOWLIST,
    MODULE_ORDER_BY_ALLOWLIST,
    PROJECT_ORDER_BY_ALLOWLIST,
    sanitize_order_by,
)
from plane.utils.paginator import Cursor, OffsetPaginator

from .catalog import IMPLEMENTED_OPERATION_IDS
from .work_items import (
    WorkItemMutationService,
    WorkItemRenameFailure,
    WorkItemRenameOutcome,
    WorkItemRenameService,
    issue_publication_payload,
)
from plane.utils.cycle_transfer_issues import transfer_cycle_issues
from plane.utils.issue_relation_mapper import get_actual_relation
from plane.utils.host import base_host

from plane.agent.lifecycle import (
    AgentDomainError,
    IdempotencyConflictError,
    InvalidTransitionError,
    TerminalEventRequiredError,
    accept_outcome,
    cancel_assignment,
    decide_hr_proposal,
    delegate_assignment,
    propose_hr_change,
    request_revision,
    review_outcome,
)
from plane.agent.lifecycle.runtime_contract import namespaced_ref


def _plane_ref(value: Any, prefix: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.startswith(f"{prefix}:"):
        raise OperationAdapterFailure("VALIDATION_ERROR")
    raw = value.removeprefix(f"{prefix}:")
    if not raw:
        raise OperationAdapterFailure("VALIDATION_ERROR")
    return raw


def _bound_actor(request: Any, workspace: Workspace, value: Any, *, role: str | None = None) -> AgentActor:
    ref = value if isinstance(value, str) else ""
    if getattr(request, "agent_actor_ref", None) != ref:
        raise OperationAdapterFailure("CALLBACK_BINDING_INVALID", 403)
    try:
        actor = AgentActor.objects.select_related("active_profile").get(
            pk=_plane_ref(ref, "agent-actor", "agent_actor_ref"), workspace=workspace
        )
    except (AgentActor.DoesNotExist, ValueError):
        raise OperationAdapterFailure("CALLBACK_BINDING_INVALID", 403) from None
    if actor.principal_id != request.user.id or not actor.is_active or actor.active_profile_id is None:
        raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
    if role is not None and actor.active_profile.role != role:
        raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
    if not WorkspaceMember.objects.filter(workspace=workspace, member=request.user, is_active=True).exists():
        raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
    return actor


def _human_admin(request: Any, workspace: Workspace) -> None:
    if (
        getattr(request.user, "is_bot", False)
        or not WorkspaceMember.objects.filter(
            workspace=workspace, member=request.user, role__in=[20, 15], is_active=True
        ).exists()
    ):
        raise OperationAdapterFailure("NOT_AUTHORIZED", 403)


def _gateway_key(data: dict[str, Any], prefix: str) -> str:
    raw = str(data.get("_gateway_idempotency_key") or "")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"idempotency:gateway-{prefix}-{digest}"


def _raise_domain_error(error: Exception) -> None:
    if isinstance(error, IdempotencyConflictError):
        raise OperationAdapterFailure("IDEMPOTENCY_CONFLICT", 409) from error
    if isinstance(error, (InvalidTransitionError, AgentDomainError, TerminalEventRequiredError, ValidationError)):
        raise OperationAdapterFailure("PLANE_CONFLICT", 409) from error
    raise error


class OperationAdapterFailure(Exception):
    """A bounded, semantic failure from a direct Plane application adapter."""

    def __init__(self, code: str, http_status: int = 400, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


class OperationRequest:
    """Permission input projection; it is not a DRF view or HTTP request."""

    def __init__(self, request: Any, *, method: str, query: dict[str, Any] | None = None):
        self.user = request.user
        self.method = method
        self.GET = query or {}
        self.query_params = self.GET
        self.META = getattr(request, "META", {})


def _method(action: str) -> str:
    return {
        "list": "GET",
        "retrieve": "GET",
        "create": "POST",
        "update": "PATCH",
        "delete": "DELETE",
    }[action]


def _query_data(data: dict[str, Any]) -> dict[str, Any]:
    params = data.get("params")
    query = dict(params) if isinstance(params, dict) else {}
    query.update({key: value for key, value in data.items() if key != "params" and value is not None})
    return query


def _fields(data: dict[str, Any]) -> tuple[str, ...]:
    value = _query_data(data).get("fields")
    if isinstance(value, str):
        return tuple(field for field in value.split(",") if field)
    if isinstance(value, (list, tuple)):
        return tuple(str(field) for field in value)
    return ()


def _expand(data: dict[str, Any]) -> tuple[str, ...]:
    value = _query_data(data).get("expand")
    if isinstance(value, str):
        return tuple(field for field in value.split(",") if field)
    if isinstance(value, (list, tuple)):
        return tuple(str(field) for field in value)
    return ()


def _bounded_page(queryset: Any, data: dict[str, Any], *, default_order: str, allowed_order: Any) -> dict[str, Any]:
    query = _query_data(data)
    raw_per_page = query.get("per_page", 1000)
    try:
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        raise OperationAdapterFailure("VALIDATION_ERROR") from None
    if per_page < 1 or per_page > 1000:
        raise OperationAdapterFailure("VALIDATION_ERROR")
    order_by = sanitize_order_by(query.get("order_by"), allowed_order, default=default_order)
    try:
        cursor = Cursor.from_string(query["cursor"]) if query.get("cursor") else Cursor(0, 0, 0)
        result = OffsetPaginator(queryset, order_by=order_by, max_limit=1000).get_result(
            limit=per_page,
            cursor=cursor,
        )
    except (TypeError, ValueError):
        raise OperationAdapterFailure("VALIDATION_ERROR") from None
    return {
        "results": result.results,
        "next_cursor": str(result.next),
        "prev_cursor": str(result.prev),
        "next_page_results": bool(result.next),
        "prev_page_results": bool(result.prev),
        "count": len(result),
        "total_results": result.hits,
        "total_pages": result.max_hits,
    }


def _permission_view(workspace: Workspace, data: dict[str, Any], *, resource_id: str | None = None) -> Any:
    kwargs = {"slug": workspace.slug}
    if data.get("project_id") is not None:
        kwargs["project_id"] = str(data["project_id"])
    if resource_id is not None:
        kwargs["page_id"] = str(resource_id)
    return SimpleNamespace(
        workspace_slug=workspace.slug,
        project_id=str(data["project_id"]) if data.get("project_id") is not None else None,
        kwargs=kwargs,
    )


def _authorize(
    permission_class: type,
    request: Any,
    workspace: Workspace,
    data: dict[str, Any],
    action: str,
    *,
    resource_id: str | None = None,
) -> bool:
    return bool(
        permission_class().has_permission(
            OperationRequest(request, method=_method(action), query=_query_data(data)),
            _permission_view(workspace, data, resource_id=resource_id),
        )
    )


def _serializer_data(data: dict[str, Any], *, drop: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in drop and value is not None}


def _bind_audit_actor(instance: Any, actor_id: Any, *, created: bool) -> None:
    """Persist the gateway caller without allowing BaseModel auto-user lookup to clear it."""

    update_fields = ["updated_by"]
    instance.updated_by_id = actor_id
    if created:
        instance.created_by_id = actor_id
        update_fields.insert(0, "created_by")
    instance.save(update_fields=update_fields, disable_auto_set_user=True)


def _model_publication_payload(
    *,
    request: Any,
    workspace: Workspace,
    model_name: str,
    model_id: str,
    requested_data: dict[str, Any],
    current_instance: dict[str, Any] | None,
    deleted: bool = False,
) -> dict[str, Any]:
    return {
        "model_activity": {
            "model_name": model_name,
            "model_id": str(model_id),
            "requested_data": requested_data,
            "current_instance": None
            if deleted
            else (json.dumps(current_instance) if current_instance is not None else None),
            "actor_id": str(request.user.id),
            "slug": workspace.slug,
            "origin": base_host(request=request, is_app=True),
            "verb": "deleted" if deleted else None,
            "deleted": deleted,
        }
    }


def _non_issue_activity_publication_payload(
    *,
    request: Any,
    workspace: Workspace,
    project_id: str,
    event_type: str,
    requested_data: dict[str, Any],
    current_instance: dict[str, Any] | None,
) -> dict[str, Any]:
    requested_json = json.dumps(requested_data)
    current_json = json.dumps(current_instance) if current_instance is not None else None
    return {
        "activity": {
            "type": event_type,
            "requested_data": requested_json,
            "actor_id": str(request.user.id),
            "issue_id": None,
            "project_id": str(project_id),
            "current_instance": current_json,
            "epoch": int(timezone.now().timestamp()),
            "origin": base_host(request=request, is_app=True),
            "expected": True,
            "deterministic_activity": False,
        },
        "notification": {
            "skip": True,
            "type": event_type,
            "issue_id": None,
            "project_id": str(project_id),
            "actor_id": str(request.user.id),
            "requested_data": requested_json,
            "current_instance": current_json,
        },
        "webhook": {"skip": True},
    }


@dataclass(frozen=True)
class ResourceSpec:
    prefix: str
    model: type
    read_serializer: type
    create_serializer: type
    update_serializer: type
    id_field: str
    permission_class: type
    scope: str = "project"
    order_by: Any = frozenset({"created_at", "updated_at", "name"})
    default_order: str = "-created_at"
    list_filter: str | None = None
    list_result_key: str | None = None


class ResourceOperation:
    """Serializer-backed resource family with explicit model scoping."""

    def __init__(self, spec: ResourceSpec, action: str):
        self.spec = spec
        self.action = action

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        resource_id = data.get(self.spec.id_field)
        if self.spec.scope == "workspace" and self.spec.prefix == "project":
            return _authorize(ProjectBasePermission, request, workspace, data, self.action, resource_id=resource_id)
        return _authorize(
            self.spec.permission_class,
            request,
            workspace,
            data,
            self.action,
            resource_id=resource_id,
        )

    def _queryset(self, workspace: Workspace, data: dict[str, Any]) -> Any:
        queryset = self.spec.model.objects.filter(workspace_id=workspace.id)
        if self.spec.scope == "project":
            queryset = queryset.filter(project_id=data["project_id"])
        elif self.spec.prefix == "project" and data.get("project_id"):
            queryset = queryset.filter(pk=data["project_id"])
        if self.spec.list_filter:
            queryset = queryset.filter(**{self.spec.list_filter: False})
        if self.spec.prefix == "project":
            queryset = queryset.filter(
                Q(project_projectmember__member_id=data.get("_caller_id"), project_projectmember__is_active=True)
                | Q(network=2)
            ).distinct()
        if self.spec.prefix in {"cycle", "module"} and not data.get("archived", False):
            queryset = queryset.filter(archived_at__isnull=True)
        if self.spec.prefix == "cycle" and data.get("status"):
            now = timezone.now()
            status = data["status"]
            if status == "current":
                queryset = queryset.filter(start_date__lte=now, end_date__gte=now)
            elif status == "upcoming":
                queryset = queryset.filter(start_date__gt=now)
            elif status == "completed":
                queryset = queryset.filter(end_date__lt=now)
            elif status == "draft":
                queryset = queryset.filter(start_date__isnull=True, end_date__isnull=True)
            elif status == "incomplete":
                queryset = queryset.filter(Q(end_date__gte=now) | Q(end_date__isnull=True))
            elif status != "all":
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
        if self.spec.prefix == "state":
            queryset = queryset.filter(is_triage=False).filter(project__archived_at__isnull=True)
        if self.spec.prefix in {"link", "comment"}:
            queryset = queryset.filter(issue_id=data["issue_id"], project__archived_at__isnull=True)
        if self.spec.prefix == "intake":
            queryset = queryset.filter(project__archived_at__isnull=True)
        return queryset

    def _instance(self, workspace: Workspace, data: dict[str, Any]) -> Any:
        resource_id = data.get(self.spec.id_field)
        if not resource_id:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        instance = self._queryset(workspace, data).filter(pk=resource_id).first()
        if instance is None:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        return instance

    def _context(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> dict[str, Any]:
        context = {
            "request": request,
            "workspace_id": str(workspace.id),
        }
        if data.get("project_id") is not None:
            context["project_id"] = str(data["project_id"])
            context["project"] = Project.objects.filter(pk=data["project_id"], workspace_id=workspace.id).first()
        return context

    def _serialize(self, instance: Any, data: dict[str, Any]) -> dict[str, Any]:
        return self.spec.read_serializer(instance, fields=_fields(data), expand=_expand(data)).data

    def execute(
        self,
        request: Any,
        workspace: Workspace,
        data: dict[str, Any],
    ) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
        data = {**data, "_caller_id": str(request.user.id)}
        if self.action == "list":
            queryset = self._queryset(workspace, data)
            page = _bounded_page(
                queryset, data, default_order=self.spec.default_order, allowed_order=self.spec.order_by
            )
            page["results"] = [self._serialize(instance, data) for instance in page["results"]]
            return 200, page, None
        if self.action == "retrieve":
            return 200, self._serialize(self._instance(workspace, data), data), None
        if self.action == "create":
            if self.spec.prefix == "cycle" and bool(data.get("start_date")) != bool(data.get("end_date")):
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            drop_fields = {
                "project_id",
                "_caller_id",
                self.spec.id_field,
                "cursor",
                "per_page",
                "order_by",
                "fields",
                "expand",
                "params",
            }
            if self.spec.prefix == "comment":
                drop_fields.add("issue_id")
            body = _serializer_data(data, drop=drop_fields)
            serializer = self.spec.create_serializer(data=body, context=self._context(request, workspace, data))
            publication = self._save(serializer, request, workspace, data, create=True)
            return 201, self._serialize(serializer.instance, data), publication
        if self.action == "update":
            instance = self._instance(workspace, data)
            current_instance = self._serialize(instance, data)
            drop_fields = {
                "project_id",
                self.spec.id_field,
                "_caller_id",
                "cursor",
                "per_page",
                "order_by",
                "fields",
                "expand",
                "params",
            }
            if self.spec.prefix == "comment":
                drop_fields.add("issue_id")
            body = _serializer_data(data, drop=drop_fields)
            serializer = self.spec.update_serializer(
                instance,
                data=body,
                partial=True,
                context=self._context(request, workspace, data),
            )
            publication = self._save(
                serializer, request, workspace, data, create=False, current_instance=current_instance
            )
            return 200, self._serialize(serializer.instance, data), publication
        if self.action == "delete":
            return self._delete(request, workspace, data)
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)

    def _save(
        self,
        serializer: Any,
        request: Any,
        workspace: Workspace,
        data: dict[str, Any],
        *,
        create: bool,
        current_instance: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not serializer.is_valid():
            raise OperationAdapterFailure("VALIDATION_ERROR", 400)
        if self.spec.prefix in {"comment", "label"}:
            external_id = serializer.validated_data.get("external_id")
            external_source = serializer.validated_data.get("external_source")
            if external_id and external_source:
                duplicate = self.spec.model.objects.filter(
                    project_id=data["project_id"],
                    external_id=external_id,
                    external_source=external_source,
                )
                if not create:
                    duplicate = duplicate.exclude(pk=serializer.instance.pk)
                if duplicate.exists():
                    raise OperationAdapterFailure("PLANE_CONFLICT", 409)
        kwargs = {"created_by_id" if create else "updated_by_id": request.user.id}
        if self.spec.scope == "project":
            kwargs["project_id"] = data["project_id"]
        if self.spec.prefix in {"link", "comment"}:
            kwargs["issue_id"] = data["issue_id"]
            if self.spec.prefix == "comment" and create:
                kwargs["actor"] = request.user
        elif self.spec.prefix == "label":
            kwargs["project_id"] = data.get("project_id")
            kwargs["workspace_id"] = workspace.id
        elif self.spec.prefix == "project":
            kwargs["workspace_id"] = workspace.id
        if create and self.spec.prefix in {"module", "project"}:
            # These canonical serializers inject their scope inside create().
            kwargs.pop("project_id", None)
            kwargs.pop("workspace_id", None)
        try:
            if self.spec.prefix == "project" and create:
                with transaction.atomic():
                    serializer.save(**kwargs)
                    project_member = ProjectMember.objects.create(
                        project_id=serializer.instance.id,
                        member_id=request.user.id,
                        role=20,
                        created_by_id=request.user.id,
                    )
                    _bind_audit_actor(project_member, request.user.id, created=True)
                    if serializer.instance.project_lead_id and serializer.instance.project_lead_id != request.user.id:
                        lead_member = ProjectMember.objects.create(
                            project_id=serializer.instance.id,
                            member_id=serializer.instance.project_lead_id,
                            role=20,
                            created_by_id=request.user.id,
                        )
                        _bind_audit_actor(lead_member, request.user.id, created=True)
                    State.objects.bulk_create(
                        [
                            State(
                                name=state["name"],
                                color=state["color"],
                                project=serializer.instance,
                                sequence=state["sequence"],
                                workspace=workspace,
                                group=state["group"],
                                default=state.get("default", False),
                                created_by_id=request.user.id,
                            )
                            for state in DEFAULT_STATES
                        ]
                    )
            else:
                serializer.save(**kwargs)
            _bind_audit_actor(serializer.instance, request.user.id, created=create)
        except serializers.ValidationError as failure:
            if self.spec.prefix == "project" and "taken" in str(failure).lower():
                raise OperationAdapterFailure("PLANE_CONFLICT", 409) from None
            raise OperationAdapterFailure("VALIDATION_ERROR", 400) from None
        except IntegrityError:
            raise OperationAdapterFailure("PLANE_CONFLICT", 409) from None
        if self.spec.prefix in {"link", "comment"}:
            issue_id = str(data["issue_id"])
            return issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=issue_id,
                project_id=str(data["project_id"]),
                event_type=f"{self.spec.prefix}.activity.{'created' if create else 'updated'}",
                requested_data=_serializer_data(data, drop={"project_id", "issue_id", self.spec.id_field}),
                current_instance_data=current_instance,
                notification=False,
                deterministic_activity=False,
            )
        return _model_publication_payload(
            request=request,
            workspace=workspace,
            model_name=self.spec.prefix,
            model_id=str(serializer.instance.id),
            requested_data=_serializer_data(data, drop={"project_id", self.spec.id_field}),
            current_instance=current_instance,
        )

    def _delete(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        instance = self._instance(workspace, data)
        current_instance = self._serialize(instance, data)
        prefix = self.spec.prefix
        if prefix == "state":
            if instance.default:
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            if Issue.objects.filter(state_id=instance.id).exists():
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
        if prefix in {"cycle", "module"}:
            creator_id = getattr(instance, "owned_by_id", None) if prefix == "cycle" else instance.created_by_id
            if (
                creator_id != request.user.id
                and not ProjectMember.objects.filter(
                    workspace_id=workspace.id,
                    project_id=data["project_id"],
                    member_id=request.user.id,
                    role=20,
                    is_active=True,
                ).exists()
            ):
                raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
        if prefix == "project":
            UserFavorite.objects.filter(project_id=instance.id, entity_identifier=instance.id).delete()
        if prefix == "cycle":
            UserFavorite.objects.filter(
                entity_type="cycle", entity_identifier=instance.id, project_id=instance.project_id
            ).delete()
        if prefix == "module":
            UserFavorite.objects.filter(
                entity_type="module", entity_identifier=instance.id, project_id=instance.project_id
            ).delete()
        publication = None
        if prefix in {"cycle", "module"}:
            issue_model = CycleIssue if prefix == "cycle" else ModuleIssue
            issue_field = "cycle_id" if prefix == "cycle" else "module_id"
            issue_ids = list(
                issue_model.objects.filter(**{issue_field: instance.id}).values_list("issue_id", flat=True)
            )
            publication = _non_issue_activity_publication_payload(
                request=request,
                workspace=workspace,
                project_id=str(data["project_id"]),
                event_type=f"{prefix}.activity.deleted",
                requested_data={
                    f"{prefix}_id": str(instance.id),
                    f"{prefix}_name": str(instance.name),
                    "issues": [str(issue_id) for issue_id in issue_ids],
                },
                current_instance={"name": str(instance.name)} if prefix == "module" else None,
            )
        if prefix in {"link", "comment"}:
            publication = issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=str(data["issue_id"]),
                project_id=str(data["project_id"]),
                event_type=f"{prefix}.activity.deleted",
                requested_data={self.spec.id_field: str(instance.id)},
                current_instance_data=current_instance,
                notification=False,
                deterministic_activity=False,
            )
        instance.delete()
        if publication is None:
            publication = _model_publication_payload(
                request=request,
                workspace=workspace,
                model_name=prefix,
                model_id=str(instance.id),
                requested_data={"id": str(instance.id)},
                current_instance=current_instance,
                deleted=True,
            )
        return 200, {"deleted": True, "id": str(instance.id)}, publication


class WorkItemReadOperation:
    permission_class = ProjectEntityPermission

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(self.permission_class, request, workspace, data, "retrieve")

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        issue = (
            Issue.objects.filter(
                workspace_id=workspace.id,
                project_id=data["project_id"],
                pk=data["issue_id"],
                project__archived_at__isnull=True,
            )
            .select_related("state", "project", "workspace")
            .first()
        )
        if issue is None:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        fields = ("id", "name", "sequence_id", "priority", "state", "project", "workspace")
        return 200, IssueSerializer(issue, fields=fields).data, None


class WorkItemRenameOperation:
    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(ProjectEntityPermission, request, workspace, data, "update")

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        try:
            outcome = WorkItemRenameService().rename(
                request=request,
                workspace=workspace,
                project_id=str(data["project_id"]),
                issue_id=str(data["issue_id"]),
                name=data["name"],
            )
        except WorkItemRenameFailure as failure:
            raise OperationAdapterFailure(failure.code, failure.http_status, failure.retryable) from None
        if not isinstance(outcome, WorkItemRenameOutcome):
            raise OperationAdapterFailure("UPSTREAM_FAILURE", 503, True)
        return 200, outcome.result, outcome.publication_payload


def _work_item_body(data: dict[str, Any]) -> dict[str, Any]:
    body = _serializer_data(
        data,
        drop={
            "project_id",
            "issue_id",
            "work_item_id",
            "cursor",
            "per_page",
            "order_by",
            "fields",
            "expand",
            "params",
            "query",
            "pql",
        },
    )
    stripped = body.pop("description_stripped", None)
    if body.get("type_id") is None:
        body.pop("type", None)
    else:
        body.pop("type", None)
    if body.get("description_html") is None and stripped is not None:
        from html import escape

        body["description_html"] = f"<p>{escape(stripped).replace(chr(10), '<br/>')}</p>"
    return body


class WorkItemOperation:
    """Typed work-item list/write family backed by the canonical issue serializer."""

    def __init__(self, action: str):
        self.action = action

    def _queryset(self, workspace: Workspace, request: Any, data: dict[str, Any]):
        queryset = (
            Issue.issue_objects.filter(
                workspace_id=workspace.id,
                project__archived_at__isnull=True,
            )
            .filter(
                Q(
                    project__project_projectmember__member_id=request.user.id,
                    project__project_projectmember__is_active=True,
                )
                | Q(project__network=2)
            )
            .distinct()
        )
        if data.get("project_id"):
            queryset = queryset.filter(project_id=data["project_id"])
        query = _query_data(data)
        if query.get("external_id") is not None:
            queryset = queryset.filter(external_id=query["external_id"])
        if query.get("external_source") is not None:
            queryset = queryset.filter(external_source=query["external_source"])
        return queryset.select_related("project", "workspace", "state", "parent").prefetch_related(
            "assignees", "labels"
        )

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        if self.action == "list" or self.action == "search":
            if self.action == "search" and not data.get("project_id"):
                return bool(
                    WorkspaceUserPermission().has_permission(
                        OperationRequest(request, method="GET"), _permission_view(workspace, data)
                    )
                )
            if self.action == "list" and not data.get("project_id"):
                return bool(
                    WorkspaceUserPermission().has_permission(
                        OperationRequest(request, method="GET"), _permission_view(workspace, data)
                    )
                )
            return _authorize(ProjectEntityPermission, request, workspace, data, "list")
        if self.action == "create":
            return _authorize(ProjectEntityPermission, request, workspace, data, "create")
        if self.action in {"retrieve", "update"}:
            return _authorize(
                ProjectEntityPermission,
                request,
                workspace,
                data,
                "retrieve" if self.action == "retrieve" else "update",
                resource_id=data.get("issue_id"),
            )
        if self.action == "delete":
            issue = Issue.objects.filter(
                workspace_id=workspace.id, project_id=data.get("project_id"), pk=data.get("issue_id")
            ).first()
            if issue is None:
                return False
            return bool(
                _authorize(
                    ProjectEntityPermission, request, workspace, data, "delete", resource_id=data.get("issue_id")
                )
                and (
                    issue.created_by_id == request.user.id
                    or ProjectMember.objects.filter(
                        workspace_id=workspace.id,
                        project_id=data.get("project_id"),
                        member_id=request.user.id,
                        role=20,
                        is_active=True,
                    ).exists()
                )
            )
        return False

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        service = WorkItemMutationService()
        if self.action == "list":
            if data.get("pql"):
                raise OperationAdapterFailure("PQL_QUERY_UNSUPPORTED", 400)
            page = _bounded_page(
                self._queryset(workspace, request, data),
                data,
                default_order="-created_at",
                allowed_order={"created_at", "updated_at", "name", "sequence_id", "priority"},
            )
            page["results"] = [
                IssueSerializer(item, fields=_fields(data), expand=_expand(data)).data for item in page["results"]
            ]
            page["total_count"] = page["total_results"]
            return 200, page, None
        if self.action == "retrieve":
            issue = self._queryset(workspace, request, data).filter(pk=data["issue_id"]).first()
            if issue is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            return 200, IssueSerializer(issue, fields=_fields(data), expand=_expand(data)).data, None
        if self.action == "create":
            outcome = service.create(
                request=request,
                workspace=workspace,
                project_id=str(data["project_id"]),
                data=_work_item_body(data),
            )
            return 201, outcome.result, outcome.publication_payload
        if self.action == "update":
            outcome = service.update(
                request=request,
                workspace=workspace,
                project_id=str(data["project_id"]),
                issue_id=str(data["issue_id"]),
                data=_work_item_body(data),
            )
            return 200, outcome.result, outcome.publication_payload
        if self.action == "delete":
            try:
                outcome = service.delete(
                    request=request,
                    workspace=workspace,
                    project_id=str(data["project_id"]),
                    issue_id=str(data["issue_id"]),
                )
            except WorkItemRenameFailure as failure:
                raise OperationAdapterFailure(failure.code, failure.http_status, failure.retryable) from None
            return 200, outcome.result, outcome.publication_payload
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)


class WorkItemSearchOperation:
    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return bool(
            WorkspaceUserPermission().has_permission(
                OperationRequest(request, method="GET"), _permission_view(workspace, data)
            )
        )

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        query = str(data.get("query", "")).strip()
        if not query:
            return 200, {"issues": []}, None
        terms = Q(name__icontains=query) | Q(project__identifier__icontains=query)
        if query.isdigit():
            terms |= Q(sequence_id=int(query))
        queryset = (
            Issue.issue_objects.filter(
                terms,
                workspace_id=workspace.id,
                project__archived_at__isnull=True,
            )
            .filter(
                Q(
                    project__project_projectmember__member_id=request.user.id,
                    project__project_projectmember__is_active=True,
                )
                | Q(project__network=2)
            )
            .distinct()
            .order_by("-updated_at")[:10]
        )
        return (
            200,
            {
                "issues": [
                    {
                        "name": issue.name,
                        "id": str(issue.id),
                        "sequence_id": issue.sequence_id,
                        "project_identifier": issue.project.identifier,
                        "project_id": str(issue.project_id),
                        "workspace_slug": workspace.slug,
                    }
                    for issue in queryset
                ]
            },
            None,
        )


class ActivityOperation:
    def __init__(self, action: str):
        self.action = action

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(ProjectEntityPermission, request, workspace, data, "retrieve")

    def _queryset(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        return (
            IssueActivity.objects.filter(
                workspace_id=workspace.id,
                project_id=data["project_id"],
                issue_id=data["issue_id"],
                project__project_projectmember__member_id=request.user.id,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
            .exclude(field__in=["comment", "vote", "reaction", "draft"])
            .select_related("actor", "workspace", "issue", "project")
        )

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        queryset = self._queryset(request, workspace, data)
        if self.action == "list":
            page = _bounded_page(queryset, data, default_order="created_at", allowed_order={"created_at", "updated_at"})
            return (
                200,
                [
                    IssueActivitySerializer(item, fields=_fields(data), expand=_expand(data)).data
                    for item in page["results"]
                ],
                None,
            )
        activity = queryset.filter(pk=data["activity_id"]).first()
        if activity is None:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        return 200, IssueActivitySerializer(activity, fields=_fields(data), expand=_expand(data)).data, None


class RelationOperation:
    def __init__(self, action: str):
        self.action = action

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(
            ProjectEntityPermission,
            request,
            workspace,
            data,
            "create" if self.action == "create" else "retrieve",
            resource_id=data.get("issue_id"),
        )

    def _source(self, workspace: Workspace, data: dict[str, Any]):
        return Issue.objects.filter(
            workspace_id=workspace.id,
            project_id=data["project_id"],
            pk=data["issue_id"],
            project__archived_at__isnull=True,
        ).first()

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        source = self._source(workspace, data)
        if source is None:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        if self.action == "list":
            relations = IssueRelation.objects.filter(
                Q(issue_id=source.id) | Q(related_issue_id=source.id),
                workspace_id=workspace.id,
            ).select_related("issue", "related_issue", "related_issue__state", "issue__state")
            grouped = {
                key: []
                for key in (
                    "blocking",
                    "blocked_by",
                    "duplicate",
                    "relates_to",
                    "start_after",
                    "start_before",
                    "finish_after",
                    "finish_before",
                )
            }
            seen = {"duplicate": set(), "relates_to": set()}
            for relation in relations:
                related = relation.related_issue if relation.issue_id == source.id else relation.issue
                relation_type = relation.relation_type
                key = relation_type
                if relation_type == "blocked_by":
                    key = "blocked_by" if relation.issue_id == source.id else "blocking"
                elif relation_type == "start_before":
                    key = "start_before" if relation.issue_id == source.id else "start_after"
                elif relation_type == "finish_before":
                    key = "finish_before" if relation.issue_id == source.id else "finish_after"
                if key not in grouped:
                    continue
                if key in seen and str(related.id) in seen[key]:
                    continue
                if key in seen:
                    seen[key].add(str(related.id))
                grouped[key].append({"project_id": str(related.project_id), "issue_id": str(related.id)})
            return 200, grouped, None
        serializer = IssueRelationCreateSerializer(
            data={"relation_type": data.get("relation_type"), "issues": data.get("work_item_ids") or []}
        )
        if data.get("relation_definition_id") or data.get("relation_definition_label"):
            raise OperationAdapterFailure("RELATION_DEFINITION_UNSUPPORTED", 400)
        if not serializer.is_valid():
            raise OperationAdapterFailure("VALIDATION_ERROR", 400)
        relation_type = serializer.validated_data["relation_type"]
        target_ids = list(
            Issue.issue_objects.filter(
                workspace_id=workspace.id, pk__in=serializer.validated_data["issues"]
            ).values_list("id", flat=True)
        )
        actual_relation = get_actual_relation(relation_type)
        reverse = relation_type in {"blocking", "start_after", "finish_after"}
        rows = [
            IssueRelation(
                issue_id=target_id if reverse else source.id,
                related_issue_id=source.id if reverse else target_id,
                relation_type=actual_relation,
                project_id=source.project_id,
                workspace_id=workspace.id,
                created_by_id=request.user.id,
                updated_by_id=request.user.id,
            )
            for target_id in target_ids
        ]
        IssueRelation.objects.bulk_create(rows, ignore_conflicts=True, batch_size=10)
        relations = IssueRelation.objects.filter(
            relation_type=actual_relation,
            workspace_id=workspace.id,
            **(
                {"issue_id__in": target_ids, "related_issue_id": source.id}
                if reverse
                else {"issue_id": source.id, "related_issue_id__in": target_ids}
            ),
        ).select_related("issue", "related_issue", "related_issue__state", "issue__state")
        serializer_class = RelatedIssueSerializer if reverse else IssueRelationSerializer
        return (
            201,
            {"relations": serializer_class(relations, many=True).data},
            issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=str(source.id),
                project_id=str(source.project_id),
                event_type="issue_relation.activity.created",
                requested_data={"relation_type": relation_type, "issues": [str(value) for value in target_ids]},
                current_instance_data=None,
                notification=True,
                deterministic_activity=False,
            ),
        )


class AssociationOperation:
    def __init__(self, family: str, action: str):
        self.family = family
        self.action = action

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(
            ProjectEntityPermission, request, workspace, data, "create" if self.action == "transfer" else "retrieve"
        )

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        if self.family == "cycle":
            container = Cycle.objects.filter(
                workspace_id=workspace.id, project_id=data["project_id"], pk=data["cycle_id"]
            ).first()
            relation = "issue_cycle__cycle_id"
            serializer = IssueSerializer
        else:
            container = Module.objects.filter(
                workspace_id=workspace.id, project_id=data["project_id"], pk=data["module_id"]
            ).first()
            relation = "issue_module__module_id"
            serializer = IssueSerializer
        if container is None:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        if self.action == "list":
            if data.get("pql"):
                raise OperationAdapterFailure("PQL_QUERY_UNSUPPORTED", 400)
            queryset = (
                Issue.issue_objects.filter(
                    workspace_id=workspace.id,
                    project_id=data["project_id"],
                    **{relation: container.id},
                )
                .filter(
                    **(
                        {"issue_cycle__deleted_at__isnull": True}
                        if self.family == "cycle"
                        else {"issue_module__deleted_at__isnull": True}
                    )
                )
                .distinct()
                .select_related("project", "workspace", "state", "parent")
                .prefetch_related("assignees", "labels")
            )
            page = _bounded_page(
                queryset,
                data,
                default_order="created_at",
                allowed_order={"created_at", "updated_at", "name", "sequence_id"},
            )
            page["results"] = [
                serializer(item, fields=_fields(data), expand=_expand(data)).data for item in page["results"]
            ]
            page["total_count"] = page["total_results"]
            return 200, page, None
        if self.family == "cycle" and self.action == "transfer":
            result = transfer_cycle_issues(
                slug=workspace.slug,
                project_id=str(data["project_id"]),
                cycle_id=str(data["cycle_id"]),
                new_cycle_id=str(data["new_cycle_id"]),
                request=request,
                user_id=request.user.id,
                activity_publisher=lambda **_: None,
            )
            if not result.get("success"):
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            return (
                200,
                {"message": "Success"},
                {
                    "activity": {
                        "type": "cycle.activity.created",
                        "requested_data": json.dumps({"cycles_list": []}),
                        "actor_id": str(request.user.id),
                        "issue_id": None,
                        "project_id": str(data["project_id"]),
                        "current_instance": json.dumps(result.get("activity_snapshot", {})),
                        "epoch": int(timezone.now().timestamp()),
                        "origin": base_host(request=request, is_app=True),
                        "expected": True,
                        "deterministic_activity": False,
                    },
                    "notification": {
                        "skip": True,
                        "type": "cycle.activity.created",
                        "issue_id": None,
                        "project_id": str(data["project_id"]),
                        "actor_id": str(request.user.id),
                        "requested_data": json.dumps({"cycles_list": []}),
                        "current_instance": json.dumps(result.get("activity_snapshot", {})),
                    },
                    "webhook": {"skip": True},
                },
            )
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)


class PageOperation:
    permission_class = ProjectPagePermission

    def __init__(self, action: str):
        self.action = action

    def _project_id(self, workspace: Workspace, data: dict[str, Any]) -> str | None:
        if data.get("project_id"):
            return str(data["project_id"])
        return None

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        project_id = self._project_id(workspace, data)
        if not project_id and self.action in {"list", "create"}:
            permission = WorkSpaceAdminPermission if self.action == "create" else WorkspaceUserPermission
            return _authorize(permission, request, workspace, data, self.action)
        if not project_id and self.action == "retrieve":
            page = Page.objects.filter(pk=data.get("page_id"), workspace_id=workspace.id, is_global=True).first()
            return bool(
                page
                and _authorize(WorkspaceUserPermission, request, workspace, data, "retrieve")
                and (page.owned_by_id == request.user.id or page.access == Page.PUBLIC_ACCESS)
            )
        if not project_id:
            return False
        scoped = {**data, "project_id": project_id}
        return _authorize(
            self.permission_class, request, workspace, scoped, self.action, resource_id=data.get("page_id")
        )

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        project_id = self._project_id(workspace, data)
        if not project_id and self.action not in {"list", "retrieve", "create"}:
            raise OperationAdapterFailure("OPERATION_REJECTED", 400)
        if self.action == "list":
            if project_id:
                queryset = (
                    Page.objects.filter(
                        workspace_id=workspace.id,
                        project_pages__project_id=project_id,
                        project_pages__deleted_at__isnull=True,
                        project_pages__project__archived_at__isnull=True,
                        parent__isnull=True,
                    )
                    .filter(Q(owned_by_id=request.user.id) | Q(access=Page.PUBLIC_ACCESS))
                    .distinct()
                )
            else:
                queryset = Page.objects.filter(workspace_id=workspace.id, is_global=True).filter(
                    Q(access=Page.PUBLIC_ACCESS) | Q(owned_by_id=request.user.id)
                )
            page = _bounded_page(
                queryset, data, default_order="-created_at", allowed_order={"created_at", "updated_at", "name"}
            )
            page["results"] = [PageSerializer(item).data for item in page["results"]]
            return 200, page, None
        if self.action == "retrieve":
            page_queryset = Page.objects.filter(pk=data.get("page_id"), workspace_id=workspace.id)
            if project_id:
                page_queryset = page_queryset.filter(
                    project_pages__project_id=project_id,
                    project_pages__deleted_at__isnull=True,
                )
            else:
                page_queryset = page_queryset.filter(
                    is_global=True,
                ).filter(Q(access=Page.PUBLIC_ACCESS) | Q(owned_by_id=request.user.id))
            page = page_queryset.first()
            if page is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            return 200, PageDetailSerializer(page).data, None
        if self.action == "create":
            body = _serializer_data(
                data,
                drop={
                    "project_id",
                    "page_id",
                    "_caller_id",
                    "cursor",
                    "per_page",
                    "order_by",
                    "fields",
                    "expand",
                    "params",
                },
            )
            valid_html, _, safe_html = validate_html_content(data.get("description_html", "<p></p>"))
            if not valid_html:
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            serializer = PageSerializer(
                data={key: value for key, value in body.items() if key != "description_html"},
                context={
                    "project_id": project_id,
                    "owned_by_id": request.user.id,
                    "description_json": data.get("description_json") or {},
                    "description_binary": None,
                    "description_html": safe_html or "<p></p>",
                },
            )
            if not serializer.is_valid():
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            try:
                if project_id:
                    serializer.save(created_by_id=request.user.id, updated_by_id=request.user.id)
                    instance = serializer.instance
                    _bind_audit_actor(instance, request.user.id, created=True)
                else:
                    page_data = dict(serializer.validated_data)
                    instance = Page.objects.create(
                        **page_data,
                        description_json=data.get("description_json") or {},
                        description_binary=None,
                        description_html=safe_html or "<p></p>",
                        owned_by_id=request.user.id,
                        workspace_id=workspace.id,
                        created_by_id=request.user.id,
                        is_global=True,
                    )
                    _bind_audit_actor(instance, request.user.id, created=True)
            except serializers.ValidationError:
                raise OperationAdapterFailure("VALIDATION_ERROR", 400) from None
            return 201, PageDetailSerializer(instance).data, None
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)


class MemberOperation:
    def __init__(self, *, workspace_scope: bool):
        self.workspace_scope = workspace_scope

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        permission = WorkSpaceAdminPermission if self.workspace_scope else ProjectMemberPermission
        return _authorize(permission, request, workspace, data, "list")

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        query = _query_data(data)
        if self.workspace_scope:
            queryset = WorkspaceMember.objects.filter(workspace_id=workspace.id).select_related("member")
            serializer = WorkspaceMemberLiteAPISerializer
        else:
            queryset = ProjectMember.objects.filter(
                workspace_id=workspace.id,
                project_id=data["project_id"],
            ).select_related("member")
            serializer = ProjectMemberLiteAPISerializer
        for field in ("first_name", "last_name", "email", "display_name"):
            if query.get(field):
                queryset = queryset.filter(**{f"member__{field}__icontains": query[field]})
        if query.get("is_bot") is not None:
            queryset = queryset.filter(member__is_bot=query["is_bot"])
        if query.get("is_active") is not None:
            queryset = queryset.filter(is_active=query["is_active"])
        if query.get("role_slug"):
            role = {"admin": 20, "member": 15, "guest": 5}.get(str(query["role_slug"]).lower())
            if role is None:
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            queryset = queryset.filter(role=role)
        page = _bounded_page(queryset, data, default_order="-created_at", allowed_order={"created_at", "updated_at"})
        page["results"] = serializer(page["results"], many=True).data
        return 200, page, None


class IntakeOperation:
    permission_class = ProjectLitePermission

    def __init__(self, action: str):
        self.action = action

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        return _authorize(
            self.permission_class, request, workspace, data, self.action, resource_id=data.get("issue_id")
        )

    def _queryset(self, workspace: Workspace, data: dict[str, Any]):
        project = Project.objects.filter(
            pk=data["project_id"], workspace_id=workspace.id, intake_view=True, archived_at__isnull=True
        ).first()
        intake = Intake.objects.filter(project_id=data["project_id"], workspace_id=workspace.id).first()
        if project is None or intake is None:
            return IntakeIssue.objects.none()
        return IntakeIssue.objects.filter(
            Q(snoozed_till__gte=timezone.now()) | Q(snoozed_till__isnull=True),
            workspace_id=workspace.id,
            project_id=data["project_id"],
            intake_id=intake.id,
        ).select_related("issue", "workspace", "project")

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        if self.action == "list":
            page = _bounded_page(
                self._queryset(workspace, data),
                data,
                default_order="-created_at",
                allowed_order={"created_at", "updated_at", "status"},
            )
            page["results"] = [IntakeIssueSerializer(item).data for item in page["results"]]
            return 200, page, None
        if self.action == "retrieve":
            item = self._queryset(workspace, data).filter(issue_id=data["issue_id"]).first()
            if item is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            return 200, IntakeIssueSerializer(item).data, None
        if self.action == "update":
            item = self._queryset(workspace, data).filter(pk=data["work_item_id"]).first()
            if item is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            body = _serializer_data(
                data,
                drop={"project_id", "issue_id", "cursor", "per_page", "order_by", "fields", "expand", "params"},
            )
            serializer = IntakeIssueUpdateSerializer(
                item, data=body, partial=True, context={"project_id": str(data["project_id"])}
            )
            if not serializer.is_valid():
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            serializer.save(updated_by_id=request.user.id)
            _bind_audit_actor(serializer.instance, request.user.id, created=False)
            return 200, IntakeIssueSerializer(serializer.instance).data, None
        if self.action == "create":
            project = Project.objects.filter(pk=data["project_id"], workspace_id=workspace.id).first()
            intake = Intake.objects.filter(project_id=data["project_id"], workspace_id=workspace.id).first()
            issue_data = data.get("data")
            if project is None or intake is None or not project.intake_view or not isinstance(issue_data, dict):
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            if not issue_data.get("name"):
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            priority = issue_data.get("priority", "none")
            if priority not in {"low", "medium", "high", "urgent", "none"}:
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            triage_state = State.triage_objects.filter(project_id=project.id, workspace_id=workspace.id).first()
            with transaction.atomic():
                if triage_state is None:
                    triage_state = State.all_state_objects.create(
                        name="Triage",
                        group="triage",
                        project_id=project.id,
                        workspace_id=workspace.id,
                        color="#4E5355",
                        sequence=65000,
                        default=False,
                        created_by_id=request.user.id,
                    )
                raw_html = issue_data.get("description_html", "<p></p>")
                valid_html, _, safe_html = validate_html_content(raw_html)
                if not valid_html:
                    raise OperationAdapterFailure("VALIDATION_ERROR", 400)
                issue = Issue.objects.create(
                    name=issue_data["name"],
                    description_json=issue_data.get("description") or issue_data.get("description_json") or {},
                    description_html=safe_html or "<p></p>",
                    priority=priority,
                    project_id=project.id,
                    state_id=triage_state.id,
                    workspace_id=workspace.id,
                    created_by_id=request.user.id,
                )
                item = IntakeIssue.objects.create(
                    intake_id=intake.id,
                    project_id=project.id,
                    workspace_id=workspace.id,
                    issue=issue,
                    source=SourceType.IN_APP,
                    created_by_id=request.user.id,
                )
                _bind_audit_actor(issue, request.user.id, created=True)
                _bind_audit_actor(item, request.user.id, created=True)
            return (
                201,
                IntakeIssueSerializer(item).data,
                issue_publication_payload(
                    request=request,
                    workspace=workspace,
                    issue_id=str(issue.id),
                    project_id=str(project.id),
                    event_type="issue.activity.created",
                    requested_data=issue_data,
                    current_instance_data=None,
                    notification=True,
                    deterministic_activity=True,
                ),
            )
        if self.action == "delete":
            item = self._queryset(workspace, data).filter(issue_id=data["issue_id"]).select_related("issue").first()
            if item is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            issue = item.issue
            issue_publication = None
            if item.status in {-2, -1, 0, 2}:
                if (
                    issue.created_by_id != request.user.id
                    and not ProjectMember.objects.filter(
                        workspace_id=workspace.id,
                        project_id=data["project_id"],
                        member_id=request.user.id,
                        role=20,
                        is_active=True,
                    ).exists()
                ):
                    raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
                current = json.loads(json.dumps(IssueSerializer(issue).data))
                issue.delete()
                issue_publication = issue_publication_payload(
                    request=request,
                    workspace=workspace,
                    issue_id=str(issue.id),
                    project_id=str(data["project_id"]),
                    event_type="issue.activity.deleted",
                    requested_data={"issue_id": str(issue.id)},
                    current_instance_data=current,
                    notification=False,
                    deterministic_activity=True,
                )
            item.delete()
            return (
                200,
                {"deleted": True, "id": str(data["issue_id"])},
                issue_publication
                or _model_publication_payload(
                    request=request,
                    workspace=workspace,
                    model_name="intake_issue",
                    model_id=str(data["issue_id"]),
                    requested_data={"id": str(data["issue_id"])},
                    current_instance=None,
                    deleted=True,
                ),
            )
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)


class AgentGovernanceOperation:
    """Typed gateway adapter for Plane-owned Agent governance mutations."""

    _ROLE_BY_OPERATION = {
        "agent.assignment.delegate": AgentRole.DELEGATOR,
        "agent.hr.propose": AgentRole.HR,
        "agent.outcome.evaluate": AgentRole.EVALUATOR,
    }

    def __init__(self, operation_id: str):
        self.operation_id = operation_id

    @staticmethod
    def _actor_authorized(request: Any, workspace: Workspace, data: dict[str, Any], role: str) -> bool:
        ref = data.get(
            {
                AgentRole.DELEGATOR: "delegator_ref",
                AgentRole.HR: "proposer_ref",
                AgentRole.EVALUATOR: "evaluator_ref",
            }[role]
        )
        if getattr(request, "agent_actor_ref", None) != ref or not isinstance(ref, str):
            return False
        try:
            actor = AgentActor.objects.select_related("active_profile").get(
                pk=_plane_ref(ref, "agent-actor", "agent_actor_ref"), workspace=workspace
            )
        except (AgentActor.DoesNotExist, OperationAdapterFailure, ValueError):
            return False
        return bool(
            actor.is_active
            and actor.principal_id == request.user.id
            and actor.active_profile_id
            and actor.active_profile.role == role
            and WorkspaceMember.objects.filter(workspace=workspace, member=request.user, is_active=True).exists()
        )

    def authorize(self, request: Any, workspace: Workspace, data: dict[str, Any]) -> bool:
        if self.operation_id in self._ROLE_BY_OPERATION:
            return self._actor_authorized(request, workspace, data, self._ROLE_BY_OPERATION[self.operation_id])
        if self.operation_id == "agent.assignment.cancel":
            if getattr(request.user, "is_bot", False):
                try:
                    actor = _bound_actor(request, workspace, getattr(request, "agent_actor_ref", None))
                    assignment = AssignmentContract.objects.get(
                        pk=_plane_ref(data.get("assignment_ref"), "assignment", "assignment_ref"),
                        workspace=workspace,
                    )
                except (AssignmentContract.DoesNotExist, OperationAdapterFailure, ValueError):
                    return False
                return actor.id in {assignment.assignee_id, assignment.delegated_by_id}
            return bool(
                not getattr(request.user, "is_bot", False)
                and WorkspaceMember.objects.filter(
                    workspace=workspace, member=request.user, role__in=[20, 15], is_active=True
                ).exists()
            )
        if self.operation_id in {"agent.hr.decide", "agent.outcome.accept", "agent.outcome.request_revision"}:
            return bool(
                not getattr(request.user, "is_bot", False)
                and WorkspaceMember.objects.filter(
                    workspace=workspace, member=request.user, role__in=[20, 15], is_active=True
                ).exists()
            )
        return bool(WorkspaceMember.objects.filter(workspace=workspace, member=request.user, is_active=True).exists())

    @staticmethod
    def _record_ref(record: Any, prefix: str) -> str:
        return namespaced_ref(prefix, str(record.id))

    @staticmethod
    def _assignment_payload(assignment: AssignmentContract) -> dict[str, Any]:
        return {
            "assignmentRef": namespaced_ref("assignment", str(assignment.id)),
            "parentAssignmentRef": (
                namespaced_ref("assignment", str(assignment.lineage_of_id)) if assignment.lineage_of_id else None
            ),
            "rootAssignmentRef": (
                namespaced_ref("assignment", str(assignment.root_assignment_id))
                if assignment.root_assignment_id
                else None
            ),
            "assigneeRef": namespaced_ref("agent-actor", str(assignment.assignee_id)),
            "delegatedByRef": (
                namespaced_ref("agent-actor", str(assignment.delegated_by_id)) if assignment.delegated_by_id else None
            ),
            "depth": assignment.delegation_depth,
            "state": assignment.state,
            "scope": assignment.scope,
            "budget": assignment.budget,
        }

    @staticmethod
    def _proposal_payload(proposal: AgentHRProposal) -> dict[str, Any]:
        return {
            "proposalRef": namespaced_ref("hr-proposal", str(proposal.id)),
            "kind": proposal.kind,
            "state": proposal.state,
            "subjectActorRef": (
                namespaced_ref("agent-actor", str(proposal.subject_actor_id)) if proposal.subject_actor_id else None
            ),
            "requestedRole": proposal.requested_role,
            "appliedActorRef": (
                namespaced_ref("agent-actor", str(proposal.applied_actor_id)) if proposal.applied_actor_id else None
            ),
            "reviewedAt": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
        }

    @staticmethod
    def _outcome_payload(outcome: OutcomeSubmission) -> dict[str, Any]:
        review = getattr(outcome, "evaluator_review", None)
        return {
            "outcomeRef": namespaced_ref("outcome-submission", str(outcome.id)),
            "state": outcome.state,
            "evaluatorRef": namespaced_ref("agent-actor", str(outcome.evaluator_id)) if outcome.evaluator_id else None,
            "evaluatorProfileRef": (
                namespaced_ref("profile-version", str(review.evaluator_profile_id))
                if review is not None and review.evaluator_profile_id
                else None
            ),
            "review": {
                "criteria": review.criteria,
                "verdict": review.verdict,
                "recommendation": review.recommendation,
                "provenance": review.provenance,
            }
            if review is not None
            else None,
            "humanReviewerRef": namespaced_ref("user", str(outcome.human_reviewer_id))
            if outcome.human_reviewer_id
            else None,
        }

    def execute(self, request: Any, workspace: Workspace, data: dict[str, Any]):
        try:
            if self.operation_id == "agent.assignment.delegate":
                parent = AssignmentContract.objects.get(
                    pk=_plane_ref(data["parent_assignment_ref"], "assignment", "parent_assignment_ref"),
                    workspace=workspace,
                )
                delegator = _bound_actor(request, workspace, data["delegator_ref"], role=AgentRole.DELEGATOR)
                assignee = AgentActor.objects.get(
                    pk=_plane_ref(data["assignee_ref"], "agent-actor", "assignee_ref"), workspace=workspace
                )
                assignment = delegate_assignment(
                    parent,
                    assignee,
                    target_ref=data["target_ref"],
                    objective=data["objective"],
                    acceptance_criteria=data["acceptance_criteria"],
                    context_refs=data.get("context_refs"),
                    scope=data.get("scope"),
                    budget=data.get("budget"),
                    idempotency_key=_gateway_key(data, "delegate"),
                    delegated_by=delegator,
                    created_by=request.user,
                )
                return 200, {"assignment": self._assignment_payload(assignment)}, None

            if self.operation_id == "agent.assignment.cancel":
                if getattr(request.user, "is_bot", False):
                    actor = _bound_actor(request, workspace, getattr(request, "agent_actor_ref", None))
                else:
                    _human_admin(request, workspace)
                assignment = AssignmentContract.objects.get(
                    pk=_plane_ref(data["assignment_ref"], "assignment", "assignment_ref"), workspace=workspace
                )
                if getattr(request.user, "is_bot", False) and actor.id not in {
                    assignment.assignee_id,
                    assignment.delegated_by_id,
                }:
                    raise OperationAdapterFailure("NOT_AUTHORIZED", 403)
                assignment = cancel_assignment(assignment)
                return 200, {"assignment": self._assignment_payload(assignment)}, None

            if self.operation_id == "agent.hr.propose":
                proposer = _bound_actor(request, workspace, data["proposer_ref"], role=AgentRole.HR)
                subject_actor = self._get_actor(workspace, data.get("subject_actor_ref"))
                subject_user = self._get_user(data.get("subject_user_ref"))
                requested_principal = self._get_user(data.get("requested_principal_ref"))
                target_assignment = self._get_assignment(workspace, data.get("target_assignment_ref"))
                requested_assignee = self._get_actor(workspace, data.get("requested_assignee_ref"))
                project = None
                project_id = data.get("project_id")
                if project_id:
                    project = Project.objects.filter(pk=project_id, workspace=workspace).first()
                    if project is None:
                        raise OperationAdapterFailure("OPERATION_REJECTED", 400)
                proposal = propose_hr_change(
                    workspace=workspace,
                    proposed_by=proposer,
                    kind=data["kind"],
                    rationale=data["rationale"],
                    idempotency_key=_gateway_key(data, "hr-propose"),
                    subject_actor=subject_actor,
                    subject_user=subject_user,
                    requested_principal=requested_principal,
                    target_assignment=target_assignment,
                    requested_assignee=requested_assignee,
                    requested_role=data.get("requested_role"),
                    requested_display_name=data.get("requested_display_name", ""),
                    requested_profile=data.get("requested_profile"),
                    project=project,
                    created_by=request.user,
                )
                return 200, {"proposal": self._proposal_payload(proposal)}, None

            if self.operation_id == "agent.hr.decide":
                _human_admin(request, workspace)
                proposal = AgentHRProposal.objects.get(
                    pk=_plane_ref(data["proposal_ref"], "hr-proposal", "proposal_ref"), workspace=workspace
                )
                proposal = decide_hr_proposal(
                    proposal,
                    human_reviewer=request.user,
                    approved=data["approved"],
                    decision_note=data.get("decision_note", ""),
                    idempotency_key=_gateway_key(data, "hr-decide"),
                )
                return 200, {"proposal": self._proposal_payload(proposal)}, None

            if self.operation_id == "agent.outcome.evaluate":
                evaluator = _bound_actor(request, workspace, data["evaluator_ref"], role=AgentRole.EVALUATOR)
                outcome = OutcomeSubmission.objects.get(
                    pk=_plane_ref(data["outcome_ref"], "outcome-submission", "outcome_ref"), workspace=workspace
                )
                outcome = review_outcome(
                    outcome,
                    evaluator=evaluator,
                    criteria=data.get("criteria"),
                    verdict=data["verdict"],
                    feedback=data.get("feedback", ""),
                    provenance=data.get("provenance"),
                    idempotency_key=_gateway_key(data, "outcome-evaluate"),
                )
                outcome = OutcomeSubmission.objects.select_related("evaluator_review").get(pk=outcome.pk)
                return 200, {"outcome": self._outcome_payload(outcome)}, None

            _human_admin(request, workspace)
            outcome = OutcomeSubmission.objects.get(
                pk=_plane_ref(data["outcome_ref"], "outcome-submission", "outcome_ref"), workspace=workspace
            )
            if self.operation_id == "agent.outcome.accept":
                outcome = accept_outcome(
                    outcome, human_reviewer=request.user, decision_note=data.get("decision_note", "")
                )
            elif self.operation_id == "agent.outcome.request_revision":
                outcome = request_revision(
                    outcome, human_reviewer=request.user, decision_note=data.get("decision_note", "")
                )
            else:
                raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)
            return 200, {"outcome": self._outcome_payload(outcome)}, None
        except (
            AgentHRProposal.DoesNotExist,
            AssignmentContract.DoesNotExist,
            AgentActor.DoesNotExist,
            OutcomeSubmission.DoesNotExist,
        ):
            raise OperationAdapterFailure("OPERATION_REJECTED", 400) from None
        except (
            AgentDomainError,
            IdempotencyConflictError,
            InvalidTransitionError,
            TerminalEventRequiredError,
            ValidationError,
        ) as error:
            _raise_domain_error(error)

    @staticmethod
    def _get_actor(workspace: Workspace, value: Any) -> AgentActor | None:
        if value is None:
            return None
        try:
            return AgentActor.objects.get(pk=_plane_ref(value, "agent-actor", "actor_ref"), workspace=workspace)
        except (AgentActor.DoesNotExist, ValueError):
            raise OperationAdapterFailure("OPERATION_REJECTED", 400) from None

    @staticmethod
    def _get_assignment(workspace: Workspace, value: Any) -> AssignmentContract | None:
        if value is None:
            return None
        try:
            return AssignmentContract.objects.get(
                pk=_plane_ref(value, "assignment", "assignment_ref"), workspace=workspace
            )
        except (AssignmentContract.DoesNotExist, ValueError):
            raise OperationAdapterFailure("OPERATION_REJECTED", 400) from None

    @staticmethod
    def _get_user(value: Any) -> User | None:
        if value is None:
            return None
        try:
            return User.objects.get(pk=_plane_ref(value, "user", "user_ref"))
        except (User.DoesNotExist, ValueError):
            raise OperationAdapterFailure("OPERATION_REJECTED", 400) from None


def _resource_handlers() -> dict[str, Any]:
    specs = (
        ResourceSpec(
            "cycle",
            Cycle,
            CycleSerializer,
            CycleCreateSerializer,
            CycleUpdateSerializer,
            "cycle_id",
            ProjectEntityPermission,
            order_by=CYCLE_ORDER_BY_ALLOWLIST,
        ),
        ResourceSpec(
            "module",
            Module,
            ModuleSerializer,
            ModuleCreateSerializer,
            ModuleUpdateSerializer,
            "module_id",
            ProjectEntityPermission,
            order_by=MODULE_ORDER_BY_ALLOWLIST,
        ),
        ResourceSpec(
            "project",
            Project,
            ProjectSerializer,
            ProjectCreateSerializer,
            ProjectUpdateSerializer,
            "project_id",
            ProjectBasePermission,
            scope="workspace",
            order_by=PROJECT_ORDER_BY_ALLOWLIST,
        ),
        ResourceSpec(
            "state", State, StateSerializer, StateSerializer, StateSerializer, "state_id", ProjectEntityPermission
        ),
        ResourceSpec(
            "label",
            Label,
            LabelSerializer,
            LabelCreateUpdateSerializer,
            LabelCreateUpdateSerializer,
            "label_id",
            ProjectEntityPermission,
        ),
        ResourceSpec(
            "link",
            IssueLink,
            IssueLinkSerializer,
            IssueLinkCreateSerializer,
            IssueLinkUpdateSerializer,
            "link_id",
            ProjectEntityPermission,
        ),
        ResourceSpec(
            "comment",
            IssueComment,
            IssueCommentSerializer,
            IssueCommentCreateSerializer,
            IssueCommentCreateSerializer,
            "comment_id",
            ProjectLitePermission,
        ),
    )
    handlers: dict[str, Any] = {
        "work_item.list": WorkItemOperation("list"),
        "work_item.create": WorkItemOperation("create"),
        "work_item.retrieve": WorkItemOperation("retrieve"),
        "work_item.update": WorkItemOperation("update"),
        "work_item.delete": WorkItemOperation("delete"),
        "work_item.search": WorkItemSearchOperation(),
        "work_item_activity.list": ActivityOperation("list"),
        "work_item_activity.retrieve": ActivityOperation("retrieve"),
        "work_item_relation.list": RelationOperation("list"),
        "work_item_relation.create": RelationOperation("create"),
        "cycle.work_item.list": AssociationOperation("cycle", "list"),
        "cycle.transfer": AssociationOperation("cycle", "transfer"),
        "module.work_item.list": AssociationOperation("module", "list"),
        "work_item.read": WorkItemReadOperation(),
        "work_item.rename": WorkItemRenameOperation(),
        "project_member.list": MemberOperation(workspace_scope=False),
        "workspace_member.list": MemberOperation(workspace_scope=True),
        "page.list": PageOperation("list"),
        "page.retrieve": PageOperation("retrieve"),
        "page.create": PageOperation("create"),
        "intake.list": IntakeOperation("list"),
        "intake.retrieve": IntakeOperation("retrieve"),
        "intake.create": IntakeOperation("create"),
        "intake.update": IntakeOperation("update"),
        "intake.delete": IntakeOperation("delete"),
        "agent.assignment.delegate": AgentGovernanceOperation("agent.assignment.delegate"),
        "agent.assignment.cancel": AgentGovernanceOperation("agent.assignment.cancel"),
        "agent.hr.propose": AgentGovernanceOperation("agent.hr.propose"),
        "agent.hr.decide": AgentGovernanceOperation("agent.hr.decide"),
        "agent.outcome.evaluate": AgentGovernanceOperation("agent.outcome.evaluate"),
        "agent.outcome.accept": AgentGovernanceOperation("agent.outcome.accept"),
        "agent.outcome.request_revision": AgentGovernanceOperation("agent.outcome.request_revision"),
    }
    for spec in specs:
        for action in ("list", "create", "retrieve", "update", "delete"):
            handlers[f"{spec.prefix}.{action}"] = ResourceOperation(spec, action)
    return handlers


OPERATION_HANDLERS = _resource_handlers()

_SPECIAL_GATEWAY_OPERATIONS = frozenset(
    {
        "user.me",
        "search_workspace",
        "catalog.search",
        "catalog.describe",
        "code_mode.spill",
        "agent.outcome.submit",
        "agent.outcome.publish",
        "work_item_attachment.list",
        "work_item_attachment.download_url",
        "work_item_attachment.upload_from_url",
        "work_item_attachment.delete",
        "work_item_attachment.read",
    }
)
if frozenset(OPERATION_HANDLERS) != IMPLEMENTED_OPERATION_IDS - _SPECIAL_GATEWAY_OPERATIONS:
    raise RuntimeError("The typed operation registry and catalog executable seam have drifted")


def get_operation_handler(operation_id: str) -> Any | None:
    """Resolve one exact registered operation; no prefix or path fallback."""

    return OPERATION_HANDLERS.get(operation_id)

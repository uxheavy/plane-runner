"""Typed application adapters for the Plane operation gateway.

These adapters intentionally stop below the HTTP layer.  They call Plane's
serializers, models, permission classes, and small domain helpers directly;
they never invoke a DRF view, construct a loopback request, or dispatch a
generic endpoint path.  The gateway remains responsible for caller binding,
idempotency, result bounds, and durable audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from plane.api.serializers import (
    CycleCreateSerializer,
    CycleSerializer,
    CycleUpdateSerializer,
    IntakeIssueSerializer,
    IntakeIssueUpdateSerializer,
    IssueCommentCreateSerializer,
    IssueCommentSerializer,
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
from .work_items import WorkItemRenameFailure, WorkItemRenameOutcome, WorkItemRenameService


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
            self._save(serializer, request, workspace, data, create=True)
            return 201, self._serialize(serializer.instance, data), None
        if self.action == "update":
            instance = self._instance(workspace, data)
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
            self._save(serializer, request, workspace, data, create=False)
            return 200, self._serialize(serializer.instance, data), None
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)

    def _save(self, serializer: Any, request: Any, workspace: Workspace, data: dict[str, Any], *, create: bool) -> None:
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
                    ProjectMember.objects.create(
                        project_id=serializer.instance.id,
                        member_id=request.user.id,
                        role=20,
                        created_by_id=request.user.id,
                    )
                    if serializer.instance.project_lead_id and serializer.instance.project_lead_id != request.user.id:
                        ProjectMember.objects.create(
                            project_id=serializer.instance.id,
                            member_id=serializer.instance.project_lead_id,
                            role=20,
                            created_by_id=request.user.id,
                        )
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
        except serializers.ValidationError as failure:
            if self.spec.prefix == "project" and "taken" in str(failure).lower():
                raise OperationAdapterFailure("PLANE_CONFLICT", 409) from None
            raise OperationAdapterFailure("VALIDATION_ERROR", 400) from None
        except IntegrityError:
            raise OperationAdapterFailure("PLANE_CONFLICT", 409) from None


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
            self.permission_class, request, workspace, data, self.action, resource_id=data.get("work_item_id")
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
            item = self._queryset(workspace, data).filter(pk=data["work_item_id"]).first()
            if item is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            return 200, IntakeIssueSerializer(item).data, None
        if self.action == "update":
            item = self._queryset(workspace, data).filter(pk=data["work_item_id"]).first()
            if item is None:
                raise OperationAdapterFailure("OPERATION_REJECTED", 400)
            body = _serializer_data(
                data,
                drop={"project_id", "work_item_id", "cursor", "per_page", "order_by", "fields", "expand", "params"},
            )
            serializer = IntakeIssueUpdateSerializer(
                item, data=body, partial=True, context={"project_id": str(data["project_id"])}
            )
            if not serializer.is_valid():
                raise OperationAdapterFailure("VALIDATION_ERROR", 400)
            serializer.save(updated_by_id=request.user.id)
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
            return 201, IntakeIssueSerializer(item).data, None
        raise OperationAdapterFailure("UNKNOWN_OPERATION", 404)


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
    }
    for spec in specs:
        for action in ("list", "create", "retrieve", "update"):
            handlers[f"{spec.prefix}.{action}"] = ResourceOperation(spec, action)
    return handlers


OPERATION_HANDLERS = _resource_handlers()

_SPECIAL_GATEWAY_OPERATIONS = frozenset(
    {
        "user.me",
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

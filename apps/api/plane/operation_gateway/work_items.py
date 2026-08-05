"""Gateway-owned semantic work-item operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework import serializers

from plane.api.serializers import IssueSerializer
from plane.db.models import Issue, Project, Workspace
from plane.utils.host import base_host


class WorkItemRenameFailure(Exception):
    """A bounded, pre-commit failure from the semantic rename service."""

    def __init__(self, code: str, http_status: int, retryable: bool):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


@dataclass(frozen=True)
class WorkItemRenameOutcome:
    result: dict[str, Any]
    publication_payload: dict[str, Any] | None


def issue_publication_payload(
    *,
    request: Any,
    workspace: Workspace,
    issue_id: str,
    project_id: str,
    event_type: str,
    requested_data: dict[str, Any],
    current_instance_data: dict[str, Any] | None,
    notification: bool,
    deterministic_activity: bool,
) -> dict[str, Any]:
    """Build one gateway-owned intent bundle for an issue-domain mutation."""

    current_instance = (
        json.dumps(current_instance_data, cls=DjangoJSONEncoder) if current_instance_data is not None else None
    )
    requested_json = json.dumps(requested_data, cls=DjangoJSONEncoder)
    actor_id = str(request.user.id)
    changed = current_instance_data is None or any(
        current_instance_data.get(key) != value for key, value in requested_data.items()
    )
    return {
        "activity": {
            "type": event_type,
            "requested_data": requested_json,
            "actor_id": actor_id,
            "issue_id": str(issue_id),
            "project_id": str(project_id),
            "current_instance": current_instance,
            "epoch": timezone.now().timestamp(),
            "origin": base_host(request=request, is_app=True),
            "expected": changed,
            "deterministic_activity": deterministic_activity,
        },
        "notification": {
            "type": event_type,
            "issue_id": str(issue_id),
            "project_id": str(project_id),
            "actor_id": actor_id,
            "subscriber": True,
            "requested_data": requested_json,
            "current_instance": current_instance,
            "skip": not notification or not changed,
        },
        "webhook": {
            "model_name": "issue",
            "model_id": str(issue_id),
            "requested_data": requested_data,
            "current_instance": current_instance or "{}",
            "actor_id": actor_id,
            "slug": workspace.slug,
            "origin": base_host(request=request, is_app=True),
        },
    }


class WorkItemMutationService:
    """Apply canonical issue serializer mutations and publish their effects."""

    def create(self, *, request: Any, workspace: Workspace, project_id: str, data: dict[str, Any]):
        project = Project.objects.filter(pk=project_id, workspace_id=workspace.id).first()
        if project is None:
            raise WorkItemRenameFailure("OPERATION_REJECTED", 400, False)
        serializer = IssueSerializer(
            data=data,
            context={
                "project_id": str(project.id),
                "workspace_id": str(workspace.id),
                "default_assignee_id": project.default_assignee_id,
            },
        )
        if not serializer.is_valid():
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False)
        try:
            serializer.save(created_by_id=request.user.id, updated_by_id=request.user.id)
        except serializers.ValidationError:
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False) from None
        issue = Issue.objects.get(pk=serializer.instance.pk)
        issue.created_by_id = request.user.id
        issue.updated_by_id = request.user.id
        issue.save(update_fields=["created_by", "updated_by"], disable_auto_set_user=True)
        return WorkItemRenameOutcome(
            result=IssueSerializer(issue).data,
            publication_payload=issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=str(issue.id),
                project_id=str(project.id),
                event_type="issue.activity.created",
                requested_data=data,
                current_instance_data=None,
                notification=True,
                deterministic_activity=True,
            ),
        )

    def update(
        self,
        *,
        request: Any,
        workspace: Workspace,
        project_id: str,
        issue_id: str,
        data: dict[str, Any],
    ):
        issue = (
            Issue.objects.select_for_update()
            .filter(workspace_id=workspace.id, project_id=project_id, pk=issue_id)
            .first()
        )
        project = Project.objects.filter(pk=project_id, workspace_id=workspace.id).first()
        if issue is None or project is None:
            raise WorkItemRenameFailure("OPERATION_REJECTED", 400, False)
        current = json.loads(json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder))
        serializer = IssueSerializer(
            issue,
            data=data,
            context={"project_id": str(project.id), "workspace_id": str(workspace.id)},
            partial=True,
        )
        if not serializer.is_valid():
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False)
        try:
            serializer.save(updated_by_id=request.user.id)
        except serializers.ValidationError:
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False) from None
        issue.updated_by_id = request.user.id
        issue.save(update_fields=["updated_by"], disable_auto_set_user=True)
        return WorkItemRenameOutcome(
            result=serializer.data,
            publication_payload=issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=str(issue.id),
                project_id=str(project.id),
                event_type="issue.activity.updated",
                requested_data=data,
                current_instance_data=current,
                notification=True,
                deterministic_activity=False,
            ),
        )

    def delete(self, *, request: Any, workspace: Workspace, project_id: str, issue_id: str):
        issue = (
            Issue.objects.select_for_update()
            .filter(workspace_id=workspace.id, project_id=project_id, pk=issue_id)
            .first()
        )
        if issue is None:
            raise WorkItemRenameFailure("OPERATION_REJECTED", 400, False)
        current = json.loads(json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder))
        issue.delete()
        return WorkItemRenameOutcome(
            result={"deleted": True, "id": str(issue_id)},
            publication_payload=issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=str(issue_id),
                project_id=str(project_id),
                event_type="issue.activity.deleted",
                requested_data={"issue_id": str(issue_id)},
                current_instance_data=current,
                notification=False,
                deterministic_activity=True,
            ),
        )


class WorkItemRenameService:
    """Apply one validated rename through Plane's existing issue serializer."""

    def rename(
        self,
        *,
        request: Any,
        workspace: Workspace,
        project_id: str,
        issue_id: str,
        name: str,
    ) -> WorkItemRenameOutcome:
        issue = (
            Issue.objects.select_for_update()
            .filter(workspace_id=workspace.id, project_id=project_id, pk=issue_id)
            .first()
        )
        project = Project.objects.filter(pk=project_id, workspace_id=workspace.id).first()
        if issue is None or project is None:
            # The gateway deliberately does not reveal whether a Plane object exists.
            raise WorkItemRenameFailure("OPERATION_REJECTED", 400, False)

        current_instance_data = json.loads(json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder))
        requested_data = {"name": name}
        serializer = IssueSerializer(
            issue,
            data=requested_data,
            context={"project_id": str(project.id), "workspace_id": str(workspace.id)},
            partial=True,
        )
        if not serializer.is_valid():
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False)

        try:
            serializer.save()
        except serializers.ValidationError:
            raise WorkItemRenameFailure("VALIDATION_ERROR", 400, False) from None
        issue.updated_by_id = request.user.id
        issue.save(update_fields=["updated_by"], disable_auto_set_user=True)

        serialized_result = serializer.data
        issue_id_string = str(issue.id)
        project_id_string = str(project.id)

        return WorkItemRenameOutcome(
            result=serialized_result,
            publication_payload=issue_publication_payload(
                request=request,
                workspace=workspace,
                issue_id=issue_id_string,
                project_id=project_id_string,
                event_type="issue.activity.updated",
                requested_data=requested_data,
                current_instance_data=current_instance_data,
                notification=True,
                deterministic_activity=True,
            ),
        )

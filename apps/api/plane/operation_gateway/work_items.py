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
    publication_payload: dict[str, Any]


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
        current_instance = json.dumps(current_instance_data, cls=DjangoJSONEncoder)
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

        serialized_result = serializer.data
        origin = base_host(request=request, is_app=True)
        actor_id = str(request.user.id)
        issue_id_string = str(issue.id)
        project_id_string = str(project.id)
        requested_json = json.dumps(requested_data, cls=DjangoJSONEncoder)
        # Keep the value stable in the durable payload while retaining enough
        # precision to distinguish two same-second gateway mutations.
        epoch = timezone.now().timestamp()

        return WorkItemRenameOutcome(
            result=serialized_result,
            publication_payload={
                "activity": {
                    "type": "issue.activity.updated",
                    "requested_data": requested_json,
                    "actor_id": actor_id,
                    "issue_id": issue_id_string,
                    "project_id": project_id_string,
                    "current_instance": current_instance,
                    "epoch": epoch,
                    "origin": origin,
                    "expected": current_instance_data.get("name") != name,
                },
                "notification": {
                    "type": "issue.activity.updated",
                    "issue_id": issue_id_string,
                    "project_id": project_id_string,
                    "actor_id": actor_id,
                    "subscriber": True,
                    "requested_data": requested_json,
                    "current_instance": current_instance,
                },
                "webhook": {
                    "model_name": "issue",
                    "model_id": issue_id_string,
                    "requested_data": requested_data,
                    "current_instance": current_instance,
                    "actor_id": actor_id,
                    "slug": workspace.slug,
                    "origin": origin,
                },
            },
        )

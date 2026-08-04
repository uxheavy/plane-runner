"""Gateway-owned semantic work-item operations and commit-safe publications."""

from __future__ import annotations

import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from plane.api.serializers import IssueSerializer
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import Issue, Project, Workspace
from plane.utils.host import base_host


class WorkItemRenameFailure(Exception):
    """A bounded, pre-commit failure from the semantic rename service."""

    def __init__(self, code: str, http_status: int, retryable: bool):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


class WorkItemPublicationFailure(Exception):
    """A commit callback could not publish a durable Plane projection."""


class WorkItemRenameService:
    """Apply one validated rename and publish its existing Plane projections on commit."""

    def rename(
        self,
        *,
        request: Any,
        workspace: Workspace,
        project_id: str,
        issue_id: str,
        name: str,
    ) -> dict[str, Any]:
        issue = (
            Issue.objects.select_for_update()
            .filter(workspace_id=workspace.id, project_id=project_id, pk=issue_id)
            .first()
        )
        project = Project.objects.filter(pk=project_id, workspace_id=workspace.id).first()
        if issue is None or project is None:
            # The gateway deliberately does not reveal whether a Plane object exists.
            raise WorkItemRenameFailure("OPERATION_REJECTED", 400, False)

        current_instance = json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder)
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

        # These callbacks run only after the transaction containing both the
        # issue write and the gateway receipt has committed. A broker failure
        # therefore becomes outcome_unknown instead of a replayable mutation.
        def publish_issue_activity() -> None:
            try:
                issue_activity.delay(
                    type="issue.activity.updated",
                    requested_data=requested_json,
                    actor_id=actor_id,
                    issue_id=issue_id_string,
                    project_id=project_id_string,
                    current_instance=current_instance,
                    epoch=int(timezone.now().timestamp()),
                    notification=True,
                    origin=origin,
                )
            except Exception:
                raise WorkItemPublicationFailure from None

        def publish_model_activity() -> None:
            try:
                model_activity.delay(
                    model_name="issue",
                    model_id=issue_id_string,
                    requested_data=requested_data,
                    current_instance=current_instance,
                    actor_id=request.user.id,
                    slug=workspace.slug,
                    origin=origin,
                )
            except Exception:
                raise WorkItemPublicationFailure from None

        transaction.on_commit(publish_issue_activity)
        transaction.on_commit(publish_model_activity)
        return serialized_result

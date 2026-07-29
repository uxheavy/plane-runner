# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Permission-scoped hydration for semantic Plane references."""

from datetime import datetime
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.settings import api_settings

from plane.db.models import (
    Cycle,
    CycleIssue,
    EstimatePoint,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueView,
    Module,
    ModuleIssue,
    Page,
    Project,
    ProjectMember,
    State,
    WorkspaceMember,
)


SCHEMA_VERSION = 1
MAX_HYDRATION_ITEMS = 50
ENTITY_TYPES = {"work_item", "project", "cycle", "module", "page", "view"}
WORK_ITEM_FIELDS = {
    "name",
    "description",
    "state",
    "priority",
    "assignees",
    "labels",
    "start_date",
    "target_date",
    "estimate",
    "cycle",
    "module",
}


def _validation_error(message):
    raise serializers.ValidationError(message)


def _strict_keys(value, required, optional=frozenset()):
    if not isinstance(value, dict):
        _validation_error("Expected an object")
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        _validation_error(f"Missing fields: {', '.join(sorted(missing))}")
    if unknown:
        _validation_error("Unknown fields are not allowed")


def _string(value, name, maximum=255):
    if not isinstance(value, str) or not value or len(value) > maximum:
        _validation_error(f"{name} must be a non-empty string of at most {maximum} characters")
    return value


def _uuid(value, name):
    value = _string(value, name, 36)
    try:
        return str(UUID(value))
    except ValueError:
        _validation_error(f"{name} must be a UUID")


def _entity_reference(value, *, document=False):
    _strict_keys(
        value,
        {"kind", "workspaceSlug", "entityType", "entityId"},
        {"projectId"},
    )
    if value["kind"] != "entity":
        _validation_error("Nested entity references must use kind 'entity'")
    entity_type = value["entityType"]
    if entity_type not in ENTITY_TYPES:
        _validation_error("Unsupported entityType")
    if document and entity_type not in {"page", "work_item"}:
        _validation_error("Editor documents must be a page or work item")

    entity_id = _uuid(value["entityId"], "entityId")
    project_id = value.get("projectId")
    if entity_type == "project":
        if project_id is not None and _uuid(project_id, "projectId") != entity_id:
            _validation_error("A project reference projectId must match entityId")
        project_id = entity_id
    elif project_id is None:
        _validation_error(f"projectId is required for {entity_type}")
    else:
        project_id = _uuid(project_id, "projectId")

    return {
        "kind": "entity",
        "workspaceSlug": _string(value["workspaceSlug"], "workspaceSlug"),
        "projectId": project_id,
        "entityType": entity_type,
        "entityId": entity_id,
    }


def _range_point(value, name):
    _strict_keys(value, {"blockId", "offset"})
    offset = value["offset"]
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or offset > 2_147_483_647:
        _validation_error(f"{name}.offset must be a non-negative 32-bit integer")
    return {"blockId": _string(value["blockId"], f"{name}.blockId"), "offset": offset}


def validate_semantic_reference(value):
    if not isinstance(value, dict):
        _validation_error("reference must be an object")
    kind = value.get("kind")
    if kind == "entity":
        return _entity_reference(value)
    if kind == "field":
        _strict_keys(value, {"kind", "entity", "fieldKey"})
        entity = _entity_reference(value["entity"])
        if entity["entityType"] != "work_item":
            _validation_error("Field references must target a work item")
        if value["fieldKey"] not in WORK_ITEM_FIELDS:
            _validation_error("Unsupported work-item field")
        return {"kind": "field", "entity": entity, "fieldKey": value["fieldKey"]}
    if kind == "editor_block":
        _strict_keys(value, {"kind", "document", "blockId"})
        return {
            "kind": kind,
            "document": _entity_reference(value["document"], document=True),
            "blockId": _string(value["blockId"], "blockId"),
        }
    if kind == "editor_range":
        _strict_keys(value, {"kind", "document", "start", "end"})
        return {
            "kind": kind,
            "document": _entity_reference(value["document"], document=True),
            "start": _range_point(value["start"], "start"),
            "end": _range_point(value["end"], "end"),
        }
    _validation_error("Unsupported reference kind")


def _observed_version(value):
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        _validation_error("observedEntityVersion must be an ISO-8601 timestamp")
    parsed = parse_datetime(value)
    if parsed is None:
        _validation_error("observedEntityVersion must be an ISO-8601 timestamp")
    return parsed


def validate_hydration_item(value):
    _strict_keys(value, {"reference"}, {"observedEntityVersion"})
    return {
        "reference": validate_semantic_reference(value["reference"]),
        "observedEntityVersion": _observed_version(value.get("observedEntityVersion")),
    }


class SemanticContextHydrationSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    items = serializers.ListField(child=serializers.JSONField(), min_length=1, max_length=MAX_HYDRATION_ITEMS)

    def to_internal_value(self, data):
        try:
            _strict_keys(data, {"schemaVersion", "items"})
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({api_settings.NON_FIELD_ERRORS_KEY: exc.detail}) from exc
        return super().to_internal_value(data)

    def validate_schemaVersion(self, value):
        if value != SCHEMA_VERSION:
            raise serializers.ValidationError(f"Only schemaVersion {SCHEMA_VERSION} is supported")
        return value

    def validate_items(self, value):
        return [validate_hydration_item(item) for item in value]


def _iso(value):
    return value.isoformat() if value is not None else None


def _failure(reference, code, message):
    return {
        "ok": False,
        "reference": reference,
        "code": code,
        "message": message,
        "retryable": False,
    }


def _project_access(user, workspace_slug, project_id):
    membership = (
        ProjectMember.objects.filter(
            workspace__slug=workspace_slug,
            project_id=project_id,
            member=user,
            is_active=True,
        )
        .values_list("role", flat=True)
        .first()
    )
    if membership is None:
        return None, None, "FORBIDDEN"
    project = Project.objects.filter(id=project_id, workspace__slug=workspace_slug).first()
    if project is None:
        return None, None, "NOT_FOUND"
    return project, membership, None


def _entity_access(user, reference):
    project, role, error = _project_access(user, reference["workspaceSlug"], reference["projectId"])
    if error:
        return None, None, error

    filters = {
        "id": reference["entityId"],
        "workspace__slug": reference["workspaceSlug"],
    }
    entity_type = reference["entityType"]
    if entity_type == "project":
        return project, project, None
    if entity_type == "work_item":
        entity = Issue.objects.filter(project_id=project.id, **filters).first()
    elif entity_type == "cycle":
        entity = Cycle.objects.filter(project_id=project.id, **filters).first()
    elif entity_type == "module":
        entity = Module.objects.filter(project_id=project.id, **filters).first()
    elif entity_type == "page":
        entity = Page.objects.filter(
            project_pages__project_id=project.id,
            project_pages__deleted_at__isnull=True,
            **filters,
        ).first()
    elif entity_type == "view":
        entity = IssueView.objects.filter(project_id=project.id, **filters).first()
    else:
        return None, project, "UNSUPPORTED"

    if entity is None:
        return None, project, "NOT_FOUND"
    is_private = (entity_type == "page" and entity.access == Page.PRIVATE_ACCESS) or (
        entity_type == "view" and entity.access == 0
    )
    if is_private and entity.owned_by_id != user.id:
        return None, project, "FORBIDDEN"
    if entity_type in {"page", "view"} and role == 5 and not project.guest_view_all_features:
        if entity.owned_by_id != user.id:
            return None, project, "FORBIDDEN"
    return entity, project, None


def _work_item_value(issue):
    cycle_id = (
        CycleIssue.objects.filter(issue=issue, cycle__deleted_at__isnull=True)
        .values_list("cycle_id", flat=True)
        .first()
    )
    return {
        "id": str(issue.id),
        "projectId": str(issue.project_id),
        "sequenceId": issue.sequence_id,
        "name": issue.name,
        "stateId": str(issue.state_id) if issue.state_id else None,
        "priority": issue.priority,
        "assigneeIds": [
            str(value) for value in IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)
        ],
        "labelIds": [
            str(value)
            for value in IssueLabel.objects.filter(issue=issue, label__deleted_at__isnull=True).values_list(
                "label_id", flat=True
            )
        ],
        "startDate": _iso(issue.start_date),
        "targetDate": _iso(issue.target_date),
        "estimatePointId": (
            str(issue.estimate_point_id)
            if issue.estimate_point_id and EstimatePoint.objects.filter(id=issue.estimate_point_id).exists()
            else None
        ),
        "cycleId": str(cycle_id) if cycle_id else None,
        "moduleIds": [
            str(value)
            for value in ModuleIssue.objects.filter(issue=issue, module__deleted_at__isnull=True).values_list(
                "module_id", flat=True
            )
        ],
        "updatedAt": _iso(issue.updated_at),
    }


def _entity_value(entity, reference, project):
    entity_type = reference["entityType"]
    if entity_type == "work_item":
        return _work_item_value(entity)
    if entity_type == "project":
        return {
            "id": str(entity.id),
            "name": entity.name,
            "identifier": entity.identifier,
            "description": entity.description,
            "archivedAt": _iso(entity.archived_at),
            "updatedAt": _iso(entity.updated_at),
        }
    if entity_type == "cycle":
        return {
            "id": str(entity.id),
            "projectId": str(entity.project_id),
            "name": entity.name,
            "description": entity.description,
            "status": None,
            "startDate": _iso(entity.start_date),
            "endDate": _iso(entity.end_date),
            "archivedAt": _iso(entity.archived_at),
            "updatedAt": _iso(entity.updated_at),
        }
    if entity_type == "module":
        return {
            "id": str(entity.id),
            "projectId": str(entity.project_id),
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
            "startDate": _iso(entity.start_date),
            "targetDate": _iso(entity.target_date),
            "archivedAt": _iso(entity.archived_at),
            "updatedAt": _iso(entity.updated_at),
        }
    if entity_type == "page":
        return {
            "id": str(entity.id),
            "name": entity.name,
            "projectIds": [str(project.id)],
            "access": entity.access,
            "isLocked": entity.is_locked,
            "archivedAt": _iso(entity.archived_at),
            "updatedAt": _iso(entity.updated_at),
        }
    if entity_type == "view":
        return {
            "id": str(entity.id),
            "projectId": str(entity.project_id),
            "name": entity.name,
            "description": entity.description,
            "access": entity.access,
            "isLocked": entity.is_locked,
            "updatedAt": _iso(entity.updated_at),
        }
    _validation_error("Unsupported entity type")


def _work_item_field(issue, field):
    if field == "name":
        return issue.name
    if field == "description":
        return issue.description_html
    if field == "state":
        state = State.objects.filter(id=issue.state_id).first() if issue.state_id else None
        return {"id": str(state.id), "name": state.name, "group": state.group} if state else None
    if field == "priority":
        return issue.priority
    if field == "assignees":
        return [
            {"id": str(assignment.assignee_id), "displayName": assignment.assignee.display_name}
            for assignment in IssueAssignee.objects.filter(issue=issue).select_related("assignee")
        ]
    if field == "labels":
        return [
            {"id": str(assignment.label_id), "name": assignment.label.name}
            for assignment in IssueLabel.objects.filter(issue=issue, label__deleted_at__isnull=True).select_related(
                "label"
            )
        ]
    if field == "start_date":
        return _iso(issue.start_date)
    if field == "target_date":
        return _iso(issue.target_date)
    if field == "estimate":
        point = EstimatePoint.objects.filter(id=issue.estimate_point_id).first() if issue.estimate_point_id else None
        return {"id": str(point.id), "key": point.key, "value": point.value} if point else None
    if field == "cycle":
        assignment = (
            CycleIssue.objects.filter(issue=issue, cycle__deleted_at__isnull=True).select_related("cycle").first()
        )
        return {"id": str(assignment.cycle_id), "name": assignment.cycle.name} if assignment else None
    if field == "module":
        return [
            {"id": str(assignment.module_id), "name": assignment.module.name}
            for assignment in ModuleIssue.objects.filter(issue=issue, module__deleted_at__isnull=True).select_related(
                "module"
            )
        ]
    _validation_error("Unsupported work-item field")


def _canonical_success(reference, value, updated_at, observed_version, authorized_at):
    stale = observed_version is not None and observed_version != updated_at
    return {
        "ok": True,
        "reference": reference,
        "resolution": "canonical",
        "authorizedAt": authorized_at,
        "stale": stale,
        "canonical": {
            "source": "server_canonical",
            "value": value,
            "resolvedAt": authorized_at,
            "entityVersion": _iso(updated_at),
        },
    }


def _hydrate_item(user, item, authorized_at):
    reference = item["reference"]
    target = reference["entity"] if reference["kind"] == "field" else reference.get("document", reference)
    entity, project, error = _entity_access(user, target)
    if error:
        messages = {
            "FORBIDDEN": "The reference is not available to the acting user",
            "NOT_FOUND": "The reference does not exist in the asserted scope",
            "UNSUPPORTED": "The reference has no approved server resolver",
        }
        return _failure(reference, error, messages[error])

    if reference["kind"] in {"editor_block", "editor_range"}:
        return {
            "ok": True,
            "reference": reference,
            "resolution": "authorization_only",
            "authorizedAt": authorized_at,
            "stale": False,
        }
    value = (
        _work_item_field(entity, reference["fieldKey"])
        if reference["kind"] == "field"
        else _entity_value(entity, reference, project)
    )
    return _canonical_success(
        reference,
        value,
        entity.updated_at,
        item["observedEntityVersion"],
        authorized_at,
    )


def hydrate_semantic_context(user, workspace_slug, items, now=None):
    validated_items = [validate_hydration_item(item) for item in items]
    authorized_at = (now or timezone.now)().isoformat()
    workspace_access = WorkspaceMember.objects.filter(
        workspace__slug=workspace_slug,
        member=user,
        is_active=True,
    ).exists()
    results = []
    for item in validated_items:
        reference = item["reference"]
        target = reference["entity"] if reference["kind"] == "field" else reference.get("document", reference)
        if target["workspaceSlug"] != workspace_slug:
            raise serializers.ValidationError("Reference workspaceSlug must match the endpoint workspace")
        if not workspace_access:
            results.append(_failure(reference, "FORBIDDEN", "The workspace is not available to the acting user"))
        else:
            results.append(_hydrate_item(user, item, authorized_at))
    return {"schemaVersion": SCHEMA_VERSION, "results": results}

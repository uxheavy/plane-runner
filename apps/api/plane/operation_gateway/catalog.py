"""Versioned semantic Plane operations exposed by the shared gateway.

The catalog is descriptive only.  It never grants permission; the gateway
asks the operation adapter to evaluate the caller against Plane's live
permission classes before invoking the canonical application service seam.
"""

from dataclasses import dataclass
from typing import Literal

from .contracts import SCHEMA_VERSION


OperationKind = Literal["read", "mutation"]
PermissionFamily = Literal["none", "workspace", "project"]


@dataclass(frozen=True)
class OperationDescriptor:
    operation_id: str
    schema_version: str
    kind: OperationKind
    family: str
    summary: str
    required_input: tuple[str, ...]
    input_fields: tuple[str, ...]
    max_result_bytes: int
    handler: str
    result_key: str
    permission: PermissionFamily


def _descriptor(
    operation_id: str,
    *,
    kind: OperationKind,
    family: str,
    summary: str,
    required_input: tuple[str, ...] = (),
    input_fields: tuple[str, ...] = (),
    max_result_bytes: int = 8 * 1024,
    handler: str | None = None,
    result_key: str,
    permission: PermissionFamily = "project",
) -> OperationDescriptor:
    return OperationDescriptor(
        operation_id=operation_id,
        schema_version=SCHEMA_VERSION,
        kind=kind,
        family=family,
        summary=summary,
        required_input=required_input,
        input_fields=input_fields,
        max_result_bytes=max_result_bytes,
        handler=handler or operation_id.replace(".", "_"),
        result_key=result_key,
        permission=permission,
    )


COMMON_PROJECT_FIELDS = ("project_id", "params", "cursor", "per_page", "order_by", "fields", "expand")
COMMON_RESOURCE_FIELDS = COMMON_PROJECT_FIELDS + (
    "name",
    "description",
    "description_html",
    "external_source",
    "external_id",
)


OPERATION_CATALOG: dict[str, OperationDescriptor] = {
    "user.me": _descriptor(
        "user.me",
        kind="read",
        family="user",
        summary="Read the authenticated Plane user projection.",
        result_key="user",
        permission="none",
        handler="user_me",
    ),
    "work_item.read": _descriptor(
        "work_item.read",
        kind="read",
        family="work_item",
        summary="Read one bounded Plane work item projection.",
        required_input=("project_id", "issue_id"),
        input_fields=("project_id", "issue_id"),
        max_result_bytes=4096,
        result_key="work_item",
        handler="work_item_read",
    ),
    "work_item.rename": _descriptor(
        "work_item.rename",
        kind="mutation",
        family="work_item",
        summary="Rename one Plane work item through the existing issue service.",
        required_input=("project_id", "issue_id", "name"),
        input_fields=("project_id", "issue_id", "name"),
        max_result_bytes=4096,
        result_key="work_item",
        handler="work_item_rename",
    ),
    "work_item_attachment.list": _descriptor(
        "work_item_attachment.list",
        kind="read",
        family="work_item_attachment",
        summary="List bounded uploaded work-item attachments.",
        required_input=("project_id", "issue_id"),
        input_fields=("project_id", "issue_id"),
        result_key="attachments",
        handler="work_item_attachment_list",
    ),
    "work_item_attachment.download_url": _descriptor(
        "work_item_attachment.download_url",
        kind="read",
        family="work_item_attachment",
        summary="Issue one bounded attachment download URL.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="attachment",
        handler="work_item_attachment_download_url",
    ),
    "work_item_attachment.upload_from_url": _descriptor(
        "work_item_attachment.upload_from_url",
        kind="mutation",
        family="work_item_attachment",
        summary="Fetch one bounded public URL into work-item storage.",
        required_input=("project_id", "issue_id", "url"),
        input_fields=("project_id", "issue_id", "url", "name"),
        result_key="attachment",
        handler="work_item_attachment_upload_from_url",
    ),
    "work_item_attachment.delete": _descriptor(
        "work_item_attachment.delete",
        kind="mutation",
        family="work_item_attachment",
        summary="Delete one work-item attachment through Plane storage.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="deleted",
        handler="work_item_attachment_delete",
    ),
    "work_item_attachment.read": _descriptor(
        "work_item_attachment.read",
        kind="read",
        family="work_item_attachment",
        summary="Authorize one bounded work-item attachment read.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="attachment_read",
        handler="work_item_attachment_read",
    ),
}


def _add_resource_operations(
    *,
    prefix: str,
    family: str,
    resource_label: str,
    result_key: str,
    fields: tuple[str, ...],
    retrieve_id: str,
    permission: PermissionFamily = "project",
    max_result_bytes: int = 8 * 1024,
    list_required_input: tuple[str, ...] | None = None,
    create_required_input: tuple[str, ...] | None = None,
    list_result_key: str | None = None,
) -> None:
    """Register one complete CRUD family with explicit typed descriptors."""

    OPERATION_CATALOG.update(
        {
            f"{prefix}.list": _descriptor(
                f"{prefix}.list",
                kind="read",
                family=family,
                summary=f"List bounded {resource_label} records through a canonical Plane application adapter.",
                required_input=list_required_input
                if list_required_input is not None
                else tuple(field for field in fields if field == "project_id"),
                input_fields=fields,
                result_key=list_result_key or f"{result_key}s",
                permission=permission,
                max_result_bytes=max_result_bytes,
            ),
            f"{prefix}.create": _descriptor(
                f"{prefix}.create",
                kind="mutation",
                family=family,
                summary=f"Create one {resource_label} through a canonical Plane application adapter.",
                required_input=create_required_input
                if create_required_input is not None
                else tuple(field for field in fields if field == "project_id")
                + tuple(field for field in fields if field == "name"),
                input_fields=fields,
                result_key=result_key,
                permission=permission,
                max_result_bytes=max_result_bytes,
            ),
            f"{prefix}.retrieve": _descriptor(
                f"{prefix}.retrieve",
                kind="read",
                family=family,
                summary=f"Retrieve one {resource_label} through a canonical Plane application adapter.",
                required_input=("project_id", retrieve_id),
                input_fields=fields + (retrieve_id,),
                result_key=result_key,
                permission=permission,
                max_result_bytes=max_result_bytes,
            ),
            f"{prefix}.update": _descriptor(
                f"{prefix}.update",
                kind="mutation",
                family=family,
                summary=f"Update one {resource_label} through a canonical Plane application adapter.",
                required_input=("project_id", retrieve_id),
                input_fields=fields + (retrieve_id,),
                result_key=result_key,
                permission=permission,
                max_result_bytes=max_result_bytes,
            ),
        }
    )


_add_resource_operations(
    prefix="work_item",
    family="work_item",
    resource_label="work item",
    result_key="work_item",
    fields=COMMON_RESOURCE_FIELDS
    + (
        "issue_id",
        "assignees",
        "labels",
        "type_id",
        "point",
        "priority",
        "start_date",
        "target_date",
        "sort_order",
        "is_draft",
        "parent",
        "state",
        "estimate_point",
        "type",
    ),
    retrieve_id="issue_id",
)
_add_resource_operations(
    prefix="cycle",
    family="cycle",
    resource_label="cycle",
    result_key="cycle",
    fields=COMMON_RESOURCE_FIELDS
    + ("cycle_id", "start_date", "end_date", "owned_by", "timezone", "archived", "status"),
    retrieve_id="cycle_id",
    create_required_input=("project_id", "name", "owned_by"),
    list_result_key="cycles",
)
_add_resource_operations(
    prefix="module",
    family="module",
    resource_label="module",
    result_key="module",
    fields=COMMON_RESOURCE_FIELDS + ("module_id", "start_date", "target_date", "status", "lead", "members", "archived"),
    retrieve_id="module_id",
    list_result_key="modules",
)
_add_resource_operations(
    prefix="project",
    family="project",
    resource_label="project",
    result_key="project",
    fields=(
        "project_id",
        "cursor",
        "per_page",
        "order_by",
        "fields",
        "expand",
        "name",
        "identifier",
        "description",
        "project_lead",
        "default_assignee",
        "emoji",
        "cover_image",
        "network",
        "module_view",
        "cycle_view",
        "issue_views_view",
        "page_view",
        "intake_view",
        "guest_view_all_features",
        "archive_in",
        "close_in",
        "timezone",
        "external_source",
        "external_id",
        "is_issue_type_enabled",
        "is_time_tracking_enabled",
        "default_state",
        "estimate",
    ),
    retrieve_id="project_id",
    permission="workspace",
    max_result_bytes=12 * 1024,
    list_required_input=(),
    create_required_input=("name", "identifier"),
    list_result_key="projects",
)
_add_resource_operations(
    prefix="state",
    family="state",
    resource_label="state",
    result_key="state",
    fields=COMMON_PROJECT_FIELDS
    + ("state_id", "name", "color", "description", "sequence", "group", "is_triage", "default"),
    retrieve_id="state_id",
    create_required_input=("project_id", "name", "color"),
    list_result_key="states",
)
_add_resource_operations(
    prefix="label",
    family="label",
    resource_label="label",
    result_key="label",
    fields=COMMON_PROJECT_FIELDS
    + ("label_id", "name", "color", "description", "parent", "sort_order", "external_source", "external_id"),
    retrieve_id="label_id",
    create_required_input=("project_id", "name"),
    list_result_key="labels",
)
_add_resource_operations(
    prefix="link",
    family="work_item_link",
    resource_label="work item link",
    result_key="link",
    fields=COMMON_PROJECT_FIELDS + ("issue_id", "link_id", "url"),
    retrieve_id="link_id",
    list_required_input=("project_id", "issue_id"),
    create_required_input=("project_id", "issue_id", "url"),
    list_result_key="links",
)
_add_resource_operations(
    prefix="comment",
    family="work_item_comment",
    resource_label="work item comment",
    result_key="comment",
    fields=COMMON_PROJECT_FIELDS
    + (
        "issue_id",
        "comment_id",
        "comment_html",
        "comment_json",
        "access",
        "external_source",
        "external_id",
    ),
    retrieve_id="comment_id",
    list_required_input=("project_id", "issue_id"),
    create_required_input=("project_id", "issue_id"),
    list_result_key="comments",
)
_add_resource_operations(
    prefix="intake",
    family="intake",
    resource_label="intake work item",
    result_key="intake_work_item",
    fields=COMMON_PROJECT_FIELDS
    + ("work_item_id", "data", "status", "snoozed_till", "duplicate_to", "source", "source_email"),
    retrieve_id="work_item_id",
    create_required_input=("project_id", "data"),
    list_result_key="intake_work_items",
)

for operation_id, descriptor in (
    (
        "page.list",
        _descriptor(
            "page.list",
            kind="read",
            family="page",
            summary="List bounded project pages.",
            input_fields=("project_id", "params", "cursor", "per_page", "order_by", "fields", "expand"),
            result_key="pages",
        ),
    ),
    (
        "page.retrieve",
        _descriptor(
            "page.retrieve",
            kind="read",
            family="page",
            summary="Retrieve one project page.",
            required_input=("page_id",),
            input_fields=("page_id", "project_id", "track_visit"),
            result_key="page",
        ),
    ),
    (
        "page.create",
        _descriptor(
            "page.create",
            kind="mutation",
            family="page",
            summary="Create one project page.",
            required_input=("name", "description_html"),
            input_fields=(
                "name",
                "description_html",
                "project_id",
                "access",
                "color",
                "is_locked",
                "archived_at",
                "view_props",
                "logo_props",
                "external_id",
                "external_source",
            ),
            result_key="page",
        ),
    ),
    (
        "project_member.list",
        _descriptor(
            "project_member.list",
            kind="read",
            family="member",
            summary="List project members with Plane membership state.",
            required_input=("project_id",),
            input_fields=(
                "project_id",
                "first_name",
                "last_name",
                "email",
                "display_name",
                "role_slug",
                "is_active",
                "is_bot",
                "cursor",
                "per_page",
                "order_by",
            ),
            result_key="members",
        ),
    ),
    (
        "workspace_member.list",
        _descriptor(
            "workspace_member.list",
            kind="read",
            family="member",
            summary="List workspace members with Plane membership state.",
            input_fields=(
                "first_name",
                "last_name",
                "email",
                "display_name",
                "role_slug",
                "is_active",
                "is_bot",
                "cursor",
                "per_page",
                "order_by",
            ),
            result_key="members",
            permission="workspace",
            max_result_bytes=12 * 1024,
        ),
    ),
):
    OPERATION_CATALOG[operation_id] = descriptor


# This is the explicit executable seam used by the MCP generator and contract
# tests.  Descriptors for other Plane-shaped families remain useful metadata,
# but they are not executable until a direct adapter is registered here.
IMPLEMENTED_OPERATION_IDS = frozenset(
    {
        "user.me",
        "work_item.read",
        "work_item.rename",
        "work_item_attachment.list",
        "work_item_attachment.download_url",
        "work_item_attachment.upload_from_url",
        "work_item_attachment.delete",
        "work_item_attachment.read",
        "page.list",
        "page.retrieve",
        "page.create",
        "project_member.list",
        "workspace_member.list",
        "intake.list",
        "intake.retrieve",
        "intake.create",
        "intake.update",
    }
    | {
        f"{prefix}.{action}"
        for prefix in ("cycle", "module", "project", "state", "label", "link", "comment")
        for action in ("list", "create", "retrieve", "update")
    }
)


def get_operation(operation_id: str) -> OperationDescriptor | None:
    return OPERATION_CATALOG.get(operation_id)


def all_operations() -> tuple[OperationDescriptor, ...]:
    return tuple(OPERATION_CATALOG.values())

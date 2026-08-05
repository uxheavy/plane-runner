"""Small explicit operation catalog; metadata never grants authorization."""

from dataclasses import dataclass
from typing import Literal

from .contracts import SCHEMA_VERSION


@dataclass(frozen=True)
class OperationDescriptor:
    operation_id: str
    schema_version: str
    kind: Literal["read", "mutation"]
    summary: str
    required_input: tuple[str, ...]
    max_result_bytes: int
    handler: str
    result_key: str


OPERATION_CATALOG: dict[str, OperationDescriptor] = {
    "work_item.read": OperationDescriptor(
        operation_id="work_item.read",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="Read one bounded Plane work item projection.",
        required_input=("project_id", "issue_id"),
        max_result_bytes=4096,
        handler="work_item_read",
        result_key="work_item",
    ),
    "work_item.rename": OperationDescriptor(
        operation_id="work_item.rename",
        schema_version=SCHEMA_VERSION,
        kind="mutation",
        summary="Rename one Plane work item through the existing issue service.",
        required_input=("project_id", "issue_id", "name"),
        max_result_bytes=4096,
        handler="work_item_rename",
        result_key="work_item",
    ),
    "user.me": OperationDescriptor(
        operation_id="user.me",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="Read the authenticated Plane user projection.",
        required_input=(),
        max_result_bytes=4096,
        handler="user_me",
        result_key="user",
    ),
    "work_item_attachment.list": OperationDescriptor(
        operation_id="work_item_attachment.list",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="List bounded uploaded attachments for one Plane work item.",
        required_input=("project_id", "issue_id"),
        max_result_bytes=8192,
        handler="work_item_attachment_list",
        result_key="attachments",
    ),
    "work_item_attachment.download_url": OperationDescriptor(
        operation_id="work_item_attachment.download_url",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="Issue one bounded presigned download URL for a work item attachment.",
        required_input=("project_id", "issue_id", "attachment_id"),
        max_result_bytes=4096,
        handler="work_item_attachment_download_url",
        result_key="attachment",
    ),
    "work_item_attachment.upload_from_url": OperationDescriptor(
        operation_id="work_item_attachment.upload_from_url",
        schema_version=SCHEMA_VERSION,
        kind="mutation",
        summary="Fetch one public bounded source and attach it through Plane storage.",
        required_input=("project_id", "issue_id", "url"),
        max_result_bytes=8192,
        handler="work_item_attachment_upload_from_url",
        result_key="attachment",
    ),
    "work_item_attachment.delete": OperationDescriptor(
        operation_id="work_item_attachment.delete",
        schema_version=SCHEMA_VERSION,
        kind="mutation",
        summary="Soft-delete one work item attachment through Plane’s attachment service.",
        required_input=("project_id", "issue_id", "attachment_id"),
        max_result_bytes=1024,
        handler="work_item_attachment_delete",
        result_key="deleted",
    ),
    "work_item_attachment.read": OperationDescriptor(
        operation_id="work_item_attachment.read",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="Authorize and issue a bounded content-read URL for an attachment.",
        required_input=("project_id", "issue_id", "attachment_id"),
        max_result_bytes=4096,
        handler="work_item_attachment_read",
        result_key="attachment_read",
    ),
}


def get_operation(operation_id: str) -> OperationDescriptor | None:
    return OPERATION_CATALOG.get(operation_id)

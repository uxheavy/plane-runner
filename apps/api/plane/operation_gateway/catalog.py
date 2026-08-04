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


OPERATION_CATALOG: dict[str, OperationDescriptor] = {
    "work_item.read": OperationDescriptor(
        operation_id="work_item.read",
        schema_version=SCHEMA_VERSION,
        kind="read",
        summary="Read one bounded Plane work item projection.",
        required_input=("project_id", "issue_id"),
        max_result_bytes=4096,
        handler="work_item_read",
    ),
    "work_item.rename": OperationDescriptor(
        operation_id="work_item.rename",
        schema_version=SCHEMA_VERSION,
        kind="mutation",
        summary="Rename one Plane work item through the existing issue service.",
        required_input=("project_id", "issue_id", "name"),
        max_result_bytes=4096,
        handler="work_item_rename",
    ),
}


def get_operation(operation_id: str) -> OperationDescriptor | None:
    return OPERATION_CATALOG.get(operation_id)

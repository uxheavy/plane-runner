"""Canonical Plane operation catalog.

The catalog describes availability and presentation only.  It never grants
permission; the Operation Gateway evaluates the live Plane caller for every
dispatch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .contracts import SCHEMA_VERSION, canonical_json

CatalogKind = Literal["read", "mutation"]
AuthorizationScope = Literal["workspace", "project"]
CodeModeCallbackKind = Literal["search", "describe", "operation"]

CODE_MODE_CALLBACK_NAMES: Mapping[CodeModeCallbackKind, str] = MappingProxyType(
    {
        "search": "search_plane_operations",
        "describe": "describe_plane_operation",
        "operation": "call_plane_operation",
    }
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class OperationDescriptor:
    operation_id: str
    schema_version: str
    kind: CatalogKind
    summary: str
    required_input: tuple[str, ...]
    max_result_bytes: int
    handler: str
    name: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    result_schema: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    authorization_scope: AuthorizationScope = "project"
    universal: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_schema", _freeze(dict(self.input_schema)))
        object.__setattr__(self, "result_schema", _freeze(dict(self.result_schema)))

    @property
    def operation_ref(self) -> str:
        return f"operation:{self.operation_id}"

    @property
    def schema_digest(self) -> str:
        value = {"inputSchema": _thaw(self.input_schema), "resultSchema": _thaw(self.result_schema)}
        return f"content:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


_UUID = {"type": "string", "format": "uuid"}
_WORK_ITEM_READ_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["project_id", "issue_id"],
    "properties": {"project_id": _UUID, "issue_id": _UUID},
}
_WORK_ITEM_RENAME_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["project_id", "issue_id", "name"],
    "properties": {"project_id": _UUID, "issue_id": _UUID, "name": {"type": "string", "minLength": 1}},
}
_SEARCH_WORKSPACE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "maxLength": 255},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "cursor": {"type": "string", "maxLength": 32},
    },
}
_CATALOG_SEARCH_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "maxLength": 255},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "cursor": {"type": "string", "maxLength": 32},
    },
}
_CATALOG_DESCRIBE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation_id"],
    "properties": {"operation_id": {"type": "string", "maxLength": 128, "minLength": 1}},
}
_WORK_ITEM_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["work_item"],
    "properties": {"work_item": {"type": "object"}},
}
_SEARCH_WORKSPACE_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {"type": "array", "maxItems": 50, "items": {"type": "object"}},
        "nextCursor": {"type": ["string", "null"]},
    },
}
_CATALOG_SEARCH_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operations"],
    "properties": {
        "operations": {"type": "array", "maxItems": 50, "items": {"type": "object"}},
        "nextCursor": {"type": ["string", "null"]},
    },
}
_CATALOG_DESCRIBE_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation"],
    "properties": {"operation": {"type": "object"}},
}


OPERATION_CATALOG: Mapping[str, OperationDescriptor] = MappingProxyType(
    {
        "search_workspace": OperationDescriptor(
            operation_id="search_workspace",
            schema_version=SCHEMA_VERSION,
            kind="read",
            summary="Search accessible Plane objects and return typed references.",
            required_input=("query",),
            max_result_bytes=8 * 1024,
            handler="search_workspace",
            name="search_workspace",
            input_schema=_SEARCH_WORKSPACE_INPUT,
            result_schema=_SEARCH_WORKSPACE_RESULT,
            tags=("core", "workspace", "search", "read"),
            authorization_scope="workspace",
            universal=True,
        ),
        "work_item.read": OperationDescriptor(
            operation_id="work_item.read",
            schema_version=SCHEMA_VERSION,
            kind="read",
            summary="Read one bounded Plane work item projection.",
            required_input=("project_id", "issue_id"),
            max_result_bytes=4096,
            handler="work_item_read",
            name="read_work_item",
            input_schema=_WORK_ITEM_READ_INPUT,
            result_schema=_WORK_ITEM_RESULT,
            tags=("work", "work-item", "read"),
            authorization_scope="project",
        ),
        "work_item.rename": OperationDescriptor(
            operation_id="work_item.rename",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Rename one Plane work item through the existing issue service.",
            required_input=("project_id", "issue_id", "name"),
            max_result_bytes=4096,
            handler="work_item_rename",
            name="rename_work_item",
            input_schema=_WORK_ITEM_RENAME_INPUT,
            result_schema=_WORK_ITEM_RESULT,
            tags=("work", "work-item", "mutation", "rename"),
            authorization_scope="project",
        ),
        "catalog.search": OperationDescriptor(
            operation_id="catalog.search",
            schema_version=SCHEMA_VERSION,
            kind="read",
            summary="Search the complete Plane operation catalog.",
            required_input=("query",),
            max_result_bytes=8 * 1024,
            handler="catalog_search",
            name="search_plane_operations",
            input_schema=_CATALOG_SEARCH_INPUT,
            result_schema=_CATALOG_SEARCH_RESULT,
            tags=("catalog", "discovery", "read"),
            authorization_scope="workspace",
        ),
        "catalog.describe": OperationDescriptor(
            operation_id="catalog.describe",
            schema_version=SCHEMA_VERSION,
            kind="read",
            summary="Describe one supported Plane operation and its schemas.",
            required_input=("operation_id",),
            max_result_bytes=8 * 1024,
            handler="catalog_describe",
            name="describe_plane_operation",
            input_schema=_CATALOG_DESCRIBE_INPUT,
            result_schema=_CATALOG_DESCRIBE_RESULT,
            tags=("catalog", "discovery", "read"),
            authorization_scope="workspace",
        ),
    }
)


def _catalog_entry(descriptor: OperationDescriptor) -> dict[str, Any]:
    return {
        "operationId": descriptor.operation_id,
        "operationRef": descriptor.operation_ref,
        "name": descriptor.name,
        "schemaVersion": descriptor.schema_version,
        "kind": descriptor.kind,
        "summary": descriptor.summary,
        "tags": list(descriptor.tags),
        "inputSchema": _thaw(descriptor.input_schema),
        "resultSchema": _thaw(descriptor.result_schema),
        "schemaDigest": descriptor.schema_digest,
        "maxResultBytes": descriptor.max_result_bytes,
        "universal": descriptor.universal,
    }


def _catalog_payload() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "codeModeCallbacks": dict(CODE_MODE_CALLBACK_NAMES),
        "operations": [_catalog_entry(OPERATION_CATALOG[key]) for key in sorted(OPERATION_CATALOG)],
    }


CATALOG_DIGEST = f"content:{hashlib.sha256(canonical_json(_catalog_payload()).encode('utf-8')).hexdigest()}"


def get_operation(operation_id: str) -> OperationDescriptor | None:
    return OPERATION_CATALOG.get(operation_id)


def code_mode_callback_names() -> dict[str, str]:
    return dict(CODE_MODE_CALLBACK_NAMES)


def operation_catalog_snapshot() -> dict[str, Any]:
    return {"catalogDigest": CATALOG_DIGEST, **_catalog_payload()}


def catalog_search(query: str = "", *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
    if not isinstance(query, str) or not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("catalog search input is invalid")
    if not 1 <= limit <= 50:
        raise ValueError("catalog search limit is invalid")
    offset = 0
    if cursor is not None:
        if not isinstance(cursor, str) or not cursor.startswith("cursor:"):
            raise ValueError("catalog search cursor is invalid")
        try:
            offset = int(cursor.removeprefix("cursor:"))
        except ValueError as exc:
            raise ValueError("catalog search cursor is invalid") from exc
        if offset < 0:
            raise ValueError("catalog search cursor is invalid")
    needle = query.strip().casefold()
    entries = [
        entry for entry in _catalog_payload()["operations"] if not needle or needle in canonical_json(entry).casefold()
    ]
    page = entries[offset : offset + limit]
    next_cursor = f"cursor:{offset + limit}" if offset + limit < len(entries) else None
    return {"operations": page, "nextCursor": next_cursor}


def describe_operation(operation_id: str) -> dict[str, Any]:
    descriptor = get_operation(operation_id)
    if descriptor is None:
        raise KeyError(operation_id)
    return {"operation": _catalog_entry(descriptor)}

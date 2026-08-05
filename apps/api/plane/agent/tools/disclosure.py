"""Presentation-only eager/progressive disclosure for Plane Agent runs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from plane.operation_gateway.catalog import CATALOG_DIGEST, OPERATION_CATALOG, OperationDescriptor


_RESERVED_PRESENTATION_KEYS = frozenset(
    {
        "allowed_operations",
        "allowedOperations",
        "operation_allowlist",
        "operationAllowlist",
        "authorization",
        "permissions",
    }
)
_PRESENTATION_KEYS = ("eager", "eager_operations", "eagerOperations")
_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _operation_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value.removeprefix("operation:")
    if not isinstance(value, Mapping):
        return None
    raw = value.get("operationId", value.get("operation_id", value.get("operationRef", value.get("operation_ref"))))
    return _operation_id(raw)


def _explicit_ids(presentation: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in _PRESENTATION_KEYS:
        if key in presentation:
            raw = presentation[key]
            if not isinstance(raw, list):
                raise ValueError("eager operation presentation must be a list")
            values.extend(raw)
    ids = []
    for raw in values:
        operation_id = _operation_id(raw)
        if operation_id is not None and operation_id not in ids:
            ids.append(operation_id)
    return ids


def _objective_tokens(assignment: Any) -> set[str]:
    objective = str(_value(assignment, "objective", ""))
    target_ref = str(_value(assignment, "target_ref", _value(assignment, "targetRef", "")))
    return set(_TOKEN_PATTERN.findall(f"{objective} {target_ref}".casefold()))


def _matches_assignment(descriptor: OperationDescriptor, tokens: set[str]) -> bool:
    searchable = set(
        _TOKEN_PATTERN.findall(" ".join((descriptor.name, descriptor.summary, *descriptor.tags)).casefold())
    )
    if descriptor.operation_id == "work_item.read" and "issue" in tokens:
        return True
    return bool(searchable & tokens)


def _entry(descriptor: OperationDescriptor) -> dict[str, Any]:
    return {
        "operationRef": descriptor.operation_ref,
        "schemaDigest": descriptor.schema_digest,
        "disclosure": "eager",
    }


def compose_tool_catalog(profile: Any, assignment: Any) -> dict[str, Any]:
    """Resolve prompt presentation without creating an authorization policy."""

    presentation = _value(profile, "tool_presentation", {}) or {}
    if not isinstance(presentation, Mapping):
        raise ValueError("tool presentation must be an object")
    forbidden = _RESERVED_PRESENTATION_KEYS & set(presentation)
    if forbidden:
        raise ValueError("tool presentation cannot define authorization or allowlists")

    selected: list[str] = []
    # The universal work core is one stable semantic operation. Everything
    # else is a presentation choice and remains globally discoverable.
    for operation_id in ("search_workspace", *_explicit_ids(presentation)):
        if operation_id in OPERATION_CATALOG and operation_id not in selected:
            selected.append(operation_id)

    tokens = _objective_tokens(assignment)
    for operation_id, descriptor in OPERATION_CATALOG.items():
        if descriptor.universal or operation_id in selected or descriptor.operation_id.startswith("catalog."):
            continue
        if _matches_assignment(descriptor, tokens):
            selected.append(operation_id)

    return {
        "catalogDigest": CATALOG_DIGEST,
        "eagerOperations": [_entry(OPERATION_CATALOG[operation_id]) for operation_id in selected],
    }


def progressive_operation_ids(eager_catalog: Mapping[str, Any]) -> tuple[str, ...]:
    eager_refs = {
        str(item.get("operationRef", "")).removeprefix("operation:")
        for item in eager_catalog.get("eagerOperations", [])
        if isinstance(item, Mapping)
    }
    return tuple(operation_id for operation_id in OPERATION_CATALOG if operation_id not in eager_refs)

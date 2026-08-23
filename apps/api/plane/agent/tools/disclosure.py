"""Presentation-only eager/progressive disclosure for Plane Agent runs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from plane.agent.validation import MAX_BOUNDED_BYTE_COUNT
from plane.operation_gateway.catalog import (
    CATALOG_DIGEST,
    OPERATION_CATALOG,
    OperationDescriptor,
    model_operation_entry,
)
from plane.operation_gateway.catalog import describe_operation
from plane.operation_gateway.contracts import canonical_json


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
MODEL_TOOLSET_KEY = "model_toolset"
MODEL_TOOLSETS = frozenset({"standard", "code_mode_only"})
MAX_EAGER_OPERATIONS = 64
MAX_EAGER_INPUT_SCHEMA_BYTES = MAX_BOUNDED_BYTE_COUNT // MAX_EAGER_OPERATIONS
MAX_EAGER_PRESENTATION_BYTES = MAX_BOUNDED_BYTE_COUNT // 2
STANDARD_ROUTE_SCHEMA_VERSION = "plane.standard-route/v1"
_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
_GENERIC_ASSIGNMENT_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "assigned",
        "authorized",
        "complete",
        "for",
        "gateway",
        "item",
        "plane",
        "result",
        "the",
        "through",
        "to",
        "work",
    }
)


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
    meaningful_tokens = tokens - _GENERIC_ASSIGNMENT_TOKENS
    searchable = set(
        _TOKEN_PATTERN.findall(" ".join((descriptor.name, descriptor.summary, *descriptor.tags)).casefold())
    )
    searchable -= _GENERIC_ASSIGNMENT_TOKENS
    if descriptor.operation_id == "work_item.read" and "issue" in tokens:
        return True
    return bool(searchable & meaningful_tokens)


def _entry(descriptor: OperationDescriptor) -> dict[str, Any]:
    operation = model_operation_entry(describe_operation(descriptor.operation_id)["operation"])
    input_schema = operation["inputSchema"]
    if not isinstance(input_schema, dict):
        raise ValueError(f"{descriptor.operation_id} input schema must be a JSON Schema object")
    input_schema_bytes = len(canonical_json(input_schema).encode("utf-8"))
    if input_schema_bytes > MAX_EAGER_INPUT_SCHEMA_BYTES:
        raise ValueError(
            f"{descriptor.operation_id} input schema exceeds {MAX_EAGER_INPUT_SCHEMA_BYTES} canonical JSON bytes"
        )
    return {
        "operationRef": descriptor.operation_ref,
        "schemaDigest": descriptor.schema_digest,
        "inputSchema": input_schema,
        "disclosure": "eager",
    }


def _standard_route(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"schemaVersion", "steps"}:
        raise ValueError("standardRoute has an invalid shape")
    if value.get("schemaVersion") != STANDARD_ROUTE_SCHEMA_VERSION:
        raise ValueError("standardRoute schemaVersion is unsupported")
    steps = value.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 7:
        raise ValueError("standardRoute steps must contain 1..7 items")
    normalized = []
    for step in steps:
        if not isinstance(step, Mapping) or set(step).difference(
            {"operationRef", "optional", "expectedStatus", "expectedErrorCode"}
        ) or "operationRef" not in step:
            raise ValueError("standardRoute has an invalid step")
        operation_id = _operation_id(step["operationRef"])
        if operation_id not in OPERATION_CATALOG:
            raise ValueError("standardRoute step is not a disclosed Plane operation")
        if step.get("optional") is not None and step.get("optional") is not True:
            raise ValueError("standardRoute optional must be true")
        if step.get("optional") is True and operation_id != "work_item.read":
            raise ValueError("standardRoute optional is reserved for prepared work_item.read")
        if step.get("expectedStatus") is not None and step.get("expectedStatus") != "denied":
            raise ValueError("standardRoute expectedStatus is unsupported")
        if step.get("expectedErrorCode") is not None and step.get("expectedErrorCode") != "NOT_AUTHORIZED":
            raise ValueError("standardRoute expectedErrorCode is unsupported")
        normalized.append(
            {
                "operationRef": f"operation:{operation_id}",
                **({"optional": True} if step.get("optional") is True else {}),
                **({"expectedStatus": "denied"} if step.get("expectedStatus") == "denied" else {}),
                **({"expectedErrorCode": "NOT_AUTHORIZED"} if step.get("expectedErrorCode") == "NOT_AUTHORIZED" else {}),
            }
        )
    return {"schemaVersion": STANDARD_ROUTE_SCHEMA_VERSION, "steps": normalized}


def compose_tool_catalog(profile: Any, assignment: Any) -> dict[str, Any]:
    """Resolve prompt presentation without creating an authorization policy."""

    presentation = _value(profile, "tool_presentation", {}) or {}
    if not isinstance(presentation, Mapping):
        raise ValueError("tool presentation must be an object")
    forbidden = _RESERVED_PRESENTATION_KEYS & set(presentation)
    if forbidden:
        raise ValueError("tool presentation cannot define authorization or allowlists")
    model_toolset = presentation.get(MODEL_TOOLSET_KEY, "standard")
    if model_toolset not in MODEL_TOOLSETS:
        raise ValueError("model_toolset must be standard or code_mode_only")
    route = _standard_route(presentation.get("standardRoute", presentation.get("standard_route")))
    if route is not None and model_toolset != "standard":
        raise ValueError("standardRoute is only supported by the standard model toolset")

    selected: list[str] = []
    # Keep the universal work core present, but let explicit route operations
    # lead the model-facing presentation. This is presentation only;
    # progressive discovery and gateway authorization stay unchanged.
    explicit_ids = _explicit_ids(presentation)
    for operation_id in (*explicit_ids, "search_workspace"):
        if operation_id in OPERATION_CATALOG and operation_id not in selected:
            if len(selected) >= MAX_EAGER_OPERATIONS:
                raise ValueError(f"eager operation presentation exceeds {MAX_EAGER_OPERATIONS} operations")
            selected.append(operation_id)

    # An explicit presentation is a route-level ordering contract, not an
    # authorization policy.  Keep the universal work core above, but do not
    # let assignment-token matching silently re-add a competing eager
    # mutation/read schema.  The complete catalog remains progressively
    # discoverable and gateway authorization is unchanged.
    if explicit_ids:
        return _bounded_eager_catalog(selected, model_toolset=model_toolset, standard_route=route)

    tokens = _objective_tokens(assignment)
    for operation_id, descriptor in OPERATION_CATALOG.items():
        if len(selected) >= MAX_EAGER_OPERATIONS:
            break
        if descriptor.universal or operation_id in selected or descriptor.operation_id.startswith("catalog."):
            continue
        if model_toolset == "code_mode_only" and operation_id == "work_item.rename":
            continue
        if _matches_assignment(descriptor, tokens):
            selected.append(operation_id)

    return _bounded_eager_catalog(selected, model_toolset=model_toolset, standard_route=route)


def _bounded_eager_catalog(
    selected: list[str], *, model_toolset: str = "standard", standard_route: dict[str, Any] | None = None
) -> dict[str, Any]:
    catalog = {
        "catalogDigest": CATALOG_DIGEST,
        "modelToolset": model_toolset,
        "eagerOperations": [_entry(OPERATION_CATALOG[operation_id]) for operation_id in selected],
    }
    if standard_route is not None:
        disclosed_refs = {entry["operationRef"] for entry in catalog["eagerOperations"]}
        if any(step["operationRef"] not in disclosed_refs for step in standard_route["steps"]):
            raise ValueError("standardRoute step is not disclosed in eagerOperations")
        catalog["standardRoute"] = standard_route
    presentation_bytes = len(canonical_json(catalog).encode("utf-8"))
    if presentation_bytes > MAX_EAGER_PRESENTATION_BYTES:
        raise ValueError(
            f"eager operation presentation exceeds {MAX_EAGER_PRESENTATION_BYTES} canonical JSON bytes"
        )
    return catalog

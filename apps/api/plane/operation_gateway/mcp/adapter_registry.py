"""Dependency-free runtime view of the generated MCP adapter registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


@dataclass(frozen=True)
class AdapterRegistration:
    tool_name: str
    adapter: str
    registration: str
    gateway_schema_version: str | None
    gateway_operation_id: str | None
    result_key: str | None
    result_mode: str
    input_aliases: dict[str, str]
    public_signature: str
    return_annotation: str
    sdk_entrypoints: tuple[str, ...]
    blocker: dict[str, Any] | None
    source_file: str
    source_line: int
    behavior: str
    mutation: bool
    capabilities: tuple[str, ...]
    preserves: tuple[str, ...]
    rationale_code: str


def _read_registry() -> dict[str, Any]:
    raw = files(__package__).joinpath("adapter_registry.json").read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("The MCP adapter registry must be an object")
    return value


def _validate_registry(value: dict[str, Any]) -> tuple[AdapterRegistration, ...]:
    if value.get("schema_version") != "plane.mcp-adapter-registry/v1":
        raise RuntimeError("Unsupported MCP adapter registry version")
    rows = value.get("actions")
    if not isinstance(rows, list) or value.get("tool_count") != len(rows):
        raise RuntimeError("The MCP adapter registry count is invalid")
    registrations = tuple(
        AdapterRegistration(
            tool_name=row["tool_name"],
            adapter=row["adapter"],
            registration=row["registration"],
            gateway_schema_version=row["gateway_schema_version"],
            gateway_operation_id=row["gateway_operation_id"],
            result_key=row["result_key"],
            result_mode=row["result_mode"],
            input_aliases=dict(row["input_aliases"]),
            public_signature=row["public_signature"],
            return_annotation=row["return_annotation"],
            sdk_entrypoints=tuple(row["sdk_entrypoints"]),
            blocker=row.get("blocker"),
            source_file=row["source_file"],
            source_line=row["source_line"],
            behavior=row["behavior"],
            mutation=row["mutation"],
            capabilities=tuple(row["capabilities"]),
            preserves=tuple(row["preserves"]),
            rationale_code=row["rationale_code"],
        )
        for row in rows
    )
    if len({row.tool_name for row in registrations}) != len(registrations):
        raise RuntimeError("The MCP adapter registry contains duplicate tools")
    for row in registrations:
        if (
            not row.source_file
            or row.source_line < 1
            or not isinstance(row.public_signature, str)
            or not row.return_annotation
        ):
            raise RuntimeError(f"Registration {row.tool_name!r} has incomplete public source metadata")
        if not row.preserves or not row.rationale_code:
            raise RuntimeError(f"Registration {row.tool_name!r} has incomplete contract evidence")
        if row.registration == "gateway":
            if not row.gateway_operation_id or row.gateway_schema_version != "plane.operation/v1":
                raise RuntimeError(f"Gateway registration {row.tool_name!r} is incomplete")
            if row.blocker is not None:
                raise RuntimeError(f"Gateway registration {row.tool_name!r} is blocked")
        elif row.registration == "blocked":
            if row.gateway_operation_id is not None or not isinstance(row.blocker, dict):
                raise RuntimeError(f"Blocked registration {row.tool_name!r} is not fail-closed")
        elif row.registration != "local":
            raise RuntimeError(f"Unknown registration state for {row.tool_name!r}")
    return registrations


ADAPTER_REGISTRY = _read_registry()
ADAPTER_REGISTRATIONS = _validate_registry(ADAPTER_REGISTRY)
_BY_TOOL = {registration.tool_name: registration for registration in ADAPTER_REGISTRATIONS}


def get_registration(tool_name: str) -> AdapterRegistration | None:
    return _BY_TOOL.get(tool_name)

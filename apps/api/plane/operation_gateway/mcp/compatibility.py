"""Fail-closed compatibility metadata for the external Plane MCP surface.

The manifest is intentionally separate from the Plane operation catalog. A
public MCP tool is not gateway-backed merely because it has a familiar name;
an exact semantic gateway operation, version, and compatibility adapter must
be recorded before a caller can route it through the gateway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Literal

from ..catalog import OPERATION_CATALOG

MCPCompatibilityManifest = dict[str, Any]
MCPDisposition = Literal["MCP-D-001", "MCP-D-002", "MCP-D-003"]
MCPAdapter = Literal["shared_sdk_transport", "local_pql", "hardened_attachment"]
MCPGatewayStatus = Literal["deferred", "local_only", "supported"]


class MCPCompatibilityError(ValueError):
    """A safe, machine-readable failure to route an MCP action."""

    def __init__(self, *, tool_name: str, code: str, rationale: str):
        super().__init__(rationale)
        self.tool_name = tool_name
        self.code = code
        self.rationale = rationale


@dataclass(frozen=True)
class MCPAction:
    """One complete, source-addressed disposition for one public MCP tool."""

    name: str
    category: str
    source_file: str
    source_line: int
    signature: str
    return_annotation: str
    disposition: MCPDisposition
    adapter: MCPAdapter
    gateway_status: MCPGatewayStatus
    gateway_operation_id: str | None
    mapping_kind: str
    behavior: str
    mutation: bool
    capabilities: tuple[str, ...]
    preserves: tuple[str, ...]
    rationale_code: str
    rationale: str
    sdk_entrypoints: tuple[str, ...]
    blocker: dict[str, Any] | None

    @classmethod
    def from_manifest(cls, value: dict[str, Any]) -> "MCPAction":
        return cls(
            name=value["name"],
            category=value["category"],
            source_file=value["source_file"],
            source_line=value["source_line"],
            signature=value["signature"],
            return_annotation=value["return_annotation"],
            disposition=value["disposition"],
            adapter=value["adapter"],
            gateway_status=value["gateway_status"],
            gateway_operation_id=value["gateway_operation_id"],
            mapping_kind=value["mapping_kind"],
            behavior=value["behavior"],
            mutation=value["mutation"],
            capabilities=tuple(value["capabilities"]),
            preserves=tuple(value["preserves"]),
            rationale_code=value["rationale_code"],
            rationale=value["rationale"],
            sdk_entrypoints=tuple(value.get("sdk_entrypoints", ())),
            blocker=value.get("blocker"),
        )


def _read_manifest() -> MCPCompatibilityManifest:
    raw = files(__package__).joinpath("manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise RuntimeError("The MCP compatibility manifest must be an object")
    return manifest


def _validate_manifest(manifest: MCPCompatibilityManifest) -> tuple[MCPAction, ...]:
    if manifest.get("schema_version") != "plane.mcp-compatibility/v1":
        raise RuntimeError("Unsupported MCP compatibility manifest version")

    source = manifest.get("source")
    raw_actions = manifest.get("actions")
    if not isinstance(source, dict) or not isinstance(raw_actions, list):
        raise RuntimeError("The MCP compatibility manifest is incomplete")
    if manifest.get("tool_count") != len(raw_actions):
        raise RuntimeError("The MCP compatibility manifest count does not match its rows")

    actions = tuple(MCPAction.from_manifest(value) for value in raw_actions)
    names = [action.name for action in actions]
    if len(set(names)) != len(names):
        raise RuntimeError("The MCP compatibility manifest contains duplicate tool names")

    for action in actions:
        if not action.name or not action.category or not action.source_file or action.source_line < 1:
            raise RuntimeError(f"MCP action {action.name!r} has incomplete source identity")
        if not isinstance(action.signature, str) or not isinstance(action.return_annotation, str):
            raise RuntimeError(f"MCP action {action.name!r} has incomplete public schema metadata")
        if not action.preserves or not action.rationale_code or not action.rationale.strip():
            raise RuntimeError(f"MCP action {action.name!r} has incomplete compatibility evidence")
        if action.disposition != "MCP-D-002" and not action.sdk_entrypoints:
            raise RuntimeError(f"MCP action {action.name!r} has no generated SDK entrypoint")
        if "*" in action.mapping_kind or "sdk_http_intent" in action.mapping_kind:
            raise RuntimeError(f"MCP action {action.name!r} uses a non-exact mapping kind")
        if action.gateway_status == "supported":
            if action.gateway_operation_id not in OPERATION_CATALOG:
                raise RuntimeError(f"MCP action {action.name!r} names an unregistered gateway operation")
            if action.blocker is not None:
                raise RuntimeError(f"Supported MCP action {action.name!r} cannot carry a blocker")
        elif action.gateway_operation_id is not None:
            raise RuntimeError(f"Deferred MCP action {action.name!r} cannot claim a gateway operation")
        elif action.disposition != "MCP-D-002":
            if not isinstance(action.blocker, dict) or not action.blocker.get("code"):
                raise RuntimeError(f"Deferred MCP action {action.name!r} has no machine-readable blocker")

        expected_adapter = {
            "MCP-D-001": "shared_sdk_transport",
            "MCP-D-002": "local_pql",
            "MCP-D-003": "hardened_attachment",
        }[action.disposition]
        if action.adapter != expected_adapter:
            raise RuntimeError(f"MCP action {action.name!r} has an inconsistent disposition adapter")

    return actions


MCP_COMPATIBILITY_MANIFEST = _read_manifest()
MCP_ACTIONS = _validate_manifest(MCP_COMPATIBILITY_MANIFEST)
_MCP_ACTIONS_BY_NAME = {action.name: action for action in MCP_ACTIONS}


def get_mcp_action(tool_name: str) -> MCPAction | None:
    """Return the exact disposition for a public tool, if it is inventoried."""

    return _MCP_ACTIONS_BY_NAME.get(tool_name)


def gateway_operation_for(tool_name: str) -> str | None:
    """Return only an explicitly registered semantic gateway operation.

    Deferred and local-only actions return ``None``. Callers must not fall
    back to a guessed operation or a direct Plane SDK/REST call.
    """

    action = get_mcp_action(tool_name)
    if action is None:
        raise MCPCompatibilityError(
            tool_name=tool_name,
            code="MCP_ACTION_NOT_INVENTORY",
            rationale="The external MCP action is not present in the pinned compatibility inventory.",
        )
    return action.gateway_operation_id


def require_gateway_operation(tool_name: str) -> str:
    """Fail closed until an exact gateway mapping is explicitly registered."""

    action = get_mcp_action(tool_name)
    if action is None:
        raise MCPCompatibilityError(
            tool_name=tool_name,
            code="MCP_ACTION_NOT_INVENTORY",
            rationale="The external MCP action is not present in the pinned compatibility inventory.",
        )
    if action.gateway_operation_id is None:
        raise MCPCompatibilityError(
            tool_name=tool_name,
            code="MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE",
            rationale=action.rationale,
        )
    return action.gateway_operation_id

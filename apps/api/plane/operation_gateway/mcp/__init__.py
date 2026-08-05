"""Compatibility metadata for the supported external Plane MCP surface."""

from .compatibility import (
    MCP_ACTIONS,
    MCP_COMPATIBILITY_MANIFEST,
    MCPCompatibilityError,
    MCPCompatibilityManifest,
    MCPAction,
    get_mcp_action,
    gateway_operation_for,
    require_gateway_operation,
)

__all__ = [
    "MCP_ACTIONS",
    "MCP_COMPATIBILITY_MANIFEST",
    "MCPAction",
    "MCPCompatibilityError",
    "MCPCompatibilityManifest",
    "gateway_operation_for",
    "get_mcp_action",
    "require_gateway_operation",
]

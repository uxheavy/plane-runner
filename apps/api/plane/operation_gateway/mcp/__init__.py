# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Compatibility metadata and pure adapters for the external Plane MCP surface."""

from .adapter_registry import get_registration
from .attachment_adapter import AttachmentGatewayAdapter, AttachmentImage
from .sdk_adapter import MCPAdapterError, MCPGatewayExecutionError, SharedSDKGatewayAdapter

__all__ = [
    "AttachmentGatewayAdapter",
    "AttachmentImage",
    "MCP_ACTIONS",
    "MCP_COMPATIBILITY_MANIFEST",
    "MCPAction",
    "MCPAdapterError",
    "MCPCompatibilityError",
    "MCPCompatibilityManifest",
    "MCPGatewayExecutionError",
    "SharedSDKGatewayAdapter",
    "gateway_operation_for",
    "get_mcp_action",
    "get_registration",
    "require_gateway_operation",
]


def __getattr__(name: str):
    """Load Django-backed compatibility metadata only for callers that need it."""

    if name in {
        "MCP_ACTIONS",
        "MCP_COMPATIBILITY_MANIFEST",
        "MCPAction",
        "MCPCompatibilityError",
        "MCPCompatibilityManifest",
        "gateway_operation_for",
        "get_mcp_action",
        "require_gateway_operation",
    }:
        from . import compatibility

        return getattr(compatibility, name)
    raise AttributeError(name)

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

"""Progressive discovery and gateway disposition projections for operators."""

from __future__ import annotations

from collections import Counter
from typing import Any

from plane.operation_gateway.catalog import CATALOG_DIGEST, OPERATION_CATALOG, catalog_search
from plane.operation_gateway.mcp.compatibility import MCP_ACTIONS


def gateway_status() -> dict[str, Any]:
    disposition = Counter(
        (
            "gateway"
            if action.gateway_status == "supported"
            else "local"
            if action.gateway_status == "local_only"
            else "unsupported"
        )
        for action in MCP_ACTIONS
    )
    unsupported = disposition["unsupported"]
    return {
        "catalog": {
            "digest": CATALOG_DIGEST,
            "operation_count": len(OPERATION_CATALOG),
        },
        "external_adapter_registry": {
            "schema_version": "plane.mcp-adapter-registry/v1",
            "tool_count": len(MCP_ACTIONS),
            "disposition": {
                "gateway": disposition["gateway"],
                # Keep the L10 field name as a compatibility alias while
                # exposing the canonical matrix disposition explicitly.
                "blocked": unsupported,
                "unsupported": unsupported,
                "local": disposition["local"],
            },
        },
        "shared_gateway": {
            "schema_version": "plane.operation/v1",
            "receipt_projection": [
                "request_id",
                "operation_id",
                "workspace_slug",
                "caller_id",
                "idempotency_key",
                "correlation_id",
                "request_digest",
                "state",
                "audit_receipt",
                "audit",
            ],
        },
    }


def catalog_page(*, query: str = "", limit: int = 10, cursor: str | None = None) -> dict[str, Any]:
    if isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("catalog limit must be between 1 and 50")
    result = catalog_search(query, limit=limit, cursor=cursor)
    return {
        "catalog_digest": CATALOG_DIGEST,
        "query": query,
        "limit": limit,
        "operations": result["operations"],
        "next_cursor": result["nextCursor"],
    }

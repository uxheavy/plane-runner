# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runtime MCP registrations derived from the pinned compatibility manifest."""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog import OPERATION_CATALOG
from ..limits import MAX_RESULT_BYTES
from .compatibility import MCP_COMPATIBILITY_MANIFEST, get_mcp_action


@dataclass(frozen=True)
class AdapterRegistration:
    tool_name: str
    gateway_operation_id: str
    result_key: str
    result_mode: str
    input_aliases: dict[str, str]
    result_limit_bytes: int


def _registrations() -> dict[str, AdapterRegistration]:
    registrations = {}
    for tool_name, override in MCP_COMPATIBILITY_MANIFEST["gateway_overrides"].items():
        action = get_mcp_action(tool_name)
        operation_id = override.get("operation_id")
        descriptor = OPERATION_CATALOG.get(operation_id)
        result_key = override.get("result_key")
        result_mode = override.get("result_mode", "value")
        input_aliases = override.get("input_aliases", {})
        if (
            action is None
            or action.gateway_operation_id != operation_id
            or descriptor is None
            or not isinstance(result_key, str)
            or not result_key
            or result_mode not in {"content", "none", "value"}
            or not isinstance(input_aliases, dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in input_aliases.items())
            or not 1 <= descriptor.max_result_bytes <= MAX_RESULT_BYTES
        ):
            raise RuntimeError(f"Invalid MCP runtime registration for {tool_name!r}")
        registrations[tool_name] = AdapterRegistration(
            tool_name=tool_name,
            gateway_operation_id=operation_id,
            result_key=result_key,
            result_mode=result_mode,
            input_aliases=dict(input_aliases),
            result_limit_bytes=descriptor.max_result_bytes,
        )
    return registrations


_BY_TOOL = _registrations()


def get_registration(tool_name: str) -> AdapterRegistration | None:
    return _BY_TOOL.get(tool_name)

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Dependency-free runtime view of the generated MCP adapter registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from ..limits import MAX_RESULT_BYTES


@dataclass(frozen=True)
class AdapterRegistration:
    tool_name: str
    adapter: str
    registration: str
    disposition: str
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
    handler: str | None
    catalog_schema_digest: str | None
    authorization_service: str
    result_limit_bytes: int
    identity_mode: str
    idempotency_policy: str
    audit_policy: str
    representative_test: str


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
            disposition=row.get(
                "disposition",
                {
                    "gateway": "MCP-D-001",
                    "unsupported": "MCP-D-004",
                    "local": "MCP-D-002",
                }.get(row["registration"], ""),
            ),
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
            handler=row["handler"],
            catalog_schema_digest=row["catalog_schema_digest"],
            authorization_service=row["authorization_service"],
            result_limit_bytes=row["result_limit_bytes"],
            identity_mode=row["identity_mode"],
            idempotency_policy=row["idempotency_policy"],
            audit_policy=row["audit_policy"],
            representative_test=row["representative_test"],
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
        if (
            isinstance(row.result_limit_bytes, bool)
            or not isinstance(row.result_limit_bytes, int)
            or not 1 <= row.result_limit_bytes <= MAX_RESULT_BYTES
            or not row.identity_mode
            or not row.idempotency_policy
            or not row.audit_policy
        ):
            raise RuntimeError(f"Registration {row.tool_name!r} has incomplete matrix bounds or policy metadata")
        expected_dispositions = {
            "gateway": {"MCP-D-001", "MCP-D-003"},
            "unsupported": "MCP-D-004",
            "local": "MCP-D-002",
        }.get(row.registration)
        if isinstance(expected_dispositions, set):
            valid_disposition = row.disposition in expected_dispositions
        else:
            valid_disposition = row.disposition == expected_dispositions
        if not valid_disposition:
            raise RuntimeError(f"Registration {row.tool_name!r} has an invalid disposition")
        if row.registration == "gateway":
            if not row.gateway_operation_id or row.gateway_schema_version != "plane.operation/v1":
                raise RuntimeError(f"Gateway registration {row.tool_name!r} is incomplete")
            if row.blocker is not None:
                raise RuntimeError(f"Gateway registration {row.tool_name!r} is blocked")
        elif row.registration == "unsupported":
            if row.gateway_operation_id is not None or not isinstance(row.blocker, dict):
                raise RuntimeError(f"Unsupported registration {row.tool_name!r} is not fail-closed")
        elif row.registration != "local":
            raise RuntimeError(f"Unknown registration state for {row.tool_name!r}")
    return registrations


ADAPTER_REGISTRY = _read_registry()
ADAPTER_REGISTRATIONS = _validate_registry(ADAPTER_REGISTRY)
_BY_TOOL = {registration.tool_name: registration for registration in ADAPTER_REGISTRATIONS}


def get_registration(tool_name: str) -> AdapterRegistration | None:
    return _BY_TOOL.get(tool_name)

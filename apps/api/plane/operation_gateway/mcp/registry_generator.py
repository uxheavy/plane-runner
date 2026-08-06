"""Pure generator for the typed external MCP adapter registration.

The pinned manifest is the source of truth for public names and signatures.
This module derives one generic registration row per action; it does not
contain per-tool handlers or invent an operation for a missing semantic seam.
"""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
from typing import Any

from ..limits import MAX_RESULT_BYTES
from .manifest import effective_manifest

REGISTRY_SCHEMA_VERSION = "plane.mcp-adapter-registry/v1"
GATEWAY_SCHEMA_VERSION = "plane.operation/v1"
REPRESENTATIVE_TEST = "plane.tests.contract.api.test_operation_gateway_mcp::test_generated_action_matrix_is_executable"


def _catalog_metadata(operation_id: str | None) -> dict[str, Any]:
    """Add executable catalog metadata from the authoritative Plane catalog."""

    if not operation_id:
        return {
            "handler": None,
            "catalog_schema_digest": None,
            "authorization_service": "edition_api_absence",
            "result_limit_bytes": MAX_RESULT_BYTES,
        }
    from ..catalog import OPERATION_CATALOG

    try:
        descriptor = OPERATION_CATALOG[operation_id]
    except KeyError:
        raise ValueError(f"Catalog metadata is missing for supported operation {operation_id!r}") from None
    return {
        "handler": descriptor.handler,
        "catalog_schema_digest": descriptor.schema_digest,
        "authorization_service": f"live_{descriptor.authorization_scope}_permission",
        "result_limit_bytes": descriptor.max_result_bytes,
    }


def canonical_manifest_digest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_adapter_registry(manifest: dict[str, Any]) -> dict[str, Any]:
    """Generate registrations and reject unsupported implicit mappings."""

    manifest = effective_manifest(manifest)
    rows: list[dict[str, Any]] = []
    overrides = manifest.get("gateway_overrides", {})
    for action in manifest.get("actions", []):
        name = action["name"]
        override = overrides.get(name)
        supported = action["gateway_status"] == "supported"
        if supported:
            if not isinstance(override, dict):
                raise ValueError(f"No exact generated operation mapping exists for supported action {name!r}")
            operation_id = override["operation_id"]
            if (
                action.get("gateway_operation_id") != operation_id
                or not isinstance(operation_id, str)
                or not operation_id
            ):
                raise ValueError(f"Manifest operation mismatch for {name!r}")
            result_key = override["result_key"]
            result_mode = override.get("result_mode", "value")
            input_aliases = override.get("input_aliases", {})
            row = {
                "tool_name": name,
                "adapter": action["adapter"],
                "registration": "gateway",
                "disposition": action["disposition"],
                "gateway_schema_version": GATEWAY_SCHEMA_VERSION,
                "gateway_operation_id": operation_id,
                "result_key": result_key,
                "result_mode": result_mode,
                "input_aliases": input_aliases,
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": action.get("sdk_entrypoints", []),
            }
            row.update(_catalog_metadata(operation_id))
            row.update(
                {
                    "identity_mode": "external_user_binding",
                    "idempotency_policy": "gateway_per_caller_operation_key",
                    "audit_policy": "append_only_gateway_audit",
                    "representative_test": REPRESENTATIVE_TEST,
                }
            )
        elif action["disposition"] == "MCP-D-002":
            row = {
                "tool_name": name,
                "adapter": action["adapter"],
                "registration": "local",
                "disposition": action["disposition"],
                "gateway_schema_version": None,
                "gateway_operation_id": None,
                "result_key": None,
                "result_mode": "local",
                "input_aliases": {},
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": [],
                "handler": "local_pql_reference",
                "catalog_schema_digest": None,
                "authorization_service": "local_only_no_plane_authority",
                "result_limit_bytes": MAX_RESULT_BYTES,
                "identity_mode": "local_no_caller_binding",
                "idempotency_policy": "local_deterministic_reference",
                "audit_policy": "not_applicable_no_plane_authority",
                "representative_test": REPRESENTATIVE_TEST,
            }
        elif action["gateway_status"] == "unsupported" and action["disposition"] == "MCP-D-004":
            blocker = action.get("blocker")
            if not isinstance(blocker, dict) or blocker.get("action") != name:
                raise ValueError(f"Unsupported action {name!r} has no action-specific disposition")
            row = {
                "tool_name": name,
                "adapter": action["adapter"],
                "registration": "unsupported",
                "disposition": action["disposition"],
                "gateway_schema_version": None,
                "gateway_operation_id": None,
                "result_key": None,
                "result_mode": "unsupported",
                "input_aliases": {},
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": action.get("sdk_entrypoints", []),
                "blocker": blocker,
                "handler": None,
                "catalog_schema_digest": None,
                "authorization_service": "edition_api_absence",
                "result_limit_bytes": MAX_RESULT_BYTES,
                "identity_mode": "external_user_preserved_fail_closed",
                "idempotency_policy": "not_invoked_fail_closed",
                "audit_policy": "unsupported_disposition_registry",
                "representative_test": REPRESENTATIVE_TEST,
            }
        row.update(
            {
                "source_file": action["source_file"],
                "source_line": action["source_line"],
                "behavior": action["behavior"],
                "mutation": action["mutation"],
                "capabilities": action["capabilities"],
                "preserves": action["preserves"],
                "rationale_code": action["rationale_code"],
            }
        )
        rows.append(row)

    if len(rows) != manifest.get("tool_count") or len({row["tool_name"] for row in rows}) != len(rows):
        raise ValueError("Generated MCP adapter registration is not exhaustive and unique")
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "manifest_digest": canonical_manifest_digest(manifest),
        "source": manifest["source"],
        "tool_count": len(rows),
        "actions": rows,
    }


def render_adapter_registry(manifest: dict[str, Any]) -> str:
    return json.dumps(build_adapter_registry(manifest), indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or render the MCP adapter registry")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check", type=Path, help="Compare the generated registry with this checked-in artifact")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rendered = render_adapter_registry(manifest)
    if args.check:
        expected = json.loads(args.check.read_text(encoding="utf-8"))
        if json.loads(rendered) != expected:
            raise SystemExit("The checked-in MCP adapter registry is stale")
        print("MCP adapter registry is current")
        return 0
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

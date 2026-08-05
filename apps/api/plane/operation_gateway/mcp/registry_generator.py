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

from .manifest import effective_manifest

REGISTRY_SCHEMA_VERSION = "plane.mcp-adapter-registry/v1"
GATEWAY_SCHEMA_VERSION = "plane.operation/v1"


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
                "gateway_schema_version": GATEWAY_SCHEMA_VERSION,
                "gateway_operation_id": operation_id,
                "result_key": result_key,
                "result_mode": result_mode,
                "input_aliases": input_aliases,
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": action.get("sdk_entrypoints", []),
            }
        elif action["disposition"] == "MCP-D-002":
            row = {
                "tool_name": name,
                "adapter": action["adapter"],
                "registration": "local",
                "gateway_schema_version": None,
                "gateway_operation_id": None,
                "result_key": None,
                "result_mode": "local",
                "input_aliases": {},
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": [],
            }
        else:
            blocker = action.get("blocker")
            if not isinstance(blocker, dict) or blocker.get("action") != name:
                raise ValueError(f"Deferred action {name!r} has no action-specific blocker")
            row = {
                "tool_name": name,
                "adapter": action["adapter"],
                "registration": "blocked",
                "gateway_schema_version": None,
                "gateway_operation_id": None,
                "result_key": None,
                "result_mode": "blocked",
                "input_aliases": {},
                "public_signature": action["signature"],
                "return_annotation": action["return_annotation"],
                "sdk_entrypoints": action.get("sdk_entrypoints", []),
                "blocker": blocker,
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

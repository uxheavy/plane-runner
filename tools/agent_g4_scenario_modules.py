#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Validate and print the scenario modules staged at the live import boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MODULE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
SOURCE_RE = re.compile(r"tools/[A-Za-z0-9_.-]+\.py\Z")
RUNTIME_RE = re.compile(r"/run/plane-scenario/[A-Za-z0-9_.-]+\.py\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_MODULES = frozenset(
    {
        "agent_g4_live_scenario",
        "agent_g4_worker_route",
        "agent_g4_worker_route_observations",
        "agent_g4_manager_route",
        "agent_g4_operator_route",
    }
)


def scenario_modules(manifest_path: Path, root: Path) -> tuple[dict[str, str], ...]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("scenario_module_manifest_unreadable") from exc
    modules = manifest.get("scenarioModules") if isinstance(manifest, dict) else None
    if not isinstance(modules, list) or not modules:
        raise ValueError("scenario_module_manifest_missing")

    parsed: list[dict[str, str]] = []
    for item in modules:
        if not isinstance(item, dict) or set(item) != {"module", "source", "runtime", "sha256"}:
            raise ValueError("scenario_module_manifest_row_invalid")
        module = item["module"]
        source = item["source"]
        runtime = item["runtime"]
        sha256 = item["sha256"]
        if (
            not isinstance(module, str)
            or not MODULE_NAME_RE.fullmatch(module)
            or not isinstance(source, str)
            or not SOURCE_RE.fullmatch(source)
            or not isinstance(runtime, str)
            or not RUNTIME_RE.fullmatch(runtime)
            or not isinstance(sha256, str)
            or not SHA256_RE.fullmatch(sha256)
        ):
            raise ValueError("scenario_module_manifest_value_invalid")
        source_candidate = root / source
        source_path = source_candidate.resolve()
        if (
            source_candidate.parent != root / "tools"
            or source_candidate.is_symlink()
            or not source_candidate.is_file()
            or source_path.parent != (root / "tools").resolve()
        ):
            raise ValueError(f"scenario_module_source_missing:{module}")
        if Path(source).stem != module or Path(runtime).stem != module:
            raise ValueError(f"scenario_module_name_path_mismatch:{module}")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != sha256:
            raise ValueError(f"scenario_module_source_hash_mismatch:{module}")
        parsed.append({"module": module, "source": source, "runtime": runtime, "sha256": sha256})

    names = [item["module"] for item in parsed]
    if len(names) != len(set(names)):
        raise ValueError("scenario_module_manifest_duplicate")
    if set(names) != REQUIRED_MODULES:
        raise ValueError("scenario_module_manifest_required_set_mismatch")
    return tuple(parsed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    for item in scenario_modules(args.manifest, args.root):
        print("\t".join(item[field] for field in ("module", "source", "runtime", "sha256")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

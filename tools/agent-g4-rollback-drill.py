#!/usr/bin/env python3
"""Run the disposable coordinated Plane Agent G4 rollback drill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from validate_agent_g4_live import validate_rollback_fixture


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools" / "agent-g4-manifest.json"
FIXTURE_PATH = ROOT / "apps" / "api" / "plane" / "tests" / "fixtures" / "agent_g4_rollback_pins.json"
MODULE_PATH = ROOT / "apps" / "api" / "plane" / "operation_gateway" / "rollback_drill.py"
SPEC = importlib.util.spec_from_file_location("agent_g4_rollback_drill", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"event=agent.g4.rollback.drill status=failed module={MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


if __name__ == "__main__":
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_rollback_fixture(FIXTURE_PATH, ROOT, manifest)
    result = MODULE.run_rollback_drill()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if result["passes"] else 1)

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).parents[1]
ROOT = TOOLS.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


operations = _load("verify_agent_g4_operations", TOOLS / "verify-agent-g4-operations.py")


class OperationsPackageTests(unittest.TestCase):
    def test_manifest_binds_every_check_to_existing_owner_test(self):
        manifest = json.loads((TOOLS / "agent-g4-operations-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["checks"]), set(manifest["testIds"]))
        self.assertTrue(all(operations._test_exists(selector) for selectors in manifest["testIds"].values() for selector in selectors))

    def test_receipt_is_provider_free_and_keeps_missing_retained_o02_explicit(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            root = Path(directory)
            events = root / "events"
            events.write_text("event=agent.g4.g4-runtime-contracts status=passed\n", encoding="utf-8")
            receipt = operations.build_receipt(stage_events=events, evidence_dir=root)
        self.assertEqual(receipt["providerAttempts"], 0)
        self.assertFalse(receipt["liveOrProviderStarted"])
        self.assertFalse(receipt["retainedO02"]["applicable"])
        self.assertIsNone(receipt["zeroProductEffectsOnDenial"])
        self.assertTrue(all(row["status"] == "missing" for row in receipt["checks"]))
        self.assertTrue(receipt["checks"][-1]["pending"])

    def test_receipt_requires_stage_evidence_for_tools_owner_test(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            root = Path(directory)
            events = root / "events"
            events.write_text("event=agent.g4.g4-runtime-contracts status=passed\n", encoding="utf-8")
            receipt = operations.build_receipt(stage_events=events, evidence_dir=root)
        coverage = receipt["checks"][2]["coverage"]
        tools_coverage = next(item for item in coverage if item["testId"].startswith("tools/"))
        self.assertEqual(tools_coverage["status"], "pass")
        self.assertEqual(tools_coverage["reason"], "canonical_stage_passed")


if __name__ == "__main__":
    unittest.main()

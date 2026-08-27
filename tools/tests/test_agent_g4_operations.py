# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


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


def _stage_results() -> list[str]:
    stages = {
        "external.mcp.pin",
        "external.sdk.pin",
        "g3-prerequisite",
        "g4-runtime-contracts",
        "g4-cross-process",
        "g4-runtime-service",
        "g4-runtime-red-team",
        "g4-gateway-workload",
        "g4-rollback",
        "g4-operator-readback",
        "g4-production-configuration",
    }
    return [f"event=agent.g4.{stage} status=passed" for stage in sorted(stages)]


def _receipt(manifest: dict[str, object], candidate: str) -> dict[str, object]:
    pins = manifest["pins"]
    candidate_binding = manifest["candidateBinding"]
    return {
        "schemaVersion": "plane-agent-g4/verifier-receipt/v1",
        "status": "passed",
        "mode": "offline",
        "binding": {
            "candidateCommit": candidate,
            "expectedCandidate": candidate,
            "sourceCommit": pins["apiArtifact"]["sourceRevision"],
            "acceptedG3Baseline": candidate_binding["acceptedG3Baseline"],
            "hermesCommit": pins["hermesCommit"],
            "mcpGitlink": pins["mcpGitlink"],
            "sdkGitlink": pins["sdkGitlink"],
            "runtimeImageTag": pins["runtimeImageTag"],
            "runtimeImageDigest": pins["runtimeImageDigest"],
            "runtimeImageRevision": pins["runtimeImageRevision"],
            "runtimeContract": pins["runtimeContract"],
            "apiArtifact": copy.deepcopy(pins["apiArtifact"]),
        },
        "actionCounters": {
            "provider_requests": 0,
            "live_requests": 0,
            "G5_actions": 0,
            "credential_mutations": 0,
        },
        "stageResults": _stage_results(),
        "cleanup": {
            "verifierExitCode": 0,
            "cleanupExitCode": 0,
            "taskResourcesRemovedOrChecked": True,
            "rawLogsRetained": False,
        },
    }


def _receipt_fixture(root: Path) -> tuple[Path, Path, Path]:
    manifest = json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))
    candidate, parent = operations._git_binding()
    manifest["candidateBinding"]["parentCommit"] = parent
    binding_manifest_path = root / "manifest.json"
    receipt_path = root / "g4-receipt.json"
    binding_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt_path.write_text(json.dumps(_receipt(manifest, candidate)), encoding="utf-8")
    return TOOLS / "agent-g4-operations-v1.json", receipt_path, binding_manifest_path


class OperationsPackageTests(unittest.TestCase):
    def test_manifest_binds_every_check_to_existing_owner_test(self):
        manifest = json.loads((TOOLS / "agent-g4-operations-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["checks"]), set(manifest["testIds"]))
        self.assertTrue(all(operations._test_exists(selector) for selectors in manifest["testIds"].values() for selector in selectors))

    def test_receipt_consumer_accepts_passed_offline_receipt_without_g3_log(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            manifest_path, receipt_path, binding_manifest_path = _receipt_fixture(Path(directory))
            with patch.object(operations, "BINDING_MANIFEST", binding_manifest_path), patch.object(operations, "_worktree_is_clean", return_value=True):
                receipt = operations.build_receipt(manifest_path, verifier_receipt_path=receipt_path)
        self.assertEqual(receipt["providerAttempts"], 0)
        self.assertFalse(receipt["liveOrProviderStarted"])
        self.assertTrue(receipt["retainedO02"]["applicable"])
        self.assertEqual(receipt["finalVerifierReceipt"]["candidateDigest"], operations._git_binding()[0])
        self.assertTrue(all(row["status"] == "pass" for row in receipt["checks"]))
        self.assertTrue(next(row for row in receipt["checks"] if row["pending"])["pending"])

    def test_receipt_consumer_rejects_nonpassed_provider_or_candidate_mismatched_receipt(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            manifest_path, receipt_path, binding_manifest_path = _receipt_fixture(Path(directory))
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            for mutation in (
                lambda item: item.update(status="failed"),
                lambda item: item["actionCounters"].update(provider_requests=1),
                lambda item: item["binding"].update(candidateCommit="0" * 40),
            ):
                candidate = copy.deepcopy(value)
                mutation(candidate)
                receipt_path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaises(operations.ReceiptInputError):
                    with patch.object(operations, "BINDING_MANIFEST", binding_manifest_path), patch.object(operations, "_worktree_is_clean", return_value=True):
                        operations.build_receipt(manifest_path, verifier_receipt_path=receipt_path)

    def test_deferred_check_prefers_canonical_stage_evidence(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            manifest_path, receipt_path, binding_manifest_path = _receipt_fixture(Path(directory))
            with patch.object(operations, "BINDING_MANIFEST", binding_manifest_path), patch.object(operations, "_worktree_is_clean", return_value=True):
                receipt = operations.build_receipt(manifest_path, verifier_receipt_path=receipt_path)
            row = next(item for item in receipt["checks"] if item["id"] == "operations.load-health-quota-safety-stop-audit-rollback")
            self.assertEqual(row["status"], "pass")
            self.assertTrue(row["pending"])
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            value["stageResults"].append("event=agent.g4.g4-rollback status=failed")
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with patch.object(operations, "BINDING_MANIFEST", binding_manifest_path), patch.object(operations, "_worktree_is_clean", return_value=True):
                receipt = operations.build_receipt(manifest_path, verifier_receipt_path=receipt_path)
            row = next(item for item in receipt["checks"] if item["id"] == "operations.load-health-quota-safety-stop-audit-rollback")
            self.assertEqual(row["status"], "fail")

    def test_output_excludes_raw_stage_lines_and_sensitive_fields(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            manifest_path, receipt_path, binding_manifest_path = _receipt_fixture(Path(directory))
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            value["stageResults"][0] += " root=/private/tmp/secret api_key=provider-secret"
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with patch.object(operations, "BINDING_MANIFEST", binding_manifest_path), patch.object(operations, "_worktree_is_clean", return_value=True):
                receipt = operations.build_receipt(manifest_path, verifier_receipt_path=receipt_path)
            output = json.dumps(receipt)
            self.assertNotIn("/private/tmp/secret", output)
            self.assertNotIn("provider-secret", output)
            self.assertNotIn("stageResults", output)


if __name__ == "__main__":
    unittest.main()

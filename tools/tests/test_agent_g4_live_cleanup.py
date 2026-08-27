# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = _load("validate_agent_g4_live", TOOLS / "validate_agent_g4_live.py")
cleanup = _load("attest_agent_g4_live_cleanup", TOOLS / "attest_agent_g4_live_cleanup.py")


class LiveCleanupTests(unittest.TestCase):
    def test_code_mode_product_only_outcome_is_valid_actual_evidence(self):
        projection = {
            "id": "worker",
            "descriptorDigest": "0" * 64,
            "schemaVersion": "plane.agent-scenario/v1",
            "actorRole": "worker",
            "profileName": "Worker",
            "expected": {
                "operationOutcomes": [],
                "evidenceKinds": [],
                "durableRecords": [],
                "productEvents": [],
            },
            "setup": {"preconditions": [], "actors": []},
            "controls": {"fault": {"selection": "none"}},
            "actual": {
                "operations": [],
                "records": [{"kind": "outcome_submission", "count": 1}],
                "productEvents": [{"kind": "outcome_submission", "count": 1}],
                "evidenceKinds": ["outcome_submission"],
            },
        }
        validator._validate_scenario_projection(projection)
        validator._validate_scenario_gate(
            {
                "passed": True,
                "failures": [],
                "operations": [],
                "durableRecords": [
                    {"kind": "outcome_submission", "expectedCount": 1, "actualCount": 1, "passed": True}
                ],
                "productEvents": [],
                "evidenceKinds": [{"kind": "outcome_submission", "passed": True}],
            }
        )

    def test_scenario_vocabulary_still_rejects_unknown_actual_kind(self):
        projection = {
            "id": "worker",
            "descriptorDigest": "0" * 64,
            "schemaVersion": "plane.agent-scenario/v1",
            "actorRole": "worker",
            "profileName": "Worker",
            "expected": {"operationOutcomes": [], "evidenceKinds": []},
            "setup": {"preconditions": [], "actors": []},
            "controls": {"fault": {"selection": "none"}},
            "actual": {
                "operations": [],
                "records": [],
                "productEvents": [],
                "evidenceKinds": ["not-a-kind"],
            },
        }
        with self.assertRaisesRegex(validator.ContractError, "evidence_scenario_actual_evidence_invalid"):
            validator._validate_scenario_projection(projection)

    def test_attestation_binds_two_receipt_hashes_and_rejects_extra_artifact(self):
        candidate = "f" * 40
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            for path in (manifest,):
                path.chmod(0o600)
            receipts = []
            for role in ("worker", "delegator"):
                run_dir = root / role
                run_dir.mkdir(mode=0o700)
                files = {}
                for name, value in (
                    ("authority.json", "{}"),
                    ("config.json", "{}"),
                    ("descriptor.json", "{}"),
                    ("result.json", '{"status":"passed"}\n'),
                ):
                    path = run_dir / name
                    path.write_text(value, encoding="utf-8")
                    path.chmod(0o600)
                    files[name] = path
                receipts.append(
                    cleanup.ReceiptInput(
                        role,
                        files["authority.json"],
                        files["config.json"],
                        files["result.json"],
                    )
                )
            with patch.object(cleanup, "validate_files", return_value={"collected": 1, "passed": 1}):
                attestation = cleanup.build_attestation(
                    manifest=manifest,
                    candidate=candidate,
                    expected_candidate=candidate,
                    command="provider-free-check",
                    receipts=receipts,
                    cleanup={
                        "containersRemaining": 0,
                        "networksRemaining": 0,
                        "volumesRemaining": 0,
                        "leasePresent": False,
                        "staleLabeledVolumesRemoved": 7,
                    },
                )
            self.assertEqual(attestation["schemaVersion"], cleanup.SCHEMA)
            self.assertEqual(attestation["candidateCommit"], candidate)
            self.assertEqual(
                [row["role"] for row in attestation["receipts"]],
                ["delegator", "worker"],
            )
            for row, receipt in zip(attestation["receipts"], sorted(receipts, key=lambda item: item.role)):
                self.assertEqual(row["sha256"], hashlib.sha256(receipt.evidence.read_bytes()).hexdigest())
            self.assertFalse(attestation["cleanup"]["rawFieldsEmitted"])
            run_dir = root / "worker"
            (run_dir / "stderr.log").write_text("redacted", encoding="utf-8")
            (run_dir / "stderr.log").chmod(stat.S_IRUSR | stat.S_IWUSR)
            with self.assertRaisesRegex(cleanup.AttestationError, "run_directory_artifacts_invalid"):
                with patch.object(cleanup, "validate_files", return_value={"collected": 1, "passed": 1}):
                    cleanup.build_attestation(
                        manifest=manifest,
                        candidate=candidate,
                        expected_candidate=candidate,
                        command="provider-free-check",
                        receipts=receipts,
                        cleanup={
                            "containersRemaining": 0,
                            "networksRemaining": 0,
                            "volumesRemaining": 0,
                            "leasePresent": False,
                            "staleLabeledVolumesRemoved": 7,
                        },
                    )


if __name__ == "__main__":
    unittest.main()

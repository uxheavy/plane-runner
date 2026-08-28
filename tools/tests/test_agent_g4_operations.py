# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


TOOLS = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_agent_g4_operations", TOOLS / "verify-agent-g4-operations.py"
)
assert SPEC is not None and SPEC.loader is not None
operations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operations)
ROLLBACK_SPEC = importlib.util.spec_from_file_location(
    "agent_g4_rollback_drill", TOOLS / "agent-g4-rollback-drill.py"
)
assert ROLLBACK_SPEC is not None and ROLLBACK_SPEC.loader is not None
rollback = importlib.util.module_from_spec(ROLLBACK_SPEC)
ROLLBACK_SPEC.loader.exec_module(rollback)


def _binding() -> dict[str, object]:
    return json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))


def _receipt() -> dict[str, object]:
    binding = _binding()
    stages = [*binding["stages"], "external.mcp.pin", "external.sdk.pin"]
    return {
        "schemaVersion": "plane-agent-g4/provider-free-verifier-receipt/v1",
        "status": "passed",
        "mode": "provider-free",
        "runtimeSourceCandidate": binding["sourceBinding"]["runtimeSourceCandidate"],
        "verifierRevision": _verifier_revision(),
        "pins": binding["pins"],
        "stageResults": [{"stage": stage, "status": "passed"} for stage in stages],
        "cleanup": {
            "verifierExitCode": 0,
            "cleanupExitCode": 0,
            "taskResourcesRemovedOrChecked": True,
        },
        "providerAttempts": 0,
    }


def _write_receipt(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _verifier_revision() -> str:
    return subprocess.check_output(
        ["git", "-C", str(TOOLS.parent), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def test_canonical_receipt_proves_operations_external_client_and_denial(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    _write_receipt(path, _receipt())

    result = operations.validate_evidence(path, verifier_revision=_verifier_revision())

    assert result["providerAttempts"] == 0
    assert all(row["status"] == "pass" for row in result["checks"])
    assert result["externalClientProof"]["passed"] is True
    assert result["zeroProductEffectsOnDenial"]["proved"] is True
    assert result["runtimeSourceCandidate"] == _binding()["sourceBinding"]["runtimeSourceCandidate"]
    assert result["verifierRevision"] == _verifier_revision()
    assert result["finalVerifierEvidence"]["verifierRevision"] == _verifier_revision()


@pytest.mark.parametrize("mutation,error", [
    (lambda value: value.update(providerAttempts=1), "not_passed_provider_free"),
    (lambda value: value.update(runtimeSourceCandidate="0" * 40), "runtime_source_binding_mismatch"),
    (lambda value: value.update(verifierRevision="0" * 40), "verifier_revision_mismatch"),
    (
        lambda value: value.update(
            stageResults=[
                row for row in value["stageResults"] if row["stage"] != "g4-rollback"
            ]
        ),
        "canonical_stage_evidence_missing",
    ),
])
def test_receipt_rejects_missing_provider_free_proof(
    tmp_path: Path,
    mutation,
    error: str,
) -> None:
    value = copy.deepcopy(_receipt())
    mutation(value)
    path = tmp_path / "receipt.json"
    _write_receipt(path, value)

    with pytest.raises(operations.OperationsEvidenceError, match=error):
        operations.validate_evidence(path, verifier_revision=_verifier_revision())


def test_receipt_rejects_verifier_revision_equal_to_runtime_source(tmp_path: Path) -> None:
    value = _receipt()
    runtime_source = value["runtimeSourceCandidate"]
    value["verifierRevision"] = runtime_source
    path = tmp_path / "receipt.json"
    _write_receipt(path, value)

    with pytest.raises(operations.OperationsEvidenceError, match="identity_not_distinct"):
        operations.validate_evidence(path, verifier_revision=runtime_source)


def test_rollback_binding_rejects_manifest_fixture_drift(tmp_path: Path) -> None:
    rollback.validate_bindings()
    fixture = json.loads(rollback.FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["current"]["planeCommit"] = "0" * 40
    path = tmp_path / "rollback.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(rollback.RollbackBindingError, match="current_plane_commit"):
        rollback.validate_bindings(fixture_path=path)


def test_rollback_binding_rejects_previous_api_contract_mutation(tmp_path: Path) -> None:
    fixture = json.loads(rollback.FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["previous"]["apiArtifact"]["contract"] = "broken.contract/v0"
    path = tmp_path / "rollback.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(rollback.RollbackBindingError, match="previous_api_artifact"):
        rollback.validate_bindings(fixture_path=path)

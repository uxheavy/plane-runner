#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Validate canonical provider-free G4 operations evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools" / "agent-g4-operations-v1.json"
BINDING_MANIFEST = ROOT / "tools" / "agent-g4-manifest.json"
_RECEIPT_SCHEMA = "plane-agent-g4/provider-free-verifier-receipt/v1"
_MAX_RECEIPT_BYTES = 128 * 1024
_GIT_SHA = re.compile(r"[0-9a-f]{40}")


class OperationsEvidenceError(ValueError):
    pass


def _repo_path(value: str) -> Path:
    return ROOT / value if value.startswith("tools/") else ROOT / "apps/api" / value.removeprefix("apps/api/")


def _test_exists(selector: str) -> bool:
    relative, separator, name = selector.partition("::")
    if not separator or not name.startswith("test_"):
        return False
    path = _repo_path(relative)
    if not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in ast.walk(tree)
    )


def _normalize(value: str) -> str:
    return value.removeprefix("apps/api/")


def _load_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperationsEvidenceError(reason) from exc
    if not isinstance(value, dict):
        raise OperationsEvidenceError(reason)
    return value


def _resolve_verifier_revision(explicit_revision: str | None) -> str:
    if explicit_revision is None:
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = [line for line in status.stdout.splitlines() if line[3:] != ".codex/config.toml"]
        if status.returncode != 0 or dirty:
            raise OperationsEvidenceError("verifier_checkout_not_clean")
        revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        value = revision.stdout.strip()
        if revision.returncode != 0 or not _GIT_SHA.fullmatch(value):
            raise OperationsEvidenceError("verifier_revision_unreadable")
        return value
    if not _GIT_SHA.fullmatch(explicit_revision):
        raise OperationsEvidenceError("verifier_revision_invalid")
    exists = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{explicit_revision}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    if exists.returncode != 0:
        raise OperationsEvidenceError("verifier_revision_unreadable")
    return explicit_revision


def _load_receipt(
    path: Path,
    binding: dict[str, Any],
    verifier_revision: str,
) -> tuple[dict[str, Any], dict[str, str], str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_RECEIPT_BYTES:
        raise OperationsEvidenceError("verifier_receipt_unreadable")
    raw = path.read_bytes()
    try:
        receipt = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OperationsEvidenceError("verifier_receipt_invalid") from exc
    if not isinstance(receipt, dict) or set(receipt) != {
        "schemaVersion", "status", "mode", "runtimeSourceCandidate", "verifierRevision", "pins",
        "stageResults", "cleanup", "providerExecutionInvoked",
    }:
        raise OperationsEvidenceError("verifier_receipt_invalid")
    if (
        receipt["schemaVersion"] != _RECEIPT_SCHEMA
        or receipt["status"] != "passed"
        or receipt["mode"] != "provider-free"
        or receipt["providerExecutionInvoked"] is not False
    ):
        raise OperationsEvidenceError("verifier_receipt_not_passed_provider_free")
    source = binding["sourceBinding"]
    if (
        receipt["runtimeSourceCandidate"] != source["runtimeSourceCandidate"]
        or receipt["pins"] != binding["pins"]
    ):
        raise OperationsEvidenceError("runtime_source_binding_mismatch")
    if receipt["verifierRevision"] != verifier_revision:
        raise OperationsEvidenceError("verifier_revision_mismatch")
    if receipt["verifierRevision"] == receipt["runtimeSourceCandidate"]:
        raise OperationsEvidenceError("verifier_runtime_identity_not_distinct")
    if (
        source["runtimeSourceCandidate"] != binding["pins"]["apiArtifact"]["sourceRevision"]
        or source["runtimeSourceCandidate"] != binding["pins"]["runtimeImageRevision"]
    ):
        raise OperationsEvidenceError("manifest_runtime_source_binding_mismatch")
    cleanup = receipt["cleanup"]
    if cleanup != {
        "verifierExitCode": 0,
        "cleanupExitCode": 0,
        "taskResourcesRemovedOrChecked": True,
    }:
        raise OperationsEvidenceError("verifier_cleanup_invalid")

    statuses: dict[str, str] = {}
    if not isinstance(receipt["stageResults"], list):
        raise OperationsEvidenceError("stage_results_invalid")
    for row in receipt["stageResults"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"stage", "status"}
            or not isinstance(row["stage"], str)
            or not isinstance(row["status"], str)
            or not re.fullmatch(r"[a-z0-9.-]+", row["stage"])
            or not re.fullmatch(r"[a-z_]+", row["status"])
        ):
            raise OperationsEvidenceError("stage_results_invalid")
        previous = statuses.setdefault(row["stage"], row["status"])
        if previous != row["status"]:
            raise OperationsEvidenceError("stage_results_conflict")
    required = set(binding["stages"])
    if any(statuses.get(stage) != "passed" for stage in required):
        raise OperationsEvidenceError("canonical_stage_evidence_missing")
    return receipt, statuses, hashlib.sha256(raw).hexdigest()


def _gitlink_matches(candidate: str, path: str, expected: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", candidate, path],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = result.stdout.strip().split() if result.returncode == 0 else []
    return len(parts) >= 4 and parts[2] == expected and parts[3] == path


def _external_client_proof(binding: dict[str, Any], statuses: dict[str, str]) -> dict[str, Any]:
    relative = "apps/api/plane/tests/contract/api/test_operation_gateway_external_clients.py"
    source = _repo_path(relative)
    g3 = ROOT / "tools" / "verify-agent-g3.sh"
    source_text = source.read_text(encoding="utf-8")
    g3_text = g3.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    tests = [
        f"{relative}::{node.name}"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]
    pins = binding["pins"]
    candidate = binding["sourceBinding"]["runtimeSourceCandidate"]
    checks = {
        "canonicalStagePassed": statuses.get("g3-prerequisite") == "passed",
        "mcpPinPassed": statuses.get("external.mcp.pin") == "passed",
        "sdkPinPassed": statuses.get("external.sdk.pin") == "passed",
        "testFileSelected": relative.removeprefix("apps/api/") in g3_text,
        "manifestBound": 'MANIFEST_ENV = "PLANE_G4_MANIFEST"' in source_text,
        "mcpGitlinkBound": _gitlink_matches(candidate, "external/plane-mcp-server", pins["mcpGitlink"]),
        "sdkGitlinkBound": _gitlink_matches(candidate, "external/plane-python-sdk", pins["sdkGitlink"]),
        "testsPresent": bool(tests),
    }
    return {"passed": all(checks.values()), "checks": checks, "testIds": tests}


def validate_evidence(
    verifier_receipt_path: Path,
    manifest_path: Path = MANIFEST,
    binding_manifest_path: Path = BINDING_MANIFEST,
    verifier_revision: str | None = None,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path, "operations_manifest_invalid")
    binding = _load_json(binding_manifest_path, "binding_manifest_invalid")
    expected_verifier_revision = _resolve_verifier_revision(verifier_revision)
    receipt, statuses, receipt_sha256 = _load_receipt(
        verifier_receipt_path,
        binding,
        expected_verifier_revision,
    )
    if (
        manifest.get("schemaVersion") != "plane.agent-operations-package/v1"
        or manifest.get("providerExecutionInvoked") is not False
        or set(manifest.get("checks", [])) != set(manifest.get("testIds", {}))
    ):
        raise OperationsEvidenceError("operations_manifest_invalid")

    stage_by_path: dict[str, str] = {}
    execution = manifest.get("execution", {})
    if execution.get("verifier") != "tools/verify-agent-g4.sh":
        raise OperationsEvidenceError("operations_manifest_invalid")
    for group in ("nondisruptive", "disruptive"):
        for row in execution.get(group, []):
            for owner in row.get("testIds", []):
                stage_by_path[_normalize(owner)] = row["stage"]

    rows = []
    for check_id in manifest["checks"]:
        coverage = []
        for selector in manifest["testIds"][check_id]:
            if not _test_exists(selector):
                raise OperationsEvidenceError(f"owner_test_missing:{selector}")
            stage = stage_by_path.get(_normalize(selector.split("::", 1)[0]))
            if stage is None:
                raise OperationsEvidenceError(f"owner_stage_missing:{selector}")
            coverage.append({"testId": selector, "stage": stage, "status": statuses.get(stage)})
        status = "pass" if coverage and all(item["status"] == "passed" for item in coverage) else "fail"
        rows.append({"id": check_id, "status": status, "coverage": coverage})
    if any(row["status"] != "pass" for row in rows):
        raise OperationsEvidenceError("operations_stage_evidence_incomplete")

    external = _external_client_proof(binding, statuses)
    if not external["passed"]:
        raise OperationsEvidenceError("external_client_proof_incomplete")
    denial = next(row for row in rows if row["id"] == "authorization.canary.denied")
    return {
        "schemaVersion": "plane-agent-operations-evidence/v1",
        "packageId": manifest["packageId"],
        "runtimeSourceCandidate": receipt["runtimeSourceCandidate"],
        "verifierRevision": receipt["verifierRevision"],
        "providerExecutionInvoked": False,
        "checks": rows,
        "externalClientProof": external,
        "zeroProductEffectsOnDenial": {
            "proved": denial["status"] == "pass",
            "stage": "g3-prerequisite",
            "testIds": [item["testId"] for item in denial["coverage"]],
        },
        "finalVerifierEvidence": {
            "schemaVersion": receipt["schemaVersion"],
            "status": receipt["status"],
            "runtimeSourceCandidate": receipt["runtimeSourceCandidate"],
            "verifierRevision": receipt["verifierRevision"],
            "sha256": receipt_sha256,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--binding-manifest", type=Path, default=BINDING_MANIFEST)
    parser.add_argument("--verifier-receipt", type=Path, required=True)
    parser.add_argument("--verifier-revision")
    args = parser.parse_args(argv)
    try:
        result = validate_evidence(
            args.verifier_receipt.resolve(),
            args.manifest.resolve(),
            args.binding_manifest.resolve(),
            args.verifier_revision,
        )
    except (KeyError, TypeError, OperationsEvidenceError) as exc:
        print(f"operations evidence rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

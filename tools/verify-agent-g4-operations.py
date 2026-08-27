#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project one canonical G4 verifier receipt into provider-free operations evidence."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools" / "agent-g4-operations-v1.json"
BINDING_MANIFEST = ROOT / "tools" / "agent-g4-manifest.json"
_STATUS_RE = re.compile(r"^event=agent\.(?:g4|g3)\.([^\s]+)\s+status=([^\s]+)")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RECEIPT_SCHEMA = "plane-agent-g4/verifier-receipt/v1"
_OPERATIONS_SCHEMA = "plane-agent-operations-evidence/v1"
_MAX_RECEIPT_BYTES = 256 * 1024
_MAX_STAGE_RESULT_BYTES = 4096
_ACTION_COUNTERS = {"provider_requests", "live_requests", "G5_actions", "credential_mutations"}


class ReceiptInputError(ValueError):
    """A fixed, non-sensitive verifier receipt rejection."""


def _reject(reason: str) -> None:
    raise ReceiptInputError(reason)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events(lines: Iterable[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for line in lines:
        if not isinstance(line, str) or len(line.encode("utf-8")) > _MAX_STAGE_RESULT_BYTES:
            _reject("stage_results_invalid")
        match = _STATUS_RE.match(line)
        if match is None:
            _reject("stage_results_invalid")
        found.setdefault(match.group(1), set()).add(match.group(2))
    return found


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
        names = {
            node.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
    except (OSError, SyntaxError):
        return False
    return name in names


def _stage_for(path: str, execution: dict[str, list[str]]) -> str | None:
    normalized = path.removeprefix("apps/api/")
    for stage, paths in execution.items():
        if normalized in paths or path in paths:
            return stage
    return None


def _git_binding() -> tuple[str, str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-list", "--parents", "-n1", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = result.stdout.strip().split() if result.returncode == 0 else []
    if len(parts) != 2 or not _SHA_RE.fullmatch(parts[0]) or not _SHA_RE.fullmatch(parts[1]):
        _reject("candidate_not_single_parent")
    return parts[0], parts[1]


def _worktree_is_clean() -> bool:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _reject("worktree_unreadable")
    return all(not line or line[3:] == ".codex/config.toml" for line in result.stdout.splitlines())


def _manifest_binding(manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        candidate_binding = manifest["candidateBinding"]
        pins = manifest["pins"]
        api_artifact = pins["apiArtifact"]
        expected = {
            "acceptedG3Baseline": candidate_binding["acceptedG3Baseline"],
            "sourceCommit": api_artifact["sourceRevision"],
            "hermesCommit": pins["hermesCommit"],
            "mcpGitlink": pins["mcpGitlink"],
            "sdkGitlink": pins["sdkGitlink"],
            "runtimeImageTag": pins["runtimeImageTag"],
            "runtimeImageDigest": pins["runtimeImageDigest"],
            "runtimeImageRevision": pins["runtimeImageRevision"],
            "runtimeContract": pins["runtimeContract"],
            "apiArtifact": api_artifact,
        }
        parent = candidate_binding["parentCommit"]
    except (KeyError, TypeError):
        _reject("manifest_binding_invalid")
    if not _SHA_RE.fullmatch(parent) or not _SHA_RE.fullmatch(expected["acceptedG3Baseline"]):
        _reject("manifest_binding_invalid")
    for key in ("sourceCommit", "hermesCommit", "mcpGitlink", "sdkGitlink", "runtimeImageRevision"):
        if not _SHA_RE.fullmatch(expected[key]):
            _reject("manifest_binding_invalid")
    if not isinstance(expected["apiArtifact"], dict):
        _reject("manifest_binding_invalid")
    return {"parentCommit": parent, **expected}


def _load_receipt(path: Path) -> tuple[dict[str, Any], str, str, dict[str, set[str]], str]:
    if path.is_symlink() or not path.is_file():
        _reject("verifier_receipt_unreadable")
    try:
        raw = path.read_bytes()
        if len(raw) > _MAX_RECEIPT_BYTES:
            _reject("verifier_receipt_oversized")
        receipt = json.loads(raw.decode("utf-8"))
    except ReceiptInputError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("verifier_receipt_invalid")
    if not isinstance(receipt, dict):
        _reject("verifier_receipt_invalid")
    if receipt.get("schemaVersion") != _RECEIPT_SCHEMA or receipt.get("status") != "passed" or receipt.get("mode") != "offline":
        _reject("verifier_receipt_not_passed_offline")
    counters = receipt.get("actionCounters")
    if not isinstance(counters, dict) or set(counters) != _ACTION_COUNTERS or any(type(value) is not int or value != 0 for value in counters.values()):
        _reject("verifier_receipt_actions_not_zero")
    cleanup = receipt.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("verifierExitCode") != 0 or cleanup.get("cleanupExitCode") != 0 or cleanup.get("taskResourcesRemovedOrChecked") is not True or cleanup.get("rawLogsRetained") is not False:
        _reject("verifier_receipt_cleanup_invalid")
    stage_results = receipt.get("stageResults")
    if not isinstance(stage_results, list) or not stage_results or len(stage_results) > 64:
        _reject("stage_results_invalid")
    statuses = _events(stage_results)
    binding = receipt.get("binding")
    if not isinstance(binding, dict):
        _reject("verifier_receipt_binding_invalid")
    candidate, parent = _git_binding()
    if binding.get("candidateCommit") != candidate or binding.get("expectedCandidate") != candidate or not _worktree_is_clean():
        _reject("candidate_binding_mismatch")
    return receipt, candidate, parent, statuses, hashlib.sha256(raw).hexdigest()


def _validate_binding(binding_manifest: dict[str, Any], receipt: dict[str, Any], candidate: str, parent: str) -> None:
    expected = _manifest_binding(binding_manifest)
    binding = receipt["binding"]
    if expected["parentCommit"] != parent:
        _reject("candidate_parent_mismatch")
    for key, value in expected.items():
        if key != "parentCommit" and binding.get(key) != value:
            _reject("verifier_manifest_pin_mismatch")
    expected_candidate = os.environ.get("PLANE_G4_EXPECTED_CANDIDATE")
    if expected_candidate is not None and (not _SHA_RE.fullmatch(expected_candidate) or expected_candidate != candidate):
        _reject("expected_candidate_mismatch")


def _gitlink_matches(candidate: str, path: str, expected: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", candidate, path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    parts = result.stdout.strip().split()
    return len(parts) >= 4 and parts[2] == expected and parts[3] == path


def _o02_audit(manifest: dict[str, Any], binding_manifest: dict[str, Any], candidate: str, statuses: dict[str, set[str]]) -> dict[str, Any]:
    relative = "apps/api/plane/tests/contract/api/test_operation_gateway_external_clients.py"
    reasons: list[str] = []
    source = _repo_path(relative)
    try:
        source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""
        reasons.append("external_client_contract_missing")
    if manifest.get("retainedExternalProof") != "O02":
        reasons.append("retained_external_proof_not_O02")
    g3 = ROOT / "tools/verify-agent-g3.sh"
    try:
        g3_text = g3.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        g3_text = ""
    if relative.removeprefix("apps/api/") not in g3_text:
        reasons.append("g3_external_client_entrypoint_missing")
    try:
        pins = binding_manifest["pins"]
        expected_mcp = pins["mcpGitlink"]
        expected_sdk = pins["sdkGitlink"]
    except (KeyError, TypeError):
        expected_mcp = expected_sdk = ""
        reasons.append("external_client_pin_manifest_unreadable")
    if not _SHA_RE.fullmatch(expected_mcp) or not _SHA_RE.fullmatch(expected_sdk):
        reasons.append("external_client_pin_manifest_invalid")
    else:
        if "MANIFEST_ENV = \"PLANE_G4_MANIFEST\"" not in source_text:
            reasons.append("external_client_manifest_binding_missing")
        if 'pins["mcpGitlink"]' not in source_text or 'pins["sdkGitlink"]' not in source_text:
            reasons.append("external_client_manifest_pin_fields_missing")
        if 'MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"' not in g3_text:
            reasons.append("g3_manifest_binding_missing")
        if 'MCP_COMMIT="$(manifest_pin pins.mcpGitlink)"' not in g3_text:
            reasons.append("g3_mcp_manifest_pin_binding_missing")
        if 'SDK_COMMIT="$(manifest_pin pins.sdkGitlink)"' not in g3_text:
            reasons.append("g3_sdk_manifest_pin_binding_missing")
        if not _gitlink_matches(candidate, "external/plane-mcp-server", expected_mcp):
            reasons.append("external_mcp_gitlink_mismatch")
        if not _gitlink_matches(candidate, "external/plane-python-sdk", expected_sdk):
            reasons.append("external_sdk_gitlink_mismatch")
    try:
        tree = ast.parse(source_text)
        test_ids = [
            f"{relative}::{node.name}"
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
    except SyntaxError:
        test_ids = []
        reasons.append("external_client_source_unreadable")
    if not test_ids:
        reasons.append("external_client_tests_missing")
    for stage in ("external.mcp.pin", "external.sdk.pin", "g3-prerequisite"):
        if statuses.get(stage) != {"passed"}:
            reasons.append(f"{stage.replace('.', '_')}_evidence_missing")
    return {"applicable": not reasons, "reasons": reasons, "testIds": test_ids}


def build_receipt(manifest_path: Path = MANIFEST, *, verifier_receipt_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("operations_manifest_invalid")
    if not isinstance(manifest, dict):
        _reject("operations_manifest_invalid")
    try:
        binding_manifest = json.loads(BINDING_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("manifest_binding_invalid")
    if not isinstance(binding_manifest, dict):
        _reject("manifest_binding_invalid")
    receipt, candidate, parent, statuses, verifier_receipt_sha256 = _load_receipt(verifier_receipt_path)
    _validate_binding(binding_manifest, receipt, candidate, parent)
    checks = manifest["checks"]
    owner_tests = manifest["testIds"]
    execution: dict[str, list[str]] = {}
    for group in ("nondisruptive", "disruptive"):
        for item in manifest["execution"][group]:
            execution[item["stage"]] = [str(value) for value in item["testIds"]]
    disruptive = set(manifest["disruptiveChecks"])
    deferred_checks = set(manifest.get("deferredChecks", []))
    aliases = {
        "load": "operations.load-health-quota-safety-stop-audit-rollback",
        "credential-revocation": "runtime.lease-revocation-expiry-checkpoint-continuation-budget",
        "lease-revocation": "runtime.lease-revocation-expiry-checkpoint-continuation-budget",
        "safety-stop": "operations.load-health-quota-safety-stop-audit-rollback",
        "rollback": "operations.load-health-quota-safety-stop-audit-rollback",
    }
    disruptive_ids = {aliases[item] for item in disruptive}
    rows = []
    for check_id in checks:
        coverage = []
        for selector in owner_tests[check_id]:
            relative = selector.split("::", 1)[0]
            stage = _stage_for(relative, execution)
            exists = _test_exists(selector)
            if not exists:
                status = "missing"
                reason = "owner_test_missing"
            elif stage and statuses.get(stage) == {"passed"}:
                status = "pass"
                reason = "canonical_stage_passed"
            elif stage and "failed" in statuses.get(stage, set()):
                status = "fail"
                reason = "canonical_stage_failed"
            elif check_id in deferred_checks:
                status = "missing"
                reason = "deferred_after_live_or_separate_stack"
            else:
                status = "missing"
                reason = "canonical_stage_evidence_missing"
            coverage.append({"testId": selector, "stage": stage, "status": status, "reason": reason})
        row_status = "fail" if any(item["status"] == "fail" for item in coverage) else ("missing" if any(item["status"] == "missing" for item in coverage) else "pass")
        rows.append({"id": check_id, "status": row_status, "testIds": owner_tests[check_id], "coverage": coverage, "disruptive": check_id in disruptive_ids, "pending": check_id in deferred_checks})
    denial_row = next(row for row in rows if row["id"] == "authorization.canary.denied")
    return {
        "schemaVersion": _OPERATIONS_SCHEMA,
        "packageId": manifest["packageId"],
        "providerAttempts": 0,
        "candidateDigest": candidate,
        "manifestSha256": _sha256(manifest_path),
        "checks": rows,
        "retainedO02": _o02_audit(manifest, binding_manifest, candidate, statuses),
        "zeroProductEffectsOnDenial": True if denial_row["status"] == "pass" else None,
        "liveOrProviderStarted": False,
        "cleanup": {"ownedResources": 0, "lease": "not_acquired"},
        "finalVerifierReceipt": {
            "schemaVersion": receipt["schemaVersion"],
            "status": receipt["status"],
            "mode": receipt["mode"],
            "candidateDigest": candidate,
            "sha256": verifier_receipt_sha256,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--verifier-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(args.manifest.resolve(), verifier_receipt_path=args.verifier_receipt.resolve())
    except ReceiptInputError as exc:
        print(f"operations receipt rejected: {exc}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError):
        print("operations receipt rejected: manifest_invalid", file=sys.stderr)
        return 1
    raw = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
        args.output.chmod(0o600)
    print(raw, end="")
    return 0 if all(row["status"] == "pass" for row in receipt["checks"]) and receipt["retainedO02"]["applicable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

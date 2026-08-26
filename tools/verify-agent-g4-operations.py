#!/usr/bin/env python3
"""Run the declared provider-free operations package against stage evidence."""

from __future__ import annotations

import argparse
import ast
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
_STATUS_RE = re.compile(r"^event=agent\.(?:g4|g3)\.([^\s]+)\s+status=([^\s]+)")
_HEX_RE = re.compile(r"^[0-9a-f]{40,64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events(path: Path | None) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    if not path or not path.is_file():
        return found
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _STATUS_RE.match(line)
        if match:
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


def _o02_audit(manifest: dict[str, Any], candidate: str, evidence_dir: Path | None) -> dict[str, Any]:
    relative = "apps/api/plane/tests/contract/api/test_operation_gateway_external_clients.py"
    reasons: list[str] = []
    source = _repo_path(relative)
    source_text = ""
    if not source.is_file():
        reasons.append("external_client_contract_missing")
    else:
        source_text = source.read_text(encoding="utf-8")
    if manifest.get("retainedExternalProof") != "O02":
        reasons.append("retained_external_proof_not_O02")
    g3 = ROOT / "tools/verify-agent-g3.sh"
    g3_text = g3.read_text(encoding="utf-8") if g3.is_file() else ""
    if not g3_text or relative.removeprefix("apps/api/") not in g3_text:
        reasons.append("g3_external_client_entrypoint_missing")
    try:
        pins = json.loads((ROOT / "tools/agent-g4-manifest.json").read_text(encoding="utf-8"))["pins"]
        expected_mcp = pins["mcpGitlink"]
        expected_sdk = pins["sdkGitlink"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        reasons.append("external_client_pin_manifest_unreadable")
    else:
        if not _HEX_RE.fullmatch(expected_mcp) or not _HEX_RE.fullmatch(expected_sdk):
            reasons.append("external_client_pin_manifest_invalid")
        if 'MANIFEST_ENV = "PLANE_G4_MANIFEST"' not in source_text:
            reasons.append("external_client_manifest_binding_missing")
        if 'pins["mcpGitlink"]' not in source_text or 'pins["sdkGitlink"]' not in source_text:
            reasons.append("external_client_manifest_pin_fields_missing")
        if 'MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"' not in g3_text:
            reasons.append("g3_manifest_binding_missing")
        if 'MCP_COMMIT="$(manifest_pin pins.mcpGitlink)"' not in g3_text:
            reasons.append("g3_mcp_manifest_pin_binding_missing")
        if 'SDK_COMMIT="$(manifest_pin pins.sdkGitlink)"' not in g3_text:
            reasons.append("g3_sdk_manifest_pin_binding_missing")
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        test_ids = [f"{relative}::{node.name}" for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    except (OSError, SyntaxError):
        test_ids = []
        reasons.append("external_client_source_unreadable")
    if not test_ids:
        reasons.append("external_client_tests_missing")
    if not _HEX_RE.fullmatch(candidate):
        reasons.append("candidate_digest_invalid")
    log = evidence_dir / "g3-prerequisite.log" if evidence_dir else None
    if not log or not log.is_file():
        reasons.append("retained_g3_evidence_missing")
    else:
        text = log.read_text(encoding="utf-8", errors="replace")
        links = {
            path: subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", candidate, path], text=True).split()[2]
            for path in ("external/plane-mcp-server", "external/plane-python-sdk")
        }
        match = re.search(
            r"event=agent\.g3\.g3-api-and-client-suite status=passed .*?external_mcp=([0-9a-f]{40}) external_sdk=([0-9a-f]{40})",
            text,
        )
        complete = re.search(rf"event=agent\.g3\.complete status=passed .*?candidate={re.escape(candidate)}(?:\s|$)", text)
        if not match or match.groups() != (links["external/plane-mcp-server"], links["external/plane-python-sdk"]):
            reasons.append("retained_g3_external_gitlink_evidence_mismatch")
        if not complete:
            reasons.append("retained_g3_candidate_evidence_mismatch")
    return {"applicable": not reasons, "reasons": reasons, "testIds": test_ids}


def build_receipt(manifest_path: Path = MANIFEST, *, stage_events: Path | None = None, evidence_dir: Path | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = manifest["checks"]
    owner_tests = manifest["testIds"]
    execution: dict[str, list[str]] = {}
    for group in ("nondisruptive", "disruptive"):
        for item in manifest["execution"][group]:
            execution[item["stage"]] = [str(value) for value in item["testIds"]]
    statuses = _events(stage_events)
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
            elif check_id in deferred_checks:
                status = "missing"
                reason = "deferred_after_live_or_separate_stack"
            elif stage and statuses.get(stage) == {"passed"}:
                status = "pass"
                reason = "canonical_stage_passed"
            elif stage and "failed" in statuses.get(stage, set()):
                status = "fail"
                reason = "canonical_stage_failed"
            else:
                status = "missing"
                reason = "canonical_stage_evidence_missing"
            coverage.append({"testId": selector, "stage": stage, "status": status, "reason": reason})
        row_status = "fail" if any(item["status"] == "fail" for item in coverage) else ("missing" if any(item["status"] == "missing" for item in coverage) else "pass")
        rows.append({"id": check_id, "status": row_status, "testIds": owner_tests[check_id], "coverage": coverage, "disruptive": check_id in disruptive_ids, "pending": check_id in deferred_checks})
    candidate = os.environ.get("PLANE_G4_EXPECTED_CANDIDATE") or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    denial_row = next(row for row in rows if row["id"] == "authorization.canary.denied")
    return {
        "schemaVersion": "plane-agent-operations-evidence/v1",
        "packageId": manifest["packageId"],
        "providerAttempts": 0,
        "candidateDigest": candidate,
        "manifestSha256": _sha256(manifest_path),
        "checks": rows,
        "retainedO02": _o02_audit(manifest, candidate, evidence_dir),
        "zeroProductEffectsOnDenial": True if denial_row["status"] == "pass" else None,
        "liveOrProviderStarted": False,
        "cleanup": {"ownedResources": 0, "lease": "not_acquired"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--stage-events", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    receipt = build_receipt(args.manifest.resolve(), stage_events=args.stage_events.resolve() if args.stage_events else None, evidence_dir=args.evidence_dir.resolve() if args.evidence_dir else None)
    raw = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
        args.output.chmod(0o600)
    print(raw, end="")
    return 0 if all(row["status"] == "pass" for row in receipt["checks"]) and receipt["retainedO02"]["applicable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

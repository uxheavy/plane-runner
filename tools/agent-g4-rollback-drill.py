#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run the disposable coordinated Plane Agent G4 rollback drill."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools" / "agent-g4-manifest.json"
FIXTURE_PATH = ROOT / "apps" / "api" / "plane" / "tests" / "fixtures" / "agent_g4_rollback_pins.json"
MODULE_PATH = ROOT / "apps" / "api" / "plane" / "operation_gateway" / "rollback_drill.py"
SPEC = importlib.util.spec_from_file_location("agent_g4_rollback_drill", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"event=agent.g4.rollback.drill status=failed module={MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RollbackBindingError(ValueError):
    pass


def _exact(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise RollbackBindingError(f"rollback_{name}_mismatch")


def _git_text(commit: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RollbackBindingError("rollback_accepted_g3_evidence_missing")
    return result.stdout


def _assignment(source: str, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}="([^"]+)"$', source, re.MULTILINE)
    if match is None:
        raise RollbackBindingError(f"rollback_accepted_g3_{name}_missing")
    return match.group(1)


def validate_bindings(
    manifest_path: Path = MANIFEST_PATH,
    fixture_path: Path = FIXTURE_PATH,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    binding = manifest["sourceBinding"]
    pins = manifest["pins"]
    current = fixture["current"]
    previous = fixture["previous"]
    strategy = fixture["strategy"]

    candidate = binding["runtimeSourceCandidate"]
    baseline = binding["acceptedG3Baseline"]
    _exact(candidate, pins["apiArtifact"]["sourceRevision"], "candidate_api_source")
    _exact(candidate, pins["runtimeImageRevision"], "candidate_runtime_source")
    _exact(current["planeCommit"], candidate, "current_plane_commit")
    _exact(previous["planeCommit"], baseline, "previous_plane_commit")
    _exact(current["migrationLeaf"], "db.0146_runtime_reconciliation_audit_fields", "current_migration")
    _exact(previous["migrationLeaf"], current["migrationLeaf"], "previous_migration_leaf")
    _exact(
        previous["apiArtifact"],
        {
            "imageTag": "plane-g3-external-client-api-tests:prepared",
            "imageDigest": "sha256:7812ed213b9cfcbe50580ded7b5e78a30d317e37dd66c1082c5dff97a9e98031",
            "sourceRevision": "9a0e870fb313eb85d93b89778076087a8897d2a2",
            "contract": "plane.operation/v1",
        },
        "previous_api_artifact",
    )
    _exact(current["apiArtifact"], pins["apiArtifact"], "current_api_artifact")
    _exact(
        current["runtime"],
        {
            "hermesCommit": pins["hermesCommit"],
            "mcpGitlink": pins["mcpGitlink"],
            "sdkGitlink": pins["sdkGitlink"],
            "imageTag": pins["runtimeImageTag"],
            "imageDigest": pins["runtimeImageDigest"],
            "runtimeRevision": pins["runtimeImageRevision"],
            "contract": pins["runtimeContract"],
        },
        "current_runtime",
    )

    services = ("api", "worker", "beat-worker", "supervisor", "agent-runtime")
    _exact(set(current["services"]), set(services), "current_services")
    _exact(set(previous["services"]), set(services), "previous_services")
    contracts = {
        service: "plane.agent-runtime/v1" if service in {"supervisor", "agent-runtime"} else "plane.operation/v1"
        for service in services
    }
    for service in services:
        artifact = pins["apiArtifact"] if service != "agent-runtime" else {
            "imageDigest": pins["runtimeImageDigest"],
            "sourceRevision": pins["runtimeImageRevision"],
        }
        expected_kind = "api" if service != "agent-runtime" else "runtime"
        _exact(
            current["services"][service],
            {
                "revision": artifact["sourceRevision"],
                "imageDigest": artifact["imageDigest"],
                "artifactKind": expected_kind,
                "artifactSourceRevision": artifact["sourceRevision"],
                "contract": contracts[service],
            },
            f"current_{service}",
        )

    accepted_source = _git_text(baseline, "tools/verify-agent-g3.sh")
    accepted_digest = _assignment(accepted_source, "API_TEST_IMAGE_DIGEST")
    for service in services:
        row = previous["services"][service]
        _exact(row["revision"], baseline, f"previous_{service}_revision")
        _exact(row["artifactKind"], "api", f"previous_{service}_artifact_kind")
        _exact(row["artifactSourceRevision"], baseline, f"previous_{service}_artifact_source")
        _exact(row["imageDigest"], accepted_digest, f"previous_{service}_digest")
        _exact(row["contract"], contracts[service], f"previous_{service}_contract")

    _exact(strategy["migration"], current["migrationLeaf"], "strategy_migration")
    _exact(strategy["previousMigration"], "db.0145_runtime_reconciliation", "strategy_previous_migration")
    _exact(strategy["compatibilityFloor"], strategy["previousMigration"], "strategy_floor")
    _exact(strategy["reverseMigrationAllowed"], False, "strategy_reverse")
    current_migration = ROOT / "apps/api/plane/db/migrations/0146_runtime_reconciliation_audit_fields.py"
    previous_migration = ROOT / "apps/api/plane/db/migrations/0145_runtime_reconciliation.py"
    _exact(
        hashlib.sha256(current_migration.read_bytes()).hexdigest(),
        strategy["currentMigrationSha256"],
        "current_migration_sha256",
    )
    for path, field in ((current_migration, "currentMigrationBlob"), (previous_migration, "previousMigrationBlob")):
        actual = subprocess.check_output(["git", "hash-object", str(path)], cwd=ROOT, text=True).strip()
        _exact(actual, strategy[field], field)


if __name__ == "__main__":
    validate_bindings()
    result = MODULE.run_rollback_drill()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if result["passes"] else 1)

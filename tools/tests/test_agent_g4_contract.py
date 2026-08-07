from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from validate_agent_g4_live import (  # noqa: E402
    ContractError,
    candidate_has_exact_parent,
    exact_binding,
    validate_files,
)
from summarize_agent_g4 import summarize  # noqa: E402


ROOT = TOOLS.parent
MANIFEST = json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))
CANDIDATE = "a" * 40
COMMAND = "python3 approved_live_probe.py --result-json"
BINDING_KEYS = (
    "candidateCommit",
    "g3Baseline",
    "hermesCommit",
    "mcpGitlink",
    "sdkGitlink",
    "runtimeImageTag",
    "runtimeImageDigest",
    "runtimeImageRevision",
    "runtimeContract",
)


def fixture() -> tuple[dict, dict, dict, str]:
    manifest = copy.deepcopy(MANIFEST)
    manifest["candidateBinding"]["parentCommit"] = "b" * 40
    manifest["pins"] = {
        "hermesCommit": "c" * 40,
        "mcpGitlink": "d" * 40,
        "sdkGitlink": "e" * 40,
        "runtimeImageTag": "plane-agent-runtime:hermes-e573a466",
        "runtimeImageDigest": "sha256:" + "f" * 64,
        "runtimeImageRevision": "1" * 40,
        "runtimeContract": "plane.agent-runtime/v1",
    }
    binding = exact_binding(manifest, CANDIDATE)
    import hashlib

    binding.update(
        {
            "commandSha256": hashlib.sha256(COMMAND.encode()).hexdigest(),
            "provider": {"name": "approved-provider", "model": "approved-model"},
            "thresholdProfile": "g4-live-approved-v1",
            "thresholds": {
                "permittedSuccessRateMin": 1.0,
                "deniedRejectionRateMin": 1.0,
                "maxLatencyP95Ms": 500,
                "maxErrorRate": 0.0,
            },
            "canaries": {
                "permitted": {"id": "canary-permitted", "expectedStatus": "allowed"},
                "denied": {"id": "canary-denied", "expectedStatus": "denied"},
            },
        }
    )
    authority = {
        "schemaVersion": "plane-agent-g4/live-authority/v1",
        "authorityId": "authority-test",
        "purpose": "g4-live-evaluation",
        "issuedAt": "2099-01-01T00:00:00Z",
        "expiresAt": "2099-01-02T00:00:00Z",
        "fallbackAllowed": False,
        "binding": binding,
    }
    config = {
        "schemaVersion": "plane-agent-g4/live-config/v1",
        "authorityId": "authority-test",
        "mode": "live",
        "offline": False,
        "fallbackAllowed": False,
        "binding": binding,
        "provider": {**binding["provider"], "fallbackUsed": False},
        "thresholdProfile": binding["thresholdProfile"],
        "thresholds": copy.deepcopy(binding["thresholds"]),
        "canaries": {key: row["id"] for key, row in binding["canaries"].items()},
        "requiredReadbacks": ["audit", "version"],
    }
    evidence = {
        "schemaVersion": "plane-agent-g4/live-evidence/v1",
        "status": "passed",
        "binding": {key: binding[key] for key in BINDING_KEYS},
        "provider": {**binding["provider"], "fallbackUsed": False},
        "canaries": {
            "permitted": {"id": "canary-permitted", "status": "allowed", "passed": True},
            "denied": {"id": "canary-denied", "status": "denied", "passed": True},
        },
        "thresholds": {
            "profile": binding["thresholdProfile"],
            "approved": binding["thresholds"],
            "observed": {
                "permittedSuccessRate": 1.0,
                "deniedRejectionRate": 1.0,
                "latencyP95Ms": 100,
                "errorRate": 0.0,
            },
        },
        "readback": {
            "audit": {"passed": True, "eventCount": 2},
            "version": {"passed": True, "binding": {key: binding[key] for key in BINDING_KEYS}},
        },
        "summary": {
            "counts": {"collected": 2, "passed": 2, "failed": 0, "skipped": 0, "xfail": 0, "deselected": 0},
            "durationMs": 100,
            "migrationLeaf": "0141",
            "workload": {"throughput": 10.0, "latencyP95Ms": 100.0, "errorRate": 0.0, "saturation": 0.2},
        },
    }
    return manifest, authority, config, json.dumps(evidence, sort_keys=True, separators=(",", ":"))


class G4ContractTests(unittest.TestCase):
    def write_case(self, manifest, authority, config, evidence):
        temp = tempfile.TemporaryDirectory()
        directory = Path(temp.name)
        paths = []
        for name, value in (("authority.json", authority), ("config.json", config), ("manifest.json", manifest)):
            path = directory / name
            path.write_text(json.dumps(value), encoding="utf-8")
            paths.append(path)
        evidence_path = directory / "evidence.json"
        evidence_path.write_text(evidence, encoding="utf-8")
        paths.append(evidence_path)
        return temp, paths

    def test_positive_evidence_is_candidate_and_pin_bound(self):
        manifest, authority, config, evidence = fixture()
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        result = validate_files(*paths, CANDIDATE, COMMAND)
        self.assertEqual(result["passed"], 2)

    def test_exact_parent_rejects_original_and_descendant_shapes(self):
        self.assertTrue(candidate_has_exact_parent(["b" * 40], "b" * 40))
        self.assertFalse(candidate_has_exact_parent([], "b" * 40))
        self.assertFalse(candidate_has_exact_parent(["b" * 40, "c" * 40], "b" * 40))
        self.assertFalse(candidate_has_exact_parent(["a" * 40], "b" * 40))

    def test_arbitrary_exit_zero_output_is_rejected(self):
        manifest, authority, config, _ = fixture()
        temp, paths = self.write_case(manifest, authority, config, "true")
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_must_be_one_json_object"):
            validate_files(*paths, CANDIDATE, COMMAND)

    def test_malformed_and_mismatched_evidence_are_rejected(self):
        manifest, authority, config, evidence_text = fixture()
        for evidence, reason in (("{", "evidence_must_be_one_json_object"),):
            temp, paths = self.write_case(manifest, authority, config, evidence)
            self.addCleanup(temp.cleanup)
            with self.subTest(reason=reason), self.assertRaisesRegex(ContractError, reason):
                validate_files(*paths, CANDIDATE, COMMAND)
        evidence = json.loads(evidence_text)
        evidence["binding"]["mcpGitlink"] = "1" * 40
        temp, paths = self.write_case(manifest, authority, config, json.dumps(evidence))
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_binding_mismatch"):
            validate_files(*paths, CANDIDATE, COMMAND)

    def test_command_hash_and_config_pin_mismatches_are_rejected(self):
        manifest, authority, config, evidence = fixture()
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "authority_command_mismatch"):
            validate_files(*paths, CANDIDATE, COMMAND + " --tampered")
        config["thresholds"]["maxLatencyP95Ms"] = 501
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "config_thresholds_mismatch"):
            validate_files(*paths, CANDIDATE, COMMAND)

    def test_wrong_baseline_pin_is_rejected(self):
        manifest, authority, config, evidence = fixture()
        authority["binding"]["g3Baseline"] = "1" * 40
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "authority_g3Baseline_mismatch"):
            validate_files(*paths, CANDIDATE, COMMAND)

    def test_provider_model_fallback_and_threshold_failures_are_rejected(self):
        for mutation, reason in (
            (lambda evidence: evidence["provider"].update({"fallbackUsed": True}), "evidence_provider_mismatch"),
            (lambda evidence: evidence["canaries"]["denied"].update({"status": "allowed"}), "evidence_denied_canary_failed"),
            (lambda evidence: evidence["thresholds"]["observed"].update({"errorRate": 0.1}), "evidence_threshold_latency_or_error_failed"),
            (lambda evidence: evidence["readback"]["audit"].update({"passed": False}), "evidence_audit_or_version_readback_failed"),
        ):
            manifest, authority, config, evidence_text = fixture()
            evidence = json.loads(evidence_text)
            mutation(evidence)
            temp, paths = self.write_case(manifest, authority, config, json.dumps(evidence))
            self.addCleanup(temp.cleanup)
            with self.subTest(reason=reason), self.assertRaisesRegex(ContractError, reason):
                validate_files(*paths, CANDIDATE, COMMAND)

    def test_runtime_image_binding_and_sanitized_metric_summary_are_structural(self):
        manifest, authority, config, evidence_text = fixture()
        evidence = json.loads(evidence_text)
        evidence["binding"]["runtimeImageTag"] = "plane-agent-runtime:wrong"
        temp, paths = self.write_case(manifest, authority, config, json.dumps(evidence))
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_binding_mismatch"):
            validate_files(*paths, CANDIDATE, COMMAND)

        stage = summarize(
            "...."
            + json.dumps(
                {
                    "event": "agent.g4.gateway.load",
                    "requests": 128,
                    "workers": 8,
                    "agents": 16,
                    "elapsedMs": 10575,
                    "throughputPerSecond": 12.104,
                    "errorRate": 0.0,
                    "saturation": 0.46875,
                    "latencyMs": {"p95": 952.743, "p99": 1212.129},
                    "queueingMs": {"p95": 25.313},
                    "resources": {"maxDatabaseConnections": 8, "maxResidentSetMb": 185.098, "cpuSeconds": 22.885},
                    "sustainedDurationSeconds": 10.575,
                }
            )
            + "\n1 passed in 10.575s\n"
            + "api_key=super-secret\n"
        )
        self.assertEqual(stage["workload_requests"], "128")
        self.assertEqual(stage["workload_workers"], "8")
        self.assertEqual(stage["workload_agents"], "16")
        self.assertEqual(stage["workload_throughput"], "12.104")
        self.assertEqual(stage["workload_latency_p95_ms"], "952.743")
        self.assertEqual(stage["workload_latency_p99_ms"], "1212.129")
        self.assertEqual(stage["workload_queue_p95_ms"], "25.313")
        self.assertEqual(stage["workload_sustained_duration_s"], "10.575")
        self.assertEqual(stage["resource_db_connections"], "8")
        self.assertEqual(stage["resource_memory_mb"], "185.098")
        self.assertEqual(stage["resource_cpu_seconds"], "22.885")
        self.assertEqual(stage["collected"], "1")
        self.assertEqual(stage["passed"], "1")
        self.assertRegex(stage["evidence_sha256"], r"^[0-9a-f]{64}$")

    def test_dirty_exception_is_narrow_and_structural(self):
        script = (ROOT / "tools/verify-agent-g4.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count('[[ "${path}" == ".codex/config.toml" ]]'), 1)
        self.assertNotIn("path == \".env\"", script)
        self.assertNotIn("path == \".git\"", script)


if __name__ == "__main__":
    unittest.main()

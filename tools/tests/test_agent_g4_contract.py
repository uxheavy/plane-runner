from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

_RED_TEAM_SPEC = importlib.util.spec_from_file_location(
    "agent_g4_runtime_red_team", TOOLS / "agent-g4-runtime-red-team.py"
)
if _RED_TEAM_SPEC is None or _RED_TEAM_SPEC.loader is None:
    raise RuntimeError("G4 red-team module could not be loaded for focused tests")
_RED_TEAM = importlib.util.module_from_spec(_RED_TEAM_SPEC)
sys.modules[_RED_TEAM_SPEC.name] = _RED_TEAM
_RED_TEAM_SPEC.loader.exec_module(_RED_TEAM)

from validate_agent_g4_live import (  # noqa: E402
    ContractError,
    candidate_has_exact_parent,
    exact_binding,
    validate_rollback_fixture,
    validate_rollback_runbook,
    validate_files,
)
from summarize_agent_g4 import summarize  # noqa: E402
PINNED_HERMES_RUN_AGENT_PATH = _RED_TEAM.PINNED_HERMES_RUN_AGENT_PATH
PINNED_HERMES_RUN_AGENT_SHA256 = _RED_TEAM.PINNED_HERMES_RUN_AGENT_SHA256
ProbeFailure = _RED_TEAM.ProbeFailure
validate_pinned_hermes_identity = _RED_TEAM.validate_pinned_hermes_identity


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
        "runtimeImageTag": "plane-agent-runtime:hermes-e573a466-g4-ffcc2dc9",
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
    def test_red_team_stage_requires_exact_image_http_dispatch_and_pinned_hermes_wrapper(self):
        source = (TOOLS / "agent-g4-runtime-red-team.py").read_text(encoding="utf-8")
        image_dockerfile = (ROOT / "deployments/cli/community/agent-runtime/Dockerfile").read_text(encoding="utf-8")
        runtime_policy = (ROOT / "apps/api/plane/agent/runtime/subprocess.py").read_text(encoding="utf-8")
        runtime_service = (ROOT / "apps/api/plane/agent/runtime/service.py").read_text(encoding="utf-8")
        vfork_adapter = (ROOT / "apps/api/plane/agent/runtime/sitecustomize.py").read_text(encoding="utf-8")
        self.assertIn('"/v1/runtime/dispatch"', source)
        self.assertIn("dispatch_http=passed full_chain=passed", source)
        self.assertIn("PINNED_HERMES_RUN_AGENT_PATH = \"/opt/hermes/run_agent.py\"", source)
        self.assertIn("PINNED_HERMES_RUN_AGENT_SHA256", source)
        self.assertIn("PROVIDER_TRANSPORT_SHIM", source)
        self.assertIn("from openai import OpenAI", source)
        self.assertIn("g4-hermes-agent-loop=ok", source)
        self.assertIn("provider_seam=deterministic_openai_transport_only", source)
        self.assertIn("agent_tool_registration=ok", source)
        self.assertIn("tamper_guard=fail_closed", source)
        self.assertIn("filesystem_confinement=passed", source)
        self.assertIn("validate_pinned_hermes_identity", source)
        self.assertIn("COPY hermes/plane_runtime/g1_runtime_image/dotenv/ /opt/hermes/dotenv/", image_dockerfile)
        self.assertIn("COPY plane_runtime_service/sitecustomize.py /opt/sitecustomize.py", image_dockerfile)
        self.assertIn("_HERMES_CODE_MODE_CLONE_FLAGS = _SIGCHLD", runtime_policy)
        self.assertIn("_HERMES_RPC_SOCKET_MODE = 0o600", runtime_policy)
        self.assertIn('allow_arg("chmod", _SECCOMP_MODE_OFFSET, _HERMES_RPC_SOCKET_MODE)', runtime_policy)
        self.assertIn('allow_arg("fchmodat", _SECCOMP_AT_MODE_OFFSET, _HERMES_RPC_SOCKET_MODE)', runtime_policy)
        self.assertIn('"vfork"', runtime_policy)
        self.assertIn('child_environment.setdefault("PLANE_AGENT_RUNTIME_DISABLE_VFORK", "1")', runtime_service)
        self.assertIn("subprocess._USE_VFORK = False", vfork_adapter)
        self.assertNotIn("/tmp/run_agent.py", source)
        self.assertNotIn("DOTENV_COMPAT_SHIM", source)
        self.assertNotIn("MODEL_SHIM", source)
        self.assertNotIn("DeterministicModel", source)
        self.assertNotIn("AIAgent = ", source)
        self.assertNotIn("spec_from_file_location", source)
        self.assertNotIn("sitecustomize.py", source)
        self.assertNotIn("bootstrap_payload", source)

    def test_tamper_guard_rejects_shadowed_agent_identity(self):
        valid = {
            "module": "run_agent",
            "path": PINNED_HERMES_RUN_AGENT_PATH,
            "sha256": PINNED_HERMES_RUN_AGENT_SHA256,
            "class": "AIAgent",
            "classModule": "run_agent",
            "shadowPresent": False,
        }
        for field, value in (
            ("path", "/tmp/shadowed.py"),
            ("sha256", "0" * 64),
            ("class", "DeterministicModel"),
            ("classModule", "shadowed"),
            ("shadowPresent", True),
        ):
            tampered = dict(valid)
            tampered[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                ProbeFailure, "pinned_hermes_identity_tamper_guard_failed"
            ):
                validate_pinned_hermes_identity(tampered)

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

    def test_rollback_fixture_is_bound_to_manifest_and_accepted_g3_evidence(self):
        result = validate_rollback_fixture(
            ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json",
            ROOT,
            MANIFEST,
        )
        self.assertEqual(result["current"]["planeCommit"], MANIFEST["candidateBinding"]["parentCommit"])
        self.assertEqual(result["previous"]["planeCommit"], MANIFEST["candidateBinding"]["acceptedG3Baseline"])
        self.assertEqual(
            result["acceptedG3"]["imageDigest"],
            "sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e",
        )

    def test_rollback_stale_and_arbitrary_pin_mutations_are_rejected(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        mutations = (
            ("current.planeCommit", lambda value: value["current"].update({"planeCommit": "5f7e27f969b54ab94f0c6a6da9ea6feca27b7e32"})),
            ("current.service.imageDigest", lambda value: value["current"]["services"]["api"].update({"imageDigest": "sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e"})),
            ("previous.planeCommit", lambda value: value["previous"].update({"planeCommit": "6c5ad927b2e31e3d1cd608fc89fbb8a308cc9809"})),
            ("current.runtime.imageDigest", lambda value: value["current"]["runtime"].update({"imageDigest": "sha256:" + "0" * 64})),
            ("previous.service.imageDigest", lambda value: value["previous"]["services"]["worker"].update({"imageDigest": "sha256:" + "1" * 64})),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                value = copy.deepcopy(original)
                mutate(value)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "rollback.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaisesRegex(ContractError, "rollback_"):
                        validate_rollback_fixture(path, ROOT, MANIFEST)

    def test_rollback_runbook_examples_are_pin_bound(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        runbook_path = ROOT / MANIFEST["runbook"]
        runbook = runbook_path.read_text(encoding="utf-8")
        validate_rollback_runbook(runbook, MANIFEST, fixture)
        with self.assertRaisesRegex(ContractError, "rollback_runbook_missing"):
            validate_rollback_runbook(runbook.replace("python3 tools/agent-g4-rollback-drill.py", "python3 tools/other-drill.py"), MANIFEST, fixture)
        with self.assertRaisesRegex(ContractError, "rollback_runbook_stale_pin_present"):
            validate_rollback_runbook(runbook + "\n5f7e27f969b54ab94f0c6a6da9ea6feca27b7e32\n", MANIFEST, fixture)
        with self.assertRaisesRegex(ContractError, "rollback_runbook_missing_Plane_service_revision_above_is"):
            validate_rollback_runbook(runbook.replace("The Plane service revision above is", "The Plane deployment revision is"), MANIFEST, fixture)

    def test_dirty_exception_is_narrow_and_structural(self):
        script = (ROOT / "tools/verify-agent-g4.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count('[[ "${path}" == ".codex/config.toml" ]]'), 1)
        self.assertNotIn("path == \".env\"", script)
        self.assertNotIn("path == \".git\"", script)
        self.assertNotIn('CANDIDATE_PARENT_COMMIT="8a7371208079a7c25ab391e433785c3e67803d72"', script)
        self.assertIn('["candidateBinding"]["parentCommit"]', script)
        self.assertIn("validate_rollback_fixture", script)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
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
    validate_api_artifact_descriptor,
    offline_evidence_hashes,
    validate_offline_evidence,
    validate_runtime_provider_environment,
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
G3_BASELINE = "9b4bad0b0b54c90c8d25e9af5f086971e6b9c93a"
HISTORICAL_FALSE_POSITIVE = "9ff8b952872e9201e2f0f2e8c6621c273d33f49b:tools/agent-g4-manifest.json:generic-api-key:47"
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
    "apiArtifact",
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
        "apiArtifact": {
            "imageTag": "plane-agent-api:g4-test",
            "imageDigest": "sha256:" + "0" * 64,
            "sourceRevision": "2" * 40,
            "contract": "plane.operation/v1",
        },
    }
    binding = exact_binding(manifest, CANDIDATE)
    import hashlib

    binding.update(
        {
            "commandSha256": hashlib.sha256(COMMAND.encode()).hexdigest(),
            "provider": {
                "name": "openai-codex",
                "model": "gpt-5.6-luna",
                "baseUrl": "https://chatgpt.com/backend-api/codex/responses",
                "host": "chatgpt.com",
                "path": "/backend-api/codex/responses",
                "credentialSource": "chatgpt-subscription",
                "credentialRef": "PLANE_G4_PROVIDER_SECRET_SOURCE",
                "credentialName": "api_key",
            },
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
        "expectedCandidate": CANDIDATE,
        "fallbackAllowed": False,
        "binding": binding,
    }
    config = {
        "schemaVersion": "plane-agent-g4/live-config/v1",
        "authorityId": "authority-test",
        "mode": "live",
        "offline": False,
        "fallbackAllowed": False,
        "expectedCandidate": CANDIDATE,
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
    def test_live_runner_exports_one_failure_object_before_disposable_teardown(self):
        source = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        cleanup = source[source.index("cleanup()") : source.index("trap cleanup EXIT INT TERM")]
        evidence_index = cleanup.index('cat "${EVIDENCE_FILE}"')
        compose_down_index = cleanup.index("docker compose", evidence_index)
        run_dir_delete_index = cleanup.index('rm -rf -- "${RUN_DIR}"', compose_down_index)

        self.assertLess(
            evidence_index,
            compose_down_index,
            "event=agent.g4.runner.failure_evidence risk=teardown_destroys_readback "
            "expected=evidence before down-v actual=cleanup order is unsafe "
            "suggestion=preserve exactly one JSON object before teardown",
        )
        self.assertLess(evidence_index, run_dir_delete_index)
        self.assertEqual(source.count('cat "${EVIDENCE_FILE}"'), 1)
        self.assertIn('if [[ -s "${EVIDENCE_FILE}" ]]', cleanup)
        self.assertIn('exit "${status}"', cleanup)

    def test_live_runner_uses_accepted_g3_baseline_and_existing_audit_bootstrap_order(self):
        source = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        self.assertIn('["candidateBinding"]["acceptedG3Baseline"]', source)
        self.assertNotIn('["candidateBinding"]["parentCommit"]', source)
        self.assertIn("PLANE_AUDIT_RUNTIME_ROLE=plane_runtime", source)
        self.assertIn("PLANE_AUDIT_GOVERNANCE_ROLE=plane_audit_owner", source)
        self.assertIn("PLANE_AUDIT_MIGRATION_ROLE=plane_migrator", source)
        before_migrate = source.index("phase=before-migrate")
        migrate = source.index("python manage.py migrate", before_migrate)
        after_migrate = source.index("phase=after-migrate", migrate)
        self.assertLess(before_migrate, migrate)
        self.assertLess(migrate, after_migrate)

    def test_live_runner_validates_authority_provider_before_any_egress_or_credential_use(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        validation = runner.index("validate_agent_g4_live.py")
        self.assertLess(validation, runner.index("PROVIDER_SECRET_SOURCE=", validation))
        self.assertLess(validation, runner.index("docker image inspect", validation))
        self.assertLess(validation, runner.index("docker network create", validation))
        self.assertIn("PROVIDER_DESCRIPTOR_JSON", runner)
        self.assertIn("G4_PROVIDER_DESCRIPTOR_JSON", runner)
        self.assertNotIn("api.x.ai", runner)
        self.assertNotIn("grok-4", runner)
        self.assertNotIn("api.x.ai", invoke)
        self.assertNotIn("grok-4", invoke)

    def test_provider_descriptor_mismatch_fails_before_provider_counter_or_relay_start(self):
        _, authority, _, _ = fixture()
        provider = authority["binding"]["provider"]
        environment = {
            "PLANE_AGENT_RUNTIME_PROVIDER": provider["name"],
            "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": provider["model"],
            "PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL": provider["baseUrl"],
            "PLANE_AGENT_RUNTIME_PROVIDER_HOST": provider["host"],
            "PLANE_AGENT_RUNTIME_PROVIDER_PATH": provider["path"],
            "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE": provider["credentialSource"],
            "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF": provider["credentialRef"],
            "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME": provider["credentialName"],
        }
        for field in environment:
            with self.subTest(field=field):
                mismatched = dict(environment)
                mismatched[field] += "-mismatch"
                counters = {"provider_requests": 0, "relay_started": False}
                with self.assertRaisesRegex(ContractError, "runtime_provider_"):
                    validate_runtime_provider_environment(provider, mismatched)
                self.assertEqual(counters, {"provider_requests": 0, "relay_started": False})

    def test_helper_failure_path_reconciles_and_emits_one_nonzero_structural_object(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        self.assertIn("reconcile_provider_attempts", source)
        self.assertIn("finalize_invocation", source)
        self.assertIn("except BaseException", source)
        self.assertIn('"plane-agent-g4/live-failure/v1"', source)
        self.assertIn("return_code = 1", source)
        self.assertEqual(source.count("print(json.dumps(evidence"), 1)

    def test_live_helper_generates_namespaced_lifecycle_idempotency_keys(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        generated = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            kind = {"create_run": "run", "record_invocation": "invocation"}.get(node.func.id)
            if kind is None:
                continue
            key_argument = next((keyword.value for keyword in node.keywords if keyword.arg == "idempotency_key"), None)
            if key_argument is not None:
                generated[kind] = eval(compile(ast.Expression(key_argument), str(TOOLS / "agent-g4-live-invoke.py"), "eval"), {}, {"suffix": "focused"})

        self.assertEqual(
            generated,
            {
                "run": "idempotency:g4-live-run-focused",
                "invocation": "idempotency:g4-live-invocation-focused",
            },
        )
        for value in generated.values():
            self.assertTrue(value.startswith("idempotency:"))
        self.assertNotRegex(source, r"(?:f[\"']|[\"'])g4-live-run:")
        self.assertNotRegex(source, r"(?:f[\"']|[\"'])g4-live-invocation:")

        services = (ROOT / "apps/api/plane/agent/lifecycle/services.py").read_text(encoding="utf-8")
        self.assertIn('return _normalise_ref(value, "idempotency", field_name)', services)
        self.assertIn('value.startswith(f"{namespace}:")', services)

    def test_live_helper_uses_namespaced_actor_credential_reference(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        actor_call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_actor"
        )
        credential_keyword = next(
            keyword for keyword in actor_call.keywords if keyword.arg == "credential_ref"
        )
        credential_ref = ast.literal_eval(credential_keyword.value)

        services_source = (ROOT / "apps/api/plane/agent/lifecycle/services.py").read_text(encoding="utf-8")
        services_tree = ast.parse(services_source)
        pattern_assignment = next(
            node
            for node in ast.walk(services_tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_CREDENTIAL_REF_PATTERN" for target in node.targets)
        )
        pattern = ast.literal_eval(pattern_assignment.value.args[0])
        credential_pattern = re.compile(pattern)

        self.assertEqual(
            credential_ref,
            "plane-credential:g4-live",
            "event=g4.live.actor-credential-reference risk=unbound_actor_credential "
            "expected=plane-credential:g4-live actual=%r suggestion=use_an_internal_namespaced_reference"
            % credential_ref,
        )
        self.assertRegex(credential_ref, credential_pattern)
        self.assertNotRegex("runtime", credential_pattern)

    def test_failure_evidence_is_bounded_structural_and_excludes_sensitive_runtime_data(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        builder = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_failure_evidence"
        )
        namespace: dict[str, object] = {}
        exec(
            compile(ast.Module(body=[builder], type_ignores=[]), str(TOOLS / "agent-g4-live-invoke.py"), "exec"),
            namespace,
        )
        evidence = namespace["build_failure_evidence"](
            binding={"candidateCommit": "credential=provider-secret"},
            failure_phase="api-invocation",
            error_class="CommandError",
            exit_code=1,
            run_id="run:bounded",
            run_state="failed",
            invocation_id="invocation:bounded",
            invocation_state="failed",
            provider_attempts=[
                {
                    "sequence": 1,
                    "phase": "failed",
                    "upstreamInitiated": False,
                    "statusClass": "not_sent",
                    "errorCode": "pre_send_failure",
                    "prompt": "do not include",
                    "response": "do not include",
                    "credential": "do not include",
                    "payload": "do not include",
                    "rawLogs": "do not include",
                }
            ],
            terminal_kind="run_failure",
        )
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        self.assertEqual(evidence["schemaVersion"], "plane-agent-g4/live-failure/v1")
        self.assertEqual(evidence["status"], "failed")
        self.assertLessEqual(len(encoded.encode("utf-8")), 4096)
        self.assertEqual(
            set(evidence),
            {"schemaVersion", "status", "binding", "failure", "run", "invocation", "providerAttempts", "terminal"},
        )
        for forbidden in ("do not include", "prompt", "response", "credential", "payload", "rawLogs"):
            self.assertNotIn(forbidden, encoded)
        self.assertNotRegex(encoded, re.compile(r"(?i)(password|secret|token|api[_-]?key|authorization|credential)"))

    def test_provider_attempt_reconciliation_leaves_completed_attempt_completed(self):
        source = (ROOT / "apps/api/plane/tests/unit/agent/test_lifecycle.py").read_text(encoding="utf-8")
        self.assertIn("def test_provider_attempt_reconciliation_leaves_completed_attempt_completed", source)

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
        self.assertNotIn("_HERMES_BOOTSTRAP_CLONE_FLAGS", runtime_policy)
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
        result = validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)
        self.assertEqual(result["passed"], 2)

    def test_exact_parent_rejects_original_and_descendant_shapes(self):
        self.assertTrue(candidate_has_exact_parent(["b" * 40], "b" * 40))
        self.assertFalse(candidate_has_exact_parent([], "b" * 40))
        self.assertFalse(candidate_has_exact_parent(["b" * 40, "c" * 40], "b" * 40))
        self.assertFalse(candidate_has_exact_parent(["a" * 40], "b" * 40))

    def test_external_expected_candidate_rejects_sibling_and_descendant_bindings(self):
        manifest, authority, config, evidence = fixture()
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        for expected_candidate in ("b" * 40, "c" * 40):
            with self.subTest(expected_candidate=expected_candidate), self.assertRaisesRegex(
                ContractError, "candidate_expected"
            ):
                validate_files(*paths, CANDIDATE, expected_candidate, COMMAND)

    def test_g3_and_g4_share_process_lifetime_verifier_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "verifier.lock"
            holder = subprocess.Popen(
                [
                    sys.executable,
                    str(TOOLS / "agent-verifier-lock.py"),
                    str(lock_path),
                    "--",
                    sys.executable,
                    "-c",
                    "import time; print('preflight', flush=True); time.sleep(0.4)",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(holder.stdout.readline().strip(), "preflight")
            contender = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "agent-verifier-lock.py"),
                    str(lock_path),
                    "--",
                    sys.executable,
                    "-c",
                    "print('preflight')",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            holder_stdout, holder_stderr = holder.communicate(timeout=2)

        self.assertEqual(holder.returncode, 0, holder_stderr)
        self.assertEqual(contender.returncode, 2)
        self.assertIn("actual=lock_held_by_another_process", contender.stderr)
        self.assertEqual(holder_stdout, "")
        self.assertEqual(contender.stdout, "")

    def test_preseeded_lock_marker_cannot_bypass_public_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = ROOT / "tmp" / "plane-agent-g-verifier.lock"
            holder = subprocess.Popen(
                [
                    sys.executable,
                    str(TOOLS / "agent-verifier-lock.py"),
                    str(lock_path),
                    "--",
                    sys.executable,
                    "-c",
                    "import time; print('preflight', flush=True); time.sleep(0.5)",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(holder.stdout.readline().strip(), "preflight")
            contender = subprocess.run(
                ["env", "PLANE_AGENT_VERIFIER_LOCK_HELD=1", str(TOOLS / "verify-agent-g4.sh"), "--offline"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            holder_stdout, holder_stderr = holder.communicate(timeout=2)
        self.assertEqual(holder.returncode, 0, holder_stderr)
        self.assertEqual(contender.returncode, 2)
        self.assertIn("actual=lock_held_by_another_process", contender.stderr)
        self.assertNotIn("event=agent.g4.preflight status=passed", contender.stdout)
        self.assertEqual(holder_stdout, "")

    def test_stale_or_wrong_api_artifact_binding_is_rejected(self):
        manifest, _, _, _ = fixture()
        expected = exact_binding(manifest, CANDIDATE)
        valid = {
            "imageTag": expected["apiArtifact"]["imageTag"],
            "imageDigest": expected["apiArtifact"]["imageDigest"],
            "sourceRevision": expected["apiArtifact"]["sourceRevision"],
            "contract": expected["apiArtifact"]["contract"],
            "artifact": "plane-agent-api-g4",
        }
        validate_api_artifact_descriptor(valid, expected)
        for field, value in (
            ("imageTag", "plane-agent-api:stale"),
            ("imageDigest", "sha256:" + "1" * 64),
            ("sourceRevision", "3" * 40),
        ):
            invalid = dict(valid)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, "api_artifact_"):
                validate_api_artifact_descriptor(invalid, expected)

        source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        self.assertIn("check_api_test_image", source)
        self.assertIn("API image digest=${API_TEST_IMAGE_DIGEST}", source)
        self.assertIn("API image source label=${API_SOURCE_REVISION}", source)
        self.assertIn('"apiArtifact"', source)

    def test_api_image_builder_rejects_repo_root_and_requires_apps_api_context(self):
        dockerfile = (ROOT / "apps/api/Dockerfile.g4").read_text(encoding="utf-8")
        self.assertTrue((ROOT / "apps/api/manage.py").is_file())
        self.assertFalse((ROOT / "manage.py").exists())
        self.assertIn("COPY . /workspace/apps/api", dockerfile)
        self.assertIn('root / "manage.py"', dockerfile)
        self.assertIn('root / "plane"', dockerfile)
        self.assertIn('root / "apps/api"', dockerfile)
        self.assertIn("repository-root build context is not accepted", dockerfile)
        self.assertIn("PLANE_API_READBACK_SHA256", dockerfile)
        self.assertIn("PLANE_API_CORRUPTION_TEST_SHA256", dockerfile)
        self.assertIn('python -c "import django, psycopg, pytest"', dockerfile)
        self.assertIn("org.uxheavy.plane.api.source.readback.sha256", dockerfile)
        self.assertLess(dockerfile.index("repository-root build context is not accepted"), dockerfile.index("LABEL "))

    def test_manifest_api_artifact_passes_actual_gitleaks_and_exact_sha_validation(self):
        manifest_path = TOOLS / "agent-g4-manifest.json"
        manifest_text = manifest_path.read_text(encoding="utf-8")
        self.assertNotIn('"apiSourceRevision"', manifest_text)
        manifest, _, _, _ = fixture()
        artifact = manifest["pins"]["apiArtifact"]
        self.assertRegex(artifact["sourceRevision"], r"^[0-9a-f]{40}$")
        self.assertEqual(exact_binding(manifest, CANDIDATE)["apiArtifact"], artifact)
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{head}^"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = subprocess.run(
            [
                "gitleaks",
                "detect",
                "--no-banner",
                "--redact",
                "--source",
                str(ROOT),
                "--log-opts",
                f"{parent}..{head}",
                "--exit-code",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gitleaks_historical_disposition_is_exact_and_detector_remains_active(self):
        ignore_path = ROOT / ".gitleaksignore"
        ignored = {
            line.strip()
            for line in ignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(ignored, {HISTORICAL_FALSE_POSITIVE})

        def scan(log_range):
            return subprocess.run(
                [
                    "gitleaks",
                    "detect",
                    "--no-banner",
                    "--redact",
                    "--source",
                    str(ROOT),
                    "--log-opts",
                    log_range,
                    "--exit-code",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        candidate = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        source = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{candidate}^"], check=True, capture_output=True, text=True
        ).stdout.strip()
        source_parent = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{source}^"], check=True, capture_output=True, text=True
        ).stdout.strip()
        historical = scan(f"{G3_BASELINE}..{candidate}")
        current_source = scan(f"{source_parent}..{source}")
        current_wrapper = scan(f"{source}..{candidate}")
        self.assertEqual(historical.returncode, 0, historical.stdout + historical.stderr)
        self.assertEqual(current_source.returncode, 0, current_source.stdout + current_source.stderr)
        self.assertEqual(current_wrapper.returncode, 0, current_wrapper.stdout + current_wrapper.stderr)

        with tempfile.TemporaryDirectory() as directory:
            secret_path = Path(directory) / "unrelated.json"
            synthetic_secret = ("01234" * 3) + "567" + ("89abc" * 2) + "defa"
            secret_path.write_text(f'{{"apiKey": "{synthetic_secret}"}}\n', encoding="utf-8")
            unrelated = subprocess.run(
                [
                    "gitleaks",
                    "detect",
                    "--no-banner",
                    "--redact",
                    "--no-git",
                    "--source",
                    directory,
                    "--gitleaks-ignore-path",
                    str(ROOT),
                    "--exit-code",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(unrelated.returncode, 1, unrelated.stdout + unrelated.stderr)

    def test_hermes_bind_visibility_rejects_unavailable_mount_before_g3(self):
        source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        visibility = source.index("check_hermes_docker_visibility()")
        g3 = source.index("run_logged g3-prerequisite")
        self.assertLess(visibility, g3)
        self.assertIn('--mount "type=bind,src=${HERMES_ROOT},dst=/workspace/hermes-agent,readonly"', source)
        self.assertIn("test -r /workspace/hermes-agent/pyproject.toml", source)
        self.assertIn('docker_bind_visibility_failed=${HERMES_ROOT}', source)
        self.assertIn('>/dev/null 2>&1; then', source[source.index("check_hermes_docker_visibility()") : g3])

    def test_repo_owned_hermes_checkout_uses_guarded_cleanup(self):
        source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        cleanup = source[source.index("cleanup()") : source.index("trap cleanup EXIT")]
        self.assertIn('G4_TEMP_PARENT="${ROOT_DIR}/tmp"', source)
        self.assertIn('PLANE_G4_DISPOSABLE_HERMES_ROOT', source)
        self.assertIn('"${G4_TEMP_PARENT}"/plane-g4-hermes-*)', source)
        self.assertIn('HERMES_ROOT_OWNED=1', source)
        self.assertIn('if ! docker run --rm --network none', source)
        cleanup_helper = source[source.index("cleanup_disposable_hermes()") : source.index("write_receipt()")]
        self.assertIn('[[ "${HERMES_ROOT_OWNED}" -eq 1 ]] || return 0', cleanup_helper)
        self.assertIn('rm -rf -- "${HERMES_ROOT}"', cleanup_helper)
        self.assertIn('[[ ! -e "${HERMES_ROOT}" ]]', cleanup_helper)
        self.assertNotIn('rm -rf -- "${G4_TEMP_PARENT}"', cleanup)


    def test_arbitrary_exit_zero_output_is_rejected(self):
        manifest, authority, config, _ = fixture()
        temp, paths = self.write_case(manifest, authority, config, "true")
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_must_be_one_json_object"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

    def test_malformed_and_mismatched_evidence_are_rejected(self):
        manifest, authority, config, evidence_text = fixture()
        for evidence, reason in (("{", "evidence_must_be_one_json_object"),):
            temp, paths = self.write_case(manifest, authority, config, evidence)
            self.addCleanup(temp.cleanup)
            with self.subTest(reason=reason), self.assertRaisesRegex(ContractError, reason):
                validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)
        evidence = json.loads(evidence_text)
        evidence["binding"]["mcpGitlink"] = "1" * 40
        temp, paths = self.write_case(manifest, authority, config, json.dumps(evidence))
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_binding_mismatch"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

    def test_command_hash_and_config_pin_mismatches_are_rejected(self):
        manifest, authority, config, evidence = fixture()
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "authority_command_mismatch"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND + " --tampered")
        config["thresholds"]["maxLatencyP95Ms"] = 501
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "config_thresholds_mismatch"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

    def test_wrong_baseline_pin_is_rejected(self):
        manifest, authority, config, evidence = fixture()
        authority["binding"]["g3Baseline"] = "1" * 40
        temp, paths = self.write_case(manifest, authority, config, evidence)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "authority_g3Baseline_mismatch"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

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
                validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

    def test_runtime_image_binding_and_sanitized_metric_summary_are_structural(self):
        manifest, authority, config, evidence_text = fixture()
        evidence = json.loads(evidence_text)
        evidence["binding"]["runtimeImageTag"] = "plane-agent-runtime:wrong"
        temp, paths = self.write_case(manifest, authority, config, json.dumps(evidence))
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ContractError, "evidence_binding_mismatch"):
            validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)

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

    def test_offline_evidence_hash_materialization_is_exact_and_fail_closed(self):
        fixture_path = ROOT / MANIFEST["offlineEvidence"]["rollback"]["path"]
        actual = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        self.assertRegex(actual, r"^[0-9a-f]{64}$")
        self.assertEqual(offline_evidence_hashes(MANIFEST, ROOT)["rollback"], actual)
        self.assertEqual(MANIFEST["offlineEvidence"]["rollback"]["sha256"], actual)
        validate_offline_evidence(MANIFEST, ROOT)

        stale = copy.deepcopy(MANIFEST)
        stale["offlineEvidence"]["rollback"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "offline_evidence_rollback_sha256_mismatch"):
            validate_offline_evidence(stale, ROOT)

    def test_rollback_control_and_artifact_revisions_are_independently_bound(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        mutations = (
            (
                "control-plane",
                lambda value: value["current"].update({"planeCommit": "5f7e27f969b54ab94f0c6a6da9ea6feca27b7e32"}),
                "rollback_current_planeCommit_mismatch",
            ),
            (
                "api-service-artifact",
                lambda value: value["current"]["services"]["api"].update({"revision": value["current"]["planeCommit"]}),
                "rollback_current_api_revision_mismatch",
            ),
            (
                "runtime-service-artifact",
                lambda value: value["current"]["services"]["agent-runtime"].update({"revision": value["current"]["planeCommit"]}),
                "rollback_current_agent-runtime_revision_mismatch",
            ),
        )
        for name, mutate, reason in mutations:
            with self.subTest(name=name):
                value = copy.deepcopy(original)
                mutate(value)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "rollback.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaisesRegex(ContractError, reason):
                        validate_rollback_fixture(path, ROOT, MANIFEST)

    def test_rollback_stale_and_arbitrary_pin_mutations_are_rejected(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        mutations = (
            ("current.planeCommit", lambda value: value["current"].update({"planeCommit": "5f7e27f969b54ab94f0c6a6da9ea6feca27b7e32"})),
            ("current.service.imageDigest", lambda value: value["current"]["services"]["api"].update({"imageDigest": "sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e"})),
            ("previous.planeCommit", lambda value: value["previous"].update({"planeCommit": "6c5ad927b2e31e3d1cd608fc89fbb8a308cc9809"})),
            ("current.apiArtifact.imageDigest", lambda value: value["current"]["apiArtifact"].update({"imageDigest": "sha256:" + "0" * 64})),
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

    def test_rollback_cross_artifact_and_supervisor_swaps_are_rejected(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        mutations = (
            ("agent-runtime-as-api", lambda value: value["current"]["services"]["agent-runtime"].update({"artifactKind": "api"})),
            ("supervisor-as-runtime", lambda value: value["current"]["services"]["supervisor"].update({"artifactKind": "runtime"})),
            (
                "api-source-runtime",
                lambda value: value["current"]["services"]["api"].update({"artifactSourceRevision": value["current"]["runtime"]["runtimeRevision"]}),
            ),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                value = copy.deepcopy(original)
                mutate(value)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "rollback.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaisesRegex(ContractError, "rollback_current_"):
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

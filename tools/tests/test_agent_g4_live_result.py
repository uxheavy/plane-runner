from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
HELPER_PATH = TOOLS / "agent-g4-live-result.py"
RUNNER_PATH = TOOLS / "agent-g4-live.sh"
HELPER_SPEC = importlib.util.spec_from_file_location("agent_g4_live_result", HELPER_PATH)
if HELPER_SPEC is None or HELPER_SPEC.loader is None:
    raise RuntimeError("G4 live result helper could not be loaded")
HELPER = importlib.util.module_from_spec(HELPER_SPEC)
sys.modules[HELPER_SPEC.name] = HELPER
HELPER_SPEC.loader.exec_module(HELPER)


class LiveResultPersistenceTests(unittest.TestCase):
    def _evidence(self, directory: Path, *, schema: str = "plane-agent-g4/live-evidence/v1") -> Path:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / "evidence.json"
        path.write_text(
            json.dumps({"schemaVersion": schema, "status": "bounded"}, separators=(",", ":")),
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def _run_helper(self, destination: Path, evidence: Path, *extra: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                sys.executable,
                str(HELPER_PATH),
                "--destination",
                str(destination),
                "--evidence",
                str(evidence),
                *extra,
            ],
            check=False,
            capture_output=True,
        )

    def test_success_and_failure_stdout_are_one_json_receipt_and_diagnostics_are_stderr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root)
            success_destination = root / "success.result"
            success = self._run_helper(success_destination, evidence, "--status", "0")
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(success.stdout, success_destination.read_bytes())

            failure_evidence = self._evidence(root / "failure", schema="plane-agent-g4/live-failure/v1")
            failure_destination = root / "failure.result"
            failure = self._run_helper(
                failure_destination,
                failure_evidence,
                "--status",
                "1",
                "--phase",
                "api-invocation",
                "--error-class",
                "RuntimeError",
            )
            self.assertEqual(failure.returncode, 0, failure.stderr)
            self.assertEqual(failure.stdout, failure_destination.read_bytes())
            self.assertEqual(json.loads(failure.stdout), json.loads(failure_evidence.read_bytes()))
            self.assertIn(b"event=agent.g4.live-runner.failure ", failure.stderr)
            self.assertNotIn(b"event=agent.g4.live-runner.failure ", failure.stdout)

    def test_two_line_status_prefix_is_not_a_valid_result_receipt(self):
        with self.assertRaises(json.JSONDecodeError):
            json.loads(b"event=agent.g4.live-runner.failure phase=api-invocation\n{}")

    def test_pre_evidence_failure_still_publishes_one_json_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "pre-provider.result"
            result = self._run_helper(
                destination,
                root / "missing-evidence.json",
                "--status",
                "42",
                "--phase",
                "credential-bind-preflight",
                "--error-class",
                "RuntimeError",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "schemaVersion": "plane-agent-g4/live-runner-failure/v1",
                    "status": "failed",
                    "phase": "credential-bind-preflight",
                    "errorClass": "RuntimeError",
                    "exitCode": 42,
                    "reasonCategory": "unavailable",
                    "stderrSha256": HELPER.EMPTY_STDERR_SHA256,
                },
            )
            self.assertEqual(result.stdout, destination.read_bytes())

    def test_runner_failure_receipt_keeps_phase_exit_class_and_stderr_digest_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "capacity.result"
            digest = "a" * 64
            result = self._run_helper(
                destination,
                root / "missing-evidence.json",
                "--status",
                "75",
                "--phase",
                "capacity-lease",
                "--error-class",
                "unavailable",
                "--stderr-sha256",
                digest,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "schemaVersion": "plane-agent-g4/live-runner-failure/v1",
                    "status": "failed",
                    "phase": "capacity-lease",
                    "errorClass": "unavailable",
                    "exitCode": 75,
                    "reasonCategory": "unavailable",
                    "stderrSha256": digest,
                },
            )

    def test_module_failure_receipt_retains_only_a_valid_module_identifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "module.result"
            result = self._run_helper(
                destination,
                root / "missing-evidence.json",
                "--status",
                "1",
                "--error-class",
                "ModuleNotFoundError",
                "--missing-module",
                "plane_runtime.bridge_v2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["missingModule"], "plane_runtime.bridge_v2")

            refused = self._run_helper(
                root / "refused.result",
                root / "missing-evidence.json",
                "--status",
                "1",
                "--error-class",
                "ModuleNotFoundError",
                "--missing-module",
                "../../provider-secret",
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"reason=missing_module_invalid", refused.stderr)

    def test_runner_failure_receipt_retains_allowlisted_boundary_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "boundary.result"
            result = self._run_helper(
                destination,
                root / "missing-evidence.json",
                "--status",
                "1",
                "--error-class",
                "FileNotFoundError",
                "--missing-path-class",
                "scenario_module_artifact",
                "--child-phase",
                "scenario_import",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["missingPathClass"],
                "scenario_module_artifact",
            )
            self.assertEqual(json.loads(result.stdout)["childPhase"], "scenario_import")
            self.assertNotIn(b"/run/plane-scenario", result.stdout)

            refused = self._run_helper(
                root / "refused.result",
                root / "missing-evidence.json",
                "--status",
                "1",
                "--missing-path-class",
                "/private/secret",
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"reason=missing_path_class_invalid", refused.stderr)

            refused_phase = self._run_helper(
                root / "refused-phase.result",
                root / "missing-evidence.json",
                "--status",
                "1",
                "--child-phase",
                "/private/secret",
            )
            self.assertEqual(refused_phase.returncode, 2)
            self.assertIn(b"reason=child_phase_invalid", refused_phase.stderr)

            mismatched = self._run_helper(
                root / "mismatched.result",
                root / "missing-evidence.json",
                "--status",
                "1",
                "--missing-path-class",
                "secret_mount",
                "--child-phase",
                "runtime_start",
            )
            self.assertEqual(mismatched.returncode, 2)
            self.assertIn(b"reason=child_phase_mismatch", mismatched.stderr)

    def test_result_is_owner_only_and_survives_run_directory_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_directory = root / "run"
            run_directory.mkdir(mode=0o700)
            evidence = self._evidence(run_directory)
            destination = root / "caller.result"
            result = self._run_helper(destination, evidence, "--status", "0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            shutil.rmtree(run_directory)
            self.assertEqual(destination.read_bytes(), result.stdout)

    def test_runner_failure_receipt_preserves_bounded_setup_error_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "setup.result"
            setup_error = json.dumps(
                {
                    "id": "setup:lineage:IntegrityError",
                    "stage": "lineage",
                    "errorClass": "IntegrityError",
                    "counters": {
                        "actors": 5,
                        "profiles": 5,
                        "assignments": 1,
                        "lineageAssignments": 0,
                        "schedules": 0,
                        "scheduleFires": 0,
                    },
                },
                separators=(",", ":"),
            )
            result = self._run_helper(
                destination,
                root / "missing-evidence.json",
                "--status",
                "1",
                "--phase",
                "api-invocation",
                "--error-class",
                "RuntimeError",
                "--setup-error",
                setup_error,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["setupError"], json.loads(setup_error))

    def test_runner_rejects_unbounded_setup_error_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_helper(
                root / "setup.result",
                root / "missing-evidence.json",
                "--status",
                "1",
                "--phase",
                "api-invocation",
                "--error-class",
                "RuntimeError",
                "--setup-error",
                '{"id":"setup:lineage:/private/secret"}',
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"reason=setup_error_invalid", result.stderr)

    def test_atomic_publish_leaves_no_destination_or_partial_file_on_publish_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root)
            destination = root / "atomic.result"
            with self.assertRaisesRegex(HELPER.ResultPersistenceError, "result_publish_failed"):
                with mock.patch.object(HELPER.os, "link", side_effect=OSError("synthetic publish failure")):
                    HELPER.persist_result(destination, evidence, status=0)
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".atomic.result.tmp-*")), [])

    def test_collision_and_symlink_destinations_are_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root)
            collision = root / "collision.result"
            collision.write_bytes(b"caller-owned")
            collision_result = self._run_helper(collision, evidence, "--status", "0")
            self.assertEqual(collision_result.returncode, 2)
            self.assertIn(b"reason=result_path_collision", collision_result.stderr)
            self.assertEqual(collision.read_bytes(), b"caller-owned")

            target = root / "target.result"
            target.write_bytes(b"target")
            symlink = root / "symlink.result"
            symlink.symlink_to(target)
            symlink_result = self._run_helper(symlink, evidence, "--status", "0")
            self.assertEqual(symlink_result.returncode, 2)
            self.assertIn(b"reason=result_path_symlink", symlink_result.stderr)
            self.assertTrue(symlink.is_symlink())
            self.assertEqual(target.read_bytes(), b"target")

    def test_only_schema_controlled_evidence_is_consumed_and_raw_diagnostics_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root, schema="plane-agent-g4/live-failure/v1")
            raw_error = root / "sanitized-error.log"
            raw_error.write_text(
                "RuntimeError /private/secret/provider-source secret=must-not-leak",
                encoding="utf-8",
            )
            destination = root / "bounded.result"
            result = self._run_helper(
                destination,
                evidence,
                "--status",
                "125",
                "--phase",
                "api-invocation",
                "--error-class",
                "RuntimeError",
                "--reason-category",
                "docker_container_start_failed",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            persisted = destination.read_bytes()
            self.assertNotIn(raw_error.read_bytes(), persisted)
            self.assertNotIn(b"/private/secret/provider-source", persisted)
            self.assertNotIn(b"must-not-leak", persisted)
            self.assertIn(b"reason_category=docker_container_start_failed", result.stderr)
            self.assertNotIn(b"reason_category=docker_container_start_failed", persisted)

            refused_destination = root / "refused.result"
            refused = self._run_helper(
                refused_destination,
                evidence,
                "--status",
                "125",
                "--reason-category",
                "/private/secret/provider-source",
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"reason=docker_reason_category_invalid", refused.stderr)
            self.assertFalse(refused_destination.exists())
            self.assertNotIn(b"/private/secret/provider-source", refused.stderr)

    def test_compose_exit_one_preserves_allowlisted_docker_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root, schema="plane-agent-g4/live-failure/v1")
            destination = root / "compose.result"
            result = self._run_helper(
                destination,
                evidence,
                "--status",
                "1",
                "--phase",
                "compose",
                "--reason-category",
                "docker_precontainer_failure",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"reason_category=docker_precontainer_failure", result.stderr)
            self.assertNotIn(b"docker_precontainer_failure", destination.read_bytes())

    def test_pre_migrate_audit_bootstrap_exit_one_preserves_allowlisted_docker_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self._evidence(root, schema="plane-agent-g4/live-failure/v1")
            destination = root / "pre-migrate.result"
            result = self._run_helper(
                destination,
                evidence,
                "--status",
                "1",
                "--phase",
                "audit-bootstrap-pre-migrate",
                "--reason-category",
                "docker_precontainer_failure",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"reason_category=docker_precontainer_failure", result.stderr)
            self.assertNotIn(b"docker_precontainer_failure", destination.read_bytes())

    def test_runner_publishes_before_resource_cleanup_and_never_deletes_ack_file(self):
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        cleanup = runner[runner.index("cleanup()") : runner.index("trap cleanup EXIT INT TERM")]
        publish = cleanup.index("agent-g4-live-result.py")
        docker_cleanup = cleanup.index('docker rm -f "${RUNTIME}"')
        run_directory_cleanup = cleanup.index('rm -rf -- "${RUN_DIR}"')
        self.assertLess(publish, docker_cleanup)
        self.assertLess(docker_cleanup, run_directory_cleanup)
        self.assertIn('cat "${RESULT_FILE}"', cleanup)
        self.assertNotIn('rm -f -- "${RESULT_FILE}"', cleanup)
        self.assertNotIn('ERROR_FILE}', cleanup[publish:docker_cleanup])

    def test_runner_validates_fresh_non_symlink_result_path_and_uses_atomic_primitives(self):
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("PLANE_G4_LIVE_RESULT_PATH", runner)
        self.assertIn("validate_result_path", runner)
        self.assertIn("os.lstat(candidate)", runner)
        helper = HELPER_PATH.read_text(encoding="utf-8")
        self.assertIn("os.O_EXCL", helper)
        self.assertIn("os.O_NOFOLLOW", helper)
        self.assertIn("os.fsync(file_descriptor)", helper)
        self.assertIn("os.link(temporary, destination, follow_symlinks=False)", helper)
        self.assertIn("0o600", helper)


if __name__ == "__main__":
    raise SystemExit(unittest.main())

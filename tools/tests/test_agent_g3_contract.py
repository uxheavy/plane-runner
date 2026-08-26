from __future__ import annotations

import unittest
import subprocess
from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "verify-agent-g3.sh").read_text(encoding="utf-8")


class G3RuffVerifierContractTests(unittest.TestCase):
    def _run_ruff_harness(self, ruff_function: str) -> subprocess.CompletedProcess[str]:
        body = SOURCE.split('run_api sh -c "', 1)[1].split('\nemit "g3-api-and-client-suite"', 1)[0]
        body = body.rsplit('\n"', 1)[0].replace(r'\$', '$')
        body = body.split('\npython manage.py bootstrap_operation_gateway_audit', 1)[0]
        body += '\nrun_ruff_baseline_aware\n'
        body = f'{ruff_function}\npython() {{ python3 "$@"; }}\n{body}'
        return subprocess.run(["bash", "-c", body], capture_output=True, text=True, check=False)

    def test_baseline_only_diagnostics_are_explicitly_allowed(self) -> None:
        result = self._run_ruff_harness(
            r'''ruff() {
    case "$*" in
        *g3-ruff-baseline*) printf '[{"filename":"/workspace/g3-ruff-baseline/apps/api/plane/foo.py","code":"F401","message":"x"}]' ;;
        *) printf '[{"filename":"plane/foo.py","code":"F401","message":"x"}]' ;;
    esac
    return 1
}'''
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("status=baseline_allowed baseline=1 new=0", result.stdout)

    def test_new_diagnostics_fail_the_lint_disposition(self) -> None:
        result = self._run_ruff_harness(
            r'''ruff() {
    case "$*" in
        *g3-ruff-baseline*) printf '[{"filename":"/workspace/g3-ruff-baseline/apps/api/plane/foo.py","code":"F401","message":"x"}]' ;;
        *) printf '[{"filename":"plane/foo.py","code":"F401","message":"x"},{"filename":"plane/foo.py","code":"E501","message":"new"}]' ;;
    esac
    return 1
}'''
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("status=failed", result.stderr)
        self.assertIn("code=E501", result.stderr)

    def test_ruff_is_bounded_against_the_accepted_baseline(self) -> None:
        self.assertIn('git -C "${ROOT_DIR}" archive "${G3_BASE_COMMIT}"', SOURCE)
        self.assertIn('apps/api/plane/agent', SOURCE)
        self.assertIn('apps/api/plane/operation_gateway', SOURCE)
        self.assertIn('apps/api/plane/tests/unit/agent', SOURCE)
        self.assertIn('apps/api/plane/tests/contract/api', SOURCE)
        self.assertIn('status = \'baseline_allowed\' if baseline else \'passed\'', SOURCE)
        self.assertIn('new = candidate - baseline', SOURCE)
        self.assertNotIn('ruff check plane/agent plane/operation_gateway plane/tests/unit/agent plane/tests/contract/api', SOURCE)

    def test_lint_failure_does_not_skip_compile_or_pytest(self) -> None:
        lint = SOURCE.index("if run_ruff_baseline_aware")
        format_check = SOURCE.index("if ruff format --check")
        compileall = SOURCE.index("python -m compileall")
        pytest = SOURCE.index("pytest -p plane.tests.g3_no_skips")
        deferred_failure = SOURCE.index('if [ "\\${RUFF_STATUS}" -ne 0 ]')
        self.assertLess(lint, format_check)
        self.assertLess(format_check, compileall)
        self.assertLess(compileall, pytest)
        self.assertGreater(deferred_failure, pytest)

    def test_baseline_snapshot_is_owned_and_mounted_read_only(self) -> None:
        self.assertIn('CREATED_RUFF_BASELINE_DIR=0', SOURCE)
        self.assertIn('case "${RUFF_BASELINE_DIR}" in', SOURCE)
        self.assertIn('"${ROOT_DIR}"/tmp/plane-g3-ruff-baseline-*)', SOURCE)
        self.assertIn('rm -rf -- "${RUFF_BASELINE_DIR}"', SOURCE)
        self.assertIn(
            '--mount "type=bind,src=${RUFF_BASELINE_DIR},dst=/workspace/g3-ruff-baseline,readonly"',
            SOURCE,
        )

    def test_external_client_proof_uses_current_manifest_pins(self) -> None:
        client_source = (
            Path(__file__).parents[2]
            / "apps/api/plane/tests/contract/api/test_operation_gateway_external_clients.py"
        ).read_text(encoding="utf-8")
        self.assertIn('MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"', SOURCE)
        self.assertIn('MCP_COMMIT="$(manifest_pin pins.mcpGitlink)"', SOURCE)
        self.assertIn('SDK_COMMIT="$(manifest_pin pins.sdkGitlink)"', SOURCE)
        self.assertIn('PLANE_G4_MANIFEST=/workspace/agent-g4-manifest.json', SOURCE)
        self.assertIn('MANIFEST_ENV = "PLANE_G4_MANIFEST"', client_source)
        self.assertIn('pins["mcpGitlink"]', client_source)
        self.assertIn('pins["sdkGitlink"]', client_source)
        self.assertIn("assert tip == expected_tip", client_source)
        self.assertNotIn("c04974ed6624f17b41e63ef8182661929e77e0d3", SOURCE + client_source)
        self.assertNotIn("7d2faf3b7ef5409e292ba0a3c7015e59f93c5889", SOURCE + client_source)


if __name__ == "__main__":
    unittest.main()

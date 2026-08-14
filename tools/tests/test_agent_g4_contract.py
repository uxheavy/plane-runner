from __future__ import annotations

import ast
import copy
import hashlib
import io
import importlib.util
import json
import os
import re
import subprocess
import tarfile
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
    validate_disposable_artifact_binding,
    validate_rollback_fixture,
    validate_rollback_runbook,
    validate_files,
)
from summarize_agent_g4 import summarize  # noqa: E402

_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "build_agent_runtime_image", TOOLS / "build-agent-runtime-image.py"
)
if _BUILDER_SPEC is None or _BUILDER_SPEC.loader is None:
    raise RuntimeError("runtime image builder module could not be loaded")
_BUILDER = importlib.util.module_from_spec(_BUILDER_SPEC)
sys.modules[_BUILDER_SPEC.name] = _BUILDER
_BUILDER_SPEC.loader.exec_module(_BUILDER)

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


def fixture(candidate: str = CANDIDATE, source_manifest: dict | None = None) -> tuple[dict, dict, dict, str]:
    manifest = copy.deepcopy(MANIFEST if source_manifest is None else source_manifest)
    if source_manifest is None:
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
    binding = exact_binding(manifest, candidate)
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
        "expectedCandidate": candidate,
        "fallbackAllowed": False,
        "binding": binding,
    }
    config = {
        "schemaVersion": "plane-agent-g4/live-config/v1",
        "authorityId": "authority-test",
        "mode": "live",
        "offline": False,
        "fallbackAllowed": False,
        "expectedCandidate": candidate,
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
            "runtimeExit": {"present": True, "kind": "completed", "finalSequence": 0, "failure": None},
            "runtimeEventIngress": {"kindCounts": {"transcript_evidence_observed": 1}},
            "providerAttempts": [
                {
                    "sequence": 1,
                    "phase": "completed",
                    "upstreamInitiated": True,
                    "statusClass": "2xx",
                    "errorCode": "",
                }
            ],
            "planeOperationAudit": [
                {"operationId": operation_id, "status": "success", "errorCode": None, "count": 1}
                for operation_id in (
                    "search_workspace",
                    "work_item.read",
                    "catalog.search",
                    "catalog.describe",
                    "agent.outcome.evaluate",
                    "agent.outcome.submit",
                    "agent.outcome.publish",
                )
            ],
            "transcriptEvidence": {"count": 1, "eventIds": ["event:transcript"]},
            "explicitPublication": {
                "count": 1,
                "refs": [
                    {
                        "productRef": "outcome-submission:one",
                        "operationAttemptRef": "operation-attempt:one",
                        "operationRef": "operation:agent.outcome.publish",
                        "applicationServiceRef": "application-service:agent-lifecycle",
                        "gatewayReceiptRef": "gateway-receipt:one",
                        "receiptRef": "receipt:one",
                        "auditReceiptRef": "audit-receipt:one",
                        "productEventRef": "product-event:one",
                    }
                ],
            },
            "replay": {
                "status": "passed",
                "providerAccess": "disabled",
                "sameInvocation": True,
                "sameIdempotencyKey": True,
                "new": {
                    "children": 0,
                    "providerAttempts": 0,
                    "invocations": 0,
                    "receipts": 0,
                    "audits": 0,
                    "usage": 0,
                    "outcomes": 0,
                    "publications": 0,
                    "terminalEvents": 0,
                    "semanticSideEffects": 0,
                },
            },
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
    def _donor_manifest(self):
        return {
            "pins": {
                "runtimeImageTag": "plane-agent-runtime:sealed-donor",
                "runtimeImageDigest": "sha256:" + "a" * 64,
                "runtimeImageRevision": "b" * 40,
                "hermesCommit": _BUILDER.HERMES_COMMIT,
                "runtimeContract": "plane.agent-runtime/v1",
            }
        }

    def _donor_metadata(self, *, digest=None, labels=None):
        expected = self._donor_manifest()["pins"]
        return {
            "imageDigest": digest or expected["runtimeImageDigest"],
            "labels": labels
            or {
                "org.uxheavy.plane.hermes.commit": expected["hermesCommit"],
                "org.uxheavy.plane.hermes.remote": "https://github.com/uxheavy/hermes-agent.git",
                "org.uxheavy.plane.runtime.revision": expected["runtimeImageRevision"],
                "org.uxheavy.plane.runtime.contract": expected["runtimeContract"],
            },
        }

    def test_sealed_donor_digest_and_labels_are_attested_against_manifest(self):
        with mock.patch.object(_BUILDER, "image_metadata", return_value=self._donor_metadata()):
            binding = _BUILDER.verify_donor_image(
                "plane-agent-runtime:sealed-donor",
                self._donor_manifest(),
            )
        self.assertEqual(binding["sourceKind"], "sealed-image")
        self.assertEqual(binding["donorDigest"], "sha256:" + "a" * 64)

        with mock.patch.object(
            _BUILDER,
            "image_metadata",
            return_value=self._donor_metadata(digest="sha256:" + "d" * 64),
        ), self.assertRaisesRegex(RuntimeError, "digest"):
            _BUILDER.verify_donor_image("plane-agent-runtime:sealed-donor", self._donor_manifest())

        labels = self._donor_metadata()["labels"]
        labels["org.uxheavy.plane.hermes.commit"] = "e" * 40
        with mock.patch.object(_BUILDER, "image_metadata", return_value=self._donor_metadata(labels=labels)), self.assertRaisesRegex(
            RuntimeError, "label mismatch"
        ):
            _BUILDER.verify_donor_image("plane-agent-runtime:sealed-donor", self._donor_manifest())

    def test_sealed_donor_rejects_unsafe_archive_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "unsafe.tar"
            destination = Path(directory) / "hermes"
            with tarfile.open(archive_path, "w") as archive:
                entry = tarfile.TarInfo("opt/hermes/../escape.py")
                entry.size = 1
                archive.addfile(entry, io.BytesIO(b"x"))
            with self.assertRaisesRegex(RuntimeError, "unsafe archive entry"):
                _BUILDER.extract_safe_hermes_archive(archive_path, destination)

            with tarfile.open(archive_path, "w") as archive:
                entry = tarfile.TarInfo("opt/hermes/link")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/passwd"
                archive.addfile(entry)
            with self.assertRaisesRegex(RuntimeError, "unsafe archive entry type"):
                _BUILDER.extract_safe_hermes_archive(archive_path, destination)

    def test_donor_checkout_inputs_are_mutually_exclusive(self):
        parser = _BUILDER.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--hermes-checkout",
                    "/tmp/hermes",
                    "--hermes-donor-image",
                    "plane-agent-runtime:sealed-donor",
                ]
            )

    def test_mixed_hermes_source_provenance_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "mixed"):
            _BUILDER.validate_hermes_source_binding(
                _BUILDER.HERMES_SOURCE_KIND_GIT,
                "plane-agent-runtime:sealed-donor",
                "sha256:" + "a" * 64,
                "b" * 64,
            )

    def test_sealed_donor_tree_digest_uses_donor_relative_keys(self):
        files = {"run_agent.py": "a" * 64}
        prefixed = {"hermes/run_agent.py": files["run_agent.py"]}
        self.assertNotEqual(_BUILDER.hermes_tree_digest(files), _BUILDER.hermes_tree_digest(prefixed))
        builder_source = (TOOLS / "build-agent-runtime-image.py").read_text(encoding="utf-8")
        self.assertIn("inventory(pathlib.Path('/opt/hermes'),'')", builder_source)

    def test_runtime_builder_inventory_is_exact_candidate_source(self):
        candidate = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        actual = _BUILDER.runtime_file_hashes(candidate)
        expected = {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "apps/api/plane/agent/runtime").rglob("*"))
            if path.is_file() and path.suffix not in {".pyc", ".pyo"} and "__pycache__" not in path.parts
        }
        self.assertEqual(actual, expected)
        pinned = "1d1012f71c48615bb28b7988ce74c82421aa1d53"
        pinned_subprocess = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{pinned}:apps/api/plane/agent/runtime/subprocess.py"],
            check=True,
            capture_output=True,
        ).stdout
        self.assertNotEqual(actual["apps/api/plane/agent/runtime/subprocess.py"], hashlib.sha256(pinned_subprocess).hexdigest())
        self.assertIn("apps/api/plane/agent/runtime/credentials.py", actual)
        self.assertIn("apps/api/plane/agent/runtime/remote.py", actual)
        self.assertIn("apps/api/plane/agent/runtime/service.py", actual)
        self.assertIn("apps/api/plane/agent/runtime/contracts.py", actual)

    def test_disposable_manifest_binds_api_runtime_and_hermes_to_one_candidate(self):
        candidate = "a" * 40
        files = {"apps/api/plane/agent/runtime/subprocess.py": "b" * 64}
        source_digest = _BUILDER.runtime_source_digest(files)
        manifest = _BUILDER.disposable_manifest(
            candidate,
            "c" * 40,
            "d" * 40,
            "github.com/uxheavy/hermes-agent",
            {
                "imageTag": "plane-agent-runtime:disposable",
                "imageDigest": "sha256:" + "e" * 64,
                "runtimeRevision": candidate,
                "hermesCommit": "d" * 40,
                "hermesRemote": "github.com/uxheavy/hermes-agent",
                "contract": "plane.agent-runtime/v1",
                "runtimeSourceDigest": source_digest,
            },
            {
                "imageTag": "plane-agent-api:disposable",
                "imageDigest": "sha256:" + "f" * 64,
                "sourceRevision": candidate,
                "contract": "plane.operation/v1",
            },
            files,
        )

        validate_disposable_artifact_binding(manifest, candidate)
        self.assertEqual(manifest["pins"]["runtimeImageRevision"], candidate)
        self.assertEqual(manifest["pins"]["apiArtifact"]["sourceRevision"], candidate)
        self.assertEqual(manifest["pins"]["hermesCommit"], "d" * 40)

        sealed = _BUILDER.disposable_manifest(
            candidate,
            "c" * 40,
            "d" * 40,
            "github.com/uxheavy/hermes-agent",
            {
                **manifest["pins"],
                "imageTag": "plane-agent-runtime:disposable-sealed",
                "imageDigest": "sha256:" + "e" * 64,
                "runtimeSourceDigest": source_digest,
            },
            manifest["pins"]["apiArtifact"],
            files,
            {
                "sourceKind": "sealed-image",
                "donorImage": "plane-agent-runtime:sealed-donor",
                "donorDigest": "sha256:" + "1" * 64,
                "treeDigest": "2" * 64,
                "files": {"run_agent.py": "3" * 64},
            },
        )
        validate_disposable_artifact_binding(sealed, candidate)
        self.assertEqual(sealed["disposableBinding"]["hermesSourceKind"], "sealed-image")
        mixed_source = copy.deepcopy(sealed)
        mixed_source["disposableBinding"]["hermesSourceKind"] = "git-checkout"
        with self.assertRaisesRegex(ContractError, "hermesSource_mixed"):
            validate_disposable_artifact_binding(mixed_source, candidate)

        mixed = copy.deepcopy(manifest)
        mixed["pins"]["apiArtifact"]["sourceRevision"] = "1" * 40
        with self.assertRaisesRegex(ContractError, "manifest_disposableBinding_pin_apiSourceRevision"):
            validate_disposable_artifact_binding(mixed, candidate)
        mixed = copy.deepcopy(manifest)
        mixed["pins"]["runtimeImageRevision"] = "2" * 40
        with self.assertRaisesRegex(ContractError, "manifest_disposableBinding_pin_runtimeRevision"):
            validate_disposable_artifact_binding(mixed, candidate)

    def test_live_runner_exports_one_failure_object_before_disposable_teardown(self):
        source = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        cleanup = source[source.index("cleanup()") : source.index("trap cleanup EXIT INT TERM")]
        result_index = cleanup.index("agent-g4-live-result.py")
        docker_cleanup_index = cleanup.index('docker rm -f "${RUNTIME}"', result_index)
        compose_down_index = cleanup.index("docker compose", docker_cleanup_index)
        run_dir_delete_index = cleanup.index('rm -rf -- "${RUN_DIR}"', compose_down_index)

        self.assertLess(
            result_index,
            compose_down_index,
            "event=agent.g4.runner.failure_evidence risk=teardown_destroys_readback "
            "expected=result before down-v actual=cleanup order is unsafe "
            "suggestion=preserve exactly one bounded receipt before teardown",
        )
        self.assertLess(result_index, run_dir_delete_index)
        self.assertIn('cat "${RESULT_FILE}"', cleanup)
        self.assertNotIn('cat "${EVIDENCE_FILE}"', cleanup)
        self.assertIn('if [[ -n "${RESULT_FILE}" ]]', cleanup)
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

    def test_live_runner_resolves_selected_manifest_before_validation_and_pin_extraction(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")

        self.assertIn(
            'MANIFEST_INPUT="${PLANE_G4_LIVE_MANIFEST:-${ROOT_DIR}/tools/agent-g4-manifest.json}"',
            runner,
        )
        self.assertIn("candidate.resolve(strict=True)", runner)
        self.assertIn("resolved.is_relative_to(disposable_root)", runner)
        resolution = runner.index('MANIFEST="$(python3 - "${ROOT_DIR}" "${MANIFEST_INPUT}"')
        validation = runner.index("validate_agent_g4_live.py")
        pin_extraction = runner.index('G4_G3_BASELINE="$(python3', validation)
        self.assertLess(resolution, validation)
        self.assertLess(validation, pin_extraction)
        self.assertEqual(runner.count('--manifest "${MANIFEST}"'), 1)
        self.assertNotIn('MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"', runner)

    def test_live_runner_uses_default_and_disposable_manifest_paths_before_offline_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean_tools = root / "tools"
            clean_tools.mkdir(mode=0o700)
            for name in (
                "agent-g4-live.sh",
                "agent-g4-live-result.py",
                "agent-g4-manifest.json",
                "validate_agent_g4_live.py",
            ):
                target = clean_tools / name
                target.write_bytes((TOOLS / name).read_bytes())
            (clean_tools / "agent-g4-live.sh").chmod(0o700)

            disposable_path = root / "tmp" / "disposable" / "manifest.json"
            disposable_path.parent.mkdir(mode=0o700, parents=True)
            disposable_manifest = copy.deepcopy(MANIFEST)
            disposable_manifest["pins"]["apiArtifact"] = {
                "imageTag": "plane-agent-api:g4-disposable",
                "imageDigest": "sha256:" + "1" * 64,
                "sourceRevision": "2" * 40,
                "contract": "plane.operation/v1",
            }
            disposable_manifest["pins"]["runtimeImageTag"] = "plane-agent-runtime:disposable"
            disposable_manifest["pins"]["runtimeImageDigest"] = "sha256:" + "3" * 64
            disposable_path.write_text(json.dumps(disposable_manifest), encoding="utf-8")

            fake_bin = root / "bin"
            fake_bin.mkdir(mode=0o700)
            docker_log = root / "docker.log"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
                "if [ \"$1\" = image ] && [ \"$2\" = inspect ]; then\n"
                "    if [ \"$3\" = \"$EXPECTED_RUNTIME_IMAGE\" ]; then\n"
                "        case \"$5\" in\n"
                "            '{{.Id}}') printf '%s\\n' \"$EXPECTED_RUNTIME_DIGEST\" ;;\n"
                "            *hermes.commit*) printf '%s\\n' \"$EXPECTED_HERMES\" ;;\n"
                "            *hermes.remote*) printf '%s\\n' 'https://github.com/uxheavy/hermes-agent.git' ;;\n"
                "            *runtime.revision*) printf '%s\\n' \"$EXPECTED_RUNTIME_REVISION\" ;;\n"
                "            *runtime.source.sha256*) printf '%s\\n' \"$EXPECTED_RUNTIME_SOURCE_DIGEST\" ;;\n"
                "            *runtime.contract*) printf '%s\\n' 'plane.agent-runtime/v1' ;;\n"
                "        esac\n"
                "    else\n"
                "    case \"$5\" in\n"
                "        '{{.Id}}') printf '%s\\n' \"$EXPECTED_API_DIGEST\" ;;\n"
                "        *source.revision*) printf '%s\\n' \"$EXPECTED_API_SOURCE\" ;;\n"
                "        *contract*) printf '%s\\n' \"$EXPECTED_API_CONTRACT\" ;;\n"
                "        *artifact*) printf '%s\\n' 'plane-agent-api-g4' ;;\n"
                "    esac\n"
                "    fi\n"
                "    exit 0\n"
                "fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = inspect ]; then exit 1; fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = create ]; then exit 0; fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = rm ]; then exit 0; fi\n"
                "case \" $* \" in *\" --network none \"*) exit 42 ;; esac\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o700)
            fake_git = fake_bin / "git"
            candidate = subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            disposable_manifest["pins"]["apiArtifact"]["sourceRevision"] = candidate
            disposable_manifest["pins"]["runtimeImageRevision"] = candidate
            disposable_path.write_text(json.dumps(disposable_manifest), encoding="utf-8")
            fake_git.write_text(
                "#!/bin/sh\n"
                f"if [ \"$1\" = rev-parse ] && [ \"$2\" = HEAD ]; then printf '%s\\n' '{candidate}'; else exit 1; fi\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o700)

            authority_path = root / "authority.json"
            config_path = root / "config.json"
            provider_source = root / "synthetic-provider-source"
            provider_source.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {"access_token": "synthetic-owner-only-codex-fixture"},
                    }
                ),
                encoding="utf-8",
            )
            provider_source.chmod(0o600)

            def run_case(manifest: dict, manifest_input: str | None) -> str:
                _, authority, config, _ = fixture(candidate, manifest)
                authority["authorityId"] = "authority-manifest-path"
                config["authorityId"] = "authority-manifest-path"
                authority_path.write_text(json.dumps(authority), encoding="utf-8")
                config_path.write_text(json.dumps(config), encoding="utf-8")
                environment = {
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DOCKER_LOG": str(docker_log),
                    "EXPECTED_API_IMAGE": manifest["pins"]["apiArtifact"]["imageTag"],
                    "EXPECTED_API_DIGEST": manifest["pins"]["apiArtifact"]["imageDigest"],
                    "EXPECTED_API_SOURCE": manifest["pins"]["apiArtifact"]["sourceRevision"],
                    "EXPECTED_API_CONTRACT": manifest["pins"]["apiArtifact"]["contract"],
                    "EXPECTED_RUNTIME_IMAGE": manifest["pins"]["runtimeImageTag"],
                    "EXPECTED_RUNTIME_DIGEST": manifest["pins"]["runtimeImageDigest"],
                    "EXPECTED_RUNTIME_REVISION": manifest["pins"]["runtimeImageRevision"],
                    "EXPECTED_RUNTIME_SOURCE_DIGEST": "",
                    "EXPECTED_HERMES": manifest["pins"]["hermesCommit"],
                    "PLANE_G4_EXPECTED_CANDIDATE": candidate,
                    "PLANE_G4_LIVE_AUTHORITY": str(authority_path),
                    "PLANE_G4_LIVE_CONFIG": str(config_path),
                    "PLANE_G4_LIVE_COMMAND": COMMAND,
                    "PLANE_G4_PROVIDER_SECRET_SOURCE": str(provider_source),
                }
                if manifest_input is not None:
                    environment["PLANE_G4_LIVE_MANIFEST"] = manifest_input
                result = subprocess.run(
                    ["bash", str(clean_tools / "agent-g4-live.sh")],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                output = result.stdout + result.stderr
                self.assertIn("phase=credential-bind-preflight", output)
                return docker_log.read_text(encoding="utf-8")

            default_log = run_case(MANIFEST, None)
            self.assertIn(MANIFEST["pins"]["apiArtifact"]["imageTag"], default_log)
            disposable_log = run_case(disposable_manifest, "tmp/disposable/manifest.json")
            self.assertIn(disposable_manifest["pins"]["apiArtifact"]["imageTag"], disposable_log)

    def test_live_runner_rejects_out_of_scope_manifest_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean_tools = root / "tools"
            clean_tools.mkdir(mode=0o700)
            runner = clean_tools / "agent-g4-live.sh"
            runner.write_bytes((TOOLS / "agent-g4-live.sh").read_bytes())
            runner.chmod(0o700)
            fake_bin = root / "bin"
            fake_bin.mkdir(mode=0o700)
            docker_log = root / "docker.log"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n", encoding="utf-8")
            fake_docker.chmod(0o700)
            fake_git = fake_bin / "git"
            candidate = "a" * 40
            fake_git.write_text(
                "#!/bin/sh\n"
                f"if [ \"$1\" = rev-parse ] && [ \"$2\" = HEAD ]; then printf '%s\\n' '{candidate}'; else exit 1; fi\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o700)
            environment = {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DOCKER_LOG": str(docker_log),
                "PLANE_G4_EXPECTED_CANDIDATE": candidate,
                "PLANE_G4_LIVE_MANIFEST": "/etc/hosts",
                "PLANE_G4_LIVE_AUTHORITY": str(root / "authority.json"),
                "PLANE_G4_LIVE_CONFIG": str(root / "config.json"),
                "PLANE_G4_LIVE_COMMAND": COMMAND,
            }
            result = subprocess.run(
                ["bash", str(runner)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("expected=durable-or-owned-disposable-manifest", result.stderr)
            self.assertFalse(docker_log.exists())

    def test_live_runner_provides_home_for_pinned_hermes_child(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")

        self.assertIn(
            'RUNTIME_CHILD_ENVIRONMENT_JSON=\'{"HOME":"/tmp","HERMES_HOME":"/tmp/hermes-home"',
            runner,
        )
        self.assertIn('--env PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON="${RUNTIME_CHILD_ENVIRONMENT_JSON}"', runner)
        self.assertIn('"PYTHONSAFEPATH":"1"', runner)
        self.assertIn('"PYTHONUNBUFFERED":"1"', runner)

    def test_live_runner_stages_bounded_owner_only_secret_before_docker_networking(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        validation = runner.index("validate_agent_g4_live.py")
        staging = runner.index("LIVE_PHASE=credential-staging")
        network_create = runner.index("docker network create")
        api_invocation = runner.index("LIVE_PHASE=api-invocation")

        self.assertLess(validation, staging)
        self.assertLess(staging, network_create)
        self.assertLess(staging, api_invocation)
        self.assertIn('PROVIDER_SECRET_FILE="${RUN_DIR}/provider-credentials"', runner)
        staging_body = runner[staging : runner.index("LIVE_PHASE=credential-bind-preflight", staging)]
        self.assertIn("stat.S_ISREG(source_stat.st_mode)", staging_body)
        self.assertIn("source_stat.st_size > MAX_PROVIDER_SECRET_BYTES", staging_body)
        self.assertIn("copied > MAX_PROVIDER_SECRET_BYTES", staging_body)
        self.assertIn("copied != source_stat.st_size", staging_body)
        self.assertIn("os.O_NOFOLLOW", runner)
        self.assertIn("os.O_EXCL", runner)
        self.assertIn("MAX_PROVIDER_SECRET_BYTES = 64 * 1024", runner)
        self.assertIn("os.fchmod(destination_fd, 0o600)", runner)
        self.assertIn("os.fsync(destination_fd)", runner)
        self.assertIn("os.close(destination_fd)", runner)
        self.assertIn("os.close(source_fd)", runner)
        self.assertIn('mkdir -m 700 -- "${RUN_DIR}"', runner)
        self.assertNotIn('--mount type=bind,src="${PROVIDER_SECRET_SOURCE}"', runner)
        self.assertNotIn('--mount type=bind,src="${PROVIDER_SECRET_FILE}"', runner)
        self.assertIn('PROVIDER_SECRET_VOLUME="${PROJECT}_provider_credentials"', runner)
        self.assertIn(
            '--mount type=volume,src="${PROVIDER_SECRET_VOLUME}",dst=/run/secrets,volume-nocopy',
            runner,
        )

    def test_live_runner_uses_one_task_owned_shared_credential_state_volume(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        runtime_start = runner.index("LIVE_PHASE=runtime-start")
        api_invocation = runner.index("LIVE_PHASE=api-invocation")
        runtime = runner[runtime_start:api_invocation]
        api = runner[api_invocation:]
        cleanup = runner[runner.index("cleanup()") : runner.index("trap cleanup EXIT INT TERM")]

        self.assertIn('CREDENTIAL_STATE_VOLUME="${PROJECT}_agent_runtime_credential_state"', runner)
        self.assertIn('CREDENTIAL_STATE_TARGET="/run/plane-agent-credentials"', runner)
        self.assertIn('CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_TARGET}/revocations.json"', runner)
        volume_create = runner.index("docker volume create")
        self.assertLess(volume_create, runtime_start)
        self.assertIn("--label com.uxheavy.plane.agent-g4-credential-state=true", runner)
        self.assertIn('--label "com.uxheavy.plane.agent-g4-project=${PROJECT}"', runner)

        shared_mount = (
            '--mount type=volume,src="${CREDENTIAL_STATE_VOLUME}",'
            'dst="${CREDENTIAL_STATE_TARGET}",volume-nocopy'
        )
        runtime_shared_mount = f"{shared_mount[:-len(',volume-nocopy')]},readonly,volume-nocopy"
        self.assertIn(runtime_shared_mount, runtime)
        self.assertIn(shared_mount, api)
        self.assertEqual(runner.count('src="${CREDENTIAL_STATE_VOLUME}"'), 2)
        self.assertEqual(runtime.count("--mount type=volume"), 1)
        self.assertEqual(api.count("--mount type=volume"), 2)
        self.assertEqual(
            runner.count('--env PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_FILE}"'),
            2,
        )
        self.assertNotIn("--tmpfs /run/plane-agent-credentials", runtime)
        self.assertNotIn("PROVIDER_SECRET_FILE", runtime)
        self.assertNotIn("plane_agent_provider_credentials", runtime)
        self.assertIn(
            '--mount type=volume,src="${PROVIDER_SECRET_VOLUME}",'
            'dst=/run/secrets,readonly,volume-nocopy',
            api,
        )

        runtime_remove = cleanup.index('docker rm -f "${RUNTIME}"')
        volume_remove = cleanup.index('docker volume rm "${CREDENTIAL_STATE_VOLUME}"')
        provider_volume_remove = cleanup.index('docker volume rm "${PROVIDER_SECRET_VOLUME}"')
        compose_down = cleanup.index("docker compose")
        run_dir_delete = cleanup.index('rm -rf -- "${RUN_DIR}"')
        self.assertLess(runtime_remove, volume_remove)
        self.assertLess(compose_down, volume_remove)
        self.assertLess(volume_remove, provider_volume_remove)
        self.assertLess(volume_remove, run_dir_delete)
        self.assertLess(provider_volume_remove, run_dir_delete)
        self.assertIn('if [[ "${CREDENTIAL_STATE_VOLUME_CREATED}" -eq 1 ]]; then', cleanup)
        self.assertIn('if [[ "${PROVIDER_SECRET_VOLUME_CREATED}" -eq 1 ]]; then', cleanup)
        self.assertIn('CREDENTIAL_STATE_VOLUME_CREATED=1', runner[volume_create:runtime_start])
        self.assertEqual(runner.count('docker volume rm "${CREDENTIAL_STATE_VOLUME}"'), 1)
        self.assertEqual(runner.count('docker volume rm "${PROVIDER_SECRET_VOLUME}"'), 1)

    def test_live_runner_creates_missing_tmp_parent_before_pre_provider_boundary(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        staging = runner.index("LIVE_PHASE=credential-staging")
        run_dir = runner.index('mkdir -m 700 -- "${RUN_DIR}"', staging)
        preflight = runner.index("LIVE_PHASE=credential-bind-preflight", run_dir)

        self.assertIn('TMP_ROOT="${ROOT_DIR}/tmp"', runner)
        self.assertIn('mkdir -m 700 -- "${TMP_ROOT}"', runner)
        self.assertIn('if [[ -L "${TMP_ROOT}" ]]; then', runner)
        self.assertIn('chmod 700 "${TMP_ROOT}"', runner)
        self.assertLess(runner.index('mkdir -m 700 -- "${TMP_ROOT}"', staging), run_dir)
        self.assertLess(run_dir, preflight)
        self.assertIn('RUN_DIR_CREATED=1', runner[run_dir:preflight])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean_tools = root / "tools"
            clean_tools.mkdir(mode=0o700)
            for name in (
                "agent-g4-live.sh",
                "agent-g4-live-result.py",
                "agent-g4-manifest.json",
                "validate_agent_g4_live.py",
            ):
                target = clean_tools / name
                target.write_bytes((TOOLS / name).read_bytes())
            (clean_tools / "agent-g4-live.sh").chmod(0o700)
            fake_bin = root / "bin"
            fake_bin.mkdir(mode=0o700)
            docker_log = root / "docker.log"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
                "if [ \"$1\" = image ] && [ \"$2\" = inspect ]; then\n"
                "    if [ \"$3\" = '" + MANIFEST["pins"]["runtimeImageTag"] + "' ]; then\n"
                "        case \"$5\" in\n"
                f"            '{{{{.Id}}}}') printf '%s\\n' '{MANIFEST['pins']['runtimeImageDigest']}' ;;\n"
                f"            *hermes.commit*) printf '%s\\n' '{MANIFEST['pins']['hermesCommit']}' ;;\n"
                "            *hermes.remote*) printf '%s\\n' 'https://github.com/uxheavy/hermes-agent.git' ;;\n"
                f"            *runtime.revision*) printf '%s\\n' '{MANIFEST['pins']['runtimeImageRevision']}' ;;\n"
                "            *runtime.source.sha256*) printf '%s\\n' '' ;;\n"
                "            *runtime.contract*) printf '%s\\n' 'plane.agent-runtime/v1' ;;\n"
                "        esac\n"
                "    else\n"
                "    case \"$5\" in\n"
                f"        '{{{{.Id}}}}') printf '%s\\n' '{MANIFEST['pins']['apiArtifact']['imageDigest']}' ;;\n"
                f"        *source.revision*) printf '%s\\n' '{MANIFEST['pins']['apiArtifact']['sourceRevision']}' ;;\n"
                f"        *contract*) printf '%s\\n' '{MANIFEST['pins']['apiArtifact']['contract']}' ;;\n"
                "        *artifact*) printf '%s\\n' 'plane-agent-api-g4' ;;\n"
                "    esac\n"
                "    fi\n"
                "    exit 0\n"
                "fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = inspect ]; then exit 1; fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = create ]; then exit 0; fi\n"
                "if [ \"$1\" = volume ] && [ \"$2\" = rm ]; then exit 0; fi\n"
                "case \" $* \" in *provider-credentials*) exit 125 ;; esac\n"
                "case \" $* \" in *\" --network none \"*) exit 42 ;; esac\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o700)
            fake_git = fake_bin / "git"
            candidate = subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            fake_git.write_text(
                "#!/bin/sh\n"
                f"if [ \"$1\" = rev-parse ] && [ \"$2\" = HEAD ]; then printf '%s\\n' '{candidate}'; else exit 1; fi\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o700)

            _, authority, config, _ = fixture(candidate, MANIFEST)
            authority["authorityId"] = "authority-clean-checkout"
            config["authorityId"] = "authority-clean-checkout"
            authority_path = root / "authority.json"
            config_path = root / "config.json"
            provider_source = root / "synthetic-provider-source"
            authority_path.write_text(json.dumps(authority), encoding="utf-8")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            provider_source.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {"access_token": "synthetic-owner-only-codex-fixture"},
                    }
                ),
                encoding="utf-8",
            )
            provider_source.chmod(0o600)

            environment = {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "TMPDIR": str(root),
                "DOCKER_LOG": str(docker_log),
                "PLANE_G4_EXPECTED_CANDIDATE": candidate,
                "PLANE_G4_LIVE_AUTHORITY": str(authority_path),
                "PLANE_G4_LIVE_CONFIG": str(config_path),
                "PLANE_G4_LIVE_COMMAND": COMMAND,
                "PLANE_G4_PROVIDER_SECRET_SOURCE": str(provider_source),
            }
            result = subprocess.run(
                ["bash", str(clean_tools / "agent-g4-live.sh")],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
            output = result.stdout + result.stderr
            self.assertIn("phase=credential-bind-preflight", output)
            self.assertNotIn("expected=invocation-run-directory", output)
            self.assertTrue((root / "tmp").is_dir())
            self.assertEqual((root / "tmp").stat().st_mode & 0o777, 0o700)
            result_files = list((root / "tmp").glob("*.result"))
            self.assertEqual(len(result_files), 1)
            self.assertEqual(result_files[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(result_files[0].read_bytes(), result.stdout.encode())
            docker_log_text = docker_log.read_text(encoding="utf-8")
            self.assertIn("--network none", docker_log_text)
            self.assertIn("provider_credentials", docker_log_text)
            self.assertIn("type=volume,src=", docker_log_text)
            self.assertNotIn("src=" + str(root / "tmp"), docker_log_text)
            self.assertNotIn("synthetic-owner-only-codex-fixture", output)
            self.assertNotIn("synthetic-owner-only-codex-fixture", docker_log_text)
            self.assertIn("volume rm", docker_log_text)

    def test_live_runner_handoffs_staged_secret_to_network_none_volume_without_logging_contents(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        preflight_start = runner.index("LIVE_PHASE=credential-bind-preflight")
        compose_start = runner.index("LIVE_PHASE=compose", preflight_start)
        preflight = runner[preflight_start:compose_start]

        self.assertIn("docker run --rm -i --network none", preflight)
        self.assertEqual(preflight.count("docker run --rm -i --network none"), 1)
        self.assertIn('docker volume inspect "${PROVIDER_SECRET_VOLUME}"', preflight)
        self.assertIn('docker volume create', preflight)
        self.assertIn("sys.stdin.buffer.read(MAX_PROVIDER_SECRET_BYTES + 1)", preflight)
        self.assertIn("follow_symlinks=False", preflight)
        self.assertIn("stat.S_IMODE(metadata.st_mode) != 0o600", preflight)
        self.assertIn("metadata.st_size > 64 * 1024", preflight)
        self.assertNotIn("cat ", preflight)
        self.assertNotIn("print(", preflight)
        self.assertNotIn('--mount type=bind,src="${PROVIDER_SECRET_FILE}"', preflight)
        self.assertLess(preflight_start, runner.index("docker compose", compose_start))

    def test_api_invocation_uses_task_volumes_and_stdin_without_invoke_source_bind_mount(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        api = runner[runner.index("LIVE_PHASE=api-invocation") :]

        self.assertIn('docker run --rm -i --network "${NETWORK}"', api)
        self.assertIn('"${API_IMAGE}" python - <"${LIVE_INVOKE_SOURCE}"', api)
        self.assertIn(
            '--mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/plane-agent-runtime-secret,readonly',
            api,
        )
        self.assertIn(
            '--mount type=volume,src="${PROVIDER_SECRET_VOLUME}",dst=/run/secrets,readonly,volume-nocopy',
            api,
        )
        self.assertIn(
            '--mount type=volume,src="${CREDENTIAL_STATE_VOLUME}",dst="${CREDENTIAL_STATE_TARGET}",volume-nocopy',
            api,
        )
        self.assertIn("--env PLANE_AGENT_RUNTIME_SECRET_FILE=/run/plane-agent-runtime-secret", api)
        self.assertNotIn('--mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/secrets/', api)
        self.assertNotIn('--mount type=bind,src="${LIVE_INVOKE_SOURCE}"', api)
        self.assertNotIn("/tmp/agent-g4-live-invoke.py", api)
        self.assertNotIn("PROVIDER_SECRET_FILE", api)
        self.assertNotIn("PLANE_G4_PROVIDER_SECRET_SOURCE", api)

    def test_live_runner_classifies_bounded_docker_mount_failures_without_raw_diagnostics(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        function = runner[runner.index("safe_docker_failure_reason()") : runner.index("\ncleanup()")]
        with tempfile.TemporaryDirectory() as directory:
            error_file = Path(directory) / "docker-error.log"
            raw_path = "/private/secret/provider-source"
            raw_secret = "synthetic-provider-secret-value"
            error_file.write_text(
                "docker: Error response from daemon: failed to create task for container: "
                "error mounting %s: create mountpoint read-only file system %s\n" % (raw_path, raw_secret),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "-c", function + '\nERROR_FILE="$1"\nsafe_docker_failure_reason', "classifier", str(error_file)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "docker_mount_target_read_only")
        self.assertNotIn(raw_path, result.stdout + result.stderr)
        self.assertNotIn(raw_secret, result.stdout + result.stderr)

    def test_live_runner_cleanup_removes_staged_secret_and_exact_invocation_directory(self):
        runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        cleanup = runner[runner.index("cleanup()") : runner.index("trap cleanup EXIT INT TERM")]

        self.assertIn('rm -f -- "${PROVIDER_SECRET_FILE}"', cleanup)
        self.assertIn('docker volume rm "${PROVIDER_SECRET_VOLUME}"', cleanup)
        self.assertIn('rm -rf -- "${RUN_DIR}"', cleanup)
        self.assertNotIn('rm -rf -- "${ROOT_DIR}"', cleanup)
        self.assertNotIn('rm -rf -- "${ROOT_DIR}/tmp"', cleanup)
        self.assertIn("trap cleanup EXIT INT TERM", runner)

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

    def test_live_helper_replays_only_after_success_with_provider_access_disabled(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        supervisor_calls = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "call_command"
        ]
        self.assertEqual(len(supervisor_calls), 2)
        primary, replay = sorted(supervisor_calls, key=lambda node: node.lineno)
        self.assertLess(primary.lineno, replay.lineno)
        gate = source.index("live product lifecycle or canary evidence was incomplete")
        self.assertLess(gate, source.index("before_replay"))
        self.assertLess(source.index("before_replay"), source.index("duration_ms"))
        self.assertIn('PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER={}', source)
        self.assertIn('"frames=0"', source)
        finally_body_calls = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Try)
            for child in node.finalbody
            for call in ast.walk(child)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "call_command"
        ]
        self.assertEqual(finally_body_calls, [])

    def test_failed_primary_has_one_supervisor_call_and_no_replay_call(self):
        source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        supervisor_calls = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "call_command"
        ]
        self.assertEqual(len(supervisor_calls), 2)
        handlers_and_finally = [
            child
            for node in ast.walk(main)
            if isinstance(node, ast.Try)
            for child in (*node.handlers, *node.finalbody)
        ]
        self.assertTrue(handlers_and_finally)
        self.assertTrue(
            all(
                not any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "call_command"
                    for call in ast.walk(child)
                )
                for child in handlers_and_finally
            )
        )
        self.assertLess(
            source.index("live product lifecycle or canary evidence was incomplete"),
            source.index("replay_stdout"),
        )

    def test_success_receipt_requires_bounded_replay_and_readback_facts(self):
        manifest, authority, config, evidence_text = fixture()
        evidence = json.loads(evidence_text)
        self.assertEqual(
            set(evidence),
            {"schemaVersion", "status", "binding", "provider", "canaries", "thresholds", "readback", "summary"},
        )
        readback = evidence["readback"]
        self.assertEqual(
            set(readback).difference({"audit", "version"}),
            {
                "runtimeExit",
                "runtimeEventIngress",
                "providerAttempts",
                "planeOperationAudit",
                "transcriptEvidence",
                "explicitPublication",
                "replay",
            },
        )
        self.assertEqual(
            [row["operationId"] for row in readback["planeOperationAudit"]],
            [
                "search_workspace",
                "work_item.read",
                "catalog.search",
                "catalog.describe",
                "agent.outcome.evaluate",
                "agent.outcome.submit",
                "agent.outcome.publish",
            ],
        )
        self.assertEqual(readback["runtimeExit"]["kind"], "completed")
        self.assertEqual(readback["transcriptEvidence"]["count"], 1)
        self.assertEqual(readback["explicitPublication"]["count"], 1)
        self.assertEqual(set(readback["replay"]["new"].values()), {0})
        temp, paths = self.write_case(manifest, authority, config, evidence_text)
        self.addCleanup(temp.cleanup)
        self.assertEqual(validate_files(*paths, CANDIDATE, CANDIDATE, COMMAND)["passed"], 2)

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
            failure_code="runtime_process_failed",
            failure_reason=(
                '{"failureCode":"runtime_process_failed","failurePhase":"launcher",'
                '"failureDetail":"authorization=secret-token"}'
            ),
            runtime_exit={
                "kind": "failed",
                "failure": {
                    "code": "budget_exhausted",
                    "retryable": False,
                    "message": "raw model text must not be copied",
                },
            },
            runtime_event_kind_counts={"usage_observed": 1, "unknown_kind": 7},
            terminal_code="budget_exhausted",
            terminal_reason=(
                '{"failureCode":"budget_exhausted","failurePhase":"runtime_process",'
                '"failureDetail":"process_exit","failureSubreason":"model_call_budget_exhausted"}'
            ),
            plane_host_operation_receipts=False,
            plane_operation_audit=[
                {
                    "operation_id": "agent.outcome.evaluate",
                    "phase": "outcome",
                    "outcome": "denied",
                    "error_code": "NOT_AUTHORIZED",
                    "request_input": "must not escape",
                }
            ],
        )
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        self.assertEqual(evidence["schemaVersion"], "plane-agent-g4/live-failure/v1")
        self.assertEqual(evidence["status"], "failed")
        self.assertLessEqual(len(encoded.encode("utf-8")), 4096)
        self.assertEqual(
            set(evidence),
            {
                "schemaVersion",
                "status",
                "binding",
                "failure",
                "run",
                "invocation",
                "runtimeExit",
                "runtimeEventIngress",
                "providerAttempts",
                "terminal",
                "planeHostOperationReceipts",
                "planeOperationAudit",
            },
        )
        for forbidden in ("do not include", "must not escape", "prompt", "response", "credential", "payload", "rawLogs"):
            self.assertNotIn(forbidden, encoded)
        self.assertNotRegex(encoded, re.compile(r"(?i)(password|secret|token|api[_-]?key|authorization|credential)"))
        self.assertEqual(
            evidence["runtimeExit"],
            {
                "present": True,
                "kind": "failed",
                "finalSequence": None,
                "failure": {"code": "budget_exhausted", "retryable": False},
            },
        )
        self.assertEqual(evidence["runtimeEventIngress"], {"kindCounts": {"usage_observed": 1}})
        self.assertEqual(
            evidence["terminal"],
            {
                "present": True,
                "kind": "run_failure",
                "code": "budget_exhausted",
                "reasonCategory": "model_call_budget_exhausted",
            },
        )
        self.assertFalse(evidence["planeHostOperationReceipts"])
        self.assertEqual(
            evidence["planeOperationAudit"],
            [
                {"operationId": "search_workspace", "status": "absent", "errorCode": None, "count": 0},
                {"operationId": "work_item.read", "status": "absent", "errorCode": None, "count": 0},
                {"operationId": "catalog.search", "status": "absent", "errorCode": None, "count": 0},
                {"operationId": "catalog.describe", "status": "absent", "errorCode": None, "count": 0},
                {
                    "operationId": "agent.outcome.evaluate",
                    "status": "denied",
                    "errorCode": "NOT_AUTHORIZED",
                    "count": 1,
                },
                {"operationId": "agent.outcome.submit", "status": "absent", "errorCode": None, "count": 0},
                {"operationId": "agent.outcome.publish", "status": "absent", "errorCode": None, "count": 0},
            ],
        )
        self.assertEqual(
            evidence["failure"],
            {
                "phase": "api-invocation",
                "errorClass": "CommandError",
                "exitCode": 1,
                "reasonCode": "runtime_process_failed",
                "reasonPhase": "launcher",
                "reasonDetail": "unavailable",
                "reasonSubreason": "unavailable",
            },
        )
        operation_statuses = namespace["build_failure_evidence"](
            binding={},
            failure_phase="api-invocation",
            error_class="RuntimeError",
            exit_code=1,
            run_id="run:operation-statuses",
            run_state="failed",
            invocation_id="invocation:operation-statuses",
            invocation_state="failed",
            provider_attempts=[],
            terminal_kind="run_failure",
            plane_operation_audit=(
                [
                    {
                        "operation_id": "work_item.read",
                        "phase": "outcome",
                        "outcome": "failure",
                        "error_code": "PLANE_CONFLICT",
                    },
                    {
                        "operation_id": "agent.outcome.publish",
                        "phase": "outcome",
                        "outcome": "outcome_unknown",
                        "error_code": "OUTCOME_UNKNOWN",
                    },
                ]
                + [
                    {
                        "operation_id": "agent.outcome.submit",
                        "phase": "outcome",
                        "outcome": "success",
                    }
                ]
                * 20
            ),
        )
        statuses = {row["operationId"]: row for row in operation_statuses["planeOperationAudit"]}
        self.assertEqual(statuses["work_item.read"], {
            "operationId": "work_item.read",
            "status": "conflict",
            "errorCode": "PLANE_CONFLICT",
            "count": 1,
        })
        self.assertEqual(statuses["agent.outcome.publish"], {
            "operationId": "agent.outcome.publish",
            "status": "unavailable",
            "errorCode": "OUTCOME_UNKNOWN",
            "count": 1,
        })
        self.assertEqual(statuses["agent.outcome.submit"]["count"], 8)
        with_subreason = namespace["build_failure_evidence"](
            binding={},
            failure_phase="api-invocation",
            error_class="CommandError",
            exit_code=1,
            run_id="run:bounded-subreason",
            run_state="blocked",
            invocation_id="invocation:bounded-subreason",
            invocation_state="blocked",
            provider_attempts=[],
            terminal_kind="run_blocker",
            failure_code="runtime_configuration_pre_dispatch_failure",
            failure_reason=(
                '{"failureCode":"runtime_configuration_pre_dispatch_failure",'
                '"failurePhase":"runtime_configuration","failureDetail":"dispatch_rejected",'
                '"failureSubreason":"runtime_configuration_rejected"}'
            ),
        )
        self.assertEqual(
            with_subreason["failure"]["reasonSubreason"],
            "runtime_configuration_rejected",
        )
        budget_failure = namespace["build_failure_evidence"](
            binding={},
            failure_phase="api-invocation",
            error_class="RuntimeError",
            exit_code=1,
            run_id="run:budget",
            run_state="failed",
            invocation_id="invocation:budget",
            invocation_state="failed",
            provider_attempts=[],
            terminal_kind="run_failure",
            failure_code="budget_exhausted",
            failure_reason=(
                '{"failureCode":"budget_exhausted",'
                '"failurePhase":"runtime_process","failureDetail":"process_exit",'
                '"failureSubreason":"model_call_budget_exhausted"}'
            ),
        )
        self.assertEqual(budget_failure["failure"]["reasonCode"], "budget_exhausted")
        self.assertEqual(budget_failure["failure"]["reasonPhase"], "runtime_process")
        self.assertEqual(budget_failure["failure"]["reasonDetail"], "process_exit")
        self.assertEqual(
            budget_failure["failure"]["reasonSubreason"],
            "model_call_budget_exhausted",
        )
        runtime_failure = namespace["build_failure_evidence"](
            binding={},
            failure_phase="api-invocation",
            error_class="RuntimeError",
            exit_code=1,
            run_id="run:runtime-error",
            run_state="failed",
            invocation_id="invocation:runtime-error",
            invocation_state="failed",
            provider_attempts=[],
            terminal_kind="run_failure",
            failure_code="runtime_error",
            failure_reason=(
                '{"failureCode":"runtime_error",'
                '"failurePhase":"runtime_process",'
                '"failureDetail":"process_exit",'
                '"failureSubreason":"runtime_execution_failed",'
                '"failureCause":"host_operation_failure"}'
            ),
            runtime_exit={
                "kind": "failed",
                "failure": {
                    "code": "runtime_error",
                    "retryable": False,
                    "cause": "host_operation_failure",
                    "message": "raw host message must not escape",
                },
            },
            terminal_code="runtime_error",
            terminal_reason=(
                '{"failureCode":"runtime_error",'
                '"failurePhase":"runtime_process",'
                '"failureDetail":"process_exit",'
                '"failureSubreason":"runtime_execution_failed",'
                '"failureCause":"host_operation_failure"}'
            ),
        )
        self.assertEqual(
            runtime_failure["runtimeExit"],
            {
                "present": True,
                "kind": "failed",
                "finalSequence": None,
                "failure": {
                    "code": "runtime_error",
                    "retryable": False,
                    "cause": "host_operation_failure",
                },
            },
        )
        self.assertEqual(
            runtime_failure["failure"]["reasonCode"],
            "runtime_error",
        )
        self.assertEqual(
            runtime_failure["failure"]["reasonSubreason"],
            "runtime_execution_failed",
        )
        self.assertEqual(
            runtime_failure["failure"]["reasonCause"],
            "host_operation_failure",
        )
        self.assertEqual(
            runtime_failure["terminal"],
            {
                "present": True,
                "kind": "run_failure",
                "code": "runtime_error",
                "reasonCategory": "host_operation_failure",
            },
        )

        parser = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_supervisor_failure_reason"
        )
        exec(
            compile(ast.Module(body=[parser], type_ignores=[]), str(TOOLS / "agent-g4-live-invoke.py"), "exec"),
            namespace,
        )
        bounded_reason = {
            "failureCode": "runtime_configuration_pre_dispatch_failure",
            "failurePhase": "runtime_configuration",
            "failureDetail": "dispatch_rejected",
            "failureSubreason": "provider_attempt_evidence_rejected",
        }
        parsed_reason = namespace["_supervisor_failure_reason"](
            "invocation=invocation:bounded state=blocked terminal=run_blocker frames=0 failure="
            + json.dumps(bounded_reason, sort_keys=True, separators=(",", ":"))
        )
        self.assertEqual(
            json.loads(parsed_reason),
            bounded_reason,
        )
        causal_reason = {
            "failureCode": "runtime_error",
            "failurePhase": "runtime_process",
            "failureDetail": "process_exit",
            "failureSubreason": "runtime_execution_failed",
            "failureCause": "invalid_usage_accounting",
        }
        self.assertEqual(
            json.loads(
                namespace["_supervisor_failure_reason"](
                    "state=failed failure="
                    + json.dumps(causal_reason, sort_keys=True, separators=(",", ":"))
                )
            ),
            causal_reason,
        )
        self.assertIsNone(
            namespace["_supervisor_failure_reason"](
                'failure={"failureCode":"runtime_configuration_pre_dispatch_failure",'
                '"failurePhase":"runtime_configuration","failureDetail":"/private/secret"}'
            )
        )
        malformed = namespace["build_failure_evidence"](
            binding={},
            failure_phase="api-invocation",
            error_class="RuntimeError",
            exit_code=1,
            run_id=None,
            run_state="failed",
            invocation_id=None,
            invocation_state="failed",
            provider_attempts=[],
            terminal_kind="none",
            failure_reason=json.dumps(
                {
                    "failureCode": ["secret-token"],
                    "failurePhase": {"path": "/private/secret"},
                    "failureDetail": ["authorization=secret-token"],
                }
            ),
        )
        self.assertEqual(malformed["failure"]["reasonCode"], "unspecified")
        self.assertEqual(malformed["failure"]["reasonPhase"], "unavailable")
        self.assertEqual(malformed["failure"]["reasonDetail"], "unavailable")
        self.assertEqual(malformed["failure"]["reasonSubreason"], "unavailable")
        self.assertNotRegex(
            json.dumps(malformed, sort_keys=True),
            re.compile(r"(?i)(password|secret|token|api[_-]?key|authorization|credential)"),
        )

    def test_provider_attempt_reconciliation_leaves_completed_attempt_completed(self):
        source = (ROOT / "apps/api/plane/tests/unit/agent/test_lifecycle.py").read_text(encoding="utf-8")
        self.assertIn("def test_provider_attempt_reconciliation_leaves_completed_attempt_completed", source)

    def test_red_team_stage_requires_exact_image_http_dispatch_and_pinned_hermes_wrapper(self):
        source = (TOOLS / "agent-g4-runtime-red-team.py").read_text(encoding="utf-8")
        image_dockerfile = (ROOT / "deployments/cli/community/agent-runtime/Dockerfile").read_text(encoding="utf-8")
        runtime_policy = (ROOT / "apps/api/plane/agent/runtime/subprocess.py").read_text(encoding="utf-8")
        runtime_service = (ROOT / "apps/api/plane/agent/runtime/service.py").read_text(encoding="utf-8")
        vfork_adapter = (ROOT / "apps/api/plane/agent/runtime/sitecustomize.py").read_text(encoding="utf-8")
        live_runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
        budget_probe = (TOOLS / "agent-g4-wave0u-probe.py").read_text(encoding="utf-8")
        bootstrap_probe = (TOOLS / "agent-g4-ut014-real-bootstrap.py").read_text(encoding="utf-8")
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
        self.assertIn("COPY hermes/ /opt/hermes/", image_dockerfile)
        self.assertIn("ENV PYTHONPATH=/opt/plane/agent/dependencies:/opt:/opt/hermes", image_dockerfile)
        self.assertIn(
            "COPY hermes/plane_runtime/g1_runtime_image/dotenv/ /opt/plane/agent/dependencies/dotenv/",
            image_dockerfile,
        )
        self.assertNotIn(
            "COPY hermes/plane_runtime/g1_runtime_image/dotenv/ /opt/hermes/dotenv/",
            image_dockerfile,
        )
        self.assertIn("COPY plane_runtime_service/sitecustomize.py /opt/sitecustomize.py", image_dockerfile)
        self.assertIn(
            'child_environment.setdefault(\n            "PYTHONPATH",\n            "/opt/plane/agent/dependencies:/opt:/opt/hermes",\n        )',
            runtime_service,
        )
        self.assertIn('"PYTHONPATH":"/tmp:/opt/plane/agent/dependencies:/opt:/opt/hermes"', live_runner)
        self.assertIn("'PYTHONPATH': '/tmp:/opt/plane/agent/dependencies:/opt:/opt/hermes'", budget_probe)
        self.assertIn(
            '"PYTHONPATH": "/opt/plane:/opt/plane/agent/dependencies:/opt:/opt/hermes"',
            bootstrap_probe,
        )
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

    def test_api_artifact_commands_import_the_copied_candidate_source(self):
        dockerfile = (ROOT / "apps/api/Dockerfile.g4").read_text(encoding="utf-8")
        resolver = (ROOT / "apps/api/bin/plane-agent-runtime-credential-resolver").read_text(encoding="utf-8")

        self.assertIn("ENV PYTHONPATH=/workspace/apps/api", dockerfile)
        self.assertIn("plane_module.__file__", dockerfile)
        self.assertIn('importlib.import_module("plane.agent.runtime.credentials")', dockerfile)
        self.assertIn("credentials_module.__file__", dockerfile)
        self.assertIn('root / "plane/agent/runtime/credentials.py"', dockerfile)
        self.assertIn("config_module.__file__", dockerfile)
        self.assertIn('config_module.RUNTIME_PROTOCOL != "plane.agent-runtime/v1"', dockerfile)
        self.assertIn("importlib.util.spec_from_file_location", resolver)
        self.assertIn('_CREDENTIALS_SOURCE = "/workspace/apps/api/plane/agent/runtime/credentials.py"', resolver)
        self.assertNotIn("from plane.agent.runtime.credentials import", resolver)
        self.assertNotIn('sys.path.insert(0, "/code")', resolver)

    def test_api_artifact_packages_the_candidate_resolver_at_the_production_path(self):
        dockerfile = (ROOT / "apps/api/Dockerfile.g4").read_text(encoding="utf-8")
        resolver = ROOT / "apps/api/bin/plane-agent-runtime-credential-resolver"

        self.assertTrue(resolver.is_file())
        self.assertTrue(resolver.stat().st_mode & 0o111)
        copy = (
            "COPY --chown=root:root ./bin/plane-agent-runtime-credential-resolver "
            "/usr/local/bin/plane-agent-runtime-credential-resolver"
        )
        self.assertIn(copy, dockerfile)
        self.assertIn("RUN chmod 755 /usr/local/bin/plane-agent-runtime-credential-resolver", dockerfile)
        self.assertIn('root / "bin/plane-agent-runtime-credential-resolver"', dockerfile)
        self.assertIn('Path("/usr/local/bin/plane-agent-runtime-credential-resolver")', dockerfile)
        self.assertIn("installed_resolver.lstat()", dockerfile)
        self.assertIn("stat.S_IMODE(installed_resolver_stat.st_mode) != 0o755", dockerfile)
        self.assertIn("installed_resolver_stat.st_uid != 0 or installed_resolver_stat.st_gid != 0", dockerfile)
        self.assertIn("installed_sha256 != source_sha256", dockerfile)
        self.assertLess(dockerfile.index(copy), dockerfile.index("RUN PLANE_API_SOURCE_REVISION="))

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

    def test_caller_owned_hermes_checkouts_survive_cleanup(self):
        source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        cleanup = source[source.index("cleanup()") : source.index("trap cleanup EXIT")]
        self.assertIn('G4_TEMP_PARENT="${ROOT_DIR}/tmp"', source)
        self.assertIn('PLANE_G4_DISPOSABLE_HERMES_ROOT', source)
        self.assertIn('"${G4_TEMP_PARENT}"/plane-g4-hermes-*)', source)
        self.assertIn('HERMES_ROOT_CREATED_BY_VERIFIER=0', source)
        self.assertNotIn('HERMES_ROOT_CREATED_BY_VERIFIER=1', source)
        self.assertIn('if ! docker run --rm --network none', source)
        cleanup_helper = source[source.index("cleanup_disposable_hermes()") : source.index("write_receipt()")]
        self.assertIn('[[ "${HERMES_ROOT_CREATED_BY_VERIFIER}" -eq 1 ]] || return 0', cleanup_helper)
        self.assertIn('rm -rf -- "${HERMES_ROOT}"', cleanup_helper)
        self.assertIn('[[ ! -e "${HERMES_ROOT}" ]]', cleanup_helper)
        self.assertNotIn('rm -rf -- "${G4_TEMP_PARENT}"', cleanup)

    def test_external_hermes_roots_are_never_cleaned_as_g3_owned_state(self):
        g4_source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        g3_source = (TOOLS / "verify-agent-g3.sh").read_text(encoding="utf-8")

        # Both Hermes paths are supplied checkouts.  Only a verifier-created
        # path may enter a destructive cleanup branch.
        self.assertIn("HERMES_ROOT_CREATED_BY_VERIFIER=0", g4_source)
        self.assertIn("G3_HERMES_ROOT_CREATED_BY_VERIFIER=0", g4_source)
        self.assertNotIn("HERMES_ROOT_CREATED_BY_VERIFIER=1", g4_source)
        self.assertNotIn("G3_HERMES_ROOT_CREATED_BY_VERIFIER=1", g4_source)
        g4_cleanup = g4_source[g4_source.index("cleanup_disposable_hermes()") : g4_source.index("write_receipt()")]
        self.assertIn('[[ "${HERMES_ROOT_CREATED_BY_VERIFIER}" -eq 1 ]] || return 0', g4_cleanup)
        self.assertIn('[[ "${G3_HERMES_ROOT_CREATED_BY_VERIFIER}" -eq 1 ]] || return 0', g4_cleanup)

        g3_cleanup = g3_source[g3_source.index("cleanup_runtime_log_dir()") : g3_source.index("trap cleanup EXIT")]
        self.assertIn("cleanup_runtime_log_dir", g3_cleanup)
        self.assertIn("CREATED_RUNTIME_LOG_DIR", g3_cleanup)
        self.assertNotIn('rm -rf -- "${HERMES_ROOT}"', g3_cleanup)
        self.assertNotIn('rm -rf -- "${HERMES_PIN_ROOT}"', g3_cleanup)

    def test_g3_prerequisite_uses_independent_accepted_hermes_pin(self):
        source = (TOOLS / "verify-agent-g4.sh").read_text(encoding="utf-8")
        self.assertIn('manifest_pin() {', source)
        self.assertIn('HERMES_COMMIT="$(manifest_pin pins.hermesCommit)"', source)
        self.assertIn('RUNTIME_IMAGE_DIGEST="$(manifest_pin pins.runtimeImageDigest)"', source)
        self.assertIn('value = json.load(open(sys.argv[1], encoding="utf-8"))', source)
        self.assertNotIn('json.loads(open(sys.argv[1]', source)
        self.assertIn('G3_HERMES_COMMIT="114eabf9d807b659e36d767e4de46ca056297ccb"', source)
        self.assertIn('G3_HERMES_ROOT="${PLANE_G3_HERMES_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/../hermes-agent}"', source)
        self.assertIn('pin_external_tree hermes-g3 "${G3_HERMES_ROOT}" "${G3_HERMES_COMMIT}"', source)
        g3 = source[source.index("run_logged g3-prerequisite") :]
        self.assertIn('PLANE_HERMES_EXTERNAL_ROOT="${HERMES_ROOT}"', g3)
        self.assertIn('PLANE_G3_HERMES_PIN_ROOT="${G3_HERMES_ROOT}"', g3)
        self.assertIn('cross_mixed_hermes_roots', source)
        g3_source = (TOOLS / "verify-agent-g3.sh").read_text(encoding="utf-8")
        self.assertIn('HERMES_PIN_ROOT="${PLANE_G3_HERMES_PIN_ROOT:-${HERMES_ROOT}}"', g3_source)
        self.assertIn('pin_external_tree hermes-pin "${HERMES_PIN_ROOT}" "${HERMES_COMMIT}"', g3_source)


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
                lambda value: value["current"]["services"]["api"].update(
                    {"revision": value["previous"]["services"]["api"]["revision"]}
                ),
                "rollback_current_api_revision_mismatch",
            ),
            (
                "runtime-service-artifact",
                lambda value: value["current"]["services"]["agent-runtime"].update(
                    {"revision": value["previous"]["services"]["agent-runtime"]["revision"]}
                ),
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
                lambda value: value["current"]["services"]["api"].update(
                    {"artifactSourceRevision": value["previous"]["services"]["api"]["artifactSourceRevision"]}
                ),
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

    def test_rollback_current_and_previous_provenance_cannot_be_cross_mixed(self):
        fixture_path = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        mutations = (
            (
                "current-uses-previous-api-digest",
                lambda value: value["current"]["services"]["api"].update(
                    {"imageDigest": value["previous"]["services"]["api"]["imageDigest"]}
                ),
                "rollback_current_api_imageDigest_mismatch",
            ),
            (
                "previous-uses-current-api-digest",
                lambda value: value["previous"]["services"]["api"].update(
                    {"imageDigest": value["current"]["services"]["api"]["imageDigest"]}
                ),
                "rollback_previous_api_imageDigest_mismatch",
            ),
            (
                "current-uses-previous-plane-commit",
                lambda value: value["current"].update({"planeCommit": value["previous"]["planeCommit"]}),
                "rollback_current_planeCommit_mismatch",
            ),
            (
                "previous-uses-current-plane-commit",
                lambda value: value["previous"].update({"planeCommit": value["current"]["planeCommit"]}),
                "rollback_previous_planeCommit_mismatch",
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

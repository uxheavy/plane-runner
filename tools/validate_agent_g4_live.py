#!/usr/bin/env python3
"""Validate the structured, candidate-bound G4 live-evaluation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BINDING_FIELDS = (
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
THRESHOLD_FIELDS = (
    "permittedSuccessRateMin",
    "deniedRejectionRateMin",
    "maxLatencyP95Ms",
    "maxErrorRate",
)
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_FIELD_RE = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|authorization|credential)\s*[\"']?\s*[:=]"
)
ROLLBACK_SERVICE_NAMES = ("api", "worker", "beat-worker", "supervisor", "agent-runtime")
ROLLBACK_MIGRATION = "db.0142_runtime_provider_attempts"
ROLLBACK_OPERATION_CONTRACT = "plane.operation/v1"
ROLLBACK_RUNTIME_CONTRACT = "plane.agent-runtime/v1"
PROVIDER_RELAY_PROTOCOL = "plane.agent-runtime/provider-relay/v1"
_CANONICAL_PROVIDER_RELAY = {
    "protocol": PROVIDER_RELAY_PROTOCOL,
    "transport": "AF_UNIX",
    "childNetworkPolicy": "none",
    "externalEgressOwner": "agent-runtime",
    "hostGatewaySeparate": True,
    "hermesHookStatus": "integrated",
}
MAX_EVIDENCE_BYTES = 16 * 1024
SAFE_CANARY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
PROVIDER_DESCRIPTOR_FIELDS = (
    "name",
    "model",
    "baseUrl",
    "host",
    "path",
    "credentialSource",
    "credentialRef",
    "credentialName",
)
EXPECTED_PROVIDER_DESCRIPTOR = {
    "name": "openai-codex",
    "model": "gpt-5.6-luna",
    "baseUrl": "https://chatgpt.com/backend-api/codex/responses",
    "host": "chatgpt.com",
    "path": "/backend-api/codex/responses",
    "credentialSource": "chatgpt-subscription",
    "credentialRef": "PLANE_G4_PROVIDER_SECRET_SOURCE",
    "credentialName": "api_key",
}
RUNTIME_PROVIDER_ENV_FIELDS = {
    "PLANE_AGENT_RUNTIME_PROVIDER": "name",
    "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "model",
    "PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL": "baseUrl",
    "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "host",
    "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "path",
    "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE": "credentialSource",
    "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF": "credentialRef",
    "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME": "credentialName",
}


def provider_relay_descriptor() -> dict[str, Any]:
    return dict(_CANONICAL_PROVIDER_RELAY)


def project_provider_relay(authority: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    relay = provider_relay_descriptor()
    authority["providerRelay"] = dict(relay)
    config["providerRelay"] = dict(relay)
    return relay


class ContractError(ValueError):
    """A safe, user-actionable contract failure."""


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name}_must_be_object")
    return value


def _required(obj: dict[str, Any], key: str, name: str) -> Any:
    if key not in obj:
        raise ContractError(f"{name}_missing_{key}")
    return obj[key]


def _exact(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise ContractError(f"{name}_mismatch")


def _bool(obj: dict[str, Any], key: str, name: str, expected: bool) -> None:
    value = _required(obj, key, name)
    if type(value) is not bool or value is not expected:
        raise ContractError(f"{name}_{key}_must_be_{str(expected).lower()}")


def _number(obj: dict[str, Any], key: str, name: str) -> float:
    value = _required(obj, key, name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name}_{key}_must_be_number")
    return float(value)


def _git_sha(value: Any, name: str) -> None:
    if not isinstance(value, str) or not GIT_RE.fullmatch(value):
        raise ContractError(f"{name}_must_be_git_sha")


def _hash(value: Any, name: str) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ContractError(f"{name}_must_be_sha256_hash")


def _digest(value: Any, name: str) -> None:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise ContractError(f"{name}_must_be_sha256_digest")


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{name}_malformed_json") from exc
    return _object(value, name)


def _parse_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{name}_must_be_datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name}_must_be_datetime") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{name}_must_have_timezone")
    return parsed.astimezone(timezone.utc)


def exact_binding(manifest: dict[str, Any], candidate: str) -> dict[str, Any]:
    candidate_binding = _object(_required(manifest, "candidateBinding", "manifest"), "candidateBinding")
    g3 = _required(candidate_binding, "acceptedG3Baseline", "candidateBinding")
    parent = _required(candidate_binding, "parentCommit", "candidateBinding")
    _git_sha(g3, "candidateBinding_acceptedG3Baseline")
    _git_sha(parent, "candidateBinding_parentCommit")
    _git_sha(candidate, "candidateCommit")
    pins = _object(_required(manifest, "pins", "manifest"), "manifest_pins")
    binding = {
        "candidateCommit": candidate,
        "g3Baseline": g3,
        "hermesCommit": _required(pins, "hermesCommit", "manifest_pins"),
        "mcpGitlink": _required(pins, "mcpGitlink", "manifest_pins"),
        "sdkGitlink": _required(pins, "sdkGitlink", "manifest_pins"),
        "runtimeImageTag": _required(pins, "runtimeImageTag", "manifest_pins"),
        "runtimeImageDigest": _required(pins, "runtimeImageDigest", "manifest_pins"),
        "runtimeImageRevision": _required(pins, "runtimeImageRevision", "manifest_pins"),
        "runtimeContract": _required(pins, "runtimeContract", "manifest_pins"),
        "apiArtifact": _object(_required(pins, "apiArtifact", "manifest_pins"), "manifest_apiArtifact"),
    }
    if set(binding["apiArtifact"]) != {"imageTag", "imageDigest", "sourceRevision", "contract"}:
        raise ContractError("manifest_apiArtifact_fields_mismatch")
    for key in BINDING_FIELDS:
        if key == "runtimeImageDigest":
            _digest(binding[key], f"manifest_{key}")
        elif key in {"runtimeImageTag", "runtimeContract"}:
            if not isinstance(binding[key], str) or not binding[key]:
                raise ContractError(f"manifest_{key}_invalid")
        elif key != "apiArtifact":
            _git_sha(binding[key], f"manifest_{key}")
    api_artifact = binding["apiArtifact"]
    _digest(api_artifact["imageDigest"], "manifest_apiArtifact_imageDigest")
    _git_sha(api_artifact["sourceRevision"], "manifest_apiArtifact_sourceRevision")
    for field in ("imageTag", "contract"):
        if not isinstance(api_artifact[field], str) or not api_artifact[field]:
            raise ContractError(f"manifest_apiArtifact_{field}_invalid")
    return binding


def validate_disposable_artifact_binding(manifest: dict[str, Any], candidate: str) -> None:
    """Require a disposable manifest to bind API and runtime to one source."""

    value = manifest.get("disposableBinding")
    if value is None:
        return
    binding = _object(value, "manifest_disposableBinding")
    required = {
        "mode",
        "candidateCommit",
        "apiSourceRevision",
        "runtimeRevision",
        "hermesCommit",
        "hermesRemote",
        "runtimeSourceDigest",
        "runtimeFiles",
    }
    source_fields = {
        "hermesSourceKind",
        "hermesDonorImage",
        "hermesDonorDigest",
        "hermesTreeDigest",
    }
    if set(binding) not in (required, required | source_fields):
        raise ContractError("manifest_disposableBinding_fields_mismatch")
    _exact(binding["mode"], "exact-api-runtime-candidate", "manifest_disposableBinding_mode")
    _exact(binding["candidateCommit"], candidate, "manifest_disposableBinding_candidateCommit")
    _git_sha(candidate, "manifest_disposableBinding_candidateCommit")
    _exact(binding["apiSourceRevision"], candidate, "manifest_disposableBinding_apiSourceRevision")
    _exact(binding["runtimeRevision"], candidate, "manifest_disposableBinding_runtimeRevision")
    _git_sha(binding["apiSourceRevision"], "manifest_disposableBinding_apiSourceRevision")
    _git_sha(binding["runtimeRevision"], "manifest_disposableBinding_runtimeRevision")

    pins = _object(_required(manifest, "pins", "manifest"), "manifest_pins")
    _exact(binding["hermesCommit"], _required(pins, "hermesCommit", "manifest_pins"), "manifest_disposableBinding_hermesCommit")
    _git_sha(binding["hermesCommit"], "manifest_disposableBinding_hermesCommit")
    _exact(binding["hermesRemote"], "github.com/uxheavy/hermes-agent", "manifest_disposableBinding_hermesRemote")
    _hash(binding["runtimeSourceDigest"], "manifest_disposableBinding_runtimeSourceDigest")

    files = _object(binding["runtimeFiles"], "manifest_disposableBinding_runtimeFiles")
    if not files:
        raise ContractError("manifest_disposableBinding_runtimeFiles_empty")
    for relative, digest in files.items():
        if (
            not isinstance(relative, str)
            or not relative.startswith("apps/api/plane/agent/runtime/")
            or relative.endswith((".pyc", ".pyo"))
            or "/__pycache__/" in relative
        ):
            raise ContractError("manifest_disposableBinding_runtimeFile_path_invalid")
        _hash(digest, "manifest_disposableBinding_runtimeFile_sha256")
    calculated = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    _exact(calculated, binding["runtimeSourceDigest"], "manifest_disposableBinding_runtimeSourceDigest")

    if source_fields.issubset(binding):
        source_kind = binding["hermesSourceKind"]
        donor_image = binding["hermesDonorImage"]
        donor_digest = binding["hermesDonorDigest"]
        tree_digest = binding["hermesTreeDigest"]
        if source_kind not in {"git-checkout", "sealed-image"}:
            raise ContractError("manifest_disposableBinding_hermesSourceKind_invalid")
        _hash(tree_digest, "manifest_disposableBinding_hermesTreeDigest")
        if source_kind == "sealed-image":
            if not isinstance(donor_image, str) or not donor_image:
                raise ContractError("manifest_disposableBinding_hermesDonorImage_missing")
            if (
                not isinstance(donor_digest, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", donor_digest)
            ):
                raise ContractError("manifest_disposableBinding_hermesDonorDigest_invalid")
        elif donor_image or donor_digest:
            raise ContractError("manifest_disposableBinding_hermesSource_mixed")

    expected = exact_binding(manifest, candidate)
    _exact(expected["runtimeImageRevision"], candidate, "manifest_disposableBinding_pin_runtimeRevision")
    _exact(expected["apiArtifact"]["sourceRevision"], candidate, "manifest_disposableBinding_pin_apiSourceRevision")
    _exact(expected["hermesCommit"], binding["hermesCommit"], "manifest_disposableBinding_pin_hermesCommit")


def _commit_parents(repo_root: Path, candidate: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-list", "--parents", "-n", "1", candidate],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ContractError("candidate_parent_lookup_failed")
    values = result.stdout.strip().split()
    if not values or values[0] != candidate:
        raise ContractError("candidate_parent_lookup_invalid")
    return values[1:]


def validate_candidate_binding(manifest: dict[str, Any], candidate: str, repo_root: Path) -> None:
    """Bind the selected manifest to either the exact wrapper or a full disposable candidate."""

    candidate_binding = _object(_required(manifest, "candidateBinding", "manifest"), "candidateBinding")
    mode = _required(candidate_binding, "mode", "candidateBinding")
    disposable = manifest.get("disposableBinding")
    if mode == "exact-single-child":
        if disposable is not None:
            raise ContractError("exact_single_child_disposable_binding_unexpected")
        parent = _required(candidate_binding, "parentCommit", "candidateBinding")
        _git_sha(parent, "candidateBinding_parentCommit")
        if not candidate_has_exact_parent(_commit_parents(repo_root, candidate), parent):
            raise ContractError("candidate_is_not_exact_single_child")
        return
    if mode == "disposable-exact-candidate":
        if disposable is None:
            raise ContractError("disposable_binding_required")
        validate_disposable_artifact_binding(manifest, candidate)
        return
    raise ContractError("candidate_binding_mode_unsupported")


def validate_api_artifact_descriptor(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Fail closed when a selected API image is not the manifest-bound artifact."""

    required = {"imageTag", "imageDigest", "sourceRevision", "contract", "artifact"}
    if set(actual) != required:
        raise ContractError("api_artifact_descriptor_fields_mismatch")
    expected_artifact = expected["apiArtifact"]
    _exact(actual["imageTag"], expected_artifact["imageTag"], "api_artifact_imageTag")
    _exact(actual["imageDigest"], expected_artifact["imageDigest"], "api_artifact_imageDigest")
    _exact(actual["sourceRevision"], expected_artifact["sourceRevision"], "api_artifact_sourceRevision")
    _exact(actual["contract"], expected_artifact["contract"], "api_artifact_contract")
    _exact(actual["artifact"], "plane-agent-api-g4", "api_artifact_kind")
    _digest(actual["imageDigest"], "api_artifact_imageDigest")
    _git_sha(actual["sourceRevision"], "api_artifact_sourceRevision")


def candidate_has_exact_parent(candidate_parents: list[str], expected_parent: str) -> bool:
    """Return true only for a one-parent wrapper, never for a descendant."""

    return len(candidate_parents) == 1 and candidate_parents[0] == expected_parent


def _git_text_at(root: Path, commit: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ContractError(f"rollback_accepted_evidence_missing_{relative.replace('/', '_')}")
    return result.stdout


def _shell_assignment(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}=\"([^\"]+)\"$", text, re.MULTILINE)
    if match is None:
        raise ContractError(f"rollback_accepted_evidence_missing_{name}")
    return match.group(1)


def _rollback_services(section: Any, name: str) -> dict[str, dict[str, str]]:
    services = _object(_required(_object(section, name), "services", name), f"{name}_services")
    if set(services) != set(ROLLBACK_SERVICE_NAMES):
        raise ContractError(f"rollback_{name}_services_mismatch")
    result: dict[str, dict[str, str]] = {}
    for service in ROLLBACK_SERVICE_NAMES:
        row = _object(services[service], f"{name}_{service}")
        if set(row) != {"revision", "imageDigest", "artifactKind", "artifactSourceRevision", "contract"}:
            raise ContractError(f"rollback_{name}_{service}_fields_mismatch")
        result[service] = {
            "revision": _required(row, "revision", f"{name}_{service}"),
            "imageDigest": _required(row, "imageDigest", f"{name}_{service}"),
            "artifactKind": _required(row, "artifactKind", f"{name}_{service}"),
            "artifactSourceRevision": _required(row, "artifactSourceRevision", f"{name}_{service}"),
            "contract": _required(row, "contract", f"{name}_{service}"),
        }
    return result


def _rollback_exact(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise ContractError(f"rollback_{name}_mismatch")


def validate_rollback_runbook(runbook_text: str, manifest: dict[str, Any], fixture: dict[str, Any]) -> None:
    """Require executable rollback instructions to use the bound pin set."""

    candidate_binding = _object(_required(manifest, "candidateBinding", "manifest"), "candidateBinding")
    pins = _object(_required(manifest, "pins", "manifest"), "manifest_pins")
    current = _object(_required(fixture, "current", "rollback"), "rollback_current")
    previous = _object(_required(fixture, "previous", "rollback"), "rollback_previous")
    current_parent = _required(candidate_binding, "parentCommit", "candidateBinding")
    g3_baseline = _required(candidate_binding, "acceptedG3Baseline", "candidateBinding")
    current_runtime = _object(_required(current, "runtime", "rollback_current"), "rollback_current_runtime")
    current_api = _object(_required(current, "apiArtifact", "rollback_current"), "rollback_current_apiArtifact")
    required = (
        "current Plane deployable service candidate is the exact",
        f"`{current_parent}`",
        "previously accepted G3",
        "candidate is Plane commit",
        f"`{g3_baseline}`",
        "Hermes commit",
        f"`{pins['hermesCommit']}`",
        "MCP gitlink",
        f"`{pins['mcpGitlink']}`",
        "SDK gitlink",
        f"`{pins['sdkGitlink']}`",
        "runtime image tag",
        f"`{pins['runtimeImageTag']}`",
        "runtime image digest",
        f"`{pins['runtimeImageDigest']}`",
        "runtime revision",
        f"`{pins['runtimeImageRevision']}`",
        "Plane service revision above is",
        "runtime image/runtimeRevision source",
        "runtime",
        "contract",
        f"`{pins['runtimeContract']}`",
        "API image tag",
        f"`{pins['apiArtifact']['imageTag']}`",
        "API image digest",
        f"`{pins['apiArtifact']['imageDigest']}`",
        "API source revision",
        f"`{pins['apiArtifact']['sourceRevision']}`",
        "API contract",
        f"`{pins['apiArtifact']['contract']}`",
        "artifactKind",
        "artifactSourceRevision",
        "only the standalone `agent-runtime` service uses the typed runtime",
        "previous services use immutable image digest",
        f"`{previous['services']['api']['imageDigest']}`",
        "python3 tools/agent-g4-rollback-drill.py",
        f"Migration `{ROLLBACK_MIGRATION}`",
        "keep the database at leaf `0142`",
        "never reverse to `0141`",
    )
    for marker in required:
        if marker not in runbook_text:
            raise ContractError(f"rollback_runbook_missing_{marker.replace(' ', '_')}")
    for stale in (
        "5f7e27f969b54ab94f0c6a6da9ea6feca27b7e32",
        "6c5ad927b2e31e3d1cd608fc89fbb8a308cc9809",
    ):
        if stale in runbook_text:
            raise ContractError("rollback_runbook_stale_pin_present")
    _rollback_exact(current_runtime["imageDigest"], pins["runtimeImageDigest"], "current_runtime_imageDigest")
    _rollback_exact(current_api, pins["apiArtifact"], "current_apiArtifact")


def validate_rollback_fixture(fixture_path: Path, root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Bind the disposable rollback fixture to G4 pins and accepted G3 evidence."""

    fixture = _read_json(fixture_path, "rollback")
    binding = _object(_required(manifest, "rollbackBinding", "manifest"), "rollbackBinding")
    _exact(
        binding,
        {
            "fixture": "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json",
            "currentParentField": "candidateBinding.parentCommit",
            "acceptedBaselineField": "candidateBinding.acceptedG3Baseline",
            "acceptedEvidence": "tools/verify-agent-g3.sh",
            "services": list(ROLLBACK_SERVICE_NAMES),
            "artifactKindField": "services.<service>.artifactKind",
            "artifactSourceRevisionField": "services.<service>.artifactSourceRevision",
        },
        "manifest_rollbackBinding",
    )
    candidate_binding = _object(_required(manifest, "candidateBinding", "manifest"), "candidateBinding")
    pins = _object(_required(manifest, "pins", "manifest"), "manifest_pins")
    current = _object(_required(fixture, "current", "rollback"), "rollback_current")
    previous = _object(_required(fixture, "previous", "rollback"), "rollback_previous")
    current_parent = _required(candidate_binding, "parentCommit", "candidateBinding")
    g3_baseline = _required(candidate_binding, "acceptedG3Baseline", "candidateBinding")
    _rollback_exact(_required(current, "planeCommit", "rollback_current"), current_parent, "current_planeCommit")
    _rollback_exact(_required(previous, "planeCommit", "rollback_previous"), g3_baseline, "previous_planeCommit")
    _rollback_exact(_required(current, "migrationLeaf", "rollback_current"), ROLLBACK_MIGRATION, "current_migrationLeaf")
    _rollback_exact(_required(previous, "migrationLeaf", "rollback_previous"), ROLLBACK_MIGRATION, "previous_migrationLeaf")

    _rollback_exact(
        _required(current, "runtime", "rollback_current"),
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
    _rollback_exact(
        _required(current, "apiArtifact", "rollback_current"),
        pins["apiArtifact"],
        "current_apiArtifact",
    )

    current_services = _rollback_services(current, "rollback_current")
    previous_services = _rollback_services(previous, "rollback_previous")
    expected_contracts = {
        service: ROLLBACK_RUNTIME_CONTRACT if service in {"supervisor", "agent-runtime"} else ROLLBACK_OPERATION_CONTRACT
        for service in ROLLBACK_SERVICE_NAMES
    }
    current_artifacts = {
        service: ("api", pins["apiArtifact"]["imageDigest"], pins["apiArtifact"]["sourceRevision"])
        for service in ("api", "worker", "beat-worker", "supervisor")
    }
    current_artifacts["agent-runtime"] = ("runtime", pins["runtimeImageDigest"], pins["runtimeImageRevision"])
    for service in ROLLBACK_SERVICE_NAMES:
        artifact_kind, artifact_digest, artifact_source_revision = current_artifacts[service]
        _rollback_exact(current_services[service]["revision"], artifact_source_revision, f"current_{service}_revision")
        _rollback_exact(current_services[service]["artifactKind"], artifact_kind, f"current_{service}_artifactKind")
        _rollback_exact(
            current_services[service]["artifactSourceRevision"],
            artifact_source_revision,
            f"current_{service}_artifactSourceRevision",
        )
        _rollback_exact(current_services[service]["imageDigest"], artifact_digest, f"current_{service}_imageDigest")
        _rollback_exact(current_services[service]["contract"], expected_contracts[service], f"current_{service}_contract")

    evidence = _git_text_at(root, g3_baseline, binding["acceptedEvidence"])
    accepted_g3 = {
        "hermesCommit": _shell_assignment(evidence, "HERMES_COMMIT"),
        "mcpGitlink": _shell_assignment(evidence, "MCP_COMMIT"),
        "sdkGitlink": _shell_assignment(evidence, "SDK_COMMIT"),
        "imageDigest": _shell_assignment(evidence, "API_TEST_IMAGE_DIGEST"),
    }
    previous_api = _object(_required(previous, "apiArtifact", "rollback_previous"), "rollback_previous_apiArtifact")
    _rollback_exact(
        previous_api,
        {
            "imageTag": "plane-g3-external-client-api-tests:prepared",
            "imageDigest": accepted_g3["imageDigest"],
            "sourceRevision": g3_baseline,
            "contract": ROLLBACK_OPERATION_CONTRACT,
        },
        "previous_api",
    )
    # Hermes is part of the runtime image and may advance for a candidate
    # while rollback still targets the immutable accepted-G3 service image.
    # The accepted G3 Hermes value remains evidence for that previous image;
    # only shared client gitlinks must remain equal across the two bindings.
    for key in ("mcpGitlink", "sdkGitlink"):
        _rollback_exact(accepted_g3[key], pins[key], f"accepted_g3_{key}")
    for service in ROLLBACK_SERVICE_NAMES:
        _rollback_exact(previous_services[service]["revision"], g3_baseline, f"previous_{service}_revision")
        _rollback_exact(previous_services[service]["artifactKind"], "api", f"previous_{service}_artifactKind")
        _rollback_exact(
            previous_services[service]["artifactSourceRevision"],
            g3_baseline,
            f"previous_{service}_artifactSourceRevision",
        )
        _rollback_exact(previous_services[service]["imageDigest"], accepted_g3["imageDigest"], f"previous_{service}_imageDigest")
        _rollback_exact(previous_services[service]["contract"], expected_contracts[service], f"previous_{service}_contract")

    strategy = _object(_required(fixture, "strategy", "rollback"), "rollback_strategy")
    _rollback_exact(strategy.get("migration"), ROLLBACK_MIGRATION, "strategy_migration")
    _rollback_exact(strategy.get("reverseMigrationAllowed"), False, "strategy_reverseMigrationAllowed")
    runbook_text = (root / _required(manifest, "runbook", "manifest")).read_text(encoding="utf-8")
    validate_rollback_runbook(runbook_text, manifest, fixture)
    return {"current": current, "previous": previous, "acceptedG3": accepted_g3}


def offline_evidence_sha256(path: Path) -> str:
    """Compute the canonical digest for a committed offline evidence file."""

    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise ContractError("offline_evidence_file_unreadable") from exc
    return hashlib.sha256(contents).hexdigest()


def offline_evidence_hashes(manifest: dict[str, Any], root: Path) -> dict[str, str]:
    """Materialize committed offline evidence digests through the validator owner."""

    entries = _object(_required(manifest, "offlineEvidence", "manifest"), "manifest_offlineEvidence")
    hashes: dict[str, str] = {}
    for name, value in entries.items():
        evidence = _object(value, f"offline_evidence_{name}")
        relative = _required(evidence, "path", f"offline_evidence_{name}")
        if not isinstance(relative, str) or not relative:
            raise ContractError(f"offline_evidence_{name}_path_invalid")
        path = root / relative
        if not path.is_file():
            raise ContractError(f"offline_evidence_{name}_missing")
        hashes[name] = offline_evidence_sha256(path)
    return hashes


def validate_offline_evidence(manifest: dict[str, Any], root: Path) -> dict[str, str]:
    """Require every manifest digest to equal its exact committed evidence bytes."""

    entries = _object(_required(manifest, "offlineEvidence", "manifest"), "manifest_offlineEvidence")
    actual_hashes = offline_evidence_hashes(manifest, root)
    for name, value in entries.items():
        evidence = _object(value, f"offline_evidence_{name}")
        expected = _required(evidence, "sha256", f"offline_evidence_{name}")
        _hash(expected, f"offline_evidence_{name}_sha256")
        _exact(actual_hashes[name], expected, f"offline_evidence_{name}_sha256")
        test_path_value = _required(evidence, "testPath", f"offline_evidence_{name}")
        if not isinstance(test_path_value, str) or not test_path_value:
            raise ContractError(f"offline_evidence_{name}_testPath_invalid")
        test_path = root / "apps/api" / test_path_value
        if not test_path.is_file():
            raise ContractError(f"offline_evidence_{name}_test_missing")
        text = test_path.read_text(encoding="utf-8")
        if "testName" in evidence:
            test_name = evidence["testName"]
            if not isinstance(test_name, str) or f"def {test_name}" not in text:
                raise ContractError(f"offline_evidence_{name}_test_missing_{test_name}")
        for marker in evidence.get("requiredMarkers", []):
            if marker not in text:
                raise ContractError(f"offline_evidence_{name}_marker_missing_{marker}")
    return actual_hashes


def _thresholds(value: Any, name: str) -> dict[str, float]:
    thresholds = _object(value, name)
    if set(thresholds) != set(THRESHOLD_FIELDS):
        raise ContractError(f"{name}_fields_mismatch")
    parsed = {key: _number(thresholds, key, name) for key in THRESHOLD_FIELDS}
    if not 0 <= parsed["permittedSuccessRateMin"] <= 1:
        raise ContractError(f"{name}_permitted_success_threshold_invalid")
    if not 0 <= parsed["deniedRejectionRateMin"] <= 1:
        raise ContractError(f"{name}_denied_rejection_threshold_invalid")
    if parsed["maxLatencyP95Ms"] < 0 or not 0 <= parsed["maxErrorRate"] <= 1:
        raise ContractError(f"{name}_threshold_invalid")
    return parsed


def _provider(value: Any, name: str) -> dict[str, str]:
    provider = _object(value, name)
    if set(provider) != set(PROVIDER_DESCRIPTOR_FIELDS):
        raise ContractError(f"{name}_fields_mismatch")
    result = {key: _required(provider, key, name) for key in PROVIDER_DESCRIPTOR_FIELDS}
    if any(not isinstance(item, str) or not item for item in result.values()):
        raise ContractError(f"{name}_invalid")
    _exact(result, EXPECTED_PROVIDER_DESCRIPTOR, f"{name}_policy")
    return result


def validate_runtime_provider_environment(provider: dict[str, str], environment: dict[str, str]) -> None:
    """Require runtime argv/env provider identity to equal the authority descriptor."""

    for environment_key, provider_key in RUNTIME_PROVIDER_ENV_FIELDS.items():
        if environment.get(environment_key) != provider[provider_key]:
            raise ContractError(f"runtime_provider_{provider_key}_mismatch")


def _provider_relay(value: Any, name: str) -> dict[str, Any]:
    relay = _object(value, name)
    required = {
        "protocol",
        "transport",
        "childNetworkPolicy",
        "externalEgressOwner",
        "hostGatewaySeparate",
        "hermesHookStatus",
    }
    if set(relay) != required:
        raise ContractError(f"{name}_fields_mismatch")
    _exact(relay["protocol"], PROVIDER_RELAY_PROTOCOL, f"{name}_protocol")
    _exact(relay["transport"], "AF_UNIX", f"{name}_transport")
    _exact(relay["childNetworkPolicy"], "none", f"{name}_child_network_policy")
    _exact(relay["externalEgressOwner"], "agent-runtime", f"{name}_egress_owner")
    _exact(relay["hostGatewaySeparate"], True, f"{name}_host_gateway_separate")
    if relay["hermesHookStatus"] not in {"pending", "integrated"}:
        raise ContractError(f"{name}_hook_status_invalid")
    return relay


def _canaries(value: Any, name: str) -> dict[str, dict[str, str]]:
    canaries = _object(value, name)
    if set(canaries) != {"permitted", "denied"}:
        raise ContractError(f"{name}_fields_mismatch")
    result: dict[str, dict[str, str]] = {}
    for key, expected_status in (("permitted", "allowed"), ("denied", "denied")):
        row = _object(canaries[key], f"{name}_{key}")
        if set(row) != {"id", "expectedStatus"} or row["expectedStatus"] != expected_status:
            raise ContractError(f"{name}_{key}_invalid")
        if not isinstance(row["id"], str) or not SAFE_CANARY_ID_RE.fullmatch(row["id"]):
            raise ContractError(f"{name}_{key}_id_invalid")
        result[key] = {"id": row["id"], "expectedStatus": expected_status}
    return result


def validate_authority(
    authority: dict[str, Any],
    manifest: dict[str, Any],
    candidate: str,
    expected_candidate: str,
    command: str,
    repo_root: Path | None = None,
    *,
    require_provider_relay: bool = False,
) -> dict[str, Any]:
    _git_sha(expected_candidate, "expectedCandidate")
    _exact(candidate, expected_candidate, "candidate_expected")
    _exact(_required(authority, "schemaVersion", "authority"), "plane-agent-g4/live-authority/v1", "authority_schema")
    _exact(_required(authority, "expectedCandidate", "authority"), expected_candidate, "authority_expected_candidate")
    _exact(_required(authority, "purpose", "authority"), "g4-live-evaluation", "authority_purpose")
    authority_id = _required(authority, "authorityId", "authority")
    if not isinstance(authority_id, str) or not SAFE_CANARY_ID_RE.fullmatch(authority_id):
        raise ContractError("authority_id_invalid")
    issued = _parse_time(_required(authority, "issuedAt", "authority"), "authority_issuedAt")
    expires = _parse_time(_required(authority, "expiresAt", "authority"), "authority_expiresAt")
    if expires <= issued or expires <= datetime.now(timezone.utc):
        raise ContractError("authority_expired_or_invalid_window")
    _bool(authority, "fallbackAllowed", "authority", False)
    binding = _object(_required(authority, "binding", "authority"), "authority_binding")
    expected = exact_binding(manifest, candidate)
    if repo_root is None:
        # Pure contract callers use synthetic commits. The real runner passes a
        # repository root during config-only preflight so Git ancestry is
        # checked before credentials, Docker, or provider access.
        validate_disposable_artifact_binding(manifest, candidate)
    else:
        validate_candidate_binding(manifest, candidate, repo_root)
    for key in BINDING_FIELDS:
        _exact(_required(binding, key, "authority_binding"), expected[key], f"authority_{key}")
    command_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()
    _exact(_required(binding, "commandSha256", "authority_binding"), command_hash, "authority_command")
    _hash(command_hash, "authority_command")
    _provider(_required(binding, "provider", "authority_binding"), "authority_provider")
    threshold_profile = _required(binding, "thresholdProfile", "authority_binding")
    if not isinstance(threshold_profile, str) or not threshold_profile:
        raise ContractError("authority_threshold_profile_invalid")
    thresholds = _thresholds(_required(binding, "thresholds", "authority_binding"), "authority_thresholds")
    canaries = _canaries(_required(binding, "canaries", "authority_binding"), "authority_canaries")
    provider_relay = _provider_relay(authority["providerRelay"], "authority_provider_relay") if "providerRelay" in authority else None
    if require_provider_relay and provider_relay is None:
        raise ContractError("authority_provider_relay_missing")
    if require_provider_relay and provider_relay != provider_relay_descriptor():
        raise ContractError("authority_provider_relay_policy_mismatch")
    return {
        "authorityId": authority_id,
        "binding": binding,
        "provider": _provider(binding["provider"], "authority_provider"),
        "thresholdProfile": threshold_profile,
        "thresholds": thresholds,
        "canaries": canaries,
        "providerRelay": provider_relay,
    }


def validate_config(
    config: dict[str, Any],
    authority_info: dict[str, Any],
    command: str,
    *,
    require_provider_relay: bool = False,
) -> None:
    _exact(_required(config, "schemaVersion", "config"), "plane-agent-g4/live-config/v1", "config_schema")
    _exact(_required(config, "authorityId", "config"), authority_info["authorityId"], "config_authority")
    _exact(_required(config, "mode", "config"), "live", "config_mode")
    _bool(config, "offline", "config", False)
    _bool(config, "fallbackAllowed", "config", False)
    _exact(_required(config, "expectedCandidate", "config"), authority_info["binding"]["candidateCommit"], "config_expected_candidate")
    if _required(config, "requiredReadbacks", "config") != ["audit", "version"]:
        raise ContractError("config_readbacks_mismatch")
    if config.get("fallbackProviders", []) != []:
        raise ContractError("config_fallback_providers_present")
    binding = _object(_required(config, "binding", "config"), "config_binding")
    _exact(binding, authority_info["binding"], "config_binding")
    config_provider_relay = _provider_relay(config["providerRelay"], "config_provider_relay") if "providerRelay" in config else None
    if require_provider_relay and config_provider_relay is None:
        raise ContractError("config_provider_relay_missing")
    _exact(config_provider_relay, authority_info["providerRelay"], "config_provider_relay")
    if require_provider_relay and config_provider_relay != provider_relay_descriptor():
        raise ContractError("config_provider_relay_policy_mismatch")
    _exact(_required(config, "provider", "config"), {**authority_info["provider"], "fallbackUsed": False}, "config_provider")
    _exact(_required(config, "thresholdProfile", "config"), authority_info["thresholdProfile"], "config_threshold_profile")
    _exact(_required(config, "thresholds", "config"), authority_info["thresholds"], "config_thresholds")
    expected_canaries = {key: row["id"] for key, row in authority_info["canaries"].items()}
    _exact(_required(config, "canaries", "config"), expected_canaries, "config_canaries")
    _exact(hashlib.sha256(command.encode("utf-8")).hexdigest(), authority_info["binding"]["commandSha256"], "config_command")


def _summary(summary: Any, name: str) -> dict[str, Any]:
    summary_obj = _object(summary, name)
    counts = _object(_required(summary_obj, "counts", name), f"{name}_counts")
    required_counts = ("collected", "passed", "failed", "skipped", "xfail", "deselected")
    if set(counts) != set(required_counts):
        raise ContractError(f"{name}_counts_fields_mismatch")
    parsed_counts: dict[str, int] = {}
    for key in required_counts:
        value = _required(counts, key, f"{name}_counts")
        if type(value) is not int or value < 0:
            raise ContractError(f"{name}_{key}_must_be_nonnegative_integer")
        parsed_counts[key] = value
    if parsed_counts["collected"] < 1 or parsed_counts["passed"] != parsed_counts["collected"]:
        raise ContractError(f"{name}_counts_not_all_passed")
    for key in ("failed", "skipped", "xfail", "deselected"):
        if parsed_counts[key] != 0:
            raise ContractError(f"{name}_{key}_must_be_zero")
    duration = _number(summary_obj, "durationMs", name)
    if duration < 0:
        raise ContractError(f"{name}_duration_invalid")
    if not isinstance(_required(summary_obj, "migrationLeaf", name), str):
        raise ContractError(f"{name}_migration_leaf_invalid")
    _object(_required(summary_obj, "workload", name), f"{name}_workload")
    return {"counts": parsed_counts, "durationMs": duration}


_LIVE_OPERATION_IDS = (
    "search_workspace",
    "work_item.read",
    "catalog.search",
    "catalog.describe",
    "agent.outcome.evaluate",
    "agent.outcome.submit",
    "agent.outcome.publish",
)
_LIVE_RUNTIME_EVENT_KINDS = {
    "progress_observed",
    "conversation_publication_observed",
    "input_request_observed",
    "artifact_observed",
    "usage_observed",
    "outcome_submission_observed",
    "failure_observed",
    "blocker_observed",
    "transcript_evidence_observed",
}
_LIVE_OPERATION_STATUSES = {"success", "denied", "conflict", "unavailable", "absent"}
_LIVE_OPERATION_ERROR_CODES = {
    "NOT_AUTHORIZED",
    "IDEMPOTENCY_CONFLICT",
    "PLANE_CONFLICT",
    "OPERATION_UNAVAILABLE",
    "OUTCOME_UNKNOWN",
    "VALIDATION_ERROR",
    "OPERATION_REJECTED",
    "UPSTREAM_FAILURE",
}
_LIVE_ATTEMPT_PHASES = {"intent", "started", "completed", "failed", "outcome_unknown", "unknown"}
_LIVE_ATTEMPT_STATUS_CLASSES = {"", "not_sent", "unknown", "2xx", "4xx", "5xx"}
_LIVE_ATTEMPT_ERROR_CODES = {
    "",
    "pre_send_failure",
    "outcome_unknown",
    "provider_error",
    "runtime_error",
    "upstream_error",
    "unspecified",
}
_LIVE_PUBLICATION_REF_PREFIXES = {
    "productRef": "outcome-submission:",
    "operationAttemptRef": "operation-attempt:",
    "operationRef": "operation:",
    "applicationServiceRef": "application-service:",
    "gatewayReceiptRef": "gateway-receipt:",
    "receiptRef": "receipt:",
    "auditReceiptRef": "audit-receipt:",
    "productEventRef": "product-event:",
}
_LIVE_READBACK_FIELDS = {
    "audit",
    "version",
    "runtimeExit",
    "runtimeEventIngress",
    "providerAttempts",
    "planeOperationAudit",
    "transcriptEvidence",
    "explicitPublication",
    "replay",
}
_LIVE_TRANSCRIPT_STATUSES = {"observed", "not_observed"}
_LIVE_TRANSCRIPT_REQUIREMENTS = {"required", "not_required"}
_LIVE_TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "status",
    "authorityId",
    "semanticDigest",
    "s00Gate",
    "providerRelay",
    "binding",
    "provider",
    "canaries",
    "thresholds",
    "readback",
    "summary",
    "failure",
    "run",
    "invocation",
    "runtimeExit",
    "runtimeEventIngress",
    "providerAttempts",
    "terminal",
    "planeHostOperationReceipts",
    "planeOperationAudit",
    "scenario",
}
_LIVE_AUDIT_FIELDS = {"passed", "eventCount", "permittedOutcome", "deniedOutcome", "submitOutcome", "publishOutcome"}
_LIVE_VERSION_FIELDS = {"passed", "binding", "source"}
_LIVE_WORKLOAD_FIELDS = {
    "invocationRef",
    "runRef",
    "actorRef",
    "terminalEventRef",
    "terminalKind",
    "invocationState",
    "outcomeCount",
    "runtimeEventCount",
    "providerHttpStatusClass",
    "usage",
}
_LIVE_USAGE_KEYS = ("inputTokens", "outputTokens", "durationMs")
_LIVE_PERMITTED_READ_IDS = {"work_item.read", "catalog.search"}
_S00_GATE_PREDICATE_FIELDS = (
    ("invocation_succeeded", ("actual",)),
    ("run_succeeded", ("actual",)),
    ("one_visible_outcome_terminal", ("terminalCount", "outcomeCount", "terminalKind")),
    (
        "one_applied_outcome_publication",
        ("count", "action", "productKind", *_LIVE_PUBLICATION_REF_PREFIXES.keys(), "expectedProductRef"),
    ),
    (
        "terminal_binding",
        (
            "source",
            "terminalRunRef",
            "expectedRunRef",
            "outcomeRunRef",
            "terminalInvocationRef",
            "expectedInvocationRef",
            "terminalProductRef",
            "expectedOutcomeRef",
            "terminalProductEventRef",
            "publishedProductEventRef",
        ),
    ),
    ("runtime_exit_completed", ("kind", "hasFailure")),
)
_S00_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")


def _safe_ref(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _S00_SAFE_REF_RE.fullmatch(value):
        raise ContractError(f"{name}_invalid")
    if any(term in value.lower() for term in ("password", "secret", "token", "credential", "authorization", "api_key")):
        raise ContractError(f"{name}_sensitive")
    return value


def _validate_s00_gate(value: Any) -> None:
    gate = _object(value, "evidence_s00Gate")
    if list(gate) != ["status", "firstFailedPredicate", "predicates"]:
        raise ContractError("evidence_s00Gate_fields_invalid")
    if not isinstance(gate["status"], str) or gate["status"] not in {"passed", "failed"}:
        raise ContractError("evidence_s00Gate_status_invalid")
    first_failed = gate["firstFailedPredicate"]
    if first_failed is not None and (
        not isinstance(first_failed, str) or first_failed not in dict(_S00_GATE_PREDICATE_FIELDS)
    ):
        raise ContractError("evidence_s00Gate_first_failed_invalid")
    predicates = _object(gate["predicates"], "evidence_s00Gate_predicates")
    if list(predicates) != [name for name, _ in _S00_GATE_PREDICATE_FIELDS]:
        raise ContractError("evidence_s00Gate_predicate_order_invalid")

    expected_passed = {}
    for name, fields in _S00_GATE_PREDICATE_FIELDS:
        row = _object(predicates[name], f"evidence_s00Gate_{name}")
        expected_fields = ["passed", *fields]
        if list(row) != expected_fields:
            raise ContractError(f"evidence_s00Gate_{name}_fields_invalid")
        if type(row["passed"]) is not bool:
            raise ContractError(f"evidence_s00Gate_{name}_passed_invalid")
        for field in fields:
            if field in {"count", "terminalCount", "outcomeCount"}:
                if type(row[field]) is not int or not 0 <= row[field] <= 256:
                    raise ContractError(f"evidence_s00Gate_{name}_{field}_invalid")
            elif field == "hasFailure":
                if type(row[field]) is not bool:
                    raise ContractError(f"evidence_s00Gate_{name}_{field}_invalid")
            else:
                _safe_ref(row[field], f"evidence_s00Gate_{name}_{field}")

        if name in {"invocation_succeeded", "run_succeeded"}:
            expected_passed[name] = row["actual"] == "succeeded"
        elif name == "one_visible_outcome_terminal":
            expected_passed[name] = (
                row["terminalCount"] == 1
                and row["outcomeCount"] == 1
                and row["terminalKind"] == "outcome_submission"
            )
        elif name == "one_applied_outcome_publication":
            expected_passed[name] = (
                row["count"] == 1
                and row["action"] == "applied"
                and row["productKind"] == "outcome_submission"
                and all(row[field] != "unavailable" for field in _LIVE_PUBLICATION_REF_PREFIXES)
                and row["operationRef"] == "operation:agent.outcome.publish"
                and row["productRef"] == row["expectedProductRef"]
            )
        elif name == "terminal_binding":
            expected_passed[name] = (
                row["source"] == "runtime"
                and row["terminalRunRef"] == row["expectedRunRef"]
                and row["outcomeRunRef"] == row["expectedRunRef"]
                and row["terminalInvocationRef"] == row["expectedInvocationRef"]
                and row["terminalProductRef"] == row["expectedOutcomeRef"]
                and row["terminalProductEventRef"] == row["publishedProductEventRef"]
            )
        else:
            expected_passed[name] = row["kind"] == "completed" and row["hasFailure"] is False
        if row["passed"] is not expected_passed[name]:
            raise ContractError(f"evidence_s00Gate_{name}_predicate_mismatch")

    computed_first_failed = next((name for name in expected_passed if not expected_passed[name]), None)
    if first_failed != computed_first_failed:
        raise ContractError("evidence_s00Gate_first_failed_mismatch")
    if gate["status"] == "passed" and computed_first_failed is not None:
        raise ContractError("evidence_s00Gate_status_mismatch")
    if gate["status"] == "failed" and computed_first_failed is None:
        raise ContractError("evidence_s00Gate_status_mismatch")


def _semantic_digest(receipt: dict[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "semanticDigest"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


_SCENARIO_ACTOR_ROLES = {
    "worker": "worker",
    "manager": "delegator",
    "operator": "worker",
}
_SCENARIO_OUTCOMES = {"success", "denied", "not_observed"}


def _validate_scenario_projection(value: Any) -> None:
    scenario = _object(value, "evidence_scenario")
    required = {"id", "descriptorDigest", "schemaVersion", "actorRole", "profileName"}
    if set(scenario).difference(required | {"expected"}) or not required.issubset(scenario):
        raise ContractError("evidence_scenario_fields_invalid")
    scenario_id = scenario["id"]
    if scenario_id not in _SCENARIO_ACTOR_ROLES or scenario["actorRole"] != _SCENARIO_ACTOR_ROLES[scenario_id]:
        raise ContractError("evidence_scenario_identity_invalid")
    if not isinstance(scenario["descriptorDigest"], str) or not HASH_RE.fullmatch(scenario["descriptorDigest"]):
        raise ContractError("evidence_scenario_digest_invalid")
    _exact(scenario["schemaVersion"], "plane.agent-scenario/v1", "evidence_scenario_schema")
    if (
        not isinstance(scenario["profileName"], str)
        or not 1 <= len(scenario["profileName"].encode("utf-8")) <= 96
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,95}", scenario["profileName"])
    ):
        raise ContractError("evidence_scenario_profile_invalid")
    if "expected" not in scenario:
        return
    expected = _object(scenario["expected"], "evidence_scenario_expected")
    if set(expected) != {"operationOutcomes", "evidenceKinds"}:
        raise ContractError("evidence_scenario_expected_fields_invalid")
    operations = expected["operationOutcomes"]
    if not isinstance(operations, list) or len(operations) > 16:
        raise ContractError("evidence_scenario_expected_operations_invalid")
    for operation in operations:
        row = _object(operation, "evidence_scenario_expected_operation")
        if set(row) != {"operationId", "outcome"}:
            raise ContractError("evidence_scenario_expected_operation_fields_invalid")
        _safe_ref(row["operationId"], "evidence_scenario_expected_operation_id")
        if row["outcome"] not in _SCENARIO_OUTCOMES:
            raise ContractError("evidence_scenario_expected_operation_outcome_invalid")
    evidence_kinds = expected["evidenceKinds"]
    if (
        not isinstance(evidence_kinds, list)
        or len(evidence_kinds) > 16
        or any(not isinstance(kind, str) or not _S00_SAFE_REF_RE.fullmatch(kind) for kind in evidence_kinds)
    ):
        raise ContractError("evidence_scenario_expected_evidence_invalid")


def _validate_semantic_digest(evidence: dict[str, Any]) -> None:
    _hash(_required(evidence, "semanticDigest", "evidence"), "evidence_semantic_digest")
    _exact(evidence["semanticDigest"], _semantic_digest(evidence), "evidence_semantic_digest")


def _validate_receipt_common(
    evidence: dict[str, Any],
    authority_info: dict[str, Any],
    expected_binding: dict[str, Any],
    *,
    status: str,
) -> None:
    _exact(_required(evidence, "binding", "evidence"), expected_binding, "evidence_binding")
    _exact(_required(evidence, "authorityId", "evidence"), authority_info["authorityId"], "evidence_authority")
    if "scenario" in evidence:
        _validate_scenario_projection(evidence["scenario"])
    gate = _required(evidence, "s00Gate", "evidence")
    _validate_s00_gate(gate)
    if status == "passed" and (gate["status"] != "passed" or gate["firstFailedPredicate"] is not None):
        raise ContractError("evidence_s00Gate_success_failed")
    canaries = _object(_required(evidence, "canaries", "evidence"), "evidence_canaries")
    if list(canaries) != ["permitted", "denied"]:
        raise ContractError("evidence_canaries_fields_invalid")
    for key, expected_status in (("permitted", "allowed"), ("denied", "denied")):
        row = _object(canaries[key], f"evidence_canaries_{key}")
        if list(row) != ["id", "status", "passed"]:
            raise ContractError(f"evidence_canaries_{key}_fields_invalid")
        _exact(row["id"], authority_info["canaries"][key]["id"], f"evidence_canaries_{key}_id")
        if status == "passed":
            if row["status"] != expected_status or row["passed"] is not True:
                raise ContractError(f"evidence_{key}_canary_failed")
        elif row["status"] != "not_evaluated" or row["passed"] is not False:
            raise ContractError(f"evidence_{key}_canary_failed")


def _read_bounded_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ContractError("evidence_oversized")
        value = path.read_bytes()
    except ContractError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ContractError("evidence_unavailable") from exc
    if len(value) > MAX_EVIDENCE_BYTES:
        raise ContractError("evidence_oversized")
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("evidence_invalid_utf8") from exc


def _validate_live_readback(evidence: dict[str, Any]) -> None:
    if set(evidence) != _LIVE_READBACK_FIELDS:
        raise ContractError("evidence_readback_fields_invalid")
    attempts = _required(evidence, "providerAttempts", "evidence")
    if not isinstance(attempts, list) or not attempts or len(attempts) > 32:
        raise ContractError("evidence_provider_attempts_invalid")
    previous_sequence = 0
    for row in attempts:
        attempt = _object(row, "evidence_provider_attempt")
        if set(attempt) != {"sequence", "phase", "upstreamInitiated", "statusClass", "errorCode"}:
            raise ContractError("evidence_provider_attempt_fields_invalid")
        sequence = attempt["sequence"]
        if (
            type(sequence) is not int
            or not 1 <= sequence <= 256
            or sequence <= previous_sequence
            or attempt["phase"] not in _LIVE_ATTEMPT_PHASES
            or type(attempt["upstreamInitiated"]) is not bool
            or attempt["statusClass"] not in _LIVE_ATTEMPT_STATUS_CLASSES
            or attempt["errorCode"] not in _LIVE_ATTEMPT_ERROR_CODES
        ):
            raise ContractError("evidence_provider_attempt_sequence_invalid")
        previous_sequence = sequence
    if any(
        attempt["phase"] == "outcome_unknown" or attempt["errorCode"] == "outcome_unknown"
        for attempt in attempts
    ):
        raise ContractError("evidence_provider_attempt_outcome_unknown")

    runtime_exit = _object(_required(evidence, "runtimeExit", "evidence"), "evidence_runtime_exit")
    if (
        set(runtime_exit) != {"present", "kind", "finalSequence", "failure"}
        or runtime_exit["present"] is not True
        or runtime_exit["kind"] != "completed"
        or type(runtime_exit["finalSequence"]) is not int
        or not 0 <= runtime_exit["finalSequence"] <= 256
        or runtime_exit["failure"] is not None
    ):
        raise ContractError("evidence_runtime_exit_final_sequence_invalid")

    ingress = _object(_required(evidence, "runtimeEventIngress", "evidence"), "evidence_runtime_ingress")
    if set(ingress) != {"kindCounts"}:
        raise ContractError("evidence_runtime_ingress_fields_invalid")
    kind_counts = _object(_required(ingress, "kindCounts", "evidence_runtime_ingress"), "evidence_runtime_ingress_counts")
    if set(kind_counts).difference(_LIVE_RUNTIME_EVENT_KINDS) or any(
        type(count) is not int or not 0 <= count <= 256 for count in kind_counts.values()
    ):
        raise ContractError("evidence_runtime_ingress_invalid")

    audit = _required(evidence, "planeOperationAudit", "evidence")
    if not isinstance(audit, list) or len(audit) != len(_LIVE_OPERATION_IDS):
        raise ContractError("evidence_operation_audit_count_invalid")
    operation_rows = {}
    for operation_id, row in zip(_LIVE_OPERATION_IDS, audit):
        operation = _object(row, "evidence_operation_audit")
        if set(operation) != {"operationId", "status", "errorCode", "count"}:
            raise ContractError("evidence_operation_audit_fields_invalid")
        if (
            operation["operationId"] != operation_id
            or operation["status"] not in _LIVE_OPERATION_STATUSES
            or operation["errorCode"] is not None
            and operation["errorCode"] not in _LIVE_OPERATION_ERROR_CODES
            or type(operation["count"]) is not int
            or not 0 <= operation["count"] <= 8
        ):
            raise ContractError("evidence_operation_audit_invalid")
        operation_rows[operation_id] = operation
    if not any(
        operation_rows[operation_id]["status"] == "success"
        and operation_rows[operation_id]["errorCode"] is None
        and operation_rows[operation_id]["count"] >= 1
        for operation_id in _LIVE_PERMITTED_READ_IDS
    ):
        raise ContractError("evidence_permitted_read_success_missing")
    evaluate = operation_rows["agent.outcome.evaluate"]
    if evaluate["status"] != "denied" or evaluate["errorCode"] != "NOT_AUTHORIZED" or evaluate["count"] != 1:
        raise ContractError("evidence_evaluate_not_authorized_invalid")
    submit = operation_rows["agent.outcome.submit"]
    if submit["status"] != "success" or submit["errorCode"] is not None or submit["count"] != 1:
        raise ContractError("evidence_agent_outcome_submit_success_invalid")
    publish = operation_rows["agent.outcome.publish"]
    if publish["status"] != "success" or publish["errorCode"] is not None or publish["count"] < 1:
        raise ContractError("evidence_agent_outcome_publish_success_invalid")
    if not any(
        attempt["phase"] == "completed"
        and attempt["upstreamInitiated"] is True
        and attempt["statusClass"] == "2xx"
        and attempt["errorCode"] == ""
        for attempt in attempts
    ):
        raise ContractError("evidence_provider_attempt_success_missing")

    transcript = _object(_required(evidence, "transcriptEvidence", "evidence"), "evidence_transcript")
    if set(transcript) != {"status", "requirement", "count", "eventIds"}:
        raise ContractError("evidence_transcript_fields_invalid")
    event_ids = transcript["eventIds"]
    if (
        transcript["status"] not in _LIVE_TRANSCRIPT_STATUSES
        or transcript["requirement"] not in _LIVE_TRANSCRIPT_REQUIREMENTS
        or type(transcript["count"]) is not int
        or not 0 <= transcript["count"] <= 32
        or not isinstance(event_ids, list)
        or len(event_ids) != transcript["count"]
        or len(event_ids) > 32
        or any(not isinstance(event_id, str) or not re.fullmatch(r"event:[A-Za-z0-9][A-Za-z0-9._~/-]{0,119}", event_id) for event_id in event_ids)
    ):
        raise ContractError("evidence_transcript_invalid")
    if transcript["status"] == "observed" and transcript["count"] < 1:
        raise ContractError("evidence_transcript_status_invalid")
    if transcript["status"] == "not_observed" and transcript["count"] != 0:
        raise ContractError("evidence_transcript_status_invalid")

    publication = _object(_required(evidence, "explicitPublication", "evidence"), "evidence_publication")
    if set(publication) != {"count", "refs"}:
        raise ContractError("evidence_publication_fields_invalid")
    refs = publication["refs"]
    if (
        type(publication["count"]) is not int
        or publication["count"] != 1
        or not isinstance(refs, list)
        or len(refs) != publication["count"]
    ):
        raise ContractError("evidence_publication_invalid")
    for row in refs:
        value = _object(row, "evidence_publication_ref")
        if set(value) != set(_LIVE_PUBLICATION_REF_PREFIXES) or any(
            not isinstance(value[field], str)
            or len(value[field].encode("utf-8")) > 128
            or not value[field].startswith(prefix)
            or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value[field])
            for field, prefix in _LIVE_PUBLICATION_REF_PREFIXES.items()
        ):
            raise ContractError("evidence_publication_ref_invalid")
    if transcript["requirement"] == "not_required" and publication["count"] != 1:
        raise ContractError("evidence_transcript_requirement_invalid")
    if transcript["requirement"] == "required" and (
        transcript["count"] < 1 or kind_counts.get("transcript_evidence_observed", 0) < 1
    ):
        raise ContractError("evidence_transcript_observation_missing")

    replay = _object(_required(evidence, "replay", "evidence"), "evidence_replay")
    if set(replay) != {"status", "providerAccess", "sameInvocation", "sameIdempotencyKey", "new"}:
        raise ContractError("evidence_replay_fields_invalid")
    expected_new = {
        "children",
        "providerAttempts",
        "invocations",
        "receipts",
        "audits",
        "usage",
        "outcomes",
        "publications",
        "terminalEvents",
        "semanticSideEffects",
    }
    new = _object(_required(replay, "new", "evidence_replay"), "evidence_replay_new")
    if (
        replay["status"] != "passed"
        or replay["providerAccess"] != "disabled"
        or replay["sameInvocation"] is not True
        or replay["sameIdempotencyKey"] is not True
        or set(new) != expected_new
        or any(type(value) is not int or value != 0 for value in new.values())
    ):
        raise ContractError("evidence_replay_new_effect_invalid")


_FAILURE_TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "status",
    "binding",
    "authorityId",
    "canaries",
    "semanticDigest",
    "failure",
    "run",
    "invocation",
    "runtimeExit",
    "runtimeEventIngress",
    "providerAttempts",
    "terminal",
    "s00Gate",
    "planeHostOperationReceipts",
    "planeOperationAudit",
    "providerRelay",
    "scenario",
}
_FAILURE_REQUIRED_TOP_LEVEL_FIELDS = _FAILURE_TOP_LEVEL_FIELDS - {"providerRelay", "scenario"}
_FAILURE_STAGES = {
    "initialization",
    "compose",
    "audit-bootstrap",
    "runtime-start",
    "runtime-health",
    "api-invocation",
    "unknown",
}
_FAILURE_ERROR_CLASSES = {
    "CommandError",
    "ConnectionError",
    "FileNotFoundError",
    "ImportError",
    "ImproperlyConfigured",
    "ModuleNotFoundError",
    "OperationalError",
    "PermissionError",
    "RuntimeError",
    "TimeoutError",
    "unspecified",
}
_FAILURE_INVOCATION_STATES = {
    "queued",
    "running",
    "waiting_for_input",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "outcome_unknown",
    "unknown",
}
_FAILURE_TERMINAL_KINDS = {
    "none",
    "outcome_submission",
    "run_failure",
    "run_blocker",
    "run_cancellation",
    "unknown",
}


def _validate_failure_receipt(
    evidence: dict[str, Any],
    authority_info: dict[str, Any],
    expected_binding: dict[str, Any],
) -> None:
    if set(evidence).difference(_FAILURE_TOP_LEVEL_FIELDS) or not _FAILURE_REQUIRED_TOP_LEVEL_FIELDS.issubset(evidence):
        raise ContractError("evidence_failure_fields_invalid")
    _exact(evidence["schemaVersion"], "plane-agent-g4/live-failure/v1", "evidence_schema")
    _exact(evidence["status"], "failed", "evidence_status")
    _validate_receipt_common(evidence, authority_info, expected_binding, status="failed")

    failure = _object(evidence["failure"], "evidence_failure")
    required_failure_fields = {
        "phase",
        "errorClass",
        "exitCode",
        "reasonCode",
        "reasonPhase",
        "reasonDetail",
        "reasonSubreason",
    }
    host_failure_fields = {
        "operationId",
        "attemptRef",
        "receiptRef",
        "status",
        "errorCode",
        "codeModePhase",
    }
    if (
        set(failure).difference(required_failure_fields | {"reasonCause", "hostOperationFailure"})
        or not required_failure_fields.issubset(failure)
    ):
        raise ContractError("evidence_failure_fields_invalid")
    if failure["phase"] not in _FAILURE_STAGES or failure["errorClass"] not in _FAILURE_ERROR_CLASSES:
        raise ContractError("evidence_failure_classification_invalid")
    if type(failure["exitCode"]) is not int or not 1 <= failure["exitCode"] <= 255:
        raise ContractError("evidence_failure_exit_code_invalid")
    for field in ("reasonCode", "reasonPhase", "reasonDetail", "reasonSubreason", "reasonCause"):
        if field in failure:
            _safe_ref(failure[field], f"evidence_failure_{field}")
    if "hostOperationFailure" in failure:
        host_failure = _object(failure["hostOperationFailure"], "evidence_host_operation_failure")
        if set(host_failure) != host_failure_fields:
            raise ContractError("evidence_host_operation_failure_fields_invalid")
        if host_failure["status"] not in {"denied", "conflict", "unavailable", "invalid"}:
            raise ContractError("evidence_host_operation_failure_status_invalid")
        if host_failure["codeModePhase"] not in {"host_callback", "unavailable"}:
            raise ContractError("evidence_host_operation_failure_phase_invalid")
        for field in ("operationId", "attemptRef", "receiptRef", "errorCode"):
            _safe_ref(host_failure[field], f"evidence_host_operation_failure_{field}")

    for name in ("run", "invocation"):
        state = _object(evidence[name], f"evidence_{name}")
        if list(state) != ["present", "id", "state"]:
            raise ContractError(f"evidence_{name}_fields_invalid")
        if type(state["present"]) is not bool or state["state"] not in _FAILURE_INVOCATION_STATES:
            raise ContractError(f"evidence_{name}_invalid")
        if state["id"] is not None:
            _safe_ref(state["id"], f"evidence_{name}_id")

    runtime_exit = _object(evidence["runtimeExit"], "evidence_runtime_exit")
    if list(runtime_exit) != ["present", "kind", "finalSequence", "failure"]:
        raise ContractError("evidence_runtime_exit_fields_invalid")
    if type(runtime_exit["present"]) is not bool or runtime_exit["kind"] not in {
        "completed",
        "waiting_for_input",
        "failed",
        "blocked",
        "cancelled",
        "unknown",
    }:
        raise ContractError("evidence_runtime_exit_invalid")
    if runtime_exit["finalSequence"] is not None and (
        type(runtime_exit["finalSequence"]) is not int or not 0 <= runtime_exit["finalSequence"] <= 256
    ):
        raise ContractError("evidence_runtime_exit_sequence_invalid")
    if runtime_exit["failure"] is not None:
        runtime_failure = _object(runtime_exit["failure"], "evidence_runtime_exit_failure")
        if set(runtime_failure).difference({"code", "retryable", "cause"}) or not {
            "code",
            "retryable",
        }.issubset(runtime_failure):
            raise ContractError("evidence_runtime_exit_failure_fields_invalid")
        if runtime_failure["code"] not in {"budget_exhausted", "runtime_error", "unavailable"} or type(
            runtime_failure["retryable"]
        ) is not bool:
            raise ContractError("evidence_runtime_exit_failure_invalid")
        if "cause" in runtime_failure:
            _safe_ref(runtime_failure["cause"], "evidence_runtime_exit_failure_cause")

    ingress = _object(evidence["runtimeEventIngress"], "evidence_runtime_ingress")
    if list(ingress) != ["kindCounts"]:
        raise ContractError("evidence_runtime_ingress_fields_invalid")
    counts = _object(ingress["kindCounts"], "evidence_runtime_ingress_counts")
    if set(counts).difference(_LIVE_RUNTIME_EVENT_KINDS) or any(
        type(count) is not int or not 0 <= count <= 256 for count in counts.values()
    ):
        raise ContractError("evidence_runtime_ingress_invalid")

    attempts = evidence["providerAttempts"]
    if not isinstance(attempts, list) or len(attempts) > 32:
        raise ContractError("evidence_provider_attempts_invalid")
    previous_sequence = 0
    for row in attempts:
        attempt = _object(row, "evidence_provider_attempt")
        if set(attempt) != {"sequence", "phase", "upstreamInitiated", "statusClass", "errorCode"}:
            raise ContractError("evidence_provider_attempt_fields_invalid")
        if (
            type(attempt["sequence"]) is not int
            or not 0 <= attempt["sequence"] <= 256
            or attempt["sequence"] <= previous_sequence
            or attempt["phase"] not in _LIVE_ATTEMPT_PHASES
            or type(attempt["upstreamInitiated"]) is not bool
            or attempt["statusClass"] not in _LIVE_ATTEMPT_STATUS_CLASSES
            or attempt["errorCode"] not in _LIVE_ATTEMPT_ERROR_CODES
        ):
            raise ContractError("evidence_provider_attempt_invalid")
        previous_sequence = attempt["sequence"]

    terminal = _object(evidence["terminal"], "evidence_terminal")
    if set(terminal).difference({"present", "kind", "code", "reasonCategory"}) or not {
        "present",
        "kind",
    }.issubset(terminal):
        raise ContractError("evidence_terminal_fields_invalid")
    if type(terminal["present"]) is not bool or terminal["kind"] not in _FAILURE_TERMINAL_KINDS:
        raise ContractError("evidence_terminal_invalid")
    for field in ("code", "reasonCategory"):
        if field in terminal:
            _safe_ref(terminal[field], f"evidence_terminal_{field}")

    if type(evidence["planeHostOperationReceipts"]) is not bool:
        raise ContractError("evidence_host_receipts_invalid")
    audit = evidence["planeOperationAudit"]
    if not isinstance(audit, list) or len(audit) != len(_LIVE_OPERATION_IDS):
        raise ContractError("evidence_operation_audit_count_invalid")
    for operation_id, row in zip(_LIVE_OPERATION_IDS, audit):
        operation = _object(row, "evidence_operation_audit")
        if set(operation) != {"operationId", "status", "errorCode", "count"} or (
            operation["operationId"] != operation_id
            or operation["status"] not in _LIVE_OPERATION_STATUSES
            or operation["errorCode"] is not None
            and operation["errorCode"] not in _LIVE_OPERATION_ERROR_CODES
            or type(operation["count"]) is not int
            or not 0 <= operation["count"] <= 8
        ):
            raise ContractError("evidence_operation_audit_invalid")
    if "providerRelay" in evidence:
        evidence_provider_relay = _provider_relay(evidence["providerRelay"], "evidence_provider_relay")
        _exact(evidence_provider_relay, authority_info["providerRelay"], "evidence_provider_relay")
    elif not (
        evidence["run"]["present"] is False
        and evidence["invocation"]["present"] is False
        and evidence["runtimeExit"]["present"] is False
        and evidence["providerAttempts"] == []
        and evidence["runtimeEventIngress"]["kindCounts"] == {}
        and evidence["terminal"]["present"] is False
        and evidence["planeHostOperationReceipts"] is False
        and all(row["count"] == 0 for row in evidence["planeOperationAudit"])
    ):
        raise ContractError("evidence_provider_relay_missing")
    _validate_semantic_digest(evidence)


def validate_evidence(
    evidence_text: str,
    manifest: dict[str, Any],
    authority_info: dict[str, Any],
    config: dict[str, Any],
    candidate: str,
) -> dict[str, Any]:
    if len(evidence_text.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ContractError("evidence_oversized")
    if SECRET_FIELD_RE.search(evidence_text):
        raise ContractError("evidence_contains_sensitive_field")
    try:
        evidence = json.loads(evidence_text.strip())
    except json.JSONDecodeError as exc:
        raise ContractError("evidence_must_be_one_json_object") from exc
    if not isinstance(evidence, dict):
        raise ContractError("evidence_must_be_one_json_object")
    if set(evidence).difference(_LIVE_TOP_LEVEL_FIELDS):
        raise ContractError("evidence_top_level_fields_invalid")
    expected = exact_binding(manifest, candidate)
    schema = _required(evidence, "schemaVersion", "evidence")
    status = _required(evidence, "status", "evidence")
    if schema == "plane-agent-g4/live-failure/v1" or status == "failed":
        _validate_failure_receipt(evidence, authority_info, expected)
        return {
            "evidenceSha256": hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
            "collected": 0,
            "passed": 0,
        }
    _exact(schema, "plane-agent-g4/live-evidence/v1", "evidence_schema")
    _exact(status, "passed", "evidence_status")
    _validate_receipt_common(evidence, authority_info, expected, status="passed")
    readback = _object(_required(evidence, "readback", "evidence"), "evidence_readback")
    _validate_live_readback(readback)
    if authority_info["providerRelay"] is None:
        raise ContractError("evidence_provider_relay_missing_authority")
    if "providerRelay" not in evidence:
        raise ContractError("evidence_provider_relay_missing")
    evidence_provider_relay = _provider_relay(evidence["providerRelay"], "evidence_provider_relay")
    _exact(evidence_provider_relay, authority_info["providerRelay"], "evidence_provider_relay")
    if evidence_provider_relay["hermesHookStatus"] != "integrated":
        raise ContractError("evidence_provider_relay_hook_not_integrated")
    _exact(_required(evidence, "provider", "evidence"), {**authority_info["provider"], "fallbackUsed": False}, "evidence_provider")
    threshold_result = _object(_required(evidence, "thresholds", "evidence"), "evidence_thresholds")
    _exact(_required(threshold_result, "profile", "evidence_thresholds"), authority_info["thresholdProfile"], "evidence_threshold_profile")
    _exact(_required(threshold_result, "approved", "evidence_thresholds"), authority_info["thresholds"], "evidence_approved_thresholds")
    observed = _object(_required(threshold_result, "observed", "evidence_thresholds"), "evidence_observed_thresholds")
    permitted_rate = _number(observed, "permittedSuccessRate", "evidence_observed_thresholds")
    denied_rate = _number(observed, "deniedRejectionRate", "evidence_observed_thresholds")
    latency = _number(observed, "latencyP95Ms", "evidence_observed_thresholds")
    error_rate = _number(observed, "errorRate", "evidence_observed_thresholds")
    approved = authority_info["thresholds"]
    if permitted_rate < approved["permittedSuccessRateMin"] or denied_rate < approved["deniedRejectionRateMin"]:
        raise ContractError("evidence_threshold_rate_failed")
    if latency > approved["maxLatencyP95Ms"] or error_rate > approved["maxErrorRate"]:
        raise ContractError("evidence_threshold_latency_or_error_failed")
    readback = _object(_required(evidence, "readback", "evidence"), "evidence_readback")
    audit = _object(_required(readback, "audit", "evidence_readback"), "evidence_audit_readback")
    version = _object(_required(readback, "version", "evidence_readback"), "evidence_version_readback")
    if set(audit).difference(_LIVE_AUDIT_FIELDS):
        raise ContractError("evidence_audit_fields_invalid")
    if set(version).difference(_LIVE_VERSION_FIELDS):
        raise ContractError("evidence_version_fields_invalid")
    if audit.get("passed") is not True or version.get("passed") is not True:
        raise ContractError("evidence_audit_or_version_readback_failed")
    if not isinstance(audit.get("eventCount"), int) or audit["eventCount"] < 1:
        raise ContractError("evidence_audit_readback_empty")
    _exact(version.get("binding"), expected, "evidence_version_binding")
    summary_obj = _object(_required(evidence, "summary", "evidence"), "evidence_summary")
    workload = _object(_required(summary_obj, "workload", "evidence_summary"), "evidence_summary_workload")
    if set(workload).difference(_LIVE_WORKLOAD_FIELDS):
        raise ContractError("evidence_workload_fields_invalid")
    usage = _object(_required(workload, "usage", "evidence_summary_workload"), "evidence_summary_usage")
    if set(usage) != set(_LIVE_USAGE_KEYS) or any(
        type(value) is not int or not 0 <= value <= 10_000_000 for value in usage.values()
    ):
        raise ContractError("evidence_usage_fields_invalid")
    summary = _summary(summary_obj, "evidence_summary")
    _validate_semantic_digest(evidence)
    return {
        "evidenceSha256": hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
        "collected": summary["counts"]["collected"],
        "passed": summary["counts"]["passed"],
    }


def validate_files(
    authority_path: Path,
    config_path: Path,
    manifest_path: Path,
    evidence_path: Path,
    candidate: str,
    expected_candidate: str,
    command: str,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path, "manifest")
    authority = _read_json(authority_path, "authority")
    config = _read_json(config_path, "config")
    authority_info = validate_authority(authority, manifest, candidate, expected_candidate, command)
    validate_config(config, authority_info, command)
    evidence = validate_evidence(_read_bounded_text(evidence_path), manifest, authority_info, config, candidate)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = _read_json(args.manifest, "manifest")
        authority = _read_json(args.authority, "authority")
        config = _read_json(args.config, "config")
        authority_info = validate_authority(
            authority,
            manifest,
            args.candidate,
            args.expected_candidate,
            args.command,
            Path.cwd(),
            require_provider_relay=args.config_only,
        )
        validate_config(config, authority_info, args.command, require_provider_relay=args.config_only)
        if args.config_only:
            result = {"evidenceSha256": "not_run", "collected": 0, "passed": 0}
        else:
            if args.evidence is None:
                raise ContractError("evidence_path_required")
            result = validate_evidence(
                _read_bounded_text(args.evidence),
                manifest,
                authority_info,
                config,
                args.candidate,
            )
    except (ContractError, OSError, UnicodeError) as exc:
        print(f"event=agent.g4.live-contract status=failed reason={exc}", file=sys.stderr)
        return 1
    print(
        "event=agent.g4.live-contract status=passed "
        f"evidence_sha256={result['evidenceSha256']} "
        f"collected={result['collected']} passed={result['passed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

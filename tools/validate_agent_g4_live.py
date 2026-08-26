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
_LIVE_OBSERVATION_THRESHOLD_PROFILES = frozenset({"g4-live-minimal-single-invocation"})
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_FIELD_RE = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|authorization|credential)\s*[\"']?\s*[:=]"
)
ROLLBACK_SERVICE_NAMES = ("api", "worker", "beat-worker", "supervisor", "agent-runtime")
ROLLBACK_MIGRATION = "db.0146_runtime_reconciliation_audit_fields"
ROLLBACK_PREVIOUS_MIGRATION = "db.0145_runtime_reconciliation"
ROLLBACK_OPERATION_CONTRACT = "plane.operation/v1"
ROLLBACK_RUNTIME_CONTRACT = "plane.agent-runtime/v1"
PROVIDER_RELAY_PROTOCOL = "plane.agent-runtime/provider-relay/v1"
_DISPOSABLE_RUNTIME_FILE_PREFIXES = (
    "apps/api/plane/agent/runtime/",
    "apps/api/plane/agent/code_mode/",
)
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
SETUP_ERROR_STAGES = {
    "shared-setup",
    "assignment",
    "preconditions",
    "lineage",
    "schedule",
    "schedule-fire",
    "run",
    "invocation",
}
SETUP_ERROR_CLASSES = {
    "AgentDomainError",
    "AgentScheduleError",
    "AttributeError",
    "ConnectionError",
    "IntegrityError",
    "KeyError",
    "LookupError",
    "OperationalError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "ValidationError",
    "ValueError",
    "unknown",
}
SETUP_ERROR_COUNTERS = {
    "actors",
    "profiles",
    "assignments",
    "lineageAssignments",
    "schedules",
    "scheduleFires",
}
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


_CHILD_DIAGNOSTIC_FIELDS = frozenset(
    {
        "exceptionClass",
        "module",
        "category",
        "stderrSha256",
        "stderrBytes",
        "termination",
        "exitCode",
    }
)
_HERMES_CHILD_DIAGNOSTIC_FIELDS = frozenset(
    {"exceptionModule", "exceptionClass", "runtimePhase", "originToken"}
)
_CODE_MODE_ERROR_CLASSES = frozenset(
    {
        "module_parse_or_load",
        "default_export_missing",
        "callback_or_protocol",
        "execution_runtime",
        "child_exit_no_result",
    }
)
_CHILD_EXCEPTION_CLASSES = frozenset(
    {
        "ModuleNotFoundError",
        "ImportError",
        "PermissionError",
        "OSError",
        "MemoryError",
        "TimeoutError",
        "PythonException",
        "Signal",
        "Unknown",
    }
)
_CHILD_MODULES = frozenset({"plane", "plane_runtime", "run_agent", "openai", "hermes", "dependency", "unknown"})
_CHILD_CATEGORIES = frozenset(
    {
        "module_not_found",
        "import_error",
        "permission_denied",
        "os_eperm",
        "memory_exhausted",
        "timeout",
        "python_traceback",
        "signal",
        "unknown",
    }
)
_HERMES_CHILD_EXCEPTION_MODULES = frozenset({"Unknown", "builtins", "httpx", "openai"})
_HERMES_CHILD_EXCEPTION_CLASSES = frozenset(
    {
        "ModuleNotFoundError",
        "ImportError",
        "PermissionError",
        "MemoryError",
        "TimeoutError",
        "OSError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "APIConnectionError",
        "APIError",
        "APIResponseValidationError",
        "APIStatusError",
        "APITimeoutError",
        "AuthenticationError",
        "BadRequestError",
        "ConflictError",
        "InternalServerError",
        "NotFoundError",
        "PermissionDeniedError",
        "RateLimitError",
        "UnprocessableEntityError",
        "ConnectTimeout",
        "PoolTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "Unknown",
    }
)
_RUNTIME_FAILURE_PHASES = frozenset(
    {"agent_initialization", "tool_configuration", "conversation", "unknown"}
)
_HERMES_CHILD_ORIGIN_TOKENS = frozenset(
    {"agent_factory", "tool_configuration", "run_conversation", "unknown"}
)


def _validate_child_diagnostic(value: Any, name: str) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{name}_invalid")
    fields = set(value)
    if fields == _CHILD_DIAGNOSTIC_FIELDS:
        if (
            value["exceptionClass"] not in _CHILD_EXCEPTION_CLASSES
            or value["module"] not in _CHILD_MODULES
            or value["category"] not in _CHILD_CATEGORIES
            or not isinstance(value["stderrSha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["stderrSha256"])
            or type(value["stderrBytes"]) is not int
            or not 0 <= value["stderrBytes"] <= 65536
            or value["termination"] not in {"exit", "signal"}
            or type(value["exitCode"]) is not int
            or not -255 <= value["exitCode"] <= 255
        ):
            raise ContractError(f"{name}_invalid")
        return
    if fields == _HERMES_CHILD_DIAGNOSTIC_FIELDS:
        if (
            value["exceptionModule"] not in _HERMES_CHILD_EXCEPTION_MODULES
            or value["exceptionClass"] not in _HERMES_CHILD_EXCEPTION_CLASSES
            or value["runtimePhase"] not in _RUNTIME_FAILURE_PHASES
            or value["originToken"] not in _HERMES_CHILD_ORIGIN_TOKENS
        ):
            raise ContractError(f"{name}_invalid")
        return
    raise ContractError(f"{name}_fields_invalid")


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


def _validate_setup_error(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"id", "stage", "errorClass", "counters"}:
        raise ContractError("runner_failure_setup_error_invalid")
    identifier = value["id"]
    if (
        not isinstance(identifier, str)
        or not 1 <= len(identifier.encode("utf-8")) <= 128
        or not re.fullmatch(r"setup:[a-z-]+:[A-Za-z]+Error|setup:[a-z-]+:unknown", identifier)
    ):
        raise ContractError("runner_failure_setup_error_invalid")
    if value["stage"] not in SETUP_ERROR_STAGES or value["errorClass"] not in SETUP_ERROR_CLASSES:
        raise ContractError("runner_failure_setup_error_invalid")
    counters = value["counters"]
    if not isinstance(counters, dict) or set(counters) != SETUP_ERROR_COUNTERS:
        raise ContractError("runner_failure_setup_error_invalid")
    if any(type(item) is not int or not 0 <= item <= 256 for item in counters.values()):
        raise ContractError("runner_failure_setup_error_invalid")


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
            or not any(relative.startswith(prefix) for prefix in _DISPOSABLE_RUNTIME_FILE_PREFIXES)
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
        "keep the database at leaf `0146`",
        "retain migration `0145`",
        "never reverse to `0144`",
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
    # previous.apiArtifact is the immutable prepared API base consumed by the
    # canonical builder. Rollback still binds the accepted-G3 deployable API
    # through previous.services and the accepted evidence above.
    previous_api = _object(_required(previous, "apiArtifact", "rollback_previous"), "rollback_previous_apiArtifact")
    _rollback_exact(previous_api["contract"], ROLLBACK_OPERATION_CONTRACT, "previous_api_contract")
    # Hermes and MCP may advance for a candidate while rollback still targets
    # the immutable accepted-G3 service image. The accepted G3 values remain
    # evidence for that previous image; the SDK remains shared because its
    # gitlink is unchanged across the accepted baseline and current candidate.
    for key in ("sdkGitlink",):
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
    _rollback_exact(strategy.get("previousMigration"), ROLLBACK_PREVIOUS_MIGRATION, "strategy_previousMigration")
    _rollback_exact(strategy.get("compatibilityFloor"), ROLLBACK_PREVIOUS_MIGRATION, "strategy_compatibilityFloor")
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
    "work_item.rename",
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
_LIVE_ATTEMPT_STATUS_CLASSES = {"", "not_sent", "unknown", "error", "2xx", "4xx", "5xx", "transport"}
_LIVE_ATTEMPT_ERROR_CODES = {
    "",
    "budget_exhausted",
    "cancelled",
    "credential_payload",
    "denied",
    "lease_invalid",
    "pre_send_failure",
    "outcome_unknown",
    "oversize",
    "request_oversize",
    "response_oversize",
    "response_chunk_oversize",
    "provider_error",
    "redirect_denied",
    "replay",
    "runtime_error",
    "upstream_error",
    "unspecified",
}
_LIVE_ATTEMPT_REASON_SUBREASONS = {
    "",
    "upstream_exception",
    "upstream_channel_closed",
    "upstream_timeout",
    "channel_closed_after_upstream",
    "reconciliation_required",
    "request_rejected",
    "auth",
    "rate_limited",
    "upstream_unavailable",
}


def _validate_live_provider_attempt_reason(status_class: str, reason_subreason: str) -> None:
    if reason_subreason not in _LIVE_ATTEMPT_REASON_SUBREASONS:
        raise ContractError("evidence_provider_attempt_reason_subreason_invalid")
    if reason_subreason in {"request_rejected", "auth", "rate_limited"} and status_class != "4xx":
        raise ContractError("evidence_provider_attempt_reason_subreason_invalid")
    if reason_subreason == "upstream_unavailable" and status_class != "5xx":
        raise ContractError("evidence_provider_attempt_reason_subreason_invalid")


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
    "scenarioGate",
    "commissionEvidence",
    "terminalLifecycle",
    "setupError",
}
_TERMINAL_LIFECYCLE_PROTOCOL = "hermes.terminal-lifecycle/v1"
_TERMINAL_LIFECYCLE_STATUSES = {"ok", "replayed", "denied", "conflict", "unavailable", "invalid"}
_TERMINAL_LIFECYCLE_ACTIONS = {"none", "proposal", "applied"}
_TERMINAL_LIFECYCLE_EXIT_CATEGORIES = {
    "unknown",
    "text_response",
    "terminal_action",
    "max_iterations_reached",
    "budget_exhausted",
    "interrupted_by_user",
    "session_persistence_failed",
    "guardrail_halt",
    "local_processing_error",
    "error_near_max_iterations",
    "partial_stream_recovery",
    "other",
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
_S00_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9_.:/@-]{1,128}$")


def _safe_ref(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _S00_SAFE_REF_RE.fullmatch(value):
        raise ContractError(f"{name}_invalid")
    if any(term in value.lower() for term in ("password", "secret", "token", "credential", "authorization", "api_key")):
        raise ContractError(f"{name}_sensitive")
    return value


def _safe_operation_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _S00_OPERATION_ID_RE.fullmatch(value):
        raise ContractError(f"{name}_invalid")
    if any(term in value.lower() for term in ("password", "secret", "token", "credential", "authorization", "api_key")):
        raise ContractError(f"{name}_sensitive")
    return value


_PREPARED_DIAGNOSTIC_FORMS = frozenset(
    {"canonical_ref", "ready_to_call", "unrecognized"}
)
_PREPARED_DIAGNOSTIC_FAILURES = frozenset(
    {"malformed", "unknown", "digest_mismatch", "binding_mismatch"}
)
_PREPARED_DIAGNOSTIC_VALUE_TYPES = frozenset(
    {"null", "boolean", "string", "integer", "number", "object", "array", "unknown"}
)
_PREPARED_DIAGNOSTIC_SIZE_CLASSES = frozenset({"small", "medium", "large", "unknown"})
_PREPARED_DIAGNOSTIC_SENSITIVE_KEYS = frozenset(
    {"auth", "credential", "key", "password", "secret", "token"}
)


def _bounded_prepared_shape_key(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    lowered = value.casefold()
    if any(part in lowered for part in _PREPARED_DIAGNOSTIC_SENSITIVE_KEYS):
        return None
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
    if any(char not in allowed for char in value):
        return None
    parts = value.split("-")
    if len(parts) == 5 and [len(part) for part in parts] == [8, 4, 4, 4, 12]:
        if all(char in "0123456789abcdefABCDEF" for part in parts for char in part):
            return None
    if len(value) >= 32 and all(char in "0123456789abcdefABCDEF" for char in value):
        return None
    return value


def _bounded_prepared_shape_diagnostic(value: Any) -> dict[str, Any] | None:
    """Validate only finite shape metadata; reject raw prepared values."""

    fields = {"schemaVersion", "acceptedForm", "failureClass", "shape"}
    shape_fields = {"keyNames", "keyNamesTruncated", "valueTypes", "nestingDepth", "sizeClass"}
    if not isinstance(value, dict) or set(value) != fields:
        return None
    if (
        value.get("schemaVersion") != "plane.prepared-call-shape/v1"
        or value.get("acceptedForm") not in _PREPARED_DIAGNOSTIC_FORMS
        or value.get("failureClass") not in _PREPARED_DIAGNOSTIC_FAILURES
    ):
        return None
    shape = value.get("shape")
    if not isinstance(shape, dict) or set(shape) != shape_fields:
        return None
    key_names = shape.get("keyNames")
    value_types = shape.get("valueTypes")
    if (
        not isinstance(key_names, list)
        or len(key_names) > 16
        or any(_bounded_prepared_shape_key(item) != item for item in key_names)
        or len(set(key_names)) != len(key_names)
        or type(shape.get("keyNamesTruncated")) is not bool
        or not isinstance(value_types, list)
        or len(value_types) > len(_PREPARED_DIAGNOSTIC_VALUE_TYPES)
        or any(
            not isinstance(item, str) or item not in _PREPARED_DIAGNOSTIC_VALUE_TYPES
            for item in value_types
        )
        or len(set(value_types)) != len(value_types)
        or type(shape.get("nestingDepth")) is not int
        or not 0 <= shape["nestingDepth"] <= 8
        or shape.get("sizeClass") not in _PREPARED_DIAGNOSTIC_SIZE_CLASSES
    ):
        return None
    return {
        "schemaVersion": "plane.prepared-call-shape/v1",
        "acceptedForm": value["acceptedForm"],
        "failureClass": value["failureClass"],
        "shape": {
            "keyNames": list(key_names),
            "keyNamesTruncated": shape["keyNamesTruncated"],
            "valueTypes": list(value_types),
            "nestingDepth": shape["nestingDepth"],
            "sizeClass": shape["sizeClass"],
        },
    }


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
_SCENARIO_RECORD_KINDS = {
    "assignment", "run", "invocation", "input_event", "audit", "publication", "terminal_event",
    "schedule", "schedule_fire", "lineage_assignment",
}
_SCENARIO_PRODUCT_KINDS = {
    "publication", "outcome_submission", "run_failure", "run_blocker", "run_cancellation", "input_event",
}
_WORKER_ROUTE_BOOLEAN_FIELDS = {
    "W01": {"actorProfileAssignmentSeparate", "snapshotBound"},
    "W02": {"catalogSearchBeforeDescribe", "boundedSearchAndRead", "hiddenObjectsAbsent"},
    "W04": {"positiveTypedHostCallback", "sameGateway", "failClosedControls"},
    "W05": {
        "contextReceipt",
        "privateMemoryPresent",
        "subjectPreferencesSeparate",
        "skillProjectionPresent",
        "excludedOtherUserAgentStale",
        "correctContextProjection",
        "otherSubjectIsolated",
        "otherAgentIsolated",
        "losslessRoundTrip",
    },
    "W07": {"oneOutcome", "oneArtifact", "evidenceAttached", "onePublishedTerminal"},
    "W08": {"runReadback", "apiCliConsistent", "crossWorkspaceDenied"},
}
_WORKER_ROUTE_IDS = {f"W{index:02d}" for index in range(1, 9)}
_OPERATOR_ROUTE_IDS = {"O01"} | {f"O{index:02d}" for index in range(3, 11)}
_OPERATOR_ROUTE_BOOLEAN_FIELDS = {
    "O04": {
        "publicMetadataOnly",
        "queuedLeaseObserved",
        "activeLeaseAdmitted",
        "rotateDispatchDenied",
        "rotateCallbackDenied",
        "revokeDispatchDenied",
        "revokeCallbackDenied",
        "expiryDispatchDenied",
        "expiryCallbackDenied",
    },
}
_MANAGER_ROUTE_BOOLEAN_FIELDS = {
    "M01": {"dynamicPlan", "noSavedWorkflowProduct"},
    "M02": {"boundedDelegation", "lineagePersisted", "independentChildRun"},
    "M03": {"queuedDescendantCancelled", "activeDescendantCancelled", "terminalVisible", "lateCallbackDenied"},
    "M04": {"nonUtcTimezone", "springForwardSkipped", "fireIdempotent", "normalAssignmentCreated"},
    "M05": {"evaluatorFirst", "humanDecisionAfterEvaluator", "revisionFreshRun", "priorSnapshotImmutable", "finalAccepted"},
    "M06": {"proposalRecorded", "humanApprovalApplied", "selfApprovalDenied", "staleApprovalDenied"},
    "M07": {"humanApprovalRequired", "chiefProvisioned", "currentMembershipCopied", "noStaleMembershipCopy", "noCrossWorkspaceMembership"},
    "M08": {"parentChildLineage", "outcomeAndArtifact", "terminalEventsAgree", "evaluatorAndHumanReadback", "immutablePriorSnapshot"},
}
_MANAGER_ROUTE_IDS = set(_MANAGER_ROUTE_BOOLEAN_FIELDS)
_SCENARIO_ROUTE_IDS = _WORKER_ROUTE_IDS | _OPERATOR_ROUTE_IDS | _MANAGER_ROUTE_IDS
_MANAGER_DIAGNOSTIC_PREDICATES = {
    "M01": {"dynamicPlan", "noSavedWorkflowProduct"},
    "M02": {"boundedDelegation", "lineagePersisted", "independentChildRun"},
    "M03": {"queuedDescendantCancelled", "activeDescendantCancelled", "terminalVisible", "lateCallbackDenied"},
    "M04": {"nonUtcTimezone", "springForwardSkipped", "fireIdempotent", "normalAssignmentCreated"},
    "M05": {"evaluatorFirst", "humanDecisionAfterEvaluator", "revisionFreshRun", "priorSnapshotImmutable", "finalAccepted"},
    "M06": {"proposalRecorded", "humanApprovalApplied", "selfApprovalDenied", "staleApprovalDenied"},
    "M07": {"humanApprovalRequired", "chiefProvisioned", "currentMembershipCopied", "noStaleMembershipCopy", "noCrossWorkspaceMembership"},
    "M08": {"parentChildLineage", "outcomeAndArtifact", "terminalEventsAgree", "evaluatorAndHumanReadback", "immutablePriorSnapshot"},
}
_MANAGER_DIAGNOSTIC_EXCEPTIONS = {
    "AgentDomainError", "AgentScheduleError", "AttributeError", "IntegrityError", "KeyError",
    "LookupError", "OperationalError", "RuntimeError", "TimeoutError", "TypeError",
    "ValidationError", "ValueError", "Unknown",
}
_MANAGER_READBACK_EXCEPTION_CLASSES = {
    "AgentDomainError", "AgentScheduleError", "AttributeError", "IntegrityError", "KeyError",
    "LookupError", "OperationalError", "RuntimeError", "TimeoutError", "TypeError",
    "ValidationError", "ValueError", "Unknown",
}


def _validate_manager_route_diagnostic(value: Any) -> None:
    diagnostic = _object(value, "evidence_manager_route_diagnostic")
    if set(diagnostic) != {"routeId", "predicate", "observed", "exceptionClass"}:
        raise ContractError("evidence_manager_route_diagnostic_fields_invalid")
    route_id = diagnostic["routeId"]
    predicate = diagnostic["predicate"]
    observed = diagnostic["observed"]
    exception_class = diagnostic["exceptionClass"]
    if route_id not in _MANAGER_DIAGNOSTIC_PREDICATES:
        raise ContractError("evidence_manager_route_diagnostic_route_invalid")
    if predicate != "unavailable" and predicate not in _MANAGER_DIAGNOSTIC_PREDICATES[route_id]:
        raise ContractError("evidence_manager_route_diagnostic_predicate_invalid")
    if type(observed) is not bool and observed not in {"exception", "non_boolean"}:
        raise ContractError("evidence_manager_route_diagnostic_observed_invalid")
    if observed == "exception":
        if exception_class not in _MANAGER_DIAGNOSTIC_EXCEPTIONS:
            raise ContractError("evidence_manager_route_diagnostic_exception_invalid")
    elif exception_class is not None:
        raise ContractError("evidence_manager_route_diagnostic_exception_invalid")


def _validate_scenario_projection(value: Any) -> None:
    scenario = _object(value, "evidence_scenario")
    required = {"id", "descriptorDigest", "schemaVersion", "actorRole", "profileName"}
    if set(scenario).difference(required | {"commissionId", "expected", "setup", "controls", "actual"}) or not required.issubset(scenario):
        raise ContractError("evidence_scenario_fields_invalid")
    scenario_id = scenario["id"]
    if scenario_id not in _SCENARIO_ACTOR_ROLES or scenario["actorRole"] != _SCENARIO_ACTOR_ROLES[scenario_id]:
        raise ContractError("evidence_scenario_identity_invalid")
    if not isinstance(scenario["descriptorDigest"], str) or not HASH_RE.fullmatch(scenario["descriptorDigest"]):
        raise ContractError("evidence_scenario_digest_invalid")
    if "commissionId" in scenario and (
        not isinstance(scenario["commissionId"], str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:/-]{0,63}", scenario["commissionId"])
    ):
        raise ContractError("evidence_scenario_commission_invalid")
    _exact(scenario["schemaVersion"], "plane.agent-scenario/v1", "evidence_scenario_schema")
    if (
        not isinstance(scenario["profileName"], str)
        or not 1 <= len(scenario["profileName"].encode("utf-8")) <= 96
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,95}", scenario["profileName"])
    ):
        raise ContractError("evidence_scenario_profile_invalid")
    expected = scenario.get("expected")
    if expected is not None:
        expected = _object(expected, "evidence_scenario_expected")
        if set(expected).difference({"operationOutcomes", "evidenceKinds", "durableRecords", "productEvents", "routeChecks"}) or not {"operationOutcomes", "evidenceKinds"}.issubset(expected):
            raise ContractError("evidence_scenario_expected_fields_invalid")
        operations = expected["operationOutcomes"]
    else:
        operations = []
    if not isinstance(operations, list) or len(operations) > 16:
        raise ContractError("evidence_scenario_expected_operations_invalid")
    for operation in operations:
        row = _object(operation, "evidence_scenario_expected_operation")
        if set(row).difference({"operationId", "outcome", "count"}) or not {"operationId", "outcome"}.issubset(row):
            raise ContractError("evidence_scenario_expected_operation_fields_invalid")
        _safe_ref(row["operationId"], "evidence_scenario_expected_operation_id")
        if row["outcome"] not in _SCENARIO_OUTCOMES:
            raise ContractError("evidence_scenario_expected_operation_outcome_invalid")
        if "count" in row and (type(row["count"]) is not int or not 0 <= row["count"] <= 256):
            raise ContractError("evidence_scenario_expected_operation_count_invalid")
    evidence_kinds = expected["evidenceKinds"] if expected is not None else []
    if (
        not isinstance(evidence_kinds, list)
        or len(evidence_kinds) > 16
        or any(not isinstance(kind, str) or kind not in _SCENARIO_RECORD_KINDS for kind in evidence_kinds)
    ):
        raise ContractError("evidence_scenario_expected_evidence_invalid")
    if expected is not None and "routeChecks" in expected:
        if (
            not isinstance(expected["routeChecks"], list)
            or len(expected["routeChecks"]) > 9
            or len(set(expected["routeChecks"])) != len(expected["routeChecks"])
            or any(check not in _SCENARIO_ROUTE_IDS for check in expected["routeChecks"])
        ):
            raise ContractError("evidence_scenario_expected_route_checks_invalid")
    for field, allowed_kinds in (("durableRecords", _SCENARIO_RECORD_KINDS), ("productEvents", _SCENARIO_PRODUCT_KINDS)):
        if expected is None or field not in expected:
            continue
        rows = expected[field]
        if not isinstance(rows, list) or len(rows) > 8:
            raise ContractError("evidence_scenario_expected_records_invalid")
        for row in rows:
            item = _object(row, "evidence_scenario_expected_record")
            if set(item) != {"kind", "count"} or item["kind"] not in allowed_kinds or type(item["count"]) is not int or not 0 <= item["count"] <= 256:
                raise ContractError("evidence_scenario_expected_record_invalid")
    setup = scenario.get("setup", {"preconditions": [], "actors": []})
    if not isinstance(setup, dict) or set(setup).difference({"preconditions", "actors", "lineage", "schedule"}):
        raise ContractError("evidence_scenario_setup_invalid")
    controls = scenario.get("controls", {"fault": {"selection": "none"}})
    if not isinstance(controls, dict) or set(controls).difference({"continuation", "revision", "cancellation", "fault"}):
        raise ContractError("evidence_scenario_controls_invalid")
    if "fault" not in controls or not isinstance(controls["fault"], dict) or controls["fault"].get("selection") not in {"none", "budget_exhausted", "runtime_unavailable"}:
        raise ContractError("evidence_scenario_fault_invalid")
    if "actual" in scenario:
        actual = _object(scenario["actual"], "evidence_scenario_actual")
        allowed_actual = {"operations", "records", "productEvents", "evidenceKinds", "routeEvidence"}
        if set(actual).difference(allowed_actual) or not {"operations", "records", "productEvents", "evidenceKinds"}.issubset(actual):
            raise ContractError("evidence_scenario_actual_invalid")
        for key in ("operations", "evidenceKinds"):
            if not isinstance(actual[key], list) or len(actual[key]) > 16:
                raise ContractError("evidence_scenario_actual_list_invalid")
        if any(kind not in _SCENARIO_RECORD_KINDS for kind in actual["evidenceKinds"]):
            raise ContractError("evidence_scenario_actual_evidence_invalid")
        for key, allowed_kinds in (("records", _SCENARIO_RECORD_KINDS), ("productEvents", _SCENARIO_PRODUCT_KINDS)):
            rows = actual[key]
            if not isinstance(rows, list) or len(rows) > 16:
                raise ContractError("evidence_scenario_actual_list_invalid")
            for row in rows:
                if not isinstance(row, dict) or set(row) != {"kind", "count"} or row["kind"] not in allowed_kinds or type(row["count"]) is not int or not 0 <= row["count"] <= 256:
                    raise ContractError("evidence_scenario_actual_record_invalid")
        if "routeEvidence" in actual:
            route_checks = expected.get("routeChecks", []) if expected is not None else []
            route_check_set = set(route_checks)
            if scenario_id == "manager":
                _validate_manager_route_evidence(actual["routeEvidence"], route_checks=route_check_set)
            elif scenario_id == "worker":
                _validate_worker_route_evidence(actual["routeEvidence"], route_checks=route_check_set)
            elif scenario_id == "operator":
                _validate_operator_route_evidence(actual["routeEvidence"], route_checks=route_check_set)
            else:
                raise ContractError("evidence_non_worker_route_evidence_unsupported")
        elif scenario_id == "operator" and expected is not None and "O04" in expected.get("routeChecks", []):
            raise ContractError("evidence_operator_o04_route_evidence_missing")


def _validate_worker_route_evidence(value: Any, *, route_checks: set[str] | None = None) -> None:
    payload = _object(value, "evidence_worker_route_evidence")
    if set(payload) != {"routes", "readback"}:
        raise ContractError("evidence_worker_route_evidence_fields_invalid")
    routes = _object(payload["routes"], "evidence_worker_routes")
    expected_route_ids = set(route_checks) if route_checks is not None else set(_WORKER_ROUTE_IDS)
    if not expected_route_ids <= _WORKER_ROUTE_IDS or set(routes) != expected_route_ids | {"replay"}:
        raise ContractError("evidence_worker_route_ids_invalid")
    for route_id in expected_route_ids & set(_WORKER_ROUTE_BOOLEAN_FIELDS):
        fields = _WORKER_ROUTE_BOOLEAN_FIELDS[route_id]
        row = _object(routes[route_id], f"evidence_worker_{route_id}")
        if set(row) != fields and not (route_id == "W01" and set(row) == fields | {"substitution"}):
            raise ContractError("evidence_worker_route_fields_invalid")
        for field in fields:
            if row[field] is not True:
                raise ContractError("evidence_worker_route_failed")
    if "W01" in expected_route_ids:
        substitution = _object(routes["W01"]["substitution"], "evidence_worker_substitution")
        if set(substitution) != {"status", "errorCode", "sideEffects"} or substitution != {
            "status": "denied", "errorCode": "NOT_AUTHORIZED", "sideEffects": 0
        }:
            raise ContractError("evidence_worker_substitution_invalid")
    if "W03" in expected_route_ids:
        rename = _object(routes["W03"], "evidence_worker_W03")
        if set(rename) != {"status", "semanticDelta", "duplicateMutation", "httpStatus", "receiptRef", "auditReceiptRef"} or rename["status"] != "replayed" or rename["semanticDelta"] != 0 or rename["duplicateMutation"] != 0 or rename["httpStatus"] != 200:
            raise ContractError("evidence_worker_rename_replay_invalid")
        for field, prefix in (("receiptRef", "receipt:"), ("auditReceiptRef", "audit-receipt:")):
            if not isinstance(rename[field], str) or not rename[field].startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", rename[field]):
                raise ContractError("evidence_worker_rename_receipt_invalid")
    if "W06" in expected_route_ids:
        governance = _object(routes["W06"], "evidence_worker_W06")
        if set(governance) != {"candidate", "candidateNotProjected", "humanApproved", "promoted", "privateAfterPromotion", "rollbackRevision", "proposalReplayStable", "unsupportedSharedDenied", "workspaceUnreviewedNotPromoted"} or any(value is not True for value in governance.values()):
            raise ContractError("evidence_worker_governance_invalid")
    replay = _object(routes["replay"], "evidence_worker_replay")
    if set(replay) != {"context"} or not isinstance(replay["context"], dict) or set(replay["context"]) != {"memoryRevisions", "skillRevisions", "proposals", "contextReceipts"} or any(type(item) is not int or item != 0 for item in replay["context"].values()):
        raise ContractError("evidence_worker_context_replay_invalid")
    readback = _object(payload["readback"], "evidence_worker_readback")
    if set(readback) != {"contextProjectionDigest"} or not isinstance(readback["contextProjectionDigest"], str) or not HASH_RE.fullmatch(readback["contextProjectionDigest"]):
        raise ContractError("evidence_worker_readback_invalid")


def _validate_manager_route_evidence(value: Any, *, route_checks: set[str] | None = None) -> None:
    payload = _object(value, "evidence_manager_route_evidence")
    if set(payload) != {"routes", "readback"}:
        raise ContractError("evidence_manager_route_evidence_fields_invalid")
    routes = _object(payload["routes"], "evidence_manager_routes")
    expected_route_ids = set(route_checks) if route_checks is not None else set(_MANAGER_ROUTE_IDS)
    if not expected_route_ids <= _MANAGER_ROUTE_IDS or set(routes) != expected_route_ids | {"replay"}:
        raise ContractError("evidence_manager_route_ids_invalid")
    for route_id in expected_route_ids:
        row = _object(routes[route_id], f"evidence_manager_{route_id}")
        if set(row) != _MANAGER_ROUTE_BOOLEAN_FIELDS[route_id] or any(item is not True for item in row.values()):
            raise ContractError("evidence_manager_route_failed")
    replay = _object(routes["replay"], "evidence_manager_replay")
    if set(replay) != {"stateMutations"} or replay["stateMutations"] != 0:
        raise ContractError("evidence_manager_replay_invalid")
    readback = _object(payload["readback"], "evidence_manager_readback")
    if set(readback) == {"readbackUnavailable"}:
        if not expected_route_ids <= {"M05", "M06"}:
            raise ContractError("evidence_manager_readback_unavailable_route_invalid")
        unavailable = _object(readback["readbackUnavailable"], "evidence_manager_readback_unavailable")
        if set(unavailable) != {"stage", "predicate", "exceptionClass"}:
            raise ContractError("evidence_manager_readback_unavailable_fields_invalid")
        if unavailable["stage"] != "postRouteReadback":
            raise ContractError("evidence_manager_readback_stage_invalid")
        if unavailable["predicate"] != "readback":
            raise ContractError("evidence_manager_readback_predicate_invalid")
        if unavailable["exceptionClass"] not in _MANAGER_READBACK_EXCEPTION_CLASSES:
            raise ContractError("evidence_manager_readback_exception_invalid")
        return
    expected_fields = {
        "assignmentCount",
        "childAssignmentCount",
        "outcomeCount",
        "artifactOutcomeCount",
        "terminalEventCount",
        "governanceReadbackDigest",
    }
    if set(readback) != expected_fields:
        raise ContractError("evidence_manager_readback_fields_invalid")
    for field in expected_fields - {"governanceReadbackDigest"}:
        if type(readback[field]) is not int or not 0 <= readback[field] <= 256:
            raise ContractError("evidence_manager_readback_count_invalid")
    if not isinstance(readback["governanceReadbackDigest"], str) or not HASH_RE.fullmatch(
        readback["governanceReadbackDigest"]
    ):
        raise ContractError("evidence_manager_readback_digest_invalid")


def _validate_operator_route_evidence(value: Any, *, route_checks: set[str] | None = None) -> None:
    payload = _object(value, "evidence_operator_route_evidence")
    if set(payload) != {"routes", "readback"}:
        raise ContractError("evidence_operator_route_evidence_fields_invalid")
    routes = _object(payload["routes"], "evidence_operator_routes")
    expected_route_ids = (set(route_checks or ()) & set(_OPERATOR_ROUTE_BOOLEAN_FIELDS))
    if set(routes) != expected_route_ids | {"replay"}:
        raise ContractError("evidence_operator_route_ids_invalid")
    for route_id in expected_route_ids:
        row = _object(routes[route_id], f"evidence_operator_{route_id}")
        if set(row) != _OPERATOR_ROUTE_BOOLEAN_FIELDS[route_id] or any(item is not True for item in row.values()):
            raise ContractError("evidence_operator_route_failed")
    replay = _object(routes["replay"], "evidence_operator_replay")
    if set(replay) != {"stateMutations"} or replay["stateMutations"] != 0:
        raise ContractError("evidence_operator_replay_invalid")
    readback = _object(payload["readback"], "evidence_operator_readback")
    if set(readback) != {"credentialLifecycleDigest", "source", "rawValuesRetained"}:
        raise ContractError("evidence_operator_readback_invalid")
    digest = readback["credentialLifecycleDigest"]
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        raise ContractError("evidence_operator_readback_invalid")
    if readback["source"] != "provider-free-runtime-lease-harness/v1" or readback["rawValuesRetained"] is not False:
        raise ContractError("evidence_operator_readback_invalid")
    expected_digest = hashlib.sha256(
        json.dumps(routes["O04"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != expected_digest:
        raise ContractError("evidence_operator_readback_invalid")


def _validate_scenario_gate(value: Any) -> None:
    gate = _object(value, "evidence_scenario_gate")
    required = {"passed", "failures", "operations", "durableRecords", "productEvents", "evidenceKinds"}
    if set(gate) != required or type(gate["passed"]) is not bool or not isinstance(gate["failures"], list):
        raise ContractError("evidence_scenario_gate_invalid")
    for row in gate["operations"]:
        item = _object(row, "evidence_scenario_gate_operation")
        if set(item) != {"operationId", "expected", "actual", "expectedCount", "actualCount", "passed"} or item["expected"] not in _SCENARIO_OUTCOMES or item["actual"] not in _SCENARIO_OUTCOMES:
            raise ContractError("evidence_scenario_gate_operation_invalid")
        _safe_ref(item["operationId"], "evidence_scenario_gate_operation_id")
    for key, allowed_kinds in (("durableRecords", _SCENARIO_RECORD_KINDS), ("productEvents", _SCENARIO_PRODUCT_KINDS)):
        if not isinstance(gate[key], list) or len(gate[key]) > 8:
            raise ContractError("evidence_scenario_gate_records_invalid")
        for row in gate[key]:
            item = _object(row, "evidence_scenario_gate_record")
            if set(item) != {"kind", "expectedCount", "actualCount", "passed"}:
                raise ContractError("evidence_scenario_gate_record_invalid")
            if item["kind"] not in allowed_kinds or type(item["expectedCount"]) is not int or not 0 <= item["expectedCount"] <= 256 or type(item["actualCount"]) is not int or not 0 <= item["actualCount"] <= 256:
                raise ContractError("evidence_scenario_gate_record_invalid")
    if not isinstance(gate["evidenceKinds"], list) or any(not isinstance(row, dict) or set(row) != {"kind", "passed"} for row in gate["evidenceKinds"]):
        raise ContractError("evidence_scenario_gate_evidence_invalid")
    if gate["passed"] != (not gate["failures"] and all(row["passed"] for row in gate["operations"] + gate["durableRecords"] + gate["productEvents"] + gate["evidenceKinds"])):
        raise ContractError("evidence_scenario_gate_predicate_mismatch")


def _validate_semantic_digest(evidence: dict[str, Any]) -> None:
    _hash(_required(evidence, "semanticDigest", "evidence"), "evidence_semantic_digest")
    _exact(evidence["semanticDigest"], _semantic_digest(evidence), "evidence_semantic_digest")


def _validate_terminal_lifecycle(value: Any) -> None:
    lifecycle = _object(value, "evidence_terminal_lifecycle")
    expected = {
        "protocol",
        "category",
        "hook_installed",
        "terminal_action_observed",
        "terminal_reason",
        "terminal_action",
        "outcome_publication",
        "finalization",
    }
    if set(lifecycle) != expected:
        raise ContractError("evidence_terminal_lifecycle_fields_invalid")
    _exact(lifecycle["protocol"], _TERMINAL_LIFECYCLE_PROTOCOL, "evidence_terminal_lifecycle_protocol")
    _exact(lifecycle["category"], "terminal_lifecycle", "evidence_terminal_lifecycle_category")
    if lifecycle["hook_installed"] is not True or type(lifecycle["terminal_action_observed"]) is not bool:
        raise ContractError("evidence_terminal_lifecycle_hook_invalid")
    if lifecycle["terminal_reason"] not in {"product_outcome_published", "none"}:
        raise ContractError("evidence_terminal_lifecycle_reason_invalid")

    def counter(value: Any, name: str) -> None:
        if type(value) is not int or not 0 <= value <= 1_000_000:
            raise ContractError(f"evidence_terminal_lifecycle_{name}_invalid")

    action = lifecycle["terminal_action"]
    if action is not None:
        action = _object(action, "evidence_terminal_lifecycle_action")
        action_fields = {
            "reason",
            "observed_at",
            "api_call_count",
            "provider_responses",
            "iteration_budget_used",
            "iteration_budget_remaining",
        }
        if set(action) != action_fields:
            raise ContractError("evidence_terminal_lifecycle_action_fields_invalid")
        if action["reason"] not in {"product_outcome_published", "terminal_action_observed"}:
            raise ContractError("evidence_terminal_lifecycle_action_reason_invalid")
        _exact(action["observed_at"], "post_tool_batch", "evidence_terminal_lifecycle_action_timing")
        for field in action_fields - {"reason", "observed_at"}:
            counter(action[field], field)

    publication = lifecycle["outcome_publication"]
    if publication is not None:
        publication = _object(publication, "evidence_terminal_lifecycle_publication")
        publication_fields = {
            "status",
            "replayed",
            "publication_action",
            "operation_ref",
            "terminal_armed",
        }
        if set(publication) != publication_fields:
            raise ContractError("evidence_terminal_lifecycle_publication_fields_invalid")
        if (
            publication["status"] not in _TERMINAL_LIFECYCLE_STATUSES
            or type(publication["replayed"]) is not bool
            or publication["publication_action"] not in _TERMINAL_LIFECYCLE_ACTIONS
            or publication["operation_ref"] not in {"none", "operation:agent.outcome.publish"}
            or type(publication["terminal_armed"]) is not bool
        ):
            raise ContractError("evidence_terminal_lifecycle_publication_invalid")

    finalization = _object(lifecycle["finalization"], "evidence_terminal_lifecycle_finalization")
    finalization_fields = {
        "api_call_count",
        "provider_responses",
        "max_iterations",
        "iteration_budget_max_total",
        "iteration_budget_used",
        "iteration_budget_remaining",
        "exit_reason_before_mapping",
        "exit_reason_after_mapping",
    }
    if set(finalization) != finalization_fields:
        raise ContractError("evidence_terminal_lifecycle_finalization_fields_invalid")
    for field in finalization_fields - {"exit_reason_before_mapping", "exit_reason_after_mapping"}:
        counter(finalization[field], field)
    for field in ("exit_reason_before_mapping", "exit_reason_after_mapping"):
        if finalization[field] not in _TERMINAL_LIFECYCLE_EXIT_CATEGORIES:
            raise ContractError(f"evidence_terminal_lifecycle_{field}_invalid")


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
        scenario = evidence["scenario"]
        if status == "failed" and isinstance(scenario, dict) and "actual" in scenario:
            # A bounded multi-commission failure may retain only the aggregate
            # gate and partial route projection; do not require a complete
            # worker route from a cell that never reached its terminal step.
            scenario = dict(scenario)
            scenario.pop("actual")
        _validate_scenario_projection(scenario)
    generic = "scenario" in evidence and isinstance(evidence["scenario"], dict) and "actual" in evidence["scenario"]
    if generic:
        gate = _required(evidence, "scenarioGate", "evidence")
        _validate_scenario_gate(gate)
        if status == "passed" and not gate["passed"]:
            raise ContractError("evidence_scenario_gate_success_failed")
    else:
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


def _validate_runtime_diagnostics(value: Any) -> None:
    diagnostics = _object(value, "evidence_runtime_diagnostics")
    required = {"version", "requests", "responses"}
    if (
        not required.issubset(diagnostics)
        or not set(diagnostics).issubset(
            required | {"hostCallbacks", "codeModeSourceDigest", "codeModeErrorClass"}
        )
        or diagnostics["version"] != 1
    ):
        raise ContractError("evidence_runtime_diagnostics_fields_invalid")
    for key, maximum in (("requests", 32), ("responses", 32)):
        rows = diagnostics[key]
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ContractError("evidence_runtime_diagnostics_rows_invalid")
        previous = 0
        for row in rows:
            item = _object(row, f"evidence_runtime_diagnostics_{key}")
            if key == "requests":
                expected = {"sequence", "toolChoice", "visibleToolset", "visibleToolCount", "serialized"}
                valid = (
                    item.get("toolChoice") in {
                        "required",
                        "auto",
                        "absent",
                        "plane_operation",
                        "plane_publish",
                        "plane_execute_typescript",
                    }
                    and item.get("visibleToolset") in {"execute_only", "execute_and_publish", "other", "empty"}
                    and type(item.get("visibleToolCount")) is int
                    and 0 <= item.get("visibleToolCount") <= 64
                    and item.get("serialized") is True
                )
            else:
                expected = {"sequence", "responseClass", "toolCall"}
                if item.get("toolCall") == "publish" and "publishArgumentShape" in item:
                    expected.add("publishArgumentShape")
                valid = item.get("responseClass") in {"tool_call", "text_response"} and item.get("toolCall") in {
                    "execute", "publish", "other", "none", "multiple"
                }
                if "publishArgumentShape" in item:
                    valid = valid and item["publishArgumentShape"] in {
                        "malformed_json",
                        "non_object",
                        "minimal_outcome",
                        "content_only_outcome",
                        "exact_redundant_outcome",
                        "partial_or_unknown_outcome",
                        "conversation",
                        "missing_required",
                    }
            if set(item) != expected or type(item.get("sequence")) is not int or not 1 <= item["sequence"] <= 256 or item["sequence"] <= previous or not valid:
                raise ContractError("evidence_runtime_diagnostics_row_invalid")
            previous = item["sequence"]
    if "codeModeSourceDigest" in diagnostics and (
        not isinstance(diagnostics["codeModeSourceDigest"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", diagnostics["codeModeSourceDigest"])
    ):
        raise ContractError("evidence_runtime_diagnostics_code_mode_source_digest_invalid")
    if (
        "codeModeErrorClass" in diagnostics
        and (
            not isinstance(diagnostics["codeModeErrorClass"], str)
            or diagnostics["codeModeErrorClass"] not in _CODE_MODE_ERROR_CLASSES
        )
    ):
        raise ContractError("evidence_runtime_diagnostics_code_mode_error_class_invalid")
    if "hostCallbacks" in diagnostics:
        callbacks = diagnostics["hostCallbacks"]
        if not isinstance(callbacks, list) or len(callbacks) > 64:
            raise ContractError("evidence_runtime_diagnostics_host_callbacks_invalid")
        previous = 0
        for row in callbacks:
            item = _object(row, "evidence_runtime_diagnostics_hostCallbacks")
            if (
                set(item) != {"sequence", "phase", "operationRefDigest"}
                or type(item.get("sequence")) is not int
                or not 1 <= item["sequence"] <= 256
                or item["sequence"] <= previous
                or item.get("phase") not in {"before_host_call", "host_return", "model_observation_emit", "adapter_event"}
                or not isinstance(item.get("operationRefDigest"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["operationRefDigest"])
            ):
                raise ContractError("evidence_runtime_diagnostics_host_callback_row_invalid")
            previous = item["sequence"]


def _validate_live_readback(evidence: dict[str, Any]) -> None:
    if set(evidence) != _LIVE_READBACK_FIELDS:
        raise ContractError("evidence_readback_fields_invalid")
    attempts = _required(evidence, "providerAttempts", "evidence")
    if not isinstance(attempts, list) or not attempts or len(attempts) > 32:
        raise ContractError("evidence_provider_attempts_invalid")
    previous_sequence = 0
    for row in attempts:
        attempt = _object(row, "evidence_provider_attempt")
        base_fields = {"sequence", "phase", "upstreamInitiated", "statusClass", "errorCode"}
        if set(attempt) not in (base_fields, base_fields | {"reasonSubreason"}):
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
        if "reasonSubreason" in attempt:
            _validate_live_provider_attempt_reason(attempt["statusClass"], attempt["reasonSubreason"])
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
    if set(ingress).difference({"kindCounts", "diagnostics"}) or "kindCounts" not in ingress:
        raise ContractError("evidence_runtime_ingress_fields_invalid")
    kind_counts = _object(_required(ingress, "kindCounts", "evidence_runtime_ingress"), "evidence_runtime_ingress_counts")
    if set(kind_counts).difference(_LIVE_RUNTIME_EVENT_KINDS) or any(
        type(count) is not int or not 0 <= count <= 256 for count in kind_counts.values()
    ):
        raise ContractError("evidence_runtime_ingress_invalid")
    if "diagnostics" in ingress:
        _validate_runtime_diagnostics(ingress["diagnostics"])

    audit = _required(evidence, "planeOperationAudit", "evidence")
    if not isinstance(audit, list) or len(audit) != len(_LIVE_OPERATION_IDS):
        raise ContractError("evidence_operation_audit_count_invalid")
    operation_rows = {}
    for operation_id, row in zip(_LIVE_OPERATION_IDS, audit):
        operation = _object(row, "evidence_operation_audit")
        if set(operation).difference({"targetDigest"}) != {"operationId", "status", "errorCode", "count"}:
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
        if "targetDigest" in operation:
            _hash(operation["targetDigest"], "evidence_operation_audit_targetDigest")
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


def _validate_scenario_readback(evidence: dict[str, Any]) -> None:
    if set(evidence) != _LIVE_READBACK_FIELDS:
        raise ContractError("evidence_readback_fields_invalid")
    attempts = evidence["providerAttempts"]
    if not isinstance(attempts, list) or len(attempts) > 32:
        raise ContractError("evidence_provider_attempts_invalid")
    previous = 0
    for row in attempts:
        base_fields = {"sequence", "phase", "upstreamInitiated", "statusClass", "errorCode"}
        if not isinstance(row, dict) or set(row) not in (base_fields, base_fields | {"reasonSubreason"}):
            raise ContractError("evidence_provider_attempt_invalid")
        if type(row["sequence"]) is not int or row["sequence"] <= previous or row["phase"] not in _LIVE_ATTEMPT_PHASES:
            raise ContractError("evidence_provider_attempt_invalid")
        if "reasonSubreason" in row:
            _validate_live_provider_attempt_reason(row["statusClass"], row["reasonSubreason"])
        previous = row["sequence"]
    runtime_exit = _object(evidence["runtimeExit"], "evidence_runtime_exit")
    if set(runtime_exit) != {"present", "kind", "finalSequence", "failure"} or runtime_exit["kind"] not in {"completed", "waiting_for_input", "failed", "blocked", "cancelled", "unknown"}:
        raise ContractError("evidence_runtime_exit_invalid")
    if not isinstance(evidence["runtimeEventIngress"], dict) or set(evidence["runtimeEventIngress"]).difference({"kindCounts", "diagnostics"}) or "kindCounts" not in evidence["runtimeEventIngress"]:
        raise ContractError("evidence_runtime_ingress_invalid")
    if "diagnostics" in evidence["runtimeEventIngress"]:
        _validate_runtime_diagnostics(evidence["runtimeEventIngress"]["diagnostics"])
    audit = evidence["planeOperationAudit"]
    if not isinstance(audit, list) or len(audit) != len(_LIVE_OPERATION_IDS):
        raise ContractError("evidence_operation_audit_count_invalid")
    for row in audit:
        if not isinstance(row, dict) or set(row).difference({"targetDigest"}) != {"operationId", "status", "errorCode", "count"} or row["status"] not in _LIVE_OPERATION_STATUSES or type(row["count"]) is not int or not 0 <= row["count"] <= 8:
            raise ContractError("evidence_operation_audit_invalid")
        if "targetDigest" in row:
            _hash(row["targetDigest"], "evidence_operation_audit_targetDigest")
    publication = evidence["explicitPublication"]
    if not isinstance(publication, dict) or set(publication) != {"count", "refs"} or type(publication["count"]) is not int or not 0 <= publication["count"] <= 8 or not isinstance(publication["refs"], list) or len(publication["refs"]) != publication["count"]:
        raise ContractError("evidence_publication_invalid")
    replay = evidence["replay"]
    if not isinstance(replay, dict) or set(replay) != {"status", "providerAccess", "sameInvocation", "sameIdempotencyKey", "new"} or replay["providerAccess"] != "disabled":
        raise ContractError("evidence_replay_invalid")
    if replay["status"] not in {"passed", "not_eligible"}:
        raise ContractError("evidence_replay_status_invalid")
    if replay["status"] == "passed" and (replay["sameInvocation"] is not True or replay["sameIdempotencyKey"] is not True):
        raise ContractError("evidence_replay_binding_invalid")
    if replay["status"] == "not_eligible" and (replay["sameInvocation"] is not False or replay["sameIdempotencyKey"] is not False):
        raise ContractError("evidence_replay_binding_invalid")
    new = replay["new"]
    if not isinstance(new, dict) or any(type(value) is not int or value != 0 for value in new.values()):
        raise ContractError("evidence_replay_effect_invalid")


def _validate_commission_evidence(value: Any, *, status: str) -> None:
    rows = value
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4:
        raise ContractError("evidence_commission_rows_invalid")
    ids = set()
    for row in rows:
        item = _object(row, "evidence_commission")
        required = {"id", "status", "run", "invocation", "providerAttempts", "scenarioGate", "routeEvidence", "replay"}
        if set(item) != required or not isinstance(item["id"], str) or not _SAFE_REF_RE.fullmatch(item["id"]):
            raise ContractError("evidence_commission_fields_invalid")
        if item["id"] in ids or item["status"] not in {"passed", "failed"}:
            raise ContractError("evidence_commission_identity_invalid")
        ids.add(item["id"])
        if status == "passed" and item["status"] != "passed":
            raise ContractError("evidence_commission_failed")
        if item["status"] == "passed":
            _validate_scenario_gate(item["scenarioGate"])
            _object(item["routeEvidence"], "evidence_commission_route_evidence")
            replay = _object(item["replay"], "evidence_commission_replay")
            if replay.get("status") != "passed" or replay.get("providerAccess") != "disabled":
                raise ContractError("evidence_commission_replay_failed")
        if not isinstance(item["providerAttempts"], list) or len(item["providerAttempts"]) > 32:
            raise ContractError("evidence_commission_attempts_invalid")


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
    "scenarioGate",
    "commissionEvidence",
    "terminalLifecycle",
}
_FAILURE_REQUIRED_TOP_LEVEL_FIELDS = _FAILURE_TOP_LEVEL_FIELDS - {
    "providerRelay", "scenario", "scenarioGate", "commissionEvidence", "terminalLifecycle"
}
_FAILURE_STAGES = {
    "initialization",
    "compose",
    "audit-bootstrap-pre-migrate",
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
    "RuntimeContractError",
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
    if "setupError" in evidence:
        _validate_setup_error(evidence["setupError"])
    if "terminalLifecycle" in evidence:
        _validate_terminal_lifecycle(evidence["terminalLifecycle"])

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
    host_failure_classes = {"transport_unavailable", "callback_exception"}
    prepared_call_reasons = {
        "unknown",
        "consumed",
        "binding_mismatch",
        "digest_mismatch",
        "malformed",
    }
    host_failure_diagnostic_fields = {"callbackPhase", "operationRefDigest"}
    if (
        set(failure).difference(
            required_failure_fields
            | {
                "reasonCause",
                "hostOperationFailure",
                "providerAttemptRef",
                "providerEventRef",
                "callbackPhase",
                "operationRefDigest",
                "codeModeHostStatus",
                "codeModeFailureClass",
                "codeModeErrorClass",
                "runtimePhase",
                "exceptionClass",
                "childDiagnostic",
                "routeDiagnostic",
            }
        )
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
    for field, prefix in (("providerAttemptRef", "provider-attempt:"), ("providerEventRef", "provider-event:")):
        if field in failure:
            _safe_ref(failure[field], f"evidence_failure_{field}")
            if not failure[field].startswith(prefix):
                raise ContractError(f"evidence_failure_{field}_prefix_invalid")
    top_level_diagnostic_fields = {"callbackPhase", "operationRefDigest"}.intersection(failure)
    if top_level_diagnostic_fields and top_level_diagnostic_fields != {"callbackPhase", "operationRefDigest"}:
        raise ContractError("evidence_failure_diagnostic_fields_invalid")
    if top_level_diagnostic_fields:
        if failure["callbackPhase"] not in {"before_host_call", "host_return", "model_observation_emit", "adapter_event"}:
            raise ContractError("evidence_failure_callback_phase_invalid")
        digest = failure["operationRefDigest"]
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ContractError("evidence_failure_operation_ref_digest_invalid")
    code_mode_fields = {"codeModeHostStatus", "codeModeFailureClass"}
    present_code_mode_fields = code_mode_fields.intersection(failure)
    if present_code_mode_fields and present_code_mode_fields != code_mode_fields:
        raise ContractError("evidence_failure_code_mode_diagnostic_fields_invalid")
    if present_code_mode_fields:
        if failure["codeModeHostStatus"] not in {
            "ok",
            "replayed",
            "denied",
            "conflict",
            "unavailable",
            "invalid",
        }:
            raise ContractError("evidence_failure_code_mode_status_invalid")
        if failure["codeModeFailureClass"] not in {
            "code_mode",
            "callback",
            "transport",
            "contract",
            "unknown",
        }:
            raise ContractError("evidence_failure_code_mode_class_invalid")
    if "codeModeErrorClass" in failure:
        if present_code_mode_fields != code_mode_fields:
            raise ContractError("evidence_failure_code_mode_diagnostic_fields_invalid")
        if (
            not isinstance(failure["codeModeErrorClass"], str)
            or failure["codeModeErrorClass"] not in _CODE_MODE_ERROR_CLASSES
        ):
            raise ContractError("evidence_failure_code_mode_error_class_invalid")
    runtime_diagnostic_fields = {"runtimePhase", "exceptionClass"}
    present_runtime_diagnostic_fields = runtime_diagnostic_fields.intersection(failure)
    if present_runtime_diagnostic_fields and present_runtime_diagnostic_fields != runtime_diagnostic_fields:
        raise ContractError("evidence_failure_runtime_diagnostic_fields_invalid")
    if present_runtime_diagnostic_fields:
        if failure["runtimePhase"] not in {"agent_initialization", "tool_configuration", "conversation", "unknown"}:
            raise ContractError("evidence_failure_runtime_phase_invalid")
        if failure["exceptionClass"] not in {
            "ModuleNotFoundError",
            "ImportError",
            "PermissionError",
            "MemoryError",
            "TimeoutError",
            "OSError",
            "RuntimeError",
            "ValueError",
            "TypeError",
            "KeyError",
            "AttributeError",
            "APIConnectionError",
            "APIError",
            "APIResponseValidationError",
            "APIStatusError",
            "APITimeoutError",
            "AuthenticationError",
            "BadRequestError",
            "ConflictError",
            "InternalServerError",
            "NotFoundError",
            "PermissionDeniedError",
            "RateLimitError",
            "UnprocessableEntityError",
            "ConnectTimeout",
            "PoolTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "Unknown",
        }:
            raise ContractError("evidence_failure_exception_class_invalid")
    if "childDiagnostic" in failure:
        _validate_child_diagnostic(failure["childDiagnostic"], "evidence_failure_child_diagnostic")
    if "hostOperationFailure" in failure:
        host_failure = _object(failure["hostOperationFailure"], "evidence_host_operation_failure")
        if (
            set(host_failure).difference(
                host_failure_fields
                | host_failure_diagnostic_fields
                | {"preparedCallInvalidReason", "failureClass", "shapeDiagnostic", "codeModeErrorClass"}
            )
            or not host_failure_fields.issubset(host_failure)
        ):
            raise ContractError("evidence_host_operation_failure_fields_invalid")
        diagnostic_fields = set(host_failure).intersection(host_failure_diagnostic_fields)
        if diagnostic_fields and diagnostic_fields != host_failure_diagnostic_fields:
            raise ContractError("evidence_host_operation_failure_diagnostic_fields_invalid")
        if host_failure["status"] not in {"denied", "conflict", "unavailable", "invalid"}:
            raise ContractError("evidence_host_operation_failure_status_invalid")
        if host_failure["codeModePhase"] not in {"host_callback", "unavailable"}:
            raise ContractError("evidence_host_operation_failure_phase_invalid")
        _safe_operation_id(host_failure["operationId"], "evidence_host_operation_failure_operationId")
        for field in ("attemptRef", "receiptRef", "errorCode"):
            _safe_ref(host_failure[field], f"evidence_host_operation_failure_{field}")
        if "failureClass" in host_failure and host_failure["failureClass"] not in host_failure_classes:
            raise ContractError("evidence_host_operation_failure_class_invalid")
        if (
            "codeModeErrorClass" in host_failure
            and (
                not isinstance(host_failure["codeModeErrorClass"], str)
                or host_failure["codeModeErrorClass"] not in _CODE_MODE_ERROR_CLASSES
            )
        ):
            raise ContractError("evidence_host_operation_failure_code_mode_error_class_invalid")
        if "preparedCallInvalidReason" in host_failure and (
            host_failure["errorCode"] != "PREPARED_CALL_INVALID"
            or host_failure["preparedCallInvalidReason"] not in prepared_call_reasons
        ):
            raise ContractError("evidence_host_operation_failure_prepared_call_reason_invalid")
        if "shapeDiagnostic" in host_failure:
            if host_failure["errorCode"] != "PREPARED_CALL_INVALID":
                raise ContractError("evidence_host_operation_failure_shape_diagnostic_invalid")
            if _bounded_prepared_shape_diagnostic(host_failure["shapeDiagnostic"]) is None:
                raise ContractError("evidence_host_operation_failure_shape_diagnostic_invalid")
        if diagnostic_fields:
            if host_failure["callbackPhase"] not in {"before_host_call", "host_return", "model_observation_emit", "adapter_event"}:
                raise ContractError("evidence_host_operation_failure_callback_phase_invalid")
            digest = host_failure["operationRefDigest"]
            if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ContractError("evidence_host_operation_failure_operation_ref_digest_invalid")

    if "routeDiagnostic" in failure:
        _validate_manager_route_diagnostic(failure["routeDiagnostic"])

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
        host_diagnostic_fields = {"callbackPhase", "operationRefDigest"}
        runtime_diagnostic_fields = {"runtimePhase", "exceptionClass"}
        runtime_failure_diagnostic_fields = host_diagnostic_fields | {
            "codeModeHostStatus",
            "codeModeFailureClass",
            "codeModeErrorClass",
        } | runtime_diagnostic_fields | {"childDiagnostic"}
        if set(runtime_failure).difference({"code", "retryable", "cause"} | runtime_failure_diagnostic_fields) or not {
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
        present_host_diagnostic_fields = host_diagnostic_fields.intersection(runtime_failure)
        if present_host_diagnostic_fields and present_host_diagnostic_fields != host_diagnostic_fields:
            raise ContractError("evidence_runtime_exit_failure_diagnostic_fields_invalid")
        if present_host_diagnostic_fields:
            if runtime_failure["callbackPhase"] not in {"before_host_call", "host_return", "model_observation_emit", "adapter_event"}:
                raise ContractError("evidence_runtime_exit_failure_callback_phase_invalid")
            digest = runtime_failure["operationRefDigest"]
            if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ContractError("evidence_runtime_exit_failure_operation_ref_digest_invalid")
        code_mode_fields = {"codeModeHostStatus", "codeModeFailureClass"}
        present_code_mode_fields = code_mode_fields.intersection(runtime_failure)
        if present_code_mode_fields and present_code_mode_fields != code_mode_fields:
            raise ContractError("evidence_runtime_exit_failure_code_mode_diagnostic_fields_invalid")
        if present_code_mode_fields:
            if runtime_failure["codeModeHostStatus"] not in {
                "ok",
                "replayed",
                "denied",
                "conflict",
                "unavailable",
                "invalid",
            }:
                raise ContractError("evidence_runtime_exit_failure_code_mode_status_invalid")
            if runtime_failure["codeModeFailureClass"] not in {
                "code_mode",
                "callback",
                "transport",
                "contract",
                "unknown",
            }:
                raise ContractError("evidence_runtime_exit_failure_code_mode_class_invalid")
        if "codeModeErrorClass" in runtime_failure:
            if present_code_mode_fields != code_mode_fields:
                raise ContractError("evidence_runtime_exit_failure_code_mode_diagnostic_fields_invalid")
            if (
                not isinstance(runtime_failure["codeModeErrorClass"], str)
                or runtime_failure["codeModeErrorClass"] not in _CODE_MODE_ERROR_CLASSES
            ):
                raise ContractError("evidence_runtime_exit_failure_code_mode_error_class_invalid")
        present_runtime_diagnostic_fields = runtime_diagnostic_fields.intersection(runtime_failure)
        if present_runtime_diagnostic_fields and present_runtime_diagnostic_fields != runtime_diagnostic_fields:
            raise ContractError("evidence_runtime_exit_failure_runtime_diagnostic_fields_invalid")
        if present_runtime_diagnostic_fields:
            if runtime_failure["runtimePhase"] not in {"agent_initialization", "tool_configuration", "conversation", "unknown"}:
                raise ContractError("evidence_runtime_exit_failure_runtime_phase_invalid")
            if runtime_failure["exceptionClass"] not in {
                "ModuleNotFoundError",
                "ImportError",
                "PermissionError",
                "MemoryError",
                "TimeoutError",
                "OSError",
                "RuntimeError",
                "ValueError",
                "TypeError",
                "KeyError",
                "AttributeError",
                "APIConnectionError",
                "APIError",
                "APIResponseValidationError",
                "APIStatusError",
                "APITimeoutError",
                "AuthenticationError",
                "BadRequestError",
                "ConflictError",
                "InternalServerError",
                "NotFoundError",
                "PermissionDeniedError",
                "RateLimitError",
                "UnprocessableEntityError",
                "ConnectTimeout",
                "PoolTimeout",
                "ReadTimeout",
                "WriteTimeout",
                "Unknown",
            }:
                raise ContractError("evidence_runtime_exit_failure_exception_class_invalid")
        if "childDiagnostic" in runtime_failure:
            _validate_child_diagnostic(
                runtime_failure["childDiagnostic"],
                "evidence_runtime_exit_failure_child_diagnostic",
            )

    ingress = _object(evidence["runtimeEventIngress"], "evidence_runtime_ingress")
    if set(ingress).difference({"kindCounts", "diagnostics"}) or "kindCounts" not in ingress:
        raise ContractError("evidence_runtime_ingress_fields_invalid")
    counts = _object(ingress["kindCounts"], "evidence_runtime_ingress_counts")
    if set(counts).difference(_LIVE_RUNTIME_EVENT_KINDS) or any(
        type(count) is not int or not 0 <= count <= 256 for count in counts.values()
    ):
        raise ContractError("evidence_runtime_ingress_invalid")
    if "diagnostics" in ingress:
        _validate_runtime_diagnostics(ingress["diagnostics"])

    attempts = evidence["providerAttempts"]
    if not isinstance(attempts, list) or len(attempts) > 32:
        raise ContractError("evidence_provider_attempts_invalid")
    previous_sequence = 0
    for row in attempts:
        attempt = _object(row, "evidence_provider_attempt")
        base_fields = {"sequence", "phase", "upstreamInitiated", "statusClass", "errorCode"}
        if set(attempt) not in (base_fields, base_fields | {"reasonSubreason"}):
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
        if "reasonSubreason" in attempt:
            _validate_live_provider_attempt_reason(attempt["statusClass"], attempt["reasonSubreason"])
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
        if set(operation).difference({"targetDigest"}) != {"operationId", "status", "errorCode", "count"} or (
            operation["operationId"] != operation_id
            or operation["status"] not in _LIVE_OPERATION_STATUSES
            or operation["errorCode"] is not None
            and operation["errorCode"] not in _LIVE_OPERATION_ERROR_CODES
            or type(operation["count"]) is not int
            or not 0 <= operation["count"] <= 8
        ):
            raise ContractError("evidence_operation_audit_invalid")
        if "targetDigest" in operation:
            _hash(operation["targetDigest"], "evidence_operation_audit_targetDigest")
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
    if "scenarioGate" in evidence:
        _validate_scenario_gate(evidence["scenarioGate"])
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
    if evidence.get("schemaVersion") == "plane-agent-g4/live-runner-failure/v1":
        required = {"schemaVersion", "status", "phase", "errorClass", "exitCode", "reasonCategory", "stderrSha256"}
        optional = {"missingModule", "missingPathClass", "childPhase", "setupError"}
        if set(evidence).difference(required | optional):
            raise ContractError("runner_failure_receipt_fields_invalid")
        _exact(evidence["status"], "failed", "runner_failure_receipt_status")
        if evidence["phase"] not in {
            "initialization",
            "credential-staging",
            "credential-bind-preflight",
            "credential-state-volume",
            "compose",
            "audit-bootstrap-pre-migrate",
            "audit-bootstrap",
            "migrate",
            "runtime-start",
            "runtime-health",
            "api-invocation",
            "capacity-lease",
        }:
            raise ContractError("runner_failure_receipt_phase_invalid")
        if evidence["errorClass"] not in {
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
            "unavailable",
            "unspecified",
        }:
            raise ContractError("runner_failure_receipt_error_class_invalid")
        if type(evidence["exitCode"]) is not int or not 1 <= evidence["exitCode"] <= 255:
            raise ContractError("runner_failure_receipt_exit_code_invalid")
        if evidence["reasonCategory"] != "unavailable" and evidence["reasonCategory"] not in {
            "docker_mount_target_read_only",
            "docker_mount_invalid",
            "docker_mount_source_unavailable",
            "docker_mount_permission_denied",
            "docker_network_configuration_invalid",
            "docker_image_unavailable",
            "docker_container_start_failed",
            "docker_precontainer_failure",
            "runtime_contract_failure",
        }:
            raise ContractError("runner_failure_receipt_reason_category_invalid")
        if not isinstance(evidence["stderrSha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", evidence["stderrSha256"]):
            raise ContractError("runner_failure_receipt_stderr_sha256_invalid")
        if "missingModule" in evidence and (
            evidence["errorClass"] != "ModuleNotFoundError"
            or not isinstance(evidence["missingModule"], str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,127}", evidence["missingModule"])
        ):
            raise ContractError("runner_failure_receipt_missing_module_invalid")
        boundary_fields = {"missingPathClass", "childPhase"}.intersection(evidence)
        if boundary_fields and boundary_fields != {"missingPathClass", "childPhase"}:
            raise ContractError("runner_failure_receipt_boundary_fields_invalid")
        if "missingPathClass" in evidence and evidence["missingPathClass"] not in {
            "api_startup",
            "scenario_module_artifact",
            "runtime_executable",
            "secret_mount",
            "child_process",
            "unclassified",
        }:
            raise ContractError("runner_failure_receipt_missing_path_class_invalid")
        if "childPhase" in evidence and evidence["childPhase"] not in {
            "api_startup",
            "scenario_import",
            "runtime_start",
            "secret_bind",
            "child_process",
            "unknown",
        }:
            raise ContractError("runner_failure_receipt_child_phase_invalid")
        if "missingPathClass" in evidence and "childPhase" in evidence:
            expected_phase = {
                "api_startup": "api_startup",
                "scenario_module_artifact": "scenario_import",
                "runtime_executable": "runtime_start",
                "secret_mount": "secret_bind",
                "child_process": "child_process",
                "unclassified": "unknown",
            }[evidence["missingPathClass"]]
            if evidence["childPhase"] != expected_phase:
                raise ContractError("runner_failure_receipt_child_phase_mismatch")
        if "setupError" in evidence:
            _validate_setup_error(evidence["setupError"])
        return {
            "evidenceSha256": hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
            "collected": 0,
            "passed": 0,
        }
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
    if "terminalLifecycle" in evidence:
        _validate_terminal_lifecycle(evidence["terminalLifecycle"])
    if "commissionEvidence" in evidence:
        _validate_commission_evidence(evidence["commissionEvidence"], status="passed")
    readback = _object(_required(evidence, "readback", "evidence"), "evidence_readback")
    generic = "scenario" in evidence and isinstance(evidence["scenario"], dict) and "actual" in evidence["scenario"]
    if generic:
        _validate_scenario_readback(readback)
    else:
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
    evidence_threshold_profile = _required(threshold_result, "profile", "evidence_thresholds")
    if evidence_threshold_profile != authority_info["thresholdProfile"] and evidence_threshold_profile not in _LIVE_OBSERVATION_THRESHOLD_PROFILES:
        raise ContractError("evidence_threshold_profile_mismatch")
    _exact(_required(threshold_result, "approved", "evidence_thresholds"), authority_info["thresholds"], "evidence_approved_thresholds")
    observed = _object(_required(threshold_result, "observed", "evidence_thresholds"), "evidence_observed_thresholds")
    permitted_rate = _number(observed, "permittedSuccessRate", "evidence_observed_thresholds")
    denied_rate = _number(observed, "deniedRejectionRate", "evidence_observed_thresholds")
    latency = _number(observed, "latencyP95Ms", "evidence_observed_thresholds")
    error_rate = _number(observed, "errorRate", "evidence_observed_thresholds")
    approved = authority_info["thresholds"]
    if not generic and (permitted_rate < approved["permittedSuccessRateMin"] or denied_rate < approved["deniedRejectionRateMin"]):
        raise ContractError("evidence_threshold_rate_failed")
    if not generic and (latency > approved["maxLatencyP95Ms"] or error_rate > approved["maxErrorRate"]):
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

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
    }
    for key in BINDING_FIELDS:
        if key == "runtimeImageDigest":
            _digest(binding[key], f"manifest_{key}")
        elif key in {"runtimeImageTag", "runtimeContract"}:
            if not isinstance(binding[key], str) or not binding[key]:
                raise ContractError(f"manifest_{key}_invalid")
        else:
            _git_sha(binding[key], f"manifest_{key}")
    return binding


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
        if set(row) != {"revision", "imageDigest", "contract"}:
            raise ContractError(f"rollback_{name}_{service}_fields_mismatch")
        result[service] = {
            "revision": _required(row, "revision", f"{name}_{service}"),
            "imageDigest": _required(row, "imageDigest", f"{name}_{service}"),
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

    current_services = _rollback_services(current, "rollback_current")
    previous_services = _rollback_services(previous, "rollback_previous")
    expected_contracts = {
        service: ROLLBACK_RUNTIME_CONTRACT if service in {"supervisor", "agent-runtime"} else ROLLBACK_OPERATION_CONTRACT
        for service in ROLLBACK_SERVICE_NAMES
    }
    for service in ROLLBACK_SERVICE_NAMES:
        _rollback_exact(current_services[service]["revision"], current_parent, f"current_{service}_revision")
        _rollback_exact(current_services[service]["imageDigest"], pins["runtimeImageDigest"], f"current_{service}_imageDigest")
        _rollback_exact(current_services[service]["contract"], expected_contracts[service], f"current_{service}_contract")

    evidence = _git_text_at(root, g3_baseline, binding["acceptedEvidence"])
    accepted_g3 = {
        "hermesCommit": _shell_assignment(evidence, "HERMES_COMMIT"),
        "mcpGitlink": _shell_assignment(evidence, "MCP_COMMIT"),
        "sdkGitlink": _shell_assignment(evidence, "SDK_COMMIT"),
        "imageDigest": _shell_assignment(evidence, "API_TEST_IMAGE_DIGEST"),
    }
    # Hermes is part of the runtime image and may advance for a candidate
    # while rollback still targets the immutable accepted-G3 service image.
    # The accepted G3 Hermes value remains evidence for that previous image;
    # only shared client gitlinks must remain equal across the two bindings.
    for key in ("mcpGitlink", "sdkGitlink"):
        _rollback_exact(accepted_g3[key], pins[key], f"accepted_g3_{key}")
    for service in ROLLBACK_SERVICE_NAMES:
        _rollback_exact(previous_services[service]["revision"], g3_baseline, f"previous_{service}_revision")
        _rollback_exact(previous_services[service]["imageDigest"], accepted_g3["imageDigest"], f"previous_{service}_imageDigest")
        _rollback_exact(previous_services[service]["contract"], expected_contracts[service], f"previous_{service}_contract")

    strategy = _object(_required(fixture, "strategy", "rollback"), "rollback_strategy")
    _rollback_exact(strategy.get("migration"), ROLLBACK_MIGRATION, "strategy_migration")
    _rollback_exact(strategy.get("reverseMigrationAllowed"), False, "strategy_reverseMigrationAllowed")
    runbook_text = (root / _required(manifest, "runbook", "manifest")).read_text(encoding="utf-8")
    validate_rollback_runbook(runbook_text, manifest, fixture)
    return {"current": current, "previous": previous, "acceptedG3": accepted_g3}


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
    if set(provider) != {"name", "model"}:
        raise ContractError(f"{name}_fields_mismatch")
    result = {key: _required(provider, key, name) for key in ("name", "model")}
    if any(not isinstance(item, str) or not item for item in result.values()):
        raise ContractError(f"{name}_invalid")
    return result


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
        if not isinstance(row["id"], str) or not row["id"]:
            raise ContractError(f"{name}_{key}_id_invalid")
        result[key] = {"id": row["id"], "expectedStatus": expected_status}
    return result


def validate_authority(
    authority: dict[str, Any],
    manifest: dict[str, Any],
    candidate: str,
    expected_candidate: str,
    command: str,
) -> dict[str, Any]:
    _git_sha(expected_candidate, "expectedCandidate")
    _exact(candidate, expected_candidate, "candidate_expected")
    _exact(_required(authority, "schemaVersion", "authority"), "plane-agent-g4/live-authority/v1", "authority_schema")
    _exact(_required(authority, "expectedCandidate", "authority"), expected_candidate, "authority_expected_candidate")
    _exact(_required(authority, "purpose", "authority"), "g4-live-evaluation", "authority_purpose")
    authority_id = _required(authority, "authorityId", "authority")
    if not isinstance(authority_id, str) or not authority_id:
        raise ContractError("authority_id_invalid")
    issued = _parse_time(_required(authority, "issuedAt", "authority"), "authority_issuedAt")
    expires = _parse_time(_required(authority, "expiresAt", "authority"), "authority_expiresAt")
    if expires <= issued or expires <= datetime.now(timezone.utc):
        raise ContractError("authority_expired_or_invalid_window")
    _bool(authority, "fallbackAllowed", "authority", False)
    binding = _object(_required(authority, "binding", "authority"), "authority_binding")
    expected = exact_binding(manifest, candidate)
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
    return {
        "authorityId": authority_id,
        "binding": binding,
        "provider": _provider(binding["provider"], "authority_provider"),
        "thresholdProfile": threshold_profile,
        "thresholds": thresholds,
        "canaries": canaries,
        "providerRelay": provider_relay,
    }


def validate_config(config: dict[str, Any], authority_info: dict[str, Any], command: str) -> None:
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
    _exact(config_provider_relay, authority_info["providerRelay"], "config_provider_relay")
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


def validate_evidence(
    evidence_text: str,
    manifest: dict[str, Any],
    authority_info: dict[str, Any],
    config: dict[str, Any],
    candidate: str,
) -> dict[str, Any]:
    if SECRET_FIELD_RE.search(evidence_text):
        raise ContractError("evidence_contains_sensitive_field")
    try:
        evidence = json.loads(evidence_text.strip())
    except json.JSONDecodeError as exc:
        raise ContractError("evidence_must_be_one_json_object") from exc
    if not isinstance(evidence, dict):
        raise ContractError("evidence_must_be_one_json_object")
    _exact(_required(evidence, "schemaVersion", "evidence"), "plane-agent-g4/live-evidence/v1", "evidence_schema")
    _exact(_required(evidence, "status", "evidence"), "passed", "evidence_status")
    expected = exact_binding(manifest, candidate)
    _exact(_required(evidence, "binding", "evidence"), expected, "evidence_binding")
    evidence_provider_relay = _provider_relay(evidence["providerRelay"], "evidence_provider_relay") if "providerRelay" in evidence else None
    _exact(evidence_provider_relay, authority_info["providerRelay"], "evidence_provider_relay")
    if evidence_provider_relay is not None and evidence_provider_relay["hermesHookStatus"] != "integrated":
        raise ContractError("evidence_provider_relay_hook_not_integrated")
    _exact(_required(evidence, "provider", "evidence"), {**authority_info["provider"], "fallbackUsed": False}, "evidence_provider")
    canaries = _object(_required(evidence, "canaries", "evidence"), "evidence_canaries")
    for key, expected_status in (("permitted", "allowed"), ("denied", "denied")):
        row = _object(_required(canaries, key, "evidence_canaries"), f"evidence_canaries_{key}")
        if row.get("id") != authority_info["canaries"][key]["id"] or row.get("status") != expected_status or row.get("passed") is not True:
            raise ContractError(f"evidence_{key}_canary_failed")
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
    if audit.get("passed") is not True or version.get("passed") is not True:
        raise ContractError("evidence_audit_or_version_readback_failed")
    if not isinstance(audit.get("eventCount"), int) or audit["eventCount"] < 1:
        raise ContractError("evidence_audit_readback_empty")
    _exact(version.get("binding"), expected, "evidence_version_binding")
    summary = _summary(_required(evidence, "summary", "evidence"), "evidence_summary")
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
    evidence = validate_evidence(evidence_path.read_text(encoding="utf-8"), manifest, authority_info, config, candidate)
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
        )
        validate_config(config, authority_info, args.command)
        if args.config_only:
            result = {"evidenceSha256": "not_run", "collected": 0, "passed": 0}
        else:
            if args.evidence is None:
                raise ContractError("evidence_path_required")
            result = validate_evidence(
                args.evidence.read_text(encoding="utf-8"),
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

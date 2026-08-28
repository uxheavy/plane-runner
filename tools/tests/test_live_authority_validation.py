# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from validate_agent_g4_live import (
    ContractError,
    EXPECTED_PROVIDER_DESCRIPTOR,
    RUNTIME_PROVIDER_ENV_FIELDS,
    _provider_relay,
    project_provider_relay,
    provider_relay_descriptor,
    validate_authority,
    validate_config,
    validate_runtime_provider_environment,
)


CANDIDATE = "a" * 40
COMMAND = "python3 approved_live_probe.py --result-json"


def _inputs():
    manifest = {
        "candidateBinding": {
            "mode": "exact-single-child",
            "acceptedG3Baseline": "b" * 40,
            "parentCommit": "c" * 40,
        },
        "pins": {
            "hermesCommit": "d" * 40,
            "mcpGitlink": "e" * 40,
            "sdkGitlink": "f" * 40,
            "runtimeImageTag": "plane-agent-runtime:test",
            "runtimeImageDigest": "sha256:" + "1" * 64,
            "runtimeImageRevision": "2" * 40,
            "runtimeContract": "plane.agent-runtime/v1",
            "apiArtifact": {
                "imageTag": "plane-agent-api:test",
                "imageDigest": "sha256:" + "3" * 64,
                "sourceRevision": "4" * 40,
                "contract": "plane.operation/v1",
            },
        },
    }
    binding = {
        "candidateCommit": CANDIDATE,
        "g3Baseline": "b" * 40,
        "hermesCommit": "d" * 40,
        "mcpGitlink": "e" * 40,
        "sdkGitlink": "f" * 40,
        "runtimeImageTag": "plane-agent-runtime:test",
        "runtimeImageDigest": "sha256:" + "1" * 64,
        "runtimeImageRevision": "2" * 40,
        "runtimeContract": "plane.agent-runtime/v1",
        "apiArtifact": manifest["pins"]["apiArtifact"],
        "commandSha256": hashlib.sha256(COMMAND.encode()).hexdigest(),
        "provider": dict(EXPECTED_PROVIDER_DESCRIPTOR),
        "thresholdProfile": "live-approved-v1",
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
        "authorityId": authority["authorityId"],
        "mode": "live",
        "offline": False,
        "fallbackAllowed": False,
        "expectedCandidate": CANDIDATE,
        "binding": binding,
        "provider": {**binding["provider"], "fallbackUsed": False},
        "thresholdProfile": binding["thresholdProfile"],
        "thresholds": binding["thresholds"],
        "canaries": {key: value["id"] for key, value in binding["canaries"].items()},
        "requiredReadbacks": ["audit", "version"],
    }
    project_provider_relay(authority, config)
    return manifest, authority, config


def test_provider_relay_projection_uses_independent_canonical_values() -> None:
    _, authority, config = _inputs()

    assert authority["providerRelay"] == provider_relay_descriptor()
    assert config["providerRelay"] == provider_relay_descriptor()
    assert authority["providerRelay"] is not config["providerRelay"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("transport", "TCP"),
        ("childNetworkPolicy", "bridge"),
        ("externalEgressOwner", "child"),
        ("hostGatewaySeparate", False),
        ("hermesHookStatus", "unknown"),
    ),
)
def test_provider_relay_rejects_authority_boundary_drift(
    field: str, value: object
) -> None:
    relay = provider_relay_descriptor()
    relay[field] = value

    with pytest.raises(ContractError):
        _provider_relay(relay, "provider_relay")


def test_authority_and_config_require_the_same_integrated_relay() -> None:
    manifest, authority, config = _inputs()
    authority_info = validate_authority(
        authority,
        manifest,
        CANDIDATE,
        CANDIDATE,
        COMMAND,
        require_provider_relay=True,
    )
    validate_config(config, authority_info, COMMAND, require_provider_relay=True)

    config["providerRelay"]["hermesHookStatus"] = "pending"
    with pytest.raises(ContractError, match="config_provider_relay_mismatch"):
        validate_config(config, authority_info, COMMAND, require_provider_relay=True)


@pytest.mark.parametrize("document", ["authority", "config"])
def test_preflight_rejects_missing_provider_relay(document: str) -> None:
    manifest, authority, config = _inputs()
    if document == "authority":
        authority.pop("providerRelay")
        with pytest.raises(ContractError, match="authority_provider_relay_missing"):
            validate_authority(
                authority,
                manifest,
                CANDIDATE,
                CANDIDATE,
                COMMAND,
                require_provider_relay=True,
            )
        return

    authority_info = validate_authority(
        authority,
        manifest,
        CANDIDATE,
        CANDIDATE,
        COMMAND,
        require_provider_relay=True,
    )
    config.pop("providerRelay")
    with pytest.raises(ContractError, match="config_provider_relay_missing"):
        validate_config(config, authority_info, COMMAND, require_provider_relay=True)


def test_runtime_provider_environment_must_match_every_authorized_field() -> None:
    provider = dict(EXPECTED_PROVIDER_DESCRIPTOR)
    environment = {
        environment_key: provider[provider_key]
        for environment_key, provider_key in RUNTIME_PROVIDER_ENV_FIELDS.items()
    }
    validate_runtime_provider_environment(provider, environment)

    for field in environment:
        mismatched = dict(environment)
        mismatched[field] += "-mismatch"
        with pytest.raises(ContractError, match="runtime_provider_"):
            validate_runtime_provider_environment(provider, mismatched)


def test_authority_rejects_identity_and_fallback_policy_changes() -> None:
    manifest, authority, _ = _inputs()
    with pytest.raises(ContractError, match="candidate_expected"):
        validate_authority(authority, manifest, CANDIDATE, "9" * 40, COMMAND)

    authority["fallbackAllowed"] = True
    with pytest.raises(ContractError, match="authority_fallbackAllowed_must_be_false"):
        validate_authority(authority, manifest, CANDIDATE, CANDIDATE, COMMAND)

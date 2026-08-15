from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


TOOLS = Path(__file__).parents[1]
sys.path.insert(0, str(TOOLS))

import agent_g4_live_scenario as scenario  # noqa: E402
import validate_agent_g4_live as validator  # noqa: E402


def descriptor_for(scenario_id: str = "worker") -> dict[str, object]:
    return {
        "schemaVersion": "plane.agent-scenario/v1",
        "scenarioId": scenario_id,
        "actor": {"role": scenario.SCENARIO_ROLES[scenario_id]},
        "profile": {
            "name": f"{scenario_id} profile",
            "instructions": "Use the assigned Plane tools and report bounded evidence.",
            "modelPolicy": {
                "provider": "openai-codex",
                "model": "gpt-5.6-luna",
                "reasoning": "xhigh",
                "fallbackAllowed": False,
            },
        },
        "assignment": {
            "targetRef": scenario.ASSIGNED_WORK_ITEM_ALIAS,
            "objective": "Complete the assigned scenario objective.",
            "acceptanceCriteria": ["The assigned acceptance evidence is recorded."],
            "contextRefs": ["memory:scenario-context"],
        },
        "prompt": "Perform the assigned scenario and retain only the requested evidence.",
    }


def descriptor_bytes(value: dict[str, object]) -> tuple[bytes, str]:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


def write_owner_only(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    path.chmod(0o600)


@pytest.mark.parametrize("scenario_id", ["worker", "manager", "operator"])
def test_supported_persona_descriptors_are_typed_and_bound(scenario_id: str) -> None:
    raw, digest = descriptor_bytes(descriptor_for(scenario_id))
    parsed = scenario.parse_descriptor_bytes(raw, digest)

    assert parsed.scenario_id == scenario_id
    assert parsed.actor_role == scenario.SCENARIO_ROLES[scenario_id]
    assert parsed.profile.model_policy.model == "gpt-5.6-luna"
    assert parsed.profile.model_policy.reasoning == "xhigh"
    assert parsed.profile.model_policy.fallback_allowed is False
    assert parsed.evidence()["descriptorDigest"] == digest


def test_expected_predicates_are_bounded_and_retained_in_evidence() -> None:
    value = descriptor_for()
    value["expected"] = {
        "operationOutcomes": [{"operationId": "work_item.read", "outcome": "success"}],
        "evidenceKinds": ["operation-audit", "publication"],
    }
    raw, digest = descriptor_bytes(value)
    parsed = scenario.parse_descriptor_bytes(raw, digest)

    assert parsed.evidence()["expected"] == value["expected"]


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: value.update({"unexpected": True}), "scenario_descriptor_fields_mismatch"),
        (lambda value: value.update({"scenarioId": "unsupported"}), "scenario_id_unsupported"),
        (lambda value: value["actor"].update({"role": "delegator"}), "scenario_actor_role_mismatch"),
        (
            lambda value: value["profile"]["modelPolicy"].update({"reasoning": "high"}),
            "scenario_model_policy_invalid",
        ),
        (
            lambda value: value["profile"].update({"instructions": "contains an api key"}),
            "scenario_profile_instructions_contains_forbidden_value",
        ),
    ],
)
def test_descriptor_validation_fails_closed(mutator, reason: str) -> None:
    value = descriptor_for()
    mutator(value)
    raw, digest = descriptor_bytes(value)

    with pytest.raises(scenario.ScenarioError, match=reason):
        scenario.parse_descriptor_bytes(raw, digest)


def test_descriptor_rejects_oversized_prompt() -> None:
    value = descriptor_for()
    value["prompt"] = "x" * (scenario.MAX_PROMPT_BYTES + 1)
    raw, digest = descriptor_bytes(value)

    with pytest.raises(scenario.ScenarioError, match="scenario_prompt_too_large"):
        scenario.parse_descriptor_bytes(raw, digest)


def test_descriptor_rejects_wrong_digest_duplicate_fields_and_oversized_arrays() -> None:
    value = descriptor_for()
    raw, _ = descriptor_bytes(value)
    with pytest.raises(scenario.ScenarioError, match="scenario_digest_mismatch"):
        scenario.parse_descriptor_bytes(raw, "0" * 64)

    duplicate = (
        b'{"schemaVersion":"plane.agent-scenario/v1","scenarioId":"worker",'
        b'"scenarioId":"worker"}'
    )
    with pytest.raises(scenario.ScenarioError, match="scenario_duplicate_field"):
        scenario.parse_descriptor_bytes(duplicate, hashlib.sha256(duplicate).hexdigest())

    oversized = descriptor_for()
    oversized["assignment"]["acceptanceCriteria"] = ["criterion"] * (scenario.MAX_ACCEPTANCE_ITEMS + 1)
    raw, digest = descriptor_bytes(oversized)
    with pytest.raises(scenario.ScenarioError, match="scenario_assignment_acceptance_invalid_list"):
        scenario.parse_descriptor_bytes(raw, digest)


def test_descriptor_path_requires_owner_only_non_symlink_file(tmp_path: Path) -> None:
    value = descriptor_for()
    raw, digest = descriptor_bytes(value)
    path = tmp_path / "scenario.json"
    write_owner_only(path, raw)
    assert scenario.load_descriptor(path, digest).scenario_id == "worker"

    path.chmod(0o640)
    with pytest.raises(scenario.ScenarioError, match="scenario_path_not_owner_only"):
        scenario.load_descriptor(path, digest)

    path.chmod(0o600)
    link = tmp_path / "scenario-link.json"
    link.symlink_to(path)
    with pytest.raises(scenario.ScenarioError, match="scenario_path_not_owner_file"):
        scenario.load_descriptor(link, digest)

    escaped = tmp_path / ".." / tmp_path.name / "scenario.json"
    with pytest.raises(scenario.ScenarioError, match="scenario_path_invalid"):
        scenario.load_descriptor(escaped, digest)


def test_s00_remains_the_no_descriptor_default_and_runner_propagates_mount_contract() -> None:
    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")

    assert 'if not path and not digest:\n        return None' in invoke
    assert 'profile_persona = ""' in invoke
    validation = runner.index("agent_g4_live_scenario.py")
    provider = runner.index('PROVIDER_SECRET_SOURCE="${PLANE_G4_PROVIDER_SECRET_SOURCE')
    assert runner.index("validate_agent_g4_live.py") < validation < provider
    assert "G4_SCENARIO_DESCRIPTOR=/run/plane-scenario/descriptor.json" in runner
    assert "G4_SCENARIO_SHA256=" in runner
    assert "dst=/run/plane-scenario,readonly,volume-nocopy" in runner


def test_identity_profile_assignment_and_evidence_are_separate() -> None:
    value = descriptor_for("manager")
    raw, digest = descriptor_bytes(value)
    parsed = scenario.parse_descriptor_bytes(raw, digest)
    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")

    assert parsed.actor_role == "delegator"
    assert parsed.profile.name == "manager profile"
    assert parsed.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
    assert 'credential_ref="plane-credential:g4-live"' in invoke
    assert 'actor_role = AgentRole.WORKER' in invoke
    assert '"delegator": AgentRole.DELEGATOR' in invoke
    assert "else scenario.assignment.target_ref" in invoke
    assert "scenario.assignment.target_ref == ASSIGNED_WORK_ITEM_ALIAS" in invoke
    assert 'evidence["scenario"] = scenario.evidence()' in invoke
    assert "permission" not in json.dumps(value)
    validator._validate_scenario_projection(parsed.evidence())
    invalid_projection = parsed.evidence()
    invalid_projection["actorRole"] = "worker"
    with pytest.raises(validator.ContractError, match="evidence_scenario_identity_invalid"):
        validator._validate_scenario_projection(invalid_projection)


def _binding_manifest(candidate: str, mode: str, disposable: dict[str, object] | None = None) -> dict[str, object]:
    parent = "b" * 40
    hermes = "c" * 40
    runtime_files = {"apps/api/plane/agent/runtime/service.py": "d" * 64}
    runtime_source_digest = hashlib.sha256(
        json.dumps(runtime_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    pins = {
        "hermesCommit": hermes,
        "mcpGitlink": "e" * 40,
        "sdkGitlink": "f" * 40,
        "runtimeImageTag": "plane-agent-runtime:test",
        "runtimeImageDigest": "sha256:" + "1" * 64,
        "runtimeImageRevision": candidate,
        "runtimeContract": "plane.agent-runtime/v1",
        "apiArtifact": {
            "imageTag": "plane-api:test",
            "imageDigest": "sha256:" + "2" * 64,
            "sourceRevision": candidate,
            "contract": "plane.operation/v1",
        },
    }
    manifest: dict[str, object] = {
        "candidateBinding": {
            "mode": mode,
            "acceptedG3Baseline": "a" * 40,
            "parentCommit": parent,
        },
        "pins": pins,
    }
    if disposable is not None:
        manifest["disposableBinding"] = disposable
    if mode == "disposable-exact-candidate":
        manifest["disposableBinding"] = {
            "mode": "exact-api-runtime-candidate",
            "candidateCommit": candidate,
            "apiSourceRevision": candidate,
            "runtimeRevision": candidate,
            "hermesCommit": hermes,
            "hermesRemote": "github.com/uxheavy/hermes-agent",
            "runtimeSourceDigest": runtime_source_digest,
            "runtimeFiles": runtime_files,
        }
    return manifest


def test_exact_single_child_binding_accepts_direct_child(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = "1" * 40
    parent = "b" * 40
    monkeypatch.setattr(validator, "_commit_parents", lambda _root, _candidate: [parent])

    validator.validate_candidate_binding(_binding_manifest(candidate, "exact-single-child"), candidate, Path.cwd())


def test_commit_parent_lookup_reads_one_exact_git_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "--quiet"], check=True)
    subprocess.run(git + ["config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(git + ["config", "user.name", "Test"], check=True)
    (repo / "file").write_text("base", encoding="utf-8")
    subprocess.run(git + ["add", "file"], check=True)
    subprocess.run(git + ["commit", "--quiet", "-m", "base"], check=True)
    parent = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    (repo / "file").write_text("child", encoding="utf-8")
    subprocess.run(git + ["commit", "--quiet", "-am", "child"], check=True)
    candidate = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()

    assert validator._commit_parents(repo, candidate) == [parent]


@pytest.mark.parametrize(
    "parents",
    [["i" * 40], ["b" * 40, "a" * 40]],
)
def test_exact_single_child_binding_rejects_advanced_or_non_single_parent(
    monkeypatch: pytest.MonkeyPatch, parents: list[str]
) -> None:
    candidate = "1" * 40
    monkeypatch.setattr(validator, "_commit_parents", lambda _root, _candidate: parents)

    with pytest.raises(validator.ContractError, match="candidate_is_not_exact_single_child"):
        validator.validate_candidate_binding(_binding_manifest(candidate, "exact-single-child"), candidate, Path.cwd())


def test_disposable_exact_candidate_requires_complete_binding_and_accepts_exact_binding() -> None:
    candidate = "1" * 40
    missing = _binding_manifest(candidate, "disposable-exact-candidate")
    missing.pop("disposableBinding")
    with pytest.raises(validator.ContractError, match="disposable_binding_required"):
        validator.validate_candidate_binding(missing, candidate, Path.cwd())

    exact = _binding_manifest(candidate, "disposable-exact-candidate")
    validator.validate_candidate_binding(exact, candidate, Path.cwd())

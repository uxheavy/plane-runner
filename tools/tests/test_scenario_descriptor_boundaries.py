# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

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
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    return raw, hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("scenario_id", ["worker", "manager", "operator"])
def test_supported_personas_parse_to_typed_bound_descriptors(scenario_id: str) -> None:
    raw, digest = descriptor_bytes(descriptor_for(scenario_id))
    parsed = scenario.parse_descriptor_bytes(raw, digest)

    assert parsed.scenario_id == scenario_id
    assert parsed.actor_role == scenario.SCENARIO_ROLES[scenario_id]
    assert parsed.profile.model_policy == scenario.ModelPolicy(
        "openai-codex", "gpt-5.6-luna", "xhigh", False
    )
    assert parsed.evidence()["descriptorDigest"] == digest


def test_assigned_target_alias_binds_only_its_versioned_namespace() -> None:
    fresh = "issue:fresh-synthetic-issue"

    assert scenario.bind_assigned_work_item_target("fixture:assigned-work-item-r2", fresh) == fresh
    assert scenario.bind_assigned_work_item_target(scenario.ASSIGNED_WORK_ITEM_ALIAS, fresh) == fresh
    assert (
        scenario.bind_assigned_work_item_target("fixture:assigned-work-items-r2", fresh)
        == "fixture:assigned-work-items-r2"
    )
    assert (
        scenario.bind_assigned_work_item_target("fixture:assigned-work-item/r2", fresh)
        == "fixture:assigned-work-item/r2"
    )
    assert scenario.bind_assigned_work_item_target("issue:caller-supplied", fresh) == "issue:caller-supplied"


def test_commission_selection_preserves_digest_and_binds_only_one_assignment() -> None:
    value = descriptor_for()
    value["commissions"] = [
        {
            "id": "first",
            "assignment": {
                "targetRef": scenario.ASSIGNED_WORK_ITEM_ALIAS,
                "objective": "first",
                "acceptanceCriteria": ["first"],
                "contextRefs": [],
            },
            "expected": {"operationOutcomes": [], "evidenceKinds": [], "routeChecks": ["W01"]},
        },
        {
            "id": "context-governance",
            "assignment": {
                "targetRef": scenario.ASSIGNED_WORK_ITEM_ALIAS,
                "objective": "context",
                "acceptanceCriteria": ["context"],
                "contextRefs": [],
            },
            "expected": {
                "operationOutcomes": [],
                "evidenceKinds": [],
                "routeChecks": ["W05", "W06"],
            },
        },
    ]
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    selected = scenario.select_commission(parsed, "context-governance")

    assert selected.selected_commission_id == "context-governance"
    assert selected.commissions == ()
    assert selected.descriptor_digest == parsed.descriptor_digest
    assert selected.expected["routeChecks"] == ["W05", "W06"]
    assert selected.evidence()["commissionId"] == "context-governance"
    with pytest.raises(scenario.ScenarioError, match="scenario_commission_not_found"):
        scenario.select_commission(parsed, "missing")


def test_runtime_selection_projects_the_named_manager_commission() -> None:
    raw = (TOOLS / "agent-g4-manager-v1.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    selected = scenario.select_runtime_descriptor(parsed, "planning-delegation")

    assert selected.commissions == ()
    assert selected.selected_commission_id == "planning-delegation"
    assert selected.descriptor_digest == parsed.descriptor_digest
    assert selected.assignment == parsed.commissions[0].assignment


def test_commission_binding_keeps_shared_profile_and_applies_toolset_override() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    identity, code_mode, context = (
        scenario.commission_descriptor(parsed, commission) for commission in parsed.commissions
    )

    assert identity.profile == context.profile == parsed.profile
    assert code_mode.profile == replace(parsed.profile, model_toolset="code_mode_only")
    assert identity.assignment.target_ref == code_mode.assignment.target_ref == context.assignment.target_ref
    assert identity.expected["routeChecks"] != code_mode.expected["routeChecks"]
    assert code_mode.expected["routeChecks"] != context.expected["routeChecks"]
    assert identity.commissions == code_mode.commissions == context.commissions == ()


def test_manager_commissions_require_the_declared_first_operation_and_a_terminal() -> None:
    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text())
    value["commissions"][0]["expected"]["operationOutcomes"][0]["operationId"] = "catalog.search"
    with pytest.raises(scenario.ScenarioError, match="first_operation_invalid"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text())
    value["commissions"][0]["expected"]["operationOutcomes"] = [
        {"operationId": "search_workspace", "outcome": "success", "count": 1}
    ]
    value["commissions"][0]["expected"]["productEvents"] = []
    with pytest.raises(scenario.ScenarioError, match="terminal_missing"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_manager_commissions_accept_an_explicit_failure_terminal() -> None:
    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text())
    expected = value["commissions"][0]["expected"]
    expected["operationOutcomes"] = [
        {"operationId": "search_workspace", "outcome": "success", "count": 1}
    ]
    expected["productEvents"] = [{"kind": "run_failure", "count": 1}]

    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    assert parsed.commissions[0].expected["productEvents"] == [{"kind": "run_failure", "count": 1}]


def test_route_check_collection_rejects_duplicates_and_unsupported_values() -> None:
    value = descriptor_for("operator")
    value["expected"] = {
        "operationOutcomes": [],
        "evidenceKinds": [],
        "routeChecks": ["O01", "O01"],
    }
    with pytest.raises(scenario.ScenarioError, match="scenario_expected_route_check_duplicate"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    value["expected"]["routeChecks"] = ["O02"]
    with pytest.raises(scenario.ScenarioError, match="scenario_expected_route_check_unsupported"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_setup_controls_and_evidence_are_typed_without_retaining_raw_input() -> None:
    value = descriptor_for("manager")
    value["setup"] = {
        "preconditions": ["isolated_workspace", "fresh_assignment", "separate_runtime_service"],
        "actors": [{"ref": "actor:operator", "role": "worker", "displayName": "Operator"}],
        "lineage": {
            "parentActorRef": "actor:primary",
            "childActorRef": "actor:operator",
            "scopeRefs": ["scope:issue"],
            "budget": 2,
        },
        "schedule": {
            "actorRef": "actor:operator",
            "cron": "* * * * *",
            "timezone": "UTC",
            "startsAt": "2026-08-15T00:00:00Z",
            "fireAt": None,
        },
    }
    value["controls"] = {
        "continuation": {
            "trigger": "human_input",
            "input": "Continue the bounded run.",
            "checkpointRef": "checkpoint:one",
        },
        "cancellation": {"timing": "after_publication", "reason": "Stop after publication."},
        "fault": {"selection": "none"},
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    evidence = parsed.evidence()

    assert parsed.setup.lineage.child_ref == "actor:operator"
    assert parsed.setup.schedule.timezone == "UTC"
    assert evidence["controls"]["continuation"]["inputDigest"]
    assert "input" not in evidence["controls"]["continuation"]
    validator._validate_scenario_projection(evidence)


def test_related_actor_setup_does_not_invent_delegator_lineage() -> None:
    value = descriptor_for("operator")
    value["setup"] = {
        "preconditions": ["assigned_work_item", "fresh_assignment"],
        "actors": [{"ref": "actor:evaluator", "role": "evaluator", "displayName": "Evaluator"}],
    }

    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    assert parsed.actor_role == "worker"
    assert parsed.setup.actors[0].role == "evaluator"
    assert parsed.setup.lineage is None


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: value["setup"].update({"unknown": True}), "scenario_setup_fields_mismatch"),
        (lambda value: value["controls"].update({"unknown": True}), "scenario_controls_fields_mismatch"),
        (
            lambda value: value["controls"]["fault"].update({"selection": "arbitrary"}),
            "scenario_controls_fault_invalid",
        ),
    ],
)
def test_setup_and_control_fields_fail_closed(mutator, reason: str) -> None:
    value = descriptor_for("operator")
    value["setup"] = {"actors": [], "preconditions": []}
    value["controls"] = {"fault": {"selection": "none"}}
    mutator(value)

    with pytest.raises(scenario.ScenarioError, match=reason):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_continuation_and_revision_are_exclusive_and_faults_are_finite() -> None:
    value = descriptor_for("operator")
    value["controls"] = {
        "continuation": {"trigger": "continuation", "input": "continue"},
        "revision": {"input": "revise", "decisionNote": "operator revision"},
        "fault": {"selection": "runtime_unavailable"},
    }
    with pytest.raises(scenario.ScenarioError, match="continuation_revision_conflict"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    value["controls"].pop("revision")
    assert scenario.parse_descriptor_bytes(*descriptor_bytes(value)).controls.fault == "runtime_unavailable"
    value["controls"]["fault"]["selection"] = "provider_outcome_unknown"
    with pytest.raises(scenario.ScenarioError, match="scenario_controls_fault_invalid"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


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
        (
            lambda value: value["profile"].update({"toolPresentation": {"unexpected": []}}),
            "scenario_profile_tool_presentation_fields_mismatch",
        ),
    ],
)
def test_descriptor_fields_fail_closed(mutator, reason: str) -> None:
    value = descriptor_for()
    mutator(value)

    with pytest.raises(scenario.ScenarioError, match=reason):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_descriptor_bounds_reject_oversized_prompt_and_arrays() -> None:
    value = descriptor_for()
    value["prompt"] = "x" * (scenario.MAX_PROMPT_BYTES + 1)
    with pytest.raises(scenario.ScenarioError, match="scenario_prompt_too_large"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    value = descriptor_for()
    value["assignment"]["acceptanceCriteria"] = ["criterion"] * (scenario.MAX_ACCEPTANCE_ITEMS + 1)
    with pytest.raises(scenario.ScenarioError, match="scenario_assignment_acceptance_invalid_list"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_descriptor_integrity_rejects_wrong_digest_and_duplicate_fields() -> None:
    raw, _ = descriptor_bytes(descriptor_for())
    with pytest.raises(scenario.ScenarioError, match="scenario_digest_mismatch"):
        scenario.parse_descriptor_bytes(raw, "0" * 64)

    duplicate = b'{"schemaVersion":"plane.agent-scenario/v1","scenarioId":"worker","scenarioId":"worker"}'
    with pytest.raises(scenario.ScenarioError, match="scenario_duplicate_field"):
        scenario.parse_descriptor_bytes(duplicate, hashlib.sha256(duplicate).hexdigest())


def test_descriptor_path_requires_an_absolute_owner_only_regular_file(tmp_path: Path) -> None:
    raw, digest = descriptor_bytes(descriptor_for())
    path = tmp_path / "scenario.json"
    path.write_bytes(raw)
    path.chmod(0o600)
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


def test_descriptor_identity_projects_to_the_validator_contract() -> None:
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(descriptor_for("manager")))
    projection = parsed.evidence()

    assert parsed.actor_role == "delegator"
    assert parsed.profile.name == "manager profile"
    assert parsed.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
    validator._validate_scenario_projection(projection)

    projection["actorRole"] = "worker"
    with pytest.raises(validator.ContractError, match="evidence_scenario_identity_invalid"):
        validator._validate_scenario_projection(projection)


def test_expected_predicates_round_trip_in_descriptor_evidence() -> None:
    value = descriptor_for()
    value["expected"] = {
        "operationOutcomes": [{"operationId": "work_item.read", "outcome": "success"}],
        "evidenceKinds": ["audit", "publication"],
    }

    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))

    assert parsed.evidence()["expected"] == value["expected"]

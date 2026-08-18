from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOLS = Path(__file__).parents[1]
sys.path.insert(0, str(TOOLS))

import agent_g4_live_scenario as scenario  # noqa: E402
import agent_g4_scenario_modules as scenario_modules  # noqa: E402
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


def test_versioned_assigned_work_item_alias_binds_to_the_fresh_issue_ref() -> None:
    fresh_issue_ref = "issue:fresh-synthetic-issue"

    assert scenario.bind_assigned_work_item_target(
        "fixture:assigned-work-item-r2", fresh_issue_ref
    ) == fresh_issue_ref
    assert scenario.bind_assigned_work_item_target(
        scenario.ASSIGNED_WORK_ITEM_ALIAS, fresh_issue_ref
    ) == fresh_issue_ref
    assert scenario.bind_assigned_work_item_target(
        "fixture:assigned-work-items-r2", fresh_issue_ref
    ) == "fixture:assigned-work-items-r2"
    assert scenario.bind_assigned_work_item_target(
        "fixture:assigned-work-item/r2", fresh_issue_ref
    ) == "fixture:assigned-work-item/r2"
    assert scenario.bind_assigned_work_item_target(
        "issue:caller-supplied", fresh_issue_ref
    ) == "issue:caller-supplied"


def test_worker_live_descriptor_covers_all_routes_and_uses_gateway_input_names() -> None:
    path = TOOLS / "agent-g4-worker-v6.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    assert parsed.scenario_id == "worker"
    assert [commission.commission_id for commission in parsed.commissions] == [
        "identity-discovery",
        "mutation-composition-publication",
        "context-governance",
    ]
    assert parsed.expected is None
    assert parsed.profile.tool_presentation == (
        "catalog.search",
        "catalog.describe",
        "agent.context.read",
        "search_workspace",
        "work_item.read",
        "work_item.rename",
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    )
    identity = parsed.commissions[0]
    mutation = parsed.commissions[1]
    context = parsed.commissions[2]
    assert {
        commission.commission_id: commission.expected["routeChecks"]
        for commission in parsed.commissions
    } == {
        "identity-discovery": ["W01", "W02"],
        "mutation-composition-publication": ["W03", "W04", "W07", "W08"],
        "context-governance": ["W05", "W06", "W07", "W08"],
    }
    assert "workItemReadCall.input.preparedCallRef unchanged" in identity.assignment.objective
    assert "execute_code" in mutation.assignment.objective
    assert "export default async function" in mutation.assignment.objective
    assert 'host.call_plane_operation("work_item.rename"' in mutation.assignment.objective
    assert "hermes_tools.plane_operation" not in mutation.assignment.objective
    mutation_route_guidance = scenario.model_route_expectations(mutation.expected)
    read_guidance = next(
        item for item in mutation_route_guidance if "invoke work_item.read" in item
    )
    assert "workItemReadCall object verbatim" in read_guidance
    assert "complete tool arguments" in read_guidance
    assert "action, operationRef" in read_guidance
    assert "exactly those three top-level tool keys" in read_guidance
    assert "opaque input.preparedCallRef" in read_guidance
    assert "keep only preparedCallRef inside input" in read_guidance
    assert "put the workItemReadCall object inside input" in read_guidance
    assert "rename operationRef to operation_ref" in read_guidance
    assert "alter or replay the preparedCallRef" in read_guidance
    assert "reconstruct project_id or issue_id" in read_guidance
    assert "Do not wrap it" in read_guidance
    assert "reconstruct project_id or issue_id from targetRef" in read_guidance
    assert "workItemReadCall input.preparedCallRef verbatim" in read_guidance
    assert "do not copy raw workItemReadInput" in read_guidance
    assert "do not reconstruct, translate, or infer" in read_guidance
    rename_guidance = next(
        item for item in mutation_route_guidance if "invoke execute_code" in item
    )
    assert rename_guidance.startswith("Route step 3: invoke execute_code exactly 1 time(s)")
    assert "restricted Code Mode composition" in rename_guidance
    assert "not by a native model mutation" in rename_guidance
    assert "execute_code" in rename_guidance
    assert "export a default function" in rename_guidance
    assert 'host.call_plane_operation("work_item.rename"' in rename_guidance
    assert "hermes_tools.plane_operation" not in rename_guidance
    assert '"subject_user_ref":"{{subjectUserRef}}"' in context.assignment.objective
    assert "private memory" in context.assignment.objective
    assert "exact current invocation run_ref" in parsed.profile.instructions
    assert "never invent, copy, or substitute another run reference" in parsed.profile.instructions
    assert "after a terminal or rejected outcome callback, do not retry either terminal operation" in parsed.profile.instructions
    assert "agent.context.read returns the complete subject-bound projection in one response" in parsed.profile.instructions
    assert "bounded TypeScript module exporting a default function" in parsed.profile.instructions
    assert "host.call_plane_operation(operationId, input, idempotencyKey, correlationId)" in parsed.profile.instructions
    assert "hermes_tools.plane_operation" not in parsed.profile.instructions
    assert "exactly one artifact and exactly one evidence item" in context.assignment.objective
    assert "exactly one artifact and exactly one evidence item" in context.assignment.acceptance_criteria[-1]


def test_select_commission_keeps_source_digest_and_removes_other_commissions() -> None:
    raw, digest = descriptor_bytes(
        {
            **descriptor_for("worker"),
            "commissions": [
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
                    "expected": {"operationOutcomes": [], "evidenceKinds": [], "routeChecks": ["W05", "W06"]},
                },
            ],
        }
    )
    parsed = scenario.parse_descriptor_bytes(raw, digest)
    selected = scenario.select_commission(parsed, "context-governance")

    assert selected.selected_commission_id == "context-governance"
    assert selected.commissions == ()
    assert selected.descriptor_digest == digest
    assert selected.expected["routeChecks"] == ["W05", "W06"]
    assert selected.evidence()["commissionId"] == "context-governance"

    with pytest.raises(scenario.ScenarioError, match="scenario_commission_not_found"):
        scenario.select_commission(parsed, "missing")


def test_single_manager_descriptor_ignores_per_run_commission_identity() -> None:
    path = TOOLS / "agent-g4-manager-v1.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    selected = scenario.select_runtime_descriptor(parsed, "manager-m01-m08-v23-primary-20260818-01")

    assert selected.commissions == ()
    assert selected.selected_commission_id is None
    assert selected.descriptor_digest == parsed.descriptor_digest
    assert selected.assignment == parsed.assignment


def test_operator_live_descriptor_covers_exact_synthetic_omar_routes() -> None:
    path = TOOLS / "agent-g4-operator-v6.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    assert parsed.scenario_id == "operator"
    assert [commission.commission_id for commission in parsed.commissions] == [
        "presentation-and-sdk-identity",
        "lease-and-replay-boundaries",
        "failure-and-budget-reconciliation",
        "ingress-health-and-rollback",
    ]
    assert parsed.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
    assert parsed.profile.model_policy == scenario.ModelPolicy("openai-codex", "gpt-5.6-luna", "xhigh", False)
    assert "pass that entry's exact operationId to catalog.describe" in parsed.profile.instructions
    assert "never pass operationRef or an operation: reference" in parsed.profile.instructions
    assert parsed.profile.tool_presentation == (
        "catalog.search",
        "catalog.describe",
        "search_workspace",
        "work_item.read",
        "work_item.rename",
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    )

    route_checks = {
        check
        for commission in parsed.commissions
        for check in commission.expected["routeChecks"]
    }
    assert route_checks == {"O01", "O03", "O04", "O05", "O06", "O07", "O08", "O09"}
    assert "O02" not in route_checks
    assert all(
        commission.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
        and commission.expected["productEvents"] == [
            {"kind": "publication", "count": 1},
            {"kind": "outcome_submission", "count": 1},
        ]
        for commission in parsed.commissions
    )
    for commission in parsed.commissions:
        validator._validate_scenario_projection(scenario.commission_descriptor(parsed, commission).evidence())
    assert "Tool presentation is descriptive only" in parsed.profile.instructions
    assert "outcome_unknown" in parsed.prompt


def test_operator_route_checks_reject_duplicates() -> None:
    value = descriptor_for("operator")
    value["expected"] = {
        "operationOutcomes": [],
        "evidenceKinds": [],
        "routeChecks": ["O01", "O01"],
    }
    raw, digest = descriptor_bytes(value)

    with pytest.raises(scenario.ScenarioError, match="scenario_expected_route_check_duplicate"):
        scenario.parse_descriptor_bytes(raw, digest)

    value["expected"]["routeChecks"] = ["O02"]
    raw, digest = descriptor_bytes(value)
    with pytest.raises(scenario.ScenarioError, match="scenario_expected_route_check_unsupported"):
        scenario.parse_descriptor_bytes(raw, digest)
def test_manager_live_descriptor_covers_elena_routes_and_fixed_model_policy() -> None:
    path = TOOLS / "agent-g4-manager-v1.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    assert parsed.scenario_id == "manager"
    assert parsed.actor_role == "delegator"
    assert parsed.profile.name == "Elena Manager"
    assert parsed.profile.model_policy.provider == "openai-codex"
    assert parsed.profile.model_policy.model == "gpt-5.6-luna"
    assert parsed.profile.model_policy.reasoning == "xhigh"
    assert parsed.profile.model_policy.fallback_allowed is False
    assert parsed.expected["routeChecks"] == [f"M{index:02d}" for index in range(1, 9)]
    assert parsed.setup.lineage.parent_ref == "actor:primary"
    assert parsed.setup.schedule.timezone == "America/Los_Angeles"
    assert "workflow product" in parsed.prompt
    validator._validate_scenario_projection(parsed.evidence())


def test_manager_assignment_context_refs_are_context_scoped_and_lineage_scope_is_separate() -> None:
    descriptor = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text(encoding="utf-8"))

    assignment_context_refs = descriptor["assignment"]["contextRefs"]
    lineage_scope_refs = descriptor["setup"]["lineage"]["scopeRefs"]

    assert assignment_context_refs
    assert all(ref.startswith("context:") for ref in assignment_context_refs)
    assert lineage_scope_refs == ["scope:manager-journey"]


def test_manager_route_validator_requires_all_bounded_routes() -> None:
    value = descriptor_for("manager")
    value["expected"] = {
        "operationOutcomes": [],
        "evidenceKinds": [],
        "routeChecks": [f"M{index:02d}" for index in range(1, 9)],
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    projection = parsed.evidence()
    route_fields = validator._MANAGER_ROUTE_BOOLEAN_FIELDS
    projection["actual"] = {
        "operations": [],
        "records": [],
        "productEvents": [],
        "evidenceKinds": [],
        "routeEvidence": {
            "routes": {
                **{route_id: {field: True for field in fields} for route_id, fields in route_fields.items()},
                "replay": {"stateMutations": 0},
            },
            "readback": {
                "assignmentCount": 1,
                "childAssignmentCount": 1,
                "outcomeCount": 2,
                "artifactOutcomeCount": 2,
                "terminalEventCount": 4,
                "governanceReadbackDigest": "0" * 64,
            },
        },
    }
    validator._validate_scenario_projection(projection)


def test_manager_synthetic_fixture_stays_outside_the_production_agent_package() -> None:
    fixture = TOOLS / "agent_g4_manager_route.py"
    production = TOOLS.parent / "apps" / "api" / "plane" / "agent" / "manager_route.py"

    assert fixture.is_file()
    assert not production.exists()
    source = fixture.read_text(encoding="utf-8")
    assert "from plane.agent.lifecycle import" in source
    assert "M01" in source and "M08" in source


def test_manager_hr_setup_is_workspace_scoped_for_chief_of_staff_governance() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text()

    assert 'scenario.scenario_id == "manager" and setup_actor.role == "hr"' in source
    assert "related_project =" in source
    assert "project=related_project" in source


def test_manager_setup_failure_receipt_has_bounded_stage_marker_and_counters() -> None:
    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text()
    runner = (TOOLS / "agent-g4-live.sh").read_text()
    result = (TOOLS / "agent-g4-live-result.py").read_text()

    for marker in (
        'setup_stage = "shared-setup"',
        'setup_stage = "assignment"',
        'setup_stage = "lineage"',
        'setup_stage = "schedule"',
        'setup_stage = "schedule-fire"',
        'event=agent.g4.live.setup-failure/v1 setupError=',
        '"lineageAssignments": 0',
    ):
        assert marker in invoke
    assert 'safe_setup_error()' in runner
    assert '--setup-error "${setup_error}"' in runner
    assert 'parser.add_argument("--setup-error", default="")' in result
    assert 'receipt["setupError"] = bounded_setup_error' in result


def test_manager_fixture_is_staged_into_the_owner_only_scenario_volume() -> None:
    source = (TOOLS / "agent-g4-live.sh").read_text()

    manifest = json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))
    manager = next(item for item in manifest["scenarioModules"] if item["module"] == "agent_g4_manager_route")
    assert manager["runtime"] == "/run/plane-scenario/agent_g4_manager_route.py"
    assert "agent_g4_manager_route" in (TOOLS / "agent_g4_scenario_modules.py").read_text(encoding="utf-8")
    assert "stage_scenario_module" in source
    assert "scenario_module_source_hash_mismatch" in source


def test_live_scenario_module_manifest_binds_every_runtime_import() -> None:
    manifest = TOOLS / "agent-g4-manifest.json"
    modules = scenario_modules.scenario_modules(manifest, TOOLS.parent)

    assert {item["module"] for item in modules} == scenario_modules.REQUIRED_MODULES
    assert all(item["runtime"].startswith("/run/plane-scenario/") for item in modules)
    runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")
    assert "scenario-module-preflight=passed" in runner
    assert "PYTHONPATH=/run/plane-scenario:/workspace/apps/api" in runner


def test_live_scenario_module_manifest_rejects_omitted_manager_route(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))
    manifest["scenarioModules"] = [
        item for item in manifest["scenarioModules"] if item["module"] != "agent_g4_manager_route"
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="required_set_mismatch"):
        scenario_modules.scenario_modules(manifest_path, TOOLS.parent)


def test_live_invocation_loads_scenario_modules_from_the_owner_only_mount() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")

    assert 'scenario_module_root = "/run/plane-scenario"' in source
    assert "spec_from_file_location(module_name, module_path)" in source
    assert '_load_scenario_module("agent_g4_manager_route")' in source
    assert "scenario_module_root_missing" in source


def test_commission_descriptor_keeps_shared_profile_and_binds_each_assignment() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    identity = scenario.commission_descriptor(parsed, parsed.commissions[0])
    mutation = scenario.commission_descriptor(parsed, parsed.commissions[1])
    context = scenario.commission_descriptor(parsed, parsed.commissions[2])
    assert identity.profile == mutation.profile == context.profile == parsed.profile
    assert identity.assignment.target_ref == mutation.assignment.target_ref == context.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
    assert identity.expected["routeChecks"] != mutation.expected["routeChecks"]
    assert mutation.expected["routeChecks"] != context.expected["routeChecks"]
    assert identity.commissions == mutation.commissions == context.commissions == ()


def test_multi_commission_prompt_preserves_the_typed_mutation_route() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_profile_expected_outcomes"),
        None,
    )
    assert helper is not None, (
        "event=worker.assignment.route_prompt actor=worker operation=compose_profile_prompt "
        "risk=required_semantic_mutation_can_be_skipped_before_publication "
        "expected=multi_commission_prompt_preserves_typed_route_guidance "
        "actual=prompt_composition_owner_missing "
        "suggestion=restore_commission_specific_expected_outcomes"
    )
    namespace: dict[str, object] = {}
    exec(
        compile(
            ast.Module(body=[helper], type_ignores=[]),
            str(TOOLS / "agent-g4-live-invoke.py"),
            "exec",
        ),
        namespace,
    )

    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    mutation = scenario.commission_descriptor(parsed, parsed.commissions[1])
    expected = namespace["_profile_expected_outcomes"](mutation)

    assert expected == list(scenario.model_route_expectations(mutation.expected))
    assert "execute_code" in expected[2]
    assert 'host.call_plane_operation("work_item.rename"' in expected[2]
    assert expected[3].startswith("Route step 4: invoke agent.outcome.evaluate")
    assert expected[-2].startswith("Route step 5: invoke agent.outcome.submit")
    assert expected[-1].startswith("Route step 6: invoke agent.outcome.publish")


def test_sequential_commissions_reuse_fixture_preconditions_before_new_run() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_commission_precondition_checks"
    )
    class _ActiveMemberships:
        def filter(self, **_kwargs):
            return self

        def exists(self) -> bool:
            return True

    namespace: dict[str, object] = {
        "WorkspaceMember": SimpleNamespace(objects=_ActiveMemberships()),
        "ProjectMember": SimpleNamespace(objects=_ActiveMemberships()),
    }
    exec(
        compile(
            ast.Module(body=[helper], type_ignores=[]),
            str(TOOLS / "agent-g4-live-invoke.py"),
            "exec",
        ),
        namespace,
    )

    first_setup = SimpleNamespace(id="setup-owner")
    shared = {
        "user": first_setup,
        "workspace": SimpleNamespace(owner_id="setup-owner", id="workspace:first", slug="g4-live-first"),
        "project": SimpleNamespace(id="project:first"),
        "actor": SimpleNamespace(
            workspace_id="workspace:first",
            project_id="project:first",
            principal_id="actor:first",
            principal=SimpleNamespace(is_active=True),
        ),
        "setup_suffix": "first",
    }
    first_assignment = SimpleNamespace(
        pk="assignment:first",
        target_ref="issue:first",
        created_by_id="setup-owner",
        revision=1,
    )
    second_assignment = SimpleNamespace(
        pk="assignment:second",
        target_ref="issue:second",
        created_by_id="setup-owner",
        revision=1,
    )
    relay = {"hostGatewaySeparate": True, "externalEgressOwner": "agent-runtime"}

    first_checks = namespace["_commission_precondition_checks"](shared, first_assignment, relay)
    second_checks = namespace["_commission_precondition_checks"](shared, second_assignment, relay)

    assert first_checks == second_checks == {
        "isolated_workspace": True,
        "assigned_work_item": True,
        "fresh_assignment": True,
        "live_authorization": True,
        "separate_runtime_service": True,
    }
    assert '"setup_suffix": suffix' in source
    assert "setup_cache=setup_cache" in source
    assert "_SHARED_WORKER_SETUP" not in source


def test_failure_commission_aggregate_gate_is_bounded_and_validated() -> None:
    gate = {
        "passed": False,
        "failures": ["commission:identity-discovery"],
        "operations": [],
        "durableRecords": [],
        "productEvents": [],
        "evidenceKinds": [],
    }

    validator._validate_scenario_gate(gate)
    assert "scenarioGate" in validator._FAILURE_TOP_LEVEL_FIELDS


def test_runner_maps_every_finite_related_role_to_the_plane_role() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text()
    expected = {
        "worker": "WORKER",
        "delegator": "DELEGATOR",
        "gardener": "GARDENER",
        "chief_of_staff": "CHIEF_OF_STAFF",
        "hr": "HR",
        "evaluator": "EVALUATOR",
        "custom": "CUSTOM",
    }
    assert set(expected) == scenario._RELATED_ROLES
    for role, plane_role in expected.items():
        assert f'"{role}": AgentRole.{plane_role}' in source


def test_expected_predicates_are_bounded_and_retained_in_evidence() -> None:
    value = descriptor_for()
    value["expected"] = {
        "operationOutcomes": [{"operationId": "work_item.read", "outcome": "success"}],
        "evidenceKinds": ["audit", "publication"],
    }
    raw, digest = descriptor_bytes(value)
    parsed = scenario.parse_descriptor_bytes(raw, digest)

    assert parsed.evidence()["expected"] == value["expected"]


def test_expected_operations_render_as_ordered_model_route_outcomes() -> None:
    expected = {
        "operationOutcomes": [
            {"operationId": "catalog.search", "outcome": "success", "count": 1},
            {"operationId": "catalog.describe", "outcome": "success", "count": 1},
            {"operationId": "agent.context.read", "outcome": "success", "count": 1},
            {"operationId": "agent.outcome.evaluate", "outcome": "denied", "count": 1},
        ]
    }

    assert scenario.model_route_expectations(expected) == (
        "Route step 1: invoke catalog.search exactly 1 time(s) and expect success. After this route call returns, advance immediately to the next route step; do not invoke this operation again for confirmation, inspection, refresh, or retry.",
        "Route step 2: invoke catalog.describe exactly 1 time(s) and expect success. After this route call returns, advance immediately to the next route step; do not invoke this operation again for confirmation, inspection, refresh, or retry. Use the next route operation's exact operationId as input.operation_id; never use operationRef or an operation: prefix.",
        "Route step 3: invoke agent.context.read exactly 1 time(s) and expect success. After this route call returns, advance immediately to the next route step; do not invoke this operation again for confirmation, inspection, refresh, or retry. This one response is the complete subject-bound projection; do not request it again.",
        "Route step 4: invoke agent.outcome.evaluate exactly 1 time(s) and expect denied. After this route call returns, advance immediately to the next route step; do not invoke this operation again for confirmation, inspection, refresh, or retry.",
    )


def test_manager_setup_controls_and_durable_expectations_are_typed() -> None:
    value = descriptor_for("manager")
    value["setup"] = {
        "preconditions": ["isolated_workspace", "fresh_assignment", "separate_runtime_service"],
        "actors": [{"ref": "actor:operator", "role": "worker", "displayName": "Operator"}],
        "lineage": {"parentActorRef": "actor:primary", "childActorRef": "actor:operator", "scopeRefs": ["scope:issue"], "budget": 2},
        "schedule": {"actorRef": "actor:operator", "cron": "* * * * *", "timezone": "UTC", "startsAt": "2026-08-15T00:00:00Z", "fireAt": None},
    }
    value["controls"] = {
        "continuation": {"trigger": "human_input", "input": "Continue the bounded run.", "checkpointRef": "checkpoint:one"},
        "cancellation": {"timing": "after_publication", "reason": "Stop after publication."},
        "fault": {"selection": "none"},
    }
    value["expected"] = {
        "operationOutcomes": [{"operationId": "agent.outcome.publish", "outcome": "success", "count": 1}],
        "evidenceKinds": ["audit", "publication"],
        "durableRecords": [{"kind": "lineage_assignment", "count": 1}],
        "productEvents": [{"kind": "publication", "count": 1}],
    }
    raw, digest = descriptor_bytes(value)
    parsed = scenario.parse_descriptor_bytes(raw, digest)
    assert parsed.actor_role == "delegator"
    assert parsed.setup.lineage is not None and parsed.setup.lineage.child_ref == "actor:operator"
    assert parsed.setup.schedule is not None and parsed.setup.schedule.timezone == "UTC"
    assert parsed.controls.continuation is not None
    assert parsed.evidence()["controls"]["continuation"]["inputDigest"]
    validator._validate_scenario_projection(parsed.evidence())


def test_operator_setup_binds_related_actor_without_delegator_lineage() -> None:
    value = descriptor_for("operator")
    value["setup"] = {
        "preconditions": ["assigned_work_item", "fresh_assignment"],
        "actors": [{"ref": "actor:evaluator", "role": "evaluator", "displayName": "Evaluator"}],
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    assert parsed.actor_role == "worker"
    assert parsed.setup.actors[0].role == "evaluator"


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: value["setup"].update({"unknown": True}), "scenario_setup_fields_mismatch"),
        (lambda value: value["controls"].update({"unknown": True}), "scenario_controls_fields_mismatch"),
        (lambda value: value["controls"]["fault"].update({"selection": "arbitrary"}), "scenario_controls_fault_invalid"),
    ],
)
def test_setup_and_control_unknown_fields_fail_closed(mutator, reason: str) -> None:
    value = descriptor_for("operator")
    value["setup"] = {"actors": [], "preconditions": []}
    value["controls"] = {"fault": {"selection": "none"}}
    mutator(value)
    raw, digest = descriptor_bytes(value)
    with pytest.raises(scenario.ScenarioError, match=reason):
        scenario.parse_descriptor_bytes(raw, digest)


def test_expectations_enforce_actual_audit_receipt_and_product_observations() -> None:
    value = descriptor_for("operator")
    value["expected"] = {
        "operationOutcomes": [{"operationId": "agent.outcome.publish", "outcome": "success"}],
        "evidenceKinds": ["audit"],
        "durableRecords": [{"kind": "publication", "count": 1}],
        "productEvents": [{"kind": "publication", "count": 1}],
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    assert scenario.evaluate_expectations(
        parsed.expected,
        operations=[{"operationId": "agent.outcome.publish", "outcome": "success", "count": 1}],
        records=[{"kind": "publication", "count": 1}],
        product_events=[{"kind": "publication", "count": 1}],
        evidence_kinds=["audit"],
    )["passed"]
    failed = scenario.evaluate_expectations(parsed.expected, operations=[], records=[], product_events=[], evidence_kinds=[])
    assert failed["passed"] is False
    assert "operation:agent.outcome.publish" in failed["failures"]


def test_requested_but_missing_actual_records_and_events_fail_expectations() -> None:
    value = descriptor_for("manager")
    value["expected"] = {
        "operationOutcomes": [],
        "evidenceKinds": ["lineage_assignment", "schedule", "input_event"],
        "durableRecords": [
            {"kind": "lineage_assignment", "count": 1},
            {"kind": "schedule", "count": 1},
            {"kind": "schedule_fire", "count": 1},
            {"kind": "input_event", "count": 1},
        ],
        "productEvents": [{"kind": "input_event", "count": 1}],
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    failed = scenario.evaluate_expectations(
        parsed.expected,
        operations=[],
        records=[
            {"kind": "lineage_assignment", "count": 0},
            {"kind": "schedule", "count": 0},
            {"kind": "schedule_fire", "count": 0},
            {"kind": "input_event", "count": 0},
        ],
        product_events=[{"kind": "input_event", "count": 0}],
        evidence_kinds=[],
    )
    assert failed["passed"] is False
    assert {
        "durableRecords:lineage_assignment",
        "durableRecords:schedule",
        "durableRecords:schedule_fire",
        "durableRecords:input_event",
        "productEvents:input_event",
        "evidence:lineage_assignment",
        "evidence:schedule",
        "evidence:input_event",
    } <= set(failed["failures"])


def test_terminal_product_event_vocabulary_is_finite_and_matches_plane() -> None:
    assert {
        "outcome_submission",
        "run_failure",
        "run_blocker",
        "run_cancellation",
    } <= scenario._PRODUCT_KINDS
    assert "input_request" not in scenario._PRODUCT_KINDS


def test_validator_accepts_actual_scenario_gate_and_rejects_failed_gate() -> None:
    value = descriptor_for("operator")
    value["expected"] = {"operationOutcomes": [], "evidenceKinds": [], "durableRecords": [], "productEvents": []}
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    projection = parsed.evidence()
    projection["actual"] = {"operations": [], "records": [], "productEvents": [], "evidenceKinds": []}
    gate = {"passed": True, "failures": [], "operations": [], "durableRecords": [], "productEvents": [], "evidenceKinds": []}
    validator._validate_scenario_projection(projection)
    validator._validate_scenario_gate(gate)
    gate["passed"] = False
    with pytest.raises(validator.ContractError, match="evidence_scenario_gate_predicate_mismatch"):
        validator._validate_scenario_gate(gate)


def test_revision_binding_is_exclusive_and_fault_selection_is_finite() -> None:
    value = descriptor_for("operator")
    value["controls"] = {
        "continuation": {"trigger": "continuation", "input": "continue"},
        "revision": {"input": "revise", "decisionNote": "operator revision"},
        "fault": {"selection": "runtime_unavailable"},
    }
    with pytest.raises(scenario.ScenarioError, match="scenario_controls_continuation_revision_conflict"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    value["controls"].pop("revision")
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    assert parsed.controls.fault == "runtime_unavailable"
    value["controls"]["fault"]["selection"] = "provider_outcome_unknown"
    with pytest.raises(scenario.ScenarioError, match="scenario_controls_fault_invalid"):
        scenario.parse_descriptor_bytes(*descriptor_bytes(value))


def test_accepted_setup_and_control_fields_reach_existing_runner_owners() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text()
    for marker in (
        "scenario.setup.actors",
        "scenario.setup.preconditions",
        "scenario.setup.lineage",
        "scenario.setup.schedule",
        "scenario.controls.continuation",
        "scenario.controls.revision",
        "scenario.controls.cancellation",
        "scenario.controls.fault",
        "create_actor(",
        "create_profile(",
        "delegate_assignment(",
        "create_schedule(",
        "fire_schedule(",
        "record_input_event(",
        "request_runtime_cancellation(",
        "_scenario_readback(",
        "RunInputEvent.objects.filter(run=run)",
        "OperationGatewayIdempotency.objects.filter(",
        "RunTerminalEvent.objects.filter(run=run, visible=True)",
    ):
        assert marker in source


def test_runner_readback_uses_actual_plane_state_and_finite_product_kinds() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text()
    readback = source.split("def _scenario_readback", 1)[1].split("def _run_continuation_supervisor", 1)[0]
    for marker in (
        "run.invocations.count()",
        "RunInputEvent.objects.filter(run=run)",
        "explicit_publication",
        "RunTerminalEvent.objects.filter(run=run, visible=True)",
        "schedule_fire.state == AgentScheduleFireState.CREATED",
    ):
        assert marker in readback
    assert "input_request" not in readback
    assert '"count": 1' not in readback


def test_worker_publication_readback_uses_explicit_product_projection_not_delivery_intents() -> None:
    source = (TOOLS / "agent-g4-live-invoke.py").read_text()
    readback = source.split("def _scenario_readback", 1)[1].split("def _run_continuation_supervisor", 1)[0]

    assert "explicit_publication=None" in readback
    assert "explicit_publication_expectations" in readback
    assert "OperationGatewayPublication" not in readback


def test_explicit_publication_projection_drives_all_publication_gates_without_delivery_rows() -> None:
    expected = {
        "operationOutcomes": [],
        "evidenceKinds": ["publication"],
        "durableRecords": [{"kind": "publication", "count": 1}],
        "productEvents": [{"kind": "publication", "count": 1}],
    }
    records, product_events, evidence_kinds = scenario.explicit_publication_expectations(
        {"count": 1, "bindings": [{"productKind": "outcome_submission"}]}
    )
    passed = scenario.evaluate_expectations(
        expected,
        operations=[],
        records=records,
        product_events=product_events,
        evidence_kinds=evidence_kinds,
    )
    assert passed["passed"]
    assert records == [{"kind": "publication", "count": 1}]
    assert product_events == [{"kind": "publication", "count": 1}]

    empty_records, empty_events, empty_evidence = scenario.explicit_publication_expectations(
        {"count": 0, "bindings": []}
    )
    failed = scenario.evaluate_expectations(
        expected,
        operations=[],
        records=empty_records,
        product_events=empty_events,
        evidence_kinds=empty_evidence,
    )
    assert failed["passed"] is False
    assert {
        "durableRecords:publication",
        "productEvents:publication",
        "evidence:publication",
    } <= set(failed["failures"])


def test_worker_route_readback_uses_smallest_bounded_owner_projection() -> None:
    source = (TOOLS / "agent_g4_worker_route.py").read_text()

    assert "build_correlation_readback(workspace, run_id=str(run.id), limit=1)" in source
    assert "build_run_readback" not in source
    assert "build_correlation_readback(workspace, run_id=str(run.id), limit=8)" not in source


def test_worker_readback_is_scoped_to_commissions_that_own_w08() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    checks = [commission.expected["routeChecks"] for commission in parsed.commissions]

    assert "W08" not in checks[0]
    assert "W08" in checks[1]
    assert "W08" in checks[2]

    source = (TOOLS / "agent-g4-live-invoke.py").read_text()
    guarded = source.split('context_facts["codeModeControlsPassed"]', 1)[1].split("context_replay_before", 1)[0]
    assert 'if "W08" in route_checks:' in guarded
    assert "worker_readback_facts" in guarded


def test_worker_route_validator_accepts_identity_only_route_evidence() -> None:
    identity_route = {
        "routes": {
            "W01": {
                "actorProfileAssignmentSeparate": True,
                "snapshotBound": True,
                "substitution": {"status": "denied", "errorCode": "NOT_AUTHORIZED", "sideEffects": 0},
            },
            "W02": {
                "catalogSearchBeforeDescribe": True,
                "boundedSearchAndRead": True,
                "hiddenObjectsAbsent": True,
            },
            "replay": {"context": {"memoryRevisions": 0, "skillRevisions": 0, "proposals": 0, "contextReceipts": 0}},
        },
        "readback": {"contextProjectionDigest": "0" * 64},
    }

    validator._validate_worker_route_evidence(identity_route, route_checks={"W01", "W02"})


def test_worker_route_validator_keeps_special_mutation_and_governance_routes_valid() -> None:
    common = {
        "W07": {
            "oneOutcome": True,
            "oneArtifact": True,
            "evidenceAttached": True,
            "onePublishedTerminal": True,
        },
        "W08": {"runReadback": True, "apiCliConsistent": True, "crossWorkspaceDenied": True},
        "replay": {"context": {"memoryRevisions": 0, "skillRevisions": 0, "proposals": 0, "contextReceipts": 0}},
    }
    mutation_route = {
        "routes": {
            "W03": {
                "status": "replayed",
                "semanticDelta": 0,
                "duplicateMutation": 0,
                "httpStatus": 200,
                "receiptRef": "receipt:rename",
                "auditReceiptRef": "audit-receipt:rename",
            },
            "W04": {
                "positiveTypedHostCallback": True,
                "sameGateway": True,
                "failClosedControls": True,
            },
            **common,
        },
        "readback": {"contextProjectionDigest": "0" * 64},
    }
    context_route = {
        "routes": {
            "W05": {
                "contextReceipt": True,
                "privateMemoryPresent": True,
                "subjectPreferencesSeparate": True,
                    "skillProjectionPresent": True,
                    "excludedOtherUserAgentStale": True,
                    "correctContextProjection": True,
                    "otherSubjectIsolated": True,
                    "otherAgentIsolated": True,
                    "losslessRoundTrip": True,
                },
                "W06": {
                    "candidate": True,
                    "candidateNotProjected": True,
                "humanApproved": True,
                "promoted": True,
                "privateAfterPromotion": True,
                "rollbackRevision": True,
                "proposalReplayStable": True,
                "unsupportedSharedDenied": True,
                "workspaceUnreviewedNotPromoted": True,
            },
            **common,
        },
        "readback": {"contextProjectionDigest": "1" * 64},
    }

    validator._validate_worker_route_evidence(
        mutation_route,
        route_checks={"W03", "W04", "W07", "W08"},
    )
    validator._validate_worker_route_evidence(
        context_route,
        route_checks={"W05", "W06", "W07", "W08"},
    )


def test_code_mode_callback_observation_requires_code_source_and_action() -> None:
    from agent_g4_worker_route_observations import has_code_mode_callback

    assert has_code_mode_callback(
        [
            {
                "body": {
                    "payload": {
                        "text": "Plane host code code operation:work_item.rename -> ok"
                    }
                }
            }
        ],
        "work_item.rename",
    )
    assert not has_code_mode_callback(
        [
            {
                "body": {
                    "payload": {
                        "text": "Plane host model mutate operation:work_item.rename -> ok"
                    }
                }
            }
        ],
        "work_item.rename",
    )


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
    assert '"eager_operations": list(scenario.profile.tool_presentation)' in invoke


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
    assert "bind_assigned_work_item_target" in invoke
    assert 'evidence["scenario"] = scenario.evidence()' in invoke
    assert "permission" not in json.dumps(value)
    validator._validate_scenario_projection(parsed.evidence())
    invalid_projection = parsed.evidence()
    invalid_projection["actorRole"] = "worker"
    with pytest.raises(validator.ContractError, match="evidence_scenario_identity_invalid"):
        validator._validate_scenario_projection(invalid_projection)


def test_worker_receipt_requires_bounded_terminal_lifecycle_observation() -> None:
    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    validate = (TOOLS / "validate_agent_g4_live.py").read_text(encoding="utf-8")

    assert "_bounded_terminal_lifecycle_observation" in invoke
    assert '"terminalLifecycle"' in invoke
    assert "terminal lifecycle observation missing" in invoke
    assert "hermes.terminal-lifecycle/v1" in invoke
    assert "def _validate_terminal_lifecycle" in validate


def test_disposable_binding_accepts_staged_code_mode_contracts() -> None:
    candidate = "1" * 40
    manifest = _binding_manifest(candidate, "disposable-exact-candidate")
    binding = manifest["disposableBinding"]
    assert isinstance(binding, dict)
    runtime_files = dict(binding["runtimeFiles"])
    runtime_files["apps/api/plane/agent/code_mode/contracts.py"] = "e" * 64
    binding["runtimeFiles"] = runtime_files
    binding["runtimeSourceDigest"] = hashlib.sha256(
        json.dumps(runtime_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    validator.validate_candidate_binding(manifest, candidate, Path.cwd())


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

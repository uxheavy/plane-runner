from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOLS = Path(__file__).parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "apps" / "api"))

import agent_g4_live_scenario as scenario  # noqa: E402
import agent_g4_operator_route as operator_route  # noqa: E402
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


def _run_code_mode_frames(source: str, callback_handler):
    runner = TOOLS.parent / "apps" / "api" / "plane" / "agent" / "code_mode" / "runner.mjs"
    help_result = subprocess.run(["node", "--help"], check=False, capture_output=True, text=True)
    permission_flag = "--permission" if "--permission" in f"{help_result.stdout}\n{help_result.stderr}" else "--experimental-permission"
    process = subprocess.Popen(
        [
            "node",
            permission_flag,
            "--no-addons",
            "--no-global-search-paths",
            "--experimental-vm-modules",
            "--disable-proto=throw",
            f"--allow-fs-read={runner}",
            "--allow-fs-read=/usr/share/node_modules/typescript",
            str(runner),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    observed = []
    try:
        process.stdin.write(
            json.dumps(
                {
                    "type": "run",
                    "source": source,
                    "input": {},
                    "callbacks": {
                        "search": "search_plane_operations",
                        "describe": "describe_plane_operation",
                        "operation": "call_plane_operation",
                        "spill": "spill_plane_result",
                    },
                }
            )
            + "\n"
        )
        process.stdin.flush()
        while True:
            frame = json.loads(process.stdout.readline())
            if frame["type"] != "callback":
                return observed, frame
            observed.append(frame)
            process.stdin.write(
                json.dumps(
                    {
                        "type": "callback_result",
                        "id": frame["id"],
                        "receipt": callback_handler(frame),
                    }
                )
                + "\n"
            )
            process.stdin.flush()
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


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


def test_code_mode_commission_binds_exact_runtime_values_and_hides_native_rename() -> None:
    path = TOOLS / "agent-g4-worker-v6.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    assert [commission.commission_id for commission in parsed.commissions] == [
        "identity-discovery",
        "code-mode-semantic-rename",
        "context-governance",
    ]
    assert "work_item.rename" not in parsed.profile.tool_presentation
    assert "plane_execute_typescript" not in parsed.profile.tool_presentation
    commission = parsed.commissions[1]
    assert commission.expected["operationOutcomes"] == [
        {"operationId": "catalog.search", "outcome": "success", "count": 1},
        {"operationId": "catalog.describe", "outcome": "success", "count": 1},
        {"operationId": "search_workspace", "outcome": "success", "count": 1},
        {"operationId": "work_item.read", "outcome": "success", "count": 1},
        {"operationId": "work_item.rename", "outcome": "success", "count": 1},
        {"operationId": "agent.outcome.submit", "outcome": "success", "count": 1},
        {"operationId": "agent.outcome.publish", "outcome": "success", "count": 1},
    ]
    assert "{{projectId}}" not in commission.assignment.objective
    assert "{{issueId}}" not in commission.assignment.objective
    assert "{{invocationId}}" not in commission.assignment.objective
    assert "{{newName}}" not in commission.assignment.objective
    assert "preparedCallRef" in commission.assignment.objective
    assert "submit exactly one bounded outcome" in commission.assignment.objective
    identity = parsed.commissions[0]
    assert [item["operationId"] for item in identity.expected["operationOutcomes"]] == [
        "search_workspace",
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    ]
    assert "runtime auto-consume" in identity.assignment.objective


def test_code_mode_runtime_binding_substitutes_every_placeholder_once() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    commission = scenario.commission_descriptor(parsed, parsed.commissions[2])
    bound = scenario.bind_code_mode_runtime_values(
        commission,
        project_id="project-fresh",
        issue_id="issue-fresh",
        invocation_id="invocation-fresh",
        new_name="V36 Code Mode Rename",
    )

    route_guidance = scenario.model_route_expectations(bound.expected)
    route_guidance = tuple(
        scenario.substitute_code_mode_placeholders(item, bound.runtime_bindings)
        for item in route_guidance
    )
    text = "\n".join(
        [bound.assignment.objective, *bound.assignment.acceptance_criteria, bound.prompt, bound.profile.instructions, *route_guidance]
    )
    assert "{{projectId}}" not in text
    assert "{{issueId}}" not in text
    assert "{{invocationId}}" not in text
    assert "{{newName}}" not in text
    assert 'project_id: workItem.project' in text
    assert 'issue_id: workItem.id' in text
    assert "project-fresh" not in text
    assert "issue-fresh" not in text
    assert 'idempotency:invocation-fresh:code-mode-catalog-search' in text
    assert 'idempotency:invocation-fresh:code-mode-catalog-describe' in text
    assert 'idempotency:invocation-fresh:code-mode-search' in text
    assert 'idempotency:invocation-fresh:code-mode-read' in text
    assert '"idempotency:invocation-fresh:code-mode-rename"' in text
    assert '"correlation:invocation-fresh:code-mode-rename"' in text
    assert 'name: "V36 Code Mode Rename"' in text


def test_code_mode_commission_uses_bound_composition_without_native_read_tools() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    mutation = scenario.commission_descriptor(parsed, parsed.commissions[1])
    bound = scenario.bind_code_mode_runtime_values(
        mutation,
        project_id="project-fresh",
        issue_id="issue-fresh",
        invocation_id="invocation-fresh",
        new_name="V60 Code Mode Rename",
    )

    guidance = tuple(
        scenario.substitute_code_mode_placeholders(item, bound.runtime_bindings)
        for item in scenario.model_route_expectations(bound.expected)
    )
    assert mutation.profile.model_toolset == "code_mode_only"
    assert guidance[0].startswith("Route step 1: invoke plane_execute_typescript")
    assert guidance[1].startswith("Route step 2: invoke plane_publish")
    assert "{{newName}}" not in "\\n".join(guidance)
    assert "V60 Code Mode Rename" in "\\n".join(guidance)
    assert "invoke work_item.read" not in "\\n".join(guidance)


def test_worker_live_descriptor_covers_all_routes_and_uses_gateway_input_names() -> None:
    path = TOOLS / "agent-g4-worker-v6.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    assert parsed.scenario_id == "worker"
    assert [commission.commission_id for commission in parsed.commissions] == [
        "identity-discovery",
        "code-mode-semantic-rename",
        "context-governance",
    ]
    assert parsed.expected is None
    assert parsed.profile.tool_presentation == (
        "catalog.search",
        "catalog.describe",
        "agent.context.read",
        "search_workspace",
        "work_item.read",
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    )
    identity = parsed.commissions[0]
    code_mode = parsed.commissions[1]
    context = parsed.commissions[2]
    assert {
        commission.commission_id: commission.expected["routeChecks"]
        for commission in parsed.commissions
    } == {
        "identity-discovery": ["W01"],
        "code-mode-semantic-rename": ["W02", "W03", "W04", "W07", "W08"],
        "context-governance": ["W05", "W06", "W07", "W08"],
    }
    assert "runtime auto-consume" in identity.assignment.objective
    assert code_mode.model_toolset == "code_mode_only"
    assert "call plane_execute_typescript exactly once" in code_mode.assignment.objective
    assert "catalog.search" in code_mode.assignment.objective
    assert "malformed or unknown prepared shape must fail closed" in code_mode.assignment.objective
    assert "hermes_tools.plane_operation" not in code_mode.assignment.objective
    assert "{{projectId}}" not in code_mode.assignment.objective
    assert "{{issueId}}" not in code_mode.assignment.objective
    assert "{{invocationId}}" not in code_mode.assignment.objective
    assert "{{newName}}" not in code_mode.assignment.objective
    assert "call plane_execute_typescript exactly once" in code_mode.assignment.objective
    assert "malformed or unknown prepared shape must fail closed" in code_mode.assignment.objective
    assert "native plane_operation and work_item.rename are not model-visible" in code_mode.assignment.acceptance_criteria[-1]
    code_mode_guidance = scenario.model_route_expectations(code_mode.expected)
    assert len(code_mode_guidance) == 2
    assert code_mode_guidance[0].startswith("Route step 1: invoke plane_execute_typescript exactly 1 time(s)")
    assert "catalog.search; pass the returned operationId verbatim to catalog.describe; search_workspace; extract only the returned workItemReadCall" in code_mode_guidance[0]
    assert 'host.call_plane_operation("work_item.read", { preparedCallRef }' in code_mode_guidance[0]
    assert 'host.call_plane_operation("work_item.rename"' in code_mode_guidance[0]
    assert 'host.call_plane_operation("agent.outcome.submit"' in code_mode_guidance[0]
    assert "Do not invoke search_workspace, work_item.read, work_item.rename, or agent.outcome.submit as model tools" in code_mode_guidance[0]
    assert code_mode_guidance[1].startswith("Route step 2: invoke plane_publish exactly 1 time(s)")
    assert '"subject_user_ref":"{{subjectUserRef}}"' in context.assignment.objective
    assert "private memory" in context.assignment.objective
    assert "exact current invocation run_ref" in parsed.profile.instructions
    assert "never invent, copy, or substitute another run reference" in parsed.profile.instructions
    assert "after a terminal or rejected outcome callback, do not retry either terminal operation" in parsed.profile.instructions
    assert "agent.context.read returns the complete subject-bound projection in one response" in parsed.profile.instructions
    assert "bounded TypeScript module exporting a default async function receiving {host,input}" in parsed.profile.instructions
    assert "host.call_plane_operation(operationId, input, idempotencyKey, correlationId)" in parsed.profile.instructions
    assert "hermes_tools.plane_operation" not in parsed.profile.instructions
    assert "exactly one artifact and exactly one evidence item" in context.assignment.objective
    assert "exactly one artifact and exactly one evidence item" in context.assignment.acceptance_criteria[-1]


def test_code_mode_composition_executes_opaque_prepared_read_then_one_rename_and_submit() -> None:
    source = scenario.code_mode_composition_template().replace("{{invocationId}}", "invocation-v59").replace(
        "{{newName}}", "V59 Code Mode Rename"
    )

    callback_count = 0

    def callback(frame):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            assert frame["args"] == [
                "catalog.search",
                {"query": "work_item.read", "limit": 5},
                "idempotency:invocation-v59:code-mode-catalog-search",
                "correlation:invocation-v59:code-mode-catalog-search",
            ]
            return {"ok": True, "result": {"operations": [{"operationId": "work_item.read"}]}}
        if callback_count == 2:
            assert frame["args"] == [
                "catalog.describe",
                {"operation_id": "work_item.read"},
                "idempotency:invocation-v59:code-mode-catalog-describe",
                "correlation:invocation-v59:code-mode-catalog-describe",
            ]
            return {"ok": True, "result": {"operation": {"operationId": "work_item.read"}}}
        if callback_count == 3:
            assert frame["args"] == [
                "search_workspace",
                {"query": "G4 Live Issue", "limit": 1},
                "idempotency:invocation-v59:code-mode-search",
                "correlation:invocation-v59:code-mode-search",
            ]
            return {
                "ok": True,
                "result": {
                    "results": [
                        {
                            "objectType": "work_item",
                            "workItemReadCall": "prepared-call:opaque",
                        }
                    ]
                },
            }
        if callback_count == 4:
            assert frame["args"] == [
                "work_item.read",
                {"preparedCallRef": "prepared-call:opaque"},
                "idempotency:invocation-v59:code-mode-read",
                "correlation:invocation-v59:code-mode-read",
            ]
            return {"ok": True, "result": {"work_item": {"project": "project-1", "id": "issue-1"}}}
        if callback_count == 5:
            assert frame["args"] == [
                "work_item.rename",
                {"project_id": "project-1", "issue_id": "issue-1", "name": "V59 Code Mode Rename"},
                "idempotency:invocation-v59:code-mode-rename",
                "correlation:invocation-v59:code-mode-rename",
            ]
            return {"ok": True, "result": {"work_item": {"name": "V59 Code Mode Rename"}}}
        assert callback_count == 6
        assert frame["args"] == [
            "agent.outcome.submit",
            {
                "summary": "Code Mode semantic rename completed.",
                "artifacts": ["artifact:code-mode-semantic-rename"],
                "evidence": ["evidence:code-mode-search-read-rename"],
            },
            "idempotency:invocation-v59:code-mode-submit",
            "correlation:invocation-v59:code-mode-submit",
        ]
        return {"ok": True, "result": {"outcome": {"outcomeRef": "outcome-submission:one"}}}

    callbacks, result = _run_code_mode_frames(source, callback)
    assert [frame["args"][0] for frame in callbacks] == [
        "catalog.search",
        "catalog.describe",
        "search_workspace",
        "work_item.read",
        "work_item.rename",
        "agent.outcome.submit",
    ]
    assert result["type"] == "result"
    assert result["value"]["submit"]["result"]["outcome"]["outcomeRef"] == "outcome-submission:one"


def test_code_mode_composition_rejects_malformed_prepared_shape_before_read_or_mutation() -> None:
    source = scenario.code_mode_composition_template()
    callback_count = 0

    def callback(frame):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            assert frame["args"][0] == "catalog.search"
            return {"ok": True, "result": {"operations": [{"operationId": "work_item.read"}]}}
        if callback_count == 2:
            assert frame["args"][0] == "catalog.describe"
            return {"ok": True, "result": {"operation": {"operationId": "work_item.read"}}}
        assert callback_count == 3
        assert frame["args"][0] == "search_workspace"
        return {
            "ok": True,
            "result": {
                "results": [
                    {
                        "objectType": "work_item",
                        "workItemReadCall": {"input": {"project_id": "raw", "issue_id": "raw"}},
                    }
                ]
            },
        }

    callbacks, result = _run_code_mode_frames(source, callback)
    assert [frame["args"][0] for frame in callbacks] == ["catalog.search", "catalog.describe", "search_workspace"]
    assert result["type"] == "error"
    assert result["code"] == "CODE_MODE_FAILED"
    assert "raw" not in json.dumps(result)


def test_code_mode_composition_returns_unknown_prepared_failure_without_mutation() -> None:
    source = scenario.code_mode_composition_template()
    callback_count = 0

    def callback(frame):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            return {"ok": True, "result": {"operations": [{"operationId": "work_item.read"}]}}
        if callback_count == 2:
            return {"ok": True, "result": {"operation": {"operationId": "work_item.read"}}}
        if callback_count == 3:
            return {
                "ok": True,
                "result": {
                    "results": [
                        {
                            "objectType": "work_item",
                            "workItemReadCall": "prepared-call:unknown",
                        }
                    ]
                },
            }
        assert callback_count == 4
        assert frame["args"][0] == "work_item.read"
        assert frame["args"][1] == {"preparedCallRef": "prepared-call:unknown"}
        return {"ok": False, "error": {"code": "PREPARED_CALL_INVALID"}}

    callbacks, result = _run_code_mode_frames(source, callback)
    assert [frame["args"][0] for frame in callbacks] == ["catalog.search", "catalog.describe", "search_workspace", "work_item.read"]
    assert result["type"] == "result"
    assert result["value"]["read"]["error"]["code"] == "PREPARED_CALL_INVALID"


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

    selected = scenario.select_runtime_descriptor(parsed, "planning-delegation")

    assert selected.commissions == ()
    assert selected.selected_commission_id == "planning-delegation"
    assert selected.descriptor_digest == parsed.descriptor_digest
    assert selected.assignment == parsed.commissions[0].assignment


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
    route_guidance = scenario.model_route_expectations(parsed.commissions[0].expected)
    assert route_guidance[2].startswith("Route step 3: invoke search_workspace exactly 1 time(s) and expect success.")
    assert 'Use exactly {"query":"G4 Live Issue","limit":1} as input' in route_guidance[2]
    assert "workItemReadCall" in route_guidance[2]
    assert "input.preparedCallRef" in route_guidance[3]
    assert "Do not pass the workItemReadCall string as the complete tool arguments" in route_guidance[3]
    assert "Tool presentation is descriptive only" in parsed.profile.instructions
    assert "outcome_unknown" in parsed.prompt


def test_operator_o04_credential_lifecycle_does_not_require_prepared_read() -> None:
    path = TOOLS / "agent-g4-operator-o04-o06-recovery.json"
    raw = path.read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    o04 = scenario.select_commission(parsed, "lease-recovery")
    o06 = scenario.select_commission(parsed, "failure-recovery")

    assert [row["operationId"] for row in o04.expected["operationOutcomes"]] == [
        "agent.outcome.evaluate",
        "agent.outcome.submit",
        "agent.outcome.publish",
    ]
    route_guidance = scenario.model_route_expectations(o04.expected)
    assert all("search_workspace" not in step for step in route_guidance)
    assert all("work_item.read" not in step for step in route_guidance)
    assert all("preparedCallRef" not in step for step in route_guidance)
    assert "live_authorization" in parsed.setup.preconditions
    assert "separate_runtime_service" in parsed.setup.preconditions
    assert o04.expected["routeChecks"] == ["O04"]
    assert "audit" in o04.expected["evidenceKinds"]
    assert "terminal_event" in o04.expected["evidenceKinds"]

    route_evidence, route_failures = operator_route.build_operator_route_evidence()
    assert route_failures == []
    validator._validate_operator_route_evidence(route_evidence, route_checks={"O04"})
    gate = scenario.evaluate_expectations(
        o04.expected,
        operations=[
            {"operationId": "agent.outcome.evaluate", "outcome": "denied", "count": 1},
            {"operationId": "agent.outcome.submit", "outcome": "success", "count": 1},
            {"operationId": "agent.outcome.publish", "outcome": "success", "count": 1},
        ],
        records=o04.expected["durableRecords"],
        product_events=o04.expected["productEvents"],
        evidence_kinds=o04.expected["evidenceKinds"],
        route_evidence=route_evidence,
    )
    assert gate["passed"] is True
    projection = o04.evidence()
    projection["actual"] = {
        "operations": [],
        "records": [],
        "productEvents": [],
        "evidenceKinds": [],
    }
    with pytest.raises(validator.ContractError, match="evidence_operator_o04_route_evidence_missing"):
        validator._validate_scenario_projection(projection)
    missing_route_gate = scenario.evaluate_expectations(
        o04.expected,
        operations=[
            {"operationId": "agent.outcome.evaluate", "outcome": "denied", "count": 1},
            {"operationId": "agent.outcome.submit", "outcome": "success", "count": 1},
            {"operationId": "agent.outcome.publish", "outcome": "success", "count": 1},
        ],
        records=o04.expected["durableRecords"],
        product_events=o04.expected["productEvents"],
        evidence_kinds=o04.expected["evidenceKinds"],
    )
    assert missing_route_gate["passed"] is False
    assert "route:O04" in missing_route_gate["failures"]
    assert [row["operationId"] for row in o06.expected["operationOutcomes"][:2]] == [
        "search_workspace",
        "work_item.read",
    ]


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
    assert parsed.expected is None
    assert [commission.commission_id for commission in parsed.commissions] == [
        "planning-delegation",
        "cancellation-schedule",
        "evaluation-hr",
        "chief-of-staff-terminal-readback",
    ]
    assert parsed.commissions[0].expected["operationOutcomes"][0] == {
        "operationId": "search_workspace",
        "outcome": "success",
        "count": 1,
    }
    assert parsed.commissions[-1].expected["operationOutcomes"][-2:] == [
        {"operationId": "agent.outcome.submit", "outcome": "success", "count": 1},
        {"operationId": "agent.outcome.publish", "outcome": "success", "count": 1},
    ]
    assert parsed.setup.lineage.parent_ref == "actor:primary"
    assert parsed.setup.schedule.timezone == "America/Los_Angeles"
    assert "workflow product" in parsed.prompt
    for commission in parsed.commissions:
        validator._validate_scenario_projection(scenario.commission_descriptor(parsed, commission).evidence())


def test_manager_commission_requires_prepared_first_operation_and_terminal() -> None:
    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text(encoding="utf-8"))
    value["commissions"][0]["expected"]["operationOutcomes"][0]["operationId"] = "catalog.search"
    raw, digest = descriptor_bytes(value)
    with pytest.raises(scenario.ScenarioError, match="scenario_manager_commission_planning-delegation_first_operation_invalid"):
        scenario.parse_descriptor_bytes(raw, digest)

    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text(encoding="utf-8"))
    value["commissions"][0]["expected"]["operationOutcomes"] = [
        {"operationId": "search_workspace", "outcome": "success", "count": 1}
    ]
    value["commissions"][0]["expected"]["productEvents"] = []
    raw, digest = descriptor_bytes(value)
    with pytest.raises(scenario.ScenarioError, match="scenario_manager_commission_planning-delegation_terminal_missing"):
        scenario.parse_descriptor_bytes(raw, digest)


def test_manager_commission_accepts_explicit_failure_terminal() -> None:
    value = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text(encoding="utf-8"))
    expected = value["commissions"][0]["expected"]
    expected["operationOutcomes"] = [
        {"operationId": "search_workspace", "outcome": "success", "count": 1}
    ]
    expected["productEvents"] = [{"kind": "run_failure", "count": 1}]
    raw, digest = descriptor_bytes(value)
    parsed = scenario.parse_descriptor_bytes(raw, digest)
    assert parsed.commissions[0].expected["productEvents"] == [{"kind": "run_failure", "count": 1}]


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


def test_manager_commission_scopes_fixture_to_declared_route_checks() -> None:
    descriptor = json.loads((TOOLS / "agent-g4-manager-v1.json").read_text(encoding="utf-8"))
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(descriptor))
    selected = scenario.select_runtime_descriptor(parsed, "planning-delegation")
    assert selected.expected["routeChecks"] == ["M01", "M02"]

    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    route = (TOOLS / "agent_g4_manager_route.py").read_text(encoding="utf-8")
    assert "route_checks=manager_route_checks" in invoke
    scope_start = route.index("selected_route_ids = set(route_checks)")
    later_route = route.index("# M03:", scope_start)
    assert "if selected_route_ids <= {\"M01\", \"M02\"}:" in route[scope_start:later_route]
    assert "route_checks is not None" in route[route.index("def build_manager_route_evidence"):]


def test_manager_m03_m04_satisfied_route_returns_before_later_cells() -> None:
    route = (TOOLS / "agent_g4_manager_route.py").read_text(encoding="utf-8")
    invoke = (TOOLS / "agent-g4-live-invoke.py").read_text(encoding="utf-8")
    m03_m04_return = route.index('if selected_route_ids <= {"M03", "M04"}:')
    m05_start = route.index("# M05:", m03_m04_return)

    assert "return {" in route[m03_m04_return:m05_start]
    assert '"M03", m03' in route[m03_m04_return:m05_start]
    assert '"M04", m04' in route[m03_m04_return:m05_start]
    assert 'scenario_gate["passed"] = not scenario_gate["failures"]' in invoke
    assert 'if not scenario_gate["passed"]:' in invoke


def test_manager_m05_m06_satisfied_route_returns_before_later_cells() -> None:
    route = (TOOLS / "agent_g4_manager_route.py").read_text(encoding="utf-8")
    m05_m06_return = route.index('if selected_route_ids <= {"M05", "M06"}:')
    m07_start = route.index("# M07:", m05_m06_return)

    selected = route[m05_m06_return:m07_start]
    assert "return {" in selected
    assert '("M05", m05)' in selected
    assert '("M06", m06)' in selected


def test_manager_m05_m06_readback_failure_is_bounded_after_route_success() -> None:
    route = (TOOLS / "agent_g4_manager_route.py").read_text(encoding="utf-8")
    selected_start = route.index('if selected_route_ids <= {"M05", "M06"}:')
    m07_start = route.index("# M07:", selected_start)
    selected = route[selected_start:m07_start]

    assert "route_result =" in selected
    assert '"readback": _post_route_readback(workspace)' in selected
    assert '"stage": "postRouteReadback"' in route
    assert '"predicate": "readback"' in route
    assert '"readbackUnavailable"' in route
    assert "except BaseException as exc" in route[route.index("def _post_route_readback"):]


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
    assert '--diagnostic "${ERROR_FILE}"' in runner
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
    assert '_load_scenario_module("agent_g4_operator_route")' in source
    assert "scenario_module_root_missing" in source


def test_commission_descriptor_keeps_shared_profile_and_binds_each_assignment() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())

    identity = scenario.commission_descriptor(parsed, parsed.commissions[0])
    code_mode = scenario.commission_descriptor(parsed, parsed.commissions[1])
    context = scenario.commission_descriptor(parsed, parsed.commissions[2])
    assert identity.profile == context.profile == parsed.profile
    assert code_mode.profile == replace(parsed.profile, model_toolset="code_mode_only")
    assert identity.assignment.target_ref == code_mode.assignment.target_ref == context.assignment.target_ref == scenario.ASSIGNED_WORK_ITEM_ALIAS
    assert identity.expected["routeChecks"] != code_mode.expected["routeChecks"]
    assert code_mode.expected["routeChecks"] != context.expected["routeChecks"]
    assert identity.commissions == code_mode.commissions == context.commissions == ()


def test_multi_commission_prompt_preserves_the_typed_code_mode_route() -> None:
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
    code_mode = scenario.commission_descriptor(parsed, parsed.commissions[1])
    expected = namespace["_profile_expected_outcomes"](code_mode)

    assert expected == list(scenario.model_route_expectations(code_mode.expected))
    assert expected[0].startswith("Route step 1: invoke plane_execute_typescript")
    assert "catalog.describe" in expected[0]
    assert 'host.call_plane_operation("work_item.rename"' in expected[0]
    assert expected[1].startswith("Route step 2: invoke plane_publish")


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


def test_not_authorized_outcome_renders_exact_canary_guidance() -> None:
    guidance = scenario.model_route_expectations(
        {
            "operationOutcomes": [
                {
                    "operationId": "agent.outcome.evaluate",
                    "outcome": "denied",
                    "errorCode": "NOT_AUTHORIZED",
                }
            ]
        }
    )
    assert guidance == (
        'Route step 1: invoke agent.outcome.evaluate exactly 1 time(s) and expect denied. '
        'After this route call returns, advance immediately to the next route step; do not invoke this '
        'operation again for confirmation, inspection, refresh, or retry. Emit exactly '
        '{"outcome_ref":"outcome-submission:not-authorized","verdict":"revision_requested"} as input; '
        'omit evaluator_ref because the trusted Plane host binds it to the current actor.',
    )


def test_standard_route_maps_typed_delivery_outcomes_without_persona_names() -> None:
    expected = {"operationOutcomes": [
        {"operationId": "search_workspace", "outcome": "success"},
        {"operationId": "work_item.read", "outcome": "success"},
        {"operationId": "agent.outcome.evaluate", "outcome": "denied", "errorCode": "NOT_AUTHORIZED"},
        {"operationId": "agent.outcome.submit", "outcome": "success"},
        {"operationId": "agent.outcome.publish", "outcome": "success"},
    ]}
    route = scenario.standard_route(expected)
    assert route == {
        "schemaVersion": "plane.standard-route/v1",
        "steps": [
            {"operationRef": "operation:search_workspace"},
            {"operationRef": "operation:work_item.read"},
            {"operationRef": "operation:agent.outcome.evaluate", "expectedStatus": "denied", "expectedErrorCode": "NOT_AUTHORIZED"},
            {"operationRef": "operation:agent.outcome.submit"},
            {"operationRef": "operation:agent.outcome.publish"},
        ],
    }
    assert "routeId" not in route
    assert scenario.standard_route({"operationOutcomes": [{"operationId": "agent.outcome.submit", "outcome": "success", "count": 2}]}) is None
    manager = scenario.standard_route({"operationOutcomes": [
        {"operationId": "search_workspace", "outcome": "success"},
        {"operationId": "agent.outcome.submit", "outcome": "success"},
        {"operationId": "agent.outcome.publish", "outcome": "success"},
    ]})
    assert manager["steps"][1] == {"operationRef": "operation:work_item.read", "optional": True}
    identity = scenario.standard_route({"operationOutcomes": [
        {"operationId": "search_workspace", "outcome": "success"},
        {"operationId": "agent.outcome.evaluate", "outcome": "denied", "errorCode": "NOT_AUTHORIZED"},
        {"operationId": "agent.outcome.submit", "outcome": "success"},
        {"operationId": "agent.outcome.publish", "outcome": "success"},
    ]})
    assert identity["steps"][1] == {"operationRef": "operation:work_item.read", "optional": True}
    assert scenario.standard_route({"operationOutcomes": [{"operationId": "x", "outcome": "denied"}]}) is None


def test_rename_route_always_exposes_the_exact_code_mode_callback() -> None:
    guidance = scenario.model_route_expectations(
        {
            "operationOutcomes": [
                {"operationId": "work_item.read", "outcome": "success", "count": 1},
                {"operationId": "work_item.rename", "outcome": "success", "count": 1},
            ],
            "routeChecks": [],
        }
    )

    assert guidance[1].startswith("Route step 2: invoke plane_execute_typescript exactly 1 time(s) to perform work_item.rename")
    assert 'host.call_plane_operation("work_item.rename", input, idempotencyKey, correlationId)' in guidance[1]


def test_semantic_rename_commission_rejects_publication_without_rename_evidence() -> None:
    raw = (TOOLS / "agent-g4-worker-v6.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    expected = parsed.commissions[1].expected
    assert expected is not None
    operations = [
        row
        for row in expected["operationOutcomes"]
        if row["operationId"] != "work_item.rename"
    ]
    records = list(expected.get("durableRecords", []))
    product_events = list(expected.get("productEvents", []))
    evidence_kinds = list(expected["evidenceKinds"])

    failed = scenario.evaluate_expectations(
        expected,
        operations=operations,
        records=records,
        product_events=product_events,
        evidence_kinds=evidence_kinds,
    )
    assert failed["passed"] is False
    assert "operation:work_item.rename" in failed["failures"]

    complete = scenario.evaluate_expectations(
        expected,
        operations=[
            *operations,
            {"operationId": "work_item.rename", "outcome": "success", "count": 1},
        ],
        records=records,
        product_events=product_events,
        evidence_kinds=evidence_kinds,
    )
    assert complete["passed"] is True


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


def test_validator_requires_retained_operator_o04_route_evidence() -> None:
    value = descriptor_for("operator")
    value["expected"] = {
        "operationOutcomes": [],
        "evidenceKinds": [],
        "routeChecks": ["O04"],
    }
    parsed = scenario.parse_descriptor_bytes(*descriptor_bytes(value))
    projection = parsed.evidence()
    projection["actual"] = {"operations": [], "records": [], "productEvents": [], "evidenceKinds": []}

    with pytest.raises(validator.ContractError, match="evidence_operator_o04_route_evidence_missing"):
        validator._validate_scenario_projection(projection)

    route_evidence, failures = operator_route.build_operator_route_evidence()
    assert not failures
    projection["actual"]["routeEvidence"] = route_evidence
    validator._validate_scenario_projection(projection)


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
            "replay": {"context": {"memoryRevisions": 0, "skillRevisions": 0, "proposals": 0, "contextReceipts": 0}},
        },
        "readback": {"contextProjectionDigest": "0" * 64},
    }

    validator._validate_worker_route_evidence(identity_route, route_checks={"W01"})


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
            "W02": {
                "catalogSearchBeforeDescribe": True,
                "boundedSearchAndRead": True,
                "hiddenObjectsAbsent": True,
            },
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
        route_checks={"W02", "W03", "W04", "W07", "W08"},
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

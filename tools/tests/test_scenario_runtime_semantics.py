# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


TOOLS = Path(__file__).parents[1]
sys.path.insert(0, str(TOOLS))

import agent_g4_live_scenario as scenario  # noqa: E402
import validate_agent_g4_live as validator  # noqa: E402


def run_code_mode_frames(source: str, callback_handler):
    runner = TOOLS.parent / "apps" / "api" / "plane" / "agent" / "code_mode" / "runner.mjs"
    help_result = subprocess.run(["node", "--help"], check=False, capture_output=True, text=True)
    permission_flag = (
        "--permission"
        if "--permission" in f"{help_result.stdout}\n{help_result.stderr}"
        else "--experimental-permission"
    )
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
                    "input": {
                        "task": {"target": "target:issue:1"},
                        "methods": [
                            {"path": "workItems.retrieve"},
                            {"path": "workItems.update"},
                        ],
                    },
                    "mode": "plane",
                    "callbacks": {"resource": "call_plane_resource", "finish": "finish_plane"},
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


def binding_manifest(candidate: str, mode: str) -> dict[str, object]:
    parent = "b" * 40
    hermes = "c" * 40
    runtime_files = {"apps/api/plane/agent/runtime/service.py": "d" * 64}
    runtime_source_digest = hashlib.sha256(
        json.dumps(runtime_files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {
        "candidateBinding": {
            "mode": mode,
            "acceptedG3Baseline": "a" * 40,
            "parentCommit": parent,
        },
        "pins": {
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
        },
    }
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


def worker_commission():
    raw = (TOOLS / "agent-g4-worker-minimal.json").read_bytes()
    parsed = scenario.parse_descriptor_bytes(raw, hashlib.sha256(raw).hexdigest())
    return scenario.select_commission(parsed, "worker-full")


def test_code_mode_commission_uses_typed_plane_semantics() -> None:
    commission = worker_commission()

    assert commission.profile.model_toolset == "code_mode_only"
    assert [row["operationId"] for row in commission.expected["operationOutcomes"]] == [
        "work_item.read",
        "work_item.rename",
    ]
    assert commission.expected["routeChecks"] == ["W01", "W03", "W04", "W08"]
    assert commission.expected["productEvents"] == [{"kind": "outcome_submission", "count": 1}]


def test_code_mode_runtime_binding_substitutes_only_typed_values() -> None:
    bound = scenario.bind_code_mode_runtime_values(
        worker_commission(),
        project_id="project-fresh",
        issue_id="issue-fresh",
        invocation_id="invocation-fresh",
        new_name="Semantic Rename",
        subject_user_ref="user:subject-fresh",
    )
    guidance = scenario.model_route_expectations(
        bound.expected, model_toolset=bound.profile.model_toolset
    )
    text = "\n".join(
        [
            bound.assignment.objective,
            *bound.assignment.acceptance_criteria,
            bound.prompt,
            bound.profile.instructions,
            *(
                scenario.substitute_code_mode_placeholders(item, bound.runtime_bindings)
                for item in guidance
            ),
        ]
    )

    assert "{{" not in text
    assert "project-fresh" not in text
    assert "issue-fresh" not in text
    assert 'name: "Semantic Rename"' in text
    assert "await plane.workItems.update(task.target" in text

    with pytest.raises(scenario.ScenarioError, match="scenario_new_name_binding_invalid"):
        scenario.bind_code_mode_runtime_values(
            worker_commission(),
            project_id="project-fresh",
            issue_id="issue-fresh",
            invocation_id="invocation-fresh",
            new_name="contains an api key",
        )


def test_code_mode_composition_executes_read_rename_and_finish() -> None:
    source = scenario.code_mode_composition_template().replace("{{newName}}", "Semantic Rename")
    callback_count = 0

    def callback(frame):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            assert frame["name"] == "call_plane_resource"
            assert frame["args"] == ["workItems.retrieve", ["target:issue:1"]]
            return {"status": "ok", "value": {"name": "before"}}
        if callback_count == 2:
            assert frame["name"] == "call_plane_resource"
            assert frame["args"] == [
                "workItems.update",
                ["target:issue:1", {"name": "Semantic Rename"}],
            ]
            return {"status": "ok", "value": {"name": "Semantic Rename"}}
        assert callback_count == 3
        assert frame["name"] == "finish_plane"
        assert frame["args"][0]["kind"] == "completed"
        return {"__plane_finish__": "completed"}

    callbacks, result = run_code_mode_frames(source, callback)

    assert [frame["name"] for frame in callbacks] == [
        "call_plane_resource",
        "call_plane_resource",
        "finish_plane",
    ]
    assert result["type"] == "result"


def test_code_mode_readback_projects_atomic_finish_without_legacy_publication() -> None:
    commission = worker_commission()
    projected = scenario.readback_expectations(
        commission.expected, model_toolset=commission.profile.model_toolset
    )

    assert [row["operationId"] for row in projected["operationOutcomes"]] == [
        "work_item.read",
        "work_item.rename",
    ]
    assert "publication" not in projected["evidenceKinds"]
    assert projected["durableRecords"][-1] == {"kind": "outcome_submission", "count": 1}
    assert projected["productEvents"] == [{"kind": "outcome_submission", "count": 1}]
    assert scenario.readback_expectations(commission.expected, model_toolset="standard") is commission.expected


def test_expected_operations_render_in_order_with_bounded_native_guidance() -> None:
    expected = {
        "operationOutcomes": [
            {"operationId": "catalog.search", "outcome": "success", "count": 1},
            {"operationId": "catalog.describe", "outcome": "success", "count": 1},
            {"operationId": "agent.context.read", "outcome": "success", "count": 1},
            {
                "operationId": "agent.outcome.evaluate",
                "outcome": "denied",
                "errorCode": "NOT_AUTHORIZED",
                "count": 1,
            },
        ]
    }

    guidance = scenario.model_route_expectations(expected)

    assert [item.split(":", 1)[0] for item in guidance] == [
        "Route step 1",
        "Route step 2",
        "Route step 3",
        "Route step 4",
    ]
    assert "exact operationId" in guidance[1]
    assert "complete subject-bound projection" in guidance[2]
    assert '"verdict":"revision_requested"' in guidance[3]


def test_standard_route_maps_only_single_typed_delivery_steps() -> None:
    expected = {
        "operationOutcomes": [
            {"operationId": "search_workspace", "outcome": "success"},
            {
                "operationId": "agent.outcome.evaluate",
                "outcome": "denied",
                "errorCode": "NOT_AUTHORIZED",
            },
            {"operationId": "agent.outcome.submit", "outcome": "success"},
            {"operationId": "agent.outcome.publish", "outcome": "success"},
        ]
    }

    route = scenario.standard_route(expected)

    assert route["schemaVersion"] == "plane.standard-route/v1"
    assert route["steps"][1] == {"operationRef": "operation:work_item.read", "optional": True}
    assert route["steps"][2] == {
        "operationRef": "operation:agent.outcome.evaluate",
        "expectedStatus": "denied",
        "expectedErrorCode": "NOT_AUTHORIZED",
    }
    assert scenario.standard_route(
        {"operationOutcomes": [{"operationId": "agent.outcome.submit", "outcome": "success", "count": 2}]}
    ) is None
    assert scenario.standard_route(
        {"operationOutcomes": [{"operationId": "unknown", "outcome": "denied"}]}
    ) is None


def test_expectation_gate_requires_every_typed_observation() -> None:
    expected = {
        "operationOutcomes": [{"operationId": "work_item.rename", "outcome": "success", "count": 1}],
        "evidenceKinds": ["audit"],
        "durableRecords": [{"kind": "publication", "count": 1}],
        "productEvents": [{"kind": "publication", "count": 1}],
    }
    failed = scenario.evaluate_expectations(
        expected,
        operations=[],
        records=[],
        product_events=[],
        evidence_kinds=[],
    )

    assert failed["passed"] is False
    assert set(failed["failures"]) == {
        "operation:work_item.rename",
        "evidence:audit",
        "durableRecords:publication",
        "productEvents:publication",
    }

    passed = scenario.evaluate_expectations(
        expected,
        operations=[{"operationId": "work_item.rename", "outcome": "success", "count": 1}],
        records=[{"kind": "publication", "count": 1}],
        product_events=[{"kind": "publication", "count": 1}],
        evidence_kinds=["audit"],
    )
    assert passed["passed"] is True


def test_explicit_publication_projection_drives_all_publication_predicates() -> None:
    expected = {
        "operationOutcomes": [],
        "evidenceKinds": ["publication"],
        "durableRecords": [{"kind": "publication", "count": 1}],
        "productEvents": [{"kind": "publication", "count": 1}],
    }
    records, events, evidence = scenario.explicit_publication_expectations(
        {"count": 1, "bindings": [{"productKind": "outcome_submission"}]}
    )
    assert scenario.evaluate_expectations(
        expected,
        operations=[],
        records=records,
        product_events=events,
        evidence_kinds=evidence,
    )["passed"]

    records, events, evidence = scenario.explicit_publication_expectations({"count": 0, "bindings": []})
    assert not scenario.evaluate_expectations(
        expected,
        operations=[],
        records=records,
        product_events=events,
        evidence_kinds=evidence,
    )["passed"]


def test_validator_rejects_a_gate_whose_summary_disagrees_with_predicates() -> None:
    gate = {
        "passed": True,
        "failures": [],
        "operations": [],
        "durableRecords": [],
        "productEvents": [],
        "evidenceKinds": [],
    }
    validator._validate_scenario_gate(gate)

    gate["passed"] = False
    with pytest.raises(validator.ContractError, match="evidence_scenario_gate_predicate_mismatch"):
        validator._validate_scenario_gate(gate)


def test_disposable_binding_accepts_code_mode_runtime_files() -> None:
    candidate = "1" * 40
    manifest = binding_manifest(candidate, "disposable-exact-candidate")
    binding = manifest["disposableBinding"]
    runtime_files = dict(binding["runtimeFiles"])
    runtime_files["apps/api/plane/agent/code_mode/contracts.py"] = "e" * 64
    binding["runtimeFiles"] = runtime_files
    binding["runtimeSourceDigest"] = hashlib.sha256(
        json.dumps(runtime_files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    validator.validate_candidate_binding(manifest, candidate, Path.cwd())


def test_exact_child_binding_accepts_one_direct_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = "1" * 40
    monkeypatch.setattr(validator, "_commit_parents", lambda _root, _candidate: ["b" * 40])

    validator.validate_candidate_binding(binding_manifest(candidate, "exact-single-child"), candidate, Path.cwd())


def test_commit_parent_lookup_reads_one_exact_git_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "--quiet"], check=True)
    subprocess.run(git + ["config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(git + ["config", "user.name", "Test"], check=True)
    (repo / "file").write_text("base")
    subprocess.run(git + ["add", "file"], check=True)
    subprocess.run(git + ["commit", "--quiet", "-m", "base"], check=True)
    parent = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    (repo / "file").write_text("child")
    subprocess.run(git + ["commit", "--quiet", "-am", "child"], check=True)
    candidate = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()

    assert validator._commit_parents(repo, candidate) == [parent]


@pytest.mark.parametrize("parents", [["i" * 40], ["b" * 40, "a" * 40]])
def test_exact_child_binding_rejects_wrong_parent_shape(
    monkeypatch: pytest.MonkeyPatch, parents: list[str]
) -> None:
    candidate = "1" * 40
    monkeypatch.setattr(validator, "_commit_parents", lambda _root, _candidate: parents)

    with pytest.raises(validator.ContractError, match="candidate_is_not_exact_single_child"):
        validator.validate_candidate_binding(
            binding_manifest(candidate, "exact-single-child"), candidate, Path.cwd()
        )


def test_disposable_binding_is_required_and_accepts_an_exact_candidate() -> None:
    candidate = "1" * 40
    missing = binding_manifest(candidate, "disposable-exact-candidate")
    missing.pop("disposableBinding")
    with pytest.raises(validator.ContractError, match="disposable_binding_required"):
        validator.validate_candidate_binding(missing, candidate, Path.cwd())

    validator.validate_candidate_binding(
        binding_manifest(candidate, "disposable-exact-candidate"), candidate, Path.cwd()
    )

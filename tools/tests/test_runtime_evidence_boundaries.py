# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))


def _invoke_helpers() -> dict[str, object]:
    path = TOOLS / "agent-g4-live-invoke.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"hashlib": hashlib, "json": json}
    support = [node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))]
    exec(compile(ast.Module(body=support, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _failure_evidence(**overrides):
    arguments = {
        "binding": {},
        "failure_phase": "api-invocation",
        "error_class": "RuntimeError",
        "exit_code": 1,
        "run_id": "run:failure",
        "run_state": "failed",
        "invocation_id": "invocation:failure",
        "invocation_state": "failed",
        "provider_attempts": [],
        "terminal_kind": "run_failure",
    }
    arguments.update(overrides)
    return _invoke_helpers()["build_failure_evidence"](**arguments)


def test_failure_evidence_is_finite_and_excludes_sensitive_values() -> None:
    project_id = "11111111-1111-4111-8111-111111111111"
    issue_id = "22222222-2222-4222-8222-222222222222"
    target_digest = hashlib.sha256(
        json.dumps(
            {"project_id": project_id, "issue_id": issue_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    evidence = _failure_evidence(
        binding={"candidateCommit": "credential=provider-secret"},
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
        plane_operation_audit=[
            {
                "operation_id": "work_item.read",
                "outcome": "denied",
                "error_code": "NOT_AUTHORIZED",
                "target_digest": target_digest,
                "request_input": {"project_id": project_id, "issue_id": issue_id},
            }
        ],
    )

    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    assert len(encoded.encode("utf-8")) <= 4096
    assert evidence["runtimeEventIngress"] == {"kindCounts": {"usage_observed": 1}}
    assert evidence["runtimeExit"]["failure"] == {
        "code": "budget_exhausted",
        "retryable": False,
    }
    assert evidence["providerAttempts"][0] == {
        "sequence": 1,
        "phase": "failed",
        "upstreamInitiated": False,
        "statusClass": "not_sent",
        "errorCode": "pre_send_failure",
    }
    read = next(
        row
        for row in evidence["planeOperationAudit"]
        if row["operationId"] == "work_item.read"
    )
    assert read["targetDigest"] == target_digest
    assert project_id not in encoded
    assert issue_id not in encoded
    assert not re.search(
        r"(?i)(password|secret|token|api[_-]?key|authorization|credential|prompt|response|payload|rawLogs)",
        encoded,
    )


def test_provider_unknown_requires_durable_upstream_attempt_evidence() -> None:
    reason = json.dumps(
        {
            "failureCode": "runtime_error",
            "failurePhase": "runtime_process",
            "failureDetail": "process_exit",
            "failureSubreason": "upstream_timeout",
            "failureCause": "provider_unknown_failure",
        }
    )

    def build(provider_attempts: list[dict[str, object]]) -> dict[str, object]:
        return _failure_evidence(
            provider_attempts=provider_attempts,
            failure_code="runtime_error",
            failure_reason=reason,
            runtime_exit={
                "kind": "failed",
                "failure": {
                    "code": "runtime_error",
                    "cause": "provider_unknown_failure",
                },
            },
            terminal_code="runtime_error",
            terminal_reason=reason,
        )

    without_attempt = build([])
    assert without_attempt["failure"]["reasonCause"] == "runtime_unknown_failure"
    assert without_attempt["runtimeExit"]["failure"]["cause"] == "runtime_unknown_failure"

    with_attempt = build(
        [
            {
                "sequence": 1,
                "phase": "outcome_unknown",
                "upstreamInitiated": True,
                "statusClass": "unknown",
                "errorCode": "outcome_unknown",
                "reasonSubreason": "upstream_timeout",
            }
        ]
    )
    assert with_attempt["failure"]["reasonCause"] == "provider_unknown_failure"
    assert with_attempt["runtimeExit"]["failure"]["cause"] == "provider_unknown_failure"


def test_runtime_diagnostics_accept_only_bounded_structural_fields() -> None:
    from validate_agent_g4_live import ContractError, _validate_runtime_diagnostics

    bounded = _invoke_helpers()["_bounded_runtime_diagnostics"]
    valid = {
        "version": 1,
        "requests": [
            {
                "sequence": 1,
                "toolChoice": "required",
                "visibleToolset": "execute_only",
                "visibleToolCount": 1,
                "serialized": True,
            }
        ],
        "responses": [
            {"sequence": 1, "responseClass": "tool_call", "toolCall": "execute"}
        ],
        "hostCallbacks": [
            {
                "sequence": 1,
                "phase": "host_return",
                "operationRefDigest": "a" * 64,
            }
        ],
    }

    assert bounded(valid) == valid
    _validate_runtime_diagnostics(valid)
    for field, value in (
        ("prompt", "raw model input"),
        ("operationRef", "operation:raw"),
    ):
        candidate = json.loads(json.dumps(valid))
        target = candidate["requests"][0] if field == "prompt" else candidate["hostCallbacks"][0]
        target[field] = value
        assert bounded(candidate) is None
        with pytest.raises(ContractError):
            _validate_runtime_diagnostics(candidate)


def test_prepared_call_failure_retains_shape_without_values() -> None:
    diagnostic = {
        "schemaVersion": "plane.prepared-call-shape/v1",
        "acceptedForm": "canonical_ref",
        "failureClass": "malformed",
        "shape": {
            "keyNames": ["preparedCallRef"],
            "keyNamesTruncated": False,
            "valueTypes": ["object", "string"],
            "nestingDepth": 1,
            "sizeClass": "small",
        },
    }
    evidence = _failure_evidence(
        failure_reason=json.dumps(
            {
                "failureCode": "runtime_error",
                "failurePhase": "runtime_process",
                "failureDetail": "process_exit",
                "failureSubreason": "runtime_execution_failed",
                "failureCause": "host_operation_failure",
                "hostOperationFailure": {
                    "operationId": "work_item.read",
                    "attemptRef": "host-request:opaque",
                    "receiptRef": "unavailable",
                    "status": "invalid",
                    "errorCode": "PREPARED_CALL_INVALID",
                    "codeModePhase": "unavailable",
                    "preparedCallInvalidReason": "malformed",
                    "shapeDiagnostic": diagnostic,
                },
            },
            separators=(",", ":"),
        )
    )

    assert evidence["failure"]["hostOperationFailure"]["shapeDiagnostic"] == diagnostic
    assert "prepared-call-value" not in json.dumps(evidence)


def test_runtime_failure_keeps_allowlisted_cause_and_drops_message() -> None:
    evidence = _failure_evidence(
        failure_reason=json.dumps(
            {
                "failureCode": "runtime_error",
                "failurePhase": "runtime_process",
                "failureDetail": "process_exit",
                "failureSubreason": "runtime_execution_failed",
                "failureCause": "provider_client_failure",
                "runtimePhase": "conversation",
                "exceptionClass": "RuntimeError",
            },
            separators=(",", ":"),
        ),
        runtime_exit={
            "kind": "failed",
            "failure": {
                "code": "runtime_error",
                "retryable": False,
                "cause": "provider_client_failure",
                "runtimePhase": "conversation",
                "exceptionClass": "RuntimeError",
                "message": "provider response must not escape",
            },
        },
    )

    assert evidence["failure"]["reasonCause"] == "provider_client_failure"
    assert evidence["runtimeExit"]["failure"]["cause"] == "provider_client_failure"
    assert "provider response must not escape" not in json.dumps(evidence)


def test_child_failure_diagnostic_is_allowlisted_and_bounded() -> None:
    helpers = _invoke_helpers()
    diagnostic = {
        "exceptionClass": "ModuleNotFoundError",
        "module": "plane_runtime",
        "category": "module_not_found",
        "stderrSha256": "a" * 64,
        "stderrBytes": 128,
        "termination": "exit",
        "exitCode": 1,
    }
    reason = {
        "failureCode": "runtime_process_failed",
        "failurePhase": "runtime_process",
        "failureDetail": "process_exit",
        "failureSubreason": "runtime_execution_failed",
        "childDiagnostic": diagnostic,
    }
    evidence = _failure_evidence(
        failure_code="runtime_process_failed",
        failure_reason=json.dumps(reason, separators=(",", ":")),
    )

    assert helpers["_bounded_child_diagnostic"](diagnostic) == diagnostic
    assert evidence["failure"]["childDiagnostic"] == diagnostic
    assert helpers["_bounded_child_diagnostic"]({**diagnostic, "stderr": "raw"}) is None


def test_replay_requires_same_identity_and_zero_side_effects() -> None:
    gate = _invoke_helpers()["_successful_primary_replay_gate"]
    common = {
        "invocation_state": "succeeded",
        "run_state": "succeeded",
        "primary_invocation_id": "invocation:accepted",
        "observed_invocation_id": "invocation:accepted",
        "primary_idempotency_key": "idempotency:accepted",
        "observed_idempotency_key": "idempotency:accepted",
        "replay_deltas": {
            "providerAttempts": 0,
            "invocations": 0,
            "receipts": 0,
            "audits": 0,
            "usage": 0,
            "outcomes": 0,
            "publications": 0,
            "terminalEvents": 0,
        },
        "semantic_side_effects": 0,
    }

    assert gate(**common)
    for change in (
        {"observed_invocation_id": "invocation:other"},
        {"observed_idempotency_key": "idempotency:other"},
        {"semantic_side_effects": 1},
        {"replay_deltas": {**common["replay_deltas"], "providerAttempts": 1}},
    ):
        candidate = dict(common)
        candidate.update(change)
        assert not gate(**candidate)


def test_completed_provider_attempt_is_not_reconciliation_failure() -> None:
    has_unknown = _invoke_helpers()["_provider_attempts_have_unknown_evidence"]
    completed = SimpleNamespace(
        phase="completed",
        error_code="",
        upstream_initiated=True,
        terminal_at="2026-08-16T00:00:00Z",
    )
    control = SimpleNamespace(state="available", failure_code="")

    assert not has_unknown([completed], control)
    assert has_unknown(
        [SimpleNamespace(**{**vars(completed), "phase": "outcome_unknown"})], control
    )
    assert has_unknown([completed], SimpleNamespace(state="outcome_unknown", failure_code=""))


def test_entrypoint_failure_projects_classification_without_exception_text() -> None:
    evidence = _invoke_helpers()["_entrypoint_failure_evidence"](
        RuntimeError("provider-secret-must-not-appear"),
        binding={},
        authority_id="authority:test",
        canary_ids={"permitted": "permitted", "denied": "denied"},
    )

    assert evidence["failure"] == {
        "phase": "api-invocation",
        "errorClass": "RuntimeError",
        "exitCode": 1,
        "reasonCode": "runtime_error",
        "reasonPhase": "launcher",
        "reasonDetail": "unclassified_exception",
        "reasonSubreason": "upstream_exception",
    }
    assert "provider-secret-must-not-appear" not in json.dumps(evidence)


def test_terminal_lifecycle_projection_rejects_unbounded_values() -> None:
    parser = _invoke_helpers()["_bounded_terminal_lifecycle_observation"]
    observation = {
        "protocol": "hermes.terminal-lifecycle/v1",
        "category": "terminal_lifecycle",
        "hook_installed": True,
        "terminal_action_observed": True,
        "terminal_reason": "product_outcome_published",
        "terminal_action": {
            "reason": "product_outcome_published",
            "observed_at": "post_tool_batch",
            "api_call_count": 2,
            "provider_responses": 2,
            "iteration_budget_used": 2,
            "iteration_budget_remaining": 14,
        },
        "outcome_publication": {
            "status": "ok",
            "replayed": False,
            "publication_action": "applied",
            "operation_ref": "operation:plane.finish",
            "terminal_armed": True,
        },
        "finalization": {
            "api_call_count": 2,
            "provider_responses": 2,
            "max_iterations": 16,
            "iteration_budget_max_total": 16,
            "iteration_budget_used": 2,
            "iteration_budget_remaining": 14,
            "exit_reason_before_mapping": "terminal_action",
            "exit_reason_after_mapping": "terminal_action",
        },
    }

    assert parser(json.dumps(observation, separators=(",", ":"))) == observation
    observation["outcome_publication"]["status"] = "raw-provider-message"
    with pytest.raises(RuntimeError, match="terminal lifecycle publication values invalid"):
        parser(json.dumps(observation, separators=(",", ":")))


def test_summary_sanitizer_removes_credentials_before_hashing() -> None:
    from summarize_agent_g4 import sanitize, summarize

    raw = "1 passed in 0.1s\napi_key=super-secret\nAuthorization: Bearer token-value\n"
    sanitized = sanitize(raw)
    summary = summarize(raw)

    assert "super-secret" not in sanitized
    assert "token-value" not in sanitized
    assert summary["evidence_sha256"] == hashlib.sha256(sanitized.encode()).hexdigest()

import copy

import pytest

from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    content_digest,
    validate_runtime_durable_state,
    validate_runtime_event,
    validate_runtime_exit,
)


def _event():
    return {
        "protocol": "plane.agent-runtime/v1",
        "trust": "untrusted",
        "workspaceRef": "workspace:test",
        "actorRef": "actor:test",
        "runId": "run:test",
        "invocationId": "invocation:test",
        "sequence": 0,
        "eventId": "event:test",
        "idempotencyKey": "idempotency:event-test",
        "correlationId": "correlation:test",
        "causationRef": "causation:test",
        "observedAt": "2026-08-05T00:00:00Z",
        "body": {
            "kind": "progress_observed",
            "payload": {"kind": "inline_text", "contentType": "text/plain", "text": "Observed."},
            "publication": {"action": "observation_only"},
        },
    }


def _exit():
    return {
        "protocol": "plane.agent-runtime/v1",
        "authority": "runtime_evidence_only",
        "workspaceRef": "workspace:test",
        "actorRef": "actor:test",
        "runId": "run:test",
        "invocationId": "invocation:test",
        "finalSequence": 0,
        "idempotencyKey": "idempotency:exit-test",
        "correlationId": "correlation:test",
        "causationRef": "causation:test",
        "kind": "completed",
    }


def _genesis():
    state = {
        "protocol": "plane.agent-runtime/v1",
        "stateVersion": "v1",
        "binding": {
            "workspaceRef": "workspace:test",
            "actorRef": "actor:test",
            "profileVersionRef": "profile-version:test",
            "runId": "run:test",
            "snapshotContentDigest": "snapshot:" + "a" * 64,
        },
        "state": "queued",
        "revision": 0,
        "lastAcceptedSequence": 0,
        "acceptedEvents": [],
        "acceptedHumanInputAnswers": [],
        "acceptedExits": [],
    }
    return {**state, "stateDigest": content_digest(state)}


def test_runtime_event_and_exit_use_generated_schema_validation():
    assert validate_runtime_event(_event())["body"]["kind"] == "progress_observed"
    assert validate_runtime_exit(_exit())["kind"] == "completed"

    unknown = copy.deepcopy(_event())
    unknown["unexpected"] = True
    with pytest.raises(RuntimeContractError, match="Additional properties"):
        validate_runtime_event(unknown)


def test_runtime_exit_failure_cause_is_finite_and_runtime_error_only():
    causal = _exit()
    causal.update(
        {
            "kind": "failed",
            "failure": {
                "code": "runtime_error",
                "message": "safe compatibility message",
                "retryable": False,
                "cause": "host_operation_failure",
            },
        }
    )
    assert validate_runtime_exit(causal)["failure"]["cause"] == "host_operation_failure"

    invalid_cause = copy.deepcopy(causal)
    invalid_cause["failure"]["cause"] = "raw-host-message"
    with pytest.raises(RuntimeContractError):
        validate_runtime_exit(invalid_cause)

    invalid_code = copy.deepcopy(causal)
    invalid_code["failure"]["code"] = "budget_exhausted"
    with pytest.raises(RuntimeContractError):
        validate_runtime_exit(invalid_code)


def test_runtime_durable_state_digest_and_revision_continuity_match_l1():
    genesis = _genesis()
    assert validate_runtime_durable_state(genesis) == genesis

    event = {
        "workspaceRef": genesis["binding"]["workspaceRef"],
        "actorRef": genesis["binding"]["actorRef"],
        "profileVersionRef": genesis["binding"]["profileVersionRef"],
        "runId": genesis["binding"]["runId"],
        "snapshotContentDigest": genesis["binding"]["snapshotContentDigest"],
        "invocationId": "invocation:test",
        "eventId": "event:test",
        "idempotencyKey": "idempotency:event-test",
        "correlationId": "correlation:test",
        "causationRef": "causation:test",
        "sequence": 0,
        "fingerprint": content_digest({"event": "test"}),
        "kind": "progress_observed",
    }
    running = {
        **genesis,
        "state": "running",
        "revision": 1,
        "previousRevision": 0,
        "previousStateDigest": genesis["stateDigest"],
        "acceptedEvents": [event],
    }
    running["stateDigest"] = content_digest({key: value for key, value in running.items() if key != "stateDigest"})
    assert validate_runtime_durable_state(running)["revision"] == 1

    broken = copy.deepcopy(running)
    broken["previousRevision"] = 4
    broken["stateDigest"] = content_digest({key: value for key, value in broken.items() if key != "stateDigest"})
    with pytest.raises(RuntimeContractError, match="previousRevision"):
        validate_runtime_durable_state(broken)

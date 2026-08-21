import copy

import pytest

from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    content_digest,
    validate_runtime_durable_state,
    validate_runtime_event,
    validate_runtime_exit,
)
from plane.agent.runtime.host_rpc import (
    PlaneHostCall,
    PlaneHostHTTPServer,
    PlaneHostResult,
    PlaneHostServer,
    PreparedCallInvalid,
    PreparedCallRegistry,
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


def test_prepared_call_rejections_have_bounded_private_reasons():
    registry = PreparedCallRegistry()
    prepared_ref = registry.register({"project_id": "project:test", "issue_id": "issue:test"})

    cases = [
        ({"preparedCallRef": prepared_ref, "issue_id": "must-not-escape"}, "malformed"),
        ({"preparedCallRef": f"prepared-call:{'0' * 64}:unknown"}, "unknown"),
    ]
    for input_data, reason in cases:
        with pytest.raises(PreparedCallInvalid) as captured:
            registry.resolve(input_data)
        assert captured.value.reason == reason
        assert prepared_ref not in str(captured.value)
        assert "must-not-escape" not in str(captured.value)

    registry.records[prepared_ref]["input"] = {"project_id": "different", "issue_id": "target"}
    with pytest.raises(PreparedCallInvalid) as captured:
        registry.resolve({"preparedCallRef": prepared_ref})
    assert captured.value.reason == "digest_mismatch"

    bound = PreparedCallRegistry()
    bound_ref = bound.register({"project_id": "project:test", "issue_id": "issue:test"})
    bound.resolve(
        {"preparedCallRef": bound_ref},
        correlation_id="correlation:first",
        idempotency_key="idempotency:first",
    )
    with pytest.raises(PreparedCallInvalid) as captured:
        bound.resolve(
            {"preparedCallRef": bound_ref},
            correlation_id="correlation:other",
            idempotency_key="idempotency:other",
        )
    assert captured.value.reason == "binding_mismatch"

    bound.mark_consumed(bound_ref)
    with pytest.raises(PreparedCallInvalid) as captured:
        bound.resolve(
            {"preparedCallRef": bound_ref},
            correlation_id="correlation:other",
            idempotency_key="idempotency:other",
        )
    assert captured.value.reason == "consumed"


def test_prepared_call_accepts_only_the_canonical_ref_shape():
    registry = PreparedCallRegistry()
    prepared_ref = registry.register({"project_id": "project:test", "issue_id": "issue:test"})

    assert registry.normalize({"preparedCallRef": prepared_ref}) == {"preparedCallRef": prepared_ref}
    assert registry.normalize({"preparedCallRef": {"preparedCallRef": prepared_ref}}) == {
        "preparedCallRef": prepared_ref
    }
    assert registry.resolve({"preparedCallRef": prepared_ref}) == {
        "project_id": "project:test",
        "issue_id": "issue:test",
    }


@pytest.mark.parametrize(
    "malformed_input",
    [
        lambda ref: {"preparedCallRef": {"preparedCallRef": {"preparedCallRef": ref}}},
        lambda ref: {
            "preparedCallRef": {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"preparedCallRef": ref},
            }
        },
        lambda ref: {"preparedCallRef": ref, "extra": "x"},
        lambda ref: {"preparedCallRef": "not-a-prepared-call"},
    ],
)
def test_prepared_call_normalization_rejects_wrappers_and_extra_fields(malformed_input):
    registry = PreparedCallRegistry()
    prepared_ref = registry.register({"project_id": "project:test", "issue_id": "issue:test"})

    with pytest.raises(PreparedCallInvalid) as captured:
        registry.normalize(malformed_input(prepared_ref))

    assert captured.value.reason == "malformed"
    assert prepared_ref not in str(captured.value)


def test_prepared_call_reason_is_owner_evidence_only(tmp_path):
    call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="read",
        operation_ref="operation:work_item.read",
        input={"preparedCallRef": "prepared-call:opaque"},
        source="model",
    )
    result = PlaneHostResult(
        request_ref=call.request_ref,
        correlation_id=call.correlation_id,
        idempotency_key=call.idempotency_key,
        status="invalid",
        replayed=False,
        error_code="PREPARED_CALL_INVALID",
        error_message="Prepared work-item read reference is invalid",
        prepared_call_invalid_reason="unknown",
    )
    server = PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=lambda _call: result)

    assert "preparedCallInvalidReason" not in result.to_wire()
    assert server._invoke_once(call) == result
    assert server.failure_evidence == {
        "operationId": "work_item.read",
        "attemptRef": call.request_ref,
        "receiptRef": "unavailable",
        "status": "invalid",
        "errorCode": "PREPARED_CALL_INVALID",
        "codeModePhase": "unavailable",
        "preparedCallInvalidReason": "unknown",
        "shapeDiagnostic": {
            "schemaVersion": "plane.prepared-call-shape/v1",
            "acceptedForm": "canonical_ref",
            "failureClass": "unknown",
            "shape": {
                "keyNames": ["preparedCallRef"],
                "keyNamesTruncated": False,
                "valueTypes": ["object", "string"],
                "nestingDepth": 1,
                "sizeClass": "small",
            },
        },
    }


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

    for cause in (
        "dependency_failure",
        "permission_failure",
        "resource_failure",
        "timeout_failure",
        "provider_client_failure",
        "runtime_unknown_failure",
        "provider_auth_failure",
        "provider_entitlement_failure",
        "provider_rate_limit",
        "provider_request_failure",
        "provider_transport_failure",
        "provider_unknown_failure",
    ):
        candidate = copy.deepcopy(causal)
        candidate["failure"]["cause"] = cause
        assert validate_runtime_exit(candidate)["failure"]["cause"] == cause

    invalid_cause = copy.deepcopy(causal)
    invalid_cause["failure"]["cause"] = "raw-host-message"
    with pytest.raises(RuntimeContractError):
        validate_runtime_exit(invalid_cause)

    invalid_code = copy.deepcopy(causal)
    invalid_code["failure"]["code"] = "budget_exhausted"
    with pytest.raises(RuntimeContractError):
        validate_runtime_exit(invalid_code)


def test_host_server_retains_bounded_first_operation_failure_context(tmp_path):
    call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="code",
        operation_ref="operation:work_item.rename",
        input={"name": "bounded"},
        source="code",
    )
    result = PlaneHostResult(
        request_ref=call.request_ref,
        correlation_id=call.correlation_id,
        idempotency_key=call.idempotency_key,
        status="unavailable",
        replayed=False,
        output={
            "requestId": "request:test",
            "auditReceipt": "audit:test",
            "error": {"code": "OPERATION_UNAVAILABLE", "message": "must not escape"},
        },
        error_code="OPERATION_UNAVAILABLE",
        error_message="must not escape",
    )
    server = PlaneHostServer(
        socket_path=tmp_path / "host.sock",
        invoke=lambda _call: result,
    )

    assert server._invoke_once(call) == result
    assert server.failure_evidence == {
        "operationId": "work_item.rename",
        "attemptRef": "operation-attempt:request:test",
        "receiptRef": "audit-receipt:audit:test",
        "status": "unavailable",
        "errorCode": "OPERATION_UNAVAILABLE",
        "codeModePhase": "host_callback",
    }


def test_host_server_does_not_promote_expected_evaluator_denial_to_runtime_failure(tmp_path):
    call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="mutate",
        operation_ref="operation:agent.outcome.evaluate",
        input={},
        source="model",
    )
    result = PlaneHostResult(
        request_ref=call.request_ref,
        correlation_id=call.correlation_id,
        idempotency_key=call.idempotency_key,
        status="denied",
        replayed=False,
        output={"error": {"code": "NOT_AUTHORIZED"}},
        error_code="NOT_AUTHORIZED",
        error_message="expected denial",
    )
    server = PlaneHostServer(
        socket_path=tmp_path / "host.sock",
        invoke=lambda _call: result,
    )

    assert server._invoke_once(call) == result
    assert server.failure_evidence is None


def _host_failure_result(call, *, status, error_code):
    return PlaneHostResult(
        request_ref=call.request_ref,
        correlation_id=call.correlation_id,
        idempotency_key=call.idempotency_key,
        status=status,
        replayed=False,
        output={"error": {"code": error_code}},
        error_code=error_code,
        error_message="test failure",
    )


def _host_failure_server(server_kind, tmp_path, invoke):
    if server_kind == "unix":
        return PlaneHostServer(socket_path=tmp_path / "host.sock", invoke=invoke)
    return PlaneHostHTTPServer(
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        port=0,
        auth_token="test-token",
        invoke=invoke,
    )


@pytest.mark.parametrize("server_kind", ["unix", "http"])
@pytest.mark.parametrize(
    ("status", "error_code"),
    [("denied", "NOT_AUTHORIZED"), ("invalid", "VALIDATION_ERROR")],
)
def test_host_servers_skip_recoverable_generic_call_observations(tmp_path, server_kind, status, error_code):
    call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="mutate",
        operation_ref="operation:work_item.rename",
        input={"name": "recoverable"},
        source="model",
    )
    result = _host_failure_result(call, status=status, error_code=error_code)
    server = _host_failure_server(server_kind, tmp_path, invoke=lambda _call: result)

    assert server._invoke_once(call) == result
    assert server.failure_evidence is None


@pytest.mark.parametrize("server_kind", ["unix", "http"])
def test_host_servers_record_publish_denial_as_fatal(tmp_path, server_kind):
    call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="publish",
        operation_ref="operation:agent.outcome.publish",
        input={"kind": "outcome"},
        source="model",
    )
    result = _host_failure_result(call, status="denied", error_code="NOT_AUTHORIZED")
    server = _host_failure_server(server_kind, tmp_path, invoke=lambda _call: result)

    assert server._invoke_once(call) == result
    assert server.failure_evidence == {
        "operationId": "agent.outcome.publish",
        "attemptRef": call.request_ref,
        "receiptRef": "unavailable",
        "status": "denied",
        "errorCode": "NOT_AUTHORIZED",
        "codeModePhase": "unavailable",
    }


@pytest.mark.parametrize("server_kind", ["unix", "http"])
def test_host_servers_retain_first_actual_fatal_after_recoverable_call(tmp_path, server_kind):
    generic_call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="mutate",
        operation_ref="operation:work_item.rename",
        input={"name": "recoverable"},
        source="model",
    )
    first_fatal_call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="code",
        operation_ref="operation:work_item.update",
        input={"name": "first fatal"},
        source="code",
    )
    later_fatal_call = PlaneHostCall(
        run_id="run:test",
        invocation_id="invocation:test",
        correlation_id="correlation:test",
        action="code",
        operation_ref="operation:work_item.delete",
        input={"name": "later fatal"},
        source="code",
    )
    results = {
        generic_call.request_ref: _host_failure_result(
            generic_call,
            status="denied",
            error_code="NOT_AUTHORIZED",
        ),
        first_fatal_call.request_ref: _host_failure_result(
            first_fatal_call,
            status="unavailable",
            error_code="UPSTREAM_FAILURE",
        ),
        later_fatal_call.request_ref: _host_failure_result(
            later_fatal_call,
            status="conflict",
            error_code="PLANE_CONFLICT",
        ),
    }
    server = _host_failure_server(server_kind, tmp_path, invoke=lambda call: results[call.request_ref])

    assert server._invoke_once(generic_call) == results[generic_call.request_ref]
    assert server.failure_evidence is None
    assert server._invoke_once(first_fatal_call) == results[first_fatal_call.request_ref]
    assert server._invoke_once(later_fatal_call) == results[later_fatal_call.request_ref]
    assert server.failure_evidence == {
        "operationId": "work_item.update",
        "attemptRef": first_fatal_call.request_ref,
        "receiptRef": "unavailable",
        "status": "unavailable",
        "errorCode": "UPSTREAM_FAILURE",
        "codeModePhase": "host_callback",
    }


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

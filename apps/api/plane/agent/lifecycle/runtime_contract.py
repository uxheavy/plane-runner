# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Boundary adapter for the generated Plane Agent runtime contract.

The JSON Schema files under ``contract_artifacts`` are an exact mechanical
copy of the accepted L1 package.  This module only verifies and executes those
artifacts; it does not carry a second hand-maintained protocol definition.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import AgentDomainError


PROTOCOL = "plane.agent-runtime/v1"
MAX_REF_BYTES = 128
MAX_BOUNDED_TEXT_BYTES = 4096
MAX_BOUNDED_PROMPT_BYTES = 32768
MAX_BOUNDED_TOKEN_BYTES = 256
MAX_BOUNDED_BYTE_COUNT = 1_048_576
MAX_INTEGER = 2_147_483_647

# This is deliberately one deterministic path inside the API artifact.  The
# API image copies ``plane/`` as a unit, so the bytes are available in both
# host checkouts and ``/code`` containers without a runtime package fallback.
ARTIFACT_DIRECTORY = Path(__file__).resolve().parent / "contract_artifacts" / "v1"
EXPECTED_MANIFEST_SHA256 = "0d722ac0028e0bff307186aa9ec3b2367115a275d21132bf7686e3eebbf6b197"
LEGACY_COMMAND_FINGERPRINT_PREFIX = "legacy1:"
_SCHEMA_NAMES = frozenset(
    {
        "run-snapshot",
        "invocation-envelope",
        "runtime-event",
        "runtime-exit",
        "runtime-durable-state",
    }
)
_REF_PATTERN = re.compile(r"^(?P<namespace>[A-Za-z][A-Za-z0-9-]*):(?P<suffix>[A-Za-z0-9][A-Za-z0-9._~/-]{0,119})$")


class RuntimeContractError(AgentDomainError, ValueError):
    """Raised when Plane data cannot satisfy the accepted runtime contract."""


def _verified_contract_artifacts() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Read and verify the exact accepted manifest and schema bytes."""

    directory = ARTIFACT_DIRECTORY
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeContractError(f"runtime contract manifest is unavailable: {manifest_path}")
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise RuntimeContractError(f"runtime contract manifest is unavailable: {manifest_path}") from exc
    if hashlib.sha256(manifest_bytes).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeContractError(f"runtime contract manifest digest drifted: {manifest_path}")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"runtime contract manifest is invalid: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeContractError(f"runtime contract artifact must be an object: {manifest_path}")
    if manifest.get("protocol") != PROTOCOL:
        raise RuntimeContractError("runtime contract protocol does not match Plane Agent v1")
    schemas = manifest.get("schemas")
    if not isinstance(schemas, dict) or frozenset(schemas) != _SCHEMA_NAMES:
        raise RuntimeContractError("runtime contract manifest does not contain the exact accepted schema set")

    parsed_schemas = {}
    for name in _SCHEMA_NAMES:
        entry = schemas[name]
        expected_filename = f"{name}.schema.json"
        if not isinstance(entry, dict) or entry.get("filename") != expected_filename:
            raise RuntimeContractError(f"runtime contract manifest entry is invalid: {name}")
        schema_path = directory / expected_filename
        if schema_path.parent != directory or not schema_path.is_file():
            raise RuntimeContractError(f"runtime contract schema is unavailable: {schema_path}")
        try:
            schema_bytes = schema_path.read_bytes()
        except OSError as exc:
            raise RuntimeContractError(f"runtime contract schema is unavailable: {schema_path}") from exc
        digest = hashlib.sha256(schema_bytes).hexdigest()
        if digest != entry.get("sha256"):
            raise RuntimeContractError(f"runtime contract schema digest drifted: {schema_path}")
        try:
            schema = json.loads(schema_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeContractError(f"runtime contract schema is invalid: {schema_path}") from exc
        if not isinstance(schema, dict):
            raise RuntimeContractError(f"runtime contract schema must be an object: {schema_path}")
        parsed_schemas[name] = schema
    return deepcopy(manifest), parsed_schemas


def contract_manifest() -> dict[str, Any]:
    """Return a freshly verified copy of the accepted runtime manifest."""

    manifest, _ = _verified_contract_artifacts()
    return manifest


def contract_digests() -> dict[str, str]:
    schemas = contract_manifest()["schemas"]
    return {
        "runSnapshot": schemas["run-snapshot"]["sha256"],
        "invocationEnvelope": schemas["invocation-envelope"]["sha256"],
        "runtimeEvent": schemas["runtime-event"]["sha256"],
        "runtimeExit": schemas["runtime-exit"]["sha256"],
        "runtimeDurableState": schemas["runtime-durable-state"]["sha256"],
    }


def canonical_json(value: Any) -> str:
    """Match the L1 canonical JSON writer for persisted JSON values."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError("runtime contract value is not canonical JSON") from exc


def content_digest(value: Any) -> str:
    return f"content:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def command_fingerprint(operation: str, binding: Any) -> str:
    """Create one deterministic digest for an idempotent semantic command."""

    command = canonical_json({"operation": operation, "binding": binding})
    return f"command:{hashlib.sha256(command.encode('utf-8')).hexdigest()}"


def legacy_command_fingerprint(operation: str, binding: Any) -> str:
    """Bind a pre-0125 row to facts that survived the migration boundary."""

    command = canonical_json({"version": "agent-lifecycle-0125-legacy-v1", "operation": operation, "binding": binding})
    return f"{LEGACY_COMMAND_FINGERPRINT_PREFIX}{hashlib.sha256(command.encode('utf-8')).hexdigest()}"


def promote_legacy_command_fingerprint(fingerprint: str, current_fingerprint: str) -> str:
    """Replace a verified legacy binding with the exact accepted command digest."""

    if not re.fullmatch(r"legacy1:[0-9a-f]{64}", fingerprint):
        raise RuntimeContractError("Only legacy1 command fingerprints can be promoted")
    if not re.fullmatch(r"command:[0-9a-f]{64}", current_fingerprint):
        raise RuntimeContractError("Legacy promotion requires a current command fingerprint")
    return current_fingerprint


def snapshot_digest(content: dict[str, Any]) -> str:
    return f"snapshot:{hashlib.sha256(canonical_json(content).encode('utf-8')).hexdigest()}"


def namespaced_ref(namespace: str, value: str) -> str:
    """Construct an exact L1 reference without normalizing caller input."""

    if not isinstance(namespace, str) or not isinstance(value, str):
        raise RuntimeContractError("runtime references require string namespace and value")
    candidate = value if value.startswith(f"{namespace}:") else f"{namespace}:{value}"
    match = _REF_PATTERN.fullmatch(candidate)
    if match is None or match.group("namespace") != namespace or len(candidate.encode("utf-8")) > MAX_REF_BYTES:
        raise RuntimeContractError(f"{namespace} reference is not valid under the accepted byte limit")
    return candidate


def _schema_validator(name: str, schemas: dict[str, dict[str, Any]]):
    try:
        from jsonschema import Draft202012Validator, validators
    except ImportError as exc:
        raise RuntimeContractError("the generated runtime schema validator is unavailable") from exc

    def utf8_byte_max(validator, limit, instance, schema):
        if isinstance(instance, str) and len(instance.encode("utf-8")) > limit:
            yield jsonschema.ValidationError(f"string exceeds {limit} UTF-8 bytes")

    def equal_properties(validator, pairs, instance, schema):
        if not isinstance(instance, dict):
            return
        for left, right in pairs:
            if left in instance and right in instance and instance[left] != instance[right]:
                yield jsonschema.ValidationError(f"{left} and {right} must be equal")

    def serialized_utf8_max(validator, limit, instance, schema):
        try:
            size = len(canonical_json(instance).encode("utf-8"))
        except RuntimeContractError:
            return
        if size > limit:
            yield jsonschema.ValidationError(f"serialized value exceeds {limit} UTF-8 bytes")

    import jsonschema

    ContractValidator = validators.extend(
        Draft202012Validator,
        {
            "x-utf8ByteMax": utf8_byte_max,
            "x-equalProperties": equal_properties,
            "x-serializedUtf8ByteMax": serialized_utf8_max,
        },
    )
    return ContractValidator(schemas[name])


@lru_cache(maxsize=None)
def _compiled_validator(name: str):
    _, schemas = _verified_contract_artifacts()
    return _schema_validator(name, schemas)


def _validator(name: str):
    """Verify packaged bytes on every use before consulting the validator cache."""

    _verified_contract_artifacts()
    return _compiled_validator(name)


def _clear_contract_cache() -> None:
    _compiled_validator.cache_clear()


contract_manifest.cache_clear = _clear_contract_cache


def _validate(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeContractError(f"{name} must be an object")
    # Recheck the on-disk bytes at every API use, not only when the compiled
    # validator is first cached.  A missing or tampered artifact therefore
    # fails closed even after a long-lived process has validated once.
    _verified_contract_artifacts()
    errors = sorted(_validator(name).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or name
        raise RuntimeContractError(f"{name}.{location}: {error.message}")
    return value


def validate_run_snapshot(snapshot: Any) -> dict[str, Any]:
    """Validate a snapshot with the exact generated L1 schema and digest."""

    value = _validate("run-snapshot", snapshot)
    if value["contractDigests"] != contract_digests():
        raise RuntimeContractError("RunSnapshot.contractDigests does not match the accepted manifest")
    expected_content_digest = snapshot_digest({key: value[key] for key in value if key != "contentDigest"})
    if value["contentDigest"] != expected_content_digest:
        raise RuntimeContractError("RunSnapshot.contentDigest does not match canonical immutable content")
    return value


def validate_invocation_envelope(envelope: Any) -> dict[str, Any]:
    """Validate an invocation envelope with the exact generated L1 schema."""

    return _validate("invocation-envelope", envelope)


def validate_runtime_event(event: Any) -> dict[str, Any]:
    """Validate an untrusted RuntimeEvent with the generated L1 schema."""

    return _validate("runtime-event", event)


def validate_runtime_exit(exit_frame: Any) -> dict[str, Any]:
    """Validate a RuntimeExit evidence frame with the generated L1 schema."""

    return _validate("runtime-exit", exit_frame)


def _runtime_state_error(message: str) -> RuntimeContractError:
    return RuntimeContractError(f"runtime-durable-state: {message}")


def _runtime_state_require(condition: bool, message: str) -> None:
    if not condition:
        raise _runtime_state_error(message)


def _same_runtime_json(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def _runtime_product_keys(binding: dict[str, Any]) -> tuple[str, ...]:
    identity = {
        "operationAttemptRef": binding["operationAttemptRef"],
        "operationRef": binding["operationRef"],
        "applicationServiceRef": binding["applicationServiceRef"],
        "gatewayReceiptRef": binding["gatewayReceiptRef"],
        "receiptRef": binding["receiptRef"],
        "auditReceiptRef": binding["auditReceiptRef"],
        "productEventRef": binding["productEventRef"],
    }
    if "cancellationRef" in binding:
        identity["cancellationRef"] = binding["cancellationRef"]
    return (
        f"operationAttemptRef:{binding['operationAttemptRef']}",
        f"gatewayReceiptRef:{binding['gatewayReceiptRef']}",
        f"receiptRef:{binding['receiptRef']}",
        f"auditReceiptRef:{binding['auditReceiptRef']}",
        f"productEventRef:{binding['productEventRef']}",
        f"product:{binding['productKind']}:{binding['productRef']}",
        f"operation-gateway:{binding['operationRef']}:{binding['gatewayReceiptRef']}",
        f"binding:{canonical_json(identity)}",
    )


def validate_runtime_durable_state(state: Any) -> dict[str, Any]:
    """Validate RuntimeDurableState shape, digest, and the accepted L1 rules."""

    value = _validate("runtime-durable-state", state)
    expected_digest = content_digest({key: item for key, item in value.items() if key != "stateDigest"})
    _runtime_state_require(
        value["stateDigest"] == expected_digest,
        "stateDigest does not match canonical state content",
    )

    has_previous_revision = "previousRevision" in value
    has_previous_digest = "previousStateDigest" in value
    _runtime_state_require(
        has_previous_revision == has_previous_digest,
        "previousRevision and previousStateDigest must be supplied together",
    )
    revision = value["revision"]
    if revision == 0:
        _runtime_state_require(
            value["state"] == "queued"
            and not has_previous_revision
            and value["lastAcceptedSequence"] == 0
            and not value["acceptedEvents"]
            and not value["acceptedHumanInputAnswers"]
            and not value["acceptedExits"]
            and "terminal" not in value
            and "pendingInput" not in value,
            "revision zero is reserved for the canonical empty queued genesis state",
        )
    else:
        _runtime_state_require(
            value.get("previousRevision") == revision - 1 and value.get("previousStateDigest") is not None,
            "previousRevision must link to the immediately preceding durable revision",
        )

    binding = value["binding"]
    event_ids = set()
    event_keys = set()
    product_keys = set()
    previous_sequence = 0 if not value["acceptedEvents"] else -1
    for index, event in enumerate(value["acceptedEvents"]):
        _runtime_state_require(event["eventId"] not in event_ids, f"acceptedEvents[{index}].eventId must be unique")
        _runtime_state_require(
            event["idempotencyKey"] not in event_keys,
            f"acceptedEvents[{index}].idempotencyKey must be unique",
        )
        _runtime_state_require(
            event["sequence"] == previous_sequence + 1,
            f"acceptedEvents[{index}].sequence is not strictly monotonic",
        )
        _runtime_state_require(
            all(
                event[field] == binding[field]
                for field in ("workspaceRef", "actorRef", "profileVersionRef", "runId", "snapshotContentDigest")
            ),
            f"acceptedEvents[{index}] is not bound to the durable snapshot",
        )
        event_ids.add(event["eventId"])
        event_keys.add(event["idempotencyKey"])
        previous_sequence = event["sequence"]
        expected_product_kind = {
            "conversation_publication_observed": "conversation",
            "input_request_observed": "input_request",
            "artifact_observed": "artifact",
            "outcome_submission_observed": "outcome_submission",
            "failure_observed": "run_failure",
            "blocker_observed": "run_blocker",
            "cancellation_observed": "run_cancellation",
        }.get(event["kind"])
        has_product_binding = "productBinding" in event
        _runtime_state_require(
            (expected_product_kind is not None) == has_product_binding,
            f"acceptedEvents[{index}].productBinding has the wrong presence",
        )
        if has_product_binding:
            product_binding = event["productBinding"]
            _runtime_state_require(
                product_binding["productKind"] == expected_product_kind,
                f"acceptedEvents[{index}].productBinding.productKind does not match the event kind",
            )
            if product_binding["action"] == "applied":
                for key in _runtime_product_keys(product_binding):
                    _runtime_state_require(
                        key not in product_keys,
                        f"acceptedEvents[{index}].productBinding reuses an applied product identity",
                    )
                    product_keys.add(key)
    if value["lastAcceptedSequence"] != previous_sequence:
        raise _runtime_state_error("lastAcceptedSequence must equal the last accepted event sequence")

    answer_event_ids = set()
    answer_receipt_keys = set()
    for index, answer in enumerate(value["acceptedHumanInputAnswers"]):
        _runtime_state_require(
            answer["workspaceRef"] == binding["workspaceRef"] and answer["runId"] == binding["runId"],
            f"acceptedHumanInputAnswers[{index}] is not bound to the durable workspace and run",
        )
        _runtime_state_require(
            answer["responderPrincipal"]["planePrincipalId"] != binding["actorRef"],
            f"acceptedHumanInputAnswers[{index}] responder must remain separate from the Agent actor",
        )
        answer_fact = {key: item for key, item in answer.items() if key != "answerFactDigest"}
        _runtime_state_require(
            answer["answerFactDigest"] == content_digest(answer_fact),
            f"acceptedHumanInputAnswers[{index}].answerFactDigest is not canonical",
        )
        _runtime_state_require(
            answer["answerEventRef"] not in answer_event_ids and answer["answerEventRef"] not in event_ids,
            f"acceptedHumanInputAnswers[{index}].answerEventRef must be unique and separate from runtime events",
        )
        for key in (
            f"authorizationReceiptRef:{answer['authorizationReceiptRef']}",
            f"applicationServiceRef:{answer['applicationServiceRef']}",
            f"gatewayReceiptRef:{answer['gatewayReceiptRef']}",
            f"receiptRef:{answer['receiptRef']}",
            f"auditReceiptRef:{answer['auditReceiptRef']}",
        ):
            _runtime_state_require(
                key not in answer_receipt_keys,
                f"acceptedHumanInputAnswers[{index}] reuses an authorization or application proof",
            )
            answer_receipt_keys.add(key)
        answer_event_ids.add(answer["answerEventRef"])

    exit_invocations = set()
    exit_keys = set()
    terminal_exits = []
    for index, exit_frame in enumerate(value["acceptedExits"]):
        _runtime_state_require(
            exit_frame["invocationId"] not in exit_invocations,
            f"acceptedExits[{index}].invocationId must be unique",
        )
        _runtime_state_require(
            exit_frame["idempotencyKey"] not in exit_keys,
            f"acceptedExits[{index}].idempotencyKey must be unique",
        )
        _runtime_state_require(
            all(
                exit_frame[field] == binding[field]
                for field in ("workspaceRef", "actorRef", "profileVersionRef", "runId", "snapshotContentDigest")
            ),
            f"acceptedExits[{index}] is not bound to the durable snapshot",
        )
        _runtime_state_require(
            exit_frame["finalSequence"] <= value["lastAcceptedSequence"],
            f"acceptedExits[{index}].finalSequence exceeds accepted sequence",
        )
        if exit_frame["kind"] == "waiting_for_input":
            _runtime_state_require(
                "inputEventId" in exit_frame,
                f"acceptedExits[{index}].inputEventId is required for a waiting exit",
            )
            input_event = next(
                (event for event in value["acceptedEvents"] if event["eventId"] == exit_frame["inputEventId"]),
                None,
            )
            _runtime_state_require(
                input_event is not None
                and input_event["kind"] == "input_request_observed"
                and input_event["sequence"] == exit_frame["finalSequence"]
                and input_event.get("productBinding", {}).get("action") == "applied"
                and input_event.get("productBinding", {}).get("productKind") == "input_request",
                f"acceptedExits[{index}].inputEventId must identify the accepted input request at finalSequence",
            )
        else:
            _runtime_state_require(
                "inputEventId" not in exit_frame,
                f"acceptedExits[{index}].inputEventId is only valid for a waiting exit",
            )
        exit_invocations.add(exit_frame["invocationId"])
        exit_keys.add(exit_frame["idempotencyKey"])
        if exit_frame["kind"] != "waiting_for_input":
            terminal_exits.append(exit_frame)
    _runtime_state_require(len(terminal_exits) <= 1, "acceptedExits may contain at most one terminal exit")

    state_name = value["state"]
    if state_name == "queued":
        _runtime_state_require(revision == 0, "queued state must remain revision zero")
    if state_name in {"queued", "running"}:
        _runtime_state_require("terminal" not in value, "terminal is forbidden before a terminal exit")
        _runtime_state_require("pendingInput" not in value, "pendingInput is forbidden outside waiting_for_input")
        _runtime_state_require(not value["acceptedExits"], "acceptedExits is forbidden before an exit")
        return value
    if state_name == "waiting_for_input":
        _runtime_state_require("terminal" not in value, "terminal is forbidden while waiting for input")
        _runtime_state_require("pendingInput" in value, "pendingInput is required while waiting for input")
        pending = value["pendingInput"]
        pending_event = next(
            (event for event in value["acceptedEvents"] if event["eventId"] == pending["eventId"]),
            None,
        )
        _runtime_state_require(
            pending_event is not None
            and pending_event["kind"] == "input_request_observed"
            and pending_event.get("productBinding", {}).get("action") == "applied"
            and pending_event.get("productBinding", {}).get("productKind") == "input_request",
            "pendingInput must bind to an applied input request event",
        )
        product_binding = pending_event["productBinding"]
        for field in (
            "productRef",
            "productEventRef",
            "operationAttemptRef",
            "operationRef",
            "applicationServiceRef",
            "gatewayReceiptRef",
            "receiptRef",
            "auditReceiptRef",
        ):
            pending_field = "inputRequestRef" if field == "productRef" else field
            _runtime_state_require(
                pending[pending_field] == product_binding[field],
                f"pendingInput.{pending_field} must match the accepted input request",
            )
        for field in ("invocationId", "correlationId", "causationRef"):
            _runtime_state_require(
                pending[field] == pending_event[field],
                f"pendingInput.{field} must match the request event",
            )
        _runtime_state_require(not terminal_exits, "waiting_for_input cannot contain a terminal exit")
        _runtime_state_require(value["acceptedExits"], "waiting_for_input must contain a waiting exit")
        _runtime_state_require(
            all(exit_frame["kind"] == "waiting_for_input" for exit_frame in value["acceptedExits"]),
            "waiting_for_input must contain only waiting exits",
        )
        last_exit = value["acceptedExits"][-1]
        _runtime_state_require(
            last_exit["finalSequence"] == value["lastAcceptedSequence"]
            and last_exit.get("inputEventId") == pending["eventId"],
            "waiting_for_input must end with the current pending input exit",
        )
        return value

    _runtime_state_require("terminal" in value, "terminal is required after a terminal exit")
    _runtime_state_require("pendingInput" not in value, "pendingInput is forbidden after a terminal exit")
    _runtime_state_require(len(terminal_exits) == 1, "terminal state must contain one terminal exit")
    terminal = value["terminal"]
    terminal_exit = terminal_exits[0]
    _runtime_state_require(
        terminal_exit.get("terminalEventId") == terminal["eventId"]
        and terminal_exit["invocationId"] == terminal["invocationId"]
        and terminal_exit["finalSequence"] == value["lastAcceptedSequence"],
        "terminal binding must match the accepted terminal exit",
    )
    expected_product_kind = {
        "succeeded": "outcome_submission",
        "failed": "run_failure",
        "blocked": "run_blocker",
        "cancelled": "run_cancellation",
    }[state_name]
    expected_exit_kind = {
        "succeeded": "completed",
        "failed": "failed",
        "blocked": "blocked",
        "cancelled": "cancelled",
    }[state_name]
    expected_event_kind = {
        "succeeded": "outcome_submission_observed",
        "failed": "failure_observed",
        "blocked": "blocker_observed",
        "cancelled": "cancellation_observed",
    }[state_name]
    _runtime_state_require(terminal_exit["kind"] == expected_exit_kind, "terminal exit kind does not match state")
    terminal_event = next((event for event in value["acceptedEvents"] if event["eventId"] == terminal["eventId"]), None)
    _runtime_state_require(
        terminal["productBinding"]["productKind"] == expected_product_kind,
        "terminal product kind does not match state",
    )
    _runtime_state_require(
        terminal_event is not None
        and terminal_event["sequence"] == value["lastAcceptedSequence"]
        and terminal_event["kind"] == expected_event_kind
        and terminal_event["invocationId"] == terminal["invocationId"]
        and terminal_event["correlationId"] == terminal["correlationId"]
        and terminal_event["causationRef"] == terminal["causationRef"]
        and _same_runtime_json(terminal_event.get("productBinding"), terminal["productBinding"]),
        "terminal binding must match the accepted terminal event",
    )
    return value


# Loading the Plane Agent lifecycle boundary is itself a startup/use check for
# the API artifact; there is no valid fallback when these bytes are absent.
contract_manifest()

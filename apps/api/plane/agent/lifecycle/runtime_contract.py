# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Small Python boundary for the accepted Plane runtime contract.

The authoritative contract remains the generated JSON Schema package under
``packages/agent-runtime-contract``.  This module locates those artifacts,
verifies their manifest digests, and performs the subset of parsing needed by
the Plane-owned persistence seam.  It deliberately does not define a second
runtime protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PROTOCOL = "plane.agent-runtime/v1"
MAX_REF_BYTES = 128
MAX_BOUNDED_TEXT_BYTES = 4096
MAX_BOUNDED_PROMPT_BYTES = 32768
MAX_BOUNDED_TOKEN_BYTES = 256
MAX_BOUNDED_BYTE_COUNT = 1_048_576
MAX_CONTEXT_ITEMS = 64
MAX_OPERATION_ITEMS = 64
MAX_ACCEPTANCE_CRITERIA = 32
MAX_INTEGER = 2_147_483_647

# The API image is built from ``apps/api`` and intentionally does not contain
# the TypeScript package. Keep only its accepted manifest pin here for that
# image boundary; when the package is present, ``contract_manifest`` verifies
# the actual schema bytes against the same pin.
_PINNED_MANIFEST = {
    "protocol": PROTOCOL,
    "schemas": {
        "run-snapshot": {
            "filename": "run-snapshot.schema.json",
            "sha256": "e538fe79ede53e6bb2e307600dbefea507e30b996c002c3dab32d543ca0e36a2",
        },
        "invocation-envelope": {
            "filename": "invocation-envelope.schema.json",
            "sha256": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
        },
        "runtime-event": {
            "filename": "runtime-event.schema.json",
            "sha256": "fcbf67ce71fa90dd9661a8f2a739b8119c59357c8bf01afabf4fe92a13de9425",
        },
        "runtime-exit": {
            "filename": "runtime-exit.schema.json",
            "sha256": "055792eb1bf4931dafe19de456b15037522f0b5e8f6a0d2fedfe0e0d1d1d1c05",
        },
        "runtime-durable-state": {
            "filename": "runtime-durable-state.schema.json",
            "sha256": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
        },
    },
}


class RuntimeContractError(ValueError):
    """Raised when Plane data cannot satisfy the accepted runtime contract."""


def _contract_directory() -> Path | None:
    lifecycle_file = Path(__file__).resolve()
    candidates = [
        parent / "packages/agent-runtime-contract/schemas/v1"
        for parent in lifecycle_file.parents
    ]
    candidates.append(Path.cwd() / "packages/agent-runtime-contract/schemas/v1")
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"unable to read runtime contract artifact: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeContractError(f"runtime contract artifact must be an object: {path}")
    return value


@lru_cache(maxsize=1)
def contract_manifest() -> dict[str, Any]:
    """Load and verify the exact accepted L1 manifest and schema bytes."""

    directory = _contract_directory()
    if directory is None:
        return _PINNED_MANIFEST
    manifest = _read_json(directory / "manifest.json")
    if manifest.get("protocol") != PROTOCOL:
        raise RuntimeContractError("runtime contract protocol does not match Plane Agent v1")
    schemas = manifest.get("schemas")
    if not isinstance(schemas, dict):
        raise RuntimeContractError("runtime contract manifest has no schema map")

    for name, entry in schemas.items():
        if not isinstance(entry, dict) or entry.get("filename") != f"{name}.schema.json":
            raise RuntimeContractError(f"runtime contract manifest entry is invalid: {name}")
        schema_path = directory / entry["filename"]
        try:
            digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeContractError(f"runtime contract schema is unavailable: {schema_path}") from exc
        if digest != entry.get("sha256"):
            raise RuntimeContractError(f"runtime contract schema digest drifted: {schema_path}")

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
    """Match the L1 canonical JSON writer for the JSON values in snapshots."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError("runtime contract value is not canonical JSON") from exc


def content_digest(value: Any) -> str:
    return f"content:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def snapshot_digest(content: dict[str, Any]) -> str:
    return f"snapshot:{hashlib.sha256(canonical_json(content).encode('utf-8')).hexdigest()}"


def namespaced_ref(namespace: str, value: str) -> str:
    suffix = value.split(":", 1)[1] if value.startswith(f"{namespace}:") else value
    suffix = re.sub(r"[^A-Za-z0-9._~/-]+", "-", str(suffix)).strip("-./")
    if not suffix or not suffix[0].isalnum():
        suffix = f"ref-{suffix}" if suffix else "ref"
    suffix = suffix[:119]
    result = f"{namespace}:{suffix}"
    if len(result.encode("utf-8")) > MAX_REF_BYTES:
        raise RuntimeContractError(f"{namespace} reference exceeds the accepted byte limit")
    return result


def _require_keys(
    value: Any,
    required: set[str],
    optional: set[str] | None = None,
    path: str = "value",
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeContractError(f"{path} must be an object")
    optional = optional or set()
    allowed = required | optional
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise RuntimeContractError(f"{path} contains unknown fields: {sorted(unknown)}")
    if missing:
        raise RuntimeContractError(f"{path} is missing fields: {sorted(missing)}")
    return value


def _string(value: Any, limit: int, path: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > limit:
        raise RuntimeContractError(f"{path} must be a non-empty string within {limit} UTF-8 bytes")
    return value


def _ref(value: Any, namespace: str, path: str) -> str:
    value = _string(value, MAX_REF_BYTES, path)
    if not re.fullmatch(rf"{re.escape(namespace)}:[A-Za-z0-9][A-Za-z0-9._~/-]{{0,119}}", value):
        raise RuntimeContractError(f"{path} is not a valid {namespace} reference")
    return value


def _digest(value: Any, namespace: str, path: str, hex_length: int = 64) -> str:
    value = _string(value, len(namespace) + 1 + hex_length, path)
    if not re.fullmatch(rf"{re.escape(namespace)}:[a-f0-9]{{{hex_length}}}", value):
        raise RuntimeContractError(f"{path} is not a valid {namespace} digest")
    return value


def _bounded_int(value: Any, path: str, maximum: int = MAX_INTEGER) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > maximum:
        raise RuntimeContractError(f"{path} must be an integer between 0 and {maximum}")
    return value


def validate_run_snapshot(snapshot: Any) -> dict[str, Any]:
    """Parse a snapshot with the L1 shape and verify its immutable digest."""

    value = _require_keys(
        snapshot,
        {
            "protocol",
            "workspaceRef",
            "runId",
            "assignment",
            "actorRef",
            "profile",
            "context",
            "toolCatalog",
            "runtimePolicy",
            "totalBudget",
            "contractDigests",
            "contentDigest",
        },
        path="RunSnapshot",
    )
    if value["protocol"] != PROTOCOL:
        raise RuntimeContractError("RunSnapshot.protocol is not the accepted Plane runtime protocol")
    _ref(value["workspaceRef"], "workspace", "RunSnapshot.workspaceRef")
    _ref(value["runId"], "run", "RunSnapshot.runId")
    assignment = _require_keys(
        value["assignment"],
        {"assignmentRef", "revision", "targetRef", "objective", "acceptanceCriteria"},
        path="RunSnapshot.assignment",
    )
    _ref(assignment["assignmentRef"], "assignment", "RunSnapshot.assignment.assignmentRef")
    _string(assignment["revision"], MAX_BOUNDED_TOKEN_BYTES, "RunSnapshot.assignment.revision")
    _ref(assignment["targetRef"], "target", "RunSnapshot.assignment.targetRef")
    _string(assignment["objective"], MAX_BOUNDED_TEXT_BYTES, "RunSnapshot.assignment.objective")
    criteria = assignment["acceptanceCriteria"]
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_ACCEPTANCE_CRITERIA:
        raise RuntimeContractError("RunSnapshot.assignment.acceptanceCriteria has an invalid item count")
    for index, criterion in enumerate(criteria):
        _string(criterion, MAX_BOUNDED_TEXT_BYTES, f"RunSnapshot.assignment.acceptanceCriteria[{index}]")

    _ref(value["actorRef"], "actor", "RunSnapshot.actorRef")
    profile = _require_keys(
        value["profile"],
        {"profileRef", "revision", "role", "behavioralPrompt"},
        path="RunSnapshot.profile",
    )
    _ref(profile["profileRef"], "profile-version", "RunSnapshot.profile.profileRef")
    _string(profile["revision"], MAX_BOUNDED_TOKEN_BYTES, "RunSnapshot.profile.revision")
    if not isinstance(profile["role"], str) or profile["role"] not in {
        "worker",
        "delegator",
        "gardener",
        "chief_of_staff",
        "hr",
        "evaluator",
        "custom",
    }:
        raise RuntimeContractError("RunSnapshot.profile.role is not a supported Plane Agent role")
    _string(profile["behavioralPrompt"], MAX_BOUNDED_PROMPT_BYTES, "RunSnapshot.profile.behavioralPrompt")

    contexts = value["context"]
    if not isinstance(contexts, list) or len(contexts) > MAX_CONTEXT_ITEMS:
        raise RuntimeContractError("RunSnapshot.context has an invalid item count")
    for index, context in enumerate(contexts):
        context = _require_keys(context, {"contextRef", "revision", "contentDigest"}, path=f"RunSnapshot.context[{index}]")
        _ref(context["contextRef"], "context", f"RunSnapshot.context[{index}].contextRef")
        _string(context["revision"], MAX_BOUNDED_TOKEN_BYTES, f"RunSnapshot.context[{index}].revision")
        _digest(context["contentDigest"], "content", f"RunSnapshot.context[{index}].contentDigest")

    catalog = _require_keys(value["toolCatalog"], {"catalogDigest", "eagerOperations"}, path="RunSnapshot.toolCatalog")
    _digest(catalog["catalogDigest"], "content", "RunSnapshot.toolCatalog.catalogDigest")
    operations = catalog["eagerOperations"]
    if not isinstance(operations, list) or len(operations) > MAX_OPERATION_ITEMS:
        raise RuntimeContractError("RunSnapshot.toolCatalog.eagerOperations has an invalid item count")
    for index, operation in enumerate(operations):
        operation = _require_keys(
            operation,
            {"operationRef", "schemaDigest", "disclosure"},
            path=f"RunSnapshot.toolCatalog.eagerOperations[{index}]",
        )
        _ref(operation["operationRef"], "operation", f"RunSnapshot.toolCatalog.eagerOperations[{index}].operationRef")
        _digest(operation["schemaDigest"], "content", f"RunSnapshot.toolCatalog.eagerOperations[{index}].schemaDigest")
        if not isinstance(operation["disclosure"], str) or operation["disclosure"] not in {"eager", "progressive"}:
            raise RuntimeContractError("RunSnapshot tool disclosure is invalid")

    policy = _require_keys(
        value["runtimePolicy"],
        {"model", "adapter", "isolation", "maxEventPayloadBytes", "maxArtifactBytes", "maxReceiptBytes"},
        path="RunSnapshot.runtimePolicy",
    )
    model = _require_keys(policy["model"], {"provider", "model"}, path="RunSnapshot.runtimePolicy.model")
    _string(model["provider"], MAX_BOUNDED_TOKEN_BYTES, "RunSnapshot.runtimePolicy.model.provider")
    _string(model["model"], MAX_BOUNDED_TOKEN_BYTES, "RunSnapshot.runtimePolicy.model.model")
    _string(policy["adapter"], MAX_BOUNDED_TOKEN_BYTES, "RunSnapshot.runtimePolicy.adapter")
    if policy["isolation"] != "single-invocation":
        raise RuntimeContractError("RunSnapshot.runtimePolicy.isolation must be single-invocation")
    for field in ("maxEventPayloadBytes", "maxArtifactBytes", "maxReceiptBytes"):
        _bounded_int(policy[field], f"RunSnapshot.runtimePolicy.{field}", MAX_BOUNDED_BYTE_COUNT)

    budget = _require_keys(value["totalBudget"], {"inputTokens", "outputTokens", "durationMs"}, path="RunSnapshot.totalBudget")
    for field in ("inputTokens", "outputTokens", "durationMs"):
        _bounded_int(budget[field], f"RunSnapshot.totalBudget.{field}")

    digests = _require_keys(
        value["contractDigests"],
        {"runSnapshot", "invocationEnvelope", "runtimeEvent", "runtimeExit", "runtimeDurableState"},
        path="RunSnapshot.contractDigests",
    )
    expected_digests = contract_digests()
    for field, expected in expected_digests.items():
        if digests[field] != expected:
            raise RuntimeContractError(f"RunSnapshot.contractDigests.{field} does not match the accepted manifest")
        if not re.fullmatch(r"[a-f0-9]{64}", digests[field]):
            raise RuntimeContractError(f"RunSnapshot.contractDigests.{field} is invalid")

    expected_content_digest = snapshot_digest({key: value[key] for key in value if key != "contentDigest"})
    if value["contentDigest"] != expected_content_digest:
        raise RuntimeContractError("RunSnapshot.contentDigest does not match canonical immutable content")
    _digest(value["contentDigest"], "snapshot", "RunSnapshot.contentDigest")
    return value


def validate_invocation_envelope(envelope: Any) -> dict[str, Any]:
    """Parse an invocation envelope using the accepted L1 field contract."""

    value = _require_keys(
        envelope,
        {
            "protocol",
            "workspaceRef",
            "actorRef",
            "runId",
            "invocationId",
            "runSnapshotDigest",
            "trigger",
            "newContextEventRefs",
            "remainingBudget",
            "lease",
            "cancellationRef",
            "causationRef",
            "correlationId",
            "idempotencyKey",
        },
        {"checkpointRef"},
        path="InvocationEnvelope",
    )
    if value["protocol"] != PROTOCOL:
        raise RuntimeContractError("InvocationEnvelope.protocol is not the accepted Plane runtime protocol")
    for field, namespace in (
        ("workspaceRef", "workspace"),
        ("actorRef", "actor"),
        ("runId", "run"),
        ("invocationId", "invocation"),
        ("cancellationRef", "cancellation"),
        ("causationRef", "causation"),
        ("correlationId", "correlation"),
        ("idempotencyKey", "idempotency"),
    ):
        _ref(value[field], namespace, f"InvocationEnvelope.{field}")
    _digest(value["runSnapshotDigest"], "snapshot", "InvocationEnvelope.runSnapshotDigest", 64)
    if "checkpointRef" in value:
        _ref(value["checkpointRef"], "checkpoint", "InvocationEnvelope.checkpointRef")

    trigger = _require_keys(
        value["trigger"],
        {"kind"},
        {"eventRef", "pendingInputEventRef", "answerFactDigest"},
        path="InvocationEnvelope.trigger",
    )
    kind = trigger["kind"]
    if not isinstance(kind, str):
        raise RuntimeContractError("InvocationEnvelope.trigger.kind is not supported")
    if kind == "initial":
        if set(trigger) != {"kind"}:
            raise RuntimeContractError("Initial invocations cannot cite continuation events")
    elif kind == "human_input":
        if set(trigger) != {"kind", "eventRef", "pendingInputEventRef", "answerFactDigest"}:
            raise RuntimeContractError("Human-input invocations require the complete Plane answer event")
        _ref(trigger["eventRef"], "event", "InvocationEnvelope.trigger.eventRef")
        _ref(trigger["pendingInputEventRef"], "event", "InvocationEnvelope.trigger.pendingInputEventRef")
        _digest(trigger["answerFactDigest"], "content", "InvocationEnvelope.trigger.answerFactDigest")
    elif kind in {"recoverable_restart", "continuation"}:
        if "answerFactDigest" in trigger:
            raise RuntimeContractError("Continuation invocations cannot cite an answer fact digest")
        if set(trigger) not in ({"kind", "eventRef"}, {"kind", "eventRef", "pendingInputEventRef"}):
            raise RuntimeContractError("Continuation invocations require an event reference")
        _ref(trigger["eventRef"], "event", "InvocationEnvelope.trigger.eventRef")
        if "pendingInputEventRef" in trigger:
            _ref(trigger["pendingInputEventRef"], "event", "InvocationEnvelope.trigger.pendingInputEventRef")
    else:
        raise RuntimeContractError("InvocationEnvelope.trigger.kind is not supported")

    context_events = value["newContextEventRefs"]
    if not isinstance(context_events, list) or len(context_events) > MAX_CONTEXT_ITEMS:
        raise RuntimeContractError("InvocationEnvelope.newContextEventRefs has an invalid item count")
    for index, event_ref in enumerate(context_events):
        _ref(event_ref, "event", f"InvocationEnvelope.newContextEventRefs[{index}]")

    budget = _require_keys(
        value["remainingBudget"],
        {"inputTokens", "outputTokens", "durationMs"},
        path="InvocationEnvelope.remainingBudget",
    )
    for field in ("inputTokens", "outputTokens", "durationMs"):
        _bounded_int(budget[field], f"InvocationEnvelope.remainingBudget.{field}")
    lease = _require_keys(
        value["lease"],
        {"leaseId", "expiresAt", "renewAfterMs"},
        path="InvocationEnvelope.lease",
    )
    _ref(lease["leaseId"], "lease", "InvocationEnvelope.lease.leaseId")
    _string(lease["expiresAt"], 64, "InvocationEnvelope.lease.expiresAt")
    _bounded_int(lease["renewAfterMs"], "InvocationEnvelope.lease.renewAfterMs")
    return value

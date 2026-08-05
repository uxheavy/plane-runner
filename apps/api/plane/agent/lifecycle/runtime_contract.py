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
EXPECTED_MANIFEST_SHA256 = "4201921ecedb70c3e8e6b026f7f720e2459b6a128a2e7dc4fa32b296227051d5"
LEGACY_COMMAND_FINGERPRINT_PREFIX = "legacy1:"
PROMOTED_LEGACY_COMMAND_FINGERPRINT_PREFIX = "legacy2:"
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


class RuntimeContractError(ValueError):
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


def promote_legacy_command_fingerprint(fingerprint: str) -> str:
    """Advance a verified legacy binding without changing its digest."""

    if not fingerprint.startswith(LEGACY_COMMAND_FINGERPRINT_PREFIX):
        raise RuntimeContractError("Only legacy command fingerprints can be promoted")
    return f"{PROMOTED_LEGACY_COMMAND_FINGERPRINT_PREFIX}{fingerprint[len(LEGACY_COMMAND_FINGERPRINT_PREFIX) :]}"


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


# Loading the Plane Agent lifecycle boundary is itself a startup/use check for
# the API artifact; there is no valid fallback when these bytes are absent.
contract_manifest()

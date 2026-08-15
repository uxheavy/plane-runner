#!/usr/bin/env python3
"""Parse the owner-supplied, versioned G4 persona scenario descriptor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict


SCENARIO_SCHEMA = "plane.agent-scenario/v1"
ASSIGNED_WORK_ITEM_ALIAS = "fixture:assigned-work-item"
MAX_DESCRIPTOR_BYTES = 128 * 1024
MAX_PROMPT_BYTES = 16 * 1024
MAX_INSTRUCTIONS_BYTES = 8 * 1024
MAX_PROFILE_NAME_BYTES = 96
MAX_OBJECTIVE_BYTES = 2 * 1024
MAX_ACCEPTANCE_ITEMS = 8
MAX_ACCEPTANCE_BYTES = 512
MAX_CONTEXT_REFS = 16
MAX_CONTEXT_REF_BYTES = 256
MAX_EXPECTED_OPERATIONS = 16
MAX_EXPECTED_EVIDENCE = 16
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]{0,255}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_RE = re.compile(
    r"(?i)(?:api[_ -]?key|authorization|bearer|cookie|credential|password|private[_ -]?key|secret|token)"
)
SCENARIO_ROLES: dict[str, Literal["worker", "delegator"]] = {
    "worker": "worker",
    "manager": "delegator",
    "operator": "worker",
}
EXPECTED_OUTCOMES = {"success", "denied", "not_observed"}


class ScenarioError(ValueError):
    """A bounded, safe descriptor failure."""


class ExpectedOperation(TypedDict):
    operationId: str
    outcome: Literal["success", "denied", "not_observed"]


class ExpectedPredicates(TypedDict):
    operationOutcomes: list[ExpectedOperation]
    evidenceKinds: list[str]


@dataclass(frozen=True)
class ModelPolicy:
    provider: Literal["openai-codex"]
    model: Literal["gpt-5.6-luna"]
    reasoning: Literal["xhigh"]
    fallback_allowed: Literal[False]


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    instructions: str
    model_policy: ModelPolicy


@dataclass(frozen=True)
class AssignmentSpec:
    target_ref: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    context_refs: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioDescriptor:
    scenario_id: str
    actor_role: Literal["worker", "delegator"]
    profile: ProfileSpec
    assignment: AssignmentSpec
    prompt: str
    expected: ExpectedPredicates | None
    descriptor_digest: str

    def evidence(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.scenario_id,
            "descriptorDigest": self.descriptor_digest,
            "schemaVersion": SCENARIO_SCHEMA,
            "actorRole": self.actor_role,
            "profileName": self.profile.name,
        }
        if self.expected is not None:
            result["expected"] = self.expected
        return result


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioError("scenario_duplicate_field")
        result[key] = value
    return result


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioError(f"scenario_{name}_must_be_object")
    return value


def _keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ScenarioError(f"scenario_{name}_fields_mismatch")


def _text(value: Any, name: str, maximum: int, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ScenarioError(f"scenario_{name}_must_be_text")
    if len(value.encode("utf-8")) > maximum:
        raise ScenarioError(f"scenario_{name}_too_large")
    if FORBIDDEN_RE.search(value):
        raise ScenarioError(f"scenario_{name}_contains_forbidden_value")
    return value


def _ref(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum or not SAFE_REF_RE.fullmatch(value):
        raise ScenarioError(f"scenario_{name}_invalid_reference")
    return value


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if FORBIDDEN_RE.search(key):
                raise ScenarioError("scenario_forbidden_field")
            _reject_forbidden_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_fields(child)
    elif isinstance(value, str) and FORBIDDEN_RE.search(value):
        raise ScenarioError("scenario_forbidden_value")


def _string_list(value: Any, name: str, maximum_items: int, maximum_bytes: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items or not value:
        raise ScenarioError(f"scenario_{name}_invalid_list")
    return tuple(_text(item, f"{name}_{index}", maximum_bytes) for index, item in enumerate(value))


def _optional_string_list(value: Any, name: str, maximum_items: int, maximum_bytes: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ScenarioError(f"scenario_{name}_invalid_list")
    return tuple(_ref(item, f"{name}_{index}", maximum_bytes) for index, item in enumerate(value))


def _expected(value: Any) -> ExpectedPredicates | None:
    if value is None:
        return None
    expected = _object(value, "expected")
    _keys(expected, {"operationOutcomes", "evidenceKinds"}, "expected")
    operations = expected["operationOutcomes"]
    if not isinstance(operations, list) or len(operations) > MAX_EXPECTED_OPERATIONS:
        raise ScenarioError("scenario_expected_operation_outcomes_invalid")
    parsed_operations: list[ExpectedOperation] = []
    for index, item in enumerate(operations):
        row = _object(item, f"expected_operation_{index}")
        _keys(row, {"operationId", "outcome"}, f"expected_operation_{index}")
        operation_id = _ref(row["operationId"], f"expected_operation_{index}_id", 128)
        outcome = row["outcome"]
        if not isinstance(outcome, str) or outcome not in EXPECTED_OUTCOMES:
            raise ScenarioError(f"scenario_expected_operation_{index}_outcome_invalid")
        parsed_operations.append({"operationId": operation_id, "outcome": outcome})
    evidence = _optional_string_list(expected["evidenceKinds"], "expected_evidence", MAX_EXPECTED_EVIDENCE, 128)
    return {"operationOutcomes": parsed_operations, "evidenceKinds": list(evidence)}


def parse_descriptor_bytes(raw: bytes, expected_digest: str) -> ScenarioDescriptor:
    if len(raw) > MAX_DESCRIPTOR_BYTES:
        raise ScenarioError("scenario_descriptor_too_large")
    if not isinstance(expected_digest, str) or not SHA256_RE.fullmatch(expected_digest):
        raise ScenarioError("scenario_digest_invalid")
    actual_digest = hashlib.sha256(raw).hexdigest()
    if actual_digest != expected_digest:
        raise ScenarioError("scenario_digest_mismatch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ScenarioError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ScenarioError("scenario_malformed_json") from exc
    descriptor = _object(value, "descriptor")
    required_keys = {"schemaVersion", "scenarioId", "actor", "profile", "assignment", "prompt"}
    if set(descriptor) not in (required_keys, required_keys | {"expected"}):
        raise ScenarioError("scenario_descriptor_fields_mismatch")
    if descriptor["schemaVersion"] != SCENARIO_SCHEMA:
        raise ScenarioError("scenario_schema_version_invalid")
    scenario_id = descriptor["scenarioId"]
    if not isinstance(scenario_id, str) or scenario_id not in SCENARIO_ROLES:
        raise ScenarioError("scenario_id_unsupported")
    actor = _object(descriptor["actor"], "actor")
    _keys(actor, {"role"}, "actor")
    actor_role = actor["role"]
    if actor_role != SCENARIO_ROLES[scenario_id]:
        raise ScenarioError("scenario_actor_role_mismatch")

    profile = _object(descriptor["profile"], "profile")
    _keys(profile, {"name", "instructions", "modelPolicy"}, "profile")
    name = profile["name"]
    if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name) or len(name.encode("utf-8")) > MAX_PROFILE_NAME_BYTES:
        raise ScenarioError("scenario_profile_name_invalid")
    instructions = _text(profile["instructions"], "profile_instructions", MAX_INSTRUCTIONS_BYTES)
    model = _object(profile["modelPolicy"], "model_policy")
    _keys(model, {"provider", "model", "reasoning", "fallbackAllowed"}, "model_policy")
    if model != {
        "provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "reasoning": "xhigh",
        "fallbackAllowed": False,
    }:
        raise ScenarioError("scenario_model_policy_invalid")
    model_policy = ModelPolicy("openai-codex", "gpt-5.6-luna", "xhigh", False)

    assignment = _object(descriptor["assignment"], "assignment")
    _keys(assignment, {"targetRef", "objective", "acceptanceCriteria", "contextRefs"}, "assignment")
    assignment_spec = AssignmentSpec(
        target_ref=_ref(assignment["targetRef"], "assignment_target", 255),
        objective=_text(assignment["objective"], "assignment_objective", MAX_OBJECTIVE_BYTES),
        acceptance_criteria=_string_list(
            assignment["acceptanceCriteria"], "assignment_acceptance", MAX_ACCEPTANCE_ITEMS, MAX_ACCEPTANCE_BYTES
        ),
        context_refs=_optional_string_list(
            assignment["contextRefs"], "assignment_context", MAX_CONTEXT_REFS, MAX_CONTEXT_REF_BYTES
        ),
    )
    prompt = _text(descriptor["prompt"], "prompt", MAX_PROMPT_BYTES)
    if prompt != prompt.strip():
        raise ScenarioError("scenario_prompt_outer_whitespace")
    _reject_forbidden_fields(descriptor)
    return ScenarioDescriptor(
        scenario_id=scenario_id,
        actor_role=actor_role,
        profile=ProfileSpec(name, instructions, model_policy),
        assignment=assignment_spec,
        prompt=prompt,
        expected=_expected(descriptor.get("expected")),
        descriptor_digest=actual_digest,
    )


def _read_owner_only(path: Path) -> bytes:
    if not path.is_absolute() or ".." in path.parts:
        raise ScenarioError("scenario_path_invalid")
    try:
        resolved = path.resolve(strict=True)
        metadata = os.stat(path, follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise ScenarioError("scenario_path_unavailable") from exc
    if resolved != path or not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise ScenarioError("scenario_path_not_owner_file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ScenarioError("scenario_path_not_owner_only")
    if metadata.st_size > MAX_DESCRIPTOR_BYTES:
        raise ScenarioError("scenario_descriptor_too_large")
    try:
        with path.open("rb") as handle:
            return handle.read(MAX_DESCRIPTOR_BYTES + 1)
    except OSError as exc:
        raise ScenarioError("scenario_path_read_failed") from exc


def load_descriptor(path: str | Path, expected_digest: str) -> ScenarioDescriptor:
    return parse_descriptor_bytes(_read_owner_only(Path(path)), expected_digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        descriptor = load_descriptor(args.descriptor, args.sha256)
    except ScenarioError as exc:
        print(f"event=agent.g4.scenario status=failed reason={exc}")
        return 1
    print(json.dumps(descriptor.evidence(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

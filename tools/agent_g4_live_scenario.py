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
MAX_EXPECTED_RECORDS = 8
MAX_ROUTE_CHECKS = 8
MAX_SETUP_ACTORS = 4
MAX_SETUP_REFS = 8
MAX_CONTROL_INPUT_BYTES = 8 * 1024
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


class ExpectedOperation(TypedDict, total=False):
    operationId: str
    outcome: Literal["success", "denied", "not_observed"]
    count: int


class ExpectedPredicates(TypedDict, total=False):
    operationOutcomes: list[ExpectedOperation]
    evidenceKinds: list[str]
    durableRecords: list[dict[str, Any]]
    productEvents: list[dict[str, Any]]
    routeChecks: list[str]


@dataclass(frozen=True)
class SetupActor:
    ref: str
    role: str
    display_name: str


@dataclass(frozen=True)
class LineageSpec:
    parent_ref: str
    child_ref: str
    scope_refs: tuple[str, ...]
    budget: int


@dataclass(frozen=True)
class ScheduleSpec:
    actor_ref: str
    cron: str
    timezone: str
    starts_at: str
    fire_at: str | None


@dataclass(frozen=True)
class SetupSpec:
    preconditions: tuple[str, ...]
    actors: tuple[SetupActor, ...]
    lineage: LineageSpec | None
    schedule: ScheduleSpec | None

    def evidence(self) -> dict[str, Any]:
        result = {
            "preconditions": list(self.preconditions),
            "actors": [{"ref": a.ref, "role": a.role, "displayName": a.display_name} for a in self.actors],
        }
        if self.lineage:
            result["lineage"] = {
                "parentActorRef": self.lineage.parent_ref,
                "childActorRef": self.lineage.child_ref,
                "scopeRefs": list(self.lineage.scope_refs),
                "budget": self.lineage.budget,
            }
        if self.schedule:
            result["schedule"] = {
                "actorRef": self.schedule.actor_ref,
                "cron": self.schedule.cron,
                "timezone": self.schedule.timezone,
                "startsAt": self.schedule.starts_at,
                "fireAt": self.schedule.fire_at,
            }
        return result


@dataclass(frozen=True)
class ControlsSpec:
    continuation: dict[str, str] | None
    revision: dict[str, str] | None
    cancellation: dict[str, str] | None
    fault: str

    def evidence(self) -> dict[str, Any]:
        result = {"fault": {"selection": self.fault}}
        for name, value in (("continuation", self.continuation), ("revision", self.revision), ("cancellation", self.cancellation)):
            if value is None:
                continue
            result[name] = dict(value)
            if "input" in result[name]:
                raw = result[name].pop("input")
                result[name]["inputBytes"] = len(raw.encode("utf-8"))
                result[name]["inputDigest"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return result


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
    setup: SetupSpec
    controls: ControlsSpec
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
        result["setup"] = self.setup.evidence()
        result["controls"] = self.controls.evidence()
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
    elif isinstance(value, str) and FORBIDDEN_RE.search(value) and value not in _PRECONDITIONS:
        raise ScenarioError("scenario_forbidden_value")


def _string_list(value: Any, name: str, maximum_items: int, maximum_bytes: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items or not value:
        raise ScenarioError(f"scenario_{name}_invalid_list")
    return tuple(_text(item, f"{name}_{index}", maximum_bytes) for index, item in enumerate(value))


def _optional_string_list(value: Any, name: str, maximum_items: int, maximum_bytes: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ScenarioError(f"scenario_{name}_invalid_list")
    return tuple(_ref(item, f"{name}_{index}", maximum_bytes) for index, item in enumerate(value))


_PRECONDITIONS = {"isolated_workspace", "assigned_work_item", "fresh_assignment", "live_authorization", "separate_runtime_service"}
_RELATED_ROLES = {"worker", "delegator", "gardener", "chief_of_staff", "hr", "evaluator", "custom"}
_FAULTS = {"none", "budget_exhausted", "runtime_unavailable"}
_TRIGGERS = {"human_input", "recoverable_restart", "continuation"}
_CANCELLATION_TIMINGS = {"before_dispatch", "after_provider_request", "after_publication"}
_RECORD_KINDS = {"assignment", "run", "invocation", "input_event", "audit", "publication", "terminal_event", "schedule", "schedule_fire", "lineage_assignment"}
_PRODUCT_KINDS = {"publication", "outcome_submission", "run_failure", "run_blocker", "run_cancellation", "input_event"}
_EVIDENCE_KINDS = _RECORD_KINDS


def _setup(value: Any) -> SetupSpec:
    if value is None:
        return SetupSpec((), (), None, None)
    setup = _object(value, "setup")
    if set(setup).difference({"preconditions", "actors", "lineage", "schedule"}):
        raise ScenarioError("scenario_setup_fields_mismatch")
    preconditions = _optional_string_list(setup.get("preconditions", []), "setup_preconditions", 8, 64)
    if any(item not in _PRECONDITIONS for item in preconditions):
        raise ScenarioError("scenario_setup_precondition_unsupported")
    actors = []
    refs = set()
    raw_actors = setup.get("actors", [])
    if not isinstance(raw_actors, list) or len(raw_actors) > MAX_SETUP_ACTORS:
        raise ScenarioError("scenario_setup_actors_invalid_list")
    for index, item in enumerate(raw_actors):
        row = _object(item, f"setup_actor_{index}")
        _keys(row, {"ref", "role", "displayName"}, f"setup_actor_{index}")
        ref = _ref(row["ref"], f"setup_actor_{index}_ref", 128)
        if not ref.startswith("actor:") or ref == "actor:primary" or ref in refs:
            raise ScenarioError("scenario_setup_actor_ref_invalid")
        role = row["role"]
        if role not in _RELATED_ROLES:
            raise ScenarioError("scenario_setup_actor_role_invalid")
        display_name = row["displayName"]
        if not isinstance(display_name, str) or not SAFE_NAME_RE.fullmatch(display_name):
            raise ScenarioError("scenario_setup_actor_display_name_invalid")
        refs.add(ref)
        actors.append(SetupActor(ref, role, display_name))
    lineage = None
    if setup.get("lineage") is not None:
        row = _object(setup["lineage"], "setup_lineage")
        _keys(row, {"parentActorRef", "childActorRef", "scopeRefs", "budget"}, "setup_lineage")
        parent = _ref(row["parentActorRef"], "setup_lineage_parent", 128)
        child = _ref(row["childActorRef"], "setup_lineage_child", 128)
        if parent == child or parent not in refs | {"actor:primary"} or child not in refs | {"actor:primary"}:
            raise ScenarioError("scenario_setup_lineage_actor_ref_invalid")
        scope_refs = _optional_string_list(row["scopeRefs"], "setup_lineage_scope", MAX_SETUP_REFS, 128)
        budget = row["budget"]
        if isinstance(budget, bool) or not isinstance(budget, int) or not 0 <= budget <= 256:
            raise ScenarioError("scenario_setup_lineage_budget_invalid")
        lineage = LineageSpec(parent, child, scope_refs, budget)
    schedule = None
    if setup.get("schedule") is not None:
        row = _object(setup["schedule"], "setup_schedule")
        _keys(row, {"actorRef", "cron", "timezone", "startsAt", "fireAt"}, "setup_schedule")
        actor_ref = _ref(row["actorRef"], "setup_schedule_actor", 128)
        if actor_ref not in refs | {"actor:primary"} or not isinstance(row["cron"], str) or len(row["cron"].split()) != 5:
            raise ScenarioError("scenario_setup_schedule_invalid")
        if any(not re.fullmatch(r"[0-9*/,?-]+", part) for part in row["cron"].split()):
            raise ScenarioError("scenario_setup_schedule_invalid")
        timezone = _ref(row["timezone"], "setup_schedule_timezone", 64)
        starts_at = _text(row["startsAt"], "setup_schedule_starts_at", 64)
        fire_at = row["fireAt"]
        if fire_at is not None:
            fire_at = _text(fire_at, "setup_schedule_fire_at", 64)
        schedule = ScheduleSpec(actor_ref, row["cron"], timezone, starts_at, fire_at)
    return SetupSpec(preconditions, tuple(actors), lineage, schedule)


def _controls(value: Any) -> ControlsSpec:
    if value is None:
        return ControlsSpec(None, None, None, "none")
    controls = _object(value, "controls")
    if set(controls).difference({"continuation", "revision", "cancellation", "fault"}):
        raise ScenarioError("scenario_controls_fields_mismatch")
    continuation = revision = cancellation = None
    if controls.get("continuation") is not None:
        row = _object(controls["continuation"], "controls_continuation")
        if set(row).difference({"trigger", "input", "checkpointRef"}) or not {"trigger", "input"}.issubset(row) or row["trigger"] not in _TRIGGERS:
            raise ScenarioError("scenario_controls_continuation_invalid")
        continuation = {"trigger": row["trigger"], "input": _text(row["input"], "controls_continuation_input", MAX_CONTROL_INPUT_BYTES)}
        if row.get("checkpointRef") is not None:
            continuation["checkpointRef"] = _ref(row["checkpointRef"], "controls_checkpoint", 128)
    if controls.get("revision") is not None:
        row = _object(controls["revision"], "controls_revision")
        if set(row).difference({"input", "decisionNote"}) or "input" not in row:
            raise ScenarioError("scenario_controls_revision_invalid")
        revision = {"input": _text(row["input"], "controls_revision_input", MAX_CONTROL_INPUT_BYTES), "decisionNote": _text(row.get("decisionNote", ""), "controls_revision_note", MAX_OBJECTIVE_BYTES, nonempty=False)}
    if continuation is not None and revision is not None:
        raise ScenarioError("scenario_controls_continuation_revision_conflict")
    if controls.get("cancellation") is not None:
        row = _object(controls["cancellation"], "controls_cancellation")
        _keys(row, {"timing", "reason"}, "controls_cancellation")
        if row["timing"] not in _CANCELLATION_TIMINGS:
            raise ScenarioError("scenario_controls_cancellation_invalid")
        cancellation = {"timing": row["timing"], "reason": _text(row["reason"], "controls_cancellation_reason", MAX_OBJECTIVE_BYTES)}
    fault = _object(controls.get("fault", {"selection": "none"}), "controls_fault")
    _keys(fault, {"selection"}, "controls_fault")
    if fault["selection"] not in _FAULTS:
        raise ScenarioError("scenario_controls_fault_invalid")
    return ControlsSpec(continuation, revision, cancellation, fault["selection"])


def _expected(value: Any) -> ExpectedPredicates | None:
    if value is None:
        return None
    expected = _object(value, "expected")
    if set(expected).difference({"operationOutcomes", "evidenceKinds", "durableRecords", "productEvents", "routeChecks"}) or not {"operationOutcomes", "evidenceKinds"}.issubset(expected):
        raise ScenarioError("scenario_expected_fields_mismatch")
    operations = expected["operationOutcomes"]
    if not isinstance(operations, list) or len(operations) > MAX_EXPECTED_OPERATIONS:
        raise ScenarioError("scenario_expected_operation_outcomes_invalid")
    parsed_operations: list[ExpectedOperation] = []
    for index, item in enumerate(operations):
        row = _object(item, f"expected_operation_{index}")
        if set(row).difference({"operationId", "outcome", "count"}) or not {"operationId", "outcome"}.issubset(row):
            raise ScenarioError(f"scenario_expected_operation_{index}_fields_invalid")
        operation_id = _ref(row["operationId"], f"expected_operation_{index}_id", 128)
        outcome = row["outcome"]
        if not isinstance(outcome, str) or outcome not in EXPECTED_OUTCOMES:
            raise ScenarioError(f"scenario_expected_operation_{index}_outcome_invalid")
        parsed = {"operationId": operation_id, "outcome": outcome}
        if "count" in row and (isinstance(row["count"], bool) or not isinstance(row["count"], int) or not 0 <= row["count"] <= 256):
            raise ScenarioError(f"scenario_expected_operation_{index}_count_invalid")
        if "count" in row:
            parsed["count"] = row["count"]
        parsed_operations.append(parsed)
    evidence = _optional_string_list(expected["evidenceKinds"], "expected_evidence", MAX_EXPECTED_EVIDENCE, 128)
    if any(kind not in _EVIDENCE_KINDS for kind in evidence):
        raise ScenarioError("scenario_expected_evidence_unsupported")
    result: ExpectedPredicates = {"operationOutcomes": parsed_operations, "evidenceKinds": list(evidence)}
    if "routeChecks" in expected:
        route_checks = _optional_string_list(expected["routeChecks"], "expected_route_checks", MAX_ROUTE_CHECKS, 8)
        if any(check not in {f"W{index:02d}" for index in range(1, 9)} for check in route_checks):
            raise ScenarioError("scenario_expected_route_check_unsupported")
        result["routeChecks"] = list(route_checks)
    for field, kinds in (("durableRecords", _RECORD_KINDS), ("productEvents", _PRODUCT_KINDS)):
        if field not in expected:
            continue
        rows = expected[field]
        if not isinstance(rows, list) or len(rows) > MAX_EXPECTED_RECORDS:
            raise ScenarioError(f"scenario_{field}_invalid_list")
        parsed_rows = []
        for index, row in enumerate(rows):
            row = _object(row, f"{field}_{index}")
            if set(row).difference({"kind", "count"}) or "kind" not in row or row["kind"] not in kinds:
                raise ScenarioError(f"scenario_{field}_{index}_invalid")
            count = row.get("count", 1)
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 256:
                raise ScenarioError(f"scenario_{field}_{index}_count_invalid")
            parsed_rows.append({"kind": row["kind"], "count": count})
        result[field] = parsed_rows
    return result


def evaluate_expectations(expected: ExpectedPredicates | None, *, operations: list[dict[str, Any]], records: list[dict[str, Any]], product_events: list[dict[str, Any]], evidence_kinds: list[str]) -> dict[str, Any]:
    if expected is None:
        return {"passed": True, "failures": [], "operations": [], "durableRecords": [], "productEvents": [], "evidenceKinds": []}
    failures = []
    actual_ops = {row.get("operationId"): row for row in operations}
    operation_results = []
    for row in expected["operationOutcomes"]:
        actual = actual_ops.get(row["operationId"], {})
        actual_outcome = actual.get("outcome", "not_observed")
        actual_count = actual.get("count", 0)
        wanted_count = row.get("count", 0 if row["outcome"] == "not_observed" else 1)
        passed = actual_outcome == row["outcome"] and actual_count == wanted_count
        operation_results.append({"operationId": row["operationId"], "expected": row["outcome"], "actual": actual_outcome, "expectedCount": wanted_count, "actualCount": actual_count, "passed": passed})
        if not passed:
            failures.append(f"operation:{row['operationId']}")
    def compare(field: str, actual_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actual_map = {row.get("kind"): row.get("count", 0) for row in actual_rows}
        result = []
        for row in expected.get(field, []):
            passed = actual_map.get(row["kind"], 0) == row["count"]
            result.append({"kind": row["kind"], "expectedCount": row["count"], "actualCount": actual_map.get(row["kind"], 0), "passed": passed})
            if not passed:
                failures.append(f"{field}:{row['kind']}")
        return result
    evidence_results = [{"kind": kind, "passed": kind in evidence_kinds} for kind in expected["evidenceKinds"]]
    failures.extend(f"evidence:{row['kind']}" for row in evidence_results if not row["passed"])
    durable_results = compare("durableRecords", records)
    product_results = compare("productEvents", product_events)
    return {"passed": not failures, "failures": failures[:32], "operations": operation_results, "durableRecords": durable_results, "productEvents": product_results, "evidenceKinds": evidence_results}


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
    if set(descriptor).difference(required_keys | {"expected", "setup", "controls"}) or not required_keys.issubset(descriptor):
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
    setup = _setup(descriptor.get("setup"))
    if setup.lineage is not None and setup.lineage.parent_ref == "actor:primary" and actor_role != "delegator":
        raise ScenarioError("scenario_setup_lineage_parent_role_invalid")
    if setup.lineage is not None and setup.lineage.parent_ref != "actor:primary":
        roles = {actor.ref: actor.role for actor in setup.actors}
        if roles.get(setup.lineage.parent_ref) != "delegator":
            raise ScenarioError("scenario_setup_lineage_parent_role_invalid")
    return ScenarioDescriptor(
        scenario_id=scenario_id,
        actor_role=actor_role,
        profile=ProfileSpec(name, instructions, model_policy),
        assignment=assignment_spec,
        prompt=prompt,
        expected=_expected(descriptor.get("expected")),
        setup=setup,
        controls=_controls(descriptor.get("controls")),
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

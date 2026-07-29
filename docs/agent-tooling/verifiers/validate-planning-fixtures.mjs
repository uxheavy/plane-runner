#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import Ajv2020 from "ajv/dist/2020.js";

const verifierPath = fileURLToPath(import.meta.url);
const contractRoot = resolve(dirname(verifierPath), "..");
const fixturePath = resolve(contractRoot, "fixtures/planning-v1.json");
const fixtureSchemaPath = resolve(contractRoot, "fixtures/planning-v1.schema.json");
const predicatePath = resolve(contractRoot, "fixtures/planning-v1.predicates.json");
const predicateSchemaPath = resolve(contractRoot, "fixtures/planning-v1.predicates.schema.json");
const promptPath = resolve(contractRoot, "prompts/release-planning-v1.md");
const contractPath = resolve(contractRoot, "EVALUATION-FIXTURE-CONTRACT.md");

const fixtureBytes = readFileSync(fixturePath);
const fixtureSchemaBytes = readFileSync(fixtureSchemaPath);
const predicateBytes = readFileSync(predicatePath);
const predicateSchemaBytes = readFileSync(predicateSchemaPath);
const promptBytes = readFileSync(promptPath);
const verifierBytes = readFileSync(verifierPath);
const fixtureSet = JSON.parse(fixtureBytes);
const predicateSet = JSON.parse(predicateBytes);
const prompt = promptBytes.toString("utf8");
const contract = readFileSync(contractPath, "utf8");
const failures = [];

const frozenArtifactDigests = {
  fixture: "88b38a00f06d65418e01f3019a0914cfef7ddacf6dbb9f4b078374623040a6c7",
  fixtureSchema: "f24542f534bf3eb22bc5a15a32ca5c2ae9208ddb21f5e8e59c9e3859b0640b89",
  predicates: "a808b01da9a07f3cfdd69143a32b2843bcaf571fbcc0e076010abd9cb89e2f2c",
  predicateSchema: "189bda3b24ee601339f9a13ca0af53c60b31cc2ca70da3281652a7454e4f3226",
  prompt: "f222d7be60baff3969e3fd4c40b100fa533c1649173cead1394e5ad6f526ec31",
};

const frozenScoring = {
  eligible_state_groups: ["backlog", "unstarted", "started"],
  generated_artifacts_are_ineligible: true,
  generated_artifact_name_pattern: "^\\[run:[A-Za-z0-9][A-Za-z0-9._-]{0,63}\\] ",
  priority_points: { urgent: 40, high: 30, medium: 20, low: 10, none: 0 },
  direct_dependent_points_each: 15,
  direct_dependent_cap: 2,
  unassigned_points: 10,
  started_points: 5,
  target_overdue_points: 20,
  target_within_three_days_points: 10,
  ineligible_state_score: -100,
  tie_break: "canonical Plane work-item key ascending (project identifier, then numeric sequence)",
  selection: "top three eligible source work items unless the fixture declares an expected pre-write error",
};

const expectedPredicateLayout = {
  common: [
    ["PLAN-COMMON-001", "resolved_provider_model_equals"],
    ["PLAN-COMMON-002", "fresh_process_and_seed"],
    ["PLAN-COMMON-003", "source_snapshot_unchanged"],
    ["PLAN-COMMON-004", "control_project_unchanged_and_absent"],
    ["PLAN-COMMON-005", "audit_correlation_complete"],
    ["PLAN-COMMON-006", "security_violation_counts_equal"],
    ["PLAN-COMMON-007", "required_tool_surface_observed"],
    ["PLAN-COMMON-008", "generated_typescript_captured_and_digest_bound"],
    ["PLAN-COMMON-009", "callback_trace_complete"],
    ["PLAN-COMMON-010", "ui_readback_matches_authoritative_state"],
    ["PLAN-COMMON-011", "cleanup_verified_absent"],
    ["PLAN-COMMON-012", "control_project_probe_denied"],
    ["PLAN-COMMON-013", "independent_read_overlap_observed"],
    ["PLAN-COMMON-014", "typescript_credential_probe_denied_with_liveness"],
    ["PLAN-COMMON-015", "typescript_direct_plane_network_probe_denied_with_liveness"],
    ["PLAN-COMMON-016", "run_budgets_within_frozen_limits"],
    ["PLAN-COMMON-017", "attempt_ledger_complete_no_hidden_retries_or_fallbacks"],
    ["PLAN-COMMON-018", "frozen_prompt_exact_and_no_human_steering"],
    ["PLAN-COMMON-019", "separate_verifier_principal_used"],
    ["PLAN-COMMON-020", "pending_human_confirmation_states_equal"],
    ["PLAN-COMMON-021", "extended_isolate_probe_matrix_denied_with_liveness"],
    ["PLAN-COMMON-022", "credential_lifecycle_old_credential_denied"],
    ["PLAN-COMMON-023", "audit_outcome_matrix_complete"],
  ],
  plan_created: [
    ["PLAN-CREATED-001", "created_artifact_counts_equal"],
    ["PLAN-CREATED-002", "created_hierarchy_equals"],
    ["PLAN-CREATED-003", "created_names_and_comment_contain_run_tag"],
    ["PLAN-CREATED-004", "comment_source_link_equals"],
    ["PLAN-CREATED-005", "selected_sources_equal_impact_top_three"],
    ["PLAN-CREATED-006", "created_assignees_within_exact_eligible_set"],
    ["PLAN-CREATED-007", "returned_link_set_equals"],
    ["PLAN-CREATED-008", "created_project_cycle_and_child_source_name_mapping_equals"],
    ["PLAN-CREATED-009", "current_invocation_replay_matches"],
    ["PLAN-CREATED-010", "no_extra_target_project_effects"],
    ["PLAN-CREATED-011", "final_readiness_summary_references_selected_sources"],
    ["PLAN-CREATED-012", "agent_release_plan_call_count_equals"],
  ],
  scenario_overrides: {
    "EV-001": [],
    "EV-002": [["PLAN-EV002-001", "forbidden_inventions_absent"]],
    "EV-003": [
      ["PLAN-EV003-001", "structured_error_equals"],
      ["PLAN-EV003-002", "created_artifact_counts_equal"],
      ["PLAN-EV003-003", "prewrite_error_response_and_call_count_equal"],
    ],
    "EV-004": [
      ["PLAN-EV004-001", "structured_error_and_authorized_candidates_equal"],
      ["PLAN-EV004-002", "created_artifact_counts_equal"],
      ["PLAN-EV004-003", "prewrite_error_response_and_call_count_equal"],
    ],
    "EV-005": [["PLAN-EV005-001", "dependency_order_equals"]],
    "EV-006": [
      ["PLAN-EV006-001", "relation_sccs_equal"],
      ["PLAN-EV006-002", "forbidden_dependency_orders_absent"],
      ["PLAN-EV006-003", "unrelated_relations_not_used_as_causality"],
    ],
    "EV-007": [
      ["PLAN-EV007-001", "overloaded_members_equal"],
      ["PLAN-EV007-002", "forbidden_assignees_absent"],
      ["PLAN-EV007-003", "eligible_assignee_choices_equal"],
    ],
    "EV-008": [["PLAN-EV008-001", "ineligible_sources_absent"]],
    "EV-009": [
      ["PLAN-EV009-001", "prior_artifact_counts_and_digests_unchanged"],
      ["PLAN-EV009-002", "prior_invocation_replay_created_count_equals"],
    ],
    "EV-010": [
      ["PLAN-EV010-001", "cursor_chain_complete"],
      ["PLAN-EV010-002", "required_sources_observed"],
    ],
  },
};

function check(condition, message) {
  if (!condition) failures.push(message);
}

function unique(values, label) {
  check(new Set(values).size === values.length, `${label} must be unique`);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

for (const [name, bytes, expected] of [
  ["fixture", fixtureBytes, frozenArtifactDigests.fixture],
  ["fixture schema", fixtureSchemaBytes, frozenArtifactDigests.fixtureSchema],
  ["predicate set", predicateBytes, frozenArtifactDigests.predicates],
  ["predicate schema", predicateSchemaBytes, frozenArtifactDigests.predicateSchema],
  ["prompt", promptBytes, frozenArtifactDigests.prompt],
]) {
  check(sha256(bytes) === expected, `${name} digest differs from the verifier-owned frozen digest`);
}

for (const [relativePath, bytes] of [
  ["fixtures/planning-v1.json", fixtureBytes],
  ["fixtures/planning-v1.schema.json", fixtureSchemaBytes],
  ["fixtures/planning-v1.predicates.json", predicateBytes],
  ["fixtures/planning-v1.predicates.schema.json", predicateSchemaBytes],
  ["prompts/release-planning-v1.md", promptBytes],
  ["verifiers/validate-planning-fixtures.mjs", verifierBytes],
]) {
  const quote = "`";
  const matchingRow = contract
    .split("\n")
    .some((line) => line.includes(quote + relativePath + quote) && line.includes(quote + sha256(bytes) + quote));
  check(matchingRow, `fixture contract has a missing, stale, or mis-keyed row for ${relativePath}`);
}

for (const [schemaBytes, data, label] of [
  [fixtureSchemaBytes, fixtureSet, "fixture set"],
  [predicateSchemaBytes, predicateSet, "predicate set"],
]) {
  const ajv = new Ajv2020({ allErrors: true, strict: true, validateFormats: false });
  const validate = ajv.compile(JSON.parse(schemaBytes));
  check(validate(data), `${label} fails strict Draft 2020-12 validation: ${JSON.stringify(validate.errors)}`);
}

function jsonPointer(root, pointer, fixtureIndex) {
  const segments = pointer
    .slice(1)
    .split("/")
    .map((segment) => segment.replaceAll("~1", "/").replaceAll("~0", "~"))
    .map((segment) => (segment === "*" ? String(fixtureIndex) : segment));
  let value = root;
  for (const segment of segments) {
    if (value === null || typeof value !== "object" || !(segment in value)) {
      throw new Error(`unresolved pointer ${pointer} at ${segment}`);
    }
    value = value[segment];
  }
  return value;
}

function formatIndexed(template, index) {
  return template.replace("%03d", String(index).padStart(3, "0"));
}

function expandWorkItems(fixture) {
  if (fixture.work_items) return fixture.work_items.map((item) => ({ generated_artifact: false, ...item }));

  const generator = fixture.work_item_generator;
  const overrides = new Map(fixture.overrides.map((override) => [override.key, override]));
  const items = [];
  for (let index = generator.index_start; index < generator.index_start + generator.count; index += 1) {
    const key = formatIndexed(generator.key_template, index);
    const item = {
      key,
      name: formatIndexed(generator.name_template, index),
      priority: generator.priority_by_modulo.values[index % generator.priority_by_modulo.modulus],
      state: generator.state_by_modulo.values[index % generator.state_by_modulo.modulus],
      assignees: generator.assignee_by_modulo.values[index % generator.assignee_by_modulo.modulus],
      cycle: generator.cycle,
      target_offset_days: (index % generator.target_offset.modulus) + generator.target_offset.add,
      generated_artifact: false,
    };
    items.push({ ...item, ...overrides.get(key) });
  }
  return items;
}

function impactOrder(fixture, workItems) {
  const stateGroups = new Map(fixtureSet.shared.states.map((state) => [state.key, state.group]));
  const byKey = new Map(workItems.map((item) => [item.key, item]));
  const generatedArtifactNamePattern = new RegExp(frozenScoring.generated_artifact_name_pattern);
  const eligible = (item) =>
    !generatedArtifactNamePattern.test(item.name) &&
    frozenScoring.eligible_state_groups.includes(stateGroups.get(item.state));
  const dependentCounts = new Map();

  for (const relation of fixture.relations) {
    let blockerKey;
    let dependentKey;
    if (relation.type === "blocked_by") {
      blockerKey = relation.to;
      dependentKey = relation.from;
    } else if (relation.type === "blocking") {
      blockerKey = relation.from;
      dependentKey = relation.to;
    } else {
      continue;
    }
    if (eligible(byKey.get(blockerKey)) && eligible(byKey.get(dependentKey))) {
      dependentCounts.set(blockerKey, (dependentCounts.get(blockerKey) ?? 0) + 1);
    }
  }

  return workItems
    .filter(eligible)
    .map((item) => {
      let score = frozenScoring.priority_points[item.priority];
      score +=
        Math.min(dependentCounts.get(item.key) ?? 0, frozenScoring.direct_dependent_cap) *
        frozenScoring.direct_dependent_points_each;
      if (item.assignees.length === 0) score += frozenScoring.unassigned_points;
      if (stateGroups.get(item.state) === "started") score += frozenScoring.started_points;
      if (item.target_offset_days < 0) score += frozenScoring.target_overdue_points;
      else if (item.target_offset_days <= 3) score += frozenScoring.target_within_three_days_points;
      return { key: item.key, score, sequence: workItems.indexOf(item) + 1 };
    })
    .toSorted((left, right) => right.score - left.score || left.sequence - right.sequence);
}

function blockerEdges(fixture) {
  return fixture.relations.flatMap((relation) => {
    if (relation.type === "blocked_by") return [[relation.to, relation.from]];
    if (relation.type === "blocking") return [[relation.from, relation.to]];
    return [];
  });
}

function stronglyConnectedComponents(nodes, edges) {
  const adjacency = new Map(nodes.map((node) => [node, []]));
  for (const [from, to] of edges) adjacency.get(from)?.push(to);
  let nextIndex = 0;
  const indices = new Map();
  const lowLinks = new Map();
  const stack = [];
  const onStack = new Set();
  const components = [];

  function visit(node) {
    indices.set(node, nextIndex);
    lowLinks.set(node, nextIndex);
    nextIndex += 1;
    stack.push(node);
    onStack.add(node);
    for (const target of adjacency.get(node) ?? []) {
      if (!indices.has(target)) {
        visit(target);
        lowLinks.set(node, Math.min(lowLinks.get(node), lowLinks.get(target)));
      } else if (onStack.has(target)) {
        lowLinks.set(node, Math.min(lowLinks.get(node), indices.get(target)));
      }
    }
    if (lowLinks.get(node) === indices.get(node)) {
      const component = [];
      let member;
      do {
        member = stack.pop();
        onStack.delete(member);
        component.push(member);
      } while (member !== node);
      if (component.length > 1) components.push(component.toSorted());
    }
  }

  for (const node of nodes) if (!indices.has(node)) visit(node);
  return components.toSorted((left, right) => left.join("\0").localeCompare(right.join("\0")));
}

function normalizedPairs(pairs) {
  return pairs
    .map((pair) => pair.toSorted())
    .toSorted((left, right) => left.join("\0").localeCompare(right.join("\0")));
}

const generatedArtifactNamePattern = new RegExp(frozenScoring.generated_artifact_name_pattern);

function isGeneratedPlanItem(item) {
  return generatedArtifactNamePattern.test(item.name);
}

const fixtures = fixtureSet.fixtures;
const expectedFixtureIds = Array.from({ length: 10 }, (_, index) => `FX-PLAN-${String(index + 1).padStart(3, "0")}`);
const expectedScenarioIds = Array.from({ length: 10 }, (_, index) => `EV-${String(index + 1).padStart(3, "0")}`);
check(fixtures.length === 10, "fixture set must contain exactly ten fixtures");
check(
  JSON.stringify(fixtures.map((fixture) => fixture.id)) === JSON.stringify(expectedFixtureIds),
  "fixture IDs must be ordered FX-PLAN-001 through FX-PLAN-010"
);
check(
  JSON.stringify(fixtures.map((fixture) => fixture.scenario_id)) === JSON.stringify(expectedScenarioIds),
  "scenario IDs must be ordered EV-001 through EV-010"
);
unique(
  fixtures.map((fixture) => fixture.project.identifier),
  "project identifiers"
);

const sharedStateKeys = new Set(fixtureSet.shared.states.map((state) => state.key));
const sharedLabelKeys = new Set(fixtureSet.shared.labels.map((label) => label.key));
const sharedMemberKeys = new Set(fixtureSet.shared.members.map((member) => member.key));
unique(
  fixtureSet.shared.states.map((state) => state.key),
  "shared state keys"
);
unique(
  fixtureSet.shared.labels.map((label) => label.key),
  "shared label keys"
);
unique(
  fixtureSet.shared.members.map((member) => member.key),
  "shared member keys"
);
check(
  JSON.stringify(fixtureSet.impact_scoring) === JSON.stringify(frozenScoring),
  "fixture scoring contract must equal the verifier-owned frozen scoring constants"
);

for (const [fixtureIndex, fixture] of fixtures.entries()) {
  const prefix = fixture.id;
  const rawCycleKeys = fixture.cycles.map((cycle) => cycle.key);
  const cycleKeys = new Set(rawCycleKeys);
  const workItems = expandWorkItems(fixture);
  const rawWorkItemKeys = workItems.map((item) => item.key);
  const workItemKeys = new Set(rawWorkItemKeys);
  unique(rawCycleKeys, `${prefix} cycle keys`);
  unique(rawWorkItemKeys, `${prefix} work-item keys`);
  unique(fixture.members, `${prefix} project member keys`);
  unique(
    fixture.relations.map((relation) => relation.key),
    `${prefix} relation keys`
  );
  unique(
    (fixture.comments ?? []).map((comment) => comment.key),
    `${prefix} comment keys`
  );

  check(fixture.members.includes("agent"), `${prefix} must include the agent member`);
  for (const member of fixture.members)
    check(sharedMemberKeys.has(member), `${prefix} references unknown member ${member}`);
  for (const cycle of fixture.cycles)
    check(cycle.start_offset_days < cycle.end_offset_days, `${prefix} cycle ${cycle.key} must start before it ends`);

  for (const item of workItems) {
    check(sharedStateKeys.has(item.state), `${prefix} ${item.key} references unknown state ${item.state}`);
    for (const member of item.assignees)
      check(sharedMemberKeys.has(member), `${prefix} ${item.key} references unknown assignee ${member}`);
    for (const label of item.labels ?? [])
      check(sharedLabelKeys.has(label), `${prefix} ${item.key} references unknown label ${label}`);
    if (item.cycle) check(cycleKeys.has(item.cycle), `${prefix} ${item.key} references unknown cycle ${item.cycle}`);
    if (item.parent)
      check(workItemKeys.has(item.parent), `${prefix} ${item.key} references unknown parent ${item.parent}`);
    check(
      Boolean(item.generated_artifact) === isGeneratedPlanItem(item),
      `${prefix} ${item.key} generated-artifact seed role must equal its agent-visible name marker`
    );
    if (item.source_work_item) {
      const sourceIndex = workItems.findIndex((candidate) => candidate.key === item.source_work_item);
      const canonicalSourceKey = `${fixture.project.identifier}-${sourceIndex + 1}`;
      check(sourceIndex >= 0, `${prefix} ${item.key} references unknown source work item ${item.source_work_item}`);
      check(item.parent && item.generated_artifact, `${prefix} ${item.key} source mapping requires a generated child`);
      check(
        item.name.startsWith(`[run:${fixture.prior_invocation?.run_tag}] [source:${canonicalSourceKey}] `),
        `${prefix} ${item.key} source mapping is not encoded in its agent-visible name`
      );
    }
  }

  for (const relation of fixture.relations) {
    check(workItemKeys.has(relation.from), `${prefix} relation references unknown source ${relation.from}`);
    check(workItemKeys.has(relation.to), `${prefix} relation references unknown target ${relation.to}`);
    check(relation.from !== relation.to, `${prefix} relation cannot be self-referential`);
  }
  for (const comment of fixture.comments ?? []) {
    check(workItemKeys.has(comment.work_item), `${prefix} comment references unknown work item ${comment.work_item}`);
  }

  const currentCycles = fixture.cycles.filter((cycle) => cycle.start_offset_days <= 0 && cycle.end_offset_days >= 0);
  if (fixture.expected.outcome === "plan_created") {
    check(currentCycles.length === 1, `${prefix} plan-created fixture must have exactly one current cycle`);
    check(fixture.expected.selected_source_keys.length === 3, `${prefix} must select exactly three sources`);
    const observed = impactOrder(fixture, workItems)
      .slice(0, 3)
      .map(({ key }) => key);
    check(
      JSON.stringify(observed) === JSON.stringify(fixture.expected.selected_source_keys),
      `${prefix} expected top three ${JSON.stringify(fixture.expected.selected_source_keys)} but oracle produced ${JSON.stringify(observed)}`
    );
  } else if (fixture.expected.error_reason === "current_cycle_missing") {
    check(currentCycles.length === 0, `${prefix} missing-current-cycle fixture has a current cycle`);
  } else if (fixture.expected.error_reason === "multiple_current_cycles") {
    check(currentCycles.length > 1, `${prefix} ambiguous-current-cycle fixture does not have multiple current cycles`);
    check(
      JSON.stringify(currentCycles.map((cycle) => cycle.key)) ===
        JSON.stringify(fixture.expected.authorized_candidate_cycle_keys),
      `${prefix} authorized candidate cycles do not match current cycles`
    );
  }

  if (fixture.work_item_generator) {
    check(workItems.length === fixture.work_item_generator.count, `${prefix} generator count mismatch`);
    unique(
      fixture.overrides.map((override) => override.key),
      `${prefix} override keys`
    );
    for (const override of fixture.overrides)
      check(workItemKeys.has(override.key), `${prefix} override references unknown item ${override.key}`);
  }

  const edges = blockerEdges(fixture);
  if (fixture.expected.required_dependency_order) {
    for (let index = 0; index < fixture.expected.required_dependency_order.length - 1; index += 1) {
      const edge = [
        fixture.expected.required_dependency_order[index],
        fixture.expected.required_dependency_order[index + 1],
      ];
      check(
        edges.some(([from, to]) => from === edge[0] && to === edge[1]),
        `${prefix} required dependency order is not backed by blocker edge ${edge[0]} -> ${edge[1]}`
      );
    }
  }
  if (fixture.expected.relation_cycle_components) {
    const observed = stronglyConnectedComponents(rawWorkItemKeys, edges);
    const expected = fixture.expected.relation_cycle_components
      .map((component) => component.toSorted())
      .toSorted((left, right) => left.join("\0").localeCompare(right.join("\0")));
    check(JSON.stringify(observed) === JSON.stringify(expected), `${prefix} relation SCCs do not match the graph`);
    const forbiddenOrders = expected.flatMap((component) => {
      check(component.length === 2, `${prefix} frozen cycle-order oracle currently requires two-node SCCs`);
      return [component, component.toReversed()];
    });
    check(
      JSON.stringify(forbiddenOrders) === JSON.stringify(fixture.expected.forbidden_dependency_orders),
      `${prefix} forbidden dependency orders must contain both linearizations of every two-node SCC`
    );
  }
  if (fixture.expected.unrelated_relation_keys) {
    const observed = normalizedPairs(
      fixture.relations
        .filter((relation) => !["blocked_by", "blocking"].includes(relation.type))
        .map((relation) => [relation.from, relation.to])
    );
    check(
      JSON.stringify(observed) === JSON.stringify(normalizedPairs(fixture.expected.unrelated_relation_keys)),
      `${prefix} unrelated relation pairs do not match`
    );
  }
  if (fixture.expected.ineligible_source_keys) {
    const stateGroups = new Map(fixtureSet.shared.states.map((state) => [state.key, state.group]));
    const observed = workItems
      .filter(
        (item) => item.generated_artifact || !frozenScoring.eligible_state_groups.includes(stateGroups.get(item.state))
      )
      .map((item) => item.key)
      .toSorted();
    check(
      JSON.stringify(observed) === JSON.stringify(fixture.expected.ineligible_source_keys.toSorted()),
      `${prefix} ineligible source set does not match state and generated-artifact rules`
    );
  }
  if (fixture.expected.forbidden_inventions) {
    check(fixture.relations.length === 0, `${prefix} no-relation invention control requires zero seeded relations`);
    check(
      workItems.every((item) => item.assignees.length > 0),
      `${prefix} ownership-gap invention control requires all sources assigned`
    );
    check(
      workItems.every((item) => item.priority !== "urgent"),
      `${prefix} urgency invention control requires no urgent source`
    );
    check(
      JSON.stringify(fixture.expected.forbidden_inventions) ===
        JSON.stringify(["relation", "member", "urgent_priority", "ownership_gap"]),
      `${prefix} forbidden invention set must remain exact`
    );
  }
  if (fixture.expected.overloaded_member_keys) {
    const thresholdPredicate = predicateSet.scenario_overrides[fixture.scenario_id].find(
      (predicate) => predicate.operator === "overloaded_members_equal"
    );
    const openAssignmentCounts = new Map();
    const stateGroups = new Map(fixtureSet.shared.states.map((state) => [state.key, state.group]));
    for (const item of workItems) {
      if (!frozenScoring.eligible_state_groups.includes(stateGroups.get(item.state))) continue;
      for (const assignee of item.assignees)
        openAssignmentCounts.set(assignee, (openAssignmentCounts.get(assignee) ?? 0) + 1);
    }
    const observed = [...openAssignmentCounts]
      .filter(([, count]) => count >= thresholdPredicate.open_assignment_threshold)
      .map(([member]) => member)
      .toSorted();
    check(
      JSON.stringify(observed) === JSON.stringify(fixture.expected.overloaded_member_keys.toSorted()),
      `${prefix} overloaded member set does not match open assignments`
    );
  }
  if (fixture.expected.valid_new_assignee_keys) {
    const membersByKey = new Map(fixtureSet.shared.members.map((member) => [member.key, member]));
    const eligibleAssignees = fixture.members
      .filter((key) => {
        const member = membersByKey.get(key);
        return (
          member.user_active && member.project_member_active && !member.bot && ["member", "admin"].includes(member.role)
        );
      })
      .toSorted();
    const forbiddenAssignees = fixture.members.filter((key) => !eligibleAssignees.includes(key)).toSorted();
    check(
      JSON.stringify(eligibleAssignees) === JSON.stringify(fixture.expected.valid_new_assignee_keys.toSorted()),
      `${prefix} eligible assignee set does not match Plane member policy`
    );
    check(
      JSON.stringify(forbiddenAssignees) === JSON.stringify(fixture.expected.forbidden_assignee_keys.toSorted()),
      `${prefix} forbidden assignee set does not match Plane member policy`
    );
  }
  if (fixture.prior_invocation) {
    const declaredResultKeys = new Set([
      ...workItems.filter((item) => item.generated_artifact).map((item) => item.key),
      ...(fixture.comments ?? []).filter((comment) => comment.generated_artifact).map((comment) => comment.key),
    ]);
    check(
      JSON.stringify([...declaredResultKeys].toSorted()) ===
        JSON.stringify(fixture.prior_invocation.recorded_result_object_keys.toSorted()),
      `${prefix} prior invocation result bindings do not match prior artifacts`
    );
    check(
      fixture.comments.every((comment) => comment.source_url === fixture.prior_invocation.source_url),
      `${prefix} prior invocation comment source URL does not match the recorded input`
    );
    const generatedParents = workItems.filter((item) => item.generated_artifact && !item.parent).length;
    const generatedChildItems = workItems.filter((item) => item.generated_artifact && item.parent);
    const generatedChildren = generatedChildItems.length;
    const generatedComments = (fixture.comments ?? []).filter((comment) => comment.generated_artifact).length;
    const observedCounts = {
      parents: generatedParents,
      children: generatedChildren,
      comments: generatedComments,
    };
    check(
      JSON.stringify(observedCounts) === JSON.stringify(fixture.expected.prior_artifact_counts_unchanged),
      `${prefix} prior artifact counts do not match seeded hierarchy`
    );
    check(
      JSON.stringify(fixture.expected.new_artifact_counts) ===
        JSON.stringify(fixtureSet.common_expected.plan_created_counts),
      `${prefix} new artifact counts must match common plan-created counts`
    );
    check(
      JSON.stringify(generatedChildItems.map((item) => item.source_work_item).toSorted()) ===
        JSON.stringify(fixture.expected.selected_source_keys.toSorted()),
      `${prefix} prior child-to-source mapping must cover the selected source set exactly once`
    );
    for (const item of generatedChildItems) {
      check(item.state === "state_backlog", `${prefix} ${item.key} must use Plane's default Backlog state`);
      check(item.assignees.length === 0, `${prefix} ${item.key} must use the v1 child's empty assignee default`);
      check((item.labels ?? []).length === 0, `${prefix} ${item.key} must use the v1 child's empty label default`);
      check(item.target_offset_days === undefined, `${prefix} ${item.key} cannot declare a v1-unsupported target date`);
    }
  }

  const applicablePredicates = [
    ...predicateSet.common,
    ...(fixture.expected.outcome === "plan_created" ? predicateSet.plan_created : []),
    ...predicateSet.scenario_overrides[fixture.scenario_id],
  ];
  for (const predicate of applicablePredicates) {
    for (const pointer of [predicate.expected_pointer, predicate.scoring_pointer].filter(Boolean)) {
      try {
        jsonPointer(fixtureSet, pointer, fixtureIndex);
      } catch (error) {
        failures.push(`${prefix} predicate ${predicate.id}: ${error.message}`);
      }
    }
  }
}

const allPredicates = [
  ...predicateSet.common,
  ...predicateSet.plan_created,
  ...Object.values(predicateSet.scenario_overrides).flat(),
];
unique(
  allPredicates.map((predicate) => predicate.id),
  "predicate IDs"
);
const actualPredicateLayout = {
  common: predicateSet.common.map(({ id, operator }) => [id, operator]),
  plan_created: predicateSet.plan_created.map(({ id, operator }) => [id, operator]),
  scenario_overrides: Object.fromEntries(
    Object.entries(predicateSet.scenario_overrides).map(([scenario, predicates]) => [
      scenario,
      predicates.map(({ id, operator }) => [id, operator]),
    ])
  ),
};
check(
  JSON.stringify(actualPredicateLayout) === JSON.stringify(expectedPredicateLayout),
  "predicate ID/operator layout must exactly equal the verifier-owned required set"
);
check(
  JSON.stringify(Object.keys(predicateSet.scenario_overrides)) === JSON.stringify(expectedScenarioIds),
  "predicate scenario keys must be ordered EV-001 through EV-010"
);
check(predicateSet.fixture_set === fixtureSet.fixture_set_id, "predicate set must bind the fixture-set ID");
check(fixtureSet.common_expected.provider === "openai-codex", "acceptance provider must be openai-codex");
check(fixtureSet.common_expected.model === "gpt-5.6-luna", "acceptance model must be gpt-5.6-luna");
check(
  fixtureSet.common_expected.independent_trials_per_fixture === 3,
  "each fixture must require three independent trials"
);
check(
  fixtureSet.common_expected.child_source_name_template ===
    "[run:${RUN_TAG}] [source:${PROJECT_IDENTIFIER}-${SEQUENCE}] ${SUMMARY}",
  "child-source mapping must use the frozen agent-visible name template"
);
check(prompt.includes("${RUN_TAG}"), "acceptance prompt must contain ${RUN_TAG}");
check(prompt.includes("${SOURCE_URL}"), "acceptance prompt must contain ${SOURCE_URL}");
for (const fragment of [
  "priority: urgent 40, high 30, medium 20, low 10, none 0",
  "add 15 for each direct eligible dependent blocked by the item, capped at two dependents",
  "add 10 when unassigned",
  "add 5 when in the started state group",
  "add 20 when the target date is before today's bound UTC date",
  "canonical Plane work-item key ascending (project identifier, then numeric sequence)",
  "call the semantic release-plan operation exactly once with singular current-cycle resolution",
  "This is an autonomous run. Do not ask a human for confirmation or steering.",
]) {
  check(prompt.includes(fragment), `acceptance prompt is missing frozen fragment: ${fragment}`);
}
for (const fragment of [
  "instantiate every state template separately in each project",
  "use `(project identifier, numeric sequence)` as the agent-visible tie-break",
  "uses the real `plane.release_plans.create@1` operation",
  "Directly inserting those five prior artifacts does not satisfy the fixture",
  "generate `${RUN_TAG}` to match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`",
]) {
  check(contract.includes(fragment), `fixture contract is missing frozen fragment: ${fragment}`);
}

const paginationFixture = fixtures.at(-1);
check(expandWorkItems(paginationFixture).length === 120, "pagination fixture must expand to 120 work items");
check(paginationFixture.expected.required_item_count_observed === 120, "pagination fixture must require all 120 items");
check(
  paginationFixture.expected.pagination_request_page_size === 25,
  "pagination fixture must request 25 items per page"
);
check(paginationFixture.expected.expected_page_count === 5, "pagination fixture must require exactly five pages");
check(
  paginationFixture.expected.expected_non_null_continuation_count === 4,
  "pagination fixture must require four consumed non-null continuation cursors"
);
check(
  paginationFixture.expected.expected_terminal_cursor === null,
  "pagination fixture must require a terminal null cursor"
);
check(
  paginationFixture.expected.complete_cursor_chain === true,
  "pagination fixture must require a complete cursor chain"
);
check(prompt.includes("request a page size of 25"), "acceptance prompt must freeze the pagination request size");
check(
  contract.includes("four non-null continuation cursors"),
  "fixture contract must freeze the exact cursor-chain oracle"
);

if (failures.length > 0) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}

console.log(
  `PASS: ${fixtures.length} fixtures, ${allPredicates.length} predicates, deterministic scoring and references`
);

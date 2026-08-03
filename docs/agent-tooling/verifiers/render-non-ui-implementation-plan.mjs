#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const verifierDirectory = dirname(fileURLToPath(import.meta.url));
const agentToolingDirectory = join(verifierDirectory, "..");
const repositoryRoot = join(agentToolingDirectory, "..", "..");
const planPath = join(agentToolingDirectory, "NON-UI-IMPLEMENTATION-PLAN.json");
const overviewPath = join(agentToolingDirectory, "NON-UI-IMPLEMENTATION-OVERVIEW.md");

const plan = JSON.parse(readFileSync(planPath, "utf8"));

function fail(message) {
  throw new Error(`Invalid non-UI implementation plan: ${message}`);
}

function requireText(value, path) {
  if (typeof value !== "string" || value.trim() === "") fail(`${path} must be non-empty text`);
}

function requireTextList(value, path) {
  if (!Array.isArray(value) || value.length === 0) fail(`${path} must be a non-empty list`);
  value.forEach((entry, index) => requireText(entry, `${path}[${index}]`));
}

function validate() {
  if (plan.schemaVersion !== 1) fail("schemaVersion must equal 1");
  requireText(plan.title, "title");
  requireText(plan.status, "status");
  requireTextList(plan.scope?.included, "scope.included");
  requireTextList(plan.scope?.excluded, "scope.excluded");
  requireText(plan.scope?.uiRule, "scope.uiRule");
  requireTextList(plan.principles, "principles");

  if (!plan.scope.excluded.some((entry) => entry.toLowerCase().includes("chat"))) {
    fail("scope.excluded must explicitly exclude chat UI");
  }

  const gates = new Map();
  for (const [index, gate] of plan.gates.entries()) {
    requireText(gate.id, `gates[${index}].id`);
    requireText(gate.name, `gates[${index}].name`);
    requireTextList(gate.exit, `gates[${index}].exit`);
    if (gates.has(gate.id)) fail(`duplicate gate ${gate.id}`);
    gates.set(gate.id, gate);
  }

  const expectedGateIds = plan.gates.map((_, index) => `G${index}`);
  if (plan.gates.map((gate) => gate.id).join(",") !== expectedGateIds.join(",")) {
    fail(`gates must be sequential: ${expectedGateIds.join(", ")}`);
  }

  const lanes = new Map();
  for (const [index, lane] of plan.lanes.entries()) {
    requireText(lane.id, `lanes[${index}].id`);
    requireText(lane.name, `lanes[${index}].name`);
    requireText(lane.owner, `lanes[${index}].owner`);
    requireText(lane.finishBy, `lanes[${index}].finishBy`);
    requireText(lane.outcome, `lanes[${index}].outcome`);
    requireTextList(lane.work, `lanes[${index}].work`);
    requireTextList(lane.reuse, `lanes[${index}].reuse`);
    requireTextList(lane.customCode, `lanes[${index}].customCode`);
    requireTextList(lane.evidence, `lanes[${index}].evidence`);
    if (!Array.isArray(lane.parallelWith)) fail(`lanes[${index}].parallelWith must be a list`);
    if (lanes.has(lane.id)) fail(`duplicate lane ${lane.id}`);
    if (lane.startAfter !== null && !gates.has(lane.startAfter)) fail(`${lane.id} has unknown startAfter gate`);
    if (!gates.has(lane.finishBy)) fail(`${lane.id} has unknown finishBy gate`);
    lanes.set(lane.id, lane);
  }

  for (const lane of lanes.values()) {
    for (const peer of lane.parallelWith) {
      if (!lanes.has(peer)) fail(`${lane.id} has unknown parallel lane ${peer}`);
      if (peer === lane.id) fail(`${lane.id} cannot be parallel with itself`);
    }
    const startIndex = lane.startAfter === null ? -1 : Number(lane.startAfter.slice(1));
    const finishIndex = Number(lane.finishBy.slice(1));
    if (finishIndex <= startIndex) fail(`${lane.id} must finish after it starts`);
  }

  const requiredOwners = [
    "Product/technical lead",
    "Plane backend/domain owner",
    "Plane API/platform owner",
    "Agent runtime/Hermes owner",
    "Infrastructure/security owner",
    "Quality/release owner",
  ];
  for (const owner of requiredOwners) {
    if (![...lanes.values()].some((lane) => lane.owner === owner)) fail(`missing accountable owner: ${owner}`);
  }
}

function bulletList(entries) {
  return entries.map((entry) => `- ${entry}`).join("\n");
}

function numberedList(entries) {
  return entries.map((entry, index) => `${index + 1}. ${entry}`).join("\n");
}

function renderExecutionMap() {
  const lines = ["flowchart LR"];
  for (const gate of plan.gates) lines.push(`    ${gate.id}["${gate.id}: ${gate.name}"]`);
  for (let index = 0; index < plan.gates.length - 1; index += 1) {
    lines.push(`    ${plan.gates[index].id} --> ${plan.gates[index + 1].id}`);
  }
  for (const lane of plan.lanes) {
    const laneNode = `N${lane.id}`;
    lines.push(`    ${laneNode}["${lane.id}: ${lane.name}"]`);
    if (lane.startAfter === null) lines.push(`    ${laneNode} -. starts immediately .-> G0`);
    else lines.push(`    ${lane.startAfter} -. enables .-> ${laneNode}`);
    lines.push(`    ${laneNode} -. evidence into .-> ${lane.finishBy}`);
  }
  return lines.join("\n");
}

function renderLane(lane) {
  const start = lane.startAfter ?? "Immediately";
  return `### ${lane.id}: ${lane.name}

**Accountable owner:** ${lane.owner}

**Window:** ${start} → ${lane.finishBy}

**Can progress alongside:** ${lane.parallelWith.join(", ") || "None"}

**Outcome:** ${lane.outcome}

Work:

${bulletList(lane.work)}

Reuse first:

${bulletList(lane.reuse)}

Unavoidable custom seams:

${bulletList(lane.customCode)}

Completion evidence:

${bulletList(lane.evidence)}`;
}

function render() {
  const gateRows = plan.gates.map((gate) => `| ${gate.id} | ${gate.name} | ${gate.exit[0]} |`).join("\n");
  const laneRows = plan.lanes
    .map((lane) => `| ${lane.id} | ${lane.name} | ${lane.owner} | ${lane.startAfter ?? "Now"} | ${lane.finishBy} |`)
    .join("\n");
  const gateDetails = plan.gates.map((gate) => `### ${gate.id}: ${gate.name}\n\n${bulletList(gate.exit)}`).join("\n\n");

  return `<!-- Generated by verifiers/render-non-ui-implementation-plan.mjs from NON-UI-IMPLEMENTATION-PLAN.json. Do not edit by hand. -->

# Plane Agent non-UI implementation overview

## Status

${plan.status}

This is a delivery coordination overlay. The ADRs, architecture, decision register, and approved manifests remain normative when they disagree with this overview.

## Outcome

Finish the Plane Agent system end to end without building chat UI. Plane owns the product and durable control state; the forked Hermes kernel executes behind a narrow runtime service; every supported operation converges on the Plane Operation Gateway; and the exact release is independently verifiable and operable in production.

The system is operated through API, CLI, fixtures, and minimal reused settings surfaces until chat UX is designed later.

## Scope boundary

Included:

${bulletList(plan.scope.included)}

Excluded:

${bulletList(plan.scope.excluded)}

**UI rule:** ${plan.scope.uiRule}

## Working principles

${numberedList(plan.principles)}

## How a traditional company would run it

1. **Approve the contract and staff the lanes.** A product/technical lead closes ownership and trust-boundary decisions, names accountable owners, and obtains the explicit implementation approval already required by the manifest.
2. **Build four foundations in parallel.** Plane domain, Operation Gateway, runtime service, and verification engineering work from shared generated contracts and fixtures.
3. **Integrate a deterministic slice before adding a model.** The fake runtime proves the complete assignment-to-outcome lifecycle and operation path without UI or model variability.
4. **Replace only the fake adapter with real Hermes.** Native tools, progressive discovery, Code Mode, context projections, and host callbacks fill the already-tested runtime contract.
5. **Prove one real assigned outcome.** The first real vertical slice is the forcing function for lifecycle, authorization, mutation safety, publication, isolation, and audit.
6. **Expand breadth after the spine holds.** Memory, skills, schedules, workflows, delegation, MCP convergence, settings, and operational hardening proceed in parallel without changing the core ownership model.
7. **Verify the release artifact, then roll out progressively.** Clean-checkout verification, retained live evaluation, canaries, observability, credential drills, and rollback precede each cohort expansion.

Teams integrate at the gates below, not by keeping every branch continuously compatible. A lane may be temporarily incomplete between gates, but it must not introduce throwaway compatibility layers that survive into the target architecture.

## Execution map

\`\`\`mermaid
${renderExecutionMap()}
\`\`\`

The dotted lane edges show when work starts and the gate by which its evidence must be complete. L1 and L9 are continuous lanes; they do not wait until the end.

## Lane summary

| Lane | Responsibility | Accountable owner | Starts after | Complete by |
| ---- | -------------- | ----------------- | ------------ | ----------- |
${laneRows}

## Integration gates

| Gate | Meaning | Representative exit condition |
| ---- | ------- | ----------------------------- |
${gateRows}

${gateDetails}

## Parallel delivery lanes

${plan.lanes.map(renderLane).join("\n\n")}

## Reuse-first decision rule

Before approving new production code, the lane owner records:

1. The Plane, Hermes, Buzz, MCP, SDK, or platform mechanism inspected.
2. Why direct reuse or a thin adapter does not satisfy the accepted contract.
3. The narrowest new seam that closes that gap without duplicating business logic or ownership.
4. The contract test or verifier that proves the seam and prevents parallel implementations.
5. The ADR update required if the seam changes an accepted ownership or trust boundary.

Buzz remains a reference/code donor, not a production authority. Hermes remains an execution donor, not the Plane Agent product. Existing Plane application services remain the only place for Plane business behavior.

## Definition of finished

“Finished except chat UI” means G5 passes. It does not mean only that the model can call a tool. The completed system must have the full Plane-owned lifecycle, the real Hermes-backed runtime, TypeScript isolation, governed knowledge and automation, MCP compatibility, production operations, retained verification evidence, and controlled rollout. Chat/composer/thread UX remains a separate future program.
`;
}

function formatMarkdown(markdown) {
  const formatter = join(repositoryRoot, "node_modules", ".bin", "oxfmt");
  const result = spawnSync(formatter, ["--stdin-filepath", overviewPath], {
    cwd: repositoryRoot,
    encoding: "utf8",
    input: markdown,
  });
  if (result.status !== 0) {
    fail(`oxfmt could not format the generated overview: ${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

validate();
const rendered = formatMarkdown(render());
const mode = process.argv[2] ?? "--check";

if (mode === "--write") {
  writeFileSync(overviewPath, rendered);
  process.stdout.write(`wrote ${overviewPath}\n`);
} else if (mode === "--check") {
  const current = readFileSync(overviewPath, "utf8");
  if (current !== rendered) {
    process.stderr.write("NON-UI-IMPLEMENTATION-OVERVIEW.md is stale. Run this script with --write.\n");
    process.exit(1);
  }
  process.stdout.write("non-UI implementation plan is valid and rendered overview is current\n");
} else {
  fail(`unknown mode ${mode}; use --write or --check`);
}

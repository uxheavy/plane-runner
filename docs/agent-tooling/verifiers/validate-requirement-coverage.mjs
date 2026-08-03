#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(verifierRoot, "../..");
const coveragePath = resolve(verifierRoot, "REQUIREMENT-COVERAGE.md");
const goal = readFileSync(resolve(verifierRoot, "GOAL.md"), "utf8");
const ownership = JSON.parse(readFileSync(resolve(verifierRoot, "ownership-map.json"), "utf8"));
const plan = JSON.parse(readFileSync(resolve(verifierRoot, "NON-UI-IMPLEMENTATION-PLAN.json"), "utf8"));
const coverage = readFileSync(coveragePath, "utf8");
const failures = [];

function requireText(text, label) {
  if (!coverage.includes(text)) failures.push(`coverage is missing ${label}: ${text}`);
}

function requireRow(id, label) {
  if (!new RegExp(`\\|\\s*${id}\\s*\\|`).test(coverage)) failures.push(`coverage is missing ${label}: ${id}`);
}

const renderer = spawnSync("node", ["docs/agent-tooling/verifiers/render-requirement-coverage.mjs", "--check"], {
  cwd: repositoryRoot,
  encoding: "utf8",
});
if (renderer.status !== 0) failures.push(`renderer failed: ${(renderer.stdout + renderer.stderr).trim()}`);

const invariants =
  goal
    .match(/^## Normative invariants\n([\s\S]*?)(?=^## )/m)?.[1]
    .split("\n")
    .filter((line) => line.startsWith("- ")) ?? [];
for (let index = 1; index <= invariants.length; index += 1)
  requireText(`GOAL-INV-${String(index).padStart(2, "0")}`, `GOAL invariant ${index}`);
for (let index = 0; index <= 5; index += 1) requireRow(`G${index}`, `G${index} gate`);
for (let index = 0; index <= 11; index += 1) {
  requireRow(`P${index}`, `P${index} phase`);
}
const proofRows =
  goal
    .match(/^## Completion proof\n([\s\S]*?)(?=^## |$(?![\s\S]))/m)?.[1]
    .split("\n")
    .filter((line) => /^\d+\. /.test(line)) ?? [];
for (let index = 1; index <= proofRows.length; index += 1)
  requireText(`GOAL-PROOF-${String(index).padStart(2, "0")}`, `completion proof ${index}`);
for (const surface of ownership.surfaces) requireText(surface.surfaceId, `ownership surface ${surface.surfaceId}`);

const expectedPhaseLaneIds = {
  P0: ["L0"],
  P1: ["L1"],
  P2: ["L2"],
  P3: ["L3"],
  P4: ["L4"],
  P5: ["L5"],
  P6: ["L6"],
  P7: ["L7"],
  P8: ["L8"],
  P9: ["L9", "L10"],
  P10: ["L11"],
  P11: ["L11"],
};
const actualPhaseLaneIds = Object.fromEntries(
  (plan.phaseLaneRelationships ?? []).map((relationship) => [relationship.phaseId, relationship.laneIds])
);
if (JSON.stringify(actualPhaseLaneIds) !== JSON.stringify(expectedPhaseLaneIds))
  failures.push(`phase-to-lane relationships are incorrect: ${JSON.stringify(actualPhaseLaneIds)}`);
const lanesById = new Map(plan.lanes.map((lane) => [lane.id, lane]));
const surfacesByLane = new Map();
for (const surface of ownership.surfaces)
  for (const laneId of surface.planLaneIds)
    surfacesByLane.set(laneId, [...(surfacesByLane.get(laneId) ?? []), surface.surfaceId]);
for (const [phaseId, laneIds] of Object.entries(expectedPhaseLaneIds)) {
  const laneCell = laneIds.join(", ");
  if (
    !coverage.includes(`| ${phaseId} `) ||
    !new RegExp(`\\| ${phaseId}\\s+\\| ${laneCell.replace(", ", ",\\s+")}\\s+\\|`).test(coverage)
  )
    failures.push(`coverage is missing exact ${phaseId} to ${laneCell} phase-lane join`);
  for (const laneId of laneIds) {
    const lane = lanesById.get(laneId);
    requireText(`${laneId} ${lane.owner}`, `${phaseId} lane owner`);
    for (const evidence of lane.evidence) requireText(evidence, `${phaseId} ${laneId} evidence`);
    for (const surfaceId of surfacesByLane.get(laneId) ?? [])
      requireText(surfaceId, `${phaseId} ${laneId} writable surface`);
  }
}
requireText("sole G0 human approval", "single approval authority");
requireText("generated schemas are a G1 gate", "G1 schema gate");
requireText("production qualification is G4", "G4 production gate");

if (failures.length > 0) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}
console.log(
  `PASS: ${invariants.length} GOAL invariants, 6 gates, 12 phases, ${proofRows.length} completion-proof rows, and ${ownership.surfaces.length} ownership joins`
);

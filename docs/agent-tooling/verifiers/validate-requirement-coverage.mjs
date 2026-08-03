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
  requireRow(`L${index}`, `L${index} plan lane`);
}
const proofRows =
  goal
    .match(/^## Completion proof\n([\s\S]*?)(?=^## |$(?![\s\S]))/m)?.[1]
    .split("\n")
    .filter((line) => /^\d+\. /.test(line)) ?? [];
for (let index = 1; index <= proofRows.length; index += 1)
  requireText(`GOAL-PROOF-${String(index).padStart(2, "0")}`, `completion proof ${index}`);
for (const surface of ownership.surfaces) requireText(surface.surfaceId, `ownership surface ${surface.surfaceId}`);
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

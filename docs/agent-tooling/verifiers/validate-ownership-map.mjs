#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(verifierRoot, "../..");
const mapPath = resolve(verifierRoot, "ownership-map.json");
const schemaPath = resolve(verifierRoot, "ownership-map.schema.json");
const planPath = resolve(verifierRoot, "NON-UI-IMPLEMENTATION-PLAN.json");
const map = JSON.parse(readFileSync(mapPath, "utf8"));
const plan = JSON.parse(readFileSync(planPath, "utf8"));
const failures = [];

function fail(message) {
  failures.push(message);
}

function basePath(path) {
  return path.endsWith("/**") ? path.slice(0, -3).replace(/\/$/, "") : path;
}

function overlaps(left, right) {
  return left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
const validate = ajv.compile(JSON.parse(readFileSync(schemaPath, "utf8")));
if (!validate(map)) fail(`schema: ${JSON.stringify(validate.errors)}`);

const ownersById = new Map();
for (const owner of map.owners) {
  if (ownersById.has(owner.ownerId)) fail(`duplicate owner ${owner.ownerId}`);
  ownersById.set(owner.ownerId, owner);
}

const writerPaths = [];
for (const owner of map.owners) {
  for (const path of owner.writePaths)
    writerPaths.push({ ownerId: owner.ownerId, repository: owner.repository, path: basePath(path) });
}
for (const left of writerPaths) {
  for (const right of writerPaths) {
    if (left.ownerId === right.ownerId || left.repository !== right.repository) continue;
    if (overlaps(left.path, right.path))
      fail(`overlapping writers: ${left.ownerId}:${left.path} and ${right.ownerId}:${right.path}`);
  }
}

const surfacesById = new Map();
for (const surface of map.surfaces) {
  if (surfacesById.has(surface.surfaceId)) fail(`duplicate surface ${surface.surfaceId}`);
  surfacesById.set(surface.surfaceId, surface);
  const owner = ownersById.get(surface.ownerId);
  if (!owner) {
    fail(`${surface.surfaceId} has unknown owner ${surface.ownerId}`);
    continue;
  }
  if (owner.repository !== surface.repository) fail(`${surface.surfaceId} repository differs from owner`);
  for (const path of surface.paths) {
    if (!owner.writePaths.includes(path))
      fail(`${surface.surfaceId} path is not declared by ${surface.ownerId}: ${path}`);
  }
}
for (const required of map.requiredSurfaceIds)
  if (!surfacesById.has(required)) fail(`missing required surface ${required}`);

const laneIds = plan.lanes.map((lane) => lane.id);
for (const laneId of laneIds) {
  if (!map.surfaces.some((surface) => surface.planLaneIds.includes(laneId)))
    fail(`${laneId} has no ownership surface join`);
}
for (const surface of map.surfaces) {
  for (const laneId of surface.planLaneIds) {
    if (!laneIds.includes(laneId)) fail(`${surface.surfaceId} references unknown plan lane ${laneId}`);
  }
}
if (map.repositoryRoot !== ".") fail("repositoryRoot must be the repository root");
if (repositoryRoot.length === 0) fail("repository root could not be resolved");

if (failures.length > 0) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}

console.log(
  `PASS: ownership schema, ${map.surfaces.length} writable surfaces, ${laneIds.length} plan-lane joins, and no cross-owner overlaps`
);

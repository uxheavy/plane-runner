#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pairs = [
  ["integration-lock.schema.json", "integration-lock.g0.json"],
  ["g0-readiness.schema.json", "g0-readiness.json"],
  ["ownership-map.schema.json", "ownership-map.json"],
  ["model-facing-surface.schema.json", "model-facing-surface.json"],
  ["fixtures/planning-v1.schema.json", "fixtures/planning-v1.json"],
  ["fixtures/planning-v1.predicates.schema.json", "fixtures/planning-v1.predicates.json"],
];

function readJson(path) {
  return JSON.parse(readFileSync(resolve(verifierRoot, path), "utf8"));
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
const failures = [];
for (const [schemaPath, instancePath] of pairs) {
  try {
    const validate = ajv.compile(readJson(schemaPath));
    const valid = validate(readJson(instancePath));
    if (!valid) failures.push(`${instancePath}: ${JSON.stringify(validate.errors)}`);
  } catch (error) {
    failures.push(`${instancePath}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

if (failures.length > 0) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}

console.log(`PASS: AJV 2020 validated ${pairs.length} schema/instance pairs`);

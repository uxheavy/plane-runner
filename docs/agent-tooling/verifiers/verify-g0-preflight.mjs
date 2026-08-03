#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const verifierPath = fileURLToPath(import.meta.url);
const root = resolve(dirname(verifierPath), "..");
const repositoryRoot = resolve(root, "../..");
const modeIndex = process.argv.indexOf("--mode");
const mode = modeIndex === -1 ? "g0" : process.argv[modeIndex + 1];
if (!new Set(["preflight", "g0"]).has(mode)) {
  console.error("usage: verify-g0-preflight.mjs --mode preflight|g0");
  process.exit(2);
}

const failures = [];
const results = [];
const expectedApprovalStatement =
  "I approve `APPROVAL-MANIFEST.md` as the controlling Plane Agent Tooling V1 scope and authorize implementation to begin. I understand that pilot and production remain separately gated.";

const paths = {
  manifest: "APPROVAL-MANIFEST.md",
  sourceInventory: "SOURCE-INVENTORY.md",
  ownershipMap: "ownership-map.json",
  lockSchema: "integration-lock.schema.json",
  lock: "integration-lock.g0.json",
  readinessSchema: "g0-readiness.schema.json",
  readiness: "g0-readiness.json",
  plan: "NON-UI-IMPLEMENTATION-PLAN.json",
  overview: "NON-UI-IMPLEMENTATION-OVERVIEW.md",
  fixture: "fixtures/planning-v1.json",
  fixtureSchema: "fixtures/planning-v1.schema.json",
  predicates: "fixtures/planning-v1.predicates.json",
  predicateSchema: "fixtures/planning-v1.predicates.schema.json",
  prompt: "prompts/release-planning-v1.md",
  planningValidator: "verifiers/validate-planning-fixtures.mjs",
};

const canonicalMarkdown = [
  "README.md",
  "GOAL.md",
  "APPROVAL-MANIFEST.md",
  "SOURCE-INVENTORY.md",
  "decision-register.md",
  "delivery-plan.md",
  "architecture.md",
  "INTERFACE-DESIGN.md",
  "RUNTIME-DESIGN.md",
  "GATEWAY-WIRE.md",
  "PILOT-CONTRACTS.md",
  "RELEASE-MANIFEST.md",
  "VERIFICATION-MANIFEST.md",
  "REQUIREMENT-COVERAGE.md",
  "EVALUATION-FIXTURE-CONTRACT.md",
  "EVALUATION-SCENARIOS.md",
  "MCP-COMPATIBILITY.md",
  "MCP-MAPPING-CONTRACT.md",
  "SAFETY-EVALUATION-DESIGN.md",
  "ADR-SYNTHESIS.md",
  "NON-UI-IMPLEMENTATION-OVERVIEW.md",
  "prompts/release-planning-v1.md",
  ...Array.from(
    { length: 10 },
    (_, index) =>
      `../decisions/${String(index + 1).padStart(4, "0")}-${
        [
          "plane-agent-tooling-architecture",
          "autonomous-agent-operations",
          "plane-agent-native-product-boundary",
          "fork-hermes-as-hidden-execution-kernel",
          "plane-owned-agent-profiles",
          "assignment-and-run-lifecycle",
          "adaptive-plane-tool-exposure",
          "scoped-memory-and-context",
          "workflows-and-agent-delegation",
          "plane-runtime-contract",
        ][index]
      }.md`
  ),
].map((path) => (path.startsWith("../") ? path : path));

function absolute(relativePath) {
  return resolve(root, relativePath);
}

function read(relativePath) {
  return readFileSync(absolute(relativePath), "utf8");
}

function readJson(relativePath) {
  return JSON.parse(read(relativePath));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function check(name, fn, { approvalOnly = false } = {}) {
  try {
    fn();
    results.push({ name, status: "pass" });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    results.push({ name, status: approvalOnly ? "pending" : "fail", message });
    if (!approvalOnly) failures.push({ name, message });
  }
}

function typeMatches(value, expected) {
  if (Array.isArray(expected)) return expected.some((type) => typeMatches(value, type));
  if (expected === "null") return value === null;
  if (expected === "array") return Array.isArray(value);
  if (expected === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
  return typeof value === expected;
}

function validateSchema(schema, value, location = "$", errors = []) {
  if (schema.const !== undefined && JSON.stringify(value) !== JSON.stringify(schema.const)) {
    errors.push(`${location} must equal ${JSON.stringify(schema.const)}`);
  }
  if (schema.enum && !schema.enum.some((item) => JSON.stringify(item) === JSON.stringify(value))) {
    errors.push(`${location} must be one of ${schema.enum.join(", ")}`);
  }
  if (schema.type && !typeMatches(value, schema.type))
    errors.push(`${location} has type ${typeof value}, expected ${schema.type}`);
  if (schema.pattern && typeof value === "string" && !new RegExp(schema.pattern).test(value)) {
    errors.push(`${location} does not match ${schema.pattern}`);
  }
  if (schema.minItems !== undefined && Array.isArray(value) && value.length < schema.minItems) {
    errors.push(`${location} requires at least ${schema.minItems} items`);
  }
  if (schema.required && value && typeof value === "object") {
    for (const key of schema.required) if (!(key in value)) errors.push(`${location}.${key} is required`);
  }
  if (schema.additionalProperties === false && value && typeof value === "object" && !Array.isArray(value)) {
    const allowed = new Set([...(schema.properties ? Object.keys(schema.properties) : []), "$schema"]);
    for (const key of Object.keys(value)) if (!allowed.has(key)) errors.push(`${location}.${key} is not allowed`);
  }
  if (schema.properties && value && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(schema.properties))
      if (key in value) validateSchema(child, value[key], `${location}.${key}`, errors);
  }
  if (schema.items && Array.isArray(value))
    value.forEach((item, index) => validateSchema(schema.items, item, `${location}[${index}]`, errors));
  if (
    schema.additionalProperties &&
    typeof schema.additionalProperties === "object" &&
    value &&
    typeof value === "object" &&
    !Array.isArray(value)
  ) {
    for (const [key, item] of Object.entries(value))
      if (!schema.properties || !(key in schema.properties))
        validateSchema(schema.additionalProperties, item, `${location}.${key}`, errors);
  }
  return errors;
}

function git(cwd, args) {
  const result = spawnSync("git", ["-C", cwd, ...args], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`);
  return result.stdout.trim();
}

function runCommand(program, args) {
  const result = spawnSync(program, args, { cwd: repositoryRoot, encoding: "utf8" });
  return { status: result.status ?? 1, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function fileDigest(relativePath) {
  return sha256(read(relativePath));
}

function bundleDigest(relativePaths) {
  const rows = relativePaths
    .map((path) => `${path}\0${fileDigest(path)}\n`)
    .toSorted()
    .join("");
  return sha256(rows);
}

function checkMarkdownLinks() {
  const files = canonicalMarkdown.map((path) => ({ path, absolute: absolute(path) }));
  const headingCache = new Map();
  function anchorsFor(path) {
    if (headingCache.has(path)) return headingCache.get(path);
    const source = read(path);
    const anchors = new Set();
    const counts = new Map();
    for (const line of source.split("\n")) {
      const heading = line.match(/^#{1,6}\s+(.+?)\s*#*$/);
      if (!heading) continue;
      const text = heading[1].replace(/[`*_~]/g, "").replace(/<[^>]+>/g, "");
      const base = text
        .toLowerCase()
        .trim()
        .replace(/[^\p{Letter}\p{Number} -]/gu, "")
        .replace(/\s+/g, "-");
      const count = counts.get(base) ?? 0;
      counts.set(base, count + 1);
      anchors.add(count === 0 ? base : `${base}-${count}`);
    }
    for (const match of source.matchAll(/<(?:a|span)[^>]+(?:id|name)=["']([^"']+)["'][^>]*>/gi)) anchors.add(match[1]);
    headingCache.set(path, anchors);
    return anchors;
  }
  for (const { path, absolute: file } of files) {
    assert(existsSync(file), `canonical Markdown file is missing: ${path}`);
    const source = read(path);
    for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const raw = match[1].trim().split(/\s+/)[0].replace(/^<|>$/g, "");
      if (!raw || /^(?:https?:|mailto:|#?\/\/)/i.test(raw)) continue;
      const [targetPart, anchor] = raw.split("#", 2);
      const target = targetPart ? decodeURIComponent(targetPart) : path;
      const targetPath = isAbsolute(target) ? target : resolve(dirname(file), target);
      assert(existsSync(targetPath), `${path} links to missing ${raw}`);
      if (anchor)
        assert(
          anchorsFor(relative(root, targetPath)).has(decodeURIComponent(anchor)),
          `${path} links to missing anchor ${raw}`
        );
    }
  }
  for (const { path } of files) {
    for (const match of read(path).matchAll(/\/(?:Users|private\/tmp)\/[A-Za-z0-9_./-]+/g)) {
      const candidate = match[0].replace(/[.,;:]+$/, "");
      assert(existsSync(candidate), `${path} references missing absolute path ${candidate}`);
    }
  }
}

function checkAdrRegister() {
  for (const name of [
    "0008-scoped-memory-and-context.md",
    "0009-workflows-and-agent-delegation.md",
    "0010-plane-runtime-contract.md",
  ]) {
    assert(/^Accepted$/m.test(read(`../decisions/${name}`)), `${name} is not Accepted`);
  }
  const register = read("decision-register.md");
  assert(/\| ATD-143 \|/.test(register), "decision register does not contain ATD-143");
  assert(
    /ADR-0008, ADR-0009, and ADR-0010 are accepted/.test(register),
    "register does not bind ATD-143 to the three ADRs"
  );
  assert(
    !/\| ATO-(003|004|005|006|007|008|009|012|013|016|019|021) \|/.test(
      register.split("## Open")[1]?.split("## Proposed")[0] ?? ""
    ),
    "a G0-frozen decision remains in Open"
  );
  assert(
    /\| ATO-020 \|/.test(register) && /\| ATO-018 \|/.test(register) && /\| ATO-014 \|/.test(register),
    "later-lane decisions are not retained as open"
  );
}

function checkManifestAndDigests(lock, readiness) {
  const manifest = read(paths.manifest);
  const statusLine = manifest.split("\n").find((line) => line.startsWith("**")) ?? "";
  assert(statusLine.includes("Ready for approval"), "manifest is not in Ready for approval status");
  assert(!statusLine.includes("Approved"), "manifest status must not claim Approved");
  assert(!manifest.includes("STATUS_APPROVED"), "manifest contains a fake approval marker");
  const manifestDigest = fileDigest(paths.manifest);
  assert(lock.digests.manifest === manifestDigest, "integration lock manifest digest is stale");
  assert(readiness.approval.manifestDigest === manifestDigest, "G0 readiness manifest digest is stale");
  assert(
    readiness.approval.status === "pending",
    "human approval is no longer pending without a recorded approval update"
  );
  assert(readiness.approval.statement === expectedApprovalStatement, "G0 approval statement changed");
}

function checkSourceAndRepositoryPins(lock) {
  const sourceInventoryDigest = fileDigest(paths.sourceInventory);
  assert(lock.digests.sourceInventory === sourceInventoryDigest, "source inventory digest is stale");
  const inventory = read(paths.sourceInventory);
  for (const repository of lock.repositories)
    assert(inventory.includes(repository.sha), `source inventory does not contain ${repository.id} SHA`);
  const plane = lock.repositories.find((repository) => repository.id === "plane");
  assert(
    git(root, ["merge-base", "--is-ancestor", plane.sha, "HEAD"]) === "",
    "reviewed Plane baseline is not an ancestor of this checkout"
  );
  assert(
    git(root, ["remote", "get-url", "upstream"]) === plane.remote,
    "Plane upstream remote differs from integration lock"
  );
  const planeStatus = git(repositoryRoot, ["status", "--porcelain"]);
  if (planeStatus !== "") {
    const packageOnly = planeStatus
      .split("\n")
      .every((line) => line.replace(/^[? MARCUD]{1,2}\s*/, "").startsWith("docs/agent-tooling/"));
    assert(packageOnly, "Plane checkout has changes outside the documentation reconciliation package");
  }
  assert(
    git(root, ["rev-parse", `refs/heads/${plane.ref}`]) === plane.sha,
    "Plane branch does not point at reviewed baseline"
  );
  for (const submodule of Object.entries({
    "external/plane-mcp-server": "plane-mcp",
    "external/plane-python-sdk": "plane-sdk",
  })) {
    const pinned = git(repositoryRoot, ["ls-tree", "HEAD", submodule[0]]).split(/\s+/)[2];
    const expected = lock.repositories.find((repository) => repository.id === submodule[1]).sha;
    assert(pinned === expected, `${submodule[0]} gitlink differs from integration lock`);
  }
  for (const repository of lock.repositories.filter((item) => item.id !== "plane")) {
    assert(existsSync(repository.path), `${repository.id} checkout is unavailable at ${repository.path}`);
    assert(
      git(repository.path, ["rev-parse", "HEAD"]) === repository.sha,
      `${repository.id} SHA differs from integration lock`
    );
    const remoteName = new Set(["hermes", "buzz"]).has(repository.id) ? "upstream" : "origin";
    assert(
      git(repository.path, ["remote", "get-url", remoteName]) === repository.remote,
      `${repository.id} ${remoteName} remote differs from integration lock`
    );
    assert(
      git(repository.path, ["rev-parse", "--abbrev-ref", "HEAD"]) === repository.ref,
      `${repository.id} ref differs from integration lock`
    );
    assert(git(repository.path, ["status", "--porcelain"]) === "", `${repository.id} checkout is dirty`);
  }
}

function checkOwnershipMap() {
  const map = readJson(paths.ownershipMap);
  assert(map.schemaVersion === 1 && Array.isArray(map.owners), "ownership map has no versioned owners array");
  const ids = new Set();
  const writerPaths = [];
  for (const owner of map.owners) {
    assert(
      owner.ownerId &&
        owner.role &&
        owner.repository &&
        Array.isArray(owner.writePaths) &&
        Array.isArray(owner.readPaths),
      "ownership row is incomplete"
    );
    assert(!ids.has(owner.ownerId), `duplicate ownership owner ${owner.ownerId}`);
    ids.add(owner.ownerId);
    for (const path of owner.writePaths) {
      const normalized = path.replace(/\/\*\*$/, "").replace(/\/$/, "");
      assert(normalized && !normalized.startsWith("/"), `ownership path must be repository-relative: ${path}`);
      writerPaths.push({ owner: owner.ownerId, repository: owner.repository, path: normalized });
    }
  }
  for (const left of writerPaths)
    for (const right of writerPaths) {
      if (left === right || left.owner === right.owner || left.repository !== right.repository) continue;
      const overlap =
        left.path === right.path || left.path.startsWith(`${right.path}/`) || right.path.startsWith(`${left.path}/`);
      assert(
        !overlap,
        `overlapping writer paths: ${left.owner}:${left.repository}/${left.path} and ${right.owner}:${right.repository}/${right.path}`
      );
    }
  for (const required of [
    "plane-control-plane-owner",
    "plane-domain-owner",
    "plane-gateway-owner",
    "plane-catalog-owner",
    "hermes-runtime-owner",
    "mcp-fork-owner",
    "sdk-fork-owner",
    "shared-contracts-owner",
    "integration-lock-writer",
    "root-integrator",
    "sol-reviewer",
  ]) {
    assert(ids.has(required), `ownership map is missing ${required}`);
  }
}

function checkIntegrationLock(lock, lockSchema, readiness, readinessSchema) {
  const lockErrors = validateSchema(lockSchema, lock);
  assert(lockErrors.length === 0, `integration lock schema validation failed: ${lockErrors.join("; ")}`);
  const readinessErrors = validateSchema(readinessSchema, readiness);
  assert(readinessErrors.length === 0, `G0 readiness schema validation failed: ${readinessErrors.join("; ")}`);
  assert(lock.status === "candidate-for-approval", "integration lock must remain candidate-for-approval");
  assert(
    lock.owners.writer === "integration-lock-writer" &&
      lock.owners.integrator === "root-integrator" &&
      lock.owners.reviewer === "sol-reviewer",
    "integration lock owner roles are incomplete"
  );
  assert(
    lock.pendingInputs.length >= 1 &&
      lock.pendingInputs.every((item) => item.state === "pending" && item.dependentGate),
    "pending P1 inputs must name their dependent gate"
  );
  assert(readiness.clauses.length === 9, "G0 readiness record must contain all nine clauses");
  assert(
    readiness.clauses.every((clause) => clause.reviewerRole === "sol-reviewer"),
    "every G0 clause must name Sol as reviewer"
  );
}

function checkRetiredNames() {
  const retired = [
    "plane_docs",
    "plane_search",
    "plane_execute",
    "plane_search_work_items",
    "plane_get_work_item",
    "plane_create_work_item",
    "plane_update_work_item",
    "plane_add_comment",
  ];
  const forbidden = [
    paths.prompt,
    paths.fixture,
    paths.predicates,
    paths.fixtureSchema,
    paths.predicateSchema,
    paths.plan,
    paths.overview,
    "RELEASE-MANIFEST.md",
    "VERIFICATION-MANIFEST.md",
    paths.lock,
    paths.readiness,
    paths.ownershipMap,
  ];
  for (const path of forbidden) {
    const source = read(path);
    for (const name of retired) assert(!source.includes(name), `${path} still authorizes retired name ${name}`);
  }
  const manifest = read(paths.manifest);
  for (const name of ["plane_docs", "plane_search", "plane_execute"]) {
    const occurrences = [...manifest.matchAll(new RegExp(`(?<![A-Za-z0-9_])${name}(?![A-Za-z0-9_])`, "g"))];
    assert(
      occurrences.every((match) =>
        /retired|never|not|rejected/i.test(manifest.slice(Math.max(0, match.index - 100), match.index + 100))
      ),
      `${name} appears outside an explicit retired-name negative control`
    );
  }
  assert(
    read(paths.prompt).includes("search_workspace") && read(paths.prompt).includes("compose_typescript"),
    "planning prompt does not use approved names"
  );
  const predicateSet = readJson(paths.predicates);
  const required =
    predicateSet.common.find((predicate) => predicate.id === "PLAN-COMMON-007")?.expected?.required ?? [];
  assert(
    JSON.stringify(required) ===
      JSON.stringify([
        "search_workspace",
        "search_catalog",
        "describe_operation",
        "compose_typescript",
        "search_work_items",
        "get_work_item",
        "create_work_item",
        "update_work_item",
        "create_comment",
      ]),
    "planning predicate surface is not the approved set"
  );
}

function checkGeneratedOverview() {
  const result = runCommand("node", ["docs/agent-tooling/verifiers/render-non-ui-implementation-plan.mjs", "--check"]);
  assert(result.status === 0, `generated overview check failed: ${(result.stdout + result.stderr).trim()}`);
}

function checkPlanningArtifacts(lock) {
  const fixture = readJson(paths.fixture);
  const predicates = readJson(paths.predicates);
  const fixtureSchema = readJson(paths.fixtureSchema);
  const predicateSchema = readJson(paths.predicateSchema);
  assert(
    fixture.schema === "plane.agent.fixture-set/v1" && fixture.fixtures?.length === 10,
    "planning fixture set is not the expected v1 ten-fixture set"
  );
  assert(
    predicates.schema === "plane.agent.predicate-set/v1" &&
      predicates.scenario_overrides &&
      Object.keys(predicates.scenario_overrides).length === 10,
    "planning predicate set is not the expected v1 ten-scenario set"
  );
  assert(fixtureSchema.properties?.schema?.const === "plane.agent.fixture-set/v1", "fixture schema is not v1");
  assert(predicateSchema.properties?.schema?.const === "plane.agent.predicate-set/v1", "predicate schema is not v1");
  assert(
    lock.digests.fixtureBundle ===
      bundleDigest([
        paths.fixture,
        paths.fixtureSchema,
        paths.predicates,
        paths.predicateSchema,
        paths.prompt,
        paths.planningValidator,
      ]),
    "fixture bundle digest is stale"
  );
  assert(
    lock.digests.planBundle === bundleDigest([paths.plan, paths.overview]),
    "generated plan bundle digest is stale"
  );
  assert(
    lock.digests.catalogBundle ===
      bundleDigest([
        "RELEASE-MANIFEST.md",
        "PILOT-CONTRACTS.md",
        "GATEWAY-WIRE.md",
        "INTERFACE-DESIGN.md",
        "RUNTIME-DESIGN.md",
      ]),
    "catalog bundle digest is stale"
  );
  assert(
    !read(paths.prompt).match(
      /plane_(?:docs|search|execute|search_work_items|get_work_item|create_work_item|update_work_item|add_comment)/
    ),
    "planning prompt contains retired names"
  );
}

const lock = readJson(paths.lock);
const readiness = readJson(paths.readiness);
const lockSchema = readJson(paths.lockSchema);
const readinessSchema = readJson(paths.readinessSchema);

check("local Markdown links, anchors, and absolute paths", checkMarkdownLinks);
check("ADR 0008/0009/0010 and register consistency", checkAdrRegister);
check("manifest status and bound digest", () => checkManifestAndDigests(lock, readiness));
check("source, repository pins, and inventory digest", () => checkSourceAndRepositoryPins(lock));
check("ownership-map schema and writer overlap", checkOwnershipMap);
check("integration-lock and readiness schema/instance consistency", () =>
  checkIntegrationLock(lock, lockSchema, readiness, readinessSchema)
);
check("retired-name negative control", checkRetiredNames);
check("generated overview current", checkGeneratedOverview);
check("planning fixtures and predicates current", () => checkPlanningArtifacts(lock));
check("G0 record completeness", () => {
  assert(readiness.status === "pending-human-approval", "G0 readiness record must remain pending-human-approval");
  assert(
    readiness.clauses.every((clause) => clause.status !== "pending" || clause.id === "G0-HUMAN-APPROVAL"),
    "only human approval may remain pending"
  );
});
check(
  "human approval",
  () => {
    assert(
      readiness.approval.status === "approved",
      "approval pending: record the exact manifest statement before implementation"
    );
  },
  { approvalOnly: true }
);

for (const result of results)
  console.log(
    `${result.status === "pass" ? "PASS" : result.status === "pending" ? "PENDING" : "FAIL"} ${result.name}${result.message ? ` — ${result.message}` : ""}`
  );

if (mode === "preflight") {
  if (failures.length > 0) {
    console.error(`G0 preflight failed with ${failures.length} non-approval failure(s).`);
    process.exit(1);
  }
  console.log("G0 preflight passed; human approval remains pending by design.");
  process.exit(0);
}

const nonApprovalFailures = results.filter((result) => result.status === "fail");
if (nonApprovalFailures.length > 0) {
  console.error(`G0 verification failed with ${nonApprovalFailures.length} non-approval failure(s).`);
  process.exit(1);
}
console.error(
  "G0 verification failed specifically because human approval is pending; no implementation authorization is implied."
);
process.exit(1);

#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const verifierPath = fileURLToPath(import.meta.url);
const root = resolve(dirname(verifierPath), "..");
const repositoryRoot = resolve(root, "../..");
const modeIndex = process.argv.indexOf("--mode");
const mode = modeIndex === -1 ? "g0" : process.argv[modeIndex + 1];
const negativeControlMode = process.argv.includes("--negative-control");
const negativeMarker = resolve(repositoryRoot, ".g0-negative-control");
if (!new Set(["preflight", "g0"]).has(mode)) {
  console.error("usage: verify-g0-preflight.mjs --mode preflight|g0");
  process.exit(2);
}

const failures = [];
const results = [];
const expectedApprovalStatement =
  "I approve `APPROVAL-MANIFEST.md` as the controlling Plane Agent Tooling V1 scope and authorize implementation to begin. I understand that pilot and production remain separately gated.";
const paths = {
  manifest: "docs/agent-tooling/APPROVAL-MANIFEST.md",
  sourceInventory: "docs/agent-tooling/SOURCE-INVENTORY.md",
  ownershipMap: "docs/agent-tooling/ownership-map.json",
  ownershipSchema: "docs/agent-tooling/ownership-map.schema.json",
  lockSchema: "docs/agent-tooling/integration-lock.schema.json",
  lock: "docs/agent-tooling/integration-lock.g0.json",
  readinessSchema: "docs/agent-tooling/g0-readiness.schema.json",
  readiness: "docs/agent-tooling/g0-readiness.json",
  modelSurfaceSchema: "docs/agent-tooling/model-facing-surface.schema.json",
  modelSurface: "docs/agent-tooling/model-facing-surface.json",
  plan: "docs/agent-tooling/NON-UI-IMPLEMENTATION-PLAN.json",
  overview: "docs/agent-tooling/NON-UI-IMPLEMENTATION-OVERVIEW.md",
  result: "docs/agent-tooling/RESULT.md",
  fixture: "docs/agent-tooling/fixtures/planning-v1.json",
  fixtureSchema: "docs/agent-tooling/fixtures/planning-v1.schema.json",
  predicates: "docs/agent-tooling/fixtures/planning-v1.predicates.json",
  predicateSchema: "docs/agent-tooling/fixtures/planning-v1.predicates.schema.json",
  prompt: "docs/agent-tooling/prompts/release-planning-v1.md",
  planningValidator: "docs/agent-tooling/verifiers/validate-planning-fixtures.mjs",
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
  "RESULT.md",
  "EVALUATION-FIXTURE-CONTRACT.md",
  "EVALUATION-SCENARIOS.md",
  "MCP-COMPATIBILITY.md",
  "MCP-MAPPING-CONTRACT.md",
  "SAFETY-EVALUATION-DESIGN.md",
  "ADR-SYNTHESIS.md",
  "NON-UI-IMPLEMENTATION-OVERVIEW.md",
  "inventories/plane-mcp-v0.2.11-dispositions.md",
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
];

// Structured authority is explicit and fail-closed. The model-facing surface
// is authoritative by default under each named operation; only these exact
// JSON-pointer contexts are metadata or historical registries. Other
// structured artifacts are evidence/configuration, except for the exact
// predicate field that mirrors the model-facing name set.
const structuredRetiredNamePolicies = {
  [paths.modelSurface]: {
    default: "unclassified",
    authoritative: [
      ["g0ContractPolicy", "*"],
      ["names", "*", "*"],
    ],
    nonModelFacing: [
      ["$schema"],
      ["schemaVersion"],
      ["surfaceId"],
      ["status"],
      ["names", "*", "operationId"],
      ["retiredNames", "*"],
      ["retiredNames", "*", "*"],
    ],
  },
  [paths.predicates]: {
    default: "non-model-facing",
    authoritative: [["common", "*", "expected", "required", "*"]],
    nonModelFacing: [],
  },
  [paths.fixture]: { default: "non-model-facing", authoritative: [], nonModelFacing: [] },
  [paths.plan]: { default: "non-model-facing", authoritative: [], nonModelFacing: [] },
  [paths.lock]: { default: "non-model-facing", authoritative: [], nonModelFacing: [] },
  [paths.readiness]: { default: "non-model-facing", authoritative: [], nonModelFacing: [] },
  [paths.ownershipMap]: { default: "non-model-facing", authoritative: [], nonModelFacing: [] },
};

function absolute(relativePath) {
  return relativePath.startsWith("docs/") ? resolve(repositoryRoot, relativePath) : resolve(root, relativePath);
}

function read(relativePath) {
  return readFileSync(absolute(relativePath), "utf8");
}

function readBytes(relativePath) {
  return readFileSync(absolute(relativePath));
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

function git(cwd, args, { allowFailure = false } = {}) {
  const result = spawnSync("git", ["-C", cwd, ...args], { encoding: "utf8" });
  if (!allowFailure && result.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`);
  }
  return { status: result.status ?? 1, stdout: result.stdout.trim(), stderr: result.stderr.trim() };
}

function runCommand(program, args) {
  const result = spawnSync(program, args, { cwd: repositoryRoot, encoding: "utf8" });
  return { status: result.status ?? 1, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function gitShow(commit, path) {
  const result = spawnSync("git", ["-C", repositoryRoot, "show", `${commit}:${path}`], { encoding: "buffer" });
  assert(result.status === 0, `git show cannot read ${commit}:${path}`);
  return result.stdout;
}

function fileDigest(relativePath) {
  return sha256(readBytes(relativePath));
}

function validateWithAjv(schemaPath, valuePath, label) {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const validate = ajv.compile(readJson(schemaPath));
  const valid = validate(readJson(valuePath));
  assert(valid, `${label} failed AJV 2020 validation: ${JSON.stringify(validate.errors)}`);
}

function checkMarkdownLinks() {
  const headingCache = new Map();
  function anchorsFor(path) {
    if (headingCache.has(path)) return headingCache.get(path);
    const source = read(path);
    const anchors = new Set();
    const counts = new Map();
    for (const line of source.split("\n")) {
      const heading = line.match(/^#{1,6}\s+(.+?)\s*#*$/);
      if (!heading) continue;
      const text = heading[1].replaceAll(/[`*_~]/g, "").replaceAll(/<[^>]+>/g, "");
      const base = text
        .toLowerCase()
        .trim()
        .replaceAll(/[^\p{Letter}\p{Number} -]/gu, "")
        .replaceAll(/\s+/g, "-");
      const count = counts.get(base) ?? 0;
      counts.set(base, count + 1);
      anchors.add(count === 0 ? base : `${base}-${count}`);
    }
    for (const match of source.matchAll(/<(?:a|span)[^>]+(?:id|name)=["']([^"']+)["'][^>]*>/gi)) anchors.add(match[1]);
    headingCache.set(path, anchors);
    return anchors;
  }
  for (const path of canonicalMarkdown) {
    const file = absolute(`docs/agent-tooling/${path}`);
    assert(existsSync(file), `canonical Markdown file is missing: ${path}`);
    const source = read(`docs/agent-tooling/${path}`);
    for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const raw = match[1].trim().split(/\s+/)[0].replace(/^<|>$/g, "");
      if (!raw || /^(?:https?:|mailto:|#?\/\/)/i.test(raw)) continue;
      const [targetPart, anchor] = raw.split("#", 2);
      const target = targetPart ? decodeURIComponent(targetPart) : `docs/agent-tooling/${path}`;
      const targetPath = isAbsolute(target) ? target : resolve(dirname(file), target);
      assert(existsSync(targetPath), `${path} links to missing ${raw}`);
      if (anchor) {
        const targetRelative = relative(root, targetPath);
        assert(anchorsFor(targetRelative).has(decodeURIComponent(anchor)), `${path} links to missing anchor ${raw}`);
      }
    }
  }
  for (const path of canonicalMarkdown) {
    for (const match of read(`docs/agent-tooling/${path}`).matchAll(/\/(?:Users|private\/tmp)\/[A-Za-z0-9_./-]+/g)) {
      const candidate = match[0].replace(/[.,;:]+$/, "");
      throw new Error(`${path} contains a non-portable absolute path ${candidate}`);
    }
  }
}

function checkAdrRegister() {
  for (const name of [
    "0001-plane-agent-tooling-architecture.md",
    "0002-autonomous-agent-operations.md",
    "0003-plane-agent-native-product-boundary.md",
    "0004-fork-hermes-as-hidden-execution-kernel.md",
    "0005-plane-owned-agent-profiles.md",
    "0006-assignment-and-run-lifecycle.md",
    "0007-adaptive-plane-tool-exposure.md",
    "0008-scoped-memory-and-context.md",
    "0009-workflows-and-agent-delegation.md",
    "0010-plane-runtime-contract.md",
  ])
    assert(/^Accepted(?:$|;)/m.test(read(`../decisions/${name}`)), `${name} is not Accepted`);
  const register = read("decision-register.md");
  assert(/\| ATD-143 \|/.test(register), "decision register does not contain ATD-143");
  assert(
    /ADR-0008, ADR-0009, and ADR-0010 are accepted/.test(register),
    "register does not bind ATD-143 to the three ADRs"
  );
  assert(
    /\| ATO-020 \|/.test(register) && /\| ATO-018 \|/.test(register) && /\| ATO-014 \|/.test(register),
    "later-lane decisions are not retained as open"
  );
}

function checkAuthorityAndContractPolicy() {
  const manifest = read(paths.manifest);
  assert(manifest.includes("sole G0 human approval authority"), "manifest does not declare the sole G0 authority");
  assert(
    manifest.includes("G1 freezes generated operation/event schemas"),
    "manifest does not demote schema freezing to G1"
  );
  assert(
    manifest.includes("Physical queue/RPC transport remains a later"),
    "manifest does not preserve the later physical transport choice"
  );
  for (const path of [
    "PILOT-CONTRACTS.md",
    "RELEASE-MANIFEST.md",
    "VERIFICATION-MANIFEST.md",
    "EVALUATION-FIXTURE-CONTRACT.md",
    "REQUIREMENT-COVERAGE.md",
  ]) {
    const source = read(`docs/agent-tooling/${path}`);
    assert(
      /cannot approve|not an approval|single G0 human approval|evidence input/i.test(source),
      `${path} lacks an explicit demotion to evidence/input status`
    );
  }
  const plan = readJson(paths.plan);
  const gate = plan.gates.find((candidate) => candidate.id === "G0");
  assert(
    gate?.exit.some((line) => /generated operation\/event schemas are a G1 input/i.test(line)),
    "G0 still freezes generated schemas"
  );
  assert(
    gate?.exit.some((line) => /physical.*queue\/RPC.*implementation-defined under ADR-0010/i.test(line)),
    "G0 does not preserve the later physical transport choice"
  );
  assert(
    !read(paths.overview).includes("Freeze the pilot operation catalog, model-facing presentation, runtime transport"),
    "generated overview still freezes physical runtime transport at G0"
  );
}

function checkAcceptedAdrSchemaAuthority() {
  for (const path of canonicalMarkdown.filter((candidate) => candidate.startsWith("../decisions/"))) {
    const source = read(`docs/agent-tooling/${path}`)
      .replaceAll(/<!--.*?-->/gs, " ")
      .replaceAll(/\s+/g, " ");
    const mentionsSchemas =
      /\b(?:generated|exact|JSON|snapshot|envelope|runtime event)[^.!?]{0,160}\bschemas?\b|\bschemas?\b[^.!?]{0,160}\b(?:generated|exact|JSON|snapshot|envelope|runtime event)\b/i.test(
        source
      );
    const mentionsImplementationPrerequisite =
      /\b(?:before|prior to|precede|preceding)\b[^.!?]{0,160}\b(?:implementation|implementing|AIAgent adaptation|runtime lane|application lane|verification lane)\b/i.test(
        source
      );
    if (mentionsSchemas && mentionsImplementationPrerequisite) {
      assert(
        /\bG1\b[^.!?]{0,180}\b(?:generate|freeze|schema|consumer|lane)|\b(?:consumer|lane)[^.!?]{0,180}\bG1\b/i.test(
          source
        ),
        `${path} retains a generated-schema prerequisite before implementation without the G1 consumer-lane boundary`
      );
    }
  }
  const runtimeAdr = read("../decisions/0010-plane-runtime-contract.md");
  assert(
    /G0[\s\S]{0,500}logical type names[\s\S]{0,500}G1[\s\S]{0,500}exact JSON Schema bytes/i.test(runtimeAdr),
    "ADR-0010 does not state the G0 logical-contract and G1 generated-schema authority boundary"
  );
  assert(
    /implementation lanes that consume those generated schemas/i.test(runtimeAdr),
    "ADR-0010 does not bind generated schema freezing to the lanes that consume it"
  );
}

function checkManifestAndDigests(lock, readiness) {
  const manifest = read(paths.manifest);
  const statusLine = manifest.split("\n").find((line) => line.startsWith("**")) ?? "";
  assert(statusLine.includes("Ready for approval"), "manifest is not in Ready for approval status");
  assert(!statusLine.includes("Approved"), "manifest status must not claim Approved");
  assert(!manifest.includes("STATUS_APPROVED"), "manifest contains a fake approval marker");
  assert(readiness.approval.statement === expectedApprovalStatement, "G0 approval statement changed");
  assert(
    readiness.approval.manifestDigest === lock.digests.files[paths.manifest],
    "readiness manifest digest differs from lock"
  );
  assert(
    readiness.evidenceDigests.files &&
      JSON.stringify(readiness.evidenceDigests.files) === JSON.stringify(lock.digests.files),
    "readiness and lock evidence maps are not byte-for-byte equal"
  );
}

function checkSourceAndRepositoryPins(lock) {
  const inventory = read(paths.sourceInventory);
  assert(!/\/Users\/|\/private\/tmp\//.test(inventory), "source inventory contains an absolute or ephemeral path");
  const contentCommit = lock.seal.contentCommit;
  const plane = lock.repositories.find((repository) => repository.id === "plane");
  assert(plane?.sha === contentCommit, "Plane repository SHA must equal sealed contentCommit");
  for (const repository of lock.repositories)
    assert(inventory.includes(repository.sha), `source inventory does not contain ${repository.id} SHA`);
  const ancestry = git(repositoryRoot, ["merge-base", "--is-ancestor", lock.reviewedBaseline.planeSha, contentCommit], {
    allowFailure: true,
  });
  assert(ancestry.status === 0, "reviewed Plane baseline is not an ancestor of sealed contentCommit");
  assert(
    git(root, ["remote", "get-url", "upstream"]).stdout === plane.remote,
    "Plane upstream remote differs from integration lock"
  );
  const status = git(repositoryRoot, ["status", "--porcelain", "--untracked-files=all"]).stdout;
  const permittedDirty =
    negativeControlMode && repositoryRoot.startsWith(resolve(tmpdir())) && existsSync(negativeMarker);
  if (!permittedDirty) assert(status === "", "authoritative Plane checkout must be clean");
  for (const [path, repositoryId] of Object.entries({
    "external/plane-mcp-server": "plane-mcp",
    "external/plane-python-sdk": "plane-sdk",
  })) {
    const pinned = git(repositoryRoot, ["ls-tree", contentCommit, path]).stdout.split(/\s+/)[2];
    const expected = lock.repositories.find((repository) => repository.id === repositoryId)?.sha;
    assert(pinned === expected, `${path} gitlink differs from integration lock`);
  }
}

function changedPaths(commit) {
  return git(repositoryRoot, ["diff-tree", "--no-commit-id", "--name-status", "-r", commit])
    .stdout.split("\n")
    .filter(Boolean)
    .map((line) => line.split("\t"));
}

function checkSeal(lock, readiness) {
  const head = git(repositoryRoot, ["rev-parse", "HEAD"]).stdout;
  const contentCommit = lock.seal.contentCommit;
  assert(contentCommit !== "0".repeat(40), "seal contentCommit is unpopulated");
  assert(
    git(repositoryRoot, ["rev-parse", `${contentCommit}^{tree}`]).stdout === lock.seal.contentTree,
    "sealed content tree is stale"
  );
  const headParent = git(repositoryRoot, ["rev-parse", "HEAD^"]).stdout;
  const sealCommit =
    readiness.status === "pending-human-approval" ? head : readiness.approval.evidenceBinding.sealedHead;
  assert(sealCommit && /^[0-9a-f]{40}$/.test(sealCommit), "seal commit is not recorded as a full commit SHA");
  const sealParent = git(repositoryRoot, ["rev-parse", `${sealCommit}^`]).stdout;
  assert(sealParent === contentCommit, "seal commit first parent must equal recorded contentCommit");
  const allowedSealPaths = [...lock.seal.allowedSealPaths].toSorted();
  assert(
    JSON.stringify([...lock.seal.sealEvidencePaths].toSorted()) === JSON.stringify(allowedSealPaths),
    "seal evidence paths must equal the allowed seal paths"
  );
  const sealChanges = changedPaths(sealCommit).toSorted((left, right) =>
    left.join("\0").localeCompare(right.join("\0"))
  );
  const expectedSealChanges = allowedSealPaths
    .map((path) => ["M", path])
    .toSorted((left, right) => left.join("\0").localeCompare(right.join("\0")));
  assert(
    JSON.stringify(sealChanges) === JSON.stringify(expectedSealChanges),
    `seal commit changed paths are not exactly the four allowed seal paths: ${JSON.stringify(sealChanges)}`
  );
  const allowed = new Set(lock.seal.allowedSealPaths);
  for (const path of lock.seal.contentPaths) {
    assert(!allowed.has(path), `content path is also an allowed seal path: ${path}`);
    assert(lock.digests.files[path] === fileDigest(path), `seal-bound digest mismatch for ${path}`);
    assert(
      sha256(gitShow(contentCommit, path)) === lock.digests.files[path],
      `content commit bytes differ for ${path}`
    );
  }
  assert(lock.seal.contentPaths.includes(paths.result), "RESULT.md must be in the normative seal content set");
  const evidencePaths = [...lock.seal.contentPaths, "docs/agent-tooling/SOURCE-INVENTORY.md"].toSorted();
  assert(
    JSON.stringify(Object.keys(lock.digests.files).toSorted()) === JSON.stringify(evidencePaths),
    "lock does not bind exactly the declared normative files"
  );
  assert(
    lock.digests.files[paths.sourceInventory] === fileDigest(paths.sourceInventory),
    "source inventory digest is stale"
  );
  const baseline = gitShow(lock.seal.worklogBaseline.commit, "docs/agent-tooling/WORKLOG.md");
  const worklog = readBytes("docs/agent-tooling/WORKLOG.md");
  assert(worklog.length > baseline.length, "WORKLOG has no appended remediation evidence");
  assert(
    lock.seal.worklogBaseline.byteLength === baseline.length && lock.seal.worklogBaseline.sha256 === sha256(baseline),
    "WORKLOG baseline seal is stale"
  );
  assert(
    sha256(worklog.subarray(0, baseline.length)) === lock.seal.worklogBaseline.sha256,
    "WORKLOG pre-existing prefix was modified"
  );
  if (readiness.status !== "pending-human-approval") {
    const sealedHead = readiness.approval.evidenceBinding.sealedHead;
    assert(
      sealCommit === sealedHead && headParent === sealedHead,
      "approved state must be an explicit readiness-only transition from the sealed head"
    );
    assert(
      git(repositoryRoot, ["rev-parse", `${sealedHead}^`]).stdout === contentCommit,
      "approved state is not based on the sealed content commit"
    );
    const parentLock = JSON.parse(gitShow(sealedHead, paths.lock));
    assert(parentLock.seal.contentCommit === contentCommit, "approved state parent does not carry the same seal");
    const approvalChanges = changedPaths(head);
    assert(
      JSON.stringify(approvalChanges) === JSON.stringify([["M", paths.readiness]]),
      "approved transition changed more than g0-readiness.json"
    );
  }
}

function checkOwnershipAndSchemas(lock, readiness) {
  for (const [schema, instance, label] of [
    [paths.lockSchema, paths.lock, "integration lock"],
    [paths.readinessSchema, paths.readiness, "G0 readiness"],
    [paths.ownershipSchema, paths.ownershipMap, "ownership map"],
    [paths.modelSurfaceSchema, paths.modelSurface, "model-facing surface"],
    [paths.fixtureSchema, paths.fixture, "planning fixtures"],
    [paths.predicateSchema, paths.predicates, "planning predicates"],
  ])
    validateWithAjv(schema, instance, label);
  assert(lock.status === "candidate-for-approval", "integration lock cannot be approved independently");
  assert(
    lock.pendingInputs.every((input) => input.state === "pending" && /^G[1-5]$/.test(input.dependentGate)),
    "future inputs must remain explicit pending slots with a declared gate"
  );
  assert(readiness.clauses.length === 9, "G0 readiness must contain nine clauses");
  assert(
    readiness.clauses.every((clause) => clause.reviewerRole === "sol-reviewer"),
    "every G0 clause must name Sol as reviewer"
  );
  const ownershipResult = runCommand("node", ["docs/agent-tooling/verifiers/validate-ownership-map.mjs"]);
  assert(
    ownershipResult.status === 0,
    `ownership validator failed: ${(ownershipResult.stdout + ownershipResult.stderr).trim()}`
  );
}

function checkModelFacingSurface() {
  const surface = readJson(paths.modelSurface);
  const expected = [
    "search_workspace",
    "search_catalog",
    "describe_operation",
    "compose_typescript",
    "search_work_items",
    "get_work_item",
    "create_work_item",
    "update_work_item",
    "create_comment",
  ];
  assert(
    JSON.stringify(surface.names.map((entry) => entry.name)) === JSON.stringify(expected),
    "model-facing name set is not exact or ordered"
  );
  assert(
    JSON.stringify(surface.names.filter((entry) => entry.kind === "eager-direct").map((entry) => entry.name)) ===
      JSON.stringify(expected.slice(4)),
    "eager direct set is not exact"
  );
  assert(
    surface.names.find((entry) => entry.name === "search_workspace").description.includes("not work-item lookup"),
    "search_workspace is not separated from search_work_items"
  );
  assert(
    surface.names
      .find((entry) => entry.name === "search_work_items")
      .description.includes("does not cover all workspace object types"),
    "search_work_items is not separated from search_workspace"
  );
  assert(
    surface.g0ContractPolicy.generatedSchemaGate === "G1" &&
      surface.g0ContractPolicy.physicalTransportGate.includes("later"),
    "model surface has an invalid G0/G1 policy"
  );
}

function escapeRegExp(value) {
  return value.replaceAll(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function tokenOccurrences(text, name) {
  const token = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(name)}(?![A-Za-z0-9_])`, "g");
  return [...text.matchAll(token)].map((match) => ({ start: match.index, end: match.index + match[0].length }));
}

function rangesForPattern(text, pattern, valueGroup = 0) {
  return [...text.matchAll(pattern)].map((match) => {
    const value =
      valueGroup === 0 ? match[0] : (match.slice(valueGroup).find((candidate) => candidate !== undefined) ?? match[0]);
    const valueOffset = valueGroup === 0 ? 0 : match[0].indexOf(value);
    return { start: match.index + valueOffset, end: match.index + valueOffset + value.length };
  });
}

function isWithinRange(occurrence, ranges) {
  return ranges.some((range) => occurrence.start >= range.start && occurrence.end <= range.end);
}

function historicalOccurrence(line, occurrence, occurrences) {
  const marker =
    /\b(?:retired|historical|negative[- ]control|legacy|supersed(?:ed|es)?|rejected|forbidden|replaced)\b/gi;
  const separators = /[;|.!?\n]/g;
  const separatorPositions = [...line.matchAll(separators)].map((match) => match.index);
  const previousSeparator = separatorPositions.findLast((position) => position < occurrence.start);
  const clauseStart = previousSeparator === undefined ? 0 : previousSeparator + 1;
  const clauseEnd = separatorPositions.find((position) => position >= occurrence.end) ?? line.length;
  const clauseOccurrences = occurrences.filter(
    (candidate) => candidate.start >= clauseStart && candidate.end <= clauseEnd
  );

  for (const match of line.matchAll(marker)) {
    const markerStart = match.index;
    const markerEnd = markerStart + match[0].length;
    if (markerStart < clauseStart || markerEnd > clauseEnd) continue;
    if (markerEnd <= occurrence.start) {
      const firstFollowing = clauseOccurrences.find((candidate) => candidate.start >= markerEnd);
      if (firstFollowing?.start === occurrence.start) return true;
    } else if (markerStart >= occurrence.end) {
      const lastPreceding = clauseOccurrences.findLast((candidate) => candidate.end <= markerStart);
      if (lastPreceding?.start === occurrence.start) return true;
    }
  }
  return false;
}

function designatedInternalIdentifierRanges(line) {
  const ranges = rangesForPattern(
    line,
    /\b(?:operationId|runtime[-_ ]adapter(?:[-_ ](?:identifier|id))?|adapter[-_ ](?:identifier|id))\b\s*[:=]\s*(?:"([^"]+)"|'([^']+)'|`([^`]+)`|([A-Za-z0-9_.@-]+))/gi,
    1
  );
  ranges.push(...rangesForPattern(line, /\bplane_runtime\.[A-Za-z0-9_.-]+/g));
  return ranges;
}

function ordinaryPathRanges(line) {
  return rangesForPattern(line, /\bdocs\/[-A-Za-z0-9_./]+/g);
}

function hasAuthoritativeTextMarker(line) {
  return /\bauthoritative\b|\bmodel[- ]facing\s+(?:name|description|purpose|schema|operation|alias|input|output|error)\b|\b(?:semantic purpose|input note|output note|error note|schema note)\b/i.test(
    line
  );
}

function retiredNameViolation(line, name, { structured = false } = {}) {
  const occurrences = tokenOccurrences(line, name);
  if (occurrences.length === 0 || (!structured && !hasAuthoritativeTextMarker(line))) return false;
  const internalRanges = designatedInternalIdentifierRanges(line);
  const pathRanges = ordinaryPathRanges(line);
  return occurrences.some(
    (occurrence) =>
      !historicalOccurrence(line, occurrence, occurrences) &&
      !isWithinRange(occurrence, internalRanges) &&
      !isWithinRange(occurrence, pathRanges)
  );
}

function pointerMatches(segments, pattern) {
  return segments.length === pattern.length && pattern.every((part, index) => part === "*" || part === segments[index]);
}

function structuredFieldClassification(path, segments) {
  const policy = structuredRetiredNamePolicies[path];
  assert(policy, `no structured retired-name authority policy exists for ${path}`);
  if (policy.nonModelFacing.some((pattern) => pointerMatches(segments, pattern))) return "non-model-facing";
  if (policy.authoritative.some((pattern) => pointerMatches(segments, pattern))) return "authoritative";
  return policy.default;
}

function jsonPointer(segments) {
  return `/${segments.map((segment) => String(segment).replaceAll("~", "~0").replaceAll("/", "~1")).join("/")}`;
}

function checkStructuredRetiredNames(path, value, retired, segments = []) {
  if (typeof value === "string") {
    const classification = structuredFieldClassification(path, segments);
    if (classification === "unclassified")
      throw new Error(`${path} has an unclassified authority pointer ${jsonPointer(segments)}`);
    if (classification !== "authoritative") return;
    for (const name of retired)
      if (retiredNameViolation(value, name, { structured: true }))
        throw new Error(`${path} authoritatively uses retired name ${name} in ${jsonPointer(segments)}`);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => checkStructuredRetiredNames(path, item, retired, [...segments, String(index)]));
    return;
  }
  if (value && typeof value === "object")
    for (const [key, child] of Object.entries(value))
      checkStructuredRetiredNames(path, child, retired, [...segments, key]);
}

function checkRetiredNameControls() {
  const surface = readJson(paths.modelSurface);
  const retired = [...surface.retiredNames.bare, ...surface.retiredNames.historicalPrefixed];
  const controls = retired.flatMap((name) => [
    { name, label: `bare ${name}`, line: `Authoritative model-facing name: ${name}`, rejects: true },
    { name, label: `dotted ${name}`, line: `Authoritative model-facing name: plane.${name}`, rejects: true },
    {
      name,
      label: `historical ${name}`,
      line: `Historical negative-control prose: retired alias ${name}`,
      rejects: false,
    },
    { name, label: `internal ${name}`, line: `operationId: "plane.${name}@1"`, rejects: false },
    {
      name,
      label: `mixed internal and authoritative ${name}`,
      line: `operationId: "plane.${name}@1"; Authoritative model-facing name: ${name}`,
      rejects: true,
    },
    {
      name,
      label: `mixed historical and authoritative ${name}`,
      line: `Rejected historical alias ${name}; Authoritative model-facing name: ${name}`,
      rejects: true,
    },
    {
      name,
      label: `ordinary path and prose ${name}`,
      line: `Implementation note: see docs/agent-tooling/README.md; ordinary prose may ${name}.`,
      rejects: false,
    },
  ]);
  for (const control of controls)
    assert(retiredNameViolation(control.line, control.name) === control.rejects, control.label);

  for (const name of retired) {
    const line = `Rejected ${name} authoritative model-facing name ${name}`;
    const occurrences = tokenOccurrences(line, name);
    assert(occurrences.length === 2, `compact same-clause control must contain two ${name} occurrences`);
    assert(
      historicalOccurrence(line, occurrences[0], occurrences),
      `compact same-clause control did not allow the explicitly rejected ${name} occurrence`
    );
    assert(
      !historicalOccurrence(line, occurrences[1], occurrences),
      `compact same-clause control incorrectly allowed the authoritative ${name} occurrence`
    );
    assert(
      retiredNameViolation(line, name),
      `compact same-clause control did not reject the later authoritative ${name} occurrence`
    );
  }
}

function checkStructuredModelFacingFields() {
  const surface = readJson(paths.modelSurface);
  const expected = surface.names.map((entry) => entry.name);
  assert(new Set(expected).size === expected.length, "model-facing names must be unique");
  assert(
    expected.every((name) => !surface.retiredNames.bare.includes(name)),
    "model-facing names contain a retired bare alias"
  );
  assert(
    expected.every((name) => !surface.retiredNames.historicalPrefixed.includes(name)),
    "model-facing names contain a retired historical alias"
  );
  const predicates = readJson(paths.predicates);
  const required = predicates.common.find((predicate) => predicate.id === "PLAN-COMMON-007")?.expected?.required;
  assert(
    JSON.stringify(required) === JSON.stringify(expected),
    "structured required tool field differs from exact model-facing set"
  );
}

function checkRetiredNames() {
  const surface = readJson(paths.modelSurface);
  const retired = [...surface.retiredNames.bare, ...surface.retiredNames.historicalPrefixed];
  const pathsToCheck = [
    paths.modelSurface,
    paths.prompt,
    paths.fixture,
    paths.predicates,
    paths.plan,
    paths.overview,
    paths.lock,
    paths.readiness,
    paths.ownershipMap,
  ];
  for (const path of pathsToCheck)
    if (path.endsWith(".json")) checkStructuredRetiredNames(path, readJson(path), retired);
    else
      for (const line of read(path).split("\n"))
        for (const name of retired)
          if (retiredNameViolation(line, name)) throw new Error(`${path} authoritatively uses retired name ${name}`);
  const required =
    readJson(paths.predicates).common.find((predicate) => predicate.id === "PLAN-COMMON-007")?.expected?.required ?? [];
  assert(
    JSON.stringify(required) === JSON.stringify(surface.names.map((entry) => entry.name)),
    "planning predicate surface differs from machine-readable exact surface"
  );
  assert(
    read(paths.prompt).includes("search_workspace") && read(paths.prompt).includes("compose_typescript"),
    "planning prompt does not use approved names"
  );
  checkStructuredModelFacingFields();
}

function checkGeneratedArtifacts(lock) {
  for (const [command, label] of [
    [["docs/agent-tooling/verifiers/render-non-ui-implementation-plan.mjs", "--check"], "generated overview"],
    [["docs/agent-tooling/verifiers/render-requirement-coverage.mjs", "--check"], "generated requirement coverage"],
    [["docs/agent-tooling/verifiers/validate-requirement-coverage.mjs"], "requirement coverage"],
    [["docs/agent-tooling/verifiers/validate-planning-fixtures.mjs"], "planning fixtures"],
  ]) {
    const result = runCommand("node", command);
    assert(result.status === 0, `${label} check failed: ${(result.stdout + result.stderr).trim()}`);
  }
  const fixturePaths = [
    paths.fixture,
    paths.fixtureSchema,
    paths.predicates,
    paths.predicateSchema,
    paths.prompt,
    paths.planningValidator,
  ];
  const fixtureBundle = sha256(
    fixturePaths
      .map((path) => `${path}\0${fileDigest(path)}\n`)
      .toSorted()
      .join("")
  );
  assert(lock.digests.files[paths.fixture] === fileDigest(paths.fixture), "fixture digest is not sealed");
  assert(fixtureBundle.length === 64, "fixture bundle digest could not be computed");
}

function checkG0Record() {
  const readiness = readJson(paths.readiness);
  if (mode === "preflight")
    assert(
      readiness.status === "pending-human-approval" && readiness.approval.status === "pending",
      "preflight accepts only a fully ready pending package"
    );
  assert(
    readiness.status === "pending-human-approval" || readiness.status === "approved",
    "G0 readiness status is invalid"
  );
  const expectedClauseStatuses = new Map(
    readiness.status === "pending-human-approval"
      ? [
          ["G0-ADR-STATUS", "ready"],
          ["G0-MANIFEST-STATUS", "ready-pending-approval"],
          ["G0-SEMANTIC-BOUNDARY", "ready"],
          ["G0-RUNTIME-CONTRACT", "ready"],
          ["G0-LIMITS-AUDIT", "ready"],
          ["G0-OWNERSHIP-LOCK", "ready"],
          ["G0-LEGACY-RECONCILIATION", "ready"],
          ["G0-GENERATED-ARTIFACTS", "ready"],
          ["G0-HUMAN-APPROVAL", "pending"],
        ]
      : [
          ["G0-ADR-STATUS", "ready"],
          ["G0-MANIFEST-STATUS", "ready"],
          ["G0-SEMANTIC-BOUNDARY", "ready"],
          ["G0-RUNTIME-CONTRACT", "ready"],
          ["G0-LIMITS-AUDIT", "ready"],
          ["G0-OWNERSHIP-LOCK", "ready"],
          ["G0-LEGACY-RECONCILIATION", "ready"],
          ["G0-GENERATED-ARTIFACTS", "ready"],
          ["G0-HUMAN-APPROVAL", "ready"],
        ]
  );
  assert(
    JSON.stringify(readiness.clauses.map((clause) => clause.id)) === JSON.stringify([...expectedClauseStatuses.keys()]),
    "G0 readiness clause IDs are not the exact ordered set"
  );
  for (const clause of readiness.clauses)
    assert(
      clause.status === expectedClauseStatuses.get(clause.id),
      `${clause.id} has status ${clause.status}; expected ${expectedClauseStatuses.get(clause.id)} for ${readiness.status}`
    );
}

const lock = readJson(paths.lock);
const readiness = readJson(paths.readiness);
check("local Markdown links, anchors, and portable paths", checkMarkdownLinks);
check("accepted ADR 0001 through 0010 and register consistency", checkAdrRegister);
check("single approval authority and G0/G1/G4 policy", checkAuthorityAndContractPolicy);
check("accepted ADR generated-schema authority", checkAcceptedAdrSchemaAuthority);
check("manifest and byte-for-byte evidence bindings", () => checkManifestAndDigests(lock, readiness));
check("source, repository pins, and reviewed-baseline separation", () => checkSourceAndRepositoryPins(lock));
check("AJV 2020 schemas, ownership join, and pending slots", () => checkOwnershipAndSchemas(lock, readiness));
check("exact model-facing surface", checkModelFacingSurface);
check("retired-name negative control", checkRetiredNames);
check("retired-name table controls", checkRetiredNameControls);
check("content/evidence seal and append-only WORKLOG prefix", () => checkSeal(lock, readiness));
check("generated overview, coverage, and planning fixtures", () => checkGeneratedArtifacts(lock));
check("G0 record completeness", checkG0Record);
check(
  "human approval",
  () => {
    if (mode === "preflight") return;
    assert(
      readiness.status === "approved" && readiness.approval.status === "approved",
      "approval pending: record the exact manifest statement before implementation"
    );
    assert(
      readiness.approval.approvedBy.identity && readiness.approval.approvedBy.reference,
      "approved state lacks approver identity/reference"
    );
    assert(
      readiness.approval.approvedAt && readiness.approval.evidenceBinding.contentCommit,
      "approved state lacks timestamp/evidence binding"
    );
    assert(
      readiness.approval.evidenceBinding.contentCommit === lock.seal.contentCommit,
      "approved state content binding differs from lock"
    );
    assert(
      readiness.approval.evidenceBinding.lockDigest === fileDigest(paths.lock),
      "approved state lock binding differs from sealed lock"
    );
  },
  { approvalOnly: mode === "g0" }
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

if (failures.length > 0) {
  console.error(`G0 verification failed with ${failures.length} non-approval failure(s).`);
  process.exit(1);
}
if (readiness.status !== "approved") {
  console.error(
    "G0 verification failed specifically because human approval is pending; no implementation authorization is implied."
  );
  process.exit(1);
}
console.log(
  "G0 verification passed for a valid approved state; this verifier does not itself grant implementation authorization."
);

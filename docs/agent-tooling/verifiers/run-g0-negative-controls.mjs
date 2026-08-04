#!/usr/bin/env node

import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(verifierRoot, "../..");
const readinessRelativePath = "docs/agent-tooling/g0-readiness.json";
const lockRelativePath = "docs/agent-tooling/integration-lock.g0.json";
const resultRelativePath = "docs/agent-tooling/RESULT.md";
const allowedSealPaths = [
  "docs/agent-tooling/SOURCE-INVENTORY.md",
  "docs/agent-tooling/WORKLOG.md",
  readinessRelativePath,
  lockRelativePath,
];
const retiredNames = [
  "docs",
  "search",
  "execute",
  "plane_docs",
  "plane_search",
  "plane_execute",
  "plane_search_work_items",
  "plane_get_work_item",
  "plane_create_work_item",
  "plane_update_work_item",
  "plane_add_comment",
];

function run(cwd, args, options = {}) {
  const result = spawnSync(args[0], args.slice(1), { cwd, encoding: "utf8", ...options });
  if (result.status !== 0) throw new Error(`${args.join(" ")} failed: ${result.stderr || result.stdout}`);
  return result.stdout.trim();
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function append(directory, path, text) {
  const target = join(directory, path);
  writeFileSync(target, `${readFileSync(target, "utf8")}${text}`);
}

function insertAfterHeading(directory, path, heading, text) {
  replace(directory, path, `${heading}\n`, `${heading}\n\n${text}\n`);
}

function replaceManifestModelFacingName(directory, name) {
  const path = "docs/agent-tooling/APPROVAL-MANIFEST.md";
  const source = readFileSync(join(directory, path), "utf8");
  const updated = source.replace(/(\|\s*)`search_catalog`(?=\s*\|)/, `$1\`${name}\``);
  if (updated === source) throw new Error("manifest search_catalog row anchor missing");
  writeFileSync(join(directory, path), updated);
}

function insertModelSurfaceSchemaDescription(directory, name) {
  const path = "docs/agent-tooling/model-facing-surface.schema.json";
  replace(
    directory,
    path,
    '"description": { "type": "string", "minLength": 1 },',
    `"description": { "type": "string", "minLength": 1, "description": "Authoritative model-facing name: ${name}" },`
  );
}

function replace(directory, path, from, to) {
  const target = join(directory, path);
  const source = readFileSync(target, "utf8");
  if (!source.includes(from)) throw new Error(`mutation anchor missing in ${path}`);
  writeFileSync(target, source.replace(from, to));
}

function refreshPromptDigest(directory) {
  const promptPath = join(directory, "docs/agent-tooling/prompts/release-planning-v1.md");
  const promptDigest = sha256(readFileSync(promptPath));
  const validatorPath = join(directory, "docs/agent-tooling/verifiers/validate-planning-fixtures.mjs");
  const validator = readFileSync(validatorPath, "utf8");
  const updatedValidator = validator.replace(/(  prompt: ")[0-9a-f]{64}(",)/, `$1${promptDigest}$2`);
  if (updatedValidator === validator && !validator.includes(`prompt: "${promptDigest}"`))
    throw new Error("prompt digest anchor missing in planning validator");
  if (updatedValidator !== validator) writeFileSync(validatorPath, updatedValidator);
  const validatorDigest = sha256(readFileSync(validatorPath));
  const contractPath = join(directory, "docs/agent-tooling/EVALUATION-FIXTURE-CONTRACT.md");
  const contract = readFileSync(contractPath, "utf8");
  const updatedContractWithPrompt = contract.replace(
    /(\| `prompts\/release-planning-v1\.md`\s+\| `)[0-9a-f]{64}/,
    `$1${promptDigest}`
  );
  const updatedContract = updatedContractWithPrompt.replace(
    /(\| `verifiers\/validate-planning-fixtures\.mjs`\s+\| `)[0-9a-f]{64}/,
    `$1${validatorDigest}`
  );
  if (updatedContract === contract && (!contract.includes(promptDigest) || !contract.includes(validatorDigest)))
    throw new Error("prompt digest anchor missing in fixture contract");
  if (updatedContract !== contract) writeFileSync(contractPath, updatedContract);
}

function commit(directory, message, args = []) {
  run(directory, ["git", "commit", ...args, "-m", message], {
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "g0-negative-control",
      GIT_AUTHOR_EMAIL: "g0-negative-control@example.invalid",
      GIT_COMMITTER_NAME: "g0-negative-control",
      GIT_COMMITTER_EMAIL: "g0-negative-control@example.invalid",
    },
  });
  return run(directory, ["git", "rev-parse", "HEAD"]);
}

function createTemporaryCheckout() {
  const temporaryParent = mkdtempSync(join(tmpdir(), "plane-g0-negative-"));
  const temporaryRoot = join(temporaryParent, "checkout");
  // Keep dependencies outside the checkout so a resealed control is clean
  // when the verifier checks its own clean-worktree invariant.
  symlinkSync(join(repositoryRoot, "node_modules"), join(temporaryParent, "node_modules"), "dir");
  run(repositoryRoot, [
    "git",
    "-c",
    "maintenance.auto=false",
    "-c",
    "gc.auto=0",
    "clone",
    "--local",
    "--no-hardlinks",
    repositoryRoot,
    temporaryRoot,
  ]);
  run(temporaryRoot, ["git", "config", "maintenance.auto", "false"]);
  run(temporaryRoot, ["git", "config", "gc.auto", "0"]);
  run(temporaryRoot, ["git", "remote", "add", "upstream", "https://github.com/uxheavy/plane-runner.git"]);
  return { temporaryParent, temporaryRoot };
}

async function cleanupTemporaryCheckout(temporaryParent, label, remove = rmSync) {
  const backoffMilliseconds = [0, 50, 150, 350, 700];
  async function attemptCleanup(attempt, lastError) {
    try {
      remove(temporaryParent, { recursive: true, force: true });
      if (!existsSync(temporaryParent)) return;
      lastError = new Error("temporary checkout still exists after recursive cleanup");
    } catch (error) {
      lastError = error;
    }
    if (attempt < backoffMilliseconds.length - 1) {
      await new Promise((done) => setTimeout(done, backoffMilliseconds[attempt + 1]));
      return attemptCleanup(attempt + 1, lastError);
    }
    throw new Error(
      `temporary checkout cleanup failed for ${label} after ${backoffMilliseconds.length} attempts: ${
        lastError instanceof Error ? lastError.message : String(lastError)
      }`
    );
  }
  return attemptCleanup(0, undefined);
}

async function runTemporaryCase(testCase, execute) {
  const { temporaryParent, temporaryRoot } = createTemporaryCheckout();
  let assertionError;
  try {
    execute(temporaryRoot);
  } catch (error) {
    assertionError = error;
  }
  let cleanupError;
  try {
    await cleanupTemporaryCheckout(temporaryParent, testCase.name);
  } catch (error) {
    cleanupError = error;
  }
  if (assertionError && cleanupError)
    throw new Error(
      `control assertion failure: ${assertionError instanceof Error ? assertionError.message : String(assertionError)}; ${
        cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
      }`
    );
  if (assertionError) throw assertionError;
  if (cleanupError) throw cleanupError;
}

function createApprovedChain(directory) {
  const readinessPath = join(directory, readinessRelativePath);
  const lockPath = join(directory, lockRelativePath);
  const readiness = JSON.parse(readFileSync(readinessPath, "utf8"));
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const sealedHead = run(directory, ["git", "rev-parse", "HEAD"]);
  if (run(directory, ["git", "rev-parse", `${sealedHead}^`]) !== lock.seal.contentCommit)
    throw new Error("approved negative control base is not content commit -> evidence seal");
  readiness.status = "approved";
  readiness.approval.status = "approved";
  for (const clause of readiness.clauses) clause.status = "ready";
  readiness.approval.approvedBy = {
    identity: "negative-control",
    reference: "docs/agent-tooling/verifiers/run-g0-negative-controls.mjs",
  };
  readiness.approval.approvedAt = "2026-08-04T00:00:00Z";
  readiness.approval.evidenceBinding = {
    contentCommit: lock.seal.contentCommit,
    sealedHead,
    lockDigest: sha256(readFileSync(lockPath)),
  };
  writeFileSync(readinessPath, `${JSON.stringify(readiness, null, 2)}\n`);
  run(directory, ["git", "add", readinessRelativePath]);
  const approvalCommit = commit(directory, "negative-control-approved-state");
  writeFileSync(join(directory, ".g0-negative-control"), "approved-state negative control\n");
  return { approvalCommit, sealedHead };
}

function createAdversarialApprovedSeal(directory) {
  const contentCommit = run(directory, ["git", "rev-parse", "HEAD^"]);
  run(directory, ["git", "reset", "--hard", contentCommit]);
  for (const path of allowedSealPaths) copyFileSync(join(repositoryRoot, path), join(directory, path));
  append(directory, resultRelativePath, "\nAdversarial semantic mutation hidden in the evidence-seal commit.\n");
  run(directory, ["git", "add", ...allowedSealPaths, resultRelativePath]);
  commit(directory, "negative-control-adversarial-seal");
  return createApprovedChain(directory);
}

const cases = [
  {
    name: "retired-name table controls",
    mutate: () => {},
    expected: "PASS retired-name table controls",
    expectSuccess: true,
    allowDirty: false,
  },
];

for (const name of retiredNames) {
  cases.push({
    name: `authoritative bare ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nAuthoritative model-facing name: ${name}\n`
      ),
    expected: `authoritatively uses retired name ${name}`,
  });
  cases.push({
    name: `authoritative dotted ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nAuthoritative model-facing name: plane.${name}\n`
      ),
    expected: `authoritatively uses retired name ${name}`,
  });
}

cases.push(
  {
    name: "changed operation schema/name",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/model-facing-surface.json",
        '"name": "search_workspace"',
        '"name": "search_workspace_changed"'
      ),
    expected: "model-facing name set is not exact",
  },
  {
    name: "changed GOAL",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/GOAL.md",
        "Full Plane integration/action coverage is a completion requirement.",
        "Changed GOAL evidence."
      ),
    expected: "seal-bound digest mismatch for docs/agent-tooling/GOAL.md",
  },
  {
    name: "changed accepted ADR",
    mutate: (directory) =>
      replace(directory, "docs/decisions/0010-plane-runtime-contract.md", "# ADR-0010", "# ADR-0010 mutated"),
    expected: "seal-bound digest mismatch for docs/decisions/0010-plane-runtime-contract.md",
  },
  {
    name: "changed verifier",
    mutate: (directory) =>
      append(directory, "docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "\n// negative-control mutation\n"),
    expected: "seal-bound digest mismatch for docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
  },
  {
    name: "changed ownership",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/ownership-map.json",
        '"planLaneIds": ["L2", "L6", "L7"]',
        '"planLaneIds": ["L2", "L6", "L99"]'
      ),
    expected: "ownership map failed AJV",
  },
  {
    name: "RESULT mutation in pending chain",
    mutate: (directory) => append(directory, resultRelativePath, "\nPending semantic mutation.\n"),
    expected: `seal-bound digest mismatch for ${resultRelativePath}`,
  },
  {
    name: "dirty tracked package",
    mutate: (directory) => append(directory, "docs/agent-tooling/README.md", "\nDirty tracked mutation.\n"),
    expected: "authoritative Plane checkout must be clean",
    allowDirty: false,
  },
  {
    name: "extra semantic file in approved seal",
    mutate: (directory) => createAdversarialApprovedSeal(directory),
    expected: "seal commit changed paths are not exactly the four allowed seal paths",
  },
  {
    name: "approved record retains G0-HUMAN-APPROVAL pending",
    mutate: (directory) => {
      createApprovedChain(directory);
      const path = join(directory, readinessRelativePath);
      const readiness = JSON.parse(readFileSync(path, "utf8"));
      readiness.clauses.find((clause) => clause.id === "G0-HUMAN-APPROVAL").status = "pending";
      writeFileSync(path, `${JSON.stringify(readiness, null, 2)}\n`);
    },
    expected: "/clauses/8/status",
  },
  {
    name: "approved record retains G0-MANIFEST-STATUS pending",
    mutate: (directory) => {
      createApprovedChain(directory);
      const path = join(directory, readinessRelativePath);
      const readiness = JSON.parse(readFileSync(path, "utf8"));
      readiness.clauses.find((clause) => clause.id === "G0-MANIFEST-STATUS").status = "ready-pending-approval";
      writeFileSync(path, `${JSON.stringify(readiness, null, 2)}\n`);
    },
    expected: "/clauses/1/status",
  },
  {
    name: "RESULT mutation in approved chain",
    mutate: (directory) => {
      createApprovedChain(directory);
      append(directory, resultRelativePath, "\nApproved-chain semantic mutation.\n");
    },
    expected: `seal-bound digest mismatch for ${resultRelativePath}`,
  },
  {
    name: "later unsealed commit after pending seal",
    mutate: (directory) => commit(directory, "negative-control-extra-post-seal-commit", ["--allow-empty"]),
    expected: "seal commit first parent must equal recorded contentCommit",
    allowDirty: false,
  },
  {
    name: "later unsealed commit after approved transition",
    mutate: (directory) => {
      createApprovedChain(directory);
      commit(directory, "negative-control-extra-post-approval-commit", ["--allow-empty"]);
    },
    expected: "approved state must be an explicit readiness-only transition from the sealed head",
    allowDirty: false,
  }
);

const resealedAdversarialCases = [];
for (const name of retiredNames) {
  resealedAdversarialCases.push({
    name: `valid-reseal ambiguous marker between identical occurrences ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\n${name} rejected ${name} authoritative model-facing name\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
  resealedAdversarialCases.push({
    name: `valid-reseal compact same-clause historical and authoritative ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nRejected ${name} authoritative model-facing name ${name}\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
  resealedAdversarialCases.push({
    name: `valid-reseal authoritative model-facing description ${name}`,
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/model-facing-surface.json",
        '"description": "Create one sanitized source-linked comment under current Plane authorization."',
        `"description": "Invoke ${name} as an authoritative model-facing operation."`
      ),
    expected: `docs/agent-tooling/model-facing-surface.json authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
  resealedAdversarialCases.push({
    name: `valid-reseal authoritative semantic note ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nAuthoritative semantic purpose/schema note: this control rejects ${name}.\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
  resealedAdversarialCases.push({
    name: `valid-reseal mixed internal and authoritative ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\noperationId: "plane.${name}@1"; Authoritative model-facing name: ${name}\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
  resealedAdversarialCases.push({
    name: `valid-reseal mixed historical and authoritative ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nRejected historical alias ${name}; separate authoritative model-facing name: ${name}\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${name}`,
    reseal: true,
    refreshPromptDigest: true,
  });
}

const resealedPositiveCases = retiredNames.map((name) => ({
  name: `valid-reseal two corresponding marker directions ${name}`,
  mutate: (directory) =>
    append(
      directory,
      "docs/agent-tooling/prompts/release-planning-v1.md",
      `\nRejected ${name}; ${name} was historical\n`
    ),
  expected: "PASS retired-name negative control",
  expectSuccess: true,
  reseal: true,
  refreshPromptDigest: true,
}));

const existingResealedPositiveCases = [
  {
    name: "valid-reseal clearly marked historical occurrence",
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        "\nHistorical negative-control prose: retired alias plane_add_comment.\n"
      ),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
    refreshPromptDigest: true,
  },
  {
    name: "valid-reseal designated internal identifier occurrence",
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        '\noperationId: "plane.plane_add_comment@1"\n'
      ),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
    refreshPromptDigest: true,
  },
  {
    name: "valid-reseal ordinary docs path and non-model-facing prose",
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/README.md",
        "\nImplementation note: see docs/agent-tooling/README.md; ordinary prose may execute a later adapter step.\n"
      ),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
  },
];

const crossFamilyPairs = retiredNames.map((first, index) => ({
  first,
  second: retiredNames[(index + 1) % retiredNames.length],
}));
const crossFamilyResealedCases = crossFamilyPairs.flatMap(({ first, second }) => [
  {
    name: `valid-reseal cross-family marker-before ${first} then ${second}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\nRejected ${first} then ${second} authoritative model-facing name\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${second}`,
    reseal: true,
    refreshPromptDigest: true,
  },
  {
    name: `valid-reseal cross-family marker-after ${first} then ${second}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        `\n${first} then ${second} rejected authoritative model-facing name\n`
      ),
    expected: `docs/agent-tooling/prompts/release-planning-v1.md authoritatively uses retired name ${first}`,
    reseal: true,
    refreshPromptDigest: true,
  },
]);

const approvalManifestAuthoritativeCases = retiredNames.map((name) => ({
  name: `valid-reseal approval-manifest authoritative ${name}`,
  mutate: (directory) =>
    append(directory, "docs/agent-tooling/APPROVAL-MANIFEST.md", `\nAuthoritative model-facing name: ${name}\n`),
  expected: `docs/agent-tooling/APPROVAL-MANIFEST.md authoritatively uses retired name ${name}`,
  reseal: true,
}));

const approvalManifestPermittedCases = retiredNames.flatMap((name) => [
  {
    name: `valid-reseal approval-manifest historical ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/APPROVAL-MANIFEST.md",
        `\nHistorical negative-control prose: retired alias ${name}.\n`
      ),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
  },
  {
    name: `valid-reseal approval-manifest internal ${name}`,
    mutate: (directory) =>
      append(directory, "docs/agent-tooling/APPROVAL-MANIFEST.md", `\noperationId: "plane.${name}@1"\n`),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
  },
  {
    name: `valid-reseal approval-manifest path and prose ${name}`,
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/APPROVAL-MANIFEST.md",
        `\nImplementation note: see docs/agent-tooling/README.md; ordinary prose may ${name}.\n`
      ),
    expected: "PASS retired-name negative control",
    expectSuccess: true,
    reseal: true,
  },
]);

const manifestTableResealedCases = retiredNames.map((name) => ({
  name: `valid-reseal frozen manifest table retired row ${name}`,
  mutate: (directory) => replaceManifestModelFacingName(directory, name),
  expected: "frozen manifest model-facing table differs from the exact ordered model-facing surface",
  reseal: true,
}));

const omittedCanonicalAuthorityCases = [
  {
    name: "valid-reseal GOAL authoritative section",
    mutate: (directory) =>
      insertAfterHeading(
        directory,
        "docs/agent-tooling/GOAL.md",
        "## Normative resource catalog and authority",
        "Authoritative model-facing name: docs"
      ),
    expected: "docs/agent-tooling/GOAL.md authoritatively uses retired name docs",
    reseal: true,
  },
  {
    name: "valid-reseal product-requirements authoritative search",
    mutate: (directory) =>
      insertAfterHeading(
        directory,
        "docs/agent-tooling/product-requirements.md",
        "## Required outcomes",
        "Authoritative model-facing name: search"
      ),
    expected: "docs/agent-tooling/product-requirements.md authoritatively uses retired name search",
    reseal: true,
  },
  {
    name: "valid-reseal model-surface-schema description execute",
    mutate: (directory) => insertModelSurfaceSchemaDescription(directory, "execute"),
    expected:
      "docs/agent-tooling/model-facing-surface.schema.json authoritatively uses retired name execute in /properties/names/items/properties/description/description",
    reseal: true,
  },
];

const authorityBoundaryCases = [
  {
    name: "valid-reseal GOAL new unclassified semantic-purpose section",
    mutate: (directory) =>
      insertAfterHeading(
        directory,
        "docs/agent-tooling/GOAL.md",
        "## Normative resource catalog and authority",
        "### New unclassified authority section\nSemantic purpose: search"
      ),
    expected: "docs/agent-tooling/GOAL.md has an unclassified or stale Markdown section policy",
    reseal: true,
  },
  {
    name: "valid-reseal ownership role authority marker",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/ownership-map.json",
        '"role": "Root integrator and shared wiring owner"',
        '"role": "Authoritative model-facing name: docs"'
      ),
    expected:
      "docs/agent-tooling/ownership-map.json has a non-model-facing authority marker for retired name docs in /owners/0/role",
    reseal: true,
  },
  {
    name: "valid-reseal readiness semantic-purpose marker",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/g0-readiness.json",
        '"ownerRole": "root-integrator",\n      "reviewerRole": "sol-reviewer"',
        '"ownerRole": "Semantic purpose: search",\n      "reviewerRole": "sol-reviewer"'
      ),
    expected:
      "docs/agent-tooling/g0-readiness.json has a non-model-facing authority marker for retired name search in /clauses/0/ownerRole",
    reseal: true,
  },
  {
    name: "valid-reseal integration-lock schema-note marker",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/integration-lock.g0.json",
        '"description": "Generated operation and event JSON Schemas, catalog digest, and cross-repository compatibility bundle"',
        '"description": "Schema note: execute"'
      ),
    expected:
      "docs/agent-tooling/integration-lock.g0.json has a non-model-facing authority marker for retired name execute in /pendingInputs/0/description",
    reseal: true,
  },
  {
    name: "valid-reseal Markdown semantic-purpose marker",
    mutate: (directory) =>
      insertAfterHeading(directory, "docs/agent-tooling/README.md", "## G0 preflight", "Semantic purpose: search"),
    expected:
      "docs/agent-tooling/README.md has a non-model-facing authority marker for retired name search in G0 preflight",
    reseal: true,
  },
  {
    name: "valid-reseal Markdown model-facing-purpose marker",
    mutate: (directory) =>
      insertAfterHeading(directory, "docs/agent-tooling/README.md", "## G0 preflight", "Model-facing purpose: execute"),
    expected:
      "docs/agent-tooling/README.md has a non-model-facing authority marker for retired name execute in G0 preflight",
    reseal: true,
  },
  {
    name: "valid-reseal Markdown schema-note marker",
    mutate: (directory) =>
      insertAfterHeading(directory, "docs/agent-tooling/README.md", "## G0 preflight", "Schema note: docs"),
    expected:
      "docs/agent-tooling/README.md has a non-model-facing authority marker for retired name docs in G0 preflight",
    reseal: true,
  },
];

const policyCoverageCases = [
  {
    name: "valid-reseal omitted product-requirements section declaration",
    mutate: (directory) => {
      replace(
        directory,
        "docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
        '        2,\n        "Required outcomes",\n        "authoritative/model-facing"\n      ],',
        ""
      );
      insertAfterHeading(
        directory,
        "docs/agent-tooling/product-requirements.md",
        "## Required outcomes",
        "Authoritative model-facing name: search"
      );
    },
    expected: "docs/agent-tooling/product-requirements.md has an unclassified or stale Markdown section policy",
    reseal: true,
  },
  {
    name: "valid-reseal drifted authority policy path",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
        '  "docs/agent-tooling/WORKLOG.md": {\n',
        '  "docs/agent-tooling/not-sealed.md": { preamble: "non-model-facing", headings: [] },\n  "docs/agent-tooling/WORKLOG.md": {\n'
      ),
    expected: "retired-name Markdown section policy paths are missing or stale",
    reseal: true,
  },
  {
    name: "valid-reseal missing structured pointer subtree",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
        '  "docs/agent-tooling/g0-readiness.json": { authoritative: [], authoritativeSubtrees: [], nonModelFacingSubtrees: [[]] },',
        '  "docs/agent-tooling/g0-readiness.json": { authoritative: [], authoritativeSubtrees: [], nonModelFacingSubtrees: [] },'
      ),
    expected: "docs/agent-tooling/g0-readiness.json has an unclassified structured authority pointer",
    reseal: true,
  },
  {
    name: "valid-reseal stale structured authority subtree",
    mutate: (directory) =>
      replace(
        directory,
        "docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
        '    authoritativeSubtrees: [["properties", "names", "items", "properties", "description"]],',
        '    authoritativeSubtrees: [["properties", "names", "items", "properties", "missing"]],'
      ),
    expected: "model-facing-surface.schema.json has a stale structured authority declaration",
    reseal: true,
  },
];

cases.push(
  ...resealedAdversarialCases,
  ...existingResealedPositiveCases,
  ...resealedPositiveCases,
  ...crossFamilyResealedCases,
  ...approvalManifestAuthoritativeCases,
  ...approvalManifestPermittedCases,
  ...manifestTableResealedCases,
  ...omittedCanonicalAuthorityCases,
  ...authorityBoundaryCases,
  ...policyCoverageCases
);

function runPreflight(directory, testCase, { allowDirty = false } = {}) {
  const args = ["docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "--mode", "preflight"];
  if (allowDirty) args.push("--negative-control");
  const result = spawnSync("node", args, { cwd: directory, encoding: "utf8" });
  const output = `${result.stdout}${result.stderr}`;
  const observed = output.includes(testCase.expected);
  if (testCase.expectSuccess ? result.status !== 0 || !observed : result.status === 0 || !observed)
    throw new Error(`unexpected result; exit=${result.status}; output=${output}`);
  return result;
}

async function runCase(testCase) {
  await runTemporaryCase(testCase, (temporaryRoot) => {
    if (testCase.allowDirty !== false) writeFileSync(join(temporaryRoot, ".g0-negative-control"), `${testCase.name}\n`);
    testCase.mutate(temporaryRoot);
    runPreflight(temporaryRoot, testCase, { allowDirty: testCase.allowDirty !== false });
    console.log(
      `${testCase.expectSuccess ? "PASS" : "PASS"}: ${testCase.name} ${testCase.expectSuccess ? "accepted" : `rejected for ${testCase.expected}`}`
    );
  });
}

async function runResealedCase(testCase) {
  await runTemporaryCase(testCase, (temporaryRoot) => {
    testCase.mutate(temporaryRoot);
    if (testCase.refreshPromptDigest) refreshPromptDigest(temporaryRoot);
    run(temporaryRoot, ["git", "add", "--all"]);
    const contentCommit = commit(temporaryRoot, `negative-control-content-${testCase.name}`);
    run(temporaryRoot, ["node", "docs/agent-tooling/verifiers/seal-g0-evidence.mjs"]);
    append(
      temporaryRoot,
      "docs/agent-tooling/WORKLOG.md",
      `\nValid-reseal negative control: ${testCase.name}; content commit ${contentCommit}.\n`
    );
    run(temporaryRoot, ["git", "add", ...allowedSealPaths]);
    commit(temporaryRoot, `negative-control-seal-${testCase.name}`);
    runPreflight(temporaryRoot, testCase);
    console.log(
      `${testCase.expectSuccess ? "PASS" : "PASS"}: ${testCase.name} ${testCase.expectSuccess ? "accepted" : `rejected for ${testCase.expected}`}`
    );
  });
}

async function runCleanupRetryControl() {
  const temporaryParent = mkdtempSync(join(tmpdir(), "plane-g0-cleanup-control-"));
  let attempts = 0;
  await cleanupTemporaryCheckout(temporaryParent, "cleanup retry/backoff control", (target, options) => {
    attempts += 1;
    if (attempts === 1) {
      const error = new Error("simulated ENOTEMPTY");
      error.code = "ENOTEMPTY";
      throw error;
    }
    rmSync(target, options);
  });
  if (attempts !== 2) throw new Error(`cleanup retry control expected two attempts, observed ${attempts}`);
  console.log("PASS: cleanup retry/backoff control accepted");
}

await cases.reduce(
  (previous, testCase) => previous.then(() => (testCase.reseal ? runResealedCase : runCase)(testCase)),
  Promise.resolve()
);
await runCleanupRetryControl();
console.log(`PASS: ${cases.length + 1} G0 negative and harness controls exercised`);

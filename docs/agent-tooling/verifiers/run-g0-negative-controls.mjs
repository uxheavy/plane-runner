#!/usr/bin/env node

import { createHash } from "node:crypto";
import { copyFileSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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

function replace(directory, path, from, to) {
  const target = join(directory, path);
  const source = readFileSync(target, "utf8");
  if (!source.includes(from)) throw new Error(`mutation anchor missing in ${path}`);
  writeFileSync(target, source.replace(from, to));
}

function commit(directory, message, args = []) {
  return run(directory, ["git", "commit", ...args, "-m", message], {
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "g0-negative-control",
      GIT_AUTHOR_EMAIL: "g0-negative-control@example.invalid",
      GIT_COMMITTER_NAME: "g0-negative-control",
      GIT_COMMITTER_EMAIL: "g0-negative-control@example.invalid",
    },
  });
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

function runCase(testCase) {
  const temporaryRoot = mkdtempSync(join(tmpdir(), "plane-g0-negative-"));
  try {
    run(repositoryRoot, ["git", "clone", "--local", "--no-hardlinks", repositoryRoot, temporaryRoot]);
    run(temporaryRoot, ["git", "remote", "add", "upstream", "https://github.com/uxheavy/plane-runner.git"]);
    symlinkSync(join(repositoryRoot, "node_modules"), join(temporaryRoot, "node_modules"), "dir");
    if (testCase.allowDirty !== false) writeFileSync(join(temporaryRoot, ".g0-negative-control"), `${testCase.name}\n`);
    testCase.mutate(temporaryRoot);
    const args = ["docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "--mode", "preflight"];
    if (testCase.allowDirty !== false) args.push("--negative-control");
    const result = spawnSync("node", args, { cwd: temporaryRoot, encoding: "utf8" });
    const output = `${result.stdout}${result.stderr}`;
    const observed = output.includes(testCase.expected);
    if (testCase.expectSuccess ? result.status !== 0 || !observed : result.status === 0 || !observed)
      throw new Error(`unexpected result; exit=${result.status}; output=${output}`);
    console.log(
      `${testCase.expectSuccess ? "PASS" : "PASS"}: ${testCase.name} ${testCase.expectSuccess ? "accepted" : `rejected for ${testCase.expected}`}`
    );
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

for (const testCase of cases) runCase(testCase);
console.log(`PASS: ${cases.length} G0 negative controls exercised`);

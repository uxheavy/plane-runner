#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

const repositoryRoot = resolve(import.meta.dirname, "../../..");
const readinessRelativePath = "docs/agent-tooling/g0-readiness.json";

function run(cwd, args, options = {}) {
  const result = spawnSync(args[0], args.slice(1), { cwd, encoding: "utf8", ...options });
  if (result.status !== 0) throw new Error(`${args.join(" ")} failed: ${result.stderr || result.stdout}`);
  return result.stdout.trim();
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

const temporaryRoot = mkdtempSync(join(tmpdir(), "plane-g0-approved-"));
try {
  run(repositoryRoot, ["git", "clone", "--local", "--no-hardlinks", repositoryRoot, temporaryRoot]);
  run(temporaryRoot, ["git", "remote", "add", "upstream", "https://github.com/uxheavy/plane-runner.git"]);
  symlinkSync(join(repositoryRoot, "node_modules"), join(temporaryRoot, "node_modules"), "dir");
  const readinessPath = join(temporaryRoot, readinessRelativePath);
  const lockPath = join(temporaryRoot, "docs/agent-tooling/integration-lock.g0.json");
  const readiness = JSON.parse(readFileSync(readinessPath, "utf8"));
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const sealedHead = run(temporaryRoot, ["git", "rev-parse", "HEAD"]);
  if (run(temporaryRoot, ["git", "rev-parse", `${sealedHead}^`]) !== lock.seal.contentCommit)
    throw new Error("approved fixture base does not model content commit -> evidence seal -> approval topology");
  const pendingResult = spawnSync("node", ["docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "--mode", "g0"], {
    cwd: temporaryRoot,
    encoding: "utf8",
  });
  const pendingOutput = `${pendingResult.stdout}${pendingResult.stderr}`;
  if (pendingResult.status === 0 || !pendingOutput.includes("human approval"))
    throw new Error(`real pending G0 did not fail only for pending approval: ${pendingOutput}`);
  readiness.status = "approved";
  readiness.approval.status = "approved";
  for (const clause of readiness.clauses) clause.status = "ready";
  readiness.approval.approvedBy = {
    identity: "temporary-approved-fixture",
    reference: "docs/agent-tooling/verifiers/test-g0-approved-fixture.mjs",
  };
  readiness.approval.approvedAt = "2026-08-04T00:00:00Z";
  readiness.approval.evidenceBinding = {
    contentCommit: lock.seal.contentCommit,
    sealedHead,
    lockDigest: sha256(readFileSync(lockPath)),
  };
  writeFileSync(readinessPath, `${JSON.stringify(readiness, null, 2)}\n`);
  run(temporaryRoot, ["git", "add", readinessRelativePath]);
  run(temporaryRoot, ["git", "commit", "-m", "negative-control-approved-state"], {
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "approved-fixture",
      GIT_AUTHOR_EMAIL: "approved-fixture@example.invalid",
      GIT_COMMITTER_NAME: "approved-fixture",
      GIT_COMMITTER_EMAIL: "approved-fixture@example.invalid",
    },
  });
  const result = spawnSync("node", ["docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "--mode", "g0"], {
    cwd: temporaryRoot,
    encoding: "utf8",
  });
  const output = `${result.stdout}${result.stderr}`;
  if (result.status !== 0) throw new Error(`approved fixture was rejected: ${output}`);
  console.log("PASS: temporary approved readiness state verified with exit 0; real pending record was not changed");
} finally {
  rmSync(temporaryRoot, { recursive: true, force: true });
}

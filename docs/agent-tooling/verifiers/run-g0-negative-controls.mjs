#!/usr/bin/env node

import { mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(verifierRoot, "../..");
const cases = [
  {
    name: "authoritative bare execute",
    mutate: (directory) =>
      append(
        directory,
        "docs/agent-tooling/prompts/release-planning-v1.md",
        "\nAuthoritative model-facing tool name: execute\n"
      ),
    expected: "authoritatively uses retired name execute",
  },
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
    name: "dirty tracked package",
    mutate: (directory) => append(directory, "docs/agent-tooling/README.md", "\nDirty tracked mutation.\n"),
    expected: "authoritative Plane checkout must be clean",
    allowDirty: false,
  },
  {
    name: "extra post-seal commit",
    mutate: (directory) => {
      const result = spawnSync("git", ["commit", "--allow-empty", "-m", "negative-control-extra-post-seal-commit"], {
        cwd: directory,
        encoding: "utf8",
        env: {
          ...process.env,
          GIT_AUTHOR_NAME: "negative-control",
          GIT_AUTHOR_EMAIL: "negative-control@example.invalid",
          GIT_COMMITTER_NAME: "negative-control",
          GIT_COMMITTER_EMAIL: "negative-control@example.invalid",
        },
      });
      if (result.status !== 0) throw new Error(`could not create extra commit: ${result.stderr}`);
    },
    expected: "pending package must be exactly content commit",
    allowDirty: false,
  },
];

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

function runCase(testCase) {
  const temporaryRoot = mkdtempSync(join(tmpdir(), "plane-g0-negative-"));
  try {
    const clone = spawnSync("git", ["clone", "--local", "--no-hardlinks", repositoryRoot, temporaryRoot], {
      encoding: "utf8",
    });
    if (clone.status !== 0)
      throw new Error(`could not clone repository for negative control: ${clone.stderr || clone.stdout}`);
    const upstream = spawnSync("git", ["remote", "add", "upstream", "https://github.com/uxheavy/plane-runner.git"], {
      cwd: temporaryRoot,
      encoding: "utf8",
    });
    if (upstream.status !== 0)
      throw new Error(`could not add upstream remote for negative control: ${upstream.stderr || upstream.stdout}`);
    symlinkSync(join(repositoryRoot, "node_modules"), join(temporaryRoot, "node_modules"), "dir");
    if (testCase.allowDirty !== false) writeFileSync(join(temporaryRoot, ".g0-negative-control"), `${testCase.name}\n`);
    testCase.mutate(temporaryRoot);
    const args = ["docs/agent-tooling/verifiers/verify-g0-preflight.mjs", "--mode", "preflight"];
    if (testCase.allowDirty !== false) args.push("--negative-control");
    const result = spawnSync("node", args, { cwd: temporaryRoot, encoding: "utf8" });
    const output = `${result.stdout}${result.stderr}`;
    if (result.status === 0 || !output.includes(testCase.expected)) {
      throw new Error(`expected rejection was not observed; exit=${result.status}; output=${output}`);
    }
    console.log(`PASS: ${testCase.name} rejected for ${testCase.expected}`);
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

for (const testCase of cases) runCase(testCase);
console.log(`PASS: ${cases.length} G0 negative controls rejected`);

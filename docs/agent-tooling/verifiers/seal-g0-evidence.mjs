#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const verifierRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(verifierRoot, "../..");
const lockPath = resolve(verifierRoot, "integration-lock.g0.json");
const readinessPath = resolve(verifierRoot, "g0-readiness.json");
const sourceInventoryPath = resolve(verifierRoot, "SOURCE-INVENTORY.md");
const baselineCommit = "96bd075c967c3f25e536734bb477269f273767cd";

function git(args) {
  const result = spawnSync("git", ["-C", repositoryRoot, ...args], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`);
  return result.stdout.trim();
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function read(path) {
  return readFileSync(resolve(path.startsWith("docs/") ? repositoryRoot : verifierRoot, path));
}

function writeJson(path, value) {
  writeFileSync(resolve(verifierRoot, path), `${JSON.stringify(value, null, 2)}\n`);
}

function formatMarkdownTables(source) {
  const lines = source.split("\n");
  const formatted = [];
  for (let index = 0; index < lines.length; index += 1) {
    const header = lines[index];
    const separator = lines[index + 1];
    if (!/^\|.*\|$/.test(header) || !/^\|(?:\s*:?-{3,}:?\s*\|)+$/.test(separator ?? "")) {
      formatted.push(header);
      continue;
    }
    const rows = [header];
    index += 2;
    while (index < lines.length && /^\|.*\|$/.test(lines[index])) {
      rows.push(lines[index]);
      index += 1;
    }
    index -= 1;
    const cells = rows.map((row) =>
      row
        .trim()
        .slice(1, -1)
        .split("|")
        .map((cell) => cell.trim())
    );
    const widths = cells[0].map((_, column) => Math.max(3, ...cells.map((row) => row[column].length)));
    const formatRow = (row) =>
      `| ${row.map((cell, column) => `${cell}${" ".repeat(widths[column] - cell.length)}`).join(" | ")} |`;
    formatted.push(formatRow(cells[0]));
    formatted.push(`| ${widths.map((width) => "-".repeat(width)).join(" | ")} |`);
    for (const row of cells.slice(1)) formatted.push(formatRow(row));
  }
  return formatted.join("\n");
}

if (git(["status", "--porcelain", "--untracked-files=all"]) !== "") {
  throw new Error("seal generation requires the content commit checkout to be clean");
}
if (git(["rev-parse", "HEAD"]) === baselineCommit)
  throw new Error("seal generation must run after the remediation content commit");

const lock = JSON.parse(readFileSync(lockPath, "utf8"));
const readiness = JSON.parse(readFileSync(readinessPath, "utf8"));
const contentCommit = git(["rev-parse", "HEAD"]);
const contentTree = git(["rev-parse", "HEAD^{tree}"]);
const baselineWorklog = spawnSync(
  "git",
  ["-C", repositoryRoot, "show", `${baselineCommit}:docs/agent-tooling/WORKLOG.md`],
  { encoding: null }
);
if (baselineWorklog.status !== 0) throw new Error("the sealed worklog baseline is unavailable");

const sourceInventory = formatMarkdownTables(
  readFileSync(sourceInventoryPath, "utf8").toString().replaceAll("__CONTENT_COMMIT__", contentCommit)
);
if (sourceInventory.includes("__CONTENT_COMMIT__"))
  throw new Error("source inventory still contains a seal placeholder");
writeFileSync(sourceInventoryPath, sourceInventory);

const contentPaths = lock.seal.contentPaths;
const evidencePaths = lock.seal.sealEvidencePaths;
const digestFiles = Object.fromEntries([
  ...contentPaths.map((path) => [path, sha256(read(path))]),
  ["docs/agent-tooling/SOURCE-INVENTORY.md", sha256(readFileSync(sourceInventoryPath))],
]);
lock.repositories.find((repository) => repository.id === "plane").sha = contentCommit;
lock.digests.files = digestFiles;
lock.seal.contentCommit = contentCommit;
lock.seal.contentTree = contentTree;
lock.seal.sealEvidencePaths = evidencePaths;
lock.seal.worklogBaseline = {
  commit: baselineCommit,
  byteLength: baselineWorklog.stdout.length,
  sha256: sha256(baselineWorklog.stdout),
};
writeJson("integration-lock.g0.json", lock);

readiness.approval.manifestDigest = sha256(read("APPROVAL-MANIFEST.md"));
readiness.evidenceDigests.files = digestFiles;
writeJson("g0-readiness.json", readiness);
console.log(
  `sealed content commit ${contentCommit}; ${contentPaths.length} content paths and ${evidencePaths.length} seal paths bound`
);

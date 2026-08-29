#!/usr/bin/env node

// Repository-specific structural checks for changed paths only.

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const GENERIC_BUCKETS = new Set(["common", "helpers", "shared", "utils"]);
const TRACKED_OUTPUTS = new Set([".next", "build", "coverage", "dist", "node_modules", "storybook-static"]);
const INTERNAL_PREFIX = "@plane/";
const EXCEPTIONS_PATH = ".github/repository-policy-exceptions.json";

function violation(rule, path, message) {
  return { rule, path, message };
}

export function parseNameStatus(raw) {
  const fields = raw.split("\0").filter(Boolean);
  const changes = [];

  for (let index = 0; index < fields.length; ) {
    const status = fields[index++];
    if (status.startsWith("R") || status.startsWith("C")) {
      const oldPath = fields[index++];
      changes.push({ status: status[0], oldPath, path: fields[index++] });
    } else {
      changes.push({ status: status[0], path: fields[index++] });
    }
  }

  return changes;
}

function newGenericBucket(path, baseHasPath) {
  const parts = path.split("/");
  const candidate =
    parts[0] === "apps" && GENERIC_BUCKETS.has(parts[2])
      ? parts.slice(0, 3).join("/")
      : parts[0] === "packages" && GENERIC_BUCKETS.has(parts[1])
        ? parts.slice(0, 2).join("/")
        : null;

  return candidate && !baseHasPath(candidate) ? candidate : null;
}

function isMigration(path) {
  return path.includes("/migrations/") && /\/\d[^/]*\.py$/.test(path);
}

function loadExceptions(readFile) {
  const raw = readFile(EXCEPTIONS_PATH);
  if (raw === null) return [];
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error(`${EXCEPTIONS_PATH} must contain a JSON array`);
  return parsed;
}

function hasExactException(exceptions, path, baseBlob, now) {
  return exceptions.some(
    (entry) =>
      entry?.rule === "RP003" &&
      entry.path === path &&
      entry.baseBlob === baseBlob(path) &&
      typeof entry.reason === "string" &&
      entry.reason.trim().length >= 12 &&
      typeof entry.approvedBy === "string" &&
      entry.approvedBy.trim().length > 0 &&
      typeof entry.expires === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(entry.expires) &&
      new Date(`${entry.expires}T00:00:00Z`).toISOString().slice(0, 10) === entry.expires &&
      entry.expires >= now.toISOString().slice(0, 10),
  );
}

function manifestViolations(path, manifest) {
  const errors = [];
  for (const section of ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]) {
    for (const [name, version] of Object.entries(manifest[section] ?? {})) {
      if (name.startsWith(INTERNAL_PREFIX) && !String(version).startsWith("workspace:")) {
        errors.push(
          violation("RP004", path, `${section}.${name} must use the workspace: protocol, found ${version}`),
        );
      }
    }
  }
  return errors;
}

function workspaceOwnerMissing(path, codeowners) {
  const workspace = path.split("/").slice(0, 2).join("/");
  const rules = codeowners
    .split("\n")
    .map((line) => line.trim().split(/\s+/))
    .filter(([pattern]) => pattern && !pattern.startsWith("#"));
  return !rules.some(
    ([pattern, ...owners]) =>
      [`${workspace}/`, `${workspace}/*`, `${workspace}/**`, `${workspace}/package.json`].includes(
        pattern.replace(/^\//, ""),
      ) && owners.some((owner) => owner.startsWith("@") || owner.includes("@")),
  );
}

export function evaluatePolicy({
  changes,
  baseHasPath,
  baseBlob,
  readFile,
  now = new Date(),
}) {
  const errors = [];
  const exceptions = loadExceptions(readFile);
  const codeowners = readFile("CODEOWNERS") ?? "";

  for (const change of changes) {
    const added = change.status === "A" || change.status === "R";

    if (added) {
      const bucket = newGenericBucket(change.path, baseHasPath);
      if (bucket) {
        errors.push(violation("RP001", change.path, `new generic bucket ${bucket} needs a concrete owner`));
      }

      const output = change.path.split("/").find((part) => TRACKED_OUTPUTS.has(part));
      if (output) {
        errors.push(violation("RP002", change.path, `tracked build output directory ${output} is forbidden`));
      }
    }

    const previousPath = change.oldPath ?? change.path;
    if (["M", "D", "R"].includes(change.status) && isMigration(previousPath)) {
      if (!hasExactException(exceptions, previousPath, baseBlob, now)) {
        errors.push(
          violation("RP003", previousPath, "existing migration history is immutable; add a new migration"),
        );
      }
    }

    if (change.path.match(/^(apps|packages)\/[^/]+\/package\.json$/)) {
      const raw = readFile(change.path);
      if (raw !== null) errors.push(...manifestViolations(change.path, JSON.parse(raw)));

      if (added && workspaceOwnerMissing(change.path, codeowners)) {
        errors.push(violation("RP005", change.path, "new workspace must have an explicit CODEOWNERS entry"));
      }
    }
  }

  return errors;
}

function git(args) {
  return execFileSync("git", args, { encoding: "utf8" }).trim();
}

export function readIndexFile(path, run = execFileSync) {
  try {
    return run("git", ["show", `:${path}`], { encoding: "utf8" });
  } catch {
    return null;
  }
}

function main(argv) {
  const staged = argv.includes("--staged");
  const baseIndex = argv.indexOf("--base");
  const base = baseIndex >= 0 ? argv[baseIndex + 1] : null;
  if (!staged && !base) throw new Error("usage: check-repository-policy.mjs --staged | --base <ref>");

  const diffArgs = staged
    ? ["diff", "--cached", "--name-status", "-z", "--find-renames"]
    : ["diff", "--name-status", "-z", "--find-renames", `${base}...HEAD`];
  const changes = parseNameStatus(execFileSync("git", diffArgs, { encoding: "utf8" }));
  const readFile = staged
    ? (path) => readIndexFile(path)
    : (path) => (existsSync(path) ? readFileSync(path, "utf8") : null);
  const baseHasPath = (path) => {
    if (staged) {
      try {
        execFileSync("git", ["cat-file", "-e", `HEAD:${path}`]);
        return true;
      } catch {
        return false;
      }
    }
    try {
      execFileSync("git", ["cat-file", "-e", `${base}:${path}`]);
      return true;
    } catch {
      return false;
    }
  };
  const baseBlob = (path) => {
    try {
      return git(["rev-parse", `${staged ? "HEAD" : base}:${path}`]);
    } catch {
      return "";
    }
  };

  const errors = evaluatePolicy({ changes, baseHasPath, baseBlob, readFile });
  for (const error of errors) console.error(`${error.path}: ${error.rule} ${error.message}`);
  if (errors.length) return 1;
  console.log(`repository policy passed (${changes.length} changed paths)`);
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 2;
  }
}

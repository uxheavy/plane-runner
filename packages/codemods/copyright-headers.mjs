/**
 * Copyright (c) 2026-present Ngo Quoc Huy
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { extname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const FORK_COPYRIGHT = "Copyright (c) 2026-present Ngo Quoc Huy";
export const UPSTREAM_COPYRIGHT =
  "Copyright (c) 2023-present Plane Software, Inc. and contributors";
export const SPDX_LICENSE = "SPDX-License-Identifier: AGPL-3.0-only";
export const PACKAGE_LICENSE = "AGPL-3.0-only";

const HEADER_SCAN_BYTES = 1024;

function headerFor(filePath) {
  if (extname(filePath) === ".py") {
    return `# ${FORK_COPYRIGHT}\n# ${SPDX_LICENSE}\n# See the LICENSE file for details.\n\n`;
  }

  return `/**\n * ${FORK_COPYRIGHT}\n * ${SPDX_LICENSE}\n * See the LICENSE file for details.\n */\n\n`;
}

export function isEligible(filePath) {
  return (
    (filePath.endsWith(".py") ||
      filePath.endsWith(".ts") ||
      filePath.endsWith(".tsx")) &&
    !filePath.includes("/migrations/") &&
    !filePath.endsWith(".config.ts") &&
    !filePath.endsWith(".d.ts")
  );
}

export function hasValidHeader(source) {
  // oxlint-disable-next-line unicorn/prefer-set-has -- Notices are substrings, not collection values.
  const header = source.slice(0, HEADER_SCAN_BYTES);
  const hasNotice = (notice) => header.includes(notice);
  const hasOwner = hasNotice(FORK_COPYRIGHT) || hasNotice(UPSTREAM_COPYRIGHT);
  return hasOwner && hasNotice(SPDX_LICENSE);
}

export function legalNotices(source) {
  return source
    .slice(0, HEADER_SCAN_BYTES)
    .split("\n")
    .filter(
      (line) =>
        line.includes("Copyright") || line.includes("SPDX-License-Identifier:")
    )
    .map((line) => line.trim());
}

export function preservesLegalNotices(before, after) {
  const notices = legalNotices(before);
  return notices.length > 0
    ? notices.every((notice) => after.includes(notice))
    : hasValidHeader(after);
}

export function transformCopyrightHeader(source, filePath) {
  // oxlint-disable-next-line unicorn/prefer-set-has -- Notices are substrings, not collection values.
  const header = source.slice(0, HEADER_SCAN_BYTES);
  const hasNotice = (notice) => header.includes(notice);

  if (hasNotice(FORK_COPYRIGHT) && hasNotice(SPDX_LICENSE)) return source;

  if (hasNotice(UPSTREAM_COPYRIGHT)) {
    return source.replace(UPSTREAM_COPYRIGHT, FORK_COPYRIGHT);
  }

  const copyrightHeader = headerFor(filePath);
  if (!source.startsWith("#!")) return copyrightHeader + source;

  const newline = source.indexOf("\n") + 1;
  return source.slice(0, newline) + copyrightHeader + source.slice(newline);
}

export function transformPackageLicense(source) {
  const metadata = JSON.parse(source);
  if (metadata.license === PACKAGE_LICENSE) return source;

  if (metadata.license === "AGPL-3.0") {
    return source.replace(
      '"license": "AGPL-3.0"',
      `"license": "${PACKAGE_LICENSE}"`
    );
  }

  if (metadata.license === undefined) {
    const privateField = /^(\s*)"private": (?:true|false),$/m;
    if (!privateField.test(source))
      throw new Error("package.json is missing a private field");
    return source.replace(
      privateField,
      `$&\n$1"license": "${PACKAGE_LICENSE}",`
    );
  }

  throw new Error(`unsupported package license: ${metadata.license}`);
}

function gitPaths(repoRoot, args, pathspecs) {
  const output = execFileSync(
    "git",
    ["-C", repoRoot, ...args, "--", ...pathspecs],
    {
      encoding: "buffer",
    }
  );

  return output.toString("utf8").split("\0").filter(Boolean);
}

function sourceFiles(repoRoot, args) {
  return gitPaths(repoRoot, args, ["*.py", "*.ts", "*.tsx"]).filter(isEligible);
}

function packageJsonFiles(repoRoot) {
  return gitPaths(
    repoRoot,
    ["ls-files", "-z"],
    ["package.json", "apps/*/package.json", "packages/*/package.json"]
  );
}

function parseArgs(args) {
  const mode = args.includes("--write-package-licenses")
    ? "write-package-licenses"
    : args.includes("--write")
      ? "write"
      : args.includes("--check")
        ? "check"
        : undefined;
  const baseFlag = mode === "write" ? "--added-from" : "--changed-from";
  const baseIndex = args.indexOf(baseFlag);
  const base = baseIndex === -1 ? undefined : args[baseIndex + 1];

  if (!mode || (mode !== "write-package-licenses" && !base)) {
    throw new Error(
      "Usage: copyright-headers.mjs --check --changed-from <git-ref> | --write --added-from <git-ref> | --write-package-licenses"
    );
  }

  return { base, mode };
}

export function run(args, cwd = process.cwd()) {
  const { base, mode } = parseArgs(args);
  const repoRoot = execFileSync(
    "git",
    ["-C", cwd, "rev-parse", "--show-toplevel"],
    { encoding: "utf8" }
  ).trim();
  const packageFiles = packageJsonFiles(repoRoot);

  if (mode === "write-package-licenses") {
    let changed = 0;
    for (const file of packageFiles) {
      const absolutePath = resolve(repoRoot, file);
      const source = readFileSync(absolutePath, "utf8");
      const transformed = transformPackageLicense(source);
      if (transformed !== source) {
        writeFileSync(absolutePath, transformed);
        changed += 1;
      }
    }
    return { changed, checked: packageFiles.length };
  }

  const addedFiles = sourceFiles(repoRoot, [
    "diff",
    "--name-only",
    "--diff-filter=A",
    "-z",
    `${base}...HEAD`,
  ]);
  const modifiedFiles =
    mode === "check"
      ? sourceFiles(repoRoot, [
          "diff",
          "--name-only",
          "--diff-filter=M",
          "-z",
          `${base}...HEAD`,
        ])
      : [];
  const files = [...addedFiles, ...modifiedFiles];

  const invalid = [];
  let changed = 0;

  for (const file of files) {
    const absolutePath = resolve(repoRoot, file);
    const source = readFileSync(absolutePath, "utf8");

    if (mode === "check") {
      if (addedFiles.includes(file)) {
        if (!hasValidHeader(source)) invalid.push(file);
      } else {
        const before = execFileSync(
          "git",
          ["-C", repoRoot, "show", `${base}:${file}`],
          { encoding: "utf8" }
        );
        if (!preservesLegalNotices(before, source)) invalid.push(file);
      }
      continue;
    }

    const transformed = transformCopyrightHeader(source, file);
    if (transformed !== source) {
      writeFileSync(absolutePath, transformed);
      changed += 1;
    }
  }

  if (mode === "check") {
    for (const file of packageFiles) {
      const metadata = JSON.parse(
        readFileSync(resolve(repoRoot, file), "utf8")
      );
      if (metadata.license !== PACKAGE_LICENSE) {
        invalid.push(`${file}: license must be ${PACKAGE_LICENSE}`);
      }
    }
  }

  if (invalid.length > 0) {
    throw new Error(`Invalid copyright headers:\n${invalid.join("\n")}`);
  }

  return { changed, checked: files.length + packageFiles.length };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const result = run(process.argv.slice(2));
    console.log(
      `Copyright headers: ${result.checked} checked, ${result.changed} changed.`
    );
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}

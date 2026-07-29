/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repositoryRoot = fileURLToPath(new URL("../../..", import.meta.url));
const documentationRoot = path.join(repositoryRoot, "docs/features/chat-semantic-context-picker");
const lessonLedger = path.join(documentationRoot, "LESSONS.md");

const implementationDirectories = [
  ["packages/chat-context/src", new Set([".ts"])],
  ["packages/chat-context/tests", new Set([".ts"])],
  ["packages/chat-context/fixtures", new Set([".json"])],
  ["packages/chat-context/scripts", new Set([".mjs"])],
];

const implementationFiles = [
  "package.json",
  "packages/chat-context/package.json",
  "packages/chat-context/tsconfig.json",
  "packages/chat-context/tsdown.config.ts",
  "packages/chat-context/verify-release.sh",
  "packages/chat-context/vitest.config.ts",
  "apps/api/plane/app/context_hydration.py",
  "apps/api/plane/app/urls/__init__.py",
  "apps/api/plane/app/urls/context_hydration.py",
  "apps/api/plane/app/views/__init__.py",
  "apps/api/plane/app/views/context_hydration.py",
  "apps/api/plane/tests/contract/api/test_semantic_context_hydration.py",
  "apps/api/plane/tests/contract/app/test_page_version_project_scope_app.py",
];

const requiredDocuments = [
  "GOAL.md",
  "LESSONS.md",
  "README.md",
  "RESULT.md",
  "WORKLOG.md",
  "delivery-plan.md",
  "decisions/0001-selection-foundation.md",
  "decisions/0002-picker-core-interface.md",
  "decisions/0003-live-editor-identity.md",
  "decisions/0004-server-hydration-boundary.md",
  "decisions/0005-composer-integration-interface.md",
  "decisions/0006-visual-fallback-boundary.md",
];

const collectFiles = async (relativeDirectory, extensions) => {
  const directory = path.join(repositoryRoot, relativeDirectory);
  const entries = await readdir(directory, { withFileTypes: true });
  const nestedFiles = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => collectFiles(path.posix.join(relativeDirectory, entry.name), extensions))
  );
  const localFiles = entries
    .filter((entry) => entry.isFile() && extensions.has(path.extname(entry.name)))
    .map((entry) => path.posix.join(relativeDirectory, entry.name));

  return [...localFiles, ...nestedFiles.flat()];
};

const discoveredFiles = (
  await Promise.all(
    implementationDirectories.map(([relativeDirectory, extensions]) => collectFiles(relativeDirectory, extensions))
  )
).flat();
const trackedFiles = [...new Set([...implementationFiles, ...discoveredFiles])].toSorted();
const hash = createHash("sha256");
const trackedContents = await Promise.all(
  trackedFiles.map(async (relativePath) => ({
    contents: await readFile(path.join(repositoryRoot, relativePath)),
    relativePath,
  }))
);

for (const { contents, relativePath } of trackedContents) {
  hash.update(relativePath);
  hash.update("\0");
  hash.update(contents);
  hash.update("\0");
}

const actualFingerprint = `sha256:${hash.digest("hex")}`;
const ledgerContents = await readFile(lessonLedger, "utf8");
const recordedFingerprint = ledgerContents.match(/Implementation fingerprint: `(?<fingerprint>sha256:[a-f0-9]{64})`/)
  ?.groups?.fingerprint;

const workspaceCatalog = await readFile(path.join(repositoryRoot, "pnpm-workspace.yaml"), "utf8");
const packageManifest = JSON.parse(
  await readFile(path.join(repositoryRoot, "packages/chat-context/package.json"), "utf8")
);
const documentChecks = await Promise.all(
  requiredDocuments.map(async (relativePath) => {
    try {
      await readFile(path.join(documentationRoot, relativePath));
      return undefined;
    } catch {
      return relativePath;
    }
  })
);
const missingDocuments = documentChecks.filter((relativePath) => relativePath !== undefined);

const violations = [];
if (recordedFingerprint !== actualFingerprint) {
  violations.push(`implementation fingerprint is ${actualFingerprint}, recorded ${recordedFingerprint ?? "none"}`);
}
if (!/^\s{2}"react-grab": "0\.1\.50"$/m.test(workspaceCatalog)) {
  violations.push("react-grab must remain exactly pinned to 0.1.50 in the workspace catalog");
}
if (!/^\s{2}"html2canvas-pro": "2\.3\.2"$/m.test(workspaceCatalog)) {
  violations.push("html2canvas-pro must remain exactly pinned to 2.3.2 in the workspace catalog");
}
if (packageManifest.dependencies?.["react-grab"] !== "catalog:") {
  violations.push("@plane/chat-context must consume react-grab through the workspace catalog");
}
if (packageManifest.dependencies?.["html2canvas-pro"] !== "catalog:") {
  violations.push("@plane/chat-context must consume html2canvas-pro through the workspace catalog");
}
if (missingDocuments.length > 0) {
  violations.push(`required feature documents are missing: ${missingDocuments.join(", ")}`);
}

if (violations.length > 0) {
  throw new Error(
    [
      "event=context_picker.documentation_contract",
      "status=failed",
      `violations=${violations.join("; ")}`,
      "suggestion=review the implementation change, update the relevant feature docs and lesson disposition, then record the printed fingerprint",
    ].join(" ")
  );
}

console.log(
  JSON.stringify({
    event: "context_picker.documentation_contract",
    status: "passed",
    implementationFingerprint: actualFingerprint,
    trackedFiles: trackedFiles.length,
    requiredDocuments: requiredDocuments.length,
  })
);

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const forbiddenMarkers = ["@react-grab/cli", "ReactGrabRenderer", "copyContent", "openFile", "registerThreeScene"];

const verifyBundle = async ({ entryFile, label, maximumGzipBytes, requiredMarkers = [] }) => {
  const entry = fileURLToPath(new URL(`../src/${entryFile}`, import.meta.url));
  const result = await build({
    root: packageRoot,
    configFile: false,
    logLevel: "silent",
    build: {
      write: false,
      minify: true,
      lib: {
        entry,
        formats: ["es"],
        fileName: label,
      },
    },
  });

  const buildResults = Array.isArray(result) ? result : [result];
  const code = buildResults
    .flatMap((buildResult) => buildResult.output)
    .filter((output) => output.type === "chunk")
    .map((output) => output.code)
    .join("\n");
  const gzipBytes = gzipSync(code).byteLength;
  const includedForbiddenMarkers = forbiddenMarkers.filter((marker) => code.includes(marker));
  const missingRequiredMarkers = requiredMarkers.filter((marker) => !code.includes(marker));

  if (includedForbiddenMarkers.length > 0 || missingRequiredMarkers.length > 0 || gzipBytes > maximumGzipBytes) {
    throw new Error(
      [
        "event=context_picker.production_bundle",
        "actor=package_consumer",
        `operation=bundle_${label}`,
        "risk=inspector_code_leak_or_renderer_regression",
        `expected=gzip_bytes<=${maximumGzipBytes} no forbidden markers and required:${requiredMarkers.join(",") || "none"}`,
        `actual=gzip_bytes:${gzipBytes} forbidden:${includedForbiddenMarkers.join(",") || "none"} missing:${missingRequiredMarkers.join(",") || "none"}`,
        "suggestion=inspect package subpath imports, dependency pinning, and tree-shaking",
      ].join(" ")
    );
  }

  console.log(
    JSON.stringify({
      event: "context_picker.production_bundle",
      status: "passed",
      bundle: label,
      gzipBytes,
      maximumGzipBytes,
      forbiddenMarkers: includedForbiddenMarkers,
      requiredMarkers,
    })
  );
};

await verifyBundle({ entryFile: "index.ts", label: "chat-context-core", maximumGzipBytes: 30_000 });
await verifyBundle({
  entryFile: "html2canvas-pro.ts",
  label: "html2canvas-pro-visual-renderer",
  maximumGzipBytes: 100_000,
  requiredMarkers: ["data-html2canvas-ignore"],
});

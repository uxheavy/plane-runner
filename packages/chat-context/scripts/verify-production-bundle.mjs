/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const entry = fileURLToPath(new URL("../src/index.ts", import.meta.url));
const maximumGzipBytes = 30_000;
const forbiddenMarkers = ["@react-grab/cli", "ReactGrabRenderer", "copyContent", "openFile", "registerThreeScene"];

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
      fileName: "chat-context",
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

if (includedForbiddenMarkers.length > 0 || gzipBytes > maximumGzipBytes) {
  throw new Error(
    [
      "event=context_picker.production_bundle",
      "actor=package_consumer",
      "operation=bundle_plane_adapter",
      "risk=full_inspector_or_cli_leaks_into_product_bundle",
      `expected=gzip_bytes<=${maximumGzipBytes} and no forbidden markers`,
      `actual=gzip_bytes:${gzipBytes} forbidden:${includedForbiddenMarkers.join(",") || "none"}`,
      "suggestion=inspect react-grab subpath imports and tree-shaking",
    ].join(" ")
  );
}

console.log(
  JSON.stringify({
    event: "context_picker.production_bundle",
    status: "passed",
    gzipBytes,
    maximumGzipBytes,
    forbiddenMarkers: includedForbiddenMarkers,
  })
);

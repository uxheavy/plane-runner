import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));

describe("generated contract artifacts", () => {
  test("manifest digests match the exact generated schema bytes", () => {
    const manifest = JSON.parse(readFileSync(`${schemaDirectory}/manifest.json`, "utf8")) as {
      protocol: string;
      schemas: Record<string, { filename: string; sha256: string }>;
    };

    expect(manifest.protocol).toBe("plane.agent-runtime/v1");
    for (const entry of Object.values(manifest.schemas)) {
      const contents = readFileSync(`${schemaDirectory}/${entry.filename}`);
      const digest = createHash("sha256").update(contents).digest("hex");
      expect(digest).toBe(entry.sha256);
    }
  });
});

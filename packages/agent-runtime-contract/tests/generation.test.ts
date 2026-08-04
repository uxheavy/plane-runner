import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const generatorPath = fileURLToPath(new URL("../scripts/generate-schemas.mjs", import.meta.url));
const schemaSourcePath = fileURLToPath(new URL("../src/schema-source.mjs", import.meta.url));

describe("generated contract artifacts", () => {
  test("fails when schema source drifts from checked-in artifacts", () => {
    expect(() =>
      execFileSync(process.execPath, [generatorPath, "--check"], {
        cwd: fileURLToPath(new URL("..", import.meta.url)),
        env: process.env,
        stdio: "pipe",
      })
    ).not.toThrow();
  });

  test("detects a source-only drift and restores the source after the probe", () => {
    const originalSource = readFileSync(schemaSourcePath, "utf8");
    const driftedSource = originalSource.replace(
      'const protocol = "plane.agent-runtime/v1";',
      'const protocol = "plane.agent-runtime/v1-drift";'
    );
    expect(driftedSource).not.toBe(originalSource);
    writeFileSync(schemaSourcePath, driftedSource, "utf8");

    try {
      expect(() =>
        execFileSync(process.execPath, [generatorPath, "--check"], {
          cwd: fileURLToPath(new URL("..", import.meta.url)),
          env: process.env,
          stdio: "pipe",
        })
      ).toThrow();
    } finally {
      writeFileSync(schemaSourcePath, originalSource, "utf8");
    }
  });

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

  test("emits only transitive reachable definitions for each root schema", () => {
    for (const name of ["run-snapshot", "invocation-envelope", "runtime-event", "runtime-exit"] as const) {
      const schema = JSON.parse(readFileSync(`${schemaDirectory}/${name}.schema.json`, "utf8")) as {
        $defs: Record<string, unknown>;
      };
      const referenced = new Set<string>();
      const collect = (value: unknown) => {
        if (Array.isArray(value)) {
          value.forEach(collect);
          return;
        }
        if (value === null || typeof value !== "object") {
          return;
        }
        const object = value as Record<string, unknown>;
        if (typeof object.$ref === "string" && object.$ref.startsWith("#/$defs/")) {
          referenced.add(object.$ref.slice("#/$defs/".length));
        }
        Object.entries(object).forEach(([key, child]) => {
          if (key !== "$defs") {
            collect(child);
          }
        });
      };

      collect(schema);
      const queue = [...referenced];
      for (const definitionName of queue) {
        collect(schema.$defs[definitionName]);
        for (const nestedName of referenced) {
          if (!queue.includes(nestedName)) {
            queue.push(nestedName);
          }
        }
      }

      expect(Object.keys(schema.$defs).toSorted()).toEqual(queue.toSorted());
    }
  });
});

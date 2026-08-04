import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

import { describe, expect, test } from "vitest";

import { generateSchemas } from "../scripts/generate-schemas.mjs";
import { schemas } from "../src/schema-source.mjs";

const packageDirectory = fileURLToPath(new URL("..", import.meta.url));
const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const generatorPath = fileURLToPath(new URL("../scripts/generate-schemas.mjs", import.meta.url));
const generatedNames = [
  "run-snapshot",
  "invocation-envelope",
  "runtime-event",
  "runtime-exit",
  "runtime-durable-state",
  "manifest",
];
const generatedFilename = (name: string) => (name === "manifest" ? "manifest.json" : `${name}.schema.json`);
const formatterPath =
  process.env.OXFMT_PATH ?? fileURLToPath(new URL("../../../node_modules/.bin/oxfmt", import.meta.url));

const readArtifacts = async (directory: string) =>
  Object.fromEntries(
    await Promise.all(
      generatedNames.map(async (name) => [name, await readFile(`${directory}/${generatedFilename(name)}`, "utf8")])
    )
  );

const rewriteByteConstraint = (value: unknown): void => {
  if (Array.isArray(value)) {
    value.forEach(rewriteByteConstraint);
    return;
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  const object = value as Record<string, unknown>;
  if (object["x-utf8ByteMax"] === 4096) {
    object["x-utf8ByteMax"] = 4095;
  }
  Object.values(object).forEach(rewriteByteConstraint);
};

const driftSchemas = () => {
  const clone = JSON.parse(JSON.stringify(schemas)) as Record<string, unknown>;
  rewriteByteConstraint(clone);
  return clone;
};

describe("generated contract artifacts", () => {
  test("fails when schema source drifts from checked-in artifacts", async () => {
    const result = await generateSchemas({
      schemas: driftSchemas(),
      outputDirectory: schemaDirectory,
      checkOnly: true,
      formatterPath,
    });
    expect(result.mismatches).toContain("runtime-event.schema.json");
  });

  test("does not rewrite tracked inputs or outputs while checking an in-memory drift", async () => {
    const sourceBefore = readFileSync(fileURLToPath(new URL("../src/byte-constraints.json", import.meta.url)), "utf8");
    const trackedBefore = await readArtifacts(schemaDirectory);

    await generateSchemas({
      schemas: driftSchemas(),
      outputDirectory: schemaDirectory,
      checkOnly: true,
      formatterPath,
    });

    expect(readFileSync(fileURLToPath(new URL("../src/byte-constraints.json", import.meta.url)), "utf8")).toBe(
      sourceBefore
    );
    await expect(readArtifacts(schemaDirectory)).resolves.toEqual(trackedBefore);
  });

  test("is deterministic and idempotent in an isolated output directory", async () => {
    const directory = await mkdtemp(`${tmpdir()}/plane-agent-runtime-generation-`);
    try {
      await generateSchemas({ outputDirectory: directory, formatterPath });
      const before = await readArtifacts(directory);
      await generateSchemas({ outputDirectory: directory, formatterPath });
      const after = await readArtifacts(directory);
      expect(after).toEqual(before);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test("supports concurrent generation without shared source or output mutation", async () => {
    const root = await mkdtemp(`${tmpdir()}/plane-agent-runtime-generation-concurrent-`);
    const directories = generatedNames.map((_, index) => `${root}/run-${index}`);
    try {
      const results = await Promise.all(
        directories.map((directory) => generateSchemas({ outputDirectory: directory, formatterPath }))
      );
      expect(results.every((result) => result.mismatches.length === 0)).toBe(true);
      const artifacts = await Promise.all(directories.map(readArtifacts));
      expect(artifacts.every((value) => JSON.stringify(value) === JSON.stringify(artifacts[0]))).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
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
    for (const name of [
      "run-snapshot",
      "invocation-envelope",
      "runtime-event",
      "runtime-exit",
      "runtime-durable-state",
    ] as const) {
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

  test("the CLI check remains read-only", () => {
    expect(() =>
      execFileSync(process.execPath, [generatorPath, "--check"], {
        cwd: packageDirectory,
        env: { ...process.env, OXFMT_PATH: formatterPath },
        stdio: "pipe",
      })
    ).not.toThrow();
  });
});

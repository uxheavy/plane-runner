import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import {
  MAX_SERIALIZED_JSON_BYTES,
  ContractParseError,
  createRuntimeSchemaValidator,
  parseRuntimeEvent,
  serializedJsonByteLength,
  type ContractJsonInput,
  verifyRuntimeExecution,
} from "../src";
import { event, observationBody } from "./fixtures";

const packageRequire = createRequire(import.meta.url);
const packageManifest = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
) as { exports: Record<string, string> };
const wire = (value: unknown): string => JSON.stringify(value);
const unsafe = (value: unknown): ContractJsonInput => value as ContractJsonInput;

describe("serialized runtime-contract boundary", () => {
  test("rejects a live Proxy without executing any trap", () => {
    const valid = event(observationBody());
    let traps = 0;
    const proxy = new Proxy(valid, {
      get() {
        traps += 1;
        throw new Error("get trap executed");
      },
      getPrototypeOf() {
        traps += 1;
        throw new Error("prototype trap executed");
      },
      ownKeys() {
        traps += 1;
        throw new Error("ownKeys trap executed");
      },
    });

    expect(() => parseRuntimeEvent(unsafe(proxy))).toThrow(ContractParseError);
    expect(createRuntimeSchemaValidator().validate("runtime-event", unsafe(proxy))).toBe(false);
    expect(traps).toBe(0);
  });

  test("rejects throwing getters without reading them", () => {
    let reads = 0;
    const value = {};
    Object.defineProperty(value, "body", {
      enumerable: true,
      get() {
        reads += 1;
        throw new Error("getter executed");
      },
    });
    expect(() => parseRuntimeEvent(unsafe(value))).toThrow(ContractParseError);
    expect(reads).toBe(0);
  });

  test("reads byte length through typed-array internals instead of caller getters", () => {
    const bytes = new TextEncoder().encode(wire(event(observationBody())));
    let reads = 0;
    Object.defineProperty(bytes, "byteLength", {
      get() {
        reads += 1;
        throw new Error("byteLength getter executed");
      },
    });
    expect(parseRuntimeEvent(bytes)).toEqual(event(observationBody()));
    expect(reads).toBe(0);
  });

  test("does not export the old live-object normalizer or configurable limits", async () => {
    const source = await import("../src/index");
    expect("normalizeJsonValue" in source).toBe(false);
    expect("CANONICAL_JSON_LIMITS" in source).toBe(false);
    expect("isCanonicalJsonUtf8ByteLengthAtMost" in source).toBe(false);
    expect("utf8ByteLengthAtMost" in source).toBe(false);
    expect("freezeRunSnapshot" in source).toBe(false);
    expect("verifyRunSnapshotContentDigest" in source).toBe(false);
    expect("verifyInvocationSnapshotBinding" in source).toBe(false);
  });

  test("enforces the serialized byte cap before JSON.parse and accepts bytes", () => {
    const validWire = wire(event(observationBody()));
    expect(parseRuntimeEvent(new TextEncoder().encode(validWire))).toEqual(event(observationBody()));
    expect(() => parseRuntimeEvent(" ".repeat(MAX_SERIALIZED_JSON_BYTES + 1))).toThrow(/maximum UTF-8 byte size/);
  });

  test("terminates deep input iteratively and rejects wide input before deep work", () => {
    let deep = "0";
    for (let index = 0; index < 20_000; index += 1) deep = `[${deep}]`;
    expect(() => serializedJsonByteLength(deep)).toThrow(/depth_exceeded/);
    expect(() => parseRuntimeEvent(deep)).toThrow(ContractParseError);

    const wide = `{${Array.from({ length: 5000 }, (_, index) => `"p${index}":0`).join(",")}}`;
    expect(() => parseRuntimeEvent(wide)).toThrow(ContractParseError);
    expect(() => serializedJsonByteLength(wide)).toThrow(/collection_size_exceeded/);
  });

  test("rejects an invalid envelope without inspecting a nested live object", () => {
    let traps = 0;
    const nested = new Proxy(
      {},
      {
        get() {
          traps += 1;
          throw new Error("nested getter executed");
        },
        ownKeys() {
          traps += 1;
          throw new Error("nested ownKeys executed");
        },
      }
    );
    expect(() => parseRuntimeEvent(unsafe({ junk: nested }))).toThrow(ContractParseError);
    expect(traps).toBe(0);
  });

  test("sanitizes attacker-controlled keys and Ajv params", () => {
    const valid = event(observationBody());
    const validator = createRuntimeSchemaValidator();
    const withSecret = { ...valid, TOP_SECRET: "do not expose" };
    expect(() => parseRuntimeEvent(wire(withSecret))).toThrow(ContractParseError);
    try {
      parseRuntimeEvent(wire(withSecret));
    } catch (error) {
      expect(String(error)).not.toContain("TOP_SECRET");
      expect(error).toMatchObject({ path: "RuntimeEvent" });
    }
    const withAjvSecret = { ...valid, ATTACKER_SECRET: "do not expose" };
    expect(validator.validate("runtime-event", wire(withAjvSecret))).toBe(false);
    expect(JSON.stringify(validator.errors("runtime-event"))).not.toContain("ATTACKER_SECRET");
    expect(JSON.stringify(validator.errors("runtime-event"))).not.toContain("additionalProperty");
  });

  test("returns independent immutable validation errors across interleaved calls", () => {
    const validator = createRuntimeSchemaValidator();
    expect(validator.validate("runtime-event", wire({ protocol: "wrong" }))).toBe(false);
    const first = validator.errors("runtime-event");
    expect(first).not.toBeNull();
    expect(Object.isFrozen(first)).toBe(true);
    expect(validator.validate("runtime-exit", wire({ protocol: "wrong" }))).toBe(false);
    const second = validator.errors("runtime-exit");
    expect(second).not.toBe(first);
    expect(Object.isFrozen(second)).toBe(true);
    expect(JSON.stringify(first)).not.toContain("runtime-exit");
    expect(() => {
      if (first !== null) (first[0] as { message: string }).message = "mutated";
    }).toThrow();
    expect(validator.errors("runtime-event")?.[0]?.message).not.toBe("mutated");
  });

  test("bounds verification input arrays and error accumulation", () => {
    const oversized = wire({
      manifest: {},
      snapshot: {},
      invocation: {},
      events: Array.from({ length: 5000 }, () => ({})),
      exit: {},
      trusted: {},
    });
    const result = verifyRuntimeExecution(oversized);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.length).toBeLessThanOrEqual(256);
  });

  test("keeps raw schemas inaccessible through package exports", async () => {
    expect(packageManifest.exports).not.toHaveProperty("./schemas/v1/*");
    expect(packageRequire.resolve("@plane/agent-runtime-contract")).toMatch(/dist\/index\.mjs$/);
    const schemaSubpath = "@plane/agent-runtime-contract/schemas/v1/runtime-event.schema.json";
    expect(() => packageRequire.resolve(schemaSubpath)).toThrow(/exports/);
    expect(() => packageRequire(schemaSubpath)).toThrow(/exports/);
    await expect(import(schemaSubpath)).rejects.toThrow(/exports/);
  });
});

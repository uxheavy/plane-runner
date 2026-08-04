import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import {
  canonicalJsonEquals,
  canonicalizeJson,
  createRuntimeSchemaValidator,
  parseRuntimeEvent,
  serializedJsonByteLength,
  validateRuntimeSchema,
  verifyRuntimeExecution,
} from "../src";
import { event, observationBody } from "./fixtures";

const packageRequire = createRequire(import.meta.url);
const packageManifest = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
) as { exports: Record<string, string> };
const wire = (value: unknown): string => JSON.stringify(value);

const expectFrozenError = (error: unknown): void => {
  expect(error).toBeInstanceOf(Error);
  expect(Object.isFrozen(error)).toBe(true);
  if (typeof error !== "object" || error === null) return;
  const record = error as Record<string, unknown>;
  expect(Object.values(record).every((value) => value === null || typeof value !== "object")).toBe(true);
  expect(() => {
    record.message = "attacker";
  }).toThrow();
  expect(() => {
    Object.defineProperty(error, "code", { value: "attacker" });
  }).toThrow();
  expect(() => Object.setPrototypeOf(error, null)).toThrow();
  let deleteThrew = false;
  try {
    delete record.code;
  } catch {
    deleteThrew = true;
  }
  expect(deleteThrew || "code" in record).toBe(true);
};

describe("serialized runtime-contract boundary", () => {
  test("rejects live objects, boxed strings, functions, symbols, and proxies before inspection", () => {
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

    expect(() => parseRuntimeEvent(proxy as never)).toThrow();
    expect(validateRuntimeSchema("runtime-event", proxy as never).valid).toBe(false);
    expect(() => parseRuntimeEvent(new String(wire(valid)) as never)).toThrow();
    expect(() => parseRuntimeEvent((() => wire(valid)) as never)).toThrow();
    expect(() => parseRuntimeEvent(Symbol("wire") as never)).toThrow();
    expect(traps).toBe(0);
  });

  test("rejects every byte view without species, getter, or proxy trap execution", () => {
    const validWire = wire(event(observationBody()));
    let speciesReads = 0;
    class EvilBytes extends Uint8Array {
      static get [Symbol.species](): typeof Uint8Array {
        speciesReads += 1;
        throw new Error("species getter executed");
      }
    }
    const byteInputs: unknown[] = [
      new Uint8Array(new TextEncoder().encode(validWire)),
      new EvilBytes(new TextEncoder().encode(validWire)),
      Buffer.from(validWire),
      new DataView(new ArrayBuffer(8)),
      new ArrayBuffer(8),
      ...(typeof SharedArrayBuffer === "undefined" ? [] : [new SharedArrayBuffer(8)]),
    ];
    for (const input of byteInputs) {
      expect(() => parseRuntimeEvent(input as never)).toThrow();
      expect(validateRuntimeSchema("runtime-event", input as never).valid).toBe(false);
    }
    const proxiedBytes = new Proxy(new Uint8Array(new TextEncoder().encode(validWire)), {
      get() {
        throw new Error("byte proxy trap executed");
      },
      getPrototypeOf() {
        throw new Error("byte prototype trap executed");
      },
    });
    expect(() => parseRuntimeEvent(proxiedBytes as never)).toThrow();
    expect(speciesReads).toBe(0);
  });

  test("keeps all public wire helpers string-only and trap-free", () => {
    let traps = 0;
    const proxy = new Proxy(
      {},
      {
        get() {
          traps += 1;
          throw new Error("input getter executed");
        },
        ownKeys() {
          traps += 1;
          throw new Error("input ownKeys executed");
        },
        getPrototypeOf() {
          traps += 1;
          throw new Error("input prototype executed");
        },
      }
    );
    expect(() => canonicalizeJson(proxy as never)).toThrow();
    expect(() => serializedJsonByteLength(proxy as never)).toThrow();
    expect(() => canonicalJsonEquals(proxy as never, "null")).toThrow();
    expect(verifyRuntimeExecution(proxy as never).ok).toBe(false);
    expect(traps).toBe(0);
  });

  test("does not export byte views, mutable limits, mutable verifier state, or error constructors", async () => {
    const source = await import("../src/index");
    for (const name of [
      "UTF8_BYTE_LIMITS",
      "MAX_SERIALIZED_JSON_BYTES",
      "CONTRACT_SCHEMA_NAMES",
      "RUNTIME_SCHEMA_NAMES",
      "runtimeSemanticVerifier",
      "ContractParseError",
    ]) {
      expect(name in source).toBe(false);
    }
    for (const value of Object.values(source)) {
      expect(Array.isArray(value)).toBe(false);
      expect(value instanceof Map || value instanceof Set).toBe(false);
    }
  });

  test("enforces private exact UTF-8 bounds without a caller mutation hook", () => {
    expect(() => parseRuntimeEvent(wire(event(observationBody("x".repeat(4096)))))).not.toThrow();
    expect(() => parseRuntimeEvent(wire(event(observationBody("x".repeat(4097)))))).toThrow();
  });

  test("bounds deep work and rejects malformed/oversized serialized strings before semantic traversal", () => {
    let deep = "0";
    for (let index = 0; index < 20_000; index += 1) deep = `[${deep}]`;
    expect(() => serializedJsonByteLength(deep)).toThrow(/depth_exceeded/);
    expect(() => parseRuntimeEvent(deep)).toThrow();

    const wide = `{${Array.from({ length: 5000 }, (_, index) => `"p${index}":0`).join(",")}}`;
    expect(() => parseRuntimeEvent(wide)).toThrow();
    expect(() => serializedJsonByteLength(wide)).toThrow(/collection_size_exceeded/);
  });

  test("returns fixed discriminator errors for unknown, huge, boxed, and Proxy schema names", () => {
    const validWire = wire(event(observationBody()));
    const unknown = validateRuntimeSchema("x".repeat(100_000), validWire);
    const boxed = validateRuntimeSchema(new String("runtime-event"), validWire);
    let traps = 0;
    const proxy = new Proxy(
      { schema: "runtime-event" },
      {
        get() {
          traps += 1;
          throw new Error("schema trap executed");
        },
      }
    );
    const proxied = validateRuntimeSchema(proxy, validWire);
    for (const result of [unknown, boxed, proxied]) {
      expect(result).toEqual({
        valid: false,
        errors: [
          {
            instancePath: "",
            schemaPath: "#",
            keyword: "x-plane-schema-name",
            params: {},
            message: "unknown runtime schema",
          },
        ],
      });
      expect(Object.isFrozen(result)).toBe(true);
      expect(Object.isFrozen(result.errors)).toBe(true);
      expect(Object.isFrozen(result.errors?.[0])).toBe(true);
      expect(Object.isFrozen(result.errors?.[0]?.params)).toBe(true);
    }
    expect(traps).toBe(0);
  });

  test("has no mutable singleton validator and removes call-stateful errors compatibility", () => {
    const validator = createRuntimeSchemaValidator();
    expect(Object.isFrozen(validator)).toBe(true);
    expect("errors" in validator).toBe(false);
    expect(validator.validate("runtime-event", wire(event(observationBody())))).toBe(true);
    expect(() => {
      (validator as { validate: unknown }).validate = () => true;
    }).toThrow();
    expect(validator.validate("runtime-event", "{}" as never)).toBe(false);
  });

  test("freezes caught parse and canonicalization errors with no attacker data", () => {
    const attacker = wire({ TOP_SECRET: "do not expose", body: "attacker" });
    let parseError: unknown;
    try {
      parseRuntimeEvent(attacker);
    } catch (error) {
      parseError = error;
    }
    expectFrozenError(parseError);
    expect(String(parseError)).not.toContain("TOP_SECRET");
    expect(String(parseError)).not.toContain("do not expose");

    let canonicalError: unknown;
    try {
      let deep = "0";
      for (let index = 0; index < 100; index += 1) deep = `[${deep}]`;
      canonicalizeJson(deep);
    } catch (error) {
      canonicalError = error;
    }
    expectFrozenError(canonicalError);
  });

  test("freezes independent schema results and verification errors", () => {
    const first = validateRuntimeSchema("runtime-event", "{}");
    const second = validateRuntimeSchema("runtime-event", "{}");
    expect(first).not.toBe(second);
    expect(first.errors).not.toBe(second.errors);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.errors)).toBe(true);
    expect(Object.isFrozen(first.errors?.[0])).toBe(true);
    expect(Object.isFrozen(first.errors?.[0]?.params)).toBe(true);
    expect(() => {
      if (first.errors) (first.errors[0] as { message: string }).message = "mutated";
    }).toThrow();

    const verification = verifyRuntimeExecution("{}");
    expect(verification.ok).toBe(false);
    expect(Object.isFrozen(verification)).toBe(true);
    if (!verification.ok) {
      expect(Object.isFrozen(verification.errors)).toBe(true);
      expect(Object.isFrozen(verification.errors[0])).toBe(true);
    }
  });

  test("keeps raw schemas and internal modules inaccessible through package exports", async () => {
    expect(packageManifest.exports).not.toHaveProperty("./schemas/v1/*");
    expect(packageRequire.resolve("@plane/agent-runtime-contract")).toMatch(/dist\/index\.mjs$/);
    const inaccessibleSubpaths = [
      "schemas/v1/runtime-event.schema.json",
      "src/contracts",
      "src/schema-validator",
      "src/internal-byte-utils",
      "src/internal-utf8-utils",
    ];
    await Promise.all(
      inaccessibleSubpaths.map(async (subpath) => {
        const specifier = `@plane/agent-runtime-contract/${subpath}`;
        expect(() => packageRequire.resolve(specifier)).toThrow(/exports/);
        expect(() => packageRequire(specifier)).toThrow(/exports/);
        await expect(import(specifier)).rejects.toThrow(/exports/);
      })
    );
  });
});

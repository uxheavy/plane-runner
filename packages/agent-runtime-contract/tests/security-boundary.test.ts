import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, test } from "vitest";

import {
  CANONICAL_JSON_LIMITS,
  ContractParseError,
  canonicalJsonEquals,
  createRuntimeSchemaValidator,
  parseRuntimeEvent,
  serializedJsonByteLength,
} from "../src";
import runtimeEventSchema from "../schemas/v1/runtime-event.schema.json" with { type: "json" };
import { appliedFailureBody, event, observationBody } from "./fixtures";

const packageManifest = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
) as { exports: Record<string, string> };
const packageRequire = createRequire(import.meta.url);

describe("schema-validation boundary remediation reproductions", () => {
  test("rejects inherited prototypes", () => {
    const valid = event(observationBody());
    const inherited = Object.create(valid) as Record<string, unknown>;
    Object.defineProperties(inherited, Object.getOwnPropertyDescriptors(valid));

    expect(() => parseRuntimeEvent(inherited)).toThrow(ContractParseError);
  });

  test("never invokes accessors", () => {
    const valid = event(observationBody());
    const getter = { ...valid } as Record<string, unknown>;
    Object.defineProperty(getter, "observedAt", {
      enumerable: true,
      get() {
        throw new Error("getter invoked");
      },
    });
    expect(() => parseRuntimeEvent(getter)).toThrow(ContractParseError);
  });

  test("does not expose raw schemas as an ordinary package subpath", () => {
    expect(packageManifest.exports).not.toHaveProperty("./schemas/v1/*");
    expect(packageRequire.resolve("@plane/agent-runtime-contract")).toMatch(/dist\/index\.mjs$/);
    expect(() => packageRequire.resolve("@plane/agent-runtime-contract/schemas/v1/runtime-event.schema.json")).toThrow(
      /exports/
    );
  });

  test("supported validation rejects violations that ordinary Ajv would accept directly", () => {
    const plainAjv = new Ajv2020({ strict: false });
    const plainValidate = plainAjv.compile(runtimeEventSchema);
    const supportedValidator = createRuntimeSchemaValidator();

    const overByteEvent = {
      ...event(observationBody()),
      body: {
        ...event(observationBody()).body,
        payload: { kind: "inline_text", contentType: "text/plain", text: "é".repeat(2049) },
        publication: { action: "observation_only" },
        kind: "progress_observed",
      },
    };
    // The generated transport artifact is intentionally not self-authoritative;
    // this remains true only for direct filesystem access, not a package API.
    expect(plainValidate(overByteEvent)).toBe(true);
    expect(supportedValidator.validate("runtime-event", overByteEvent)).toBe(false);

    const mismatchedEqualityEvent = {
      ...event(appliedFailureBody()),
      body: {
        ...event(appliedFailureBody()).body,
        publication: {
          ...event(appliedFailureBody()).body.publication,
          productRef: "product-event:other",
        },
      },
    };
    expect(plainValidate(mismatchedEqualityEvent)).toBe(true);
    expect(supportedValidator.validate("runtime-event", mismatchedEqualityEvent)).toBe(false);
    expect(() => new Ajv2020({ strict: true }).compile(runtimeEventSchema)).toThrow();
  });

  test("normalizes null-prototype JSON and rejects unsafe object shapes", () => {
    const valid = event(observationBody());
    const nullPrototype = Object.assign(Object.create(null), valid);
    expect(() => parseRuntimeEvent(nullPrototype)).not.toThrow();

    const pollution = { ...valid } as Record<string, unknown>;
    Object.defineProperty(pollution, "__proto__", { enumerable: true, value: {} });
    expect(() => parseRuntimeEvent(pollution)).toThrow(ContractParseError);

    const inherited = Object.create({ observedAt: valid.observedAt }) as Record<string, unknown>;
    Object.defineProperties(inherited, Object.getOwnPropertyDescriptors(valid));
    expect(() => parseRuntimeEvent(inherited)).toThrow(ContractParseError);
    expect(() => parseRuntimeEvent([])).toThrow(ContractParseError);
    expect(() => parseRuntimeEvent(new Date())).toThrow(ContractParseError);
    expect(() => parseRuntimeEvent(new Map())).toThrow(ContractParseError);
    expect(() => parseRuntimeEvent(new Set())).toThrow(ContractParseError);
  });

  test("rejects accessors, sparse arrays, cycles, and unsupported scalar values deterministically", () => {
    const valid = event(observationBody());
    const getter = { ...valid } as Record<string, unknown>;
    Object.defineProperty(getter, "observedAt", {
      enumerable: true,
      get() {
        throw new Error("secret-getter-input");
      },
    });
    expect(() => parseRuntimeEvent(getter)).toThrow(ContractParseError);

    const validator = createRuntimeSchemaValidator();
    expect(validator.validate("runtime-event", getter)).toBe(false);
    expect(validator.errors("runtime-event")).toEqual([
      {
        instancePath: "",
        schemaPath: "#",
        keyword: "x-plane-safe-json",
        params: { reason: "unsupported_or_unbounded_input" },
        message: "must be bounded plain JSON data",
      },
    ]);
    expect(JSON.stringify(validator.errors("runtime-event"))).not.toContain("secret-getter-input");

    const sparse: unknown[] = [];
    sparse.length = 1;
    expect(() => parseRuntimeEvent(sparse)).toThrow(ContractParseError);

    const cyclic = { ...valid } as Record<string, unknown>;
    cyclic.body = cyclic;
    expect(() => parseRuntimeEvent(cyclic)).toThrow(/cyclic JSON value/);

    for (const unsupported of [undefined, 1n, Symbol("unsupported"), () => undefined]) {
      expect(() => parseRuntimeEvent(unsupported)).toThrow(ContractParseError);
    }
  });

  test("bounds depth, node count, strings, and canonical work before materializing output", () => {
    let deep: unknown = 0;
    for (let index = 0; index <= CANONICAL_JSON_LIMITS.maxDepth; index += 1) {
      deep = [deep];
    }
    expect(() => serializedJsonByteLength(deep)).toThrow(/depth_exceeded/);

    const manyNodes = Object.fromEntries(
      Array.from({ length: CANONICAL_JSON_LIMITS.maxCollectionItems }, (_, index) => [index, [0, 0]])
    );
    expect(() => serializedJsonByteLength(manyNodes)).toThrow(/node_count_exceeded/);

    const huge = "x".repeat(CANONICAL_JSON_LIMITS.maxStringBytes + 1);
    expect(() => serializedJsonByteLength(huge)).toThrow(/string_bytes_exceeded/);

    const oversizedCanonical = "x".repeat(CANONICAL_JSON_LIMITS.maxCanonicalBytes);
    expect(() => serializedJsonByteLength(oversizedCanonical)).toThrow(/serialized_bytes_exceeded/);
  });

  test("uses exact own-property equality with bounded normalization", () => {
    expect(canonicalJsonEquals({ a: 1, b: ["x", true] }, { b: ["x", true], a: 1 })).toBe(true);
    expect(canonicalJsonEquals(Object.assign(Object.create(null), { a: 1 }), { a: 2 })).toBe(false);

    const inherited = Object.create({ a: 1 });
    expect(() => canonicalJsonEquals(inherited, { a: 1 })).toThrow(/unsupported_prototype/);
  });
});

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { describe, expect, test, vi } from "vitest";

import {
  canonicalJsonEquals,
  canonicalizeJson,
  createActorRef,
  createApplicationServiceRef,
  createArtifactRef,
  createAssignmentRef,
  createAuditReceiptRef,
  createAuthorizationReceiptRef,
  createCancellationRef,
  createContentDigest,
  createContractDigest,
  createContextRef,
  createCorrelationId,
  createOperationAttemptRef,
  createOutcomeSubmissionRef,
  createProfileVersionRef,
  createRunSnapshotContentDigest,
  createRunId,
  createRuntimeSchemaValidator,
  createTargetRef,
  createWorkspaceRef,
  parseContentDigest,
  parseActorRef,
  parseApplicationServiceRef,
  parseArtifactRef,
  parseAssignmentRef,
  parseAuditReceiptRef,
  parseAuthorizationReceiptRef,
  parseCancellationRef,
  parseContextRef,
  parseCorrelationId,
  parseContractDigest,
  parseOperationAttemptRef,
  parseOutcomeSubmissionRef,
  parseProfileVersionRef,
  parseRunSnapshotContentDigest,
  parseRuntimeEvent,
  parseRunId,
  parseTargetRef,
  parseWorkspaceRef,
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

  test("rejects oversized schema names before closed-set lookup", () => {
    const validWire = wire(event(observationBody()));
    const lookup = vi.spyOn(Set.prototype, "has");
    try {
      lookup.mockClear();
      expect(validateRuntimeSchema("x".repeat(1_000_000), validWire)).toEqual({
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
      expect(lookup).not.toHaveBeenCalled();
    } finally {
      lookup.mockRestore();
    }
  });

  const assertMinimalImpossibleNamespaceSuffixes = (): void => {
    const namespaceCases: readonly {
      namespace: string;
      create: (value: string) => unknown;
      parse: (value: unknown) => unknown;
    }[] = [
      { namespace: "run", create: createRunId, parse: parseRunId },
      { namespace: "actor", create: createActorRef, parse: parseActorRef },
      { namespace: "target", create: createTargetRef, parse: parseTargetRef },
      { namespace: "context", create: createContextRef, parse: parseContextRef },
      { namespace: "artifact", create: createArtifactRef, parse: parseArtifactRef },
      { namespace: "workspace", create: createWorkspaceRef, parse: parseWorkspaceRef },
      { namespace: "assignment", create: createAssignmentRef, parse: parseAssignmentRef },
      { namespace: "correlation", create: createCorrelationId, parse: parseCorrelationId },
      { namespace: "cancellation", create: createCancellationRef, parse: parseCancellationRef },
      { namespace: "audit-receipt", create: createAuditReceiptRef, parse: parseAuditReceiptRef },
      { namespace: "profile-version", create: createProfileVersionRef, parse: parseProfileVersionRef },
      { namespace: "operation-attempt", create: createOperationAttemptRef, parse: parseOperationAttemptRef },
      { namespace: "outcome-submission", create: createOutcomeSubmissionRef, parse: parseOutcomeSubmissionRef },
      { namespace: "application-service", create: createApplicationServiceRef, parse: parseApplicationServiceRef },
      {
        namespace: "authorization-receipt",
        create: createAuthorizationReceiptRef,
        parse: parseAuthorizationReceiptRef,
      },
    ];
    const originalRegexTest = RegExp.prototype.test;
    const regex = vi.spyOn(RegExp.prototype, "test");
    const concat = vi.spyOn(String.prototype, "concat");
    const charCodeAt = vi.spyOn(String.prototype, "charCodeAt");
    const startsWith = vi.spyOn(String.prototype, "startsWith");
    const normalize = vi.spyOn(String.prototype, "normalize");
    const slice = vi.spyOn(String.prototype, "slice");
    let hostileSuffix = "";
    let hostileInput = "";
    let hostileRegexCalls = 0;
    regex.mockImplementation(function (this: RegExp, value: string) {
      if (value === hostileSuffix || value === hostileInput) hostileRegexCalls += 1;
      return originalRegexTest.call(this, value);
    });
    try {
      expect(createContextRef("a".repeat(120))).toHaveLength(128);
      expect(parseContextRef(`context:${"a".repeat(120)}`)).toHaveLength(128);
      expect(regex).toHaveBeenCalled();
      expect(concat).toHaveBeenCalled();
      expect(charCodeAt).toHaveBeenCalled();
      expect(startsWith).toHaveBeenCalled();

      const assertNoHostileWork = (operation: () => unknown): void => {
        regex.mockClear();
        concat.mockClear();
        charCodeAt.mockClear();
        startsWith.mockClear();
        normalize.mockClear();
        slice.mockClear();
        hostileRegexCalls = 0;

        let rejected = false;
        try {
          operation();
        } catch {
          rejected = true;
        }
        const pathCalls = {
          hostileRegex: hostileRegexCalls,
          concat: concat.mock.calls.length,
          charCodeAt: charCodeAt.mock.calls.length,
          startsWith: startsWith.mock.calls.length,
          normalize: normalize.mock.calls.length,
          slice: slice.mock.calls.length,
        };
        expect(rejected).toBe(true);
        expect(pathCalls).toEqual({
          hostileRegex: 0,
          concat: 0,
          charCodeAt: 0,
          startsWith: 0,
          normalize: 0,
          slice: 0,
        });
      };

      for (const { namespace, create, parse } of namespaceCases) {
        const maximumSuffixLength = Math.min(120, 128 - namespace.length - 1);
        hostileSuffix = "a".repeat(maximumSuffixLength + 1);
        hostileInput = `${namespace}:${hostileSuffix}`;
        assertNoHostileWork(() => create(hostileSuffix));
        assertNoHostileWork(() => parse(hostileInput));
      }
    } finally {
      regex.mockRestore();
      concat.mockRestore();
      charCodeAt.mockRestore();
      startsWith.mockRestore();
      normalize.mockRestore();
      slice.mockRestore();
    }
  };

  test("rejects oversized digest and reference values before proportional scans", () => {
    const oversized = "a".repeat(1_000_000);
    const oversizedContent = `content:${oversized}`;
    const oversizedSnapshot = `snapshot:${oversized}`;
    const originalCharCodeAt = String.prototype.charCodeAt;
    const charCodeAt = vi.spyOn(String.prototype, "charCodeAt");
    let oversizedValueScanned = false;
    charCodeAt.mockImplementation(function (this: string, index: number) {
      if (this.length > 128) oversizedValueScanned = true;
      return originalCharCodeAt.call(this, index);
    });
    try {
      const rejected = [
        () => createContractDigest(oversized),
        () => parseContractDigest(oversized),
        () => createContentDigest(oversized),
        () => parseContentDigest(oversizedContent),
        () => createRunSnapshotContentDigest(oversized),
        () => parseRunSnapshotContentDigest(oversizedSnapshot),
        () => createWorkspaceRef(oversized),
        () => parseWorkspaceRef(oversized),
      ];
      for (const operation of rejected) expect(operation).toThrow();
      expect(oversizedValueScanned).toBe(false);
    } finally {
      charCodeAt.mockRestore();
    }
    assertMinimalImpossibleNamespaceSuffixes();
  });

  test("keeps multibyte digest scans within the private digest maximum", () => {
    const value = "🙂".repeat(18);
    const inspectedIndexes: number[] = [];
    const originalCharCodeAt = String.prototype.charCodeAt;
    const charCodeAt = vi.spyOn(String.prototype, "charCodeAt");
    charCodeAt.mockImplementation(function (this: string, index: number) {
      if (this === value) inspectedIndexes.push(index);
      return originalCharCodeAt.call(this, index);
    });
    try {
      expect(() => createContractDigest(value)).toThrow();
      expect(() => createContentDigest(value)).toThrow();
      expect(() => createRunSnapshotContentDigest(value)).toThrow();
      expect(inspectedIndexes.length).toBeGreaterThan(0);
      expect(Math.max(...inspectedIndexes)).toBeLessThan(value.length - 1);
    } finally {
      charCodeAt.mockRestore();
    }
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

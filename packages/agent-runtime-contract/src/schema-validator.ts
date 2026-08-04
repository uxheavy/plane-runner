import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";

import invocationEnvelopeSchema from "../schemas/v1/invocation-envelope.schema.json" with { type: "json" };
import runSnapshotSchema from "../schemas/v1/run-snapshot.schema.json" with { type: "json" };
import runtimeDurableStateSchema from "../schemas/v1/runtime-durable-state.schema.json" with { type: "json" };
import runtimeEventSchema from "../schemas/v1/runtime-event.schema.json" with { type: "json" };
import runtimeExitSchema from "../schemas/v1/runtime-exit.schema.json" with { type: "json" };
import { PLANE_AGENT_RUNTIME_PROTOCOL, type ContractJsonInput } from "./contracts";
import { utf8ByteLengthAtMost } from "./internal-utf8-utils";

const MAX_SERIALIZED_JSON_BYTES = 1_048_576;
const MAX_DEPTH = 64;
const MAX_NODES = 10_000;
const MAX_COLLECTION_ITEMS = 4096;
const MAX_WORK = 32 * 1024 * 1024;

const schemaDefinitions = {
  "run-snapshot": runSnapshotSchema,
  "invocation-envelope": invocationEnvelopeSchema,
  "runtime-event": runtimeEventSchema,
  "runtime-exit": runtimeExitSchema,
  "runtime-durable-state": runtimeDurableStateSchema,
} as const;

const RUNTIME_SCHEMA_NAMES = [
  "run-snapshot",
  "invocation-envelope",
  "runtime-event",
  "runtime-exit",
  "runtime-durable-state",
] as const;
const RUNTIME_SCHEMA_NAME_MAX_LENGTH = RUNTIME_SCHEMA_NAMES.reduce(
  (maximum, name) => Math.max(maximum, name.length),
  0
);
const RUNTIME_SCHEMA_NAME_SET = new Set<keyof typeof schemaDefinitions>(RUNTIME_SCHEMA_NAMES);

const requiredProperties = {
  "run-snapshot": [
    "protocol",
    "workspaceRef",
    "runId",
    "assignment",
    "actorRef",
    "profile",
    "context",
    "toolCatalog",
    "runtimePolicy",
    "totalBudget",
    "contractDigests",
    "contentDigest",
  ],
  "invocation-envelope": [
    "protocol",
    "workspaceRef",
    "actorRef",
    "runId",
    "invocationId",
    "runSnapshotDigest",
    "trigger",
    "newContextEventRefs",
    "remainingBudget",
    "lease",
    "cancellationRef",
    "causationRef",
    "correlationId",
    "idempotencyKey",
  ],
  "runtime-event": [
    "protocol",
    "trust",
    "workspaceRef",
    "actorRef",
    "runId",
    "invocationId",
    "sequence",
    "eventId",
    "idempotencyKey",
    "correlationId",
    "causationRef",
    "observedAt",
    "body",
  ],
  "runtime-exit": [
    "protocol",
    "authority",
    "workspaceRef",
    "actorRef",
    "runId",
    "invocationId",
    "finalSequence",
    "idempotencyKey",
    "correlationId",
    "causationRef",
    "kind",
  ],
  "runtime-durable-state": [
    "protocol",
    "stateVersion",
    "binding",
    "state",
    "revision",
    "stateDigest",
    "lastAcceptedSequence",
    "acceptedEvents",
    "acceptedHumanInputAnswers",
    "acceptedExits",
  ],
} as const;

const optionalProperties = {
  "run-snapshot": [],
  "invocation-envelope": ["checkpointRef"],
  "runtime-event": [],
  "runtime-exit": ["inputEventRef", "failure"],
  "runtime-durable-state": ["previousRevision", "previousStateDigest", "terminal", "pendingInput"],
} as const;

export type RuntimeSchemaName = keyof typeof schemaDefinitions;

export type SafeValidationError = Readonly<{
  instancePath: "";
  schemaPath: "#";
  keyword: "x-plane-schema-name" | "x-plane-safe-json";
  params: Readonly<Record<string, never>>;
  message: "unknown runtime schema" | "contract value is invalid";
}>;

export type RuntimeSchemaValidationResult = Readonly<{
  valid: boolean;
  errors: readonly SafeValidationError[] | null;
}>;

export type RuntimeSchemaValidator = Readonly<{
  validate(name: unknown, value: ContractJsonInput): boolean;
}>;

const isKnownRuntimeSchemaName = (value: unknown): value is RuntimeSchemaName =>
  typeof value === "string" &&
  value.length <= RUNTIME_SCHEMA_NAME_MAX_LENGTH &&
  RUNTIME_SCHEMA_NAME_SET.has(value as RuntimeSchemaName);

const schemaNameError = (): readonly SafeValidationError[] =>
  Object.freeze([
    Object.freeze({
      instancePath: "" as const,
      schemaPath: "#" as const,
      keyword: "x-plane-schema-name" as const,
      params: Object.freeze({}),
      message: "unknown runtime schema" as const,
    }),
  ]);

const valueError = (): readonly SafeValidationError[] =>
  Object.freeze([
    Object.freeze({
      instancePath: "" as const,
      schemaPath: "#" as const,
      keyword: "x-plane-safe-json" as const,
      params: Object.freeze({}),
      message: "contract value is invalid" as const,
    }),
  ]);

const invalidSchemaResult = (): RuntimeSchemaValidationResult =>
  Object.freeze({ valid: false, errors: schemaNameError() });

const invalidValueResult = (): RuntimeSchemaValidationResult => Object.freeze({ valid: false, errors: valueError() });

const validResult = (): RuntimeSchemaValidationResult => Object.freeze({ valid: true, errors: null });

function decodeSerializedJson(value: unknown): unknown {
  if (
    typeof value !== "string" ||
    value.length > MAX_SERIALIZED_JSON_BYTES ||
    !utf8ByteLengthAtMost(value, MAX_SERIALIZED_JSON_BYTES)
  ) {
    return undefined;
  }
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return undefined;
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

function cheapRootCheck(name: RuntimeSchemaName, value: unknown): boolean {
  if (!isRecord(value) || value.protocol !== PLANE_AGENT_RUNTIME_PROTOCOL) return false;
  const allowed = new Set<string>([...requiredProperties[name], ...optionalProperties[name]]);
  let propertyCount = 0;
  for (const key in value) {
    if (!Object.hasOwn(value, key)) continue;
    propertyCount += 1;
    if (propertyCount > MAX_COLLECTION_ITEMS || !allowed.has(key)) return false;
  }
  return requiredProperties[name].every((key) => Object.hasOwn(value, key));
}

const utf8Bytes = (value: string): number => {
  let bytes = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff && value.charCodeAt(index + 1) >= 0xdc00) {
      bytes += 4;
      index += 1;
    } else if (codeUnit <= 0x7f) {
      bytes += 1;
    } else if (codeUnit <= 0x7ff) {
      bytes += 2;
    } else {
      bytes += 3;
    }
  }
  return bytes;
};

function boundedJsonByteLength(value: unknown): number | undefined {
  type Frame = { value: object; keys: string[]; index: number; array: boolean };
  const stack: Frame[] = [];
  let bytes = 0;
  let work = 0;
  let nodes = 0;
  const add = (amount: number) => {
    bytes += amount;
    work += amount + 1;
    if (bytes > MAX_SERIALIZED_JSON_BYTES || work > MAX_WORK) throw new Error();
  };
  const push = (candidate: unknown, depth: number): void => {
    if (depth > MAX_DEPTH) throw new Error();
    nodes += 1;
    if (nodes > MAX_NODES) throw new Error();
    if (candidate === null) {
      add(4);
      return;
    }
    if (typeof candidate === "string") {
      add(utf8Bytes(JSON.stringify(candidate)));
      return;
    }
    if (typeof candidate === "boolean") {
      add(candidate ? 4 : 5);
      return;
    }
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      add(utf8Bytes(JSON.stringify(candidate)));
      return;
    }
    if (candidate === null || typeof candidate !== "object") throw new Error();
    if (Array.isArray(candidate)) {
      if (candidate.length > MAX_COLLECTION_ITEMS) throw new Error();
      add(1);
      stack.push({
        value: candidate,
        keys: Array.from({ length: candidate.length }, (_, index) => String(index)),
        index: 0,
        array: true,
      });
      return;
    }
    const keys: string[] = [];
    for (const key in candidate) {
      if (Object.hasOwn(candidate, key)) {
        keys.push(key);
        if (keys.length > MAX_COLLECTION_ITEMS) throw new Error();
      }
    }
    add(1);
    stack.push({ value: candidate, keys, index: 0, array: false });
  };
  push(value, 0);
  while (stack.length > 0) {
    const frame = stack[stack.length - 1];
    if (frame.index === frame.keys.length) {
      add(1);
      stack.pop();
      continue;
    }
    if (frame.index > 0) add(1);
    const key = frame.keys[frame.index];
    frame.index += 1;
    if (!frame.array) add(utf8Bytes(JSON.stringify(key)) + 1);
    const child = (frame.value as Record<string, unknown>)[key];
    push(child, stack.length);
  }
  return bytes;
}

const utf8ByteMaxValidator = (limit: number, value: unknown): boolean =>
  typeof value === "string" && utf8ByteLengthAtMost(value, limit);

const equalPropertiesValidator = (pairs: unknown, value: unknown): boolean => {
  if (!isRecord(value) || !Array.isArray(pairs)) return false;
  return pairs.every(
    (pair) =>
      Array.isArray(pair) &&
      pair.length === 2 &&
      typeof pair[0] === "string" &&
      typeof pair[1] === "string" &&
      Object.hasOwn(value, pair[0]) &&
      Object.hasOwn(value, pair[1]) &&
      value[pair[0]] === value[pair[1]]
  );
};

const serializedUtf8ByteMaxValidator = (limit: number, value: unknown): boolean => {
  try {
    const length = boundedJsonByteLength(value);
    return length !== undefined && length <= limit;
  } catch {
    return false;
  }
};

function compileValidators(): Record<RuntimeSchemaName, ValidateFunction> {
  const ajv = new Ajv2020({ allErrors: false, strict: true, strictRequired: false, strictTypes: false });
  ajv.addKeyword({ keyword: "x-utf8ByteMax", type: "string", schemaType: "number", validate: utf8ByteMaxValidator });
  ajv.addKeyword({
    keyword: "x-equalProperties",
    type: "object",
    schemaType: "array",
    validate: equalPropertiesValidator,
  });
  ajv.addKeyword({
    keyword: "x-serializedUtf8ByteMax",
    type: "object",
    schemaType: "number",
    validate: serializedUtf8ByteMaxValidator,
  });
  return Object.fromEntries(
    Object.entries(schemaDefinitions).map(([name, schema]) => [name, ajv.compile(schema)])
  ) as Record<RuntimeSchemaName, ValidateFunction>;
}

export function validateRuntimeSchema(name: unknown, value: ContractJsonInput): RuntimeSchemaValidationResult {
  if (!isKnownRuntimeSchemaName(name)) return invalidSchemaResult();
  const decoded = decodeSerializedJson(value);
  if (decoded === undefined || !cheapRootCheck(name, decoded)) return invalidValueResult();
  try {
    return compileValidators()[name](decoded) ? validResult() : invalidValueResult();
  } catch {
    return invalidValueResult();
  }
}

/** Validate one bounded JSON string without exposing parser or validator state. */
export function createRuntimeSchemaValidator(): RuntimeSchemaValidator {
  return Object.freeze({
    validate(name: unknown, value: ContractJsonInput): boolean {
      return validateRuntimeSchema(name, value).valid;
    },
  });
}

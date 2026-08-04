import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";

import invocationEnvelopeSchema from "../schemas/v1/invocation-envelope.schema.json" with { type: "json" };
import runSnapshotSchema from "../schemas/v1/run-snapshot.schema.json" with { type: "json" };
import runtimeDurableStateSchema from "../schemas/v1/runtime-durable-state.schema.json" with { type: "json" };
import runtimeEventSchema from "../schemas/v1/runtime-event.schema.json" with { type: "json" };
import runtimeExitSchema from "../schemas/v1/runtime-exit.schema.json" with { type: "json" };
import { MAX_SERIALIZED_JSON_BYTES, PLANE_AGENT_RUNTIME_PROTOCOL, type ContractJsonInput } from "./contracts";
import { copyUint8Array, uint8ArrayByteLength, utf8ByteLengthAtMost } from "./internal-byte-utils";

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

const requiredProperties: Record<RuntimeSchemaName, readonly string[]> = {
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
};

const optionalProperties: Record<RuntimeSchemaName, readonly string[]> = {
  "run-snapshot": [],
  "invocation-envelope": ["checkpointRef"],
  "runtime-event": [],
  "runtime-exit": ["inputEventRef", "failure"],
  "runtime-durable-state": ["previousRevision", "previousStateDigest", "terminal", "pendingInput"],
};

const safeBoundaryError = (): readonly SafeValidationError[] =>
  Object.freeze([
    Object.freeze({
      instancePath: "",
      schemaPath: "#",
      keyword: "x-plane-safe-json",
      params: Object.freeze({}),
      message: "input must be bounded serialized JSON",
    }),
  ]);

export const RUNTIME_SCHEMA_NAMES = Object.keys(schemaDefinitions) as [
  keyof typeof schemaDefinitions,
  ...(keyof typeof schemaDefinitions)[],
];

export type RuntimeSchemaName = keyof typeof schemaDefinitions;

export type SafeValidationError = Readonly<{
  instancePath: "";
  schemaPath: string;
  keyword: string;
  params: Readonly<Record<string, never>>;
  message: string;
}>;

export type RuntimeSchemaValidator = Readonly<{
  validate(name: RuntimeSchemaName, value: ContractJsonInput): boolean;
  errors(name: RuntimeSchemaName): readonly SafeValidationError[] | null;
}>;

const isUint8Array = (value: unknown): value is Uint8Array => ArrayBuffer.isView(value) && value instanceof Uint8Array;

function decodeSerializedJson(value: ContractJsonInput): unknown {
  let text: string;
  if (typeof value === "string") {
    if (!utf8ByteLengthAtMost(value, MAX_SERIALIZED_JSON_BYTES)) return undefined;
    text = value;
  } else if (isUint8Array(value)) {
    if (uint8ArrayByteLength(value) > MAX_SERIALIZED_JSON_BYTES) return undefined;
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(copyUint8Array(value));
    } catch {
      return undefined;
    }
  } else {
    return undefined;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

function cheapRootCheck(name: RuntimeSchemaName, value: unknown): boolean {
  if (!isRecord(value) || value.protocol !== PLANE_AGENT_RUNTIME_PROTOCOL) return false;
  const allowed = new Set([...requiredProperties[name], ...optionalProperties[name]]);
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
    if (!frame.array) {
      add(utf8Bytes(JSON.stringify(key)) + 1);
    }
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

function sanitizeAjvError(error: ErrorObject): SafeValidationError {
  const schemaPath = /^#[A-Za-z0-9_./~$-]*$/.test(error.schemaPath) ? error.schemaPath : "#";
  return Object.freeze({
    instancePath: "",
    schemaPath,
    keyword: error.keyword,
    params: Object.freeze({}),
    message: "contract value is invalid",
  });
}

/** Validate serialized contract bytes without exposing Ajv state or accepting live objects. */
export function createRuntimeSchemaValidator(): RuntimeSchemaValidator {
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

  const validators = Object.fromEntries(
    Object.entries(schemaDefinitions).map(([name, schema]) => [name, ajv.compile(schema)])
  ) as Record<RuntimeSchemaName, ValidateFunction>;
  const validationErrors = new Map<RuntimeSchemaName, readonly SafeValidationError[] | null>();

  return {
    validate(name, value) {
      const decoded = decodeSerializedJson(value);
      if (decoded === undefined || !cheapRootCheck(name, decoded)) {
        validationErrors.set(name, safeBoundaryError());
        return false;
      }
      try {
        const valid = validators[name](decoded);
        const errors = validators[name].errors;
        validationErrors.set(
          name,
          valid || errors === null || errors === undefined ? null : Object.freeze(errors.map(sanitizeAjvError))
        );
        return valid;
      } catch {
        validationErrors.set(name, safeBoundaryError());
        return false;
      }
    },
    errors(name) {
      const errors = validationErrors.get(name);
      return errors === null || errors === undefined
        ? (errors ?? null)
        : Object.freeze(errors.map((error) => Object.freeze({ ...error, params: Object.freeze({}) })));
    },
  };
}

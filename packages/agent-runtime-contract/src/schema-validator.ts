import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";

import invocationEnvelopeSchema from "../schemas/v1/invocation-envelope.schema.json" with { type: "json" };
import runSnapshotSchema from "../schemas/v1/run-snapshot.schema.json" with { type: "json" };
import runtimeDurableStateSchema from "../schemas/v1/runtime-durable-state.schema.json" with { type: "json" };
import runtimeEventSchema from "../schemas/v1/runtime-event.schema.json" with { type: "json" };
import runtimeExitSchema from "../schemas/v1/runtime-exit.schema.json" with { type: "json" };
import { canonicalizeJson } from "./contracts";

const utf8Encoder = new TextEncoder();

const utf8ByteMaxValidator = (limit: number, value: unknown): boolean =>
  typeof value === "string" && utf8Encoder.encode(value).byteLength <= limit;

const equalPropertiesValidator = (pairs: unknown, value: unknown): boolean => {
  if (value === null || typeof value !== "object" || !Array.isArray(pairs)) {
    return false;
  }

  const object = value as Record<string, unknown>;
  return pairs.every(
    (pair) =>
      Array.isArray(pair) &&
      pair.length === 2 &&
      typeof pair[0] === "string" &&
      typeof pair[1] === "string" &&
      object[pair[0]] === object[pair[1]]
  );
};

const serializedUtf8ByteMaxValidator = (limit: number, value: unknown): boolean => {
  try {
    return utf8Encoder.encode(canonicalizeJson(value)).byteLength <= limit;
  } catch {
    return false;
  }
};

const schemaDefinitions = {
  "run-snapshot": runSnapshotSchema,
  "invocation-envelope": invocationEnvelopeSchema,
  "runtime-event": runtimeEventSchema,
  "runtime-exit": runtimeExitSchema,
  "runtime-durable-state": runtimeDurableStateSchema,
} as const;

export const RUNTIME_SCHEMA_NAMES = Object.keys(schemaDefinitions) as [
  keyof typeof schemaDefinitions,
  ...(keyof typeof schemaDefinitions)[],
];

export type RuntimeSchemaName = keyof typeof schemaDefinitions;

export type RuntimeSchemaValidator = Readonly<{
  validate(name: RuntimeSchemaName, value: unknown): boolean;
  errors(name: RuntimeSchemaName): readonly ErrorObject[] | null;
}>;

/**
 * The authoritative JSON-Schema entry point for plane.agent-runtime/v1.
 *
 * The checked-in schemas intentionally use Plane-owned keywords for UTF-8 byte
 * limits, canonical serialized-size limits, and cross-property identity. A
 * plain Ajv instance is therefore only a partial JSON-Schema interpreter and
 * must not be used as the runtime contract validator.
 */
export function createRuntimeSchemaValidator(): RuntimeSchemaValidator {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  ajv.addKeyword({
    keyword: "x-utf8ByteMax",
    type: "string",
    schemaType: "number",
    validate: utf8ByteMaxValidator,
  });
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

  return {
    validate(name, value) {
      return validators[name](value);
    },
    errors(name) {
      return validators[name].errors ?? null;
    },
  };
}

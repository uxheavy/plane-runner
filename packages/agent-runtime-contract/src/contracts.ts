import { createHash } from "node:crypto";

import byteConstraints from "./byte-constraints.json" with { type: "json" };

export const PLANE_AGENT_RUNTIME_PROTOCOL = "plane.agent-runtime/v1" as const;

const MAX_REF_LENGTH = byteConstraints.reference.jsonSchemaMaxLength;
const REF_IDENTIFIER_MAX_LENGTH = byteConstraints.reference.identifierCharacterMaxLength;
const utf8ByteLengthUpTo = (value: string, limit = Number.MAX_SAFE_INTEGER): number => {
  let bytes = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    let increment: number;
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        increment = 4;
        index += 1;
      } else {
        increment = 3;
      }
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      increment = 3;
    } else if (codeUnit <= 0x7f) {
      increment = 1;
    } else if (codeUnit <= 0x7ff) {
      increment = 2;
    } else {
      increment = 3;
    }
    bytes += increment;
    if (bytes > limit) {
      return limit + 1;
    }
  }
  return bytes;
};

export const utf8ByteLengthAtMost = (value: string, limit: number): boolean =>
  utf8ByteLengthUpTo(value, limit) <= limit;
declare const validatedContractBrand: unique symbol;

export type PlaneAgentRuntimeProtocol = typeof PLANE_AGENT_RUNTIME_PROTOCOL;

declare const opaqueRefBrand: unique symbol;

type ValidatedContract<Name extends string> = {
  readonly [validatedContractBrand]: Name;
};

type ValidatedContractName =
  | "RunSnapshot"
  | "InvocationEnvelope"
  | "RuntimeEvent"
  | "RuntimeExit"
  | "RuntimeDurableState";

const parsedContracts: Readonly<Record<ValidatedContractName, WeakSet<object>>> = {
  RunSnapshot: new WeakSet<object>(),
  InvocationEnvelope: new WeakSet<object>(),
  RuntimeEvent: new WeakSet<object>(),
  RuntimeExit: new WeakSet<object>(),
  RuntimeDurableState: new WeakSet<object>(),
};

function markValidatedContract<Name extends ValidatedContractName, T extends object>(
  value: T,
  name: Name
): T & ValidatedContract<Name> {
  parsedContracts[name].add(value);
  return value as T & ValidatedContract<Name>;
}

function isValidatedContract<Name extends ValidatedContractName>(value: unknown, name: Name): boolean {
  return value !== null && typeof value === "object" && parsedContracts[name].has(value);
}

export type OpaqueRef<Tag extends string> = string & {
  readonly [opaqueRefBrand]: Tag;
};

export type WorkspaceRef = OpaqueRef<"workspace">;
export type ActorRef = OpaqueRef<"actor">;
export type AssignmentRef = OpaqueRef<"assignment">;
export type ProfileVersionRef = OpaqueRef<"profile-version">;
export type RunId = OpaqueRef<"run">;
export type InvocationId = OpaqueRef<"invocation">;
export type TargetRef = OpaqueRef<"target">;
export type ContextRef = OpaqueRef<"context">;
export type OperationRef = OpaqueRef<"operation">;
export type EventRef = OpaqueRef<"event">;
export type EventId = EventRef;
export type CorrelationId = OpaqueRef<"correlation">;
export type IdempotencyKey = OpaqueRef<"idempotency">;
export type CausationRef = OpaqueRef<"causation">;
export type CancellationRef = OpaqueRef<"cancellation">;
export type CheckpointRef = OpaqueRef<"checkpoint">;
export type LeaseId = OpaqueRef<"lease">;
export type OperationAttemptRef = OpaqueRef<"operation-attempt">;
export type ReceiptRef = OpaqueRef<"receipt">;
export type AuditReceiptRef = OpaqueRef<"audit-receipt">;
export type ProductEventRef = OpaqueRef<"product-event">;
export type ConversationRef = OpaqueRef<"conversation">;
export type InputRequestRef = OpaqueRef<"input-request">;
export type ArtifactRef = OpaqueRef<"artifact">;
export type OutcomeSubmissionRef = OpaqueRef<"outcome-submission">;
export type PayloadRef = OpaqueRef<"payload">;
export type ApplicationServiceRef = OpaqueRef<"application-service">;
export type GatewayReceiptRef = OpaqueRef<"gateway-receipt">;
export type AuthorizationReceiptRef = OpaqueRef<"authorization-receipt">;
export type ContractDigest = OpaqueRef<"contract-digest">;
export type ContentDigest = OpaqueRef<"content-digest">;
export type RunSnapshotContentDigest = OpaqueRef<"run-snapshot-content-digest">;

const REF_SUFFIX_PATTERN = new RegExp(`^[A-Za-z0-9][A-Za-z0-9._~/-]{0,${REF_IDENTIFIER_MAX_LENGTH - 1}}$`);
const NAMESPACED_REF_PATTERN = new RegExp(
  `^[a-z][a-z0-9-]{0,30}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,${REF_IDENTIFIER_MAX_LENGTH - 1}}$`
);
const hexDigestPattern = (minimum: number, maximum: number) =>
  new RegExp(`^[a-f0-9]{${minimum === maximum ? minimum : `${minimum},${maximum}`}}$`);
const DIGEST_PATTERN = hexDigestPattern(
  byteConstraints.contractDigest.jsonSchemaMinLength,
  byteConstraints.contractDigest.jsonSchemaMaxLength
);

type RefTag = string;

function makeNamespacedRef<Tag extends RefTag>(tag: Tag, namespace: string, value: string): OpaqueRef<Tag> {
  void tag;
  if (!REF_SUFFIX_PATTERN.test(value)) {
    throw new TypeError(
      `${namespace} references must contain a 1-${REF_IDENTIFIER_MAX_LENGTH} character identifier suffix`
    );
  }

  const namespaced = `${namespace}:${value}`;
  if (
    namespaced.length > MAX_REF_LENGTH ||
    utf8ByteLengthUpTo(namespaced, UTF8_BYTE_LIMITS.reference) > UTF8_BYTE_LIMITS.reference
  ) {
    throw new TypeError(`${namespace} references must be at most 128 characters`);
  }

  return namespaced as OpaqueRef<Tag>;
}

function parseNamespacedRef<Tag extends RefTag>(tag: Tag, namespace: string, value: unknown): OpaqueRef<Tag> {
  void tag;
  if (
    typeof value !== "string" ||
    value.length > MAX_REF_LENGTH ||
    utf8ByteLengthUpTo(value, UTF8_BYTE_LIMITS.reference) > UTF8_BYTE_LIMITS.reference ||
    !NAMESPACED_REF_PATTERN.test(value)
  ) {
    throw new TypeError(`${namespace} references must use the ${namespace}:<identifier> namespace`);
  }

  if (!value.startsWith(`${namespace}:`)) {
    throw new TypeError(`Expected a ${namespace} reference`);
  }

  return value as OpaqueRef<Tag>;
}

function defineRef<Tag extends RefTag>(tag: Tag, namespace: string) {
  return {
    create: (value: string) => makeNamespacedRef(tag, namespace, value),
    parse: (value: unknown) => parseNamespacedRef(tag, namespace, value),
  };
}

const refs = {
  workspace: defineRef("workspace", "workspace"),
  actor: defineRef("actor", "actor"),
  assignment: defineRef("assignment", "assignment"),
  profileVersion: defineRef("profile-version", "profile-version"),
  run: defineRef("run", "run"),
  invocation: defineRef("invocation", "invocation"),
  target: defineRef("target", "target"),
  context: defineRef("context", "context"),
  operation: defineRef("operation", "operation"),
  event: defineRef("event", "event"),
  correlation: defineRef("correlation", "correlation"),
  idempotency: defineRef("idempotency", "idempotency"),
  causation: defineRef("causation", "causation"),
  cancellation: defineRef("cancellation", "cancellation"),
  checkpoint: defineRef("checkpoint", "checkpoint"),
  lease: defineRef("lease", "lease"),
  operationAttempt: defineRef("operation-attempt", "operation-attempt"),
  receipt: defineRef("receipt", "receipt"),
  auditReceipt: defineRef("audit-receipt", "audit-receipt"),
  productEvent: defineRef("product-event", "product-event"),
  conversation: defineRef("conversation", "conversation"),
  inputRequest: defineRef("input-request", "input-request"),
  artifact: defineRef("artifact", "artifact"),
  outcomeSubmission: defineRef("outcome-submission", "outcome-submission"),
  payload: defineRef("payload", "payload"),
  applicationService: defineRef("application-service", "application-service"),
  gatewayReceipt: defineRef("gateway-receipt", "gateway-receipt"),
  authorizationReceipt: defineRef("authorization-receipt", "authorization-receipt"),
} as const;

export const createWorkspaceRef = refs.workspace.create;
export const parseWorkspaceRef = refs.workspace.parse;
export const createActorRef = refs.actor.create;
export const parseActorRef = refs.actor.parse;
export const createAssignmentRef = refs.assignment.create;
export const parseAssignmentRef = refs.assignment.parse;
export const createProfileVersionRef = refs.profileVersion.create;
export const parseProfileVersionRef = refs.profileVersion.parse;
export const createRunId = refs.run.create;
export const parseRunId = refs.run.parse;
export const createInvocationId = refs.invocation.create;
export const parseInvocationId = refs.invocation.parse;
export const createTargetRef = refs.target.create;
export const parseTargetRef = refs.target.parse;
export const createContextRef = refs.context.create;
export const parseContextRef = refs.context.parse;
export const createOperationRef = refs.operation.create;
export const parseOperationRef = refs.operation.parse;
export const createEventRef = refs.event.create;
export const parseEventRef = refs.event.parse;
export const createCorrelationId = refs.correlation.create;
export const parseCorrelationId = refs.correlation.parse;
export const createIdempotencyKey = refs.idempotency.create;
export const parseIdempotencyKey = refs.idempotency.parse;
export const createCausationRef = refs.causation.create;
export const parseCausationRef = refs.causation.parse;
export const createCancellationRef = refs.cancellation.create;
export const parseCancellationRef = refs.cancellation.parse;
export const createCheckpointRef = refs.checkpoint.create;
export const parseCheckpointRef = refs.checkpoint.parse;
export const createLeaseId = refs.lease.create;
export const parseLeaseId = refs.lease.parse;
export const createOperationAttemptRef = refs.operationAttempt.create;
export const parseOperationAttemptRef = refs.operationAttempt.parse;
export const createReceiptRef = refs.receipt.create;
export const parseReceiptRef = refs.receipt.parse;
export const createAuditReceiptRef = refs.auditReceipt.create;
export const parseAuditReceiptRef = refs.auditReceipt.parse;
export const createProductEventRef = refs.productEvent.create;
export const parseProductEventRef = refs.productEvent.parse;
export const createConversationRef = refs.conversation.create;
export const parseConversationRef = refs.conversation.parse;
export const createInputRequestRef = refs.inputRequest.create;
export const parseInputRequestRef = refs.inputRequest.parse;
export const createArtifactRef = refs.artifact.create;
export const parseArtifactRef = refs.artifact.parse;
export const createOutcomeSubmissionRef = refs.outcomeSubmission.create;
export const parseOutcomeSubmissionRef = refs.outcomeSubmission.parse;
export const createPayloadRef = refs.payload.create;
export const parsePayloadRef = refs.payload.parse;
export const createApplicationServiceRef = refs.applicationService.create;
export const parseApplicationServiceRef = refs.applicationService.parse;
export const createGatewayReceiptRef = refs.gatewayReceipt.create;
export const parseGatewayReceiptRef = refs.gatewayReceipt.parse;
export const createAuthorizationReceiptRef = refs.authorizationReceipt.create;
export const parseAuthorizationReceiptRef = refs.authorizationReceipt.parse;

function namespacedDigestBounds(namespace: string, constraint: typeof byteConstraints.contentDigest) {
  const prefixBytes = utf8ByteLengthUpTo(`${namespace}:`);
  return {
    minimum: constraint.utf8ByteMin - prefixBytes,
    maximum: constraint.utf8ByteMax - prefixBytes,
  };
}

function makeDigest<Tag extends RefTag>(
  tag: Tag,
  namespace: string,
  value: string,
  constraint: typeof byteConstraints.contentDigest
): OpaqueRef<Tag> {
  void tag;
  const bounds = namespacedDigestBounds(namespace, constraint);
  const bytes = utf8ByteLengthUpTo(value);
  if (
    bytes < bounds.minimum ||
    bytes > bounds.maximum ||
    !hexDigestPattern(bounds.minimum, bounds.maximum).test(value)
  ) {
    throw new TypeError(`${namespace} digests must be lowercase SHA-256 hex strings`);
  }

  return `${namespace}:${value}` as OpaqueRef<Tag>;
}

function parseNamespacedDigest<Tag extends RefTag>(
  tag: Tag,
  namespace: string,
  value: unknown,
  constraint: typeof byteConstraints.contentDigest
): OpaqueRef<Tag> {
  void tag;
  if (typeof value !== "string" || !value.startsWith(`${namespace}:`)) {
    throw new TypeError(`Expected a ${namespace} digest`);
  }

  return makeDigest(tag, namespace, value.slice(namespace.length + 1), constraint);
}

export function createContractDigest(value: string): ContractDigest {
  const bytes = utf8ByteLengthUpTo(value);
  if (
    bytes < byteConstraints.contractDigest.utf8ByteMin ||
    bytes > byteConstraints.contractDigest.utf8ByteMax ||
    !DIGEST_PATTERN.test(value)
  ) {
    throw new TypeError("Contract digests must be lowercase SHA-256 hex strings");
  }

  return value as ContractDigest;
}

export function parseContractDigest(value: unknown): ContractDigest {
  if (typeof value !== "string") {
    throw new TypeError("Contract digests must be strings");
  }

  return createContractDigest(value);
}

export const createContentDigest = (value: string): ContentDigest =>
  makeDigest("content-digest", "content", value, byteConstraints.contentDigest);
export const parseContentDigest = (value: unknown): ContentDigest =>
  parseNamespacedDigest("content-digest", "content", value, byteConstraints.contentDigest);
export const createRunSnapshotContentDigest = (value: string): RunSnapshotContentDigest =>
  makeDigest("run-snapshot-content-digest", "snapshot", value, byteConstraints.runSnapshotContentDigest);
export const parseRunSnapshotContentDigest = (value: unknown): RunSnapshotContentDigest =>
  parseNamespacedDigest("run-snapshot-content-digest", "snapshot", value, byteConstraints.runSnapshotContentDigest);

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const key of Reflect.ownKeys(value)) {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || !("value" in descriptor)) {
        throw new TypeError("Contract values cannot contain accessors");
      }
      deepFreeze(descriptor.value);
    }
    Object.freeze(value);
  }

  return value;
}

export function freezeRunSnapshot(snapshot: RunSnapshot): RunSnapshot {
  return deepFreeze(snapshot);
}

export type BoundedText = string;
export type BoundedPrompt = string;
export type Timestamp = string;

export type AgentRole = "worker" | "delegator" | "gardener" | "chief_of_staff" | "hr" | "evaluator" | "custom";

export type AssignmentSnapshot = Readonly<{
  assignmentRef: AssignmentRef;
  revision: string;
  targetRef: TargetRef;
  objective: BoundedText;
  acceptanceCriteria: readonly BoundedText[];
}>;

export type ProfileSnapshot = Readonly<{
  profileRef: ProfileVersionRef;
  revision: string;
  role: AgentRole;
  behavioralPrompt: BoundedPrompt;
}>;

export type VersionedContextRef = Readonly<{
  contextRef: ContextRef;
  revision: string;
  contentDigest: ContentDigest;
}>;

export type OperationDescriptor = Readonly<{
  operationRef: OperationRef;
  schemaDigest: ContentDigest;
  disclosure: "eager" | "progressive";
}>;

export type ToolCatalogSnapshot = Readonly<{
  catalogDigest: ContentDigest;
  eagerOperations: readonly OperationDescriptor[];
}>;

export type RuntimeModelRoute = Readonly<{
  provider: string;
  model: string;
}>;

export type RuntimePolicy = Readonly<{
  model: RuntimeModelRoute;
  adapter: string;
  isolation: "single-invocation";
  maxEventPayloadBytes: number;
  maxArtifactBytes: number;
  maxReceiptBytes: number;
}>;

export type RuntimeBudgetPolicy = Readonly<{
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
}>;

export type RuntimeBudget = Readonly<{
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
}>;

export type ContractDigests = Readonly<{
  runSnapshot: ContractDigest;
  invocationEnvelope: ContractDigest;
  runtimeEvent: ContractDigest;
  runtimeExit: ContractDigest;
  runtimeDurableState: ContractDigest;
}>;

export const CONTRACT_SCHEMA_NAMES = [
  "run-snapshot",
  "invocation-envelope",
  "runtime-event",
  "runtime-exit",
  "runtime-durable-state",
] as const;
export type ContractSchemaName = (typeof CONTRACT_SCHEMA_NAMES)[number];

export type ContractManifest = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  schemas: Readonly<Record<ContractSchemaName, Readonly<{ filename: string; sha256: ContractDigest }>>>;
}>;

export function contractDigestsFromManifest(manifest: ContractManifest): ContractDigests {
  return {
    runSnapshot: manifest.schemas["run-snapshot"].sha256,
    invocationEnvelope: manifest.schemas["invocation-envelope"].sha256,
    runtimeEvent: manifest.schemas["runtime-event"].sha256,
    runtimeExit: manifest.schemas["runtime-exit"].sha256,
    runtimeDurableState: manifest.schemas["runtime-durable-state"].sha256,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseManifestEntry(value: unknown, name: ContractSchemaName) {
  const object = requireRecord(value, `ContractManifest.schemas.${name}`, ["filename", "sha256"]);
  if (object.filename !== `${name}.schema.json`) {
    throw new TypeError(`Invalid manifest entry for ${name}`);
  }

  return { filename: object.filename, sha256: parseContractDigest(object.sha256) };
}

export function parseContractManifest(value: unknown): ContractManifest {
  const object = requireRecord(parseRawJson(value, "ContractManifest"), "ContractManifest", ["protocol", "schemas"]);
  if (object.protocol !== PLANE_AGENT_RUNTIME_PROTOCOL) {
    throw new TypeError("Invalid Plane Agent runtime contract manifest");
  }
  const schemas = requireRecord(object.schemas, "ContractManifest.schemas", CONTRACT_SCHEMA_NAMES);
  return {
    protocol: PLANE_AGENT_RUNTIME_PROTOCOL,
    schemas: {
      "run-snapshot": parseManifestEntry(schemas["run-snapshot"], "run-snapshot"),
      "invocation-envelope": parseManifestEntry(schemas["invocation-envelope"], "invocation-envelope"),
      "runtime-event": parseManifestEntry(schemas["runtime-event"], "runtime-event"),
      "runtime-exit": parseManifestEntry(schemas["runtime-exit"], "runtime-exit"),
      "runtime-durable-state": parseManifestEntry(schemas["runtime-durable-state"], "runtime-durable-state"),
    },
  };
}

type RunSnapshotShape = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  workspaceRef: WorkspaceRef;
  runId: RunId;
  assignment: AssignmentSnapshot;
  actorRef: ActorRef;
  profile: ProfileSnapshot;
  context: readonly VersionedContextRef[];
  toolCatalog: ToolCatalogSnapshot;
  runtimePolicy: RuntimePolicy;
  totalBudget: RuntimeBudgetPolicy;
  contractDigests: ContractDigests;
  contentDigest: RunSnapshotContentDigest;
}>;

export type RunSnapshot = RunSnapshotShape & ValidatedContract<"RunSnapshot">;
export type RunSnapshotContent = Omit<RunSnapshotShape, "contentDigest">;

function withoutSnapshotContentDigest(snapshot: RunSnapshot | RunSnapshotContent): RunSnapshotContent {
  if ("contentDigest" in snapshot) {
    const { contentDigest: _contentDigest, ...content } = snapshot;
    return content;
  }

  return snapshot;
}

export function canonicalizeJson(value: unknown): string {
  const normalized = normalizeJsonValue(value);
  measureNormalizedJsonUtf8Bytes(normalized, CANONICAL_JSON_LIMITS.maxCanonicalBytes);
  return writeCanonicalJson(normalized);
}

export function serializedJsonByteLength(value: unknown): number {
  return measureCanonicalJsonUtf8Bytes(value);
}

export const UTF8_BYTE_LIMITS = {
  reference: byteConstraints.reference.utf8ByteMax,
  boundedText: byteConstraints.boundedText.utf8ByteMax,
  boundedPrompt: byteConstraints.boundedPrompt.utf8ByteMax,
  boundedToken: byteConstraints.boundedToken.utf8ByteMax,
  timestamp: byteConstraints.timestamp.utf8ByteMax,
  serializedContract: byteConstraints.serializedContract.utf8ByteMax,
} as const;

export const MAX_SERIALIZED_JSON_BYTES = UTF8_BYTE_LIMITS.serializedContract;
const MAX_BOUNDED_BYTE_COUNT = byteConstraints.boundedByteCount.numericMax;

export type CanonicalJsonLimits = Readonly<{
  maxDepth: number;
  maxNodes: number;
  maxStringBytes: number;
  maxCollectionItems: number;
  maxWork: number;
  maxCanonicalBytes: number;
}>;

export const CANONICAL_JSON_LIMITS: CanonicalJsonLimits = Object.freeze({
  maxDepth: 64,
  maxNodes: 10_000,
  maxStringBytes: 16 * 1024 * 1024,
  maxCollectionItems: 4096,
  maxWork: 32 * 1024 * 1024,
  maxCanonicalBytes: 16 * 1024 * 1024,
});

type SafeJsonErrorCode =
  | "depth_exceeded"
  | "node_count_exceeded"
  | "string_bytes_exceeded"
  | "collection_size_exceeded"
  | "work_exceeded"
  | "cycle_detected"
  | "unsupported_prototype"
  | "unsupported_accessor"
  | "unsupported_symbol_key"
  | "unsupported_non_enumerable"
  | "sparse_array"
  | "unsupported_value"
  | "serialized_bytes_exceeded";

class SafeJsonError extends TypeError {
  readonly code: SafeJsonErrorCode;

  constructor(code: SafeJsonErrorCode) {
    super(code);
    this.name = "SafeJsonError";
    this.code = code;
  }
}

const safeJsonErrorMessage = (error: unknown): string => {
  if (!(error instanceof SafeJsonError)) {
    return "contains unsupported JSON data";
  }
  switch (error.code) {
    case "depth_exceeded":
      return "exceeds the maximum JSON depth";
    case "node_count_exceeded":
      return "exceeds the maximum JSON node count";
    case "string_bytes_exceeded":
      return "exceeds the maximum accumulated UTF-8 string bytes";
    case "collection_size_exceeded":
      return "exceeds the maximum JSON collection size";
    case "work_exceeded":
      return "exceeds the maximum JSON validation work";
    case "cycle_detected":
      return "contains a cyclic JSON value";
    case "unsupported_prototype":
      return "must contain only plain JSON objects and arrays";
    case "unsupported_accessor":
      return "must not contain accessors";
    case "unsupported_symbol_key":
      return "must not contain symbol keys";
    case "unsupported_non_enumerable":
      return "must not contain non-enumerable properties";
    case "sparse_array":
      return "must not contain sparse arrays";
    case "serialized_bytes_exceeded":
      return "exceeds the configured canonical UTF-8 byte limit";
    case "unsupported_value":
      return "contains an unsupported JSON value";
  }
};

type NormalizationState = {
  readonly limits: CanonicalJsonLimits;
  nodes: number;
  stringBytes: number;
  work: number;
  active: WeakSet<object>;
};

const spendNormalizationWork = (state: NormalizationState, amount: number): void => {
  state.work += amount;
  if (state.work > state.limits.maxWork) {
    throw new SafeJsonError("work_exceeded");
  }
};

const countNormalizationNode = (state: NormalizationState): void => {
  state.nodes += 1;
  spendNormalizationWork(state, 1);
  if (state.nodes > state.limits.maxNodes) {
    throw new SafeJsonError("node_count_exceeded");
  }
};

const isCanonicalArrayIndex = (key: string, length: number): boolean => {
  if (key === "0") return length > 0;
  if (!/^[1-9][0-9]*$/.test(key)) return false;
  const index = Number(key);
  return Number.isSafeInteger(index) && index < length;
};

function normalizeJsonValueInternal(value: unknown, depth: number, state: NormalizationState): unknown {
  if (depth > state.limits.maxDepth) {
    throw new SafeJsonError("depth_exceeded");
  }
  countNormalizationNode(state);

  if (value === null) {
    return null;
  }
  if (typeof value === "string") {
    const bytes = utf8ByteLengthUpTo(value, state.limits.maxStringBytes);
    if (bytes > state.limits.maxStringBytes) {
      throw new SafeJsonError("string_bytes_exceeded");
    }
    state.stringBytes += bytes;
    if (state.stringBytes > state.limits.maxStringBytes) {
      throw new SafeJsonError("string_bytes_exceeded");
    }
    spendNormalizationWork(state, bytes + 1);
    return value;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new SafeJsonError("unsupported_value");
    }
    spendNormalizationWork(state, 8);
    return value;
  }
  if (typeof value !== "object") {
    throw new SafeJsonError("unsupported_value");
  }

  if (state.active.has(value)) {
    throw new SafeJsonError("cycle_detected");
  }
  state.active.add(value);
  try {
    if (Array.isArray(value)) {
      if (Object.getPrototypeOf(value) !== Array.prototype) {
        throw new SafeJsonError("unsupported_prototype");
      }
      const lengthDescriptor = Object.getOwnPropertyDescriptor(value, "length");
      if (lengthDescriptor === undefined || !("value" in lengthDescriptor)) {
        throw new SafeJsonError("sparse_array");
      }
      const length = lengthDescriptor.value;
      if (!Number.isSafeInteger(length) || length < 0 || length > state.limits.maxCollectionItems) {
        throw new SafeJsonError("collection_size_exceeded");
      }
      const keys = Reflect.ownKeys(value);
      if (keys.length - 1 > state.limits.maxCollectionItems) {
        throw new SafeJsonError("collection_size_exceeded");
      }
      for (const key of keys) {
        if (typeof key !== "string") {
          throw new SafeJsonError("unsupported_symbol_key");
        }
        if (key !== "length" && !isCanonicalArrayIndex(key, length)) {
          throw new SafeJsonError("unsupported_value");
        }
      }
      const normalized: unknown[] = [];
      for (let index = 0; index < length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
        if (descriptor === undefined) {
          throw new SafeJsonError("sparse_array");
        }
        if (!("value" in descriptor)) {
          throw new SafeJsonError("unsupported_accessor");
        }
        if (!descriptor.enumerable) {
          throw new SafeJsonError("unsupported_non_enumerable");
        }
        normalized.push(normalizeJsonValueInternal(descriptor.value, depth + 1, state));
      }
      return normalized;
    }

    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new SafeJsonError("unsupported_prototype");
    }
    const keys = Reflect.ownKeys(value);
    if (keys.length > state.limits.maxCollectionItems) {
      throw new SafeJsonError("collection_size_exceeded");
    }
    const normalized = Object.create(null) as Record<string, unknown>;
    for (const key of keys) {
      if (typeof key !== "string") {
        throw new SafeJsonError("unsupported_symbol_key");
      }
      const keyBytes = utf8ByteLengthUpTo(key, state.limits.maxStringBytes);
      if (keyBytes > state.limits.maxStringBytes) {
        throw new SafeJsonError("string_bytes_exceeded");
      }
      state.stringBytes += keyBytes;
      if (state.stringBytes > state.limits.maxStringBytes) {
        throw new SafeJsonError("string_bytes_exceeded");
      }
      spendNormalizationWork(state, keyBytes + 1);
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined) {
        throw new SafeJsonError("unsupported_value");
      }
      if (!("value" in descriptor)) {
        throw new SafeJsonError("unsupported_accessor");
      }
      if (!descriptor.enumerable) {
        throw new SafeJsonError("unsupported_non_enumerable");
      }
      Object.defineProperty(normalized, key, {
        configurable: true,
        enumerable: true,
        value: normalizeJsonValueInternal(descriptor.value, depth + 1, state),
        writable: true,
      });
    }
    return normalized;
  } finally {
    state.active.delete(value);
  }
}

export function normalizeJsonValue(value: unknown, overrides: Partial<CanonicalJsonLimits> = {}): unknown {
  const limits = { ...CANONICAL_JSON_LIMITS, ...overrides };
  return normalizeJsonValueInternal(value, 0, {
    limits,
    nodes: 0,
    stringBytes: 0,
    work: 0,
    active: new WeakSet<object>(),
  });
}

type CanonicalMeasurementState = {
  bytes: number;
  work: number;
  readonly maxBytes: number;
  readonly maxWork: number;
};

const addCanonicalBytes = (state: CanonicalMeasurementState, bytes: number): void => {
  state.bytes += bytes;
  state.work += bytes + 1;
  if (state.bytes > state.maxBytes) {
    throw new SafeJsonError("serialized_bytes_exceeded");
  }
  if (state.work > state.maxWork) {
    throw new SafeJsonError("work_exceeded");
  }
};

const jsonStringByteLength = (value: string, state: CanonicalMeasurementState): void => {
  addCanonicalBytes(state, 1);
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (
      codeUnit === 0x22 ||
      codeUnit === 0x5c ||
      codeUnit === 0x08 ||
      codeUnit === 0x09 ||
      codeUnit === 0x0a ||
      codeUnit === 0x0c ||
      codeUnit === 0x0d
    ) {
      addCanonicalBytes(state, 2);
      continue;
    }
    if (codeUnit < 0x20) {
      addCanonicalBytes(state, 6);
      continue;
    }
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        addCanonicalBytes(state, 4);
        index += 1;
      } else {
        addCanonicalBytes(state, 6);
      }
      continue;
    }
    if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      addCanonicalBytes(state, 6);
      continue;
    }
    addCanonicalBytes(state, codeUnit <= 0x7f ? 1 : codeUnit <= 0x7ff ? 2 : 3);
  }
  addCanonicalBytes(state, 1);
};

function measureNormalizedJsonUtf8Bytes(value: unknown, maxBytes: number): number {
  const state: CanonicalMeasurementState = {
    bytes: 0,
    work: 0,
    maxBytes,
    maxWork: CANONICAL_JSON_LIMITS.maxWork,
  };
  const measure = (candidate: unknown): void => {
    if (candidate === null) {
      addCanonicalBytes(state, 4);
      return;
    }
    if (typeof candidate === "string") {
      jsonStringByteLength(candidate, state);
      return;
    }
    if (typeof candidate === "boolean") {
      addCanonicalBytes(state, candidate ? 4 : 5);
      return;
    }
    if (typeof candidate === "number") {
      addCanonicalBytes(state, utf8ByteLengthUpTo(JSON.stringify(candidate)));
      return;
    }
    if (Array.isArray(candidate)) {
      addCanonicalBytes(state, 1);
      candidate.forEach((item, index) => {
        if (index > 0) addCanonicalBytes(state, 1);
        measure(item);
      });
      addCanonicalBytes(state, 1);
      return;
    }
    const object = candidate as Record<string, unknown>;
    addCanonicalBytes(state, 1);
    Object.keys(object)
      .toSorted()
      .forEach((key, index) => {
        if (index > 0) addCanonicalBytes(state, 1);
        jsonStringByteLength(key, state);
        addCanonicalBytes(state, 1);
        measure(object[key]);
      });
    addCanonicalBytes(state, 1);
  };
  measure(value);
  return state.bytes;
}

function measureCanonicalJsonUtf8Bytes(value: unknown, maxBytes = CANONICAL_JSON_LIMITS.maxCanonicalBytes): number {
  return measureNormalizedJsonUtf8Bytes(normalizeJsonValue(value), maxBytes);
}

export function isCanonicalJsonUtf8ByteLengthAtMost(value: unknown, limit: number): boolean {
  try {
    measureCanonicalJsonUtf8Bytes(value, limit);
    return true;
  } catch {
    return false;
  }
}

function writeCanonicalJson(value: unknown): string {
  if (value === null || typeof value === "string" || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => writeCanonicalJson(item)).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .toSorted()
    .map((key) => `${JSON.stringify(key)}:${writeCanonicalJson(object[key])}`)
    .join(",")}}`;
}

export function canonicalJsonEquals(left: unknown, right: unknown): boolean {
  const normalizedLeft = normalizeJsonValue(left);
  const normalizedRight = normalizeJsonValue(right);
  const compare = (first: unknown, second: unknown, depth: number): boolean => {
    if (depth > CANONICAL_JSON_LIMITS.maxDepth) {
      throw new SafeJsonError("depth_exceeded");
    }
    if (first === null || second === null || typeof first !== "object" || typeof second !== "object") {
      if (typeof first !== typeof second) return false;
      return typeof first === "number" && typeof second === "number"
        ? JSON.stringify(first) === JSON.stringify(second)
        : first === second;
    }
    if (Array.isArray(first) !== Array.isArray(second)) return false;
    if (Array.isArray(first)) {
      if (first.length !== (second as unknown[]).length) return false;
      return first.every((item, index) => compare(item, (second as unknown[])[index], depth + 1));
    }
    const firstObject = first as Record<string, unknown>;
    const secondObject = second as Record<string, unknown>;
    const firstKeys = Object.keys(firstObject).toSorted();
    const secondKeys = Object.keys(secondObject).toSorted();
    if (firstKeys.length !== secondKeys.length) return false;
    return firstKeys.every(
      (key, index) => key === secondKeys[index] && compare(firstObject[key], secondObject[key], depth + 1)
    );
  };
  return compare(normalizedLeft, normalizedRight, 0);
}

export class ContractParseError extends TypeError {
  readonly path: string;

  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "ContractParseError";
    this.path = path;
  }
}

function parseRawJson(value: unknown, path: string): unknown {
  let parsed = value;
  if (typeof value === "string") {
    if (utf8ByteLengthUpTo(value, CANONICAL_JSON_LIMITS.maxCanonicalBytes) > CANONICAL_JSON_LIMITS.maxCanonicalBytes) {
      throw new ContractParseError(path, "serialized JSON input exceeds the configured UTF-8 byte limit");
    }
    try {
      parsed = JSON.parse(value) as unknown;
    } catch {
      throw new ContractParseError(path, "must be valid JSON");
    }
  }
  try {
    return normalizeJsonValue(parsed);
  } catch (error) {
    throw new ContractParseError(path, safeJsonErrorMessage(error));
  }
}

function requireRecord(value: unknown, path: string, required: readonly string[], optional: readonly string[] = []) {
  if (!isRecord(value)) {
    throw new ContractParseError(path, "must be an object");
  }
  const allowed = new Set([...required, ...optional]);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      throw new ContractParseError(`${path}.${key}`, "unknown properties are not allowed");
    }
  }
  for (const key of required) {
    if (!Object.hasOwn(value, key)) {
      throw new ContractParseError(`${path}.${key}`, "is required");
    }
  }
  return value;
}

function parseString(value: unknown, path: string, limit: number, min = 1): string {
  if (typeof value !== "string") {
    throw new ContractParseError(path, "must be a string");
  }
  const bytes = utf8ByteLengthUpTo(value, limit);
  if (bytes < min || bytes > limit) {
    throw new ContractParseError(path, `must be between ${min} and ${limit} UTF-8 bytes`);
  }
  return value;
}

function parseLiteral<T extends string>(value: unknown, expected: T, path: string): T {
  if (value !== expected) {
    throw new ContractParseError(path, `must equal ${expected}`);
  }
  return expected;
}

function parseInteger(value: unknown, path: string, maximum = 2_147_483_647): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0 || value > maximum) {
    throw new ContractParseError(path, `must be an integer between 0 and ${maximum}`);
  }
  return value;
}

function parseRef<Tag extends string>(
  value: unknown,
  path: string,
  parser: (value: unknown) => OpaqueRef<Tag>
): OpaqueRef<Tag> {
  try {
    const parsed = parser(value);
    if (serializedJsonByteLength(parsed) - 2 > UTF8_BYTE_LIMITS.reference) {
      throw new TypeError("reference exceeds the UTF-8 byte limit");
    }
    return parsed;
  } catch (error) {
    if (error instanceof ContractParseError) {
      throw error;
    }
    throw new ContractParseError(path, error instanceof Error ? error.message : "invalid reference");
  }
}

function parseBoundedText(value: unknown, path: string): BoundedText {
  return parseString(value, path, UTF8_BYTE_LIMITS.boundedText, byteConstraints.boundedText.utf8ByteMin) as BoundedText;
}

function parseBoundedPrompt(value: unknown, path: string): BoundedPrompt {
  return parseString(
    value,
    path,
    UTF8_BYTE_LIMITS.boundedPrompt,
    byteConstraints.boundedPrompt.utf8ByteMin
  ) as BoundedPrompt;
}

function parseBoundedToken(value: unknown, path: string): string {
  return parseString(value, path, UTF8_BYTE_LIMITS.boundedToken, byteConstraints.boundedToken.utf8ByteMin);
}

function parseTimestamp(value: unknown, path: string): Timestamp {
  return parseString(value, path, UTF8_BYTE_LIMITS.timestamp, byteConstraints.timestamp.utf8ByteMin) as Timestamp;
}

function parseDigest(
  value: unknown,
  path: string,
  parser: (value: unknown) => ContentDigest | ContractDigest | RunSnapshotContentDigest
) {
  try {
    return parser(value);
  } catch (error) {
    throw new ContractParseError(path, error instanceof Error ? error.message : "invalid digest");
  }
}

function parseBudget(value: unknown, path: string): RuntimeBudget {
  const object = requireRecord(value, path, ["inputTokens", "outputTokens", "durationMs"]);
  return {
    inputTokens: parseInteger(object.inputTokens, `${path}.inputTokens`),
    outputTokens: parseInteger(object.outputTokens, `${path}.outputTokens`),
    durationMs: parseInteger(object.durationMs, `${path}.durationMs`),
  };
}

function parsePublication<ProductKind extends string, ProductRef extends OpaqueRef<string>>(
  value: unknown,
  path: string,
  productKind: ProductKind,
  parseProductRef: (value: unknown) => ProductRef,
  terminal = false,
  appliedOnly = false
): Publication<ProductKind, ProductRef> {
  const object = requireRecord(
    value,
    path,
    terminal
      ? [
          "action",
          "productKind",
          "productRef",
          "operationAttemptRef",
          "operationRef",
          "applicationServiceRef",
          "gatewayReceiptRef",
          "receiptRef",
          "auditReceiptRef",
          "productEventRef",
        ]
      : ["action", "productKind", "productRef", "operationAttemptRef"],
    terminal && productKind === "run_cancellation"
      ? ["cancellationRef"]
      : terminal
        ? []
        : [
            "operationRef",
            "applicationServiceRef",
            "gatewayReceiptRef",
            "receiptRef",
            "auditReceiptRef",
            "productEventRef",
          ]
  );
  parseLiteral(object.productKind, productKind, `${path}.productKind`);
  const action = object.action;
  if (action === "proposal" && !terminal && !appliedOnly) {
    for (const key of [
      "operationRef",
      "applicationServiceRef",
      "gatewayReceiptRef",
      "receiptRef",
      "auditReceiptRef",
      "productEventRef",
    ]) {
      if (Object.hasOwn(object, key)) {
        throw new ContractParseError(`${path}.${key}`, "is only valid for an applied publication");
      }
    }
    return {
      action,
      productKind,
      productRef: parseProductRef(object.productRef),
      operationAttemptRef: parseRef(
        object.operationAttemptRef,
        `${path}.operationAttemptRef`,
        parseOperationAttemptRef
      ),
    } as unknown as Publication<ProductKind, ProductRef>;
  }
  if (action !== "applied") {
    throw new ContractParseError(`${path}.action`, "must be applied for this product publication");
  }
  const parsed = {
    action,
    productKind,
    productRef: parseProductRef(object.productRef),
    operationAttemptRef: parseRef(object.operationAttemptRef, `${path}.operationAttemptRef`, parseOperationAttemptRef),
    operationRef: parseRef(object.operationRef, `${path}.operationRef`, parseOperationRef),
    applicationServiceRef: parseRef(
      object.applicationServiceRef,
      `${path}.applicationServiceRef`,
      parseApplicationServiceRef
    ),
    gatewayReceiptRef: parseRef(object.gatewayReceiptRef, `${path}.gatewayReceiptRef`, parseGatewayReceiptRef),
    receiptRef: parseRef(object.receiptRef, `${path}.receiptRef`, parseReceiptRef),
    auditReceiptRef: parseRef(object.auditReceiptRef, `${path}.auditReceiptRef`, parseAuditReceiptRef),
    productEventRef: parseRef(object.productEventRef, `${path}.productEventRef`, parseProductEventRef),
  } as Publication<ProductKind, ProductRef>;
  if (terminal && parsed.action === "applied" && parsed.productRef !== parsed.productEventRef) {
    throw new ContractParseError(`${path}.productEventRef`, "must identify the exact visible terminal product event");
  }
  if (productKind === "run_cancellation") {
    return {
      ...parsed,
      cancellationRef: parseRef(object.cancellationRef, `${path}.cancellationRef`, parseCancellationRef),
    } as unknown as Publication<ProductKind, ProductRef>;
  }
  return parsed;
}

function parseBoundedPayload(value: unknown, path: string): BoundedPayload {
  if (!isRecord(value)) {
    throw new ContractParseError(path, "must be an object");
  }
  const object = value;
  if (object.kind === "inline_text") {
    const inline = requireRecord(object, path, ["kind", "contentType", "text"]);
    return {
      kind: "inline_text",
      contentType: parseLiteral(inline.contentType, "text/plain", `${path}.contentType`),
      text: parseBoundedText(inline.text, `${path}.text`),
    };
  }
  if (object.kind === "payload_ref") {
    const reference = requireRecord(object, path, ["kind", "payloadRef", "contentType", "contentDigest", "sizeBytes"]);
    return {
      kind: "payload_ref",
      payloadRef: parseRef(reference.payloadRef, `${path}.payloadRef`, parsePayloadRef),
      contentType: parseBoundedToken(reference.contentType, `${path}.contentType`),
      contentDigest: parseDigest(reference.contentDigest, `${path}.contentDigest`, parseContentDigest) as ContentDigest,
      sizeBytes: parseInteger(reference.sizeBytes, `${path}.sizeBytes`, MAX_BOUNDED_BYTE_COUNT),
    };
  }
  throw new ContractParseError(`${path}.kind`, "must identify a supported payload variant");
}

function parseArtifact(value: unknown, path: string): ArtifactReference {
  const object = requireRecord(value, path, ["artifactRef", "contentDigest", "mediaType", "sizeBytes"]);
  return {
    artifactRef: parseRef(object.artifactRef, `${path}.artifactRef`, parseArtifactRef),
    contentDigest: parseDigest(object.contentDigest, `${path}.contentDigest`, parseContentDigest) as ContentDigest,
    mediaType: parseBoundedToken(object.mediaType, `${path}.mediaType`),
    sizeBytes: parseInteger(object.sizeBytes, `${path}.sizeBytes`, MAX_BOUNDED_BYTE_COUNT),
  };
}

function parseRuntimeFailure(value: unknown, path: string): RuntimeFailure {
  const object = requireRecord(value, path, ["code", "message", "retryable"]);
  const codes = ["runtime_error", "lease_expired", "invalid_continuation", "budget_exhausted", "cancelled"] as const;
  if (!codes.includes(object.code as (typeof codes)[number])) {
    throw new ContractParseError(`${path}.code`, "is not a supported runtime failure code");
  }
  if (typeof object.retryable !== "boolean") {
    throw new ContractParseError(`${path}.retryable`, "must be a boolean");
  }
  return {
    code: object.code,
    message: parseBoundedText(object.message, `${path}.message`),
    retryable: object.retryable,
  } as RuntimeFailure;
}

function parseRuntimeUsage(value: unknown, path: string): RuntimeUsage {
  return parseBudget(value, path);
}

function parseBody(value: unknown, path: string): RuntimeEventBody {
  if (!isRecord(value)) {
    throw new ContractParseError(path, "must be an object");
  }
  const base = value;
  switch (base.kind) {
    case "progress_observed": {
      const object = requireRecord(base, path, ["kind", "payload", "publication"]);
      const publication = requireRecord(object.publication, `${path}.publication`, ["action"]);
      return {
        kind: base.kind,
        payload: parseBoundedPayload(object.payload, `${path}.payload`),
        publication: { action: parseLiteral(publication.action, "observation_only", `${path}.publication.action`) },
      };
    }
    case "conversation_publication_observed": {
      const object = requireRecord(base, path, ["kind", "payload", "publication"]);
      return {
        kind: base.kind,
        payload: parseBoundedPayload(object.payload, `${path}.payload`),
        publication: parsePublication(object.publication, `${path}.publication`, "conversation", (item) =>
          parseRef(item, `${path}.publication.productRef`, parseConversationRef)
        ),
      } as RuntimeEventBody;
    }
    case "input_request_observed": {
      const object = requireRecord(base, path, ["kind", "question", "publication"]);
      return {
        kind: base.kind,
        question: parseBoundedText(object.question, `${path}.question`),
        publication: parsePublication(object.publication, `${path}.publication`, "input_request", (item) =>
          parseRef(item, `${path}.publication.productRef`, parseInputRequestRef)
        ),
      } as RuntimeEventBody;
    }
    case "artifact_observed": {
      const object = requireRecord(base, path, ["kind", "artifact", "publication"]);
      const artifact = parseArtifact(object.artifact, `${path}.artifact`);
      return {
        kind: base.kind,
        artifact,
        publication: parsePublication(object.publication, `${path}.publication`, "artifact", (item) =>
          parseRef(item, `${path}.publication.productRef`, parseArtifactRef)
        ),
      } as RuntimeEventBody;
    }
    case "usage_observed": {
      const object = requireRecord(base, path, ["kind", "usage", "publication"]);
      const publication = requireRecord(object.publication, `${path}.publication`, ["action"]);
      return {
        kind: base.kind,
        usage: parseRuntimeUsage(object.usage, `${path}.usage`),
        publication: { action: parseLiteral(publication.action, "observation_only", `${path}.publication.action`) },
      };
    }
    case "outcome_submission_observed": {
      const object = requireRecord(base, path, ["kind", "payload", "publication"]);
      return {
        kind: base.kind,
        payload: parseBoundedPayload(object.payload, `${path}.payload`),
        publication: parsePublication(
          object.publication,
          `${path}.publication`,
          "outcome_submission",
          (item) => parseRef(item, `${path}.publication.productRef`, parseOutcomeSubmissionRef),
          false,
          true
        ) as OutcomeSubmissionPublication,
      } as RuntimeEventBody;
    }
    case "failure_observed": {
      const object = requireRecord(base, path, ["kind", "failure", "publication"]);
      return {
        kind: base.kind,
        failure: parseRuntimeFailure(object.failure, `${path}.failure`),
        publication: parsePublication(
          object.publication,
          `${path}.publication`,
          "run_failure",
          (item) => parseRef(item, `${path}.publication.productRef`, parseProductEventRef),
          true
        ) as FailurePublication,
      };
    }
    case "blocker_observed": {
      const object = requireRecord(base, path, ["kind", "reason", "publication"]);
      return {
        kind: base.kind,
        reason: parseBoundedText(object.reason, `${path}.reason`),
        publication: parsePublication(
          object.publication,
          `${path}.publication`,
          "run_blocker",
          (item) => parseRef(item, `${path}.publication.productRef`, parseProductEventRef),
          true
        ) as BlockerPublication,
      };
    }
    case "cancellation_observed": {
      const object = requireRecord(base, path, ["kind", "reason", "cancellationRef", "publication"]);
      const cancellationRef = parseRef(object.cancellationRef, `${path}.cancellationRef`, parseCancellationRef);
      const publication = parsePublication(
        object.publication,
        `${path}.publication`,
        "run_cancellation",
        (item) => parseRef(item, `${path}.publication.productRef`, parseProductEventRef),
        true
      ) as CancellationPublication;
      const publicationObject = object.publication as Record<string, unknown>;
      const publicationCancellationRef = parseRef(
        publicationObject.cancellationRef,
        `${path}.publication.cancellationRef`,
        parseCancellationRef
      );
      if (publicationCancellationRef !== cancellationRef) {
        throw new ContractParseError(
          `${path}.publication.cancellationRef`,
          "must match the event cancellation reference"
        );
      }
      return {
        kind: base.kind,
        reason: parseBoundedText(object.reason, `${path}.reason`),
        cancellationRef,
        publication,
      };
    }
    case "transcript_evidence_observed": {
      const object = requireRecord(base, path, ["kind", "payload", "publication"]);
      const publication = requireRecord(object.publication, `${path}.publication`, ["action"]);
      return {
        kind: base.kind,
        payload: parseBoundedPayload(object.payload, `${path}.payload`),
        publication: { action: parseLiteral(publication.action, "observation_only", `${path}.publication.action`) },
      };
    }
    default:
      throw new ContractParseError(`${path}.kind`, "is not a supported runtime event kind");
  }
}

function parseContractDigests(value: unknown, path: string): ContractDigests {
  const object = requireRecord(value, path, [
    "runSnapshot",
    "invocationEnvelope",
    "runtimeEvent",
    "runtimeExit",
    "runtimeDurableState",
  ]);
  return {
    runSnapshot: parseDigest(object.runSnapshot, `${path}.runSnapshot`, parseContractDigest) as ContractDigest,
    invocationEnvelope: parseDigest(
      object.invocationEnvelope,
      `${path}.invocationEnvelope`,
      parseContractDigest
    ) as ContractDigest,
    runtimeEvent: parseDigest(object.runtimeEvent, `${path}.runtimeEvent`, parseContractDigest) as ContractDigest,
    runtimeExit: parseDigest(object.runtimeExit, `${path}.runtimeExit`, parseContractDigest) as ContractDigest,
    runtimeDurableState: parseDigest(
      object.runtimeDurableState,
      `${path}.runtimeDurableState`,
      parseContractDigest
    ) as ContractDigest,
  };
}

function parseSnapshotContent(value: unknown, path: string): RunSnapshotContent {
  const object = requireRecord(
    value,
    path,
    [
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
    ],
    ["contentDigest"]
  );
  const assignmentObject = requireRecord(object.assignment, `${path}.assignment`, [
    "assignmentRef",
    "revision",
    "targetRef",
    "objective",
    "acceptanceCriteria",
  ]);
  if (
    !Array.isArray(assignmentObject.acceptanceCriteria) ||
    assignmentObject.acceptanceCriteria.length < 1 ||
    assignmentObject.acceptanceCriteria.length > 32
  ) {
    throw new ContractParseError(`${path}.assignment.acceptanceCriteria`, "must contain between 1 and 32 items");
  }
  const profileObject = requireRecord(object.profile, `${path}.profile`, [
    "profileRef",
    "revision",
    "role",
    "behavioralPrompt",
  ]);
  const roles = ["worker", "delegator", "gardener", "chief_of_staff", "hr", "evaluator", "custom"] as const;
  if (!roles.includes(profileObject.role as (typeof roles)[number])) {
    throw new ContractParseError(`${path}.profile.role`, "is not a supported Plane Agent role");
  }
  if (!Array.isArray(object.context) || object.context.length > 64) {
    throw new ContractParseError(`${path}.context`, "must contain at most 64 items");
  }
  const contexts = object.context.map((item, index) => {
    const contextObject = requireRecord(item, `${path}.context[${index}]`, ["contextRef", "revision", "contentDigest"]);
    return {
      contextRef: parseRef(contextObject.contextRef, `${path}.context[${index}].contextRef`, parseContextRef),
      revision: parseBoundedToken(contextObject.revision, `${path}.context[${index}].revision`),
      contentDigest: parseDigest(
        contextObject.contentDigest,
        `${path}.context[${index}].contentDigest`,
        parseContentDigest
      ) as ContentDigest,
    };
  });
  const catalogObject = requireRecord(object.toolCatalog, `${path}.toolCatalog`, ["catalogDigest", "eagerOperations"]);
  if (!Array.isArray(catalogObject.eagerOperations) || catalogObject.eagerOperations.length > 64) {
    throw new ContractParseError(`${path}.toolCatalog.eagerOperations`, "must contain at most 64 items");
  }
  const eagerOperations = catalogObject.eagerOperations.map((item, index) => {
    const operationObject = requireRecord(item, `${path}.toolCatalog.eagerOperations[${index}]`, [
      "operationRef",
      "schemaDigest",
      "disclosure",
    ]);
    if (operationObject.disclosure !== "eager" && operationObject.disclosure !== "progressive") {
      throw new ContractParseError(`${path}.toolCatalog.eagerOperations[${index}].disclosure`, "is not supported");
    }
    return {
      operationRef: parseRef(
        operationObject.operationRef,
        `${path}.toolCatalog.eagerOperations[${index}].operationRef`,
        parseOperationRef
      ),
      schemaDigest: parseDigest(
        operationObject.schemaDigest,
        `${path}.toolCatalog.eagerOperations[${index}].schemaDigest`,
        parseContentDigest
      ) as ContentDigest,
      disclosure: operationObject.disclosure as "eager" | "progressive",
    };
  });
  const runtimePolicyObject = requireRecord(object.runtimePolicy, `${path}.runtimePolicy`, [
    "model",
    "adapter",
    "isolation",
    "maxEventPayloadBytes",
    "maxArtifactBytes",
    "maxReceiptBytes",
  ]);
  const modelObject = requireRecord(runtimePolicyObject.model, `${path}.runtimePolicy.model`, ["provider", "model"]);
  if (runtimePolicyObject.isolation !== "single-invocation") {
    throw new ContractParseError(`${path}.runtimePolicy.isolation`, "must be single-invocation");
  }
  const parsed: RunSnapshotContent = {
    protocol: parseLiteral(object.protocol, PLANE_AGENT_RUNTIME_PROTOCOL, `${path}.protocol`),
    workspaceRef: parseRef(object.workspaceRef, `${path}.workspaceRef`, parseWorkspaceRef),
    runId: parseRef(object.runId, `${path}.runId`, parseRunId),
    assignment: {
      assignmentRef: parseRef(assignmentObject.assignmentRef, `${path}.assignment.assignmentRef`, parseAssignmentRef),
      revision: parseBoundedToken(assignmentObject.revision, `${path}.assignment.revision`),
      targetRef: parseRef(assignmentObject.targetRef, `${path}.assignment.targetRef`, parseTargetRef),
      objective: parseBoundedText(assignmentObject.objective, `${path}.assignment.objective`),
      acceptanceCriteria: assignmentObject.acceptanceCriteria.map((item, index) =>
        parseBoundedText(item, `${path}.assignment.acceptanceCriteria[${index}]`)
      ),
    },
    actorRef: parseRef(object.actorRef, `${path}.actorRef`, parseActorRef),
    profile: {
      profileRef: parseRef(profileObject.profileRef, `${path}.profile.profileRef`, parseProfileVersionRef),
      revision: parseBoundedToken(profileObject.revision, `${path}.profile.revision`),
      role: profileObject.role as AgentRole,
      behavioralPrompt: parseBoundedPrompt(profileObject.behavioralPrompt, `${path}.profile.behavioralPrompt`),
    },
    context: contexts,
    toolCatalog: {
      catalogDigest: parseDigest(
        catalogObject.catalogDigest,
        `${path}.toolCatalog.catalogDigest`,
        parseContentDigest
      ) as ContentDigest,
      eagerOperations,
    },
    runtimePolicy: {
      model: {
        provider: parseBoundedToken(modelObject.provider, `${path}.runtimePolicy.model.provider`),
        model: parseBoundedToken(modelObject.model, `${path}.runtimePolicy.model.model`),
      },
      adapter: parseBoundedToken(runtimePolicyObject.adapter, `${path}.runtimePolicy.adapter`),
      isolation: "single-invocation",
      maxEventPayloadBytes: parseInteger(
        runtimePolicyObject.maxEventPayloadBytes,
        `${path}.runtimePolicy.maxEventPayloadBytes`,
        MAX_BOUNDED_BYTE_COUNT
      ),
      maxArtifactBytes: parseInteger(
        runtimePolicyObject.maxArtifactBytes,
        `${path}.runtimePolicy.maxArtifactBytes`,
        MAX_BOUNDED_BYTE_COUNT
      ),
      maxReceiptBytes: parseInteger(
        runtimePolicyObject.maxReceiptBytes,
        `${path}.runtimePolicy.maxReceiptBytes`,
        MAX_BOUNDED_BYTE_COUNT
      ),
    },
    totalBudget: parseBudget(object.totalBudget, `${path}.totalBudget`),
    contractDigests: parseContractDigests(object.contractDigests, `${path}.contractDigests`),
  };
  return parsed;
}

export function parseRunSnapshot(value: unknown): RunSnapshot {
  const raw = parseRawJson(value, "RunSnapshot");
  const object = requireRecord(raw, "RunSnapshot", [
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
  ]);
  const content = parseSnapshotContent(object, "RunSnapshot");
  const contentDigest = parseDigest(
    object.contentDigest,
    "RunSnapshot.contentDigest",
    parseRunSnapshotContentDigest
  ) as RunSnapshotContentDigest;
  const parsed = { ...content, contentDigest };
  if (computeRunSnapshotContentDigest(content) !== contentDigest) {
    throw new ContractParseError(
      "RunSnapshot.contentDigest",
      "does not match the canonical immutable snapshot content"
    );
  }
  return deepFreeze(markValidatedContract(parsed, "RunSnapshot"));
}

export function parseInvocationEnvelope(value: unknown): InvocationEnvelope {
  const raw = parseRawJson(value, "InvocationEnvelope");
  const object = requireRecord(
    raw,
    "InvocationEnvelope",
    [
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
    ["checkpointRef"]
  );
  const triggerObject = requireRecord(
    object.trigger,
    "InvocationEnvelope.trigger",
    ["kind"],
    ["eventRef", "pendingInputEventRef", "answerFactDigest"]
  );
  let trigger: InvocationTrigger;
  if (triggerObject.kind === "initial") {
    if (
      Object.hasOwn(triggerObject, "eventRef") ||
      Object.hasOwn(triggerObject, "pendingInputEventRef") ||
      Object.hasOwn(triggerObject, "answerFactDigest")
    ) {
      throw new ContractParseError("InvocationEnvelope.trigger", "initial invocations cannot cite continuation events");
    }
    trigger = { kind: "initial" };
  } else if (triggerObject.kind === "human_input") {
    if (
      !Object.hasOwn(triggerObject, "eventRef") ||
      !Object.hasOwn(triggerObject, "pendingInputEventRef") ||
      !Object.hasOwn(triggerObject, "answerFactDigest")
    ) {
      throw new ContractParseError(
        "InvocationEnvelope.trigger",
        "human-input invocations require the Plane answer event, exact pending input event, and answer fact digest"
      );
    }
    trigger = {
      kind: "human_input",
      eventRef: parseRef(triggerObject.eventRef, "InvocationEnvelope.trigger.eventRef", parseEventRef),
      pendingInputEventRef: parseRef(
        triggerObject.pendingInputEventRef,
        "InvocationEnvelope.trigger.pendingInputEventRef",
        parseEventRef
      ),
      answerFactDigest: parseDigest(
        triggerObject.answerFactDigest,
        "InvocationEnvelope.trigger.answerFactDigest",
        parseContentDigest
      ) as ContentDigest,
    };
  } else if (triggerObject.kind === "recoverable_restart" || triggerObject.kind === "continuation") {
    if (Object.hasOwn(triggerObject, "answerFactDigest")) {
      throw new ContractParseError(
        "InvocationEnvelope.trigger.answerFactDigest",
        "is only valid for a human-input invocation"
      );
    }
    if (!Object.hasOwn(triggerObject, "eventRef")) {
      throw new ContractParseError("InvocationEnvelope.trigger.eventRef", "is required for a continuation");
    }
    trigger = {
      kind: triggerObject.kind,
      eventRef: parseRef(triggerObject.eventRef, "InvocationEnvelope.trigger.eventRef", parseEventRef),
      ...(triggerObject.pendingInputEventRef === undefined
        ? {}
        : {
            pendingInputEventRef: parseRef(
              triggerObject.pendingInputEventRef,
              "InvocationEnvelope.trigger.pendingInputEventRef",
              parseEventRef
            ),
          }),
    };
  } else {
    throw new ContractParseError("InvocationEnvelope.trigger.kind", "is not supported");
  }
  if (!Array.isArray(object.newContextEventRefs) || object.newContextEventRefs.length > 64) {
    throw new ContractParseError("InvocationEnvelope.newContextEventRefs", "must contain at most 64 items");
  }
  const parsed = {
    protocol: parseLiteral(object.protocol, PLANE_AGENT_RUNTIME_PROTOCOL, "InvocationEnvelope.protocol"),
    workspaceRef: parseRef(object.workspaceRef, "InvocationEnvelope.workspaceRef", parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, "InvocationEnvelope.actorRef", parseActorRef),
    runId: parseRef(object.runId, "InvocationEnvelope.runId", parseRunId),
    invocationId: parseRef(object.invocationId, "InvocationEnvelope.invocationId", parseInvocationId),
    runSnapshotDigest: parseDigest(
      object.runSnapshotDigest,
      "InvocationEnvelope.runSnapshotDigest",
      parseRunSnapshotContentDigest
    ) as RunSnapshotContentDigest,
    trigger,
    newContextEventRefs: object.newContextEventRefs.map((item, index) =>
      parseRef(item, `InvocationEnvelope.newContextEventRefs[${index}]`, parseEventRef)
    ),
    ...(object.checkpointRef === undefined
      ? {}
      : { checkpointRef: parseRef(object.checkpointRef, "InvocationEnvelope.checkpointRef", parseCheckpointRef) }),
    remainingBudget: parseBudget(object.remainingBudget, "InvocationEnvelope.remainingBudget"),
    lease: (() => {
      const lease = requireRecord(object.lease, "InvocationEnvelope.lease", ["leaseId", "expiresAt", "renewAfterMs"]);
      return {
        leaseId: parseRef(lease.leaseId, "InvocationEnvelope.lease.leaseId", parseLeaseId),
        expiresAt: parseTimestamp(lease.expiresAt, "InvocationEnvelope.lease.expiresAt"),
        renewAfterMs: parseInteger(lease.renewAfterMs, "InvocationEnvelope.lease.renewAfterMs"),
      };
    })(),
    cancellationRef: parseRef(object.cancellationRef, "InvocationEnvelope.cancellationRef", parseCancellationRef),
    causationRef: parseRef(object.causationRef, "InvocationEnvelope.causationRef", parseCausationRef),
    correlationId: parseRef(object.correlationId, "InvocationEnvelope.correlationId", parseCorrelationId),
    idempotencyKey: parseRef(object.idempotencyKey, "InvocationEnvelope.idempotencyKey", parseIdempotencyKey),
  } satisfies InvocationEnvelopeShape;
  return deepFreeze(markValidatedContract(parsed, "InvocationEnvelope"));
}

export function parseRuntimeEvent(value: unknown): RuntimeEvent {
  const raw = parseRawJson(value, "RuntimeEvent");
  const object = requireRecord(raw, "RuntimeEvent", [
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
  ]);
  const parsed = {
    protocol: parseLiteral(object.protocol, PLANE_AGENT_RUNTIME_PROTOCOL, "RuntimeEvent.protocol"),
    trust: parseLiteral(object.trust, "untrusted", "RuntimeEvent.trust"),
    workspaceRef: parseRef(object.workspaceRef, "RuntimeEvent.workspaceRef", parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, "RuntimeEvent.actorRef", parseActorRef),
    runId: parseRef(object.runId, "RuntimeEvent.runId", parseRunId),
    invocationId: parseRef(object.invocationId, "RuntimeEvent.invocationId", parseInvocationId),
    sequence: parseInteger(object.sequence, "RuntimeEvent.sequence"),
    eventId: parseRef(object.eventId, "RuntimeEvent.eventId", parseEventRef),
    idempotencyKey: parseRef(object.idempotencyKey, "RuntimeEvent.idempotencyKey", parseIdempotencyKey),
    correlationId: parseRef(object.correlationId, "RuntimeEvent.correlationId", parseCorrelationId),
    causationRef: parseRef(object.causationRef, "RuntimeEvent.causationRef", parseCausationRef),
    observedAt: parseTimestamp(object.observedAt, "RuntimeEvent.observedAt"),
    body: parseBody(object.body, "RuntimeEvent.body"),
  } satisfies RuntimeEventShape;
  const result = deepFreeze(markValidatedContract(parsed, "RuntimeEvent"));
  if (!isCanonicalJsonUtf8ByteLengthAtMost(result, MAX_SERIALIZED_JSON_BYTES)) {
    throw new ContractParseError("RuntimeEvent", "canonical serialized UTF-8 bytes exceed the global limit");
  }
  return result;
}

export function parseRuntimeExit(value: unknown): RuntimeExit {
  const raw = parseRawJson(value, "RuntimeExit");
  const object = requireRecord(
    raw,
    "RuntimeExit",
    [
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
    ["inputEventRef", "failure"]
  );
  const base = {
    protocol: parseLiteral(object.protocol, PLANE_AGENT_RUNTIME_PROTOCOL, "RuntimeExit.protocol"),
    authority: parseLiteral(object.authority, "runtime_evidence_only", "RuntimeExit.authority"),
    workspaceRef: parseRef(object.workspaceRef, "RuntimeExit.workspaceRef", parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, "RuntimeExit.actorRef", parseActorRef),
    runId: parseRef(object.runId, "RuntimeExit.runId", parseRunId),
    invocationId: parseRef(object.invocationId, "RuntimeExit.invocationId", parseInvocationId),
    finalSequence: parseInteger(object.finalSequence, "RuntimeExit.finalSequence"),
    idempotencyKey: parseRef(object.idempotencyKey, "RuntimeExit.idempotencyKey", parseIdempotencyKey),
    correlationId: parseRef(object.correlationId, "RuntimeExit.correlationId", parseCorrelationId),
    causationRef: parseRef(object.causationRef, "RuntimeExit.causationRef", parseCausationRef),
  };
  let parsed: RuntimeExitShape;
  if (object.kind === "completed") {
    if (Object.hasOwn(object, "inputEventRef") || Object.hasOwn(object, "failure")) {
      throw new ContractParseError("RuntimeExit", "completed exits cannot carry failure or input references");
    }
    parsed = { ...base, kind: "completed" };
  } else if (object.kind === "waiting_for_input") {
    if (Object.hasOwn(object, "failure") || !Object.hasOwn(object, "inputEventRef")) {
      throw new ContractParseError("RuntimeExit", "waiting exits require only an input event reference");
    }
    parsed = {
      ...base,
      kind: "waiting_for_input",
      inputEventRef: parseRef(object.inputEventRef, "RuntimeExit.inputEventRef", parseEventRef),
    };
  } else if (object.kind === "failed" || object.kind === "blocked" || object.kind === "cancelled") {
    if (Object.hasOwn(object, "inputEventRef") || !Object.hasOwn(object, "failure")) {
      throw new ContractParseError("RuntimeExit", "terminal failure exits require exactly one failure");
    }
    parsed = { ...base, kind: object.kind, failure: parseRuntimeFailure(object.failure, "RuntimeExit.failure") };
  } else {
    throw new ContractParseError("RuntimeExit.kind", "is not supported");
  }
  return deepFreeze(markValidatedContract(parsed, "RuntimeExit"));
}

const sha256 = (value: string): string => createHash("sha256").update(value, "utf8").digest("hex");

export function computeRunSnapshotContentDigest(snapshot: RunSnapshot | RunSnapshotContent): RunSnapshotContentDigest {
  return createRunSnapshotContentDigest(sha256(canonicalizeJson(withoutSnapshotContentDigest(snapshot))));
}

export function verifyRunSnapshotContentDigest(snapshot: RunSnapshot): boolean {
  return (
    isValidatedContract(snapshot, "RunSnapshot") && snapshot.contentDigest === computeRunSnapshotContentDigest(snapshot)
  );
}

export function verifyInvocationSnapshotBinding(snapshot: RunSnapshot, invocation: InvocationEnvelope): boolean {
  return (
    isValidatedContract(snapshot, "RunSnapshot") &&
    isValidatedContract(invocation, "InvocationEnvelope") &&
    verifyRunSnapshotContentDigest(snapshot) &&
    invocation.runSnapshotDigest === snapshot.contentDigest
  );
}

export function createRunSnapshot(
  input: Omit<RunSnapshotShape, "contractDigests" | "contentDigest">,
  manifest: ContractManifest
): RunSnapshot {
  const content: RunSnapshotContent = {
    ...input,
    contractDigests: contractDigestsFromManifest(manifest),
  };
  return parseRunSnapshot({ ...content, contentDigest: computeRunSnapshotContentDigest(content) });
}

export type InvocationTrigger =
  | Readonly<{ kind: "initial" }>
  | Readonly<{
      kind: "human_input";
      eventRef: EventRef;
      pendingInputEventRef: EventRef;
      answerFactDigest: ContentDigest;
    }>
  | Readonly<{
      kind: "recoverable_restart" | "continuation";
      eventRef: EventRef;
      pendingInputEventRef?: EventRef;
    }>;

export type RuntimeLease = Readonly<{
  leaseId: LeaseId;
  expiresAt: Timestamp;
  renewAfterMs: number;
}>;

type InvocationEnvelopeShape = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  runId: RunId;
  invocationId: InvocationId;
  runSnapshotDigest: RunSnapshotContentDigest;
  trigger: InvocationTrigger;
  newContextEventRefs: readonly EventRef[];
  checkpointRef?: CheckpointRef;
  remainingBudget: RuntimeBudget;
  lease: RuntimeLease;
  cancellationRef: CancellationRef;
  causationRef: CausationRef;
  correlationId: CorrelationId;
  idempotencyKey: IdempotencyKey;
}>;

export type InvocationEnvelope = InvocationEnvelopeShape & ValidatedContract<"InvocationEnvelope">;

export type BoundedPayload =
  | Readonly<{ kind: "inline_text"; contentType: "text/plain"; text: BoundedText }>
  | Readonly<{
      kind: "payload_ref";
      payloadRef: PayloadRef;
      contentType: string;
      contentDigest: ContentDigest;
      sizeBytes: number;
    }>;

export type ArtifactReference = Readonly<{
  artifactRef: ArtifactRef;
  contentDigest: ContentDigest;
  mediaType: string;
  sizeBytes: number;
}>;

export type RuntimeFailure = Readonly<{
  code: "runtime_error" | "lease_expired" | "invalid_continuation" | "budget_exhausted" | "cancelled";
  message: BoundedText;
  retryable: boolean;
}>;

export type RuntimeUsage = Readonly<{
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
}>;

type Publication<ProductKind extends string, ProductRef extends OpaqueRef<string>> =
  | Readonly<{
      action: "proposal";
      productKind: ProductKind;
      productRef: ProductRef;
      operationAttemptRef: OperationAttemptRef;
    }>
  | Readonly<{
      action: "applied";
      productKind: ProductKind;
      productRef: ProductRef;
      operationAttemptRef: OperationAttemptRef;
      operationRef: OperationRef;
      applicationServiceRef: ApplicationServiceRef;
      gatewayReceiptRef: GatewayReceiptRef;
      receiptRef: ReceiptRef;
      auditReceiptRef: AuditReceiptRef;
      productEventRef: ProductEventRef;
    }>;

type AppliedPublication<ProductKind extends string, ProductRef extends OpaqueRef<string>> = Extract<
  Publication<ProductKind, ProductRef>,
  { action: "applied" }
>;

export type ConversationPublication = Publication<"conversation", ConversationRef>;
export type InputRequestPublication = Publication<"input_request", InputRequestRef>;
export type ArtifactPublication = Publication<"artifact", ArtifactRef>;
export type OutcomeSubmissionPublication = AppliedPublication<"outcome_submission", OutcomeSubmissionRef>;
type TerminalPublication<ProductKind extends string> = Readonly<{
  action: "applied";
  productKind: ProductKind;
  productRef: ProductEventRef;
  operationAttemptRef: OperationAttemptRef;
  operationRef: OperationRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  productEventRef: ProductEventRef;
}>;

export type FailurePublication = TerminalPublication<"run_failure">;
export type BlockerPublication = TerminalPublication<"run_blocker">;
export type CancellationPublication = TerminalPublication<"run_cancellation"> &
  Readonly<{
    cancellationRef: CancellationRef;
  }>;
export type AnyProductPublication =
  | ConversationPublication
  | InputRequestPublication
  | ArtifactPublication
  | OutcomeSubmissionPublication
  | FailurePublication
  | BlockerPublication
  | CancellationPublication;

export type RuntimeEventBody =
  | Readonly<{
      kind: "progress_observed";
      payload: BoundedPayload;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "conversation_publication_observed";
      payload: BoundedPayload;
      publication: ConversationPublication;
    }>
  | Readonly<{
      kind: "input_request_observed";
      question: BoundedText;
      publication: InputRequestPublication;
    }>
  | Readonly<{
      kind: "artifact_observed";
      artifact: ArtifactReference;
      publication: ArtifactPublication;
    }>
  | Readonly<{
      kind: "usage_observed";
      usage: RuntimeUsage;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "outcome_submission_observed";
      payload: BoundedPayload;
      publication: OutcomeSubmissionPublication;
    }>
  | Readonly<{
      kind: "failure_observed";
      failure: RuntimeFailure;
      publication: FailurePublication;
    }>
  | Readonly<{
      kind: "blocker_observed";
      reason: BoundedText;
      publication: BlockerPublication;
    }>
  | Readonly<{
      kind: "cancellation_observed";
      reason: BoundedText;
      cancellationRef: CancellationRef;
      publication: CancellationPublication;
    }>
  | Readonly<{
      kind: "transcript_evidence_observed";
      payload: BoundedPayload;
      publication: Readonly<{ action: "observation_only" }>;
    }>;

type RuntimeEventShape = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  trust: "untrusted";
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  runId: RunId;
  invocationId: InvocationId;
  sequence: number;
  eventId: EventId;
  idempotencyKey: IdempotencyKey;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  observedAt: Timestamp;
  body: RuntimeEventBody;
}>;

export type RuntimeEvent = RuntimeEventShape & ValidatedContract<"RuntimeEvent">;

type RuntimeExitBase = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  authority: "runtime_evidence_only";
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  runId: RunId;
  invocationId: InvocationId;
  finalSequence: number;
  idempotencyKey: IdempotencyKey;
  correlationId: CorrelationId;
  causationRef: CausationRef;
}>;

type RuntimeExitShape =
  | (RuntimeExitBase & Readonly<{ kind: "completed" }>)
  | (RuntimeExitBase & Readonly<{ kind: "waiting_for_input"; inputEventRef: EventRef }>)
  | (RuntimeExitBase & Readonly<{ kind: "failed" | "blocked" | "cancelled"; failure: RuntimeFailure }>);

export type RuntimeExit = RuntimeExitShape & ValidatedContract<"RuntimeExit">;

export type RuntimeVerificationErrorCode =
  | "unparsed_contract_input"
  | "unparsed_durable_state"
  | "durable_state_invalid"
  | "authority_facts_missing"
  | "contract_digest_mismatch"
  | "snapshot_content_digest_mismatch"
  | "invocation_snapshot_binding_mismatch"
  | "invocation_identity_mismatch"
  | "durable_state_head_mismatch"
  | "durable_state_digest_mismatch"
  | "initial_checkpoint_forbidden"
  | "continuation_checkpoint_missing"
  | "checkpoint_untrusted"
  | "lease_untrusted"
  | "budget_baseline_missing"
  | "budget_increased"
  | "event_identity_mismatch"
  | "event_sequence_invalid"
  | "event_duplicate"
  | "event_idempotency_duplicate"
  | "event_idempotency_conflict"
  | "event_correlation_mismatch"
  | "events_after_terminal"
  | "event_payload_too_large"
  | "artifact_too_large"
  | "receipt_too_large"
  | "publication_receipt_duplicate"
  | "publication_receipt_unused"
  | "publication_receipt_missing"
  | "publication_receipt_mismatch"
  | "publication_authority_mismatch"
  | "publication_product_mismatch"
  | "cancellation_mismatch"
  | "terminal_event_mismatch"
  | "final_sequence_mismatch"
  | "exit_identity_mismatch"
  | "exit_reference_mismatch"
  | "exit_failure_mismatch"
  | "pending_input_mismatch"
  | "human_input_answer_mismatch"
  | "publication_product_duplicate";

export type RuntimeVerificationError = Readonly<{
  code: RuntimeVerificationErrorCode;
  path: string;
  message: string;
}>;

export type TrustedCheckpointVerification = Readonly<{
  checkpointRef: CheckpointRef;
  isVerified: boolean;
}>;

export type TrustedLeaseVerification = Readonly<{
  leaseId: LeaseId;
  isValid: boolean;
}>;

export type TrustedCancellationVerification = Readonly<{
  cancellationRef: CancellationRef;
  isCancelled: boolean;
}>;

export type RuntimeLifecycleState =
  | "queued"
  | "running"
  | "waiting_for_input"
  | "succeeded"
  | "failed"
  | "blocked"
  | "cancelled";

export type TrustedRuntimeAuthority = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  invocationId: InvocationId;
  snapshotContentDigest: RunSnapshotContentDigest;
  cancellationRef: CancellationRef;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  invocationIdempotencyKey: IdempotencyKey;
}>;

export const RUNTIME_DURABLE_STATE_VERSION = "v1" as const;

export type RuntimeDurableStateBinding = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  snapshotContentDigest: RunSnapshotContentDigest;
}>;

export type TrustedDurableStateHead = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  snapshotContentDigest: RunSnapshotContentDigest;
  revision: number;
  stateDigest: ContentDigest;
  previousRevision?: number;
  previousStateDigest?: ContentDigest;
}>;

export type DurableAcceptedProductBinding =
  | Readonly<{
      action: "proposal";
      productKind: "conversation" | "input_request" | "artifact";
      productRef: ConversationRef | InputRequestRef | ArtifactRef;
      operationAttemptRef: OperationAttemptRef;
    }>
  | Readonly<{
      action: "applied";
      productKind: AnyProductPublication["productKind"];
      productRef: AnyProductPublication["productRef"];
      operationAttemptRef: OperationAttemptRef;
      operationRef: OperationRef;
      applicationServiceRef: ApplicationServiceRef;
      gatewayReceiptRef: GatewayReceiptRef;
      receiptRef: ReceiptRef;
      auditReceiptRef: AuditReceiptRef;
      productEventRef: ProductEventRef;
      cancellationRef?: CancellationRef;
    }>;

export type DurableAcceptedEvent = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  snapshotContentDigest: RunSnapshotContentDigest;
  eventId: EventId;
  idempotencyKey: IdempotencyKey;
  invocationId: InvocationId;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  sequence: number;
  fingerprint: ContentDigest;
  kind: RuntimeEventBody["kind"];
  productBinding?: DurableAcceptedProductBinding;
}>;

export type TrustedHumanAnswerResponderPrincipal = Readonly<{
  kind: "human_user" | "external_integration";
  planePrincipalId: ActorRef;
}>;

export type TrustedHumanInputAnswerFact = Readonly<{
  answerEventRef: EventRef;
  inputRequestRef: InputRequestRef;
  responderPrincipal: TrustedHumanAnswerResponderPrincipal;
  workspaceRef: WorkspaceRef;
  runId: RunId;
  authorizationReceiptRef: AuthorizationReceiptRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  payloadDigest: ContentDigest;
}>;

export type TrustedHumanInputAnswer = TrustedHumanInputAnswerFact &
  Readonly<{
    answerFactDigest: ContentDigest;
  }>;

export type TrustedHumanAnswerHead = Readonly<{
  answerFactDigest: ContentDigest;
}>;

export type DurableAcceptedHumanInputAnswer = TrustedHumanInputAnswer;

export type DurableAcceptedExit = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  snapshotContentDigest: RunSnapshotContentDigest;
  invocationId: InvocationId;
  idempotencyKey: IdempotencyKey;
  finalSequence: number;
  fingerprint: ContentDigest;
  kind: RuntimeExit["kind"];
  inputEventId?: EventId;
  terminalEventId?: EventId;
}>;

export type DurableTerminalBinding = Readonly<{
  eventId: EventId;
  invocationId: InvocationId;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  productBinding: Extract<DurableAcceptedProductBinding, { action: "applied" }>;
}>;

export type DurablePendingInputBinding = Readonly<{
  eventId: EventId;
  invocationId: InvocationId;
  correlationId: CorrelationId;
  causationRef: CausationRef;
  inputRequestRef: InputRequestRef;
  productEventRef: ProductEventRef;
  operationAttemptRef: OperationAttemptRef;
  operationRef: OperationRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  questionDigest: ContentDigest;
}>;

type RuntimeDurableStateShape = Readonly<{
  protocol: PlaneAgentRuntimeProtocol;
  stateVersion: typeof RUNTIME_DURABLE_STATE_VERSION;
  binding: RuntimeDurableStateBinding;
  state: RuntimeLifecycleState;
  revision: number;
  stateDigest: ContentDigest;
  previousRevision?: number;
  previousStateDigest?: ContentDigest;
  lastAcceptedSequence: number;
  acceptedEvents: readonly DurableAcceptedEvent[];
  acceptedHumanInputAnswers: readonly DurableAcceptedHumanInputAnswer[];
  acceptedExits: readonly DurableAcceptedExit[];
  terminal?: DurableTerminalBinding;
  pendingInput?: DurablePendingInputBinding;
}>;

export type RuntimeDurableState = RuntimeDurableStateShape & ValidatedContract<"RuntimeDurableState">;

export type TrustedPublicationReceipt = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  invocationId: InvocationId;
  productKind: AnyProductPublication["productKind"];
  productRef: AnyProductPublication["productRef"];
  operationAttemptRef: OperationAttemptRef;
  operationRef: OperationRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  productEventRef: ProductEventRef;
  cancellationRef?: CancellationRef;
}>;

export type RuntimeVerificationFacts = Readonly<{
  authority: TrustedRuntimeAuthority;
  lifecycle: RuntimeDurableState;
  durableStateHead: TrustedDurableStateHead;
  lease: TrustedLeaseVerification;
  cancellation: TrustedCancellationVerification;
  checkpoint?: TrustedCheckpointVerification;
  humanInputAnswer?: TrustedHumanInputAnswer;
  humanInputAnswerHead?: TrustedHumanAnswerHead;
  previousRemainingBudget?: RuntimeBudget;
  publicationReceipts: readonly TrustedPublicationReceipt[];
}>;

export type RuntimeVerificationInput = Readonly<{
  manifest: ContractManifest;
  snapshot: RunSnapshot;
  invocation: InvocationEnvelope;
  events: readonly RuntimeEvent[];
  exit: RuntimeExit;
  trusted: RuntimeVerificationFacts;
}>;

export type RuntimeExecutionState = RuntimeExit["kind"];

export type RuntimeVerificationSuccess = Readonly<{
  ok: true;
  result: "accepted" | "idempotent_replay";
  state: RuntimeExecutionState;
  finalSequence: number;
  terminalEventCount: number;
  nextLifecycle: RuntimeDurableState;
}>;

export type RuntimeVerificationFailure = Readonly<{
  ok: false;
  errors: readonly RuntimeVerificationError[];
}>;

export type RuntimeVerificationResult = RuntimeVerificationSuccess | RuntimeVerificationFailure;

export interface RuntimeSemanticVerifier {
  verify(input: RuntimeVerificationInput): RuntimeVerificationResult;
}

const DURABLE_EVENT_KINDS = [
  "progress_observed",
  "conversation_publication_observed",
  "input_request_observed",
  "artifact_observed",
  "usage_observed",
  "outcome_submission_observed",
  "failure_observed",
  "blocker_observed",
  "cancellation_observed",
  "transcript_evidence_observed",
] as const;

const DURABLE_PRODUCT_KINDS = [
  "conversation",
  "input_request",
  "artifact",
  "outcome_submission",
  "run_failure",
  "run_blocker",
  "run_cancellation",
] as const;

const DURABLE_TERMINAL_KINDS = ["run_failure", "run_blocker", "run_cancellation", "outcome_submission"] as const;
const DURABLE_PROPOSAL_PRODUCT_KINDS = ["conversation", "input_request", "artifact"] as const;

function parseRuntimeDurableStateBinding(value: unknown, path: string): RuntimeDurableStateBinding {
  const object = requireRecord(value, path, [
    "workspaceRef",
    "actorRef",
    "profileVersionRef",
    "runId",
    "snapshotContentDigest",
  ]);
  return {
    workspaceRef: parseRef(object.workspaceRef, `${path}.workspaceRef`, parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, `${path}.actorRef`, parseActorRef),
    profileVersionRef: parseRef(object.profileVersionRef, `${path}.profileVersionRef`, parseProfileVersionRef),
    runId: parseRef(object.runId, `${path}.runId`, parseRunId),
    snapshotContentDigest: parseDigest(
      object.snapshotContentDigest,
      `${path}.snapshotContentDigest`,
      parseRunSnapshotContentDigest
    ) as RunSnapshotContentDigest,
  };
}

function parseDurableProductRef(productKind: (typeof DURABLE_PRODUCT_KINDS)[number], value: unknown, path: string) {
  switch (productKind) {
    case "conversation":
      return parseRef(value, path, parseConversationRef);
    case "input_request":
      return parseRef(value, path, parseInputRequestRef);
    case "run_failure":
    case "run_blocker":
    case "run_cancellation":
      return parseRef(value, path, parseProductEventRef);
    case "artifact":
      return parseRef(value, path, parseArtifactRef);
    case "outcome_submission":
      return parseRef(value, path, parseOutcomeSubmissionRef);
  }
}

function parseDurableProductBinding(value: unknown, path: string): DurableAcceptedProductBinding {
  const base = requireRecord(
    value,
    path,
    ["action", "productKind", "productRef", "operationAttemptRef"],
    [
      "operationRef",
      "applicationServiceRef",
      "gatewayReceiptRef",
      "receiptRef",
      "auditReceiptRef",
      "productEventRef",
      "cancellationRef",
    ]
  );
  if (base.action !== "proposal" && base.action !== "applied") {
    throw new ContractParseError(`${path}.action`, "must be proposal or applied");
  }
  if (!DURABLE_PRODUCT_KINDS.includes(base.productKind as (typeof DURABLE_PRODUCT_KINDS)[number])) {
    throw new ContractParseError(`${path}.productKind`, "is not a supported product kind");
  }
  const productKind = base.productKind as (typeof DURABLE_PRODUCT_KINDS)[number];
  const productRef = parseDurableProductRef(productKind, base.productRef, `${path}.productRef`);
  const operationAttemptRef = parseRef(
    base.operationAttemptRef,
    `${path}.operationAttemptRef`,
    parseOperationAttemptRef
  );
  if (base.action === "proposal") {
    if (!DURABLE_PROPOSAL_PRODUCT_KINDS.includes(productKind as (typeof DURABLE_PROPOSAL_PRODUCT_KINDS)[number])) {
      throw new ContractParseError(`${path}.action`, "terminal durable product bindings cannot be proposals");
    }
    for (const key of [
      "operationRef",
      "applicationServiceRef",
      "gatewayReceiptRef",
      "receiptRef",
      "auditReceiptRef",
      "productEventRef",
      "cancellationRef",
    ]) {
      if (Object.hasOwn(base, key)) {
        throw new ContractParseError(`${path}.${key}`, "is only valid for an applied product binding");
      }
    }
    return { action: "proposal", productKind, productRef, operationAttemptRef } as DurableAcceptedProductBinding;
  }

  const object = requireRecord(
    value,
    path,
    [
      "action",
      "productKind",
      "productRef",
      "operationAttemptRef",
      "operationRef",
      "applicationServiceRef",
      "gatewayReceiptRef",
      "receiptRef",
      "auditReceiptRef",
      "productEventRef",
      ...(productKind === "run_cancellation" ? ["cancellationRef"] : []),
    ],
    []
  );
  const applied = {
    action: "applied" as const,
    productKind,
    productRef,
    operationAttemptRef,
    operationRef: parseRef(object.operationRef, `${path}.operationRef`, parseOperationRef),
    applicationServiceRef: parseRef(
      object.applicationServiceRef,
      `${path}.applicationServiceRef`,
      parseApplicationServiceRef
    ),
    gatewayReceiptRef: parseRef(object.gatewayReceiptRef, `${path}.gatewayReceiptRef`, parseGatewayReceiptRef),
    receiptRef: parseRef(object.receiptRef, `${path}.receiptRef`, parseReceiptRef),
    auditReceiptRef: parseRef(object.auditReceiptRef, `${path}.auditReceiptRef`, parseAuditReceiptRef),
    productEventRef: parseRef(object.productEventRef, `${path}.productEventRef`, parseProductEventRef),
  };
  if (
    (productKind === "run_failure" || productKind === "run_blocker" || productKind === "run_cancellation") &&
    applied.productRef !== applied.productEventRef
  ) {
    throw new ContractParseError(`${path}.productEventRef`, "must identify the terminal product");
  }
  if (productKind === "run_cancellation") {
    return {
      ...applied,
      cancellationRef: parseRef(object.cancellationRef, `${path}.cancellationRef`, parseCancellationRef),
    } as DurableAcceptedProductBinding;
  }
  return applied as DurableAcceptedProductBinding;
}

function parseDurableAcceptedEvent(value: unknown, path: string): DurableAcceptedEvent {
  const object = requireRecord(
    value,
    path,
    [
      "workspaceRef",
      "actorRef",
      "profileVersionRef",
      "runId",
      "snapshotContentDigest",
      "invocationId",
      "eventId",
      "idempotencyKey",
      "correlationId",
      "causationRef",
      "sequence",
      "fingerprint",
      "kind",
    ],
    ["productBinding"]
  );
  if (!DURABLE_EVENT_KINDS.includes(object.kind as (typeof DURABLE_EVENT_KINDS)[number])) {
    throw new ContractParseError(`${path}.kind`, "is not a supported runtime event kind");
  }
  const productBinding = Object.hasOwn(object, "productBinding")
    ? parseDurableProductBinding(object.productBinding, `${path}.productBinding`)
    : undefined;
  return {
    workspaceRef: parseRef(object.workspaceRef, `${path}.workspaceRef`, parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, `${path}.actorRef`, parseActorRef),
    profileVersionRef: parseRef(object.profileVersionRef, `${path}.profileVersionRef`, parseProfileVersionRef),
    runId: parseRef(object.runId, `${path}.runId`, parseRunId),
    snapshotContentDigest: parseDigest(
      object.snapshotContentDigest,
      `${path}.snapshotContentDigest`,
      parseRunSnapshotContentDigest
    ) as RunSnapshotContentDigest,
    invocationId: parseRef(object.invocationId, `${path}.invocationId`, parseInvocationId),
    eventId: parseRef(object.eventId, `${path}.eventId`, parseEventRef),
    idempotencyKey: parseRef(object.idempotencyKey, `${path}.idempotencyKey`, parseIdempotencyKey),
    correlationId: parseRef(object.correlationId, `${path}.correlationId`, parseCorrelationId),
    causationRef: parseRef(object.causationRef, `${path}.causationRef`, parseCausationRef),
    sequence: parseInteger(object.sequence, `${path}.sequence`),
    fingerprint: parseDigest(object.fingerprint, `${path}.fingerprint`, parseContentDigest) as ContentDigest,
    kind: object.kind as RuntimeEventBody["kind"],
    ...(productBinding === undefined ? {} : { productBinding }),
  };
}

function parseDurableAcceptedExit(value: unknown, path: string): DurableAcceptedExit {
  const object = requireRecord(
    value,
    path,
    [
      "workspaceRef",
      "actorRef",
      "profileVersionRef",
      "runId",
      "snapshotContentDigest",
      "invocationId",
      "idempotencyKey",
      "finalSequence",
      "fingerprint",
      "kind",
    ],
    ["inputEventId", "terminalEventId"]
  );
  const kinds = ["completed", "waiting_for_input", "failed", "blocked", "cancelled"] as const;
  if (!kinds.includes(object.kind as (typeof kinds)[number])) {
    throw new ContractParseError(`${path}.kind`, "is not a supported runtime exit kind");
  }
  const terminalEventId = Object.hasOwn(object, "terminalEventId")
    ? parseRef(object.terminalEventId, `${path}.terminalEventId`, parseEventRef)
    : undefined;
  const inputEventId = Object.hasOwn(object, "inputEventId")
    ? parseRef(object.inputEventId, `${path}.inputEventId`, parseEventRef)
    : undefined;
  return {
    workspaceRef: parseRef(object.workspaceRef, `${path}.workspaceRef`, parseWorkspaceRef),
    actorRef: parseRef(object.actorRef, `${path}.actorRef`, parseActorRef),
    profileVersionRef: parseRef(object.profileVersionRef, `${path}.profileVersionRef`, parseProfileVersionRef),
    runId: parseRef(object.runId, `${path}.runId`, parseRunId),
    snapshotContentDigest: parseDigest(
      object.snapshotContentDigest,
      `${path}.snapshotContentDigest`,
      parseRunSnapshotContentDigest
    ) as RunSnapshotContentDigest,
    invocationId: parseRef(object.invocationId, `${path}.invocationId`, parseInvocationId),
    idempotencyKey: parseRef(object.idempotencyKey, `${path}.idempotencyKey`, parseIdempotencyKey),
    finalSequence: parseInteger(object.finalSequence, `${path}.finalSequence`),
    fingerprint: parseDigest(object.fingerprint, `${path}.fingerprint`, parseContentDigest) as ContentDigest,
    kind: object.kind as RuntimeExit["kind"],
    ...(inputEventId === undefined ? {} : { inputEventId }),
    ...(terminalEventId === undefined ? {} : { terminalEventId }),
  };
}

function parseDurableTerminalBinding(value: unknown, path: string): DurableTerminalBinding {
  const object = requireRecord(value, path, [
    "eventId",
    "invocationId",
    "correlationId",
    "causationRef",
    "productBinding",
  ]);
  const productBinding = parseDurableProductBinding(object.productBinding, `${path}.productBinding`);
  if (
    productBinding.action !== "applied" ||
    !DURABLE_TERMINAL_KINDS.includes(productBinding.productKind as (typeof DURABLE_TERMINAL_KINDS)[number])
  ) {
    throw new ContractParseError(`${path}.productBinding`, "must be one applied terminal product binding");
  }
  if (
    productBinding.productKind !== "outcome_submission" &&
    productBinding.productRef !== productBinding.productEventRef
  ) {
    throw new ContractParseError(`${path}.productBinding.productEventRef`, "must identify the terminal product");
  }
  return {
    eventId: parseRef(object.eventId, `${path}.eventId`, parseEventRef),
    invocationId: parseRef(object.invocationId, `${path}.invocationId`, parseInvocationId),
    correlationId: parseRef(object.correlationId, `${path}.correlationId`, parseCorrelationId),
    causationRef: parseRef(object.causationRef, `${path}.causationRef`, parseCausationRef),
    productBinding: productBinding as Extract<DurableAcceptedProductBinding, { action: "applied" }>,
  };
}

function parseDurablePendingInput(value: unknown, path: string): DurablePendingInputBinding {
  const object = requireRecord(value, path, [
    "eventId",
    "invocationId",
    "correlationId",
    "causationRef",
    "inputRequestRef",
    "productEventRef",
    "operationAttemptRef",
    "operationRef",
    "applicationServiceRef",
    "gatewayReceiptRef",
    "receiptRef",
    "auditReceiptRef",
    "questionDigest",
  ]);
  return {
    eventId: parseRef(object.eventId, `${path}.eventId`, parseEventRef),
    invocationId: parseRef(object.invocationId, `${path}.invocationId`, parseInvocationId),
    correlationId: parseRef(object.correlationId, `${path}.correlationId`, parseCorrelationId),
    causationRef: parseRef(object.causationRef, `${path}.causationRef`, parseCausationRef),
    inputRequestRef: parseRef(object.inputRequestRef, `${path}.inputRequestRef`, parseInputRequestRef),
    productEventRef: parseRef(object.productEventRef, `${path}.productEventRef`, parseProductEventRef),
    operationAttemptRef: parseRef(object.operationAttemptRef, `${path}.operationAttemptRef`, parseOperationAttemptRef),
    operationRef: parseRef(object.operationRef, `${path}.operationRef`, parseOperationRef),
    applicationServiceRef: parseRef(
      object.applicationServiceRef,
      `${path}.applicationServiceRef`,
      parseApplicationServiceRef
    ),
    gatewayReceiptRef: parseRef(object.gatewayReceiptRef, `${path}.gatewayReceiptRef`, parseGatewayReceiptRef),
    receiptRef: parseRef(object.receiptRef, `${path}.receiptRef`, parseReceiptRef),
    auditReceiptRef: parseRef(object.auditReceiptRef, `${path}.auditReceiptRef`, parseAuditReceiptRef),
    questionDigest: parseDigest(object.questionDigest, `${path}.questionDigest`, parseContentDigest) as ContentDigest,
  };
}

function parseTrustedHumanAnswerResponderPrincipal(value: unknown, path: string): TrustedHumanAnswerResponderPrincipal {
  const object = requireRecord(value, path, ["kind", "planePrincipalId"]);
  const kinds = ["human_user", "external_integration"] as const;
  if (!kinds.includes(object.kind as (typeof kinds)[number])) {
    throw new ContractParseError(`${path}.kind`, "must identify a human user or external integration");
  }
  return {
    kind: object.kind as TrustedHumanAnswerResponderPrincipal["kind"],
    planePrincipalId: parseRef(object.planePrincipalId, `${path}.planePrincipalId`, parseActorRef),
  };
}

function parseDurableHumanInputAnswer(value: unknown, path: string): DurableAcceptedHumanInputAnswer {
  const object = requireRecord(value, path, [
    "answerEventRef",
    "inputRequestRef",
    "responderPrincipal",
    "workspaceRef",
    "runId",
    "authorizationReceiptRef",
    "applicationServiceRef",
    "gatewayReceiptRef",
    "receiptRef",
    "auditReceiptRef",
    "correlationId",
    "causationRef",
    "payloadDigest",
    "answerFactDigest",
  ]);
  return {
    answerEventRef: parseRef(object.answerEventRef, `${path}.answerEventRef`, parseEventRef),
    inputRequestRef: parseRef(object.inputRequestRef, `${path}.inputRequestRef`, parseInputRequestRef),
    responderPrincipal: parseTrustedHumanAnswerResponderPrincipal(
      object.responderPrincipal,
      `${path}.responderPrincipal`
    ),
    workspaceRef: parseRef(object.workspaceRef, `${path}.workspaceRef`, parseWorkspaceRef),
    runId: parseRef(object.runId, `${path}.runId`, parseRunId),
    authorizationReceiptRef: parseRef(
      object.authorizationReceiptRef,
      `${path}.authorizationReceiptRef`,
      parseAuthorizationReceiptRef
    ),
    applicationServiceRef: parseRef(
      object.applicationServiceRef,
      `${path}.applicationServiceRef`,
      parseApplicationServiceRef
    ),
    gatewayReceiptRef: parseRef(object.gatewayReceiptRef, `${path}.gatewayReceiptRef`, parseGatewayReceiptRef),
    receiptRef: parseRef(object.receiptRef, `${path}.receiptRef`, parseReceiptRef),
    auditReceiptRef: parseRef(object.auditReceiptRef, `${path}.auditReceiptRef`, parseAuditReceiptRef),
    correlationId: parseRef(object.correlationId, `${path}.correlationId`, parseCorrelationId),
    causationRef: parseRef(object.causationRef, `${path}.causationRef`, parseCausationRef),
    payloadDigest: parseDigest(object.payloadDigest, `${path}.payloadDigest`, parseContentDigest) as ContentDigest,
    answerFactDigest: parseDigest(
      object.answerFactDigest,
      `${path}.answerFactDigest`,
      parseContentDigest
    ) as ContentDigest,
  };
}

function requireDurableConsistency(condition: boolean, path: string, message: string): asserts condition {
  if (!condition) {
    throw new ContractParseError(path, message);
  }
}

function sameJson(left: unknown, right: unknown): boolean {
  return canonicalJsonEquals(left, right);
}

export function computeTrustedHumanInputAnswerDigest(
  answer: TrustedHumanInputAnswerFact | TrustedHumanInputAnswer
): ContentDigest {
  const fact =
    "answerFactDigest" in answer ? (({ answerFactDigest: _answerFactDigest, ...content }) => content)(answer) : answer;
  return createContentDigest(sha256(canonicalizeJson(fact)));
}

type RuntimeDurableStateContent = Omit<RuntimeDurableStateShape, "stateDigest">;

function withoutRuntimeDurableStateDigest(
  state: RuntimeDurableState | RuntimeDurableStateContent
): RuntimeDurableStateContent {
  if ("stateDigest" in state) {
    const { stateDigest: _stateDigest, ...content } = state;
    return content;
  }
  return state;
}

export function computeRuntimeDurableStateDigest(
  state: RuntimeDurableState | RuntimeDurableStateContent
): ContentDigest {
  return createContentDigest(sha256(canonicalizeJson(withoutRuntimeDurableStateDigest(state))));
}

export function createInitialRuntimeDurableState(binding: RuntimeDurableStateBinding): RuntimeDurableState {
  const content: RuntimeDurableStateContent = {
    protocol: PLANE_AGENT_RUNTIME_PROTOCOL,
    stateVersion: RUNTIME_DURABLE_STATE_VERSION,
    binding,
    state: "queued",
    revision: 0,
    lastAcceptedSequence: 0,
    acceptedEvents: [],
    acceptedHumanInputAnswers: [],
    acceptedExits: [],
  };
  return parseRuntimeDurableState({ ...content, stateDigest: computeRuntimeDurableStateDigest(content) });
}

type AppliedProductIdentitySource = Readonly<{
  productKind: DurableAcceptedProductBinding["productKind"];
  productRef: DurableAcceptedProductBinding["productRef"];
  operationAttemptRef: OperationAttemptRef;
  operationRef: OperationRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  productEventRef: ProductEventRef;
  cancellationRef?: CancellationRef;
}>;

function productUniquenessKeys(binding: AppliedProductIdentitySource): readonly string[] {
  return [
    `operationAttemptRef:${binding.operationAttemptRef}`,
    `gatewayReceiptRef:${binding.gatewayReceiptRef}`,
    `receiptRef:${binding.receiptRef}`,
    `auditReceiptRef:${binding.auditReceiptRef}`,
    `productEventRef:${binding.productEventRef}`,
    `product:${binding.productKind}:${binding.productRef}`,
    `operation-gateway:${binding.operationRef}:${binding.gatewayReceiptRef}`,
    `binding:${canonicalizeJson({
      operationAttemptRef: binding.operationAttemptRef,
      operationRef: binding.operationRef,
      applicationServiceRef: binding.applicationServiceRef,
      gatewayReceiptRef: binding.gatewayReceiptRef,
      receiptRef: binding.receiptRef,
      auditReceiptRef: binding.auditReceiptRef,
      productEventRef: binding.productEventRef,
      ...(binding.cancellationRef === undefined ? {} : { cancellationRef: binding.cancellationRef }),
    })}`,
  ];
}

function isAppliedProductBinding(
  binding: DurableAcceptedProductBinding | undefined
): binding is Extract<DurableAcceptedProductBinding, { action: "applied" }> {
  return binding?.action === "applied";
}

function validateRuntimeDurableStateConsistency(state: RuntimeDurableStateShape, path: string): void {
  requireDurableConsistency(
    Number.isSafeInteger(state.revision) && state.revision >= 0,
    `${path}.revision`,
    "must be a non-negative safe integer"
  );
  if (state.revision === 0) {
    requireDurableConsistency(
      state.state === "queued" &&
        state.previousRevision === undefined &&
        state.previousStateDigest === undefined &&
        state.lastAcceptedSequence === 0 &&
        state.acceptedEvents.length === 0 &&
        state.acceptedHumanInputAnswers.length === 0 &&
        state.acceptedExits.length === 0 &&
        state.terminal === undefined &&
        state.pendingInput === undefined,
      `${path}`,
      "revision zero is reserved for the canonical empty queued genesis state"
    );
  } else {
    requireDurableConsistency(
      state.previousRevision === state.revision - 1 && state.previousStateDigest !== undefined,
      `${path}.previousRevision`,
      "must link to the immediately preceding durable revision"
    );
  }
  const eventIds = new Set<string>();
  const eventKeys = new Set<string>();
  const productKeys = new Set<string>();
  let previousSequence = state.acceptedEvents.length === 0 ? 0 : -1;
  for (const [index, event] of state.acceptedEvents.entries()) {
    requireDurableConsistency(
      !eventIds.has(event.eventId),
      `${path}.acceptedEvents[${index}].eventId`,
      "must be unique"
    );
    requireDurableConsistency(
      !eventKeys.has(event.idempotencyKey),
      `${path}.acceptedEvents[${index}].idempotencyKey`,
      "must be unique"
    );
    requireDurableConsistency(
      event.sequence === previousSequence + 1,
      `${path}.acceptedEvents[${index}].sequence`,
      "must be strictly monotonic"
    );
    requireDurableConsistency(
      event.workspaceRef === state.binding.workspaceRef &&
        event.actorRef === state.binding.actorRef &&
        event.profileVersionRef === state.binding.profileVersionRef &&
        event.runId === state.binding.runId &&
        event.snapshotContentDigest === state.binding.snapshotContentDigest,
      `${path}.acceptedEvents[${index}]`,
      "must bind to the durable run, actor, profile, and snapshot"
    );
    eventIds.add(event.eventId);
    eventKeys.add(event.idempotencyKey);
    previousSequence = event.sequence;
    const productRequired = [
      "conversation_publication_observed",
      "input_request_observed",
      "artifact_observed",
      "outcome_submission_observed",
      "failure_observed",
      "blocker_observed",
      "cancellation_observed",
    ].includes(event.kind);
    requireDurableConsistency(
      productRequired === (event.productBinding !== undefined),
      `${path}.acceptedEvents[${index}].productBinding`,
      productRequired ? "is required for product events" : "is forbidden for observation-only events"
    );
    if (event.productBinding !== undefined) {
      const expectedProductKind =
        event.kind === "conversation_publication_observed"
          ? "conversation"
          : event.kind === "input_request_observed"
            ? "input_request"
            : event.kind === "artifact_observed"
              ? "artifact"
              : event.kind === "outcome_submission_observed"
                ? "outcome_submission"
                : event.kind === "failure_observed"
                  ? "run_failure"
                  : event.kind === "blocker_observed"
                    ? "run_blocker"
                    : "run_cancellation";
      requireDurableConsistency(
        event.productBinding.productKind === expectedProductKind,
        `${path}.acceptedEvents[${index}].productBinding.productKind`,
        "must match the accepted event kind"
      );
      if (isAppliedProductBinding(event.productBinding)) {
        for (const key of productUniquenessKeys(event.productBinding)) {
          requireDurableConsistency(
            !productKeys.has(key),
            `${path}.acceptedEvents[${index}].productBinding`,
            "must not reuse an applied product identity or receipt across durable history"
          );
          productKeys.add(key);
        }
      }
    }
  }
  requireDurableConsistency(
    state.lastAcceptedSequence === previousSequence,
    `${path}.lastAcceptedSequence`,
    "must equal the last accepted event sequence"
  );

  const answerEventIds = new Set<string>();
  const answerReceiptKeys = new Set<string>();
  for (const [index, answer] of state.acceptedHumanInputAnswers.entries()) {
    requireDurableConsistency(
      answer.workspaceRef === state.binding.workspaceRef && answer.runId === state.binding.runId,
      `${path}.acceptedHumanInputAnswers[${index}]`,
      "must bind to the durable workspace and run"
    );
    requireDurableConsistency(
      answer.responderPrincipal.planePrincipalId !== state.binding.actorRef,
      `${path}.acceptedHumanInputAnswers[${index}].responderPrincipal.planePrincipalId`,
      "must remain separate from the Agent actor"
    );
    requireDurableConsistency(
      computeTrustedHumanInputAnswerDigest(answer) === answer.answerFactDigest,
      `${path}.acceptedHumanInputAnswers[${index}].answerFactDigest`,
      "must match the canonical complete answer fact"
    );
    requireDurableConsistency(
      !answerEventIds.has(answer.answerEventRef),
      `${path}.acceptedHumanInputAnswers[${index}].answerEventRef`,
      "must be unique"
    );
    requireDurableConsistency(
      !eventIds.has(answer.answerEventRef),
      `${path}.acceptedHumanInputAnswers[${index}].answerEventRef`,
      "must not be manufactured as a runtime event"
    );
    for (const key of [
      `authorizationReceiptRef:${answer.authorizationReceiptRef}`,
      `applicationServiceRef:${answer.applicationServiceRef}`,
      `gatewayReceiptRef:${answer.gatewayReceiptRef}`,
      `receiptRef:${answer.receiptRef}`,
      `auditReceiptRef:${answer.auditReceiptRef}`,
    ]) {
      requireDurableConsistency(
        !answerReceiptKeys.has(key),
        `${path}.acceptedHumanInputAnswers[${index}]`,
        "must not reuse an answer authorization or application proof"
      );
      answerReceiptKeys.add(key);
    }
    answerEventIds.add(answer.answerEventRef);
  }

  const exitInvocations = new Set<string>();
  const exitKeys = new Set<string>();
  const terminalExits = state.acceptedExits.filter((exit) => exit.kind !== "waiting_for_input");
  for (const [index, exit] of state.acceptedExits.entries()) {
    requireDurableConsistency(
      !exitInvocations.has(exit.invocationId),
      `${path}.acceptedExits[${index}].invocationId`,
      "must be unique"
    );
    requireDurableConsistency(
      !exitKeys.has(exit.idempotencyKey),
      `${path}.acceptedExits[${index}].idempotencyKey`,
      "must be unique"
    );
    requireDurableConsistency(
      exit.workspaceRef === state.binding.workspaceRef &&
        exit.actorRef === state.binding.actorRef &&
        exit.profileVersionRef === state.binding.profileVersionRef &&
        exit.runId === state.binding.runId &&
        exit.snapshotContentDigest === state.binding.snapshotContentDigest,
      `${path}.acceptedExits[${index}]`,
      "must bind to the durable run, actor, profile, and snapshot"
    );
    requireDurableConsistency(
      exit.finalSequence <= state.lastAcceptedSequence,
      `${path}.acceptedExits[${index}].finalSequence`,
      "cannot exceed the accepted sequence"
    );
    if (exit.kind === "waiting_for_input") {
      requireDurableConsistency(
        exit.inputEventId !== undefined,
        `${path}.acceptedExits[${index}].inputEventId`,
        "is required for a waiting exit"
      );
      const inputEvent = state.acceptedEvents.find((event) => event.eventId === exit.inputEventId);
      requireDurableConsistency(
        inputEvent !== undefined &&
          inputEvent.kind === "input_request_observed" &&
          inputEvent.sequence === exit.finalSequence &&
          inputEvent.productBinding?.action === "applied" &&
          inputEvent.productBinding.productKind === "input_request",
        `${path}.acceptedExits[${index}].inputEventId`,
        "must identify the exact accepted input-request product at the exit final sequence"
      );
    } else {
      requireDurableConsistency(
        exit.inputEventId === undefined,
        `${path}.acceptedExits[${index}].inputEventId`,
        "is only valid for a waiting exit"
      );
    }
    exitInvocations.add(exit.invocationId);
    exitKeys.add(exit.idempotencyKey);
  }
  requireDurableConsistency(
    terminalExits.length <= 1,
    `${path}.acceptedExits`,
    "must contain at most one terminal exit"
  );

  if (state.state === "queued" || state.state === "running") {
    requireDurableConsistency(state.terminal === undefined, `${path}.terminal`, "is forbidden before a terminal exit");
    requireDurableConsistency(
      state.pendingInput === undefined,
      `${path}.pendingInput`,
      "is forbidden outside waiting_for_input"
    );
    requireDurableConsistency(state.acceptedExits.length === 0, `${path}.acceptedExits`, "is forbidden before an exit");
    if (state.state === "queued") {
      requireDurableConsistency(state.revision === 0, `${path}.revision`, "must remain 0 while queued");
      requireDurableConsistency(
        state.acceptedEvents.length === 0,
        `${path}.acceptedEvents`,
        "is forbidden while queued"
      );
      requireDurableConsistency(
        state.lastAcceptedSequence === 0,
        `${path}.lastAcceptedSequence`,
        "must remain 0 while queued"
      );
      requireDurableConsistency(
        state.acceptedHumanInputAnswers.length === 0,
        `${path}.acceptedHumanInputAnswers`,
        "is forbidden on the explicit initial state"
      );
    }
    return;
  }

  if (state.state === "waiting_for_input") {
    requireDurableConsistency(state.terminal === undefined, `${path}.terminal`, "is forbidden while waiting for input");
    const pending = state.pendingInput;
    requireDurableConsistency(pending !== undefined, `${path}.pendingInput`, "is required while waiting for input");
    if (pending !== undefined) {
      const pendingEvent = state.acceptedEvents.find((event) => event.eventId === pending.eventId);
      requireDurableConsistency(
        pendingEvent !== undefined,
        `${path}.pendingInput.eventId`,
        "must identify an accepted event"
      );
      requireDurableConsistency(
        pendingEvent?.kind === "input_request_observed",
        `${path}.pendingInput.eventId`,
        "must identify the accepted pending request"
      );
      const binding = pendingEvent?.productBinding;
      requireDurableConsistency(
        binding?.action === "applied" && binding.productKind === "input_request",
        `${path}.pendingInput`,
        "must bind to an applied input request"
      );
      if (binding?.action === "applied" && binding.productKind === "input_request") {
        requireDurableConsistency(
          binding.productRef === pending.inputRequestRef,
          `${path}.pendingInput.inputRequestRef`,
          "must match the accepted request"
        );
        requireDurableConsistency(
          binding.productEventRef === pending.productEventRef,
          `${path}.pendingInput.productEventRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.operationAttemptRef === pending.operationAttemptRef,
          `${path}.pendingInput.operationAttemptRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.operationRef === pending.operationRef,
          `${path}.pendingInput.operationRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.applicationServiceRef === pending.applicationServiceRef,
          `${path}.pendingInput.applicationServiceRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.gatewayReceiptRef === pending.gatewayReceiptRef,
          `${path}.pendingInput.gatewayReceiptRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.receiptRef === pending.receiptRef,
          `${path}.pendingInput.receiptRef`,
          "must match the accepted request receipt"
        );
        requireDurableConsistency(
          binding.auditReceiptRef === pending.auditReceiptRef,
          `${path}.pendingInput.auditReceiptRef`,
          "must match the accepted request receipt"
        );
      }
      requireDurableConsistency(
        pendingEvent?.invocationId === pending.invocationId,
        `${path}.pendingInput.invocationId`,
        "must match the request event"
      );
      requireDurableConsistency(
        pendingEvent?.correlationId === pending.correlationId,
        `${path}.pendingInput.correlationId`,
        "must match the request event"
      );
      requireDurableConsistency(
        pendingEvent?.causationRef === pending.causationRef,
        `${path}.pendingInput.causationRef`,
        "must match the request event"
      );
    }
    requireDurableConsistency(
      terminalExits.length === 0,
      `${path}.acceptedExits`,
      "must not contain a terminal exit while waiting"
    );
    requireDurableConsistency(state.acceptedExits.length > 0, `${path}.acceptedExits`, "must contain a waiting exit");
    requireDurableConsistency(
      state.acceptedExits.every((exit) => exit.kind === "waiting_for_input"),
      `${path}.acceptedExits`,
      "must contain only waiting exits"
    );
    const lastExit = state.acceptedExits.at(-1);
    requireDurableConsistency(
      lastExit?.kind === "waiting_for_input" &&
        lastExit.finalSequence === state.lastAcceptedSequence &&
        lastExit.inputEventId === pending?.eventId,
      `${path}.acceptedExits`,
      "must end with the waiting exit for the exact current pending input request"
    );
    return;
  }

  const terminal = state.terminal;
  requireDurableConsistency(terminal !== undefined, `${path}.terminal`, "is required after a terminal exit");
  requireDurableConsistency(
    state.pendingInput === undefined,
    `${path}.pendingInput`,
    "is forbidden after a terminal exit"
  );
  const terminalExit = terminalExits[0];
  requireDurableConsistency(terminalExit !== undefined, `${path}.acceptedExits`, "must contain one terminal exit");
  if (terminal !== undefined && terminalExit !== undefined) {
    requireDurableConsistency(
      terminal.eventId === terminalExit.terminalEventId,
      `${path}.terminal.eventId`,
      "must match the accepted terminal exit"
    );
    requireDurableConsistency(
      terminal.invocationId === terminalExit.invocationId,
      `${path}.terminal.invocationId`,
      "must match the accepted terminal exit"
    );
    const expectedProductKind =
      state.state === "succeeded"
        ? "outcome_submission"
        : state.state === "failed"
          ? "run_failure"
          : state.state === "blocked"
            ? "run_blocker"
            : "run_cancellation";
    const expectedExitKind =
      state.state === "succeeded"
        ? "completed"
        : state.state === "failed"
          ? "failed"
          : state.state === "blocked"
            ? "blocked"
            : "cancelled";
    const expectedTerminalEventKind =
      state.state === "succeeded"
        ? "outcome_submission_observed"
        : state.state === "failed"
          ? "failure_observed"
          : state.state === "blocked"
            ? "blocker_observed"
            : "cancellation_observed";
    requireDurableConsistency(
      terminalExit.kind === expectedExitKind,
      `${path}.acceptedExits`,
      "must match the lifecycle state"
    );
    requireDurableConsistency(
      terminalExit.finalSequence === state.lastAcceptedSequence,
      `${path}.acceptedExits`,
      "must end at the accepted sequence"
    );
    requireDurableConsistency(
      terminal.productBinding.productKind === expectedProductKind,
      `${path}.terminal.productBinding.productKind`,
      "must match the lifecycle state"
    );
    const terminalEvent = state.acceptedEvents.find((event) => event.eventId === terminal.eventId);
    requireDurableConsistency(
      terminalEvent !== undefined,
      `${path}.terminal.eventId`,
      "must identify an accepted terminal event"
    );
    if (terminalEvent !== undefined) {
      requireDurableConsistency(
        terminalEvent.sequence === state.lastAcceptedSequence,
        `${path}.terminal.eventId`,
        "must identify the final accepted event"
      );
      requireDurableConsistency(
        terminalEvent.kind === expectedTerminalEventKind,
        `${path}.terminal.eventId`,
        "must identify the lifecycle terminal event kind"
      );
      requireDurableConsistency(
        terminalEvent.invocationId === terminal.invocationId,
        `${path}.terminal.invocationId`,
        "must match the terminal event"
      );
      requireDurableConsistency(
        terminalEvent.correlationId === terminal.correlationId,
        `${path}.terminal.correlationId`,
        "must match the terminal event"
      );
      requireDurableConsistency(
        terminalEvent.causationRef === terminal.causationRef,
        `${path}.terminal.causationRef`,
        "must match the terminal event"
      );
      requireDurableConsistency(
        terminalEvent.productBinding !== undefined && sameJson(terminalEvent.productBinding, terminal.productBinding),
        `${path}.terminal`,
        "must match the accepted terminal event"
      );
    }
  }
}

export function parseRuntimeDurableState(value: unknown): RuntimeDurableState {
  const raw = parseRawJson(value, "RuntimeDurableState");
  const object = requireRecord(
    raw,
    "RuntimeDurableState",
    [
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
    ["previousRevision", "previousStateDigest", "terminal", "pendingInput"]
  );
  const states = ["queued", "running", "waiting_for_input", "succeeded", "failed", "blocked", "cancelled"] as const;
  if (!states.includes(object.state as (typeof states)[number])) {
    throw new ContractParseError("RuntimeDurableState.state", "is not a supported lifecycle state");
  }
  const acceptedEventsRaw = object.acceptedEvents;
  if (!Array.isArray(acceptedEventsRaw) || acceptedEventsRaw.length > 4096) {
    throw new ContractParseError("RuntimeDurableState.acceptedEvents", "must contain at most 4096 events");
  }
  const acceptedExitsRaw = object.acceptedExits;
  if (!Array.isArray(acceptedExitsRaw) || acceptedExitsRaw.length > 256) {
    throw new ContractParseError("RuntimeDurableState.acceptedExits", "must contain at most 256 exits");
  }
  if (
    typeof object.lastAcceptedSequence !== "number" ||
    !Number.isInteger(object.lastAcceptedSequence) ||
    object.lastAcceptedSequence < 0
  ) {
    throw new ContractParseError("RuntimeDurableState.lastAcceptedSequence", "must be a non-negative integer");
  }
  const revision = parseInteger(object.revision, "RuntimeDurableState.revision");
  if (Object.hasOwn(object, "previousRevision") !== Object.hasOwn(object, "previousStateDigest")) {
    throw new ContractParseError(
      "RuntimeDurableState.previousRevision",
      "previousRevision and previousStateDigest must be supplied together"
    );
  }
  const acceptedHumanInputAnswersRaw = object.acceptedHumanInputAnswers;
  if (!Array.isArray(acceptedHumanInputAnswersRaw) || acceptedHumanInputAnswersRaw.length > 256) {
    throw new ContractParseError(
      "RuntimeDurableState.acceptedHumanInputAnswers",
      "must contain at most 256 accepted answer facts"
    );
  }
  const parsed: RuntimeDurableStateShape = {
    protocol: parseLiteral(object.protocol, PLANE_AGENT_RUNTIME_PROTOCOL, "RuntimeDurableState.protocol"),
    stateVersion: parseLiteral(object.stateVersion, RUNTIME_DURABLE_STATE_VERSION, "RuntimeDurableState.stateVersion"),
    binding: parseRuntimeDurableStateBinding(object.binding, "RuntimeDurableState.binding"),
    state: object.state as RuntimeLifecycleState,
    revision,
    stateDigest: parseDigest(
      object.stateDigest,
      "RuntimeDurableState.stateDigest",
      parseContentDigest
    ) as ContentDigest,
    ...(Object.hasOwn(object, "previousRevision")
      ? {
          previousRevision: parseInteger(object.previousRevision, "RuntimeDurableState.previousRevision"),
          previousStateDigest: parseDigest(
            object.previousStateDigest,
            "RuntimeDurableState.previousStateDigest",
            parseContentDigest
          ) as ContentDigest,
        }
      : {}),
    lastAcceptedSequence: object.lastAcceptedSequence,
    acceptedEvents: acceptedEventsRaw.map((item, index) =>
      parseDurableAcceptedEvent(item, `RuntimeDurableState.acceptedEvents[${index}]`)
    ),
    acceptedHumanInputAnswers: acceptedHumanInputAnswersRaw.map((item, index) =>
      parseDurableHumanInputAnswer(item, `RuntimeDurableState.acceptedHumanInputAnswers[${index}]`)
    ),
    acceptedExits: acceptedExitsRaw.map((item, index) =>
      parseDurableAcceptedExit(item, `RuntimeDurableState.acceptedExits[${index}]`)
    ),
    ...(Object.hasOwn(object, "terminal")
      ? { terminal: parseDurableTerminalBinding(object.terminal, "RuntimeDurableState.terminal") }
      : {}),
    ...(Object.hasOwn(object, "pendingInput")
      ? { pendingInput: parseDurablePendingInput(object.pendingInput, "RuntimeDurableState.pendingInput") }
      : {}),
  };
  if (computeRuntimeDurableStateDigest(parsed) !== parsed.stateDigest) {
    throw new ContractParseError(
      "RuntimeDurableState.stateDigest",
      "does not match the canonical durable state content"
    );
  }
  validateRuntimeDurableStateConsistency(parsed, "RuntimeDurableState");
  return deepFreeze(markValidatedContract(parsed, "RuntimeDurableState"));
}

const budgetFields = ["inputTokens", "outputTokens", "durationMs"] as const;

function sameBudgetOrLower(candidate: RuntimeBudget, baseline: RuntimeBudget): boolean {
  return budgetFields.every((field) => candidate[field] <= baseline[field]);
}

function publicationIsApplied(
  publication: AnyProductPublication | Readonly<{ action: "observation_only" }>
): publication is Extract<AnyProductPublication, { action: "applied" }> {
  return publication.action === "applied";
}

function addVerificationError(
  errors: RuntimeVerificationError[],
  code: RuntimeVerificationErrorCode,
  path: string,
  message: string
) {
  errors.push({ code, path, message });
}

function fingerprint(value: unknown): ContentDigest {
  return createContentDigest(sha256(canonicalizeJson(value)));
}

function authorityMatches(
  snapshot: RunSnapshot,
  invocation: InvocationEnvelope,
  authority: TrustedRuntimeAuthority
): boolean {
  return (
    authority.workspaceRef === snapshot.workspaceRef &&
    authority.workspaceRef === invocation.workspaceRef &&
    authority.actorRef === snapshot.actorRef &&
    authority.actorRef === invocation.actorRef &&
    authority.profileVersionRef === snapshot.profile.profileRef &&
    authority.runId === snapshot.runId &&
    authority.runId === invocation.runId &&
    authority.invocationId === invocation.invocationId &&
    authority.snapshotContentDigest === snapshot.contentDigest &&
    authority.cancellationRef === invocation.cancellationRef &&
    authority.correlationId === invocation.correlationId &&
    authority.causationRef === invocation.causationRef &&
    authority.invocationIdempotencyKey === invocation.idempotencyKey
  );
}

function receiptMatches(
  publication: Extract<AnyProductPublication, { action: "applied" }>,
  receipt: TrustedPublicationReceipt,
  snapshot: RunSnapshot,
  invocation: InvocationEnvelope
): boolean {
  const cancellationRef = "cancellationRef" in publication ? publication.cancellationRef : undefined;
  const receiptCancellationRef = "cancellationRef" in receipt ? receipt.cancellationRef : undefined;
  return (
    receipt.workspaceRef === snapshot.workspaceRef &&
    receipt.actorRef === snapshot.actorRef &&
    receipt.profileVersionRef === snapshot.profile.profileRef &&
    receipt.runId === snapshot.runId &&
    receipt.invocationId === invocation.invocationId &&
    receipt.productKind === publication.productKind &&
    receipt.productRef === publication.productRef &&
    receipt.operationAttemptRef === publication.operationAttemptRef &&
    receipt.operationRef === publication.operationRef &&
    receipt.applicationServiceRef === publication.applicationServiceRef &&
    receipt.gatewayReceiptRef === publication.gatewayReceiptRef &&
    receipt.receiptRef === publication.receiptRef &&
    receipt.auditReceiptRef === publication.auditReceiptRef &&
    receipt.productEventRef === publication.productEventRef &&
    receiptCancellationRef === cancellationRef
  );
}

function prevalidatePublicationReceipts(
  receipts: readonly TrustedPublicationReceipt[],
  errors: RuntimeVerificationError[],
  historicalProductKeys: ReadonlySet<string>,
  replayableProductKeys: ReadonlySet<string>
): void {
  const seen = new Map<string, number>();
  for (const [index, receipt] of receipts.entries()) {
    for (const key of productUniquenessKeys(receipt)) {
      if (seen.has(key)) {
        addVerificationError(
          errors,
          "publication_receipt_duplicate",
          `trusted.publicationReceipts[${index}]`,
          "Every current trusted receipt identity and binding tuple must be unique"
        );
      } else if (historicalProductKeys.has(key) && !replayableProductKeys.has(key)) {
        addVerificationError(
          errors,
          "publication_receipt_duplicate",
          `trusted.publicationReceipts[${index}]`,
          "A current trusted receipt cannot reuse an applied product identity or receipt from durable history"
        );
      } else {
        seen.set(key, index);
      }
    }
  }
}

function verifyPublication(
  body: RuntimeEventBody,
  eventPath: string,
  snapshot: RunSnapshot,
  invocation: InvocationEnvelope,
  trustedReceipts: readonly TrustedPublicationReceipt[],
  usedReceiptIndexes: Set<number>,
  errors: RuntimeVerificationError[]
) {
  const publicationBody =
    body.kind === "conversation_publication_observed" ||
    body.kind === "input_request_observed" ||
    body.kind === "artifact_observed" ||
    body.kind === "outcome_submission_observed" ||
    body.kind === "failure_observed" ||
    body.kind === "blocker_observed" ||
    body.kind === "cancellation_observed";
  if (!publicationBody) {
    return;
  }

  const publication = body.publication;
  if (body.kind === "artifact_observed" && publication.productRef !== body.artifact.artifactRef) {
    addVerificationError(
      errors,
      "publication_product_mismatch",
      `${eventPath}.publication.productRef`,
      "Artifact publication must reference the observed artifact"
    );
  }
  if (body.kind === "cancellation_observed") {
    if (
      body.cancellationRef !== invocation.cancellationRef ||
      !("cancellationRef" in publication) ||
      publication.cancellationRef !== invocation.cancellationRef
    ) {
      addVerificationError(
        errors,
        "cancellation_mismatch",
        `${eventPath}.cancellationRef`,
        "Cancellation authority and publication receipt must bind to the exact invocation cancellation reference"
      );
    }
  }
  if (!publicationIsApplied(publication)) {
    if (body.kind === "failure_observed" || body.kind === "blocker_observed" || body.kind === "cancellation_observed") {
      addVerificationError(
        errors,
        "publication_receipt_missing",
        `${eventPath}.publication`,
        "Terminal lifecycle application observations require an applied Plane receipt"
      );
    }
    return;
  }

  if (!isCanonicalJsonUtf8ByteLengthAtMost(publication, snapshot.runtimePolicy.maxReceiptBytes)) {
    addVerificationError(
      errors,
      "receipt_too_large",
      `${eventPath}.publication`,
      "Publication application receipt metadata exceeds the resolved snapshot receipt limit"
    );
  }
  const matchingReceiptIndexes = trustedReceipts
    .map((receipt, index) => (receiptMatches(publication, receipt, snapshot, invocation) ? index : undefined))
    .filter((index): index is number => index !== undefined);
  const receiptAlreadyConsumed =
    matchingReceiptIndexes.length === 1 && usedReceiptIndexes.has(matchingReceiptIndexes[0]);
  if (matchingReceiptIndexes.length !== 1 || receiptAlreadyConsumed) {
    const sameProduct = trustedReceipts.some(
      (receipt) => receipt.productKind === publication.productKind && receipt.productRef === publication.productRef
    );
    addVerificationError(
      errors,
      matchingReceiptIndexes.length > 1 || receiptAlreadyConsumed
        ? "publication_receipt_mismatch"
        : sameProduct
          ? "publication_authority_mismatch"
          : "publication_receipt_missing",
      `${eventPath}.publication`,
      receiptAlreadyConsumed
        ? "A trusted application receipt can be consumed by only one applied runtime event"
        : sameProduct
          ? "The product receipt is not bound to the trusted workspace, actor, profile, run, invocation, or gateway facts"
          : "Applied product publication requires a matching trusted Plane application-service, gateway, and audit receipt"
    );
  } else {
    usedReceiptIndexes.add(matchingReceiptIndexes[0]);
  }
}

function isTerminalBody(body: RuntimeEventBody): boolean {
  return (
    body.kind === "outcome_submission_observed" ||
    body.kind === "failure_observed" ||
    body.kind === "blocker_observed" ||
    body.kind === "cancellation_observed"
  );
}

function stateForExit(kind: RuntimeExit["kind"]): RuntimeLifecycleState {
  switch (kind) {
    case "completed":
      return "succeeded";
    case "waiting_for_input":
      return "waiting_for_input";
    case "failed":
      return "failed";
    case "blocked":
      return "blocked";
    case "cancelled":
      return "cancelled";
  }
}

function verifyTerminalEvents(
  events: readonly RuntimeEvent[],
  exit: RuntimeExit,
  invocation: InvocationEnvelope,
  errors: RuntimeVerificationError[]
): number {
  const terminalEvents = events.filter((event) => isTerminalBody(event.body));
  const inputRequests = events.filter((event) => event.body.kind === "input_request_observed");
  if (
    terminalEvents.some((event, index) => index !== terminalEvents.length - 1 || event !== events[events.length - 1])
  ) {
    addVerificationError(
      errors,
      "events_after_terminal",
      "events",
      "A terminal lifecycle event must be the final event; later progress, usage, transcript, or publication is rejected"
    );
  }

  switch (exit.kind) {
    case "completed": {
      const outcomes = events.filter((event) => event.body.kind === "outcome_submission_observed");
      if (
        terminalEvents.length !== 1 ||
        outcomes.length !== 1 ||
        outcomes[0] === undefined ||
        !publicationIsApplied(outcomes[0].body.publication) ||
        outcomes[0] !== events[events.length - 1]
      ) {
        addVerificationError(
          errors,
          "terminal_event_mismatch",
          "exit.kind",
          "A completed invocation requires exactly one receipt-correlated outcome-submission application as its final event"
        );
      }
      break;
    }
    case "waiting_for_input":
      if (
        terminalEvents.length !== 0 ||
        inputRequests.length !== 1 ||
        inputRequests[0] === undefined ||
        inputRequests[0].eventId !== exit.inputEventRef ||
        inputRequests[0] !== events[events.length - 1] ||
        !publicationIsApplied(inputRequests[0].body.publication) ||
        inputRequests[0].body.publication.productKind !== "input_request"
      ) {
        addVerificationError(
          errors,
          "terminal_event_mismatch",
          "exit.kind",
          "A waiting invocation requires one receipt-correlated input-request application as its final event"
        );
      }
      break;
    case "failed": {
      const failures = events.filter((event) => event.body.kind === "failure_observed");
      if (
        terminalEvents.length !== 1 ||
        failures.length !== 1 ||
        failures[0] === undefined ||
        failures[0] !== events[events.length - 1] ||
        failures[0].body.kind !== "failure_observed" ||
        failures[0].body.failure.code !== exit.failure.code ||
        failures[0].body.failure.message !== exit.failure.message ||
        failures[0].body.failure.retryable !== exit.failure.retryable ||
        !publicationIsApplied(failures[0].body.publication) ||
        failures[0].body.publication.productKind !== "run_failure"
      ) {
        addVerificationError(
          errors,
          "exit_failure_mismatch",
          "exit.failure",
          "A failed exit must have one matching receipt-correlated run-failure application as its final event"
        );
      }
      break;
    }
    case "blocked": {
      const blockers = events.filter((event) => event.body.kind === "blocker_observed");
      if (
        terminalEvents.length !== 1 ||
        blockers.length !== 1 ||
        blockers[0] === undefined ||
        blockers[0] !== events[events.length - 1] ||
        !publicationIsApplied(blockers[0].body.publication) ||
        blockers[0].body.publication.productKind !== "run_blocker"
      ) {
        addVerificationError(
          errors,
          "terminal_event_mismatch",
          "exit.kind",
          "A blocked exit requires one receipt-correlated run-blocker application as its final event"
        );
      }
      break;
    }
    case "cancelled": {
      const cancellations = events.filter((event) => event.body.kind === "cancellation_observed");
      if (
        terminalEvents.length !== 1 ||
        cancellations.length !== 1 ||
        cancellations[0] === undefined ||
        cancellations[0] !== events[events.length - 1] ||
        cancellations[0].body.kind !== "cancellation_observed" ||
        cancellations[0].body.cancellationRef !== invocation.cancellationRef ||
        !publicationIsApplied(cancellations[0].body.publication) ||
        cancellations[0].body.publication.productKind !== "run_cancellation" ||
        exit.failure.code !== "cancelled"
      ) {
        addVerificationError(
          errors,
          "cancellation_mismatch",
          "exit",
          "A cancelled exit requires one exact cancellation product-event application bound to invocation.cancellationRef"
        );
      }
      break;
    }
  }
  return terminalEvents.length;
}

function invocationTransitionIsLegal(state: RuntimeLifecycleState, trigger: InvocationTrigger): boolean {
  if (state === "queued") {
    return trigger.kind === "initial";
  }
  if (state === "running") {
    return trigger.kind === "continuation" || trigger.kind === "recoverable_restart";
  }
  if (state === "waiting_for_input") {
    return trigger.kind === "human_input" || trigger.kind === "continuation";
  }
  return false;
}

function hasAcceptedTriggerEvent(trigger: InvocationTrigger, acceptedEvents: readonly DurableAcceptedEvent[]): boolean {
  if (trigger.kind === "initial") {
    return true;
  }
  if (trigger.kind === "human_input" || trigger.pendingInputEventRef !== undefined) {
    return acceptedEvents.some((event) => event.eventId === trigger.pendingInputEventRef);
  }
  return acceptedEvents.some((event) => event.eventId === trigger.eventRef);
}

function validateLifecycleFacts(lifecycle: RuntimeDurableState, errors: RuntimeVerificationError[]) {
  if (!Number.isInteger(lifecycle.lastAcceptedSequence) || lifecycle.lastAcceptedSequence < 0) {
    addVerificationError(
      errors,
      "authority_facts_missing",
      "trusted.lifecycle.lastAcceptedSequence",
      "Durable sequence must be a non-negative integer"
    );
  }
  const eventIds = new Set<string>();
  const idempotencyKeys = new Set<string>();
  for (const [index, event] of lifecycle.acceptedEvents.entries()) {
    if (eventIds.has(event.eventId)) {
      addVerificationError(
        errors,
        "event_duplicate",
        `trusted.lifecycle.acceptedEvents[${index}].eventId`,
        "Durable event IDs must be unique"
      );
    }
    if (idempotencyKeys.has(event.idempotencyKey)) {
      addVerificationError(
        errors,
        "event_idempotency_duplicate",
        `trusted.lifecycle.acceptedEvents[${index}].idempotencyKey`,
        "Durable idempotency keys must be unique"
      );
    }
    eventIds.add(event.eventId);
    idempotencyKeys.add(event.idempotencyKey);
  }
}

function durableProductBindingFromPublication(publication: AnyProductPublication): DurableAcceptedProductBinding {
  return publication;
}

function productBindingFromRuntimeEvent(event: RuntimeEvent): DurableAcceptedProductBinding | undefined {
  const body = event.body;
  if (
    body.kind !== "conversation_publication_observed" &&
    body.kind !== "input_request_observed" &&
    body.kind !== "artifact_observed" &&
    body.kind !== "outcome_submission_observed" &&
    body.kind !== "failure_observed" &&
    body.kind !== "blocker_observed" &&
    body.kind !== "cancellation_observed"
  ) {
    return undefined;
  }
  return durableProductBindingFromPublication(body.publication);
}

function durableAcceptedEventFromRuntimeEvent(
  event: RuntimeEvent,
  binding: RuntimeDurableStateBinding
): DurableAcceptedEvent {
  const body = event.body;
  const productBinding = productBindingFromRuntimeEvent(event);
  return {
    ...binding,
    invocationId: event.invocationId,
    eventId: event.eventId,
    idempotencyKey: event.idempotencyKey,
    correlationId: event.correlationId,
    causationRef: event.causationRef,
    sequence: event.sequence,
    fingerprint: fingerprint(event),
    kind: body.kind,
    ...(productBinding === undefined ? {} : { productBinding }),
  };
}

function pendingInputFromRuntimeEvent(event: RuntimeEvent): DurablePendingInputBinding | undefined {
  if (event.body.kind !== "input_request_observed" || event.body.publication.action !== "applied") {
    return undefined;
  }
  const publication = event.body.publication;
  return {
    eventId: event.eventId,
    invocationId: event.invocationId,
    correlationId: event.correlationId,
    causationRef: event.causationRef,
    inputRequestRef: publication.productRef,
    productEventRef: publication.productEventRef,
    operationAttemptRef: publication.operationAttemptRef,
    operationRef: publication.operationRef,
    applicationServiceRef: publication.applicationServiceRef,
    gatewayReceiptRef: publication.gatewayReceiptRef,
    receiptRef: publication.receiptRef,
    auditReceiptRef: publication.auditReceiptRef,
    questionDigest: fingerprint({ question: event.body.question }),
  };
}

function terminalBindingFromRuntimeEvent(event: RuntimeEvent): DurableTerminalBinding | undefined {
  if (
    event.body.kind !== "outcome_submission_observed" &&
    event.body.kind !== "failure_observed" &&
    event.body.kind !== "blocker_observed" &&
    event.body.kind !== "cancellation_observed"
  ) {
    return undefined;
  }
  if (event.body.publication.action !== "applied") {
    return undefined;
  }
  return {
    eventId: event.eventId,
    invocationId: event.invocationId,
    correlationId: event.correlationId,
    causationRef: event.causationRef,
    productBinding: durableProductBindingFromPublication(event.body.publication) as Extract<
      DurableAcceptedProductBinding,
      { action: "applied" }
    >,
  };
}

function verifyPendingInputContinuation(
  trigger: InvocationTrigger,
  lifecycle: RuntimeDurableState,
  newContextEventRefs: readonly EventRef[],
  errors: RuntimeVerificationError[]
): void {
  const isWaiting = lifecycle.state === "waiting_for_input";
  const hasPendingTrigger = trigger.kind !== "initial" && trigger.pendingInputEventRef !== undefined;
  if (!isWaiting) {
    if (trigger.kind === "human_input" || hasPendingTrigger) {
      addVerificationError(
        errors,
        "pending_input_mismatch",
        "invocation.trigger",
        "Only a waiting run may continue from a pending input request"
      );
    }
    return;
  }

  const pending = lifecycle.pendingInput;
  if (
    trigger.kind !== "human_input" ||
    pending === undefined ||
    trigger.pendingInputEventRef === undefined ||
    trigger.pendingInputEventRef !== pending.eventId
  ) {
    addVerificationError(
      errors,
      "pending_input_mismatch",
      "invocation.trigger.pendingInputEventRef",
      "Continuation must cite the exact currently pending input request event"
    );
    return;
  }
  if (!newContextEventRefs.includes(pending.eventId) || !newContextEventRefs.includes(trigger.eventRef)) {
    addVerificationError(
      errors,
      "pending_input_mismatch",
      "invocation.newContextEventRefs",
      "Continuation context must include both the pending request and the Plane-owned answer event"
    );
  }
}

function verifyTrustedHumanInputAnswer(
  snapshot: RunSnapshot,
  invocation: InvocationEnvelope,
  lifecycle: RuntimeDurableState,
  events: readonly RuntimeEvent[],
  fact: TrustedHumanInputAnswer | undefined,
  head: TrustedHumanAnswerHead | undefined,
  errors: RuntimeVerificationError[]
): void {
  if (invocation.trigger.kind !== "human_input") {
    if (fact !== undefined || head !== undefined) {
      addVerificationError(
        errors,
        "human_input_answer_mismatch",
        "trusted.humanInputAnswer",
        "A trusted human answer fact and head are valid only for a human-input invocation"
      );
    }
    return;
  }
  if (fact === undefined || head === undefined) {
    addVerificationError(
      errors,
      "human_input_answer_mismatch",
      "trusted.humanInputAnswer",
      "Human-input invocations require one trusted Plane answer fact and its independent Plane answer head"
    );
    return;
  }
  let parsedResponderPrincipal: TrustedHumanAnswerResponderPrincipal | undefined;
  try {
    parseRef(fact.answerEventRef, "trusted.humanInputAnswer.answerEventRef", parseEventRef);
    parseRef(fact.inputRequestRef, "trusted.humanInputAnswer.inputRequestRef", parseInputRequestRef);
    parsedResponderPrincipal = parseTrustedHumanAnswerResponderPrincipal(
      fact.responderPrincipal,
      "trusted.humanInputAnswer.responderPrincipal"
    );
    parseRef(fact.workspaceRef, "trusted.humanInputAnswer.workspaceRef", parseWorkspaceRef);
    parseRef(fact.runId, "trusted.humanInputAnswer.runId", parseRunId);
    parseRef(
      fact.authorizationReceiptRef,
      "trusted.humanInputAnswer.authorizationReceiptRef",
      parseAuthorizationReceiptRef
    );
    parseRef(fact.applicationServiceRef, "trusted.humanInputAnswer.applicationServiceRef", parseApplicationServiceRef);
    parseRef(fact.gatewayReceiptRef, "trusted.humanInputAnswer.gatewayReceiptRef", parseGatewayReceiptRef);
    parseRef(fact.receiptRef, "trusted.humanInputAnswer.receiptRef", parseReceiptRef);
    parseRef(fact.auditReceiptRef, "trusted.humanInputAnswer.auditReceiptRef", parseAuditReceiptRef);
    parseRef(fact.correlationId, "trusted.humanInputAnswer.correlationId", parseCorrelationId);
    parseRef(fact.causationRef, "trusted.humanInputAnswer.causationRef", parseCausationRef);
    parseDigest(fact.payloadDigest, "trusted.humanInputAnswer.payloadDigest", parseContentDigest);
    parseDigest(fact.answerFactDigest, "trusted.humanInputAnswer.answerFactDigest", parseContentDigest);
    parseDigest(head.answerFactDigest, "trusted.humanInputAnswerHead.answerFactDigest", parseContentDigest);
  } catch {
    addVerificationError(
      errors,
      "human_input_answer_mismatch",
      "trusted.humanInputAnswer",
      "The trusted Plane answer must carry valid authorization, application, and audit proof references"
    );
  }
  const pending = lifecycle.pendingInput;
  const exactBinding =
    lifecycle.state === "waiting_for_input" &&
    pending !== undefined &&
    fact.workspaceRef === snapshot.workspaceRef &&
    fact.runId === snapshot.runId &&
    fact.answerEventRef === invocation.trigger.eventRef &&
    fact.inputRequestRef === pending.inputRequestRef &&
    fact.correlationId === invocation.correlationId &&
    fact.causationRef === invocation.causationRef &&
    parsedResponderPrincipal !== undefined &&
    parsedResponderPrincipal.planePrincipalId !== snapshot.actorRef &&
    fact.answerFactDigest === head.answerFactDigest &&
    fact.answerFactDigest === invocation.trigger.answerFactDigest &&
    computeTrustedHumanInputAnswerDigest(fact) === head.answerFactDigest;
  if (!exactBinding) {
    addVerificationError(
      errors,
      "human_input_answer_mismatch",
      "trusted.humanInputAnswer",
      "The trusted Plane answer must bind to the current pending request, run, correlation, causation, separate responder principal, and independent answer head"
    );
  }
  if (events.some((event) => event.eventId === fact.answerEventRef)) {
    addVerificationError(
      errors,
      "human_input_answer_mismatch",
      "events",
      "Runtime events cannot manufacture the Plane answer that triggered an invocation"
    );
  }
  if (lifecycle.acceptedHumanInputAnswers.some((answer) => answer.answerEventRef === fact.answerEventRef)) {
    addVerificationError(
      errors,
      "human_input_answer_mismatch",
      "trusted.humanInputAnswer.answerEventRef",
      "A Plane answer fact can be consumed only once across invocations and restarts"
    );
  }
}

function durableStateHeadMatches(
  snapshot: RunSnapshot,
  lifecycle: RuntimeDurableState,
  head: TrustedDurableStateHead | undefined
): boolean {
  return (
    head !== undefined &&
    head.workspaceRef === snapshot.workspaceRef &&
    head.actorRef === snapshot.actorRef &&
    head.profileVersionRef === snapshot.profile.profileRef &&
    head.runId === snapshot.runId &&
    head.snapshotContentDigest === snapshot.contentDigest &&
    head.revision === lifecycle.revision &&
    head.stateDigest === lifecycle.stateDigest &&
    head.previousRevision === lifecycle.previousRevision &&
    head.previousStateDigest === lifecycle.previousStateDigest
  );
}

export function verifyRuntimeExecution(input: RuntimeVerificationInput): RuntimeVerificationResult {
  const errors: RuntimeVerificationError[] = [];
  const { manifest, snapshot, invocation, events, exit, trusted } = input;
  const durableStateParsed = trusted !== undefined && isValidatedContract(trusted.lifecycle, "RuntimeDurableState");
  if (
    !trusted ||
    !isValidatedContract(snapshot, "RunSnapshot") ||
    !isValidatedContract(invocation, "InvocationEnvelope") ||
    !events.every((event) => isValidatedContract(event, "RuntimeEvent")) ||
    !isValidatedContract(exit, "RuntimeExit") ||
    !durableStateParsed
  ) {
    addVerificationError(
      errors,
      !durableStateParsed ? "unparsed_durable_state" : "unparsed_contract_input",
      "input",
      !durableStateParsed
        ? "Runtime semantic verification accepts only parser-produced durable state"
        : "Runtime semantic verification accepts only parser-produced contract values"
    );
    return { ok: false, errors };
  }
  if (!trusted || !trusted.authority || !trusted.lifecycle) {
    addVerificationError(
      errors,
      "authority_facts_missing",
      "trusted",
      "Trusted authority and durable lifecycle facts are required"
    );
    return { ok: false, errors };
  }
  validateLifecycleFacts(trusted.lifecycle, errors);
  if (!durableStateHeadMatches(snapshot, trusted.lifecycle, trusted.durableStateHead)) {
    addVerificationError(
      errors,
      "durable_state_head_mismatch",
      "trusted.durableStateHead",
      "The supplied parsed durable state must exactly match the independently trusted Plane durable head"
    );
  }
  if (
    trusted.lifecycle.binding.workspaceRef !== snapshot.workspaceRef ||
    trusted.lifecycle.binding.actorRef !== snapshot.actorRef ||
    trusted.lifecycle.binding.profileVersionRef !== snapshot.profile.profileRef ||
    trusted.lifecycle.binding.runId !== snapshot.runId ||
    trusted.lifecycle.binding.snapshotContentDigest !== snapshot.contentDigest
  ) {
    addVerificationError(
      errors,
      "durable_state_invalid",
      "trusted.lifecycle.binding",
      "Durable state must bind to the exact workspace, actor, profile, run, and snapshot"
    );
  }
  verifyTrustedHumanInputAnswer(
    snapshot,
    invocation,
    trusted.lifecycle,
    events,
    trusted.humanInputAnswer,
    trusted.humanInputAnswerHead,
    errors
  );
  const expectedContractDigests = contractDigestsFromManifest(manifest);
  if (JSON.stringify(snapshot.contractDigests) !== JSON.stringify(expectedContractDigests)) {
    addVerificationError(
      errors,
      "contract_digest_mismatch",
      "snapshot.contractDigests",
      "Snapshot contract digests must match the supplied generated manifest"
    );
  }
  if (!verifyRunSnapshotContentDigest(snapshot)) {
    addVerificationError(
      errors,
      "snapshot_content_digest_mismatch",
      "snapshot.contentDigest",
      "Snapshot content digest does not match canonical immutable content"
    );
  }
  if (!verifyInvocationSnapshotBinding(snapshot, invocation)) {
    addVerificationError(
      errors,
      "invocation_snapshot_binding_mismatch",
      "invocation.runSnapshotDigest",
      "Invocation must bind to the exact immutable snapshot content digest"
    );
  }
  if (!authorityMatches(snapshot, invocation, trusted.authority)) {
    addVerificationError(
      errors,
      "authority_facts_missing",
      "trusted.authority",
      "Trusted expected workspace, actor, profile, run, invocation, snapshot, and correlation bindings do not match"
    );
  }
  if (
    trusted.cancellation.cancellationRef !== invocation.cancellationRef ||
    trusted.lease.leaseId !== invocation.lease.leaseId ||
    !trusted.lease.isValid
  ) {
    addVerificationError(
      errors,
      "lease_untrusted",
      "trusted.lease",
      "The trusted lease and cancellation reference must bind to this invocation"
    );
  }
  if (!trusted.cancellation.isCancelled && exit.kind === "cancelled") {
    addVerificationError(
      errors,
      "cancellation_mismatch",
      "trusted.cancellation",
      "A cancelled exit requires trusted cancellation authority"
    );
  }
  if (trusted.cancellation.isCancelled && exit.kind !== "cancelled") {
    addVerificationError(
      errors,
      "cancellation_mismatch",
      "exit.kind",
      "Trusted cancellation cannot finish as a non-cancelled exit"
    );
  }
  if (!sameBudgetOrLower(invocation.remainingBudget, snapshot.totalBudget)) {
    addVerificationError(
      errors,
      "budget_increased",
      "invocation.remainingBudget",
      "Remaining invocation budget cannot exceed the run total budget"
    );
  }
  if (invocation.trigger.kind !== "initial") {
    if (!invocation.newContextEventRefs.includes(invocation.trigger.eventRef)) {
      addVerificationError(
        errors,
        "invocation_identity_mismatch",
        "invocation.newContextEventRefs",
        "Trigger event must be included as new context"
      );
    }
    if (trusted.previousRemainingBudget === undefined) {
      addVerificationError(
        errors,
        "budget_baseline_missing",
        "trusted.previousRemainingBudget",
        "Continuation verification requires the prior durable remaining budget"
      );
    } else if (!sameBudgetOrLower(invocation.remainingBudget, trusted.previousRemainingBudget)) {
      addVerificationError(
        errors,
        "budget_increased",
        "invocation.remainingBudget",
        "Remaining budget must be cumulative and monotonic across invocations"
      );
    }
    if (
      (invocation.trigger.kind === "continuation" || invocation.trigger.kind === "recoverable_restart") &&
      invocation.checkpointRef === undefined
    ) {
      addVerificationError(
        errors,
        "continuation_checkpoint_missing",
        "invocation.checkpointRef",
        "Continuation and restart invocations require a checkpoint"
      );
    }
    if (!hasAcceptedTriggerEvent(invocation.trigger, trusted.lifecycle.acceptedEvents)) {
      addVerificationError(
        errors,
        "invocation_identity_mismatch",
        "invocation.trigger.eventRef",
        "Continuation trigger must reference a durable accepted event"
      );
    }
  } else if (invocation.checkpointRef !== undefined) {
    addVerificationError(
      errors,
      "initial_checkpoint_forbidden",
      "invocation.checkpointRef",
      "Initial invocations cannot carry a continuation checkpoint"
    );
  }
  if (
    invocation.checkpointRef !== undefined &&
    (trusted.checkpoint?.checkpointRef !== invocation.checkpointRef || !trusted.checkpoint.isVerified)
  ) {
    addVerificationError(
      errors,
      "checkpoint_untrusted",
      "trusted.checkpoint",
      "Checkpoint identity and safety must be trusted by the host"
    );
  }

  const acceptedById = new Map(trusted.lifecycle.acceptedEvents.map((event) => [event.eventId, event]));
  const acceptedByIdempotency = new Map(trusted.lifecycle.acceptedEvents.map((event) => [event.idempotencyKey, event]));
  const historicalProductKeys = new Set<string>();
  for (const acceptedEvent of trusted.lifecycle.acceptedEvents) {
    if (isAppliedProductBinding(acceptedEvent.productBinding)) {
      for (const key of productUniquenessKeys(acceptedEvent.productBinding)) {
        historicalProductKeys.add(key);
      }
    }
  }
  const replayableProductKeys = new Set<string>();
  for (const runtimeEvent of events) {
    const acceptedEvent = acceptedById.get(runtimeEvent.eventId);
    const productBinding = productBindingFromRuntimeEvent(runtimeEvent);
    if (
      acceptedEvent !== undefined &&
      acceptedEvent.fingerprint === fingerprint(runtimeEvent) &&
      productBinding !== undefined &&
      isAppliedProductBinding(productBinding) &&
      sameJson(acceptedEvent.productBinding, productBinding)
    ) {
      for (const key of productUniquenessKeys(productBinding)) {
        replayableProductKeys.add(key);
      }
    }
  }
  const seenEventIds = new Set<string>();
  const seenIdempotencyKeys = new Set<string>();
  const newEvents: DurableAcceptedEvent[] = [];
  let expectedSequence = trusted.lifecycle.revision === 0 ? 0 : trusted.lifecycle.lastAcceptedSequence + 1;
  let allEventsReplay = true;
  const usedReceiptIndexes = new Set<number>();
  prevalidatePublicationReceipts(trusted.publicationReceipts, errors, historicalProductKeys, replayableProductKeys);
  for (const [index, event] of events.entries()) {
    const path = `events[${index}]`;
    if (
      event.workspaceRef !== trusted.authority.workspaceRef ||
      event.actorRef !== trusted.authority.actorRef ||
      event.runId !== trusted.authority.runId ||
      event.invocationId !== trusted.authority.invocationId ||
      event.correlationId !== trusted.authority.correlationId ||
      event.causationRef !== trusted.authority.causationRef
    ) {
      addVerificationError(
        errors,
        "event_identity_mismatch",
        path,
        "Event identity must match the trusted authority facts"
      );
    }
    if (seenEventIds.has(event.eventId)) {
      addVerificationError(
        errors,
        "event_duplicate",
        `${path}.eventId`,
        "Event IDs must be unique within a submission"
      );
    }
    if (seenIdempotencyKeys.has(event.idempotencyKey)) {
      addVerificationError(
        errors,
        "event_idempotency_duplicate",
        `${path}.idempotencyKey`,
        "Event idempotency keys must be unique within a submission"
      );
    }
    seenEventIds.add(event.eventId);
    seenIdempotencyKeys.add(event.idempotencyKey);
    const eventFingerprint = fingerprint(event);
    const durableById = acceptedById.get(event.eventId);
    const durableByKey = acceptedByIdempotency.get(event.idempotencyKey);
    if (durableById !== undefined || durableByKey !== undefined) {
      if (
        durableById === undefined ||
        durableByKey === undefined ||
        durableById.fingerprint !== eventFingerprint ||
        durableByKey.fingerprint !== eventFingerprint ||
        durableById.idempotencyKey !== event.idempotencyKey ||
        durableByKey.eventId !== event.eventId
      ) {
        addVerificationError(
          errors,
          "event_idempotency_conflict",
          path,
          "A replayed event ID or idempotency key conflicts with durable accepted content"
        );
      }
    } else {
      allEventsReplay = false;
      if (event.sequence !== expectedSequence) {
        addVerificationError(
          errors,
          "event_sequence_invalid",
          `${path}.sequence`,
          "New event sequences must continue from the trusted durable lastAcceptedSequence"
        );
      }
      expectedSequence += 1;
      newEvents.push(durableAcceptedEventFromRuntimeEvent(event, trusted.lifecycle.binding));
    }
    const productBinding = productBindingFromRuntimeEvent(event);
    if (isAppliedProductBinding(productBinding) && historicalProductKeys.size > 0) {
      const exactReplay =
        durableById !== undefined &&
        durableById.fingerprint === eventFingerprint &&
        sameJson(durableById.productBinding, productBinding);
      if (!exactReplay && productUniquenessKeys(productBinding).some((key) => historicalProductKeys.has(key))) {
        addVerificationError(
          errors,
          "publication_product_duplicate",
          "events.body",
          "An applied product event cannot reuse an operation, receipt, product identity, or binding tuple from durable history"
        );
      }
    }
    if (
      !isCanonicalJsonUtf8ByteLengthAtMost(
        event,
        Math.min(MAX_SERIALIZED_JSON_BYTES, snapshot.runtimePolicy.maxEventPayloadBytes)
      )
    ) {
      addVerificationError(
        errors,
        "event_payload_too_large",
        `${path}`,
        "Whole canonical UTF-8 event bytes exceed the global or RunSnapshot event limit"
      );
    }
    if (
      event.body.kind === "artifact_observed" &&
      event.body.artifact.sizeBytes > snapshot.runtimePolicy.maxArtifactBytes
    ) {
      addVerificationError(
        errors,
        "artifact_too_large",
        `${path}.body.artifact.sizeBytes`,
        "Artifact size exceeds the resolved snapshot artifact limit"
      );
    }
    verifyPublication(event.body, path, snapshot, invocation, trusted.publicationReceipts, usedReceiptIndexes, errors);
  }
  for (let index = 1; index < events.length; index += 1) {
    if (isTerminalBody(events[index - 1].body)) {
      addVerificationError(
        errors,
        "events_after_terminal",
        `events[${index}]`,
        "No event may follow a terminal lifecycle observation"
      );
    }
  }

  const expectedFinalSequence =
    events.length === 0 ? trusted.lifecycle.lastAcceptedSequence : events[events.length - 1].sequence;
  if (exit.finalSequence !== expectedFinalSequence) {
    addVerificationError(
      errors,
      "final_sequence_mismatch",
      "exit.finalSequence",
      "Exit finalSequence must equal the last accepted event sequence"
    );
  }
  verifyPendingInputContinuation(invocation.trigger, trusted.lifecycle, invocation.newContextEventRefs, errors);
  for (const [index] of trusted.publicationReceipts.entries()) {
    if (!usedReceiptIndexes.has(index)) {
      addVerificationError(
        errors,
        "publication_receipt_unused",
        `trusted.publicationReceipts[${index}]`,
        "Every trusted application receipt must be consumed by exactly one applied runtime event"
      );
    }
  }
  if (
    exit.workspaceRef !== trusted.authority.workspaceRef ||
    exit.actorRef !== trusted.authority.actorRef ||
    exit.runId !== trusted.authority.runId ||
    exit.invocationId !== trusted.authority.invocationId ||
    exit.idempotencyKey !== trusted.authority.invocationIdempotencyKey ||
    exit.correlationId !== trusted.authority.correlationId ||
    exit.causationRef !== trusted.authority.causationRef
  ) {
    addVerificationError(
      errors,
      "exit_identity_mismatch",
      "exit",
      "Exit identity must match the trusted authority facts"
    );
  }
  const terminalEventCount = verifyTerminalEvents(events, exit, invocation, errors);
  const exitFingerprint = fingerprint(exit);
  const durableExit = trusted.lifecycle.acceptedExits.find(
    (accepted) => accepted.invocationId === exit.invocationId || accepted.idempotencyKey === exit.idempotencyKey
  );
  const exactExitReplay = durableExit !== undefined && durableExit.fingerprint === exitFingerprint && allEventsReplay;
  if (durableExit !== undefined && durableExit.fingerprint !== exitFingerprint) {
    addVerificationError(
      errors,
      "event_idempotency_conflict",
      "exit",
      "A replayed invocation exit conflicts with durable accepted content"
    );
  }
  if (durableExit !== undefined && !allEventsReplay) {
    addVerificationError(
      errors,
      "event_idempotency_conflict",
      "events",
      "A previously accepted invocation cannot accept new events during an exit replay"
    );
  }
  const transitionIsNew = durableExit === undefined;
  if (transitionIsNew && !invocationTransitionIsLegal(trusted.lifecycle.state, invocation.trigger)) {
    addVerificationError(
      errors,
      "terminal_event_mismatch",
      "trusted.lifecycle.state",
      "The invocation trigger is not a legal transition from the trusted durable lifecycle state"
    );
  }
  if (errors.length > 0) {
    return { ok: false, errors };
  }
  if (exactExitReplay) {
    const replayLifecycle = parseRuntimeDurableState(canonicalizeJson(trusted.lifecycle));
    return {
      ok: true,
      result: "idempotent_replay",
      state: exit.kind,
      finalSequence: exit.finalSequence,
      terminalEventCount,
      nextLifecycle: replayLifecycle,
    };
  }

  const finalEvent = events.at(-1);
  const nextTerminal = finalEvent === undefined ? undefined : terminalBindingFromRuntimeEvent(finalEvent);
  const nextPending = finalEvent === undefined ? undefined : pendingInputFromRuntimeEvent(finalEvent);
  const nextLifecycleRaw: RuntimeDurableStateContent = {
    protocol: PLANE_AGENT_RUNTIME_PROTOCOL,
    stateVersion: RUNTIME_DURABLE_STATE_VERSION,
    binding: trusted.lifecycle.binding,
    state: stateForExit(exit.kind),
    revision: trusted.lifecycle.revision + 1,
    previousRevision: trusted.lifecycle.revision,
    previousStateDigest: trusted.lifecycle.stateDigest,
    lastAcceptedSequence: Math.max(trusted.lifecycle.lastAcceptedSequence, ...newEvents.map((event) => event.sequence)),
    acceptedEvents: [...trusted.lifecycle.acceptedEvents, ...newEvents],
    acceptedHumanInputAnswers: [
      ...trusted.lifecycle.acceptedHumanInputAnswers,
      ...(invocation.trigger.kind === "human_input" && trusted.humanInputAnswer !== undefined
        ? [trusted.humanInputAnswer]
        : []),
    ],
    acceptedExits: [
      ...trusted.lifecycle.acceptedExits,
      {
        ...trusted.lifecycle.binding,
        invocationId: exit.invocationId,
        idempotencyKey: exit.idempotencyKey,
        finalSequence: exit.finalSequence,
        fingerprint: exitFingerprint,
        kind: exit.kind,
        ...(exit.kind === "waiting_for_input" ? { inputEventId: exit.inputEventRef } : {}),
        ...(nextTerminal === undefined ? {} : { terminalEventId: nextTerminal.eventId }),
      },
    ],
    ...(nextTerminal === undefined ? {} : { terminal: nextTerminal }),
    ...(exit.kind === "waiting_for_input" && nextPending !== undefined ? { pendingInput: nextPending } : {}),
  };
  const nextLifecycle = parseRuntimeDurableState({
    ...nextLifecycleRaw,
    stateDigest: computeRuntimeDurableStateDigest(nextLifecycleRaw),
  });
  return {
    ok: true,
    result: "accepted",
    state: exit.kind,
    finalSequence: exit.finalSequence,
    terminalEventCount,
    nextLifecycle,
  };
}

export const runtimeSemanticVerifier: RuntimeSemanticVerifier = {
  verify: verifyRuntimeExecution,
};

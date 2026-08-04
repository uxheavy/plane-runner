import { createHash } from "node:crypto";

export const PLANE_AGENT_RUNTIME_PROTOCOL = "plane.agent-runtime/v1" as const;
export const MAX_SERIALIZED_JSON_BYTES = 1_048_576;

export type PlaneAgentRuntimeProtocol = typeof PLANE_AGENT_RUNTIME_PROTOCOL;

declare const opaqueRefBrand: unique symbol;
const validatedContractMarker = Symbol("plane.agent-runtime/v1 validated contract");

type ValidatedContract<Name extends string> = {
  readonly [validatedContractMarker]: Name;
};

type ValidatedContractName = "RunSnapshot" | "InvocationEnvelope" | "RuntimeEvent" | "RuntimeExit";

function markValidatedContract<Name extends ValidatedContractName, T extends object>(
  value: T,
  name: Name
): T & ValidatedContract<Name> {
  Object.defineProperty(value, validatedContractMarker, {
    configurable: false,
    enumerable: false,
    value: name,
    writable: false,
  });
  return value as T & ValidatedContract<Name>;
}

function isValidatedContract<Name extends ValidatedContractName>(value: unknown, name: Name): boolean {
  return isRecord(value) && (value as Record<PropertyKey, unknown>)[validatedContractMarker] === name;
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
export type ContractDigest = OpaqueRef<"contract-digest">;
export type ContentDigest = OpaqueRef<"content-digest">;
export type RunSnapshotContentDigest = OpaqueRef<"run-snapshot-content-digest">;

const REF_SUFFIX_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._~/-]{0,119}$/;
const NAMESPACED_REF_PATTERN = /^[a-z][a-z0-9-]{0,30}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,119}$/;
const DIGEST_PATTERN = /^[a-f0-9]{64}$/;
const MAX_REF_LENGTH = 128;

type RefTag = string;

function makeNamespacedRef<Tag extends RefTag>(tag: Tag, namespace: string, value: string): OpaqueRef<Tag> {
  void tag;
  if (!REF_SUFFIX_PATTERN.test(value)) {
    throw new TypeError(`${namespace} references must contain a 1-120 character identifier suffix`);
  }

  const namespaced = `${namespace}:${value}`;
  if (namespaced.length > MAX_REF_LENGTH) {
    throw new TypeError(`${namespace} references must be at most 128 characters`);
  }

  return namespaced as OpaqueRef<Tag>;
}

function parseNamespacedRef<Tag extends RefTag>(tag: Tag, namespace: string, value: unknown): OpaqueRef<Tag> {
  void tag;
  if (typeof value !== "string" || value.length > MAX_REF_LENGTH || !NAMESPACED_REF_PATTERN.test(value)) {
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

function makeDigest<Tag extends RefTag>(tag: Tag, namespace: string, value: string): OpaqueRef<Tag> {
  void tag;
  if (!DIGEST_PATTERN.test(value)) {
    throw new TypeError(`${namespace} digests must be lowercase SHA-256 hex strings`);
  }

  return `${namespace}:${value}` as OpaqueRef<Tag>;
}

function parseNamespacedDigest<Tag extends RefTag>(tag: Tag, namespace: string, value: unknown): OpaqueRef<Tag> {
  void tag;
  if (typeof value !== "string" || !value.startsWith(`${namespace}:`)) {
    throw new TypeError(`Expected a ${namespace} digest`);
  }

  return makeDigest(tag, namespace, value.slice(namespace.length + 1));
}

export function createContractDigest(value: string): ContractDigest {
  if (!DIGEST_PATTERN.test(value)) {
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

export const createContentDigest = (value: string): ContentDigest => makeDigest("content-digest", "content", value);
export const parseContentDigest = (value: unknown): ContentDigest =>
  parseNamespacedDigest("content-digest", "content", value);
export const createRunSnapshotContentDigest = (value: string): RunSnapshotContentDigest =>
  makeDigest("run-snapshot-content-digest", "snapshot", value);
export const parseRunSnapshotContentDigest = (value: unknown): RunSnapshotContentDigest =>
  parseNamespacedDigest("run-snapshot-content-digest", "snapshot", value);

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const key of Reflect.ownKeys(value)) {
      deepFreeze(Reflect.get(value, key));
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
}>;

export const CONTRACT_SCHEMA_NAMES = ["run-snapshot", "invocation-envelope", "runtime-event", "runtime-exit"] as const;
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
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseManifestEntry(value: unknown, name: ContractSchemaName) {
  if (!isRecord(value) || value.filename !== `${name}.schema.json`) {
    throw new TypeError(`Invalid manifest entry for ${name}`);
  }

  return { filename: value.filename, sha256: parseContractDigest(value.sha256) };
}

export function parseContractManifest(value: unknown): ContractManifest {
  if (!isRecord(value) || value.protocol !== PLANE_AGENT_RUNTIME_PROTOCOL || !isRecord(value.schemas)) {
    throw new TypeError("Invalid Plane Agent runtime contract manifest");
  }

  const schemas = value.schemas;
  return {
    protocol: PLANE_AGENT_RUNTIME_PROTOCOL,
    schemas: {
      "run-snapshot": parseManifestEntry(schemas["run-snapshot"], "run-snapshot"),
      "invocation-envelope": parseManifestEntry(schemas["invocation-envelope"], "invocation-envelope"),
      "runtime-event": parseManifestEntry(schemas["runtime-event"], "runtime-event"),
      "runtime-exit": parseManifestEntry(schemas["runtime-exit"], "runtime-exit"),
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
  if (value === null) {
    return "null";
  }

  if (typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("Canonical JSON cannot contain non-finite numbers");
    }
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalizeJson(item)).join(",")}]`;
  }

  if (typeof value === "object") {
    const object = value as Record<string, unknown>;
    const entries = Object.keys(object)
      .toSorted()
      .filter((key) => object[key] !== undefined)
      .map((key) => `${JSON.stringify(key)}:${canonicalizeJson(object[key])}`);
    return `{${entries.join(",")}}`;
  }

  throw new TypeError("Canonical JSON cannot contain undefined, bigint, function, or symbol values");
}

export function serializedJsonByteLength(value: unknown): number {
  return new TextEncoder().encode(canonicalizeJson(value)).byteLength;
}

export const UTF8_BYTE_LIMITS = {
  reference: 128,
  boundedText: 4096,
  boundedPrompt: 32768,
  boundedToken: 256,
  timestamp: 64,
  serializedContract: MAX_SERIALIZED_JSON_BYTES,
} as const;

export class ContractParseError extends TypeError {
  readonly path: string;

  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "ContractParseError";
    this.path = path;
  }
}

function parseRawJson(value: unknown, path: string): unknown {
  if (typeof value !== "string") {
    return value;
  }

  try {
    return JSON.parse(value) as unknown;
  } catch {
    throw new ContractParseError(path, "must be valid JSON");
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
  const bytes = new TextEncoder().encode(value).byteLength;
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
  return parseString(value, path, UTF8_BYTE_LIMITS.boundedText) as BoundedText;
}

function parseBoundedPrompt(value: unknown, path: string): BoundedPrompt {
  return parseString(value, path, UTF8_BYTE_LIMITS.boundedPrompt) as BoundedPrompt;
}

function parseBoundedToken(value: unknown, path: string): string {
  return parseString(value, path, UTF8_BYTE_LIMITS.boundedToken);
}

function parseTimestamp(value: unknown, path: string): Timestamp {
  return parseString(value, path, UTF8_BYTE_LIMITS.timestamp) as Timestamp;
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
  terminal = false
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
  if (action === "proposal" && !terminal) {
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
      sizeBytes: parseInteger(reference.sizeBytes, `${path}.sizeBytes`, 1_048_576),
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
    sizeBytes: parseInteger(object.sizeBytes, `${path}.sizeBytes`, 1_048_576),
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
        publication: parsePublication(object.publication, `${path}.publication`, "outcome_submission", (item) =>
          parseRef(item, `${path}.publication.productRef`, parseOutcomeSubmissionRef)
        ),
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
  const object = requireRecord(value, path, ["runSnapshot", "invocationEnvelope", "runtimeEvent", "runtimeExit"]);
  return {
    runSnapshot: parseDigest(object.runSnapshot, `${path}.runSnapshot`, parseContractDigest) as ContractDigest,
    invocationEnvelope: parseDigest(
      object.invocationEnvelope,
      `${path}.invocationEnvelope`,
      parseContractDigest
    ) as ContractDigest,
    runtimeEvent: parseDigest(object.runtimeEvent, `${path}.runtimeEvent`, parseContractDigest) as ContractDigest,
    runtimeExit: parseDigest(object.runtimeExit, `${path}.runtimeExit`, parseContractDigest) as ContractDigest,
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
        1_048_576
      ),
      maxArtifactBytes: parseInteger(
        runtimePolicyObject.maxArtifactBytes,
        `${path}.runtimePolicy.maxArtifactBytes`,
        1_048_576
      ),
      maxReceiptBytes: parseInteger(
        runtimePolicyObject.maxReceiptBytes,
        `${path}.runtimePolicy.maxReceiptBytes`,
        1_048_576
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
  const triggerObject = requireRecord(object.trigger, "InvocationEnvelope.trigger", ["kind"], ["eventRef"]);
  let trigger: InvocationTrigger;
  if (triggerObject.kind === "initial") {
    if (Object.hasOwn(triggerObject, "eventRef")) {
      throw new ContractParseError("InvocationEnvelope.trigger.eventRef", "is forbidden for an initial invocation");
    }
    trigger = { kind: "initial" };
  } else if (
    triggerObject.kind === "human_input" ||
    triggerObject.kind === "recoverable_restart" ||
    triggerObject.kind === "continuation"
  ) {
    trigger = {
      kind: triggerObject.kind,
      eventRef: parseRef(triggerObject.eventRef, "InvocationEnvelope.trigger.eventRef", parseEventRef),
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
  if (serializedJsonByteLength(result) > MAX_SERIALIZED_JSON_BYTES) {
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
      kind: "human_input" | "recoverable_restart" | "continuation";
      eventRef: EventRef;
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

export type ConversationPublication = Publication<"conversation", ConversationRef>;
export type InputRequestPublication = Publication<"input_request", InputRequestRef>;
export type ArtifactPublication = Publication<"artifact", ArtifactRef>;
export type OutcomeSubmissionPublication = Publication<"outcome_submission", OutcomeSubmissionRef>;
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
  | "authority_facts_missing"
  | "contract_digest_mismatch"
  | "snapshot_content_digest_mismatch"
  | "invocation_snapshot_binding_mismatch"
  | "invocation_identity_mismatch"
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
  | "publication_receipt_missing"
  | "publication_receipt_mismatch"
  | "publication_authority_mismatch"
  | "publication_product_mismatch"
  | "cancellation_mismatch"
  | "terminal_event_mismatch"
  | "final_sequence_mismatch"
  | "exit_identity_mismatch"
  | "exit_reference_mismatch"
  | "exit_failure_mismatch";

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

export type DurableAcceptedEvent = Readonly<{
  eventId: EventId;
  idempotencyKey: IdempotencyKey;
  invocationId: InvocationId;
  sequence: number;
  fingerprint: ContentDigest;
  kind: RuntimeEventBody["kind"];
}>;

export type DurableAcceptedExit = Readonly<{
  invocationId: InvocationId;
  idempotencyKey: IdempotencyKey;
  finalSequence: number;
  fingerprint: ContentDigest;
  kind: RuntimeExit["kind"];
}>;

export type RuntimeDurableState = Readonly<{
  state: RuntimeLifecycleState;
  lastAcceptedSequence: number;
  acceptedEvents: readonly DurableAcceptedEvent[];
  acceptedExits: readonly DurableAcceptedExit[];
}>;

export type TrustedPublicationReceipt = Readonly<{
  workspaceRef: WorkspaceRef;
  actorRef: ActorRef;
  profileVersionRef: ProfileVersionRef;
  runId: RunId;
  invocationId: InvocationId;
  cancellationRef?: CancellationRef;
  productKind: AnyProductPublication["productKind"];
  productRef: AnyProductPublication["productRef"];
  operationAttemptRef: OperationAttemptRef;
  operationRef: OperationRef;
  applicationServiceRef: ApplicationServiceRef;
  gatewayReceiptRef: GatewayReceiptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  productEventRef: ProductEventRef;
}>;

export type RuntimeVerificationFacts = Readonly<{
  authority: TrustedRuntimeAuthority;
  lifecycle: RuntimeDurableState;
  lease: TrustedLeaseVerification;
  cancellation: TrustedCancellationVerification;
  checkpoint?: TrustedCheckpointVerification;
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
    receipt.cancellationRef === cancellationRef
  );
}

function verifyPublication(
  body: RuntimeEventBody,
  eventPath: string,
  snapshot: RunSnapshot,
  invocation: InvocationEnvelope,
  authority: TrustedRuntimeAuthority,
  trustedReceipts: readonly TrustedPublicationReceipt[],
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

  if (serializedJsonByteLength(publication) > snapshot.runtimePolicy.maxReceiptBytes) {
    addVerificationError(
      errors,
      "receipt_too_large",
      `${eventPath}.publication`,
      "Publication application receipt metadata exceeds the resolved snapshot receipt limit"
    );
  }
  const matchingReceipt = trustedReceipts.find((receipt) => receiptMatches(publication, receipt, snapshot, invocation));
  if (matchingReceipt === undefined) {
    const sameProduct = trustedReceipts.some(
      (receipt) => receipt.productKind === publication.productKind && receipt.productRef === publication.productRef
    );
    addVerificationError(
      errors,
      sameProduct ? "publication_authority_mismatch" : "publication_receipt_missing",
      `${eventPath}.publication`,
      sameProduct
        ? "The product receipt is not bound to the trusted workspace, actor, profile, run, invocation, or gateway facts"
        : "Applied product publication requires a matching trusted Plane application-service, gateway, and audit receipt"
    );
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
  const accepted = acceptedEvents.find((event) => event.eventId === trigger.eventRef);
  return accepted !== undefined && (trigger.kind !== "human_input" || accepted.kind === "input_request_observed");
}

function validateLifecycleFacts(lifecycle: RuntimeDurableState, errors: RuntimeVerificationError[]) {
  if (!Number.isInteger(lifecycle.lastAcceptedSequence) || lifecycle.lastAcceptedSequence < -1) {
    addVerificationError(
      errors,
      "authority_facts_missing",
      "trusted.lifecycle.lastAcceptedSequence",
      "Durable sequence must start at -1 or a non-negative integer"
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

export function verifyRuntimeExecution(input: RuntimeVerificationInput): RuntimeVerificationResult {
  const errors: RuntimeVerificationError[] = [];
  const { manifest, snapshot, invocation, events, exit, trusted } = input;
  if (
    !isValidatedContract(snapshot, "RunSnapshot") ||
    !isValidatedContract(invocation, "InvocationEnvelope") ||
    !events.every((event) => isValidatedContract(event, "RuntimeEvent")) ||
    !isValidatedContract(exit, "RuntimeExit")
  ) {
    addVerificationError(
      errors,
      "unparsed_contract_input",
      "input",
      "Runtime semantic verification accepts only parser-produced contract values"
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
  const seenEventIds = new Set<string>();
  const seenIdempotencyKeys = new Set<string>();
  const newEvents: DurableAcceptedEvent[] = [];
  let expectedSequence = trusted.lifecycle.lastAcceptedSequence + 1;
  let allEventsReplay = true;
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
      newEvents.push({
        eventId: event.eventId,
        idempotencyKey: event.idempotencyKey,
        invocationId: event.invocationId,
        sequence: event.sequence,
        fingerprint: eventFingerprint,
        kind: event.body.kind,
      });
    }
    if (
      serializedJsonByteLength(event) > MAX_SERIALIZED_JSON_BYTES ||
      serializedJsonByteLength(event) > snapshot.runtimePolicy.maxEventPayloadBytes
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
    verifyPublication(event.body, path, snapshot, invocation, trusted.authority, trusted.publicationReceipts, errors);
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
    return {
      ok: true,
      result: "idempotent_replay",
      state: exit.kind,
      finalSequence: exit.finalSequence,
      terminalEventCount,
      nextLifecycle: trusted.lifecycle,
    };
  }

  const nextLifecycle: RuntimeDurableState = {
    state: stateForExit(exit.kind),
    lastAcceptedSequence: Math.max(trusted.lifecycle.lastAcceptedSequence, ...newEvents.map((event) => event.sequence)),
    acceptedEvents: [...trusted.lifecycle.acceptedEvents, ...newEvents],
    acceptedExits: [
      ...trusted.lifecycle.acceptedExits,
      {
        invocationId: exit.invocationId,
        idempotencyKey: exit.idempotencyKey,
        finalSequence: exit.finalSequence,
        fingerprint: exitFingerprint,
        kind: exit.kind,
      },
    ],
  };
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

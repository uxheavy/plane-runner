import { createHash } from "node:crypto";

export const PLANE_AGENT_RUNTIME_PROTOCOL = "plane.agent-runtime/v1" as const;

export type PlaneAgentRuntimeProtocol = typeof PLANE_AGENT_RUNTIME_PROTOCOL;

declare const opaqueRefBrand: unique symbol;

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

export type RunSnapshot = Readonly<{
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

export type RunSnapshotContent = Omit<RunSnapshot, "contentDigest">;

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

const sha256 = (value: string): string => createHash("sha256").update(value, "utf8").digest("hex");

export function computeRunSnapshotContentDigest(snapshot: RunSnapshot | RunSnapshotContent): RunSnapshotContentDigest {
  return createRunSnapshotContentDigest(sha256(canonicalizeJson(withoutSnapshotContentDigest(snapshot))));
}

export function verifyRunSnapshotContentDigest(snapshot: RunSnapshot): boolean {
  return snapshot.contentDigest === computeRunSnapshotContentDigest(snapshot);
}

export function verifyInvocationSnapshotBinding(snapshot: RunSnapshot, invocation: InvocationEnvelope): boolean {
  return verifyRunSnapshotContentDigest(snapshot) && invocation.runSnapshotDigest === snapshot.contentDigest;
}

export function createRunSnapshot(
  input: Omit<RunSnapshot, "contractDigests" | "contentDigest">,
  manifest: ContractManifest
): RunSnapshot {
  const content: RunSnapshotContent = {
    ...input,
    contractDigests: contractDigestsFromManifest(manifest),
  };
  return freezeRunSnapshot({ ...content, contentDigest: computeRunSnapshotContentDigest(content) });
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

export type InvocationEnvelope = Readonly<{
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
      receiptRef: ReceiptRef;
      auditReceiptRef: AuditReceiptRef;
      productEventRef: ProductEventRef;
    }>;

export type ConversationPublication = Publication<"conversation", ConversationRef>;
export type InputRequestPublication = Publication<"input_request", InputRequestRef>;
export type ArtifactPublication = Publication<"artifact", ArtifactRef>;
export type OutcomeSubmissionPublication = Publication<"outcome_submission", OutcomeSubmissionRef>;
export type AnyProductPublication =
  | ConversationPublication
  | InputRequestPublication
  | ArtifactPublication
  | OutcomeSubmissionPublication;

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
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "blocker_observed";
      reason: BoundedText;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "cancellation_observed";
      reason: BoundedText;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "transcript_evidence_observed";
      payload: BoundedPayload;
      publication: Readonly<{ action: "observation_only" }>;
    }>;

export type RuntimeEvent = Readonly<{
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

export type RuntimeExit =
  | (RuntimeExitBase & Readonly<{ kind: "completed" }>)
  | (RuntimeExitBase & Readonly<{ kind: "waiting_for_input"; inputEventRef: EventRef }>)
  | (RuntimeExitBase & Readonly<{ kind: "failed" | "blocked" | "cancelled"; failure: RuntimeFailure }>);

export const MAX_SERIALIZED_JSON_BYTES = 1_048_576;

export type RuntimeVerificationErrorCode =
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
  | "event_correlation_mismatch"
  | "event_payload_too_large"
  | "artifact_too_large"
  | "receipt_too_large"
  | "publication_receipt_missing"
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
  isCancelled: boolean;
}>;

export type TrustedPublicationReceipt = Readonly<{
  productKind: AnyProductPublication["productKind"];
  productRef: AnyProductPublication["productRef"];
  operationAttemptRef: OperationAttemptRef;
  receiptRef: ReceiptRef;
  auditReceiptRef: AuditReceiptRef;
  productEventRef: ProductEventRef;
}>;

export type RuntimeVerificationFacts = Readonly<{
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
  state: RuntimeExecutionState;
  finalSequence: number;
  terminalEventCount: number;
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

function verifyPublication(
  body: RuntimeEventBody,
  eventPath: string,
  snapshot: RunSnapshot,
  trustedReceipts: readonly TrustedPublicationReceipt[],
  errors: RuntimeVerificationError[]
) {
  if (
    body.kind !== "conversation_publication_observed" &&
    body.kind !== "input_request_observed" &&
    body.kind !== "artifact_observed" &&
    body.kind !== "outcome_submission_observed"
  ) {
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

  if (!publicationIsApplied(publication)) {
    return;
  }

  if (serializedJsonByteLength(publication) > snapshot.runtimePolicy.maxReceiptBytes) {
    addVerificationError(
      errors,
      "receipt_too_large",
      `${eventPath}.publication`,
      "Publication receipt metadata exceeds the resolved snapshot receipt limit"
    );
  }

  const receiptMatches = trustedReceipts.some(
    (receipt) =>
      receipt.productKind === publication.productKind &&
      receipt.productRef === publication.productRef &&
      receipt.operationAttemptRef === publication.operationAttemptRef &&
      receipt.receiptRef === publication.receiptRef &&
      receipt.auditReceiptRef === publication.auditReceiptRef &&
      receipt.productEventRef === publication.productEventRef
  );
  if (!receiptMatches) {
    addVerificationError(
      errors,
      "publication_receipt_missing",
      `${eventPath}.publication`,
      "Applied product publication requires a matching trusted operation and audit receipt"
    );
  }
}

function verifyTerminalEvents(
  events: readonly RuntimeEvent[],
  exit: RuntimeExit,
  cancellationIsTrusted: boolean,
  errors: RuntimeVerificationError[]
) {
  const terminalEvents = events.filter(
    ({ body }) =>
      body.kind === "outcome_submission_observed" ||
      body.kind === "failure_observed" ||
      body.kind === "blocker_observed" ||
      body.kind === "cancellation_observed"
  );
  const count = (kind: RuntimeEventBody["kind"]) => events.filter((event) => event.body.kind === kind).length;

  if (exit.kind === "completed") {
    const outcomes = events.filter((event) => event.body.kind === "outcome_submission_observed");
    const outcome = outcomes[0];
    if (
      terminalEvents.length !== 1 ||
      outcomes.length !== 1 ||
      outcome === undefined ||
      outcome.body.kind !== "outcome_submission_observed" ||
      !publicationIsApplied(outcome.body.publication)
    ) {
      addVerificationError(
        errors,
        "terminal_event_mismatch",
        "exit.kind",
        "A completed invocation requires exactly one receipt-correlated outcome submission event"
      );
    }
  } else if (exit.kind === "waiting_for_input") {
    const inputRequests = events.filter((event) => event.body.kind === "input_request_observed");
    if (terminalEvents.length !== 0 || inputRequests.length !== 1) {
      addVerificationError(
        errors,
        "terminal_event_mismatch",
        "exit.kind",
        "A waiting invocation requires one published input request and no terminal event"
      );
    } else if (inputRequests[0].eventId !== exit.inputEventRef) {
      addVerificationError(
        errors,
        "exit_reference_mismatch",
        "exit.inputEventRef",
        "The waiting exit must reference the input-request event"
      );
    } else if (
      inputRequests[0].body.kind !== "input_request_observed" ||
      !publicationIsApplied(inputRequests[0].body.publication)
    ) {
      addVerificationError(
        errors,
        "terminal_event_mismatch",
        "events",
        "The waiting input request must have a receipt-correlated product publication"
      );
    }
  } else if (exit.kind === "failed") {
    const failures = events.filter((event) => event.body.kind === "failure_observed");
    if (
      terminalEvents.length !== 1 ||
      failures.length !== 1 ||
      failures[0] === undefined ||
      failures[0].body.kind !== "failure_observed" ||
      failures[0].body.failure.code !== exit.failure.code
    ) {
      addVerificationError(
        errors,
        "exit_failure_mismatch",
        "exit.failure",
        "A failed exit must have one matching failure observation"
      );
    }
  } else if (exit.kind === "blocked") {
    if (terminalEvents.length !== 1 || count("blocker_observed") !== 1) {
      addVerificationError(
        errors,
        "terminal_event_mismatch",
        "exit.kind",
        "A blocked exit must have exactly one blocker observation"
      );
    }
  } else if (exit.kind === "cancelled") {
    if (!cancellationIsTrusted || exit.failure.code !== "cancelled") {
      addVerificationError(
        errors,
        "cancellation_mismatch",
        "exit",
        "A cancelled exit requires trusted cancellation and a cancelled failure code"
      );
    }
    if (terminalEvents.length !== 1 || count("cancellation_observed") !== 1) {
      addVerificationError(
        errors,
        "terminal_event_mismatch",
        "exit.kind",
        "A cancelled exit must have exactly one cancellation observation"
      );
    }
  }

  return terminalEvents.length;
}

export function verifyRuntimeExecution(input: RuntimeVerificationInput): RuntimeVerificationResult {
  const errors: RuntimeVerificationError[] = [];
  const { manifest, snapshot, invocation, events, exit, trusted } = input;
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
      "Snapshot content digest does not match canonical content excluding the digest field"
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

  if (
    invocation.workspaceRef !== snapshot.workspaceRef ||
    invocation.actorRef !== snapshot.actorRef ||
    invocation.runId !== snapshot.runId
  ) {
    addVerificationError(
      errors,
      "invocation_identity_mismatch",
      "invocation",
      "Invocation workspace, actor, and run must match the resolved snapshot"
    );
  }

  if (invocation.trigger.kind === "initial") {
    if (invocation.checkpointRef !== undefined) {
      addVerificationError(
        errors,
        "initial_checkpoint_forbidden",
        "invocation.checkpointRef",
        "Initial invocations cannot carry a continuation checkpoint"
      );
    }
  } else {
    if (!invocation.newContextEventRefs.includes(invocation.trigger.eventRef)) {
      addVerificationError(
        errors,
        "invocation_identity_mismatch",
        "invocation.newContextEventRefs",
        "Continuation trigger event must be included as new context"
      );
    }
    const checkpointRequired =
      invocation.trigger.kind === "continuation" || invocation.trigger.kind === "recoverable_restart";
    if (checkpointRequired && invocation.checkpointRef === undefined) {
      addVerificationError(
        errors,
        "continuation_checkpoint_missing",
        "invocation.checkpointRef",
        "Continuation and restart invocations require a checkpoint"
      );
    }
  }

  if (invocation.checkpointRef !== undefined) {
    if (trusted.checkpoint?.checkpointRef !== invocation.checkpointRef || !trusted.checkpoint.isVerified) {
      addVerificationError(
        errors,
        "checkpoint_untrusted",
        "trusted.checkpoint",
        "A checkpoint is usable only when the trusted host has verified its identity and safety"
      );
    }
  }
  if (trusted.lease.leaseId !== invocation.lease.leaseId || !trusted.lease.isValid) {
    addVerificationError(
      errors,
      "lease_untrusted",
      "trusted.lease",
      "The invocation lease must be checked by the trusted host before execution"
    );
  }

  const totalBudget = snapshot.totalBudget;
  if (!sameBudgetOrLower(invocation.remainingBudget, totalBudget)) {
    addVerificationError(
      errors,
      "budget_increased",
      "invocation.remainingBudget",
      "Remaining invocation budget cannot exceed the run total budget"
    );
  }
  if (invocation.trigger.kind !== "initial") {
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
  }

  const seenSequences = new Set<number>();
  const seenEventIds = new Set<string>();
  const seenIdempotencyKeys = new Set<string>();
  events.forEach((event, index) => {
    const path = `events[${index}]`;
    if (
      event.workspaceRef !== snapshot.workspaceRef ||
      event.actorRef !== snapshot.actorRef ||
      event.runId !== snapshot.runId ||
      event.invocationId !== invocation.invocationId
    ) {
      addVerificationError(
        errors,
        "event_identity_mismatch",
        path,
        "Event identity must match the verified invocation and snapshot"
      );
    }
    if (event.correlationId !== invocation.correlationId || event.causationRef !== invocation.causationRef) {
      addVerificationError(
        errors,
        "event_correlation_mismatch",
        `${path}.correlationId`,
        "Event correlation and causation must remain bound to the invocation"
      );
    }
    if (event.sequence !== index || seenSequences.has(event.sequence)) {
      addVerificationError(
        errors,
        "event_sequence_invalid",
        `${path}.sequence`,
        "Events must be ordered once with contiguous sequence numbers starting at zero"
      );
    }
    if (seenEventIds.has(event.eventId)) {
      addVerificationError(
        errors,
        "event_duplicate",
        `${path}.eventId`,
        "Event IDs must be unique within one invocation"
      );
    }
    if (seenIdempotencyKeys.has(event.idempotencyKey)) {
      addVerificationError(
        errors,
        "event_idempotency_duplicate",
        `${path}.idempotencyKey`,
        "Event idempotency keys must be unique within one invocation"
      );
    }
    seenSequences.add(event.sequence);
    seenEventIds.add(event.eventId);
    seenIdempotencyKeys.add(event.idempotencyKey);

    if (
      serializedJsonByteLength(event) > MAX_SERIALIZED_JSON_BYTES ||
      serializedJsonByteLength(event.body) > snapshot.runtimePolicy.maxEventPayloadBytes
    ) {
      addVerificationError(
        errors,
        "event_payload_too_large",
        `${path}.body`,
        "Serialized UTF-8 event bytes must fit both the global envelope limit and the resolved snapshot payload limit"
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
    verifyPublication(event.body, path, snapshot, trusted.publicationReceipts, errors);
  });

  const expectedFinalSequence = events.length === 0 ? 0 : events.length - 1;
  if (exit.finalSequence !== expectedFinalSequence) {
    addVerificationError(
      errors,
      "final_sequence_mismatch",
      "exit.finalSequence",
      "Exit finalSequence must equal the last verified event sequence"
    );
  }
  if (
    exit.workspaceRef !== invocation.workspaceRef ||
    exit.actorRef !== invocation.actorRef ||
    exit.runId !== invocation.runId ||
    exit.invocationId !== invocation.invocationId ||
    exit.idempotencyKey !== invocation.idempotencyKey ||
    exit.correlationId !== invocation.correlationId ||
    exit.causationRef !== invocation.causationRef
  ) {
    addVerificationError(
      errors,
      "exit_identity_mismatch",
      "exit",
      "Exit identity and correlation must match the invocation"
    );
  }
  if (trusted.cancellation.isCancelled && exit.kind !== "cancelled") {
    addVerificationError(
      errors,
      "cancellation_mismatch",
      "exit.kind",
      "A trusted cancellation cannot finish as a non-cancelled exit"
    );
  }

  const terminalEventCount = verifyTerminalEvents(events, exit, trusted.cancellation.isCancelled, errors);
  if (errors.length > 0) {
    return { ok: false, errors };
  }

  return { ok: true, state: exit.kind, finalSequence: exit.finalSequence, terminalEventCount };
}

export const runtimeSemanticVerifier: RuntimeSemanticVerifier = {
  verify: verifyRuntimeExecution,
};

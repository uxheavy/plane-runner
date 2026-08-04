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
export type EventId = OpaqueRef<"event-id">;
export type CorrelationId = OpaqueRef<"correlation">;
export type IdempotencyKey = OpaqueRef<"idempotency">;
export type CausationRef = OpaqueRef<"causation">;
export type CancellationRef = OpaqueRef<"cancellation">;
export type CheckpointRef = OpaqueRef<"checkpoint">;
export type LeaseId = OpaqueRef<"lease">;
export type OperationAttemptRef = OpaqueRef<"operation-attempt">;
export type ReceiptRef = OpaqueRef<"receipt">;
export type ProductEventRef = OpaqueRef<"product-event">;
export type ArtifactRef = OpaqueRef<"artifact">;
export type PayloadRef = OpaqueRef<"payload">;
export type ContractDigest = OpaqueRef<"contract-digest">;
export type ContentDigest = OpaqueRef<"content-digest">;

const OPAQUE_REF_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._~:/-]{0,127}$/;
const DIGEST_PATTERN = /^[a-f0-9]{64}$/;

export function createOpaqueRef<Tag extends string>(value: string): OpaqueRef<Tag> {
  if (!OPAQUE_REF_PATTERN.test(value)) {
    throw new TypeError("Opaque references must be 1-128 printable identifier characters");
  }

  return value as OpaqueRef<Tag>;
}

export function createContractDigest(value: string): ContractDigest {
  if (!DIGEST_PATTERN.test(value)) {
    throw new TypeError("Contract digests must be lowercase SHA-256 hex strings");
  }

  return value as ContractDigest;
}

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
}>;

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
  runSnapshotDigest: ContractDigest;
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

export type PublicationBoundary =
  | Readonly<{ action: "observation_only" }>
  | Readonly<{
      action: "explicit_plane_publication_requested";
      operationAttemptRef: OperationAttemptRef;
    }>
  | Readonly<{
      action: "plane_publication_receipt_observed";
      operationAttemptRef: OperationAttemptRef;
      receiptRef: ReceiptRef;
      productEventRef: ProductEventRef;
    }>;

export type RuntimeEventBody =
  | Readonly<{
      kind: "progress_observed";
      payload: BoundedPayload;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "conversation_publication_observed";
      payload: BoundedPayload;
      publication: Exclude<PublicationBoundary, { action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "input_request_observed";
      question: BoundedText;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "artifact_observed";
      artifact: ArtifactReference;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "usage_observed";
      usage: RuntimeUsage;
      publication: Readonly<{ action: "observation_only" }>;
    }>
  | Readonly<{
      kind: "outcome_submission_observed";
      payload: BoundedPayload;
      publication: Exclude<PublicationBoundary, { action: "observation_only" }>;
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

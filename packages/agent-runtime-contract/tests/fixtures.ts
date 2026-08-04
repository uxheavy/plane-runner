import {
  createContractDigest,
  createOpaqueRef,
  freezeRunSnapshot,
  type BoundedPayload,
  type ContentDigest,
  type ContractDigest,
  type InvocationEnvelope,
  type RunSnapshot,
  type RuntimeBudget,
  type RuntimeEvent,
  type RuntimeEventBody,
  type RuntimeExit,
} from "../src";

export const ref = <Tag extends string>(value: string) => createOpaqueRef<Tag>(value);

export const digest = (character = "a"): ContractDigest => createContractDigest(character.repeat(64));
export const contentDigest = (character = "b"): ContentDigest => ref<"content-digest">(character.repeat(64));

export const workspaceRef = ref<"workspace">("workspace-1");
export const actorRef = ref<"actor">("actor-1");
export const runId = ref<"run">("run-1");
export const invocationId = ref<"invocation">("invocation-1");
export const eventRef = ref<"event">("event-1");
export const correlationId = ref<"correlation">("correlation-1");
export const causationRef = ref<"causation">("causation-1");
export const idempotencyKey = ref<"idempotency">("idempotency-1");

export const snapshot: RunSnapshot = freezeRunSnapshot({
  protocol: "plane.agent-runtime/v1",
  workspaceRef,
  runId,
  assignment: {
    assignmentRef: ref<"assignment">("assignment-1"),
    revision: "revision-1",
    targetRef: ref<"target">("issue-1"),
    objective: "Produce the requested result.",
    acceptanceCriteria: ["The result is reviewable."],
  },
  actorRef,
  profile: {
    profileRef: ref<"profile-version">("profile-1"),
    revision: "revision-1",
    role: "worker",
    behavioralPrompt: "Complete the assignment within the supplied Plane contract.",
  },
  context: [
    {
      contextRef: ref<"context">("context-1"),
      revision: "revision-1",
      contentDigest: contentDigest(),
    },
  ],
  toolCatalog: {
    catalogDigest: contentDigest("c"),
    eagerOperations: [
      {
        operationRef: ref<"operation">("search_workspace"),
        schemaDigest: contentDigest("d"),
        disclosure: "eager",
      },
    ],
  },
  runtimePolicy: {
    model: { provider: "test-provider", model: "test-model" },
    adapter: "deterministic-test-adapter",
    isolation: "single-invocation",
    maxEventPayloadBytes: 4096,
    maxArtifactBytes: 65536,
    maxReceiptBytes: 4096,
  },
  totalBudget: { inputTokens: 1000, outputTokens: 500, durationMs: 60000 },
  contractDigests: {
    runSnapshot: digest("e"),
    invocationEnvelope: digest("f"),
    runtimeEvent: digest("1"),
    runtimeExit: digest("2"),
  },
});

export const budget = (inputTokens: number, outputTokens: number, durationMs: number): RuntimeBudget => ({
  inputTokens,
  outputTokens,
  durationMs,
});

export const envelope = (remainingBudget: RuntimeBudget = budget(1000, 500, 60000)): InvocationEnvelope => ({
  protocol: "plane.agent-runtime/v1",
  workspaceRef,
  actorRef,
  runId,
  invocationId,
  runSnapshotDigest: digest("e"),
  trigger: { kind: "initial" },
  newContextEventRefs: [],
  remainingBudget,
  lease: {
    leaseId: ref<"lease">("lease-1"),
    expiresAt: "2026-08-04T10:00:00Z",
    renewAfterMs: 10000,
  },
  cancellationRef: ref<"cancellation">("cancellation-1"),
  causationRef,
  correlationId,
  idempotencyKey,
});

export const inlinePayload = (text = "An observation."): BoundedPayload => ({
  kind: "inline_text",
  contentType: "text/plain",
  text,
});

export const event = (body: RuntimeEventBody, sequence = 0): RuntimeEvent => ({
  protocol: "plane.agent-runtime/v1",
  trust: "untrusted",
  workspaceRef,
  actorRef,
  runId,
  invocationId,
  sequence,
  eventId: ref<"event-id">(`event-id-${sequence}`),
  idempotencyKey,
  correlationId,
  causationRef,
  observedAt: "2026-08-04T10:00:00Z",
  body,
});

export const observationBody = (text = "An observation."): RuntimeEventBody => ({
  kind: "progress_observed",
  payload: inlinePayload(text),
  publication: { action: "observation_only" },
});

export const publicationBody = (): RuntimeEventBody => ({
  kind: "conversation_publication_observed",
  payload: inlinePayload("A proposed Plane publication."),
  publication: {
    action: "explicit_plane_publication_requested",
    operationAttemptRef: ref<"operation-attempt">("operation-attempt-1"),
  },
});

const exitBase = {
  protocol: "plane.agent-runtime/v1" as const,
  authority: "runtime_evidence_only" as const,
  workspaceRef,
  actorRef,
  runId,
  invocationId,
  finalSequence: 0,
  idempotencyKey,
  correlationId,
  causationRef,
};

export const exits: RuntimeExit[] = [
  { ...exitBase, kind: "completed" },
  { ...exitBase, kind: "waiting_for_input", inputEventRef: eventRef },
  {
    ...exitBase,
    kind: "failed",
    failure: { code: "runtime_error", message: "The runtime stopped.", retryable: true },
  },
  {
    ...exitBase,
    kind: "blocked",
    failure: { code: "invalid_continuation", message: "Continuation is unsafe.", retryable: false },
  },
  {
    ...exitBase,
    kind: "cancelled",
    failure: { code: "cancelled", message: "Cancellation was requested.", retryable: false },
  },
];

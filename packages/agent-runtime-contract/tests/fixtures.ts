import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  createActorRef,
  createAssignmentRef,
  createAuditReceiptRef,
  createCancellationRef,
  createCausationRef,
  createContentDigest,
  createContextRef,
  createContractDigest,
  createCorrelationId,
  createConversationRef,
  createEventRef,
  createIdempotencyKey,
  createInputRequestRef,
  createInvocationId,
  createLeaseId,
  createOperationAttemptRef,
  createOperationRef,
  createOutcomeSubmissionRef,
  createProductEventRef,
  createProfileVersionRef,
  createReceiptRef,
  createRunId,
  createRunSnapshot,
  createTargetRef,
  createWorkspaceRef,
  parseContractManifest,
  type BoundedPayload,
  type ContractDigest,
  type ContractManifest,
  type InvocationEnvelope,
  type RunSnapshot,
  type RuntimeBudget,
  type RuntimeEvent,
  type RuntimeEventBody,
  type RuntimeExit,
} from "../src";

const manifestDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));

export const manifest: ContractManifest = parseContractManifest(
  JSON.parse(readFileSync(`${manifestDirectory}/manifest.json`, "utf8"))
);

export const digest = (character = "a"): ContractDigest => createContractDigest(character.repeat(64));
export const contentDigest = (character = "b") => createContentDigest(character.repeat(64));

export const workspaceRef = createWorkspaceRef("workspace-1");
export const actorRef = createActorRef("actor-1");
export const runId = createRunId("run-1");
export const invocationId = createInvocationId("invocation-1");
export const eventRef = createEventRef("event-1");
export const correlationId = createCorrelationId("correlation-1");
export const causationRef = createCausationRef("causation-1");
export const idempotencyKey = createIdempotencyKey("idempotency-1");

export const snapshot: RunSnapshot = createRunSnapshot(
  {
    protocol: "plane.agent-runtime/v1",
    workspaceRef,
    runId,
    assignment: {
      assignmentRef: createAssignmentRef("assignment-1"),
      revision: "revision-1",
      targetRef: createTargetRef("issue-1"),
      objective: "Produce the requested result.",
      acceptanceCriteria: ["The result is reviewable."],
    },
    actorRef,
    profile: {
      profileRef: createProfileVersionRef("profile-1"),
      revision: "revision-1",
      role: "worker",
      behavioralPrompt: "Complete the assignment within the supplied Plane contract.",
    },
    context: [
      {
        contextRef: createContextRef("context-1"),
        revision: "revision-1",
        contentDigest: contentDigest(),
      },
    ],
    toolCatalog: {
      catalogDigest: contentDigest("c"),
      eagerOperations: [
        {
          operationRef: createOperationRef("search_workspace"),
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
  },
  manifest
);

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
  runSnapshotDigest: snapshot.contentDigest,
  trigger: { kind: "initial" },
  newContextEventRefs: [],
  remainingBudget,
  lease: {
    leaseId: createLeaseId("lease-1"),
    expiresAt: "2026-08-04T10:00:00Z",
    renewAfterMs: 10000,
  },
  cancellationRef: createCancellationRef("cancellation-1"),
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
  eventId: createEventRef(`event-id-${sequence}`),
  idempotencyKey: createIdempotencyKey(`event-idempotency-${sequence}`),
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
    action: "proposal",
    productKind: "conversation",
    productRef: createConversationRef("conversation-1"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-1"),
  },
});

export const appliedConversationBody = (): RuntimeEventBody => ({
  kind: "conversation_publication_observed",
  payload: inlinePayload("A visible Plane publication."),
  publication: {
    action: "applied",
    productKind: "conversation",
    productRef: createConversationRef("conversation-1"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-1"),
    receiptRef: createReceiptRef("receipt-1"),
    auditReceiptRef: createAuditReceiptRef("audit-1"),
    productEventRef: createProductEventRef("product-event-1"),
  },
});

export const appliedInputRequestBody = (requestId = "input-request-1"): RuntimeEventBody => ({
  kind: "input_request_observed",
  question: "Please provide the missing detail.",
  publication: {
    action: "applied",
    productKind: "input_request",
    productRef: createInputRequestRef(requestId),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-input"),
    receiptRef: createReceiptRef("receipt-input"),
    auditReceiptRef: createAuditReceiptRef("audit-input"),
    productEventRef: createProductEventRef("product-event-input"),
  },
});

export const appliedOutcomeBody = (): RuntimeEventBody => ({
  kind: "outcome_submission_observed",
  payload: inlinePayload("The completed outcome."),
  publication: {
    action: "applied",
    productKind: "outcome_submission",
    productRef: createOutcomeSubmissionRef("outcome-1"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-outcome"),
    receiptRef: createReceiptRef("receipt-outcome"),
    auditReceiptRef: createAuditReceiptRef("audit-outcome"),
    productEventRef: createProductEventRef("product-event-outcome"),
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

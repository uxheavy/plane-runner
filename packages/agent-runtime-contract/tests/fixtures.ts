import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  createActorRef,
  createArtifactRef,
  createApplicationServiceRef,
  createAuthorizationReceiptRef,
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
  createGatewayReceiptRef,
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
  createRunSnapshot as createRunSnapshotWire,
  createTargetRef,
  createWorkspaceRef,
  computeTrustedHumanInputAnswerDigest as computeTrustedHumanInputAnswerDigestWire,
  parseContractManifest as parseContractManifestWire,
  parseInvocationEnvelope as parseInvocationEnvelopeWire,
  parseRuntimeEvent as parseRuntimeEventWire,
  parseRuntimeExit as parseRuntimeExitWire,
  type BoundedPayload,
  type ContractDigest,
  type ContractManifest,
  type InvocationEnvelope,
  type RunSnapshot,
  type RuntimeBudget,
  type RuntimeEvent,
  type RuntimeEventBody,
  type RuntimeExit,
  type TrustedHumanInputAnswer,
} from "../src";

const toWire = (value: unknown): string => (typeof value === "string" ? value : JSON.stringify(value));
const createRunSnapshot = (input: unknown, manifestValue: unknown) =>
  createRunSnapshotWire(toWire(input), toWire(manifestValue));
const parseInvocationEnvelope = (value: unknown) => parseInvocationEnvelopeWire(toWire(value));
const parseRuntimeEvent = (value: unknown) => parseRuntimeEventWire(toWire(value));
const parseRuntimeExit = (value: unknown) => parseRuntimeExitWire(toWire(value));
const computeTrustedHumanInputAnswerDigest = (value: unknown) =>
  computeTrustedHumanInputAnswerDigestWire(toWire(value));

const manifestDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));

export const manifest: ContractManifest = parseContractManifestWire(
  readFileSync(`${manifestDirectory}/manifest.json`, "utf8")
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
          inputSchema: {
            type: "object",
            additionalProperties: false,
            required: ["query"],
            properties: {
              query: { type: "string", maxLength: 255 },
              limit: { type: "integer", minimum: 1, maximum: 50 },
              cursor: { type: "string", maxLength: 32 },
            },
          },
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

export const envelope = (remainingBudget: RuntimeBudget = budget(1000, 500, 60000)): InvocationEnvelope =>
  parseInvocationEnvelope({
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

export const event = (body: RuntimeEventBody, sequence = 0): RuntimeEvent =>
  parseRuntimeEvent({
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
    operationRef: createOperationRef("publish-conversation"),
    applicationServiceRef: createApplicationServiceRef("conversation-service"),
    gatewayReceiptRef: createGatewayReceiptRef("gateway-conversation"),
    receiptRef: createReceiptRef("receipt-1"),
    auditReceiptRef: createAuditReceiptRef("audit-1"),
    productEventRef: createProductEventRef("product-event-1"),
  },
});

export const appliedArtifactBody = (): RuntimeEventBody => ({
  kind: "artifact_observed",
  artifact: {
    artifactRef: createArtifactRef("artifact-1"),
    contentDigest: contentDigest("e"),
    mediaType: "text/plain",
    sizeBytes: 1,
  },
  publication: {
    action: "applied",
    productKind: "artifact",
    productRef: createArtifactRef("artifact-1"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-artifact"),
    operationRef: createOperationRef("publish-artifact"),
    applicationServiceRef: createApplicationServiceRef("artifact-service"),
    gatewayReceiptRef: createGatewayReceiptRef("gateway-artifact"),
    receiptRef: createReceiptRef("receipt-artifact"),
    auditReceiptRef: createAuditReceiptRef("audit-artifact"),
    productEventRef: createProductEventRef("product-event-artifact"),
  },
});

export const proposalArtifactBody = (): RuntimeEventBody => ({
  kind: "artifact_observed",
  artifact: {
    artifactRef: createArtifactRef("artifact-proposal"),
    contentDigest: contentDigest("f"),
    mediaType: "text/plain",
    sizeBytes: 1,
  },
  publication: {
    action: "proposal",
    productKind: "artifact",
    productRef: createArtifactRef("artifact-proposal"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-artifact-proposal"),
  },
});

export const observationUsageBody = (): RuntimeEventBody => ({
  kind: "usage_observed",
  usage: { inputTokens: 1, outputTokens: 2, durationMs: 3 },
  publication: { action: "observation_only" },
});

export const transcriptEvidenceBody = (): RuntimeEventBody => ({
  kind: "transcript_evidence_observed",
  payload: inlinePayload("Transcript evidence."),
  publication: { action: "observation_only" },
});

export const appliedInputRequestBody = (requestId = "input-request-1"): RuntimeEventBody => ({
  kind: "input_request_observed",
  question: "Please provide the missing detail.",
  publication: {
    action: "applied",
    productKind: "input_request",
    productRef: createInputRequestRef(requestId),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-" + requestId),
    operationRef: createOperationRef("request-input-" + requestId),
    applicationServiceRef: createApplicationServiceRef("input-service-" + requestId),
    gatewayReceiptRef: createGatewayReceiptRef("gateway-input-" + requestId),
    receiptRef: createReceiptRef("receipt-input-" + requestId),
    auditReceiptRef: createAuditReceiptRef("audit-input-" + requestId),
    productEventRef: createProductEventRef("product-event-input-" + requestId),
  },
});

export const proposalInputRequestBody = (): RuntimeEventBody => ({
  kind: "input_request_observed",
  question: "Please provide the missing detail.",
  publication: {
    action: "proposal",
    productKind: "input_request",
    productRef: createInputRequestRef("input-request-proposal"),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-input-proposal"),
  },
});

export const trustedHumanInputAnswer = (
  invocation: InvocationEnvelope,
  requestId = "input-request-1",
  answerEventId = "human-answer-1"
): TrustedHumanInputAnswer => {
  const fact = {
    answerEventRef: createEventRef(answerEventId),
    inputRequestRef: createInputRequestRef(requestId),
    responderPrincipal: { kind: "human_user" as const, planePrincipalId: createActorRef("human-1") },
    workspaceRef,
    runId,
    authorizationReceiptRef: createAuthorizationReceiptRef("authorization-" + answerEventId),
    applicationServiceRef: createApplicationServiceRef("answer-" + answerEventId),
    gatewayReceiptRef: createGatewayReceiptRef("answer-" + answerEventId),
    receiptRef: createReceiptRef("answer-" + answerEventId),
    auditReceiptRef: createAuditReceiptRef("answer-" + answerEventId),
    correlationId: invocation.correlationId,
    causationRef: invocation.causationRef,
    payloadDigest: contentDigest("a"),
  } satisfies Omit<TrustedHumanInputAnswer, "answerFactDigest">;
  return { ...fact, answerFactDigest: computeTrustedHumanInputAnswerDigest(fact) };
};

export const appliedOutcomeBody = (suffix = "outcome-1"): RuntimeEventBody => ({
  kind: "outcome_submission_observed",
  payload: inlinePayload("The completed outcome."),
  publication: {
    action: "applied",
    productKind: "outcome_submission",
    productRef: createOutcomeSubmissionRef(suffix),
    operationAttemptRef: createOperationAttemptRef("operation-attempt-" + suffix),
    operationRef: createOperationRef("submit-" + suffix),
    applicationServiceRef: createApplicationServiceRef("outcome-service-" + suffix),
    gatewayReceiptRef: createGatewayReceiptRef("gateway-" + suffix),
    receiptRef: createReceiptRef("receipt-" + suffix),
    auditReceiptRef: createAuditReceiptRef("audit-" + suffix),
    productEventRef: createProductEventRef("product-event-" + suffix),
  },
});

const terminalPublicationFields = (suffix: string) => ({
  operationAttemptRef: createOperationAttemptRef(`operation-attempt-${suffix}`),
  operationRef: createOperationRef(`terminal-${suffix}`),
  applicationServiceRef: createApplicationServiceRef(`terminal-${suffix}`),
  gatewayReceiptRef: createGatewayReceiptRef(`terminal-${suffix}`),
  receiptRef: createReceiptRef(`terminal-${suffix}`),
  auditReceiptRef: createAuditReceiptRef(`terminal-${suffix}`),
  productEventRef: createProductEventRef(`terminal-${suffix}`),
});

export const appliedFailureBody = (): RuntimeEventBody => ({
  kind: "failure_observed",
  failure: { code: "runtime_error", message: "The runtime stopped.", retryable: true },
  publication: {
    action: "applied",
    productKind: "run_failure",
    productRef: createProductEventRef("terminal-failure"),
    ...terminalPublicationFields("failure"),
  },
});

export const appliedBlockerBody = (): RuntimeEventBody => ({
  kind: "blocker_observed",
  reason: "The runtime is blocked.",
  publication: {
    action: "applied",
    productKind: "run_blocker",
    productRef: createProductEventRef("terminal-blocker"),
    ...terminalPublicationFields("blocker"),
  },
});

export const appliedCancellationBody = (): RuntimeEventBody => ({
  kind: "cancellation_observed",
  reason: "Cancelled by Plane.",
  cancellationRef: createCancellationRef("cancellation-1"),
  publication: {
    action: "applied",
    productKind: "run_cancellation",
    productRef: createProductEventRef("terminal-cancellation"),
    ...terminalPublicationFields("cancellation"),
    cancellationRef: createCancellationRef("cancellation-1"),
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
  parseRuntimeExit({ ...exitBase, kind: "completed" }),
  parseRuntimeExit({ ...exitBase, kind: "waiting_for_input", inputEventRef: eventRef }),
  parseRuntimeExit({
    ...exitBase,
    kind: "failed",
    failure: { code: "runtime_error", message: "The runtime stopped.", retryable: true },
  }),
  parseRuntimeExit({
    ...exitBase,
    kind: "blocked",
    failure: { code: "invalid_continuation", message: "Continuation is unsafe.", retryable: false },
  }),
  parseRuntimeExit({
    ...exitBase,
    kind: "cancelled",
    failure: { code: "cancelled", message: "Cancellation was requested.", retryable: false },
  }),
];

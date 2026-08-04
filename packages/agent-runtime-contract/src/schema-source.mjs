const protocol = "plane.agent-runtime/v1";
const draft = "https://json-schema.org/draft/2020-12/schema";

const ref = (name) => ({ $ref: `#/$defs/${name}` });
const opaque = (kind) => ({ ...ref("opaqueRef"), "x-plane-opaque-kind": kind });
const digest = (kind) => ({ ...ref("digest"), "x-plane-opaque-kind": kind });

const definitions = {
  opaqueRef: {
    type: "string",
    minLength: 1,
    maxLength: 128,
    pattern: "^[A-Za-z0-9][A-Za-z0-9._~:/-]{0,127}$",
  },
  digest: {
    type: "string",
    pattern: "^[a-f0-9]{64}$",
  },
  boundedText: {
    type: "string",
    minLength: 1,
    maxLength: 4096,
  },
  boundedPrompt: {
    type: "string",
    minLength: 1,
    maxLength: 32768,
  },
  boundedToken: {
    type: "string",
    minLength: 1,
    maxLength: 256,
  },
  timestamp: {
    type: "string",
    minLength: 1,
    maxLength: 64,
  },
  nonNegativeInteger: {
    type: "integer",
    minimum: 0,
    maximum: 2147483647,
  },
  boundedByteCount: {
    type: "integer",
    minimum: 0,
    maximum: 1048576,
  },
  runtimeFailure: {
    type: "object",
    additionalProperties: false,
    required: ["code", "message", "retryable"],
    properties: {
      code: {
        enum: ["runtime_error", "lease_expired", "invalid_continuation", "budget_exhausted", "cancelled"],
      },
      message: ref("boundedText"),
      retryable: { type: "boolean" },
    },
  },
  runtimeUsage: {
    type: "object",
    additionalProperties: false,
    required: ["inputTokens", "outputTokens", "durationMs"],
    properties: {
      inputTokens: ref("nonNegativeInteger"),
      outputTokens: ref("nonNegativeInteger"),
      durationMs: ref("nonNegativeInteger"),
    },
  },
  runtimeBudget: {
    type: "object",
    additionalProperties: false,
    required: ["inputTokens", "outputTokens", "durationMs"],
    properties: {
      inputTokens: ref("nonNegativeInteger"),
      outputTokens: ref("nonNegativeInteger"),
      durationMs: ref("nonNegativeInteger"),
    },
  },
  boundedPayload: {
    oneOf: [
      {
        type: "object",
        additionalProperties: false,
        required: ["kind", "contentType", "text"],
        properties: {
          kind: { const: "inline_text" },
          contentType: { const: "text/plain" },
          text: ref("boundedText"),
        },
      },
      {
        type: "object",
        additionalProperties: false,
        required: ["kind", "payloadRef", "contentType", "contentDigest", "sizeBytes"],
        properties: {
          kind: { const: "payload_ref" },
          payloadRef: opaque("payload"),
          contentType: ref("boundedToken"),
          contentDigest: digest("content"),
          sizeBytes: ref("boundedByteCount"),
        },
      },
    ],
  },
  artifactReference: {
    type: "object",
    additionalProperties: false,
    required: ["artifactRef", "contentDigest", "mediaType", "sizeBytes"],
    properties: {
      artifactRef: opaque("artifact"),
      contentDigest: digest("content"),
      mediaType: ref("boundedToken"),
      sizeBytes: ref("boundedByteCount"),
    },
  },
  observationPublication: {
    type: "object",
    additionalProperties: false,
    required: ["action"],
    properties: {
      action: { const: "observation_only" },
    },
  },
  publicationRequest: {
    type: "object",
    additionalProperties: false,
    required: ["action", "operationAttemptRef"],
    properties: {
      action: { const: "explicit_plane_publication_requested" },
      operationAttemptRef: opaque("operation-attempt"),
    },
  },
  publicationReceipt: {
    type: "object",
    additionalProperties: false,
    required: ["action", "operationAttemptRef", "receiptRef", "productEventRef"],
    properties: {
      action: { const: "plane_publication_receipt_observed" },
      operationAttemptRef: opaque("operation-attempt"),
      receiptRef: opaque("receipt"),
      productEventRef: opaque("product-event"),
    },
  },
  publicationBoundary: {
    oneOf: [ref("observationPublication"), ref("publicationRequest"), ref("publicationReceipt")],
  },
  publicationRequired: {
    oneOf: [ref("publicationRequest"), ref("publicationReceipt")],
  },
};

const objectSchema = (name, required, properties, extra = {}) => ({
  $schema: draft,
  $id: `https://plane.dev/schemas/${protocol}/${name}.schema.json`,
  title: name,
  type: "object",
  additionalProperties: false,
  required,
  properties,
  $defs: definitions,
  ...extra,
});

const assignment = {
  type: "object",
  additionalProperties: false,
  required: ["assignmentRef", "revision", "targetRef", "objective", "acceptanceCriteria"],
  properties: {
    assignmentRef: opaque("assignment"),
    revision: ref("boundedToken"),
    targetRef: opaque("target"),
    objective: ref("boundedText"),
    acceptanceCriteria: {
      type: "array",
      minItems: 1,
      maxItems: 32,
      items: ref("boundedText"),
    },
  },
};

const profile = {
  type: "object",
  additionalProperties: false,
  required: ["profileRef", "revision", "role", "behavioralPrompt"],
  properties: {
    profileRef: opaque("profile-version"),
    revision: ref("boundedToken"),
    role: {
      enum: ["worker", "delegator", "gardener", "chief_of_staff", "hr", "evaluator", "custom"],
    },
    behavioralPrompt: ref("boundedPrompt"),
  },
};

const context = {
  type: "array",
  maxItems: 64,
  items: {
    type: "object",
    additionalProperties: false,
    required: ["contextRef", "revision", "contentDigest"],
    properties: {
      contextRef: opaque("context"),
      revision: ref("boundedToken"),
      contentDigest: digest("content"),
    },
  },
};

const toolCatalog = {
  type: "object",
  additionalProperties: false,
  required: ["catalogDigest", "eagerOperations"],
  properties: {
    catalogDigest: digest("content"),
    eagerOperations: {
      type: "array",
      maxItems: 64,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["operationRef", "schemaDigest", "disclosure"],
        properties: {
          operationRef: opaque("operation"),
          schemaDigest: digest("content"),
          disclosure: { enum: ["eager", "progressive"] },
        },
      },
    },
  },
};

const runtimePolicy = {
  type: "object",
  additionalProperties: false,
  required: ["model", "adapter", "isolation", "maxEventPayloadBytes", "maxArtifactBytes", "maxReceiptBytes"],
  properties: {
    model: {
      type: "object",
      additionalProperties: false,
      required: ["provider", "model"],
      properties: {
        provider: ref("boundedToken"),
        model: ref("boundedToken"),
      },
    },
    adapter: ref("boundedToken"),
    isolation: { const: "single-invocation" },
    maxEventPayloadBytes: ref("boundedByteCount"),
    maxArtifactBytes: ref("boundedByteCount"),
    maxReceiptBytes: ref("boundedByteCount"),
  },
};

const contractDigests = {
  type: "object",
  additionalProperties: false,
  required: ["runSnapshot", "invocationEnvelope", "runtimeEvent", "runtimeExit"],
  properties: {
    runSnapshot: digest("contract-digest"),
    invocationEnvelope: digest("contract-digest"),
    runtimeEvent: digest("contract-digest"),
    runtimeExit: digest("contract-digest"),
  },
};

const runSnapshot = objectSchema(
  "RunSnapshot",
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
  {
    protocol: { const: protocol },
    workspaceRef: opaque("workspace"),
    runId: opaque("run"),
    assignment,
    actorRef: opaque("actor"),
    profile,
    context,
    toolCatalog,
    runtimePolicy,
    totalBudget: ref("runtimeBudget"),
    contractDigests,
  }
);

const invocationTrigger = {
  oneOf: [
    {
      type: "object",
      additionalProperties: false,
      required: ["kind"],
      properties: { kind: { const: "initial" } },
    },
    {
      type: "object",
      additionalProperties: false,
      required: ["kind", "eventRef"],
      properties: {
        kind: { enum: ["human_input", "recoverable_restart", "continuation"] },
        eventRef: opaque("event"),
      },
    },
  ],
};

const lease = {
  type: "object",
  additionalProperties: false,
  required: ["leaseId", "expiresAt", "renewAfterMs"],
  properties: {
    leaseId: opaque("lease"),
    expiresAt: ref("timestamp"),
    renewAfterMs: ref("nonNegativeInteger"),
  },
};

const invocationEnvelope = objectSchema(
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
  {
    protocol: { const: protocol },
    workspaceRef: opaque("workspace"),
    actorRef: opaque("actor"),
    runId: opaque("run"),
    invocationId: opaque("invocation"),
    runSnapshotDigest: digest("contract-digest"),
    trigger: invocationTrigger,
    newContextEventRefs: {
      type: "array",
      maxItems: 64,
      items: opaque("event"),
    },
    checkpointRef: opaque("checkpoint"),
    remainingBudget: ref("runtimeBudget"),
    lease,
    cancellationRef: opaque("cancellation"),
    causationRef: opaque("causation"),
    correlationId: opaque("correlation"),
    idempotencyKey: opaque("idempotency"),
  }
);

const eventBodies = [
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "payload", "publication"],
    properties: {
      kind: { const: "progress_observed" },
      payload: ref("boundedPayload"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "payload", "publication"],
    properties: {
      kind: { const: "conversation_publication_observed" },
      payload: ref("boundedPayload"),
      publication: ref("publicationRequired"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "question", "publication"],
    properties: {
      kind: { const: "input_request_observed" },
      question: ref("boundedText"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "artifact", "publication"],
    properties: {
      kind: { const: "artifact_observed" },
      artifact: ref("artifactReference"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "usage", "publication"],
    properties: {
      kind: { const: "usage_observed" },
      usage: ref("runtimeUsage"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "payload", "publication"],
    properties: {
      kind: { const: "outcome_submission_observed" },
      payload: ref("boundedPayload"),
      publication: ref("publicationRequired"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "failure", "publication"],
    properties: {
      kind: { const: "failure_observed" },
      failure: ref("runtimeFailure"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "reason", "publication"],
    properties: {
      kind: { const: "blocker_observed" },
      reason: ref("boundedText"),
      publication: ref("observationPublication"),
    },
  },
];

const runtimeEvent = objectSchema(
  "RuntimeEvent",
  [
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
  {
    protocol: { const: protocol },
    trust: { const: "untrusted" },
    workspaceRef: opaque("workspace"),
    actorRef: opaque("actor"),
    runId: opaque("run"),
    invocationId: opaque("invocation"),
    sequence: ref("nonNegativeInteger"),
    eventId: opaque("event-id"),
    idempotencyKey: opaque("idempotency"),
    correlationId: opaque("correlation"),
    causationRef: opaque("causation"),
    observedAt: ref("timestamp"),
    body: { oneOf: eventBodies },
  }
);

const runtimeExitBaseProperties = {
  protocol: { const: protocol },
  authority: { const: "runtime_evidence_only" },
  workspaceRef: opaque("workspace"),
  actorRef: opaque("actor"),
  runId: opaque("run"),
  invocationId: opaque("invocation"),
  finalSequence: ref("nonNegativeInteger"),
  idempotencyKey: opaque("idempotency"),
  correlationId: opaque("correlation"),
  causationRef: opaque("causation"),
  kind: {
    enum: ["completed", "waiting_for_input", "failed", "blocked", "cancelled"],
  },
  inputEventRef: opaque("event"),
  failure: ref("runtimeFailure"),
};

const runtimeExit = objectSchema(
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
  runtimeExitBaseProperties,
  {
    oneOf: [
      {
        required: ["kind"],
        properties: { kind: { const: "completed" } },
        not: { anyOf: [{ required: ["failure"] }, { required: ["inputEventRef"] }] },
      },
      {
        required: ["kind", "inputEventRef"],
        properties: { kind: { const: "waiting_for_input" } },
        not: { required: ["failure"] },
      },
      {
        required: ["kind", "failure"],
        properties: { kind: { enum: ["failed", "blocked", "cancelled"] } },
        not: { required: ["inputEventRef"] },
      },
    ],
  }
);

export const schemas = {
  "run-snapshot": runSnapshot,
  "invocation-envelope": invocationEnvelope,
  "runtime-event": runtimeEvent,
  "runtime-exit": runtimeExit,
};

export { protocol };

const protocol = "plane.agent-runtime/v1";
const draft = "https://json-schema.org/draft/2020-12/schema";

const ref = (name) => ({ $ref: `#/$defs/${name}` });
const namespacedPattern = (namespace) => `^${namespace}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,119}$`;
const digestPattern = (namespace) => `^${namespace}:[a-f0-9]{64}$`;

const definitions = {
  workspaceRef: { type: "string", maxLength: 128, pattern: namespacedPattern("workspace") },
  actorRef: { type: "string", maxLength: 128, pattern: namespacedPattern("actor") },
  assignmentRef: { type: "string", maxLength: 128, pattern: namespacedPattern("assignment") },
  profileVersionRef: { type: "string", maxLength: 128, pattern: namespacedPattern("profile-version") },
  runId: { type: "string", maxLength: 128, pattern: namespacedPattern("run") },
  invocationId: { type: "string", maxLength: 128, pattern: namespacedPattern("invocation") },
  targetRef: { type: "string", maxLength: 128, pattern: namespacedPattern("target") },
  contextRef: { type: "string", maxLength: 128, pattern: namespacedPattern("context") },
  operationRef: { type: "string", maxLength: 128, pattern: namespacedPattern("operation") },
  eventRef: { type: "string", maxLength: 128, pattern: namespacedPattern("event") },
  correlationId: { type: "string", maxLength: 128, pattern: namespacedPattern("correlation") },
  idempotencyKey: { type: "string", maxLength: 128, pattern: namespacedPattern("idempotency") },
  causationRef: { type: "string", maxLength: 128, pattern: namespacedPattern("causation") },
  cancellationRef: { type: "string", maxLength: 128, pattern: namespacedPattern("cancellation") },
  checkpointRef: { type: "string", maxLength: 128, pattern: namespacedPattern("checkpoint") },
  leaseId: { type: "string", maxLength: 128, pattern: namespacedPattern("lease") },
  operationAttemptRef: { type: "string", maxLength: 128, pattern: namespacedPattern("operation-attempt") },
  receiptRef: { type: "string", maxLength: 128, pattern: namespacedPattern("receipt") },
  auditReceiptRef: { type: "string", maxLength: 128, pattern: namespacedPattern("audit-receipt") },
  productEventRef: { type: "string", maxLength: 128, pattern: namespacedPattern("product-event") },
  conversationRef: { type: "string", maxLength: 128, pattern: namespacedPattern("conversation") },
  inputRequestRef: { type: "string", maxLength: 128, pattern: namespacedPattern("input-request") },
  artifactRef: { type: "string", maxLength: 128, pattern: namespacedPattern("artifact") },
  outcomeSubmissionRef: { type: "string", maxLength: 128, pattern: namespacedPattern("outcome-submission") },
  payloadRef: { type: "string", maxLength: 128, pattern: namespacedPattern("payload") },
  contractDigest: { type: "string", minLength: 64, maxLength: 64, pattern: "^[a-f0-9]{64}$" },
  contentDigest: { type: "string", minLength: 72, maxLength: 72, pattern: digestPattern("content") },
  runSnapshotContentDigest: {
    type: "string",
    minLength: 73,
    maxLength: 73,
    pattern: digestPattern("snapshot"),
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
          payloadRef: ref("payloadRef"),
          contentType: ref("boundedToken"),
          contentDigest: ref("contentDigest"),
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
      artifactRef: ref("artifactRef"),
      contentDigest: ref("contentDigest"),
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
};

const publicationDefinition = (productKind, productRef) => ({
  oneOf: [
    {
      type: "object",
      additionalProperties: false,
      required: ["action", "productKind", "productRef", "operationAttemptRef"],
      properties: {
        action: { const: "proposal" },
        productKind: { const: productKind },
        productRef: ref(productRef),
        operationAttemptRef: ref("operationAttemptRef"),
      },
    },
    {
      type: "object",
      additionalProperties: false,
      required: [
        "action",
        "productKind",
        "productRef",
        "operationAttemptRef",
        "receiptRef",
        "auditReceiptRef",
        "productEventRef",
      ],
      properties: {
        action: { const: "applied" },
        productKind: { const: productKind },
        productRef: ref(productRef),
        operationAttemptRef: ref("operationAttemptRef"),
        receiptRef: ref("receiptRef"),
        auditReceiptRef: ref("auditReceiptRef"),
        productEventRef: ref("productEventRef"),
      },
    },
  ],
});

definitions.conversationPublication = publicationDefinition("conversation", "conversationRef");
definitions.inputRequestPublication = publicationDefinition("input_request", "inputRequestRef");
definitions.artifactPublication = publicationDefinition("artifact", "artifactRef");
definitions.outcomeSubmissionPublication = publicationDefinition("outcome_submission", "outcomeSubmissionRef");

const objectSchema = (name, required, properties, extra = {}) => {
  const root = {
    $schema: draft,
    $id: `https://plane.dev/schemas/${protocol}/${name}.schema.json`,
    title: name,
    type: "object",
    additionalProperties: false,
    required,
    properties,
    ...extra,
  };

  const reachable = new Set();
  const collect = (value) => {
    if (Array.isArray(value)) {
      value.forEach(collect);
      return;
    }
    if (value === null || typeof value !== "object") {
      return;
    }
    if (typeof value.$ref === "string" && value.$ref.startsWith("#/$defs/")) {
      reachable.add(value.$ref.slice("#/$defs/".length));
    }
    Object.entries(value).forEach(([key, child]) => {
      if (key !== "$defs") {
        collect(child);
      }
    });
  };
  collect(root);

  const queue = [...reachable];
  for (const definitionName of queue) {
    collect(definitions[definitionName]);
    for (const nestedName of reachable) {
      if (!queue.includes(nestedName)) {
        queue.push(nestedName);
      }
    }
  }

  root.$defs = Object.fromEntries(
    [...reachable].toSorted().map((definitionName) => [definitionName, definitions[definitionName]])
  );
  return root;
};

const assignment = {
  type: "object",
  additionalProperties: false,
  required: ["assignmentRef", "revision", "targetRef", "objective", "acceptanceCriteria"],
  properties: {
    assignmentRef: ref("assignmentRef"),
    revision: ref("boundedToken"),
    targetRef: ref("targetRef"),
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
    profileRef: ref("profileVersionRef"),
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
      contextRef: ref("contextRef"),
      revision: ref("boundedToken"),
      contentDigest: ref("contentDigest"),
    },
  },
};

const toolCatalog = {
  type: "object",
  additionalProperties: false,
  required: ["catalogDigest", "eagerOperations"],
  properties: {
    catalogDigest: ref("contentDigest"),
    eagerOperations: {
      type: "array",
      maxItems: 64,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["operationRef", "schemaDigest", "disclosure"],
        properties: {
          operationRef: ref("operationRef"),
          schemaDigest: ref("contentDigest"),
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
    runSnapshot: ref("contractDigest"),
    invocationEnvelope: ref("contractDigest"),
    runtimeEvent: ref("contractDigest"),
    runtimeExit: ref("contractDigest"),
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
    "contentDigest",
  ],
  {
    protocol: { const: protocol },
    workspaceRef: ref("workspaceRef"),
    runId: ref("runId"),
    assignment,
    actorRef: ref("actorRef"),
    profile,
    context,
    toolCatalog,
    runtimePolicy,
    totalBudget: ref("runtimeBudget"),
    contractDigests,
    contentDigest: ref("runSnapshotContentDigest"),
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
        eventRef: ref("eventRef"),
      },
    },
  ],
};

const lease = {
  type: "object",
  additionalProperties: false,
  required: ["leaseId", "expiresAt", "renewAfterMs"],
  properties: {
    leaseId: ref("leaseId"),
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
    workspaceRef: ref("workspaceRef"),
    actorRef: ref("actorRef"),
    runId: ref("runId"),
    invocationId: ref("invocationId"),
    runSnapshotDigest: ref("runSnapshotContentDigest"),
    trigger: invocationTrigger,
    newContextEventRefs: {
      type: "array",
      maxItems: 64,
      items: ref("eventRef"),
    },
    checkpointRef: ref("checkpointRef"),
    remainingBudget: ref("runtimeBudget"),
    lease,
    cancellationRef: ref("cancellationRef"),
    causationRef: ref("causationRef"),
    correlationId: ref("correlationId"),
    idempotencyKey: ref("idempotencyKey"),
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
      publication: ref("conversationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "question", "publication"],
    properties: {
      kind: { const: "input_request_observed" },
      question: ref("boundedText"),
      publication: ref("inputRequestPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "artifact", "publication"],
    properties: {
      kind: { const: "artifact_observed" },
      artifact: ref("artifactReference"),
      publication: ref("artifactPublication"),
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
      publication: ref("outcomeSubmissionPublication"),
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
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "reason", "publication"],
    properties: {
      kind: { const: "cancellation_observed" },
      reason: ref("boundedText"),
      publication: ref("observationPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "payload", "publication"],
    properties: {
      kind: { const: "transcript_evidence_observed" },
      payload: ref("boundedPayload"),
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
    workspaceRef: ref("workspaceRef"),
    actorRef: ref("actorRef"),
    runId: ref("runId"),
    invocationId: ref("invocationId"),
    sequence: ref("nonNegativeInteger"),
    eventId: ref("eventRef"),
    idempotencyKey: ref("idempotencyKey"),
    correlationId: ref("correlationId"),
    causationRef: ref("causationRef"),
    observedAt: ref("timestamp"),
    body: { oneOf: eventBodies },
  }
);

const runtimeExitBaseProperties = {
  protocol: { const: protocol },
  authority: { const: "runtime_evidence_only" },
  workspaceRef: ref("workspaceRef"),
  actorRef: ref("actorRef"),
  runId: ref("runId"),
  invocationId: ref("invocationId"),
  finalSequence: ref("nonNegativeInteger"),
  idempotencyKey: ref("idempotencyKey"),
  correlationId: ref("correlationId"),
  causationRef: ref("causationRef"),
  kind: {
    enum: ["completed", "waiting_for_input", "failed", "blocked", "cancelled"],
  },
  inputEventRef: ref("eventRef"),
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

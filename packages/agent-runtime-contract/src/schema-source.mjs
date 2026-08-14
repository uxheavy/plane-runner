import byteConstraints from "./byte-constraints.json" with { type: "json" };

const protocol = "plane.agent-runtime/v1";
const draft = "https://json-schema.org/draft/2020-12/schema";

const ref = (name) => ({ $ref: `#/$defs/${name}` });
const namespacedPattern = (namespace) =>
  `^${namespace}:[A-Za-z0-9][A-Za-z0-9._~/-]{0,${byteConstraints.reference.identifierCharacterMaxLength - 1}}$`;
const digestPattern = (namespace, constraint) => {
  const prefixLength = `${namespace}:`.length;
  const minimum = constraint.jsonSchemaMinLength - prefixLength;
  const maximum = constraint.jsonSchemaMaxLength - prefixLength;
  return `^${namespace}:[a-f0-9]{${minimum === maximum ? minimum : `${minimum},${maximum}`}}$`;
};
const hexPattern = (constraint) =>
  `^[a-f0-9]{${constraint.jsonSchemaMinLength === constraint.jsonSchemaMaxLength ? constraint.jsonSchemaMinLength : `${constraint.jsonSchemaMinLength},${constraint.jsonSchemaMaxLength}`}}$`;
const stringWithBytes = (constraint, extra = {}) => ({
  type: "string",
  minLength: constraint.jsonSchemaMinLength,
  maxLength: constraint.jsonSchemaMaxLength,
  "x-utf8ByteMax": constraint.utf8ByteMax,
  ...extra,
});

const definitions = {
  workspaceRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("workspace") }),
  actorRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("actor") }),
  assignmentRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("assignment") }),
  profileVersionRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("profile-version") }),
  runId: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("run") }),
  invocationId: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("invocation") }),
  targetRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("target") }),
  contextRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("context") }),
  operationRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("operation") }),
  eventRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("event") }),
  correlationId: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("correlation") }),
  idempotencyKey: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("idempotency") }),
  causationRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("causation") }),
  cancellationRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("cancellation") }),
  checkpointRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("checkpoint") }),
  leaseId: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("lease") }),
  operationAttemptRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("operation-attempt") }),
  applicationServiceRef: stringWithBytes(byteConstraints.reference, {
    pattern: namespacedPattern("application-service"),
  }),
  gatewayReceiptRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("gateway-receipt") }),
  authorizationReceiptRef: stringWithBytes(byteConstraints.reference, {
    pattern: namespacedPattern("authorization-receipt"),
  }),
  receiptRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("receipt") }),
  auditReceiptRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("audit-receipt") }),
  productEventRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("product-event") }),
  conversationRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("conversation") }),
  inputRequestRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("input-request") }),
  artifactRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("artifact") }),
  outcomeSubmissionRef: stringWithBytes(byteConstraints.reference, {
    pattern: namespacedPattern("outcome-submission"),
  }),
  payloadRef: stringWithBytes(byteConstraints.reference, { pattern: namespacedPattern("payload") }),
  contractDigest: stringWithBytes(byteConstraints.contractDigest, {
    pattern: hexPattern(byteConstraints.contractDigest),
  }),
  contentDigest: stringWithBytes(byteConstraints.contentDigest, {
    pattern: digestPattern("content", byteConstraints.contentDigest),
  }),
  runSnapshotContentDigest: stringWithBytes(byteConstraints.runSnapshotContentDigest, {
    pattern: digestPattern("snapshot", byteConstraints.runSnapshotContentDigest),
  }),
  boundedText: stringWithBytes(byteConstraints.boundedText),
  boundedPrompt: stringWithBytes(byteConstraints.boundedPrompt),
  boundedToken: stringWithBytes(byteConstraints.boundedToken),
  timestamp: stringWithBytes(byteConstraints.timestamp),
  nonNegativeInteger: {
    type: "integer",
    minimum: 0,
    maximum: 2147483647,
  },
  boundedByteCount: {
    type: "integer",
    minimum: 0,
    maximum: byteConstraints.boundedByteCount.numericMax,
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
      cause: {
        enum: [
          "host_operation_failure",
          "cancellation_monitor_failure",
          "invalid_usage_accounting",
          "static_configuration_failure",
        ],
      },
    },
    allOf: [
      {
        if: { required: ["cause"] },
        // oxlint-disable-next-line unicorn/no-thenable -- `then` is a required JSON Schema keyword.
        then: { properties: { code: { const: "runtime_error" } } },
      },
    ],
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
  trustedHumanAnswerResponderPrincipal: {
    type: "object",
    additionalProperties: false,
    required: ["kind", "planePrincipalId"],
    properties: {
      kind: { enum: ["human_user", "external_integration"] },
      planePrincipalId: ref("actorRef"),
    },
  },
};

const publicationDefinition = (productKind, productRef, appliedOnly = false) => {
  const applied = {
    type: "object",
    additionalProperties: false,
    required: [
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
    ],
    properties: {
      action: { const: "applied" },
      productKind: { const: productKind },
      productRef: ref(productRef),
      operationAttemptRef: ref("operationAttemptRef"),
      operationRef: ref("operationRef"),
      applicationServiceRef: ref("applicationServiceRef"),
      gatewayReceiptRef: ref("gatewayReceiptRef"),
      receiptRef: ref("receiptRef"),
      auditReceiptRef: ref("auditReceiptRef"),
      productEventRef: ref("productEventRef"),
    },
  };
  if (appliedOnly) {
    return applied;
  }
  return {
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
      applied,
    ],
  };
};

definitions.conversationPublication = publicationDefinition("conversation", "conversationRef");
definitions.inputRequestPublication = publicationDefinition("input_request", "inputRequestRef");
definitions.artifactPublication = publicationDefinition("artifact", "artifactRef");
definitions.outcomeSubmissionPublication = publicationDefinition("outcome_submission", "outcomeSubmissionRef", true);
const terminalPublicationDefinition = (productKind, includeCancellationRef = false) => ({
  type: "object",
  additionalProperties: false,
  required: [
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
    ...(includeCancellationRef ? ["cancellationRef"] : []),
  ],
  properties: {
    action: { const: "applied" },
    productKind: { const: productKind },
    productRef: ref("productEventRef"),
    operationAttemptRef: ref("operationAttemptRef"),
    operationRef: ref("operationRef"),
    applicationServiceRef: ref("applicationServiceRef"),
    gatewayReceiptRef: ref("gatewayReceiptRef"),
    receiptRef: ref("receiptRef"),
    auditReceiptRef: ref("auditReceiptRef"),
    productEventRef: ref("productEventRef"),
    ...(includeCancellationRef ? { cancellationRef: ref("cancellationRef") } : {}),
  },
  "x-equalProperties": [["productRef", "productEventRef"]],
});
definitions.failurePublication = terminalPublicationDefinition("run_failure");
definitions.blockerPublication = terminalPublicationDefinition("run_blocker");
definitions.cancellationPublication = terminalPublicationDefinition("run_cancellation", true);

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
    maxCodeModeInputBytes: ref("boundedByteCount"),
    maxCodeModeOutputBytes: ref("boundedByteCount"),
    maxCodeModeCalls: ref("nonNegativeInteger"),
  },
};

const contractDigests = {
  type: "object",
  additionalProperties: false,
  required: ["runSnapshot", "invocationEnvelope", "runtimeEvent", "runtimeExit", "runtimeDurableState"],
  properties: {
    runSnapshot: ref("contractDigest"),
    invocationEnvelope: ref("contractDigest"),
    runtimeEvent: ref("contractDigest"),
    runtimeExit: ref("contractDigest"),
    runtimeDurableState: ref("contractDigest"),
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
      properties: {
        kind: { const: "human_input" },
        eventRef: ref("eventRef"),
        pendingInputEventRef: ref("eventRef"),
        answerFactDigest: ref("contentDigest"),
      },
      required: ["kind", "eventRef", "pendingInputEventRef", "answerFactDigest"],
    },
    {
      type: "object",
      additionalProperties: false,
      required: ["kind", "eventRef"],
      properties: {
        kind: { enum: ["recoverable_restart", "continuation"] },
        eventRef: ref("eventRef"),
        pendingInputEventRef: ref("eventRef"),
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
      publication: ref("failurePublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "reason", "publication"],
    properties: {
      kind: { const: "blocker_observed" },
      reason: ref("boundedText"),
      publication: ref("blockerPublication"),
    },
  },
  {
    type: "object",
    additionalProperties: false,
    required: ["kind", "reason", "cancellationRef", "publication"],
    properties: {
      kind: { const: "cancellation_observed" },
      reason: ref("boundedText"),
      cancellationRef: ref("cancellationRef"),
      publication: ref("cancellationPublication"),
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
  },
  { "x-serializedUtf8ByteMax": byteConstraints.serializedContract.utf8ByteMax }
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

const durableStateBinding = {
  type: "object",
  additionalProperties: false,
  required: ["workspaceRef", "actorRef", "profileVersionRef", "runId", "snapshotContentDigest"],
  properties: {
    workspaceRef: ref("workspaceRef"),
    actorRef: ref("actorRef"),
    profileVersionRef: ref("profileVersionRef"),
    runId: ref("runId"),
    snapshotContentDigest: ref("runSnapshotContentDigest"),
  },
};

definitions.durableConversationBinding = publicationDefinition("conversation", "conversationRef");
definitions.durableInputRequestBinding = publicationDefinition("input_request", "inputRequestRef");
definitions.durableArtifactBinding = publicationDefinition("artifact", "artifactRef");
definitions.durableOutcomeSubmissionBinding = publicationDefinition("outcome_submission", "outcomeSubmissionRef", true);
definitions.durableFailureBinding = terminalPublicationDefinition("run_failure");
definitions.durableBlockerBinding = terminalPublicationDefinition("run_blocker");
definitions.durableCancellationBinding = terminalPublicationDefinition("run_cancellation", true);

const durableProductBindingVariants = [
  ref("durableConversationBinding"),
  ref("durableInputRequestBinding"),
  ref("durableArtifactBinding"),
  ref("durableOutcomeSubmissionBinding"),
  ref("durableFailureBinding"),
  ref("durableBlockerBinding"),
  ref("durableCancellationBinding"),
];

const durableProductBinding = {
  oneOf: durableProductBindingVariants,
};

const durableAcceptedEventBase = {
  type: "object",
  additionalProperties: false,
  required: [
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
  properties: {
    workspaceRef: ref("workspaceRef"),
    actorRef: ref("actorRef"),
    profileVersionRef: ref("profileVersionRef"),
    runId: ref("runId"),
    snapshotContentDigest: ref("runSnapshotContentDigest"),
    invocationId: ref("invocationId"),
    eventId: ref("eventRef"),
    idempotencyKey: ref("idempotencyKey"),
    correlationId: ref("correlationId"),
    causationRef: ref("causationRef"),
    sequence: ref("nonNegativeInteger"),
    fingerprint: ref("contentDigest"),
    kind: {
      enum: [
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
      ],
    },
    productBinding: durableProductBinding,
  },
};

const durableAcceptedEvent = {
  ...durableAcceptedEventBase,
  oneOf: [
    {
      properties: {
        kind: {
          enum: ["progress_observed", "usage_observed", "transcript_evidence_observed"],
        },
      },
      not: { required: ["productBinding"] },
    },
    {
      properties: {
        kind: { const: "conversation_publication_observed" },
        productBinding: ref("durableConversationBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "input_request_observed" },
        productBinding: ref("durableInputRequestBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "artifact_observed" },
        productBinding: ref("durableArtifactBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "outcome_submission_observed" },
        productBinding: ref("durableOutcomeSubmissionBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "failure_observed" },
        productBinding: ref("durableFailureBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "blocker_observed" },
        productBinding: ref("durableBlockerBinding"),
      },
      required: ["productBinding"],
    },
    {
      properties: {
        kind: { const: "cancellation_observed" },
        productBinding: ref("durableCancellationBinding"),
      },
      required: ["productBinding"],
    },
  ],
};

const durableHumanInputAnswer = {
  type: "object",
  additionalProperties: false,
  required: [
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
  ],
  properties: {
    answerEventRef: ref("eventRef"),
    inputRequestRef: ref("inputRequestRef"),
    responderPrincipal: ref("trustedHumanAnswerResponderPrincipal"),
    workspaceRef: ref("workspaceRef"),
    runId: ref("runId"),
    authorizationReceiptRef: ref("authorizationReceiptRef"),
    applicationServiceRef: ref("applicationServiceRef"),
    gatewayReceiptRef: ref("gatewayReceiptRef"),
    receiptRef: ref("receiptRef"),
    auditReceiptRef: ref("auditReceiptRef"),
    correlationId: ref("correlationId"),
    causationRef: ref("causationRef"),
    payloadDigest: ref("contentDigest"),
    answerFactDigest: ref("contentDigest"),
  },
};

const durableAcceptedExit = {
  type: "object",
  additionalProperties: false,
  required: [
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
  properties: {
    workspaceRef: ref("workspaceRef"),
    actorRef: ref("actorRef"),
    profileVersionRef: ref("profileVersionRef"),
    runId: ref("runId"),
    snapshotContentDigest: ref("runSnapshotContentDigest"),
    invocationId: ref("invocationId"),
    idempotencyKey: ref("idempotencyKey"),
    finalSequence: { type: "integer", minimum: 0 },
    fingerprint: ref("contentDigest"),
    kind: { enum: ["completed", "waiting_for_input", "failed", "blocked", "cancelled"] },
    inputEventId: ref("eventRef"),
    terminalEventId: ref("eventRef"),
  },
};

const durableTerminalBinding = {
  type: "object",
  additionalProperties: false,
  required: ["eventId", "invocationId", "correlationId", "causationRef", "productBinding"],
  properties: {
    eventId: ref("eventRef"),
    invocationId: ref("invocationId"),
    correlationId: ref("correlationId"),
    causationRef: ref("causationRef"),
    productBinding: {
      oneOf: [
        ref("durableOutcomeSubmissionBinding"),
        ref("durableFailureBinding"),
        ref("durableBlockerBinding"),
        ref("durableCancellationBinding"),
      ],
    },
  },
};

const durablePendingInput = {
  type: "object",
  additionalProperties: false,
  required: [
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
  ],
  properties: {
    eventId: ref("eventRef"),
    invocationId: ref("invocationId"),
    correlationId: ref("correlationId"),
    causationRef: ref("causationRef"),
    inputRequestRef: ref("inputRequestRef"),
    productEventRef: ref("productEventRef"),
    operationAttemptRef: ref("operationAttemptRef"),
    operationRef: ref("operationRef"),
    applicationServiceRef: ref("applicationServiceRef"),
    gatewayReceiptRef: ref("gatewayReceiptRef"),
    receiptRef: ref("receiptRef"),
    auditReceiptRef: ref("auditReceiptRef"),
    questionDigest: ref("contentDigest"),
  },
};

const runtimeDurableState = objectSchema(
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
  {
    protocol: { const: protocol },
    stateVersion: { const: "v1" },
    binding: durableStateBinding,
    state: {
      enum: ["queued", "running", "waiting_for_input", "succeeded", "failed", "blocked", "cancelled"],
    },
    revision: { type: "integer", minimum: 0, maximum: 2147483647 },
    stateDigest: ref("contentDigest"),
    previousRevision: { type: "integer", minimum: 0, maximum: 2147483647 },
    previousStateDigest: ref("contentDigest"),
    lastAcceptedSequence: { type: "integer", minimum: 0 },
    acceptedEvents: { type: "array", maxItems: 4096, items: durableAcceptedEvent },
    acceptedHumanInputAnswers: { type: "array", maxItems: 256, items: durableHumanInputAnswer },
    acceptedExits: { type: "array", maxItems: 256, items: durableAcceptedExit },
    terminal: durableTerminalBinding,
    pendingInput: durablePendingInput,
  },
  {
    allOf: [
      {
        oneOf: [
          {
            properties: {
              state: { const: "queued" },
              revision: { const: 0 },
              lastAcceptedSequence: { const: 0 },
              acceptedEvents: { maxItems: 0 },
              acceptedHumanInputAnswers: { maxItems: 0 },
              acceptedExits: { maxItems: 0 },
            },
            not: {
              anyOf: [
                { required: ["previousRevision"] },
                { required: ["previousStateDigest"] },
                { required: ["terminal"] },
                { required: ["pendingInput"] },
              ],
            },
          },
          {
            properties: { revision: { minimum: 1 } },
            required: ["previousRevision", "previousStateDigest"],
          },
        ],
      },
      {
        oneOf: [
          {
            properties: { state: { enum: ["queued", "running"] } },
            not: { anyOf: [{ required: ["terminal"] }, { required: ["pendingInput"] }] },
          },
          {
            properties: { state: { const: "waiting_for_input" } },
            required: ["pendingInput"],
            not: { required: ["terminal"] },
          },
          {
            properties: { state: { enum: ["succeeded", "failed", "blocked", "cancelled"] } },
            required: ["terminal"],
            not: { required: ["pendingInput"] },
          },
        ],
      },
    ],
  }
);

export const schemas = {
  "run-snapshot": runSnapshot,
  "invocation-envelope": invocationEnvelope,
  "runtime-event": runtimeEvent,
  "runtime-exit": runtimeExit,
  "runtime-durable-state": runtimeDurableState,
};

export { protocol };

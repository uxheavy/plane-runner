import { describe, expect, test } from "vitest";

import {
  computeRunSnapshotContentDigest as computeRunSnapshotContentDigestWire,
  computeRuntimeDurableStateDigest as computeRuntimeDurableStateDigestWire,
  computeTrustedHumanInputAnswerDigest as computeTrustedHumanInputAnswerDigestWire,
  createRuntimeSchemaValidator,
  createActorRef,
  createApplicationServiceRef,
  createAuditReceiptRef,
  createAuthorizationReceiptRef,
  createInitialRuntimeDurableState as createInitialRuntimeDurableStateWire,
  createContentDigest,
  createContractDigest,
  createRunSnapshotContentDigest,
  createCausationRef,
  createCheckpointRef,
  createCorrelationId,
  createEventRef,
  createGatewayReceiptRef,
  createIdempotencyKey,
  createInputRequestRef,
  createInvocationId,
  createLeaseId,
  createOperationRef,
  createProductEventRef,
  createReceiptRef,
  createRunId,
  createWorkspaceRef,
  MAX_SERIALIZED_JSON_BYTES,
  createOutcomeSubmissionRef,
  parseInvocationEnvelope as parseInvocationEnvelopeWire,
  parseRunSnapshot as parseRunSnapshotWire,
  parseRuntimeEvent as parseRuntimeEventWire,
  parseRuntimeExit as parseRuntimeExitWire,
  parseRuntimeDurableState as parseRuntimeDurableStateWire,
  serializedJsonByteLength as serializedJsonByteLengthWire,
  UTF8_BYTE_LIMITS,
  verifyRuntimeExecution as verifyRuntimeExecutionWire,
  type RuntimeDurableState,
  type RuntimeEvent,
  type RuntimeEventBody,
  type RuntimeVerificationFacts,
  type TrustedDurableStateHead,
  type TrustedHumanAnswerHead,
  type TrustedHumanInputAnswer,
  type TrustedPublicationReceipt,
} from "../src";
import {
  appliedBlockerBody,
  appliedCancellationBody,
  appliedConversationBody,
  appliedArtifactBody,
  appliedFailureBody,
  appliedInputRequestBody,
  appliedOutcomeBody,
  contentDigest,
  envelope,
  event,
  exits,
  inlinePayload,
  manifest,
  observationBody,
  observationUsageBody,
  proposalArtifactBody,
  proposalInputRequestBody,
  publicationBody,
  snapshot,
  transcriptEvidenceBody,
  trustedHumanInputAnswer,
} from "./fixtures";

const toWire = (value: unknown): string | Uint8Array =>
  typeof value === "string" || value instanceof Uint8Array ? value : JSON.stringify(value);
const parseInvocationEnvelope = (value: unknown) => parseInvocationEnvelopeWire(toWire(value));
const parseRunSnapshot = (value: unknown) => parseRunSnapshotWire(toWire(value));
const parseRuntimeEvent = (value: unknown) => parseRuntimeEventWire(toWire(value));
const parseRuntimeExit = (value: unknown) => parseRuntimeExitWire(toWire(value));
const parseRuntimeDurableState = (value: unknown) => parseRuntimeDurableStateWire(toWire(value));
const createInitialRuntimeDurableState = (value: unknown) => createInitialRuntimeDurableStateWire(toWire(value));
const computeRunSnapshotContentDigest = (value: unknown) => computeRunSnapshotContentDigestWire(toWire(value));
const computeRuntimeDurableStateDigest = (value: unknown) => computeRuntimeDurableStateDigestWire(toWire(value));
const computeTrustedHumanInputAnswerDigest = (value: unknown) =>
  computeTrustedHumanInputAnswerDigestWire(toWire(value));
const serializedJsonByteLength = (value: unknown) =>
  serializedJsonByteLengthWire(value instanceof Uint8Array ? value : JSON.stringify(value));
const verifyRuntimeExecution = (value: unknown) => verifyRuntimeExecutionWire(toWire(value));

const schemaNames = [
  "run-snapshot",
  "invocation-envelope",
  "runtime-event",
  "runtime-exit",
  "runtime-durable-state",
] as const;
const schemaValidator = createRuntimeSchemaValidator();
const validators = Object.fromEntries(
  schemaNames.map((name) => [name, (value: unknown) => schemaValidator.validate(name, toWire(value))])
) as Record<(typeof schemaNames)[number], (value: unknown) => boolean>;

const assertValid = (name: (typeof schemaNames)[number], value: unknown) => {
  const valid = validators[name](value);
  expect(valid, schemaValidator.errors(name) ? JSON.stringify(schemaValidator.errors(name)) : undefined).toBe(true);
};

const durableStateWithAppliedEvent = (body: RuntimeEventBody, productBindingOverride?: unknown) => {
  const genesis = createInitialRuntimeDurableState({
    workspaceRef: snapshot.workspaceRef,
    actorRef: snapshot.actorRef,
    profileVersionRef: snapshot.profile.profileRef,
    runId: snapshot.runId,
    snapshotContentDigest: snapshot.contentDigest,
  });
  const observed = event(body);
  const publication =
    "publication" in observed.body && observed.body.publication.action !== "observation_only"
      ? observed.body.publication
      : undefined;
  const content = {
    ...genesis,
    state: "running" as const,
    revision: 1,
    previousRevision: 0,
    previousStateDigest: genesis.stateDigest,
    lastAcceptedSequence: 0,
    acceptedEvents: [
      {
        ...genesis.binding,
        invocationId: observed.invocationId,
        eventId: observed.eventId,
        idempotencyKey: observed.idempotencyKey,
        correlationId: observed.correlationId,
        causationRef: observed.causationRef,
        sequence: 0,
        fingerprint: contentDigest("a"),
        kind: observed.body.kind,
        ...(publication === undefined
          ? {}
          : { productBinding: productBindingOverride === undefined ? publication : productBindingOverride }),
      },
    ],
  };
  return {
    ...content,
    stateDigest: computeRuntimeDurableStateDigest(content as unknown as RuntimeDurableState),
  };
};

const durableStateHead = (lifecycle: RuntimeDurableState): TrustedDurableStateHead => ({
  workspaceRef: lifecycle.binding.workspaceRef,
  actorRef: lifecycle.binding.actorRef,
  profileVersionRef: lifecycle.binding.profileVersionRef,
  runId: lifecycle.binding.runId,
  snapshotContentDigest: lifecycle.binding.snapshotContentDigest,
  revision: lifecycle.revision,
  stateDigest: lifecycle.stateDigest,
  ...(lifecycle.previousRevision === undefined
    ? {}
    : {
        previousRevision: lifecycle.previousRevision,
        previousStateDigest: lifecycle.previousStateDigest,
      }),
});

const trusted = (
  invocation = envelope(),
  lifecycle: RuntimeDurableState = createInitialRuntimeDurableState({
    workspaceRef: snapshot.workspaceRef,
    actorRef: snapshot.actorRef,
    profileVersionRef: snapshot.profile.profileRef,
    runId: snapshot.runId,
    snapshotContentDigest: snapshot.contentDigest,
  }),
  overrides: Partial<RuntimeVerificationFacts> = {}
): RuntimeVerificationFacts => {
  const resolvedLifecycle = overrides.lifecycle ?? lifecycle;
  return {
    authority: {
      workspaceRef: snapshot.workspaceRef,
      actorRef: snapshot.actorRef,
      profileVersionRef: snapshot.profile.profileRef,
      runId: snapshot.runId,
      invocationId: invocation.invocationId,
      snapshotContentDigest: snapshot.contentDigest,
      cancellationRef: invocation.cancellationRef,
      correlationId: invocation.correlationId,
      causationRef: invocation.causationRef,
      invocationIdempotencyKey: invocation.idempotencyKey,
    },
    lifecycle: resolvedLifecycle,
    durableStateHead: overrides.durableStateHead ?? durableStateHead(resolvedLifecycle),
    lease: { leaseId: invocation.lease.leaseId, isValid: true },
    cancellation: { cancellationRef: invocation.cancellationRef, isCancelled: false },
    publicationReceipts: [],
    ...overrides,
  };
};

const receiptFor = (eventValue: RuntimeEvent): TrustedPublicationReceipt => {
  if (
    eventValue.body.kind !== "conversation_publication_observed" &&
    eventValue.body.kind !== "input_request_observed" &&
    eventValue.body.kind !== "artifact_observed" &&
    eventValue.body.kind !== "outcome_submission_observed" &&
    eventValue.body.kind !== "failure_observed" &&
    eventValue.body.kind !== "blocker_observed" &&
    eventValue.body.kind !== "cancellation_observed"
  ) {
    throw new Error("Expected a product publication event");
  }
  if (eventValue.body.publication.action !== "applied") {
    throw new Error("Expected an applied publication");
  }
  const receipt = {
    workspaceRef: snapshot.workspaceRef,
    actorRef: snapshot.actorRef,
    profileVersionRef: snapshot.profile.profileRef,
    runId: snapshot.runId,
    invocationId: eventValue.invocationId,
    productKind: eventValue.body.publication.productKind,
    productRef: eventValue.body.publication.productRef,
    operationAttemptRef: eventValue.body.publication.operationAttemptRef,
    operationRef: eventValue.body.publication.operationRef,
    applicationServiceRef: eventValue.body.publication.applicationServiceRef,
    gatewayReceiptRef: eventValue.body.publication.gatewayReceiptRef,
    receiptRef: eventValue.body.publication.receiptRef,
    auditReceiptRef: eventValue.body.publication.auditReceiptRef,
    productEventRef: eventValue.body.publication.productEventRef,
  };
  if (eventValue.body.kind === "cancellation_observed") {
    return { ...receipt, cancellationRef: eventValue.body.cancellationRef };
  }
  if (receipt.productKind === "run_cancellation") {
    throw new Error("Only cancellation observations may carry a cancellation receipt");
  }
  return receipt;
};

const withReceipts = (
  invocation: ReturnType<typeof envelope>,
  events: readonly RuntimeEvent[],
  extra: Partial<RuntimeVerificationFacts> = {}
) =>
  trusted(invocation, undefined, {
    publicationReceipts: events.filter((item) => item.body.kind !== "progress_observed").map(receiptFor),
    ...("humanInputAnswer" in extra && extra.humanInputAnswer !== undefined
      ? { humanInputAnswerHead: { answerFactDigest: extra.humanInputAnswer.answerFactDigest } }
      : {}),
    ...extra,
  });

describe("parsed plane.agent-runtime/v1 contract boundary", () => {
  test("parses all four raw JSON contracts and rejects recursive unknown fields", () => {
    assertValid("run-snapshot", snapshot);
    assertValid("invocation-envelope", envelope());
    assertValid("runtime-event", event(observationBody()));
    assertValid("runtime-exit", exits[0]);
    assertValid("runtime-durable-state", trusted().lifecycle);
    expect(() => parseRunSnapshot({ ...snapshot, profile: { ...snapshot.profile, nested: {} } })).toThrow(
      /unknown properties/
    );
    expect(() => parseInvocationEnvelope({ ...envelope(), lease: { ...envelope().lease, nested: {} } })).toThrow(
      /unknown properties/
    );
    expect(() =>
      parseRuntimeEvent({ ...event(observationBody()), body: { ...event(observationBody()).body, nested: {} } })
    ).toThrow(/unknown properties/);
    expect(() => parseRuntimeExit({ ...exits[0], nested: {} })).toThrow(/unknown properties/);
  });

  test("accepts serialized contracts and rejects live objects at the public verifier boundary", () => {
    const outcome = event(appliedOutcomeBody());
    const base = {
      manifest,
      snapshot,
      invocation: envelope(),
      events: [outcome],
      exit: exits[0],
      trusted: withReceipts(envelope(), [outcome]),
    };
    expect(verifyRuntimeExecution(JSON.stringify(base)).ok).toBe(true);

    let traps = 0;
    const liveInput = new Proxy(base, {
      get() {
        traps += 1;
        throw new Error("live verifier input was inspected");
      },
      ownKeys() {
        traps += 1;
        throw new Error("live verifier input keys were inspected");
      },
    });
    const rejected = verifyRuntimeExecutionWire(liveInput as never);
    expect(rejected).toEqual({
      ok: false,
      errors: [{ code: "unparsed_contract_input", path: "input", message: expect.any(String) }],
    });
    expect(traps).toBe(0);
  });

  test("rejects namespaced cross-type substitutions and reparses serialized verifier input", () => {
    expect(() => parseRunSnapshot({ ...snapshot, workspaceRef: snapshot.actorRef })).toThrow();
    expect(() => parseInvocationEnvelope({ ...envelope(), runId: snapshot.actorRef })).toThrow();
    expect(() => parseRuntimeEvent({ ...event(observationBody()), actorRef: snapshot.workspaceRef })).toThrow();
    expect(() => parseRuntimeExit({ ...exits[0], runId: snapshot.actorRef })).toThrow();

    const outcome = event(appliedOutcomeBody());
    const rawSnapshot = JSON.parse(JSON.stringify(snapshot)) as typeof snapshot;
    const rawInvocation = JSON.parse(JSON.stringify(envelope())) as ReturnType<typeof envelope>;
    const rawEvent = JSON.parse(JSON.stringify(outcome)) as RuntimeEvent;
    const rawExit = JSON.parse(JSON.stringify(exits[0])) as (typeof exits)[number];
    const result = verifyRuntimeExecution({
      manifest,
      snapshot: rawSnapshot,
      invocation: rawInvocation,
      events: [rawEvent],
      exit: rawExit,
      trusted: withReceipts(envelope(), [outcome]),
    });
    expect(result.ok).toBe(true);
  });

  test("keeps snapshot content digest immutable and binds invocation to exact content", () => {
    expect(parseRunSnapshot(JSON.stringify(snapshot)).contentDigest).toBe(snapshot.contentDigest);
    expect(() =>
      parseRunSnapshot({ ...snapshot, contentDigest: createRunSnapshotContentDigest("f".repeat(64)) })
    ).toThrow();
    expect(
      parseInvocationEnvelope({ ...envelope(), runSnapshotDigest: createRunSnapshotContentDigest("f".repeat(64)) })
    ).toBeDefined();
  });

  test("accepts only the canonical genesis and rejects alternate revision-zero states in parser and schema", () => {
    const genesis = createInitialRuntimeDurableState({
      workspaceRef: snapshot.workspaceRef,
      actorRef: snapshot.actorRef,
      profileVersionRef: snapshot.profile.profileRef,
      runId: snapshot.runId,
      snapshotContentDigest: snapshot.contentDigest,
    });
    assertValid("runtime-durable-state", genesis);
    expect(parseRuntimeDurableState(JSON.stringify(genesis))).toEqual(genesis);

    const withDigest = (overrides: Record<string, unknown>) => {
      const content = { ...genesis, ...overrides };
      return {
        ...content,
        stateDigest: computeRuntimeDurableStateDigest(content as unknown as RuntimeDurableState),
      };
    };
    const linkedRunning = withDigest({
      state: "running",
      revision: 1,
      previousRevision: 0,
      previousStateDigest: genesis.stateDigest,
    });
    expect(validators["runtime-durable-state"]?.(linkedRunning)).toBe(true);
    expect(parseRuntimeDurableState(linkedRunning).state).toBe("running");
    const request = event(appliedInputRequestBody(), 0);
    const populated = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: envelope(),
      events: [request],
      exit: parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId }),
      trusted: withReceipts(envelope(), [request]),
    });
    expect(populated.ok).toBe(true);
    if (!populated.ok) return;
    const invalidStates = [
      withDigest({ state: "running" }),
      withDigest({ state: "queued", revision: 1 }),
      withDigest({
        state: "queued",
        acceptedEvents: populated.nextLifecycle.acceptedEvents,
        lastAcceptedSequence: populated.nextLifecycle.lastAcceptedSequence,
      }),
    ];
    for (const invalid of invalidStates) {
      expect(validators["runtime-durable-state"]?.(invalid)).toBe(false);
      expect(() => parseRuntimeDurableState(invalid)).toThrow();
    }

    const alternateGenesis = withDigest({ lastAcceptedSequence: 1 });
    expect(validators["runtime-durable-state"]?.(alternateGenesis)).toBe(false);
    expect(() => parseRuntimeDurableState(alternateGenesis)).toThrow();
  });
});

describe("parser and generated-schema compatibility matrix", () => {
  const bodies = [
    observationBody(),
    publicationBody(),
    appliedConversationBody(),
    proposalInputRequestBody(),
    appliedInputRequestBody(),
    proposalArtifactBody(),
    appliedArtifactBody(),
    observationUsageBody(),
    appliedOutcomeBody("compatibility-outcome"),
    appliedFailureBody(),
    appliedBlockerBody(),
    appliedCancellationBody(),
    transcriptEvidenceBody(),
  ] as const;

  test.each(bodies)("accepts every parsed durable event/action variant in the generated schema", (body) => {
    const parsed = parseRuntimeEvent(event(body));
    assertValid("runtime-event", parsed);
  });

  test("rejects outcome-submission proposals in the parser and generated schema", () => {
    const invalid = {
      ...event(appliedOutcomeBody()),
      body: {
        ...event(appliedOutcomeBody()).body,
        publication: {
          ...event(appliedOutcomeBody()).body.publication,
          action: "proposal",
        },
      },
    } as unknown;
    expect(validators["runtime-event"](invalid)).toBe(false);
    expect(() => parseRuntimeEvent(invalid)).toThrow();
  });

  test.each([appliedOutcomeBody(), appliedFailureBody(), appliedBlockerBody(), appliedCancellationBody()] as const)(
    "rejects a proposal for every terminal product kind",
    (body) => {
      const parsedEvent = event(body);
      const invalid = {
        ...parsedEvent,
        body: {
          ...parsedEvent.body,
          publication: { ...parsedEvent.body.publication, action: "proposal" },
        },
      } as unknown;
      expect(validators["runtime-event"](invalid)).toBe(false);
      expect(() => parseRuntimeEvent(invalid)).toThrow();
    }
  );

  test("rejects terminal durable proposals in both parser and schema", () => {
    const terminalProposal = {
      ...event(appliedFailureBody()),
      body: {
        ...event(appliedFailureBody()).body,
        publication: {
          ...event(appliedFailureBody()).body.publication,
          action: "proposal",
        },
      },
    } as unknown;
    expect(validators["runtime-event"](terminalProposal)).toBe(false);
    expect(() => parseRuntimeEvent(terminalProposal)).toThrow();
  });

  test("rejects terminal durable proposals in durable state parser and schema", () => {
    const invocation = envelope();
    const terminal = event(appliedFailureBody());
    const verified = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [terminal],
      exit: exits[2],
      trusted: withReceipts(invocation, [terminal]),
    });
    expect(verified.ok).toBe(true);
    if (!verified.ok) return;
    const acceptedEvent = verified.nextLifecycle.acceptedEvents[0];
    expect(acceptedEvent?.productBinding).toBeDefined();
    if (acceptedEvent?.productBinding === undefined) return;
    const invalidContent = {
      ...verified.nextLifecycle,
      acceptedEvents: [
        {
          ...acceptedEvent,
          productBinding: { ...acceptedEvent.productBinding, action: "proposal" as const },
        },
      ],
    };
    const invalid = {
      ...invalidContent,
      stateDigest: computeRuntimeDurableStateDigest(invalidContent as unknown as RuntimeDurableState),
    };
    expect(validators["runtime-durable-state"](invalid)).toBe(false);
    expect(() => parseRuntimeDurableState(invalid)).toThrow();
  });

  test("rejects an outcome-submission proposal in durable state parser and schema", () => {
    const invocation = envelope();
    const outcome = event(appliedOutcomeBody("durable-outcome-proposal"));
    const verified = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: withReceipts(invocation, [outcome]),
    });
    expect(verified.ok).toBe(true);
    if (!verified.ok) return;
    const acceptedEvent = verified.nextLifecycle.acceptedEvents[0];
    if (acceptedEvent?.productBinding === undefined) return;
    const invalidContent = {
      ...verified.nextLifecycle,
      acceptedEvents: [
        {
          ...acceptedEvent,
          productBinding: { ...acceptedEvent.productBinding, action: "proposal" as const },
        },
      ],
    };
    const invalid = {
      ...invalidContent,
      stateDigest: computeRuntimeDurableStateDigest(invalidContent as unknown as RuntimeDurableState),
    };
    expect(validators["runtime-durable-state"](invalid)).toBe(false);
    expect(() => parseRuntimeDurableState(invalid)).toThrow();
  });

  test.each([
    ["conversation", appliedConversationBody(), appliedArtifactBody()],
    ["input_request", appliedInputRequestBody(), appliedArtifactBody()],
    ["artifact", appliedArtifactBody(), appliedConversationBody()],
    ["outcome_submission", appliedOutcomeBody("history-outcome"), appliedArtifactBody()],
    ["run_failure", appliedFailureBody(), appliedArtifactBody()],
    ["run_blocker", appliedBlockerBody(), appliedArtifactBody()],
    ["run_cancellation", appliedCancellationBody(), appliedArtifactBody()],
  ] as const)("couples %s history kind to its applied product binding", (_name, body, alternateBody) => {
    const valid = durableStateWithAppliedEvent(body);
    expect(schemaValidator.validate("runtime-durable-state", toWire(valid))).toBe(true);
    expect(() => parseRuntimeDurableState(valid)).not.toThrow();

    const alternatePublication = event(alternateBody).body.publication;
    const mismatched = durableStateWithAppliedEvent(body, alternatePublication);
    expect(schemaValidator.validate("runtime-durable-state", toWire(mismatched))).toBe(false);
    expect(() => parseRuntimeDurableState(mismatched)).toThrow(/must match the accepted event kind/);
  });

  test.each([appliedFailureBody(), appliedBlockerBody(), appliedCancellationBody()] as const)(
    "rejects a terminal history binding whose product reference differs from its product event reference",
    (body) => {
      const publication = event(body).body.publication;
      const mismatched = durableStateWithAppliedEvent(body, {
        ...publication,
        productEventRef: createProductEventRef("different-terminal-event"),
      });
      expect(schemaValidator.validate("runtime-durable-state", toWire(mismatched))).toBe(false);
      expect(() => parseRuntimeDurableState(mismatched)).toThrow(/must identify the terminal product/);
    }
  );
});

describe("audited terminal product-event boundary", () => {
  test("requires exact product kind and trusted application-service/gateway/audit receipt for completion", () => {
    const invocation = envelope();
    const outcome = event(appliedOutcomeBody());
    const valid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: withReceipts(invocation, [outcome]),
    });
    expect(valid.ok).toBe(true);
    if (valid.ok) expect(valid.result).toBe("accepted");

    const forged = {
      ...outcome,
      body: { ...outcome.body, publication: { ...outcome.body.publication, productKind: "run_failure" } },
    };
    expect(() => parseRuntimeEvent(forged)).toThrow();
  });

  test.each([
    ["failure", appliedFailureBody(), exits[2]],
    ["blocker", appliedBlockerBody(), exits[3]],
  ] as const)("requires the exact visible %s product event", (_label, body, exit) => {
    const invocation = envelope();
    const observed = event(body);
    const valid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [observed],
      exit,
      trusted: withReceipts(invocation, [observed]),
    });
    expect(valid.ok).toBe(true);
    const missing = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [observed],
      exit,
      trusted: trusted(invocation),
    });
    expect(missing.ok).toBe(false);
  });

  test("rejects missing, forged, wrong-kind, and wrong-invocation receipts", () => {
    const invocation = envelope();
    const observed = event(appliedOutcomeBody());

    expect(() =>
      parseRuntimeEvent({
        ...observed,
        body: {
          ...observed.body,
          publication: { ...observed.body.publication, gatewayReceiptRef: undefined },
        },
      })
    ).toThrow();

    const forged = parseRuntimeEvent({
      ...observed,
      body: {
        ...observed.body,
        publication: {
          ...observed.body.publication,
          productRef: createOutcomeSubmissionRef("outcome-submission-forged"),
        },
      },
    });
    expect(
      verifyRuntimeExecution({
        manifest,
        snapshot,
        invocation,
        events: [forged],
        exit: exits[0],
        trusted: withReceipts(invocation, [observed]),
      }).ok
    ).toBe(false);

    expect(() =>
      parseRuntimeEvent({
        ...observed,
        body: { ...observed.body, publication: { ...observed.body.publication, productKind: "run_failure" } },
      })
    ).toThrow();

    const wrongInvocationReceipt = { ...receiptFor(observed), invocationId: createInvocationId("other-invocation") };
    const wrongInvocation = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [observed],
      exit: exits[0],
      trusted: withReceipts(invocation, [observed], { publicationReceipts: [wrongInvocationReceipt] }),
    });
    expect(wrongInvocation.ok).toBe(false);
  });

  test("requires one globally unambiguous receipt per applied event", () => {
    const invocation = envelope();
    const conversation = event(appliedConversationBody(), 0);
    const outcome = event(appliedOutcomeBody(), 1);
    const completedExit = parseRuntimeExit({ ...exits[0], finalSequence: 1 });
    const conversationReceipt = receiptFor(conversation);
    const outcomeReceipt = receiptFor(outcome);

    const legitimate = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [conversation, outcome],
      exit: completedExit,
      trusted: trusted(invocation, undefined, { publicationReceipts: [conversationReceipt, outcomeReceipt] }),
    });
    expect(legitimate.ok).toBe(true);

    const repeatedConversation = event(appliedConversationBody(), 1);
    const finalOutcome = event(appliedOutcomeBody(), 2);
    const reusedReceipt = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [conversation, repeatedConversation, finalOutcome],
      exit: parseRuntimeExit({ ...exits[0], finalSequence: 2 }),
      trusted: trusted(invocation, undefined, {
        publicationReceipts: [conversationReceipt, receiptFor(finalOutcome)],
      }),
    });
    expect(reusedReceipt.ok).toBe(false);
    if (!reusedReceipt.ok)
      expect(reusedReceipt.errors.some((error) => error.code === "publication_receipt_mismatch")).toBe(true);

    const duplicate = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: trusted(invocation, undefined, { publicationReceipts: [outcomeReceipt, outcomeReceipt] }),
    });
    expect(duplicate.ok).toBe(false);
    if (!duplicate.ok)
      expect(duplicate.errors.some((error) => error.code === "publication_receipt_duplicate")).toBe(true);

    const conflicting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: trusted(invocation, undefined, {
        publicationReceipts: [
          outcomeReceipt,
          { ...outcomeReceipt, operationRef: createOperationRef("operation-conflict") },
        ],
      }),
    });
    expect(conflicting.ok).toBe(false);
    if (!conflicting.ok)
      expect(conflicting.errors.some((error) => error.code === "publication_receipt_duplicate")).toBe(true);

    const sharedIdentity = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [conversation, outcome],
      exit: completedExit,
      trusted: trusted(invocation, undefined, {
        publicationReceipts: [
          conversationReceipt,
          {
            ...outcomeReceipt,
            auditReceiptRef: conversationReceipt.auditReceiptRef,
            productEventRef: conversationReceipt.productEventRef,
          },
        ],
      }),
    });
    expect(sharedIdentity.ok).toBe(false);
    if (!sharedIdentity.ok)
      expect(sharedIdentity.errors.some((error) => error.code === "publication_receipt_duplicate")).toBe(true);

    const unused = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: trusted(invocation, undefined, { publicationReceipts: [outcomeReceipt, conversationReceipt] }),
    });
    expect(unused.ok).toBe(false);
    if (!unused.ok) expect(unused.errors.some((error) => error.code === "publication_receipt_unused")).toBe(true);
  });

  test("binds cancellation authority and receipt to exact invocation cancellationRef", () => {
    const invocation = envelope();
    const observed = event(appliedCancellationBody());
    const valid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [observed],
      exit: exits[4],
      trusted: withReceipts(invocation, [observed], {
        cancellation: { cancellationRef: invocation.cancellationRef, isCancelled: true },
      }),
    });
    expect(valid.ok).toBe(true);

    const wrongRef = parseRuntimeEvent({
      ...observed,
      body: {
        ...observed.body,
        cancellationRef: "cancellation:wrong",
        publication: { ...observed.body.publication, cancellationRef: "cancellation:wrong" },
      },
    });
    expect(
      verifyRuntimeExecution({
        manifest,
        snapshot,
        invocation,
        events: [wrongRef],
        exit: exits[4],
        trusted: withReceipts(invocation, [observed], {
          cancellation: { cancellationRef: invocation.cancellationRef, isCancelled: true },
        }),
      }).ok
    ).toBe(false);
  });

  test("does not treat transcript/failure observations as product authority", () => {
    const transcript = event({
      kind: "transcript_evidence_observed",
      payload: inlinePayload("final model text"),
      publication: { action: "observation_only" },
    });
    const failed = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: envelope(),
      events: [transcript],
      exit: exits[0],
      trusted: trusted(),
    });
    expect(failed.ok).toBe(false);
  });
});

describe("durable lifecycle and idempotent replay", () => {
  test("parses, freezes, and binds durable waiting state across serialization and restart", () => {
    const initialInvocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waitingExit = parseRuntimeExit({
      ...exits[1],
      inputEventRef: request.eventId,
    });
    const first = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: initialInvocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(initialInvocation, [request]),
    });
    expect(first.ok).toBe(true);
    if (!first.ok) return;
    expect(Object.isFrozen(first.nextLifecycle)).toBe(true);
    expect(Object.isFrozen(first.nextLifecycle.pendingInput)).toBe(true);
    expect(Object.isFrozen(first.nextLifecycle.acceptedEvents)).toBe(true);
    expect(Object.isFrozen(first.nextLifecycle.acceptedEvents[0])).toBe(true);
    expect(Object.isFrozen(first.nextLifecycle.acceptedEvents[0]?.productBinding)).toBe(true);

    const serializedState = JSON.stringify(first.nextLifecycle);
    const reparsedState = parseRuntimeDurableState(serializedState);
    expect(reparsedState).not.toBe(first.nextLifecycle);
    expect(reparsedState).toEqual(first.nextLifecycle);
    const mutableCopy = JSON.parse(serializedState) as RuntimeDurableState;
    const rejectedUnparsedState = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: initialInvocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(initialInvocation, [request], { lifecycle: mutableCopy }),
    });
    expect(rejectedUnparsedState.ok).toBe(false);
    if (!rejectedUnparsedState.ok) expect(rejectedUnparsedState.errors[0]?.code).toBe("pending_input_mismatch");

    expect(() =>
      parseRuntimeDurableState({
        ...reparsedState,
        pendingInput: {
          ...reparsedState.pendingInput,
          inputRequestRef: "input-request:historical",
        },
      })
    ).toThrow(/must match the accepted request|stateDigest/);

    const answerFact = trustedHumanInputAnswer(
      parseInvocationEnvelope({
        ...initialInvocation,
        invocationId: createInvocationId("invocation-2"),
        trigger: {
          kind: "human_input",
          eventRef: createEventRef("human-answer-1"),
          pendingInputEventRef: request.eventId,
          answerFactDigest: contentDigest("a"),
        },
        newContextEventRefs: [request.eventId, createEventRef("human-answer-1")],
        checkpointRef: createCheckpointRef("checkpoint-1"),
        lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-2") },
        causationRef: createCausationRef("causation-2"),
        correlationId: createCorrelationId("correlation-2"),
        idempotencyKey: createIdempotencyKey("idempotency-2"),
      })
    );
    const continuation = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("invocation-2"),
      trigger: {
        kind: "human_input",
        eventRef: answerFact.answerEventRef,
        pendingInputEventRef: request.eventId,
        answerFactDigest: answerFact.answerFactDigest,
      },
      newContextEventRefs: [request.eventId, answerFact.answerEventRef],
      checkpointRef: createCheckpointRef("checkpoint-1"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-2") },
      causationRef: createCausationRef("causation-2"),
      correlationId: createCorrelationId("correlation-2"),
      idempotencyKey: createIdempotencyKey("idempotency-2"),
    });
    const secondRequest = parseRuntimeEvent({
      ...event(appliedInputRequestBody("input-request-2"), 1),
      invocationId: continuation.invocationId,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const waitingContinuationExit = parseRuntimeExit({
      ...exits[1],
      invocationId: continuation.invocationId,
      finalSequence: 1,
      inputEventRef: secondRequest.eventId,
      idempotencyKey: continuation.idempotencyKey,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const secondWaiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [secondRequest],
      exit: waitingContinuationExit,
      trusted: withReceipts(continuation, [secondRequest], {
        lifecycle: reparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: answerFact,
      }),
    });
    expect(secondWaiting.ok, secondWaiting.ok ? undefined : JSON.stringify(secondWaiting.errors)).toBe(true);
    if (!secondWaiting.ok) return;
    expect(secondWaiting.nextLifecycle.pendingInput?.eventId).toBe(secondRequest.eventId);
    expect(secondWaiting.nextLifecycle.acceptedExits).toHaveLength(2);

    const secondReparsedState = parseRuntimeDurableState(JSON.stringify(secondWaiting.nextLifecycle));
    const finalAnswerEventRef = createEventRef("human-answer-2");
    const finalInvocation = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("invocation-3"),
      trigger: {
        kind: "human_input",
        eventRef: finalAnswerEventRef,
        pendingInputEventRef: secondRequest.eventId,
        answerFactDigest: contentDigest("b"),
      },
      newContextEventRefs: [secondRequest.eventId, finalAnswerEventRef],
      checkpointRef: createCheckpointRef("checkpoint-2"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-3") },
      causationRef: createCausationRef("causation-3"),
      correlationId: createCorrelationId("correlation-3"),
      idempotencyKey: createIdempotencyKey("idempotency-3"),
    });
    const finalAnswer = trustedHumanInputAnswer(finalInvocation, "input-request-2", "human-answer-2");
    const resolvedFinalInvocation = parseInvocationEnvelope({
      ...finalInvocation,
      trigger: {
        kind: "human_input",
        eventRef: finalAnswer.answerEventRef,
        pendingInputEventRef: secondRequest.eventId,
        answerFactDigest: finalAnswer.answerFactDigest,
      },
    });
    const outcome = parseRuntimeEvent({
      ...event(appliedOutcomeBody(), 2),
      invocationId: resolvedFinalInvocation.invocationId,
      correlationId: resolvedFinalInvocation.correlationId,
      causationRef: resolvedFinalInvocation.causationRef,
    });
    const finalExit = parseRuntimeExit({
      ...exits[0],
      invocationId: resolvedFinalInvocation.invocationId,
      finalSequence: 2,
      idempotencyKey: resolvedFinalInvocation.idempotencyKey,
      correlationId: resolvedFinalInvocation.correlationId,
      causationRef: resolvedFinalInvocation.causationRef,
    });
    const resumed = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: resolvedFinalInvocation,
      events: [outcome],
      exit: finalExit,
      trusted: withReceipts(resolvedFinalInvocation, [outcome], {
        lifecycle: secondReparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: resolvedFinalInvocation.checkpointRef!, isVerified: true },
        humanInputAnswer: finalAnswer,
      }),
    });
    expect(resumed.ok, resumed.ok ? undefined : JSON.stringify(resumed.errors)).toBe(true);

    const staleTrigger = parseInvocationEnvelope({
      ...finalInvocation,
      trigger: {
        kind: "human_input",
        eventRef: finalAnswer.answerEventRef,
        pendingInputEventRef: request.eventId,
        answerFactDigest: finalAnswer.answerFactDigest,
      },
      newContextEventRefs: [request.eventId, finalAnswer.answerEventRef],
    });
    const stale = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: staleTrigger,
      events: [outcome],
      exit: finalExit,
      trusted: withReceipts(staleTrigger, [outcome], {
        lifecycle: secondReparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: staleTrigger.checkpointRef!, isVerified: true },
        humanInputAnswer: trustedHumanInputAnswer(staleTrigger),
      }),
    });
    expect(stale.ok).toBe(false);
  });

  test("returns explicit replay after carrying accepted state across calls and restarts", () => {
    const invocation = envelope();
    const outcome = event(appliedOutcomeBody());
    const first = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: withReceipts(invocation, [outcome]),
    });
    expect(first.ok).toBe(true);
    if (!first.ok) return;

    const replay = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [parseRuntimeEvent(JSON.parse(JSON.stringify(outcome)))],
      exit: parseRuntimeExit(JSON.parse(JSON.stringify(exits[0]))),
      trusted: withReceipts(invocation, [outcome], { lifecycle: first.nextLifecycle }),
    });
    expect(replay.ok).toBe(true);
    if (replay.ok) expect(replay.result).toBe("idempotent_replay");

    const extendedReplay = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [event(observationBody("after accepted exit"), 1), outcome],
      exit: exits[0],
      trusted: withReceipts(invocation, [outcome], { lifecycle: first.nextLifecycle }),
    });
    expect(extendedReplay.ok).toBe(false);

    const conflicting = parseRuntimeEvent({
      ...outcome,
      body: { ...outcome.body, payload: inlinePayload("different") },
    });
    const conflict = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [conflicting],
      exit: exits[0],
      trusted: withReceipts(invocation, [outcome], { lifecycle: first.nextLifecycle }),
    });
    expect(conflict.ok).toBe(false);
  });

  test("rejects out-of-order, duplicate, terminal-after-progress, and prior-terminal transitions", () => {
    const first = event(observationBody("first"), 0);
    const terminalBody = appliedOutcomeBody();
    const terminal = event(terminalBody, 1);
    const later = event(observationBody("after terminal"), 2);
    const invocation = envelope();
    const invalid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [first, terminal, later],
      exit: exits[0],
      trusted: withReceipts(invocation, [terminal]),
    });
    expect(invalid.ok).toBe(false);

    const duplicate = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [first, first],
      exit: exits[0],
      trusted: trusted(invocation),
    });
    expect(duplicate.ok).toBe(false);

    const priorTerminalEvent = event(terminalBody, 0);
    const firstTerminal = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [priorTerminalEvent],
      exit: exits[0],
      trusted: withReceipts(invocation, [priorTerminalEvent]),
    });
    expect(firstTerminal.ok).toBe(true);
    if (!firstTerminal.ok) return;
    const conflictingPriorTerminal = parseRuntimeEvent({
      ...priorTerminalEvent,
      body: { ...priorTerminalEvent.body, payload: inlinePayload("different terminal") },
    });
    const prior = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [conflictingPriorTerminal],
      exit: exits[0],
      trusted: withReceipts(invocation, [conflictingPriorTerminal], { lifecycle: firstTerminal.nextLifecycle }),
    });
    expect(prior.ok).toBe(false);
  });
});

describe("independently trusted durable heads and history", () => {
  test("rejects reset, stale, alternate-byte, and previous-link state against the Plane head", () => {
    const invocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waitingExit = parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId });
    const accepted = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(invocation, [request]),
    });
    expect(accepted.ok).toBe(true);
    if (!accepted.ok) return;

    const trustedHead = durableStateHead(accepted.nextLifecycle);
    const reset = createInitialRuntimeDurableState(accepted.nextLifecycle.binding);
    const resetResult = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(invocation, [request], { lifecycle: reset, durableStateHead: trustedHead }),
    });
    expect(resetResult.ok).toBe(false);
    if (!resetResult.ok)
      expect(resetResult.errors.some((error) => error.code === "durable_state_head_mismatch")).toBe(true);

    const alternateContent = {
      ...accepted.nextLifecycle,
      acceptedEvents: [
        {
          ...accepted.nextLifecycle.acceptedEvents[0],
          fingerprint: contentDigest("e"),
        },
      ],
    };
    const alternate = parseRuntimeDurableState({
      ...alternateContent,
      stateDigest: computeRuntimeDurableStateDigest(alternateContent),
    });
    const alternateResult = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(invocation, [request], { lifecycle: alternate, durableStateHead: trustedHead }),
    });
    expect(alternateResult.ok).toBe(false);

    const previousLinkContent = {
      ...accepted.nextLifecycle,
      previousStateDigest: contentDigest("f"),
    };
    const previousLink = parseRuntimeDurableState({
      ...previousLinkContent,
      stateDigest: computeRuntimeDurableStateDigest(previousLinkContent),
    });
    const previousLinkResult = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(invocation, [request], {
        lifecycle: previousLink,
        durableStateHead: trustedHead,
      }),
    });
    expect(previousLinkResult.ok).toBe(false);
  });

  test("advances and freezes the digest chain and correlates every waiting exit", () => {
    const invocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waitingExit = parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId });
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(invocation, [request]),
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.nextLifecycle.revision).toBe(1);
    expect(result.nextLifecycle.previousRevision).toBe(0);
    expect(result.nextLifecycle.previousStateDigest).toBe(trusted().lifecycle.stateDigest);
    expect(result.nextLifecycle.stateDigest).toBe(computeRuntimeDurableStateDigest(result.nextLifecycle));
    expect(result.nextLifecycle.acceptedExits[0]?.inputEventId).toBe(request.eventId);
    expect(Object.isFrozen(result.nextLifecycle)).toBe(true);

    const fabricatedExitContent = {
      ...result.nextLifecycle,
      acceptedExits: result.nextLifecycle.acceptedExits.map((exit) =>
        Object.assign({}, exit, { finalSequence: exit.finalSequence + 1 })
      ),
    };
    expect(() =>
      parseRuntimeDurableState({
        ...fabricatedExitContent,
        stateDigest: computeRuntimeDurableStateDigest(fabricatedExitContent),
      })
    ).toThrow(/exact accepted input-request product|cannot exceed the accepted sequence/);
  });

  test.each([
    "operationAttemptRef",
    "gatewayReceiptRef",
    "receiptRef",
    "auditReceiptRef",
    "productEventRef",
    "productRef",
  ] as const)("rejects historical %s reuse on a restart", (field) => {
    const originalInvocation = envelope();
    const historicalEvent = event(appliedOutcomeBody("historical-outcome"));
    const historical = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: originalInvocation,
      events: [historicalEvent],
      exit: exits[0],
      trusted: withReceipts(originalInvocation, [historicalEvent]),
    });
    expect(historical.ok).toBe(true);
    if (!historical.ok) return;

    const restartedInvocation = parseInvocationEnvelope({
      ...envelope(),
      invocationId: createInvocationId("invocation-restart"),
      lease: { ...envelope().lease, leaseId: createLeaseId("lease-restart") },
      causationRef: createCausationRef("causation-restart"),
      correlationId: createCorrelationId("correlation-restart"),
      idempotencyKey: createIdempotencyKey("idempotency-restart"),
    });
    const currentBody = appliedOutcomeBody("current-outcome");
    const historicalPublication = historicalEvent.body;
    if (
      historicalPublication.kind !== "outcome_submission_observed" ||
      currentBody.kind !== "outcome_submission_observed"
    ) {
      throw new Error("Expected outcome publications");
    }
    const current = parseRuntimeEvent({
      ...event(currentBody, 1),
      invocationId: restartedInvocation.invocationId,
      causationRef: restartedInvocation.causationRef,
      correlationId: restartedInvocation.correlationId,
    });
    const currentPublication = current.body.publication;
    const historicalFields = historicalPublication.publication as unknown as Record<string, unknown>;
    const reused = parseRuntimeEvent({
      ...current,
      body: {
        ...current.body,
        publication: {
          ...currentPublication,
          [field]: historicalFields[field],
        },
      },
    });
    const currentExit = parseRuntimeExit({
      ...exits[0],
      invocationId: restartedInvocation.invocationId,
      finalSequence: 1,
      idempotencyKey: restartedInvocation.idempotencyKey,
      correlationId: restartedInvocation.correlationId,
      causationRef: restartedInvocation.causationRef,
    });
    const rejected = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: restartedInvocation,
      events: [reused],
      exit: currentExit,
      trusted: withReceipts(restartedInvocation, [reused], { lifecycle: historical.nextLifecycle }),
    });
    expect(rejected.ok).toBe(false);
    if (!rejected.ok) {
      expect(
        rejected.errors.some(
          (error) => error.code === "publication_receipt_duplicate" || error.code === "publication_product_duplicate"
        )
      ).toBe(true);
    }
  });

  test("rejects a combined historical identity collision on a restart", () => {
    const originalInvocation = envelope();
    const historicalEvent = event(appliedOutcomeBody("historical-combined"));
    const historical = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: originalInvocation,
      events: [historicalEvent],
      exit: exits[0],
      trusted: withReceipts(originalInvocation, [historicalEvent]),
    });
    expect(historical.ok).toBe(true);
    if (!historical.ok) return;

    const restartedInvocation = parseInvocationEnvelope({
      ...envelope(),
      invocationId: createInvocationId("invocation-combined-restart"),
      lease: { ...envelope().lease, leaseId: createLeaseId("lease-combined-restart") },
      causationRef: createCausationRef("causation-combined-restart"),
      correlationId: createCorrelationId("correlation-combined-restart"),
      idempotencyKey: createIdempotencyKey("idempotency-combined-restart"),
    });
    const current = parseRuntimeEvent({
      ...event(appliedOutcomeBody("current-combined"), 1),
      invocationId: restartedInvocation.invocationId,
      causationRef: restartedInvocation.causationRef,
      correlationId: restartedInvocation.correlationId,
    });
    if (
      historicalEvent.body.kind !== "outcome_submission_observed" ||
      current.body.kind !== "outcome_submission_observed" ||
      historicalEvent.body.publication.action !== "applied" ||
      current.body.publication.action !== "applied"
    ) {
      throw new Error("Expected outcome publications");
    }
    const historicalPublication = historicalEvent.body.publication;
    const currentPublication = current.body.publication;
    const reused = parseRuntimeEvent({
      ...current,
      body: {
        ...current.body,
        publication: {
          ...currentPublication,
          productRef: historicalPublication.productRef,
          operationAttemptRef: historicalPublication.operationAttemptRef,
          operationRef: historicalPublication.operationRef,
          applicationServiceRef: historicalPublication.applicationServiceRef,
          gatewayReceiptRef: historicalPublication.gatewayReceiptRef,
          receiptRef: historicalPublication.receiptRef,
          auditReceiptRef: historicalPublication.auditReceiptRef,
          productEventRef: historicalPublication.productEventRef,
        },
      },
    });
    const rejected = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: restartedInvocation,
      events: [reused],
      exit: parseRuntimeExit({
        ...exits[0],
        invocationId: restartedInvocation.invocationId,
        finalSequence: 1,
        idempotencyKey: restartedInvocation.idempotencyKey,
        correlationId: restartedInvocation.correlationId,
        causationRef: restartedInvocation.causationRef,
      }),
      trusted: withReceipts(restartedInvocation, [reused], { lifecycle: historical.nextLifecycle }),
    });
    expect(rejected.ok).toBe(false);
  });
});

describe("Plane-owned human answer boundary", () => {
  test("requires one exact trusted responder fact and never accepts a runtime answer event", () => {
    const initialInvocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waitingExit = parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId });
    const waiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: initialInvocation,
      events: [request],
      exit: waitingExit,
      trusted: withReceipts(initialInvocation, [request]),
    });
    expect(waiting.ok).toBe(true);
    if (!waiting.ok) return;

    const continuationSeed = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("invocation-answer"),
      trigger: {
        kind: "human_input",
        eventRef: createEventRef("human-answer-boundary"),
        pendingInputEventRef: request.eventId,
        answerFactDigest: contentDigest("c"),
      },
      newContextEventRefs: [request.eventId, createEventRef("human-answer-boundary")],
      checkpointRef: createCheckpointRef("checkpoint-answer"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-answer") },
      causationRef: createCausationRef("causation-answer"),
      correlationId: createCorrelationId("correlation-answer"),
      idempotencyKey: createIdempotencyKey("idempotency-answer"),
    });
    const fact = trustedHumanInputAnswer(continuationSeed, "input-request-1", "human-answer-boundary");
    const continuation = parseInvocationEnvelope({
      ...continuationSeed,
      trigger: {
        kind: "human_input",
        eventRef: fact.answerEventRef,
        pendingInputEventRef: request.eventId,
        answerFactDigest: fact.answerFactDigest,
      },
    });
    const outcome = parseRuntimeEvent({
      ...event(appliedOutcomeBody("answer-outcome"), 1),
      invocationId: continuation.invocationId,
      causationRef: continuation.causationRef,
      correlationId: continuation.correlationId,
    });
    const exit = parseRuntimeExit({
      ...exits[0],
      invocationId: continuation.invocationId,
      finalSequence: 1,
      idempotencyKey: continuation.idempotencyKey,
      causationRef: continuation.causationRef,
      correlationId: continuation.correlationId,
    });
    const accepted = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [outcome],
      exit,
      trusted: withReceipts(continuation, [outcome], {
        lifecycle: waiting.nextLifecycle,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: fact,
      }),
    });
    expect(accepted.ok).toBe(true);
    if (!accepted.ok) return;

    const duplicateFact = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [outcome],
      exit,
      trusted: withReceipts(continuation, [outcome], {
        lifecycle: accepted.nextLifecycle,
        durableStateHead: durableStateHead(accepted.nextLifecycle),
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: fact,
      }),
    });
    expect(duplicateFact.ok).toBe(false);

    const runtimeFake = {
      ...outcome,
      eventId: fact.answerEventRef,
    };
    expect(() => parseRuntimeEvent(runtimeFake)).not.toThrow();
    const fakeResult = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [runtimeFake],
      exit,
      trusted: withReceipts(continuation, [runtimeFake], {
        lifecycle: waiting.nextLifecycle,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: fact,
      }),
    });
    expect(fakeResult.ok).toBe(false);

    expect(() =>
      parseRuntimeEvent({
        ...outcome,
        body: {
          kind: "human_input_answer_observed",
          inputRequestRef: fact.inputRequestRef,
          payload: inlinePayload("fake"),
          publication: outcome.body.publication,
        },
      })
    ).toThrow();
  });

  test.each([
    [
      "responder kind",
      (answer: TrustedHumanInputAnswer) => ({
        ...answer,
        responderPrincipal: { ...answer.responderPrincipal, kind: "external_integration" as const },
      }),
    ],
    [
      "responder id",
      (answer: TrustedHumanInputAnswer) => ({
        ...answer,
        responderPrincipal: { ...answer.responderPrincipal, planePrincipalId: createActorRef("human-2") },
      }),
    ],
    [
      "request",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, inputRequestRef: createInputRequestRef("unrelated-request") }),
    ],
    [
      "answer event",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, answerEventRef: createEventRef("unrelated-answer") }),
    ],
    [
      "workspace",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, workspaceRef: createWorkspaceRef("workspace-2") }),
    ],
    ["run", (answer: TrustedHumanInputAnswer) => ({ ...answer, runId: createRunId("run-2") })],
    [
      "authorization",
      (answer: TrustedHumanInputAnswer) => ({
        ...answer,
        authorizationReceiptRef: createAuthorizationReceiptRef("unrelated-authorization"),
      }),
    ],
    [
      "application service",
      (answer: TrustedHumanInputAnswer) => ({
        ...answer,
        applicationServiceRef: createApplicationServiceRef("unrelated-application"),
      }),
    ],
    [
      "gateway",
      (answer: TrustedHumanInputAnswer) => ({
        ...answer,
        gatewayReceiptRef: createGatewayReceiptRef("unrelated-gateway"),
      }),
    ],
    [
      "receipt",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, receiptRef: createReceiptRef("unrelated-receipt") }),
    ],
    [
      "audit",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, auditReceiptRef: createAuditReceiptRef("unrelated-audit") }),
    ],
    [
      "correlation",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, correlationId: createCorrelationId("unrelated-correlation") }),
    ],
    [
      "causation",
      (answer: TrustedHumanInputAnswer) => ({ ...answer, causationRef: createCausationRef("unrelated-causation") }),
    ],
    ["payload digest", (answer: TrustedHumanInputAnswer) => ({ ...answer, payloadDigest: contentDigest("f") })],
    ["answer head digest", (answer: TrustedHumanInputAnswer) => ({ ...answer, answerFactDigest: contentDigest("f") })],
  ] as const)("rejects an independently valid unrelated %s field", (_name, mutate) => {
    const initialInvocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: initialInvocation,
      events: [request],
      exit: parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId }),
      trusted: withReceipts(initialInvocation, [request]),
    });
    expect(waiting.ok).toBe(true);
    if (!waiting.ok) return;

    const seed = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("field-attack-invocation"),
      trigger: {
        kind: "human_input",
        eventRef: createEventRef("field-attack-answer"),
        pendingInputEventRef: request.eventId,
        answerFactDigest: contentDigest("d"),
      },
      newContextEventRefs: [request.eventId, createEventRef("field-attack-answer")],
      checkpointRef: createCheckpointRef("field-attack-checkpoint"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("field-attack-lease") },
      causationRef: createCausationRef("field-attack-causation"),
      correlationId: createCorrelationId("field-attack-correlation"),
      idempotencyKey: createIdempotencyKey("field-attack-idempotency"),
    });
    const fact = trustedHumanInputAnswer(seed, "input-request-1", "field-attack-answer");
    const continuation = parseInvocationEnvelope({
      ...seed,
      trigger: {
        kind: "human_input",
        eventRef: fact.answerEventRef,
        pendingInputEventRef: request.eventId,
        answerFactDigest: fact.answerFactDigest,
      },
    });
    const outcome = parseRuntimeEvent({
      ...event(appliedOutcomeBody("field-attack-outcome"), 1),
      invocationId: continuation.invocationId,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const exit = parseRuntimeExit({
      ...exits[0],
      invocationId: continuation.invocationId,
      finalSequence: 1,
      idempotencyKey: continuation.idempotencyKey,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [outcome],
      exit,
      trusted: withReceipts(continuation, [outcome], {
        lifecycle: waiting.nextLifecycle,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: mutate(fact),
      }),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.some((error) => error.code === "human_input_answer_mismatch")).toBe(true);
  });

  test("rejects a separately altered expected answer head digest", () => {
    const initialInvocation = envelope();
    const request = event(appliedInputRequestBody(), 0);
    const waiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: initialInvocation,
      events: [request],
      exit: parseRuntimeExit({ ...exits[1], inputEventRef: request.eventId }),
      trusted: withReceipts(initialInvocation, [request]),
    });
    expect(waiting.ok).toBe(true);
    if (!waiting.ok) return;
    const seed = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("head-attack-invocation"),
      trigger: {
        kind: "human_input",
        eventRef: createEventRef("head-attack-answer"),
        pendingInputEventRef: request.eventId,
        answerFactDigest: contentDigest("e"),
      },
      newContextEventRefs: [request.eventId, createEventRef("head-attack-answer")],
      checkpointRef: createCheckpointRef("head-attack-checkpoint"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("head-attack-lease") },
      causationRef: createCausationRef("head-attack-causation"),
      correlationId: createCorrelationId("head-attack-correlation"),
      idempotencyKey: createIdempotencyKey("head-attack-idempotency"),
    });
    const fact = trustedHumanInputAnswer(seed, "input-request-1", "head-attack-answer");
    const continuation = parseInvocationEnvelope({
      ...seed,
      trigger: {
        kind: "human_input",
        eventRef: fact.answerEventRef,
        pendingInputEventRef: request.eventId,
        answerFactDigest: fact.answerFactDigest,
      },
    });
    const outcome = parseRuntimeEvent({
      ...event(appliedOutcomeBody("head-attack-outcome"), 1),
      invocationId: continuation.invocationId,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [outcome],
      exit: parseRuntimeExit({
        ...exits[0],
        invocationId: continuation.invocationId,
        finalSequence: 1,
        idempotencyKey: continuation.idempotencyKey,
        correlationId: continuation.correlationId,
        causationRef: continuation.causationRef,
      }),
      trusted: withReceipts(continuation, [outcome], {
        lifecycle: waiting.nextLifecycle,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef!, isVerified: true },
        humanInputAnswer: fact,
        humanInputAnswerHead: { answerFactDigest: contentDigest("f") } satisfies TrustedHumanAnswerHead,
      }),
    });
    expect(result.ok).toBe(false);
    expect(computeTrustedHumanInputAnswerDigest(fact)).toBe(fact.answerFactDigest);
  });
});

describe("explicit UTF-8 bounds", () => {
  test("drives every named bounded field from the shared byte source", () => {
    const referenceSuffix = "a".repeat(UTF8_BYTE_LIMITS.reference - "workspace:".length);
    expect(createWorkspaceRef(referenceSuffix)).toHaveLength(UTF8_BYTE_LIMITS.reference);
    expect(() => createWorkspaceRef(`${referenceSuffix}a`)).toThrow();

    const exactText = "🙂".repeat(UTF8_BYTE_LIMITS.boundedText / 4);
    expect(() => parseRuntimeEvent(event(observationBody(exactText)))).not.toThrow();
    expect(() => parseRuntimeEvent(event(observationBody(`${exactText}🙂`)))).toThrow();

    const exactPromptSnapshotContent = {
      ...snapshot,
      profile: {
        ...snapshot.profile,
        behavioralPrompt: "p".repeat(UTF8_BYTE_LIMITS.boundedPrompt),
      },
    };
    expect(() =>
      parseRunSnapshot({
        ...exactPromptSnapshotContent,
        contentDigest: computeRunSnapshotContentDigest(exactPromptSnapshotContent),
      })
    ).not.toThrow();
    expect(() =>
      parseRunSnapshot({
        ...exactPromptSnapshotContent,
        profile: {
          ...exactPromptSnapshotContent.profile,
          behavioralPrompt: `${"p".repeat(UTF8_BYTE_LIMITS.boundedPrompt)}p`,
        },
        contentDigest: computeRunSnapshotContentDigest({
          ...exactPromptSnapshotContent,
          profile: {
            ...exactPromptSnapshotContent.profile,
            behavioralPrompt: `${"p".repeat(UTF8_BYTE_LIMITS.boundedPrompt)}p`,
          },
        }),
      })
    ).toThrow();

    const exactTokenSnapshotContent = {
      ...snapshot,
      profile: { ...snapshot.profile, revision: "r".repeat(UTF8_BYTE_LIMITS.boundedToken) },
    };
    expect(() =>
      parseRunSnapshot({
        ...exactTokenSnapshotContent,
        contentDigest: computeRunSnapshotContentDigest(exactTokenSnapshotContent),
      })
    ).not.toThrow();
    expect(() =>
      parseRunSnapshot({
        ...exactTokenSnapshotContent,
        profile: { ...exactTokenSnapshotContent.profile, revision: `${"r".repeat(UTF8_BYTE_LIMITS.boundedToken)}r` },
        contentDigest: computeRunSnapshotContentDigest({
          ...exactTokenSnapshotContent,
          profile: {
            ...exactTokenSnapshotContent.profile,
            revision: `${"r".repeat(UTF8_BYTE_LIMITS.boundedToken)}r`,
          },
        }),
      })
    ).toThrow();

    const exactTimestampEvent = {
      ...event(observationBody()),
      observedAt: "t".repeat(UTF8_BYTE_LIMITS.timestamp),
    };
    expect(() => parseRuntimeEvent(exactTimestampEvent)).not.toThrow();
    expect(() =>
      parseRuntimeEvent({ ...exactTimestampEvent, observedAt: `${exactTimestampEvent.observedAt}t` })
    ).toThrow();

    expect(createContractDigest("a".repeat(64))).toHaveLength(64);
    expect(createContentDigest("b".repeat(64))).toHaveLength(UTF8_BYTE_LIMITS.reference - 56);
    expect(createRunSnapshotContentDigest("c".repeat(64))).toHaveLength(UTF8_BYTE_LIMITS.reference - 55);
    expect(() => createContractDigest("a".repeat(65))).toThrow();

    const maximumByteCountSnapshotContent = {
      ...snapshot,
      runtimePolicy: {
        ...snapshot.runtimePolicy,
        maxEventPayloadBytes: 1_048_576,
        maxArtifactBytes: 1_048_576,
        maxReceiptBytes: 1_048_576,
      },
    };
    expect(() =>
      parseRunSnapshot({
        ...maximumByteCountSnapshotContent,
        contentDigest: computeRunSnapshotContentDigest(maximumByteCountSnapshotContent),
      })
    ).not.toThrow();
    expect(MAX_SERIALIZED_JSON_BYTES).toBe(UTF8_BYTE_LIMITS.serializedContract);
  });

  test("distinguishes ASCII code-unit edges, emoji byte edges, and serialized overhead", () => {
    expect(serializedJsonByteLength("🙂")).toBe(6);
    const eventWithText = (text: string) => {
      const base = event(observationBody("x"));
      return {
        ...base,
        body: { ...base.body, payload: inlinePayload(text) },
      };
    };
    const parityCases = [
      ["ASCII exact", "x".repeat(UTF8_BYTE_LIMITS.boundedText), true],
      ["ASCII over", "x".repeat(UTF8_BYTE_LIMITS.boundedText + 1), false],
      ["emoji exact", "🙂".repeat(UTF8_BYTE_LIMITS.boundedText / 4), true],
      ["emoji over", "🙂".repeat(UTF8_BYTE_LIMITS.boundedText / 4 + 1), false],
      ["NFC exact", "é".repeat(UTF8_BYTE_LIMITS.boundedText / 2), true],
      ["NFD exact", "e\u0301".repeat(Math.floor(UTF8_BYTE_LIMITS.boundedText / 3)), true],
      ["NFD boundary over", `${"e\u0301".repeat(Math.floor(UTF8_BYTE_LIMITS.boundedText / 3))}\u0301`, false],
    ] as const;
    for (const [name, text, expected] of parityCases) {
      const value = eventWithText(text);
      expect(validators["runtime-event"](value), name).toBe(expected);
      if (expected) {
        expect(() => parseRuntimeEvent(value), name).not.toThrow();
      } else {
        expect(() => parseRuntimeEvent(value), name).toThrow();
      }
    }
    const smallSnapshotContent = {
      ...snapshot,
      runtimePolicy: {
        ...snapshot.runtimePolicy,
        maxEventPayloadBytes: serializedJsonByteLength(event(observationBody("x"))) - 1,
      },
    };
    const smallSnapshot = parseRunSnapshot({
      ...smallSnapshotContent,
      contentDigest: computeRunSnapshotContentDigest(smallSnapshotContent),
    });
    const bounded = verifyRuntimeExecution({
      manifest,
      snapshot: smallSnapshot,
      invocation: envelope(),
      events: [event(observationBody("x"))],
      exit: exits[0],
      trusted: trusted(),
    });
    expect(bounded.ok).toBe(false);
  });

  test("covers exact, +1 ASCII, and multibyte edges for every shared byte-bound field", () => {
    const parseSnapshotField = (field: "behavioralPrompt" | "revision", value: string) => {
      const content = {
        ...snapshot,
        profile:
          field === "behavioralPrompt"
            ? { ...snapshot.profile, behavioralPrompt: value }
            : { ...snapshot.profile, revision: value },
      };
      return parseRunSnapshot({
        ...content,
        contentDigest: computeRunSnapshotContentDigest(content),
      });
    };
    const boundedCases = [
      {
        name: "text",
        limit: UTF8_BYTE_LIMITS.boundedText,
        parse: (value: string) => parseRuntimeEvent(event(observationBody(value))),
      },
      {
        name: "prompt",
        limit: UTF8_BYTE_LIMITS.boundedPrompt,
        parse: (value: string) => parseSnapshotField("behavioralPrompt", value),
      },
      {
        name: "token",
        limit: UTF8_BYTE_LIMITS.boundedToken,
        parse: (value: string) => parseSnapshotField("revision", value),
      },
      {
        name: "timestamp",
        limit: UTF8_BYTE_LIMITS.timestamp,
        parse: (value: string) => parseRuntimeEvent({ ...event(observationBody()), observedAt: value }),
      },
    ] as const;

    for (const { name, limit, parse } of boundedCases) {
      expect(() => parse("a".repeat(limit)), name).not.toThrow();
      expect(() => parse("a".repeat(limit) + "a"), name).toThrow();
      const multibyteExact = "🙂".repeat(Math.floor(limit / 4));
      expect(new TextEncoder().encode(multibyteExact).byteLength).toBe(limit);
      expect(() => parse(multibyteExact), name).not.toThrow();
      expect(() => parse(multibyteExact + "🙂"), name).toThrow();
    }

    const exactReferenceSuffix = "a".repeat(UTF8_BYTE_LIMITS.reference - "workspace:".length);
    expect(createWorkspaceRef(exactReferenceSuffix)).toBe("workspace:" + exactReferenceSuffix);
    expect(() => createWorkspaceRef(exactReferenceSuffix + "a")).toThrow();
    expect(() => createWorkspaceRef("🙂")).toThrow();

    expect(createContractDigest("a".repeat(64))).toHaveLength(64);
    expect(() => createContractDigest("a".repeat(65))).toThrow();
    expect(() => createContractDigest("🙂".repeat(16))).toThrow();
    expect(createContentDigest("b".repeat(64))).toHaveLength(UTF8_BYTE_LIMITS.reference - 56);
    expect(() => createContentDigest("b".repeat(65))).toThrow();
    expect(() => createContentDigest("🙂".repeat(16))).toThrow();

    const exactSerializedAscii = "x".repeat(MAX_SERIALIZED_JSON_BYTES - 2);
    expect(serializedJsonByteLength(exactSerializedAscii)).toBe(MAX_SERIALIZED_JSON_BYTES);
    expect(() => serializedJsonByteLength(exactSerializedAscii + "x")).toThrow(/maximum UTF-8 byte size/);
    const exactSerializedEmoji = "🙂".repeat(MAX_SERIALIZED_JSON_BYTES / 4 - 1);
    expect(serializedJsonByteLength(exactSerializedEmoji)).toBe(MAX_SERIALIZED_JSON_BYTES - 2);
    expect(() => serializedJsonByteLength(exactSerializedEmoji + "🙂")).toThrow(/maximum UTF-8 byte size/);
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, test } from "vitest";

import {
  computeRunSnapshotContentDigest,
  createContentDigest,
  createContractDigest,
  createRunSnapshotContentDigest,
  createCausationRef,
  createCheckpointRef,
  createCorrelationId,
  createEventRef,
  createIdempotencyKey,
  createInvocationId,
  createLeaseId,
  createOperationRef,
  createWorkspaceRef,
  MAX_SERIALIZED_JSON_BYTES,
  createOutcomeSubmissionRef,
  parseInvocationEnvelope,
  parseRunSnapshot,
  parseRuntimeEvent,
  parseRuntimeExit,
  parseRuntimeDurableState,
  serializedJsonByteLength,
  UTF8_BYTE_LIMITS,
  verifyRuntimeExecution,
  type RuntimeDurableState,
  type RuntimeEvent,
  type RuntimeVerificationFacts,
  type TrustedPublicationReceipt,
} from "../src";
import {
  appliedBlockerBody,
  appliedCancellationBody,
  appliedConversationBody,
  appliedFailureBody,
  appliedHumanInputAnswerBody,
  appliedInputRequestBody,
  appliedOutcomeBody,
  contentDigest,
  envelope,
  event,
  exits,
  inlinePayload,
  manifest,
  observationBody,
  snapshot,
} from "./fixtures";

const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const schemaNames = [
  "run-snapshot",
  "invocation-envelope",
  "runtime-event",
  "runtime-exit",
  "runtime-durable-state",
] as const;
const ajv = new Ajv2020({ allErrors: true, strict: false });
const validators = Object.fromEntries(
  schemaNames.map((name) => [
    name,
    ajv.compile(JSON.parse(readFileSync(`${schemaDirectory}/${name}.schema.json`, "utf8")) as object),
  ])
);

const assertValid = (name: (typeof schemaNames)[number], value: unknown) => {
  const valid = validators[name](value);
  expect(valid, validators[name].errors ? JSON.stringify(validators[name].errors) : undefined).toBe(true);
};

const trusted = (
  invocation = envelope(),
  lifecycle: RuntimeDurableState = parseRuntimeDurableState({
    protocol: "plane.agent-runtime/v1",
    stateVersion: "v1",
    binding: {
      workspaceRef: snapshot.workspaceRef,
      actorRef: snapshot.actorRef,
      profileVersionRef: snapshot.profile.profileRef,
      runId: snapshot.runId,
      snapshotContentDigest: snapshot.contentDigest,
    },
    state: "queued",
    lastAcceptedSequence: -1,
    acceptedEvents: [],
    acceptedExits: [],
  }),
  overrides: Partial<RuntimeVerificationFacts> = {}
): RuntimeVerificationFacts => ({
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
  lifecycle,
  lease: { leaseId: invocation.lease.leaseId, isValid: true },
  cancellation: { cancellationRef: invocation.cancellationRef, isCancelled: false },
  publicationReceipts: [],
  ...overrides,
});

const receiptFor = (eventValue: RuntimeEvent): TrustedPublicationReceipt => {
  if (
    eventValue.body.kind !== "conversation_publication_observed" &&
    eventValue.body.kind !== "input_request_observed" &&
    eventValue.body.kind !== "human_input_answer_observed" &&
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

const withReceipts = (invocation: ReturnType<typeof envelope>, events: readonly RuntimeEvent[], extra = {}) =>
  trusted(invocation, undefined, {
    publicationReceipts: events.filter((item) => item.body.kind !== "progress_observed").map(receiptFor),
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

  test("accepts only the exact parser output for every contract kind", () => {
    const outcome = event(appliedOutcomeBody());
    const parsed = {
      snapshot,
      invocation: envelope(),
      event: outcome,
      exit: exits[0],
    };
    const base = {
      manifest,
      snapshot: parsed.snapshot,
      invocation: parsed.invocation,
      events: [parsed.event],
      exit: parsed.exit,
      trusted: withReceipts(parsed.invocation, [parsed.event]),
    };
    const attempts: Array<[string, unknown, keyof typeof base]> = [
      ["spread", { ...parsed.snapshot }, "snapshot"],
      ["json", JSON.parse(JSON.stringify(parsed.invocation)), "invocation"],
      ["prototype", [Object.create(Object.getPrototypeOf(parsed.event))], "events"],
      ["proxy", new Proxy(parsed.exit, {}), "exit"],
      ["wrong-kind", parsed.snapshot, "invocation"],
    ];
    for (const [label, value, field] of attempts) {
      const input = { ...base, [field]: value } as typeof base;
      const result = verifyRuntimeExecution(input);
      expect(result.ok, label).toBe(false);
      if (!result.ok) expect(result.errors[0]?.code, label).toMatch(/unparsed_contract_input/);
    }
    const durableAttempts: Array<[string, unknown]> = [
      ["durable-proxy", new Proxy(base.trusted.lifecycle, {})],
      ["durable-wrong-kind", parsed.snapshot],
      ["durable-spread", { ...base.trusted.lifecycle }],
    ];
    for (const [label, lifecycle] of durableAttempts) {
      const result = verifyRuntimeExecution({
        ...base,
        trusted: { ...base.trusted, lifecycle: lifecycle as RuntimeDurableState },
      });
      expect(result.ok, label).toBe(false);
      if (!result.ok) expect(result.errors[0]?.code, label).toBe("unparsed_durable_state");
    }
  });

  test("rejects namespaced cross-type substitutions and semantic verification rejects raw casts", () => {
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
    expect(result).toEqual({
      ok: false,
      errors: [{ code: "unparsed_contract_input", path: "input", message: expect.any(String) }],
    });
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
    if (!rejectedUnparsedState.ok) expect(rejectedUnparsedState.errors[0]?.code).toBe("unparsed_durable_state");

    expect(() =>
      parseRuntimeDurableState({
        ...reparsedState,
        pendingInput: {
          ...reparsedState.pendingInput,
          inputRequestRef: "input-request:historical",
        },
      })
    ).toThrow(/must match the accepted request/);

    const answerEventRef = createEventRef("event-id-1");
    const continuation = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("invocation-2"),
      trigger: {
        kind: "human_input",
        eventRef: answerEventRef,
        pendingInputEventRef: request.eventId,
      },
      newContextEventRefs: [request.eventId, answerEventRef],
      checkpointRef: createCheckpointRef("checkpoint-1"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-2") },
      causationRef: createCausationRef("causation-2"),
      correlationId: createCorrelationId("correlation-2"),
      idempotencyKey: createIdempotencyKey("idempotency-2"),
    });
    const answer = parseRuntimeEvent({
      ...event(appliedHumanInputAnswerBody(), 1),
      invocationId: continuation.invocationId,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const secondRequest = parseRuntimeEvent({
      ...event(appliedInputRequestBody("input-request-2"), 2),
      invocationId: continuation.invocationId,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const waitingContinuationExit = parseRuntimeExit({
      ...exits[1],
      invocationId: continuation.invocationId,
      finalSequence: 2,
      inputEventRef: secondRequest.eventId,
      idempotencyKey: continuation.idempotencyKey,
      correlationId: continuation.correlationId,
      causationRef: continuation.causationRef,
    });
    const secondWaiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: continuation,
      events: [answer, secondRequest],
      exit: waitingContinuationExit,
      trusted: withReceipts(continuation, [answer, secondRequest], {
        lifecycle: reparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: continuation.checkpointRef, isVerified: true },
      }),
    });
    expect(secondWaiting.ok, secondWaiting.ok ? undefined : JSON.stringify(secondWaiting.errors)).toBe(true);
    if (!secondWaiting.ok) return;
    expect(secondWaiting.nextLifecycle.pendingInput?.eventId).toBe(secondRequest.eventId);
    expect(secondWaiting.nextLifecycle.acceptedExits).toHaveLength(2);

    const secondReparsedState = parseRuntimeDurableState(JSON.stringify(secondWaiting.nextLifecycle));
    const finalAnswerEventRef = createEventRef("event-id-3");
    const finalInvocation = parseInvocationEnvelope({
      ...initialInvocation,
      invocationId: createInvocationId("invocation-3"),
      trigger: {
        kind: "human_input",
        eventRef: finalAnswerEventRef,
        pendingInputEventRef: secondRequest.eventId,
      },
      newContextEventRefs: [secondRequest.eventId, finalAnswerEventRef],
      checkpointRef: createCheckpointRef("checkpoint-2"),
      lease: { ...initialInvocation.lease, leaseId: createLeaseId("lease-3") },
      causationRef: createCausationRef("causation-3"),
      correlationId: createCorrelationId("correlation-3"),
      idempotencyKey: createIdempotencyKey("idempotency-3"),
    });
    const finalAnswer = parseRuntimeEvent({
      ...event(appliedHumanInputAnswerBody("input-request-2"), 3),
      invocationId: finalInvocation.invocationId,
      correlationId: finalInvocation.correlationId,
      causationRef: finalInvocation.causationRef,
    });
    const outcome = parseRuntimeEvent({
      ...event(appliedOutcomeBody(), 4),
      invocationId: finalInvocation.invocationId,
      correlationId: finalInvocation.correlationId,
      causationRef: finalInvocation.causationRef,
    });
    const finalExit = parseRuntimeExit({
      ...exits[0],
      invocationId: finalInvocation.invocationId,
      finalSequence: 4,
      idempotencyKey: finalInvocation.idempotencyKey,
      correlationId: finalInvocation.correlationId,
      causationRef: finalInvocation.causationRef,
    });
    const resumed = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: finalInvocation,
      events: [finalAnswer, outcome],
      exit: finalExit,
      trusted: withReceipts(finalInvocation, [finalAnswer, outcome], {
        lifecycle: secondReparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: finalInvocation.checkpointRef, isVerified: true },
      }),
    });
    expect(resumed.ok, resumed.ok ? undefined : JSON.stringify(resumed.errors)).toBe(true);

    const staleTrigger = parseInvocationEnvelope({
      ...finalInvocation,
      trigger: {
        kind: "human_input",
        eventRef: finalAnswer.eventId,
        pendingInputEventRef: request.eventId,
      },
      newContextEventRefs: [request.eventId, finalAnswer.eventId],
    });
    const staleAnswer = parseRuntimeEvent({
      ...event(appliedHumanInputAnswerBody("input-request-1"), 3),
      invocationId: staleTrigger.invocationId,
      correlationId: staleTrigger.correlationId,
      causationRef: staleTrigger.causationRef,
    });
    const stale = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: staleTrigger,
      events: [staleAnswer, outcome],
      exit: finalExit,
      trusted: withReceipts(staleTrigger, [staleAnswer, outcome], {
        lifecycle: secondReparsedState,
        previousRemainingBudget: initialInvocation.remainingBudget,
        checkpoint: { checkpointRef: staleTrigger.checkpointRef, isVerified: true },
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

    const priorTerminal: RuntimeDurableState = parseRuntimeDurableState({
      protocol: "plane.agent-runtime/v1",
      stateVersion: "v1",
      binding: {
        workspaceRef: snapshot.workspaceRef,
        actorRef: snapshot.actorRef,
        profileVersionRef: snapshot.profile.profileRef,
        runId: snapshot.runId,
        snapshotContentDigest: snapshot.contentDigest,
      },
      state: "succeeded",
      lastAcceptedSequence: 0,
      acceptedEvents: [
        {
          workspaceRef: snapshot.workspaceRef,
          actorRef: snapshot.actorRef,
          profileVersionRef: snapshot.profile.profileRef,
          runId: snapshot.runId,
          snapshotContentDigest: snapshot.contentDigest,
          invocationId: invocation.invocationId,
          eventId: terminal.eventId,
          idempotencyKey: terminal.idempotencyKey,
          correlationId: invocation.correlationId,
          causationRef: invocation.causationRef,
          sequence: 0,
          fingerprint: contentDigest("a"),
          kind: "outcome_submission_observed",
          productBinding: terminalBody.publication,
        },
      ],
      acceptedExits: [
        {
          workspaceRef: snapshot.workspaceRef,
          actorRef: snapshot.actorRef,
          profileVersionRef: snapshot.profile.profileRef,
          runId: snapshot.runId,
          snapshotContentDigest: snapshot.contentDigest,
          invocationId: invocation.invocationId,
          idempotencyKey: invocation.idempotencyKey,
          finalSequence: 0,
          fingerprint: contentDigest("b"),
          kind: "completed",
          terminalEventId: terminal.eventId,
        },
      ],
      terminal: {
        eventId: terminal.eventId,
        invocationId: invocation.invocationId,
        correlationId: invocation.correlationId,
        causationRef: invocation.causationRef,
        productBinding: terminalBody.publication,
      },
    });
    const prior = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [terminal],
      exit: exits[0],
      trusted: withReceipts(invocation, [terminal], { lifecycle: priorTerminal }),
    });
    expect(prior.ok).toBe(false);
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
    expect(() => parseRuntimeEvent(event(observationBody("x".repeat(4096))))).not.toThrow();
    const emojiEvent = {
      ...event(observationBody("x")),
      body: {
        ...event(observationBody("x")).body,
        payload: inlinePayload("🙂".repeat(2048)),
      },
    };
    expect(validators["runtime-event"](emojiEvent)).toBe(true);
    expect(() => parseRuntimeEvent(emojiEvent)).toThrow();
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
});

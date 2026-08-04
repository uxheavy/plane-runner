import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, test } from "vitest";

import {
  computeRunSnapshotContentDigest,
  createRunSnapshotContentDigest,
  createInvocationId,
  createOutcomeSubmissionRef,
  parseInvocationEnvelope,
  parseRunSnapshot,
  parseRuntimeEvent,
  parseRuntimeExit,
  serializedJsonByteLength,
  verifyRuntimeExecution,
  type RuntimeDurableState,
  type RuntimeEvent,
  type RuntimeVerificationFacts,
} from "../src";
import {
  appliedBlockerBody,
  appliedCancellationBody,
  appliedFailureBody,
  appliedOutcomeBody,
  envelope,
  event,
  exits,
  inlinePayload,
  manifest,
  observationBody,
  snapshot,
} from "./fixtures";

const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const schemaNames = ["run-snapshot", "invocation-envelope", "runtime-event", "runtime-exit"] as const;
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
  lifecycle: RuntimeDurableState = {
    state: "queued",
    lastAcceptedSequence: -1,
    acceptedEvents: [],
    acceptedExits: [],
  },
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

const receiptFor = (eventValue: RuntimeEvent) => {
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
  return {
    workspaceRef: snapshot.workspaceRef,
    actorRef: snapshot.actorRef,
    profileVersionRef: snapshot.profile.profileRef,
    runId: snapshot.runId,
    invocationId: eventValue.invocationId,
    cancellationRef: eventValue.body.kind === "cancellation_observed" ? eventValue.body.cancellationRef : undefined,
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
    const terminal = event(appliedOutcomeBody(), 1);
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

    const priorTerminal: RuntimeDurableState = {
      state: "succeeded",
      lastAcceptedSequence: 1,
      acceptedEvents: [],
      acceptedExits: [],
    };
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

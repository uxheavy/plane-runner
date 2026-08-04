import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, test } from "vitest";

import {
  contractDigestsFromManifest,
  createArtifactRef,
  createCheckpointRef,
  createEventRef,
  createInvocationId,
  createOperationAttemptRef,
  createRunSnapshotContentDigest,
  computeRunSnapshotContentDigest,
  serializedJsonByteLength,
  verifyRunSnapshotContentDigest,
  verifyInvocationSnapshotBinding,
  verifyRuntimeExecution,
  type RuntimeEvent,
  type RuntimeVerificationFacts,
} from "../src";
import {
  appliedConversationBody,
  appliedInputRequestBody,
  appliedOutcomeBody,
  budget,
  contentDigest,
  envelope,
  event,
  exits,
  inlinePayload,
  manifest,
  observationBody,
  publicationBody,
  snapshot,
} from "./fixtures";

const schemaDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const schemaNames = ["run-snapshot", "invocation-envelope", "runtime-event", "runtime-exit"] as const;
const ajv = new Ajv2020({ allErrors: true, strict: false });

const validators = Object.fromEntries(
  schemaNames.map((name) => {
    const schema = JSON.parse(readFileSync(`${schemaDirectory}/${name}.schema.json`, "utf8")) as object;
    return [name, ajv.compile(schema)];
  })
);

const assertValid = (name: (typeof schemaNames)[number], value: unknown) => {
  const valid = validators[name](value);
  expect(valid, validators[name].errors ? JSON.stringify(validators[name].errors) : undefined).toBe(true);
};

const trusted = (
  invocation = envelope(),
  overrides: Partial<RuntimeVerificationFacts> = {}
): RuntimeVerificationFacts => ({
  lease: { leaseId: invocation.lease.leaseId, isValid: true },
  cancellation: { isCancelled: false },
  publicationReceipts: [],
  ...overrides,
});

const appliedReceipt = (eventValue: RuntimeEvent) => {
  if (
    eventValue.body.kind !== "conversation_publication_observed" &&
    eventValue.body.kind !== "input_request_observed" &&
    eventValue.body.kind !== "artifact_observed" &&
    eventValue.body.kind !== "outcome_submission_observed"
  ) {
    throw new Error("Expected a product publication event");
  }
  if (eventValue.body.publication.action !== "applied") {
    throw new Error("Expected an applied publication");
  }
  return {
    productKind: eventValue.body.publication.productKind,
    productRef: eventValue.body.publication.productRef,
    operationAttemptRef: eventValue.body.publication.operationAttemptRef,
    receiptRef: eventValue.body.publication.receiptRef,
    auditReceiptRef: eventValue.body.publication.auditReceiptRef,
    productEventRef: eventValue.body.publication.productEventRef,
  };
};

describe("plane.agent-runtime/v1 schemas", () => {
  test("validates the immutable run snapshot and rejects per-invocation input", () => {
    assertValid("run-snapshot", snapshot);
    expect(snapshot).not.toHaveProperty("input");

    const withInput = { ...snapshot, input: "human answer" };
    expect(validators["run-snapshot"](withInput)).toBe(false);
  });

  test("populates contract digests from the exact generated manifest", () => {
    expect(snapshot.contractDigests).toEqual(contractDigestsFromManifest(manifest));
    expect(snapshot.contractDigests.runSnapshot).toBe(manifest.schemas["run-snapshot"].sha256);
  });

  test("canonicalizes snapshot content without self-reference and detects mutation", () => {
    expect(verifyRunSnapshotContentDigest(snapshot)).toBe(true);
    expect(
      computeRunSnapshotContentDigest({ ...snapshot, contentDigest: createRunSnapshotContentDigest("f".repeat(64)) })
    ).toBe(snapshot.contentDigest);

    const mutated = {
      ...snapshot,
      assignment: { ...snapshot.assignment, objective: "A different immutable objective." },
    };
    expect(computeRunSnapshotContentDigest(mutated)).not.toBe(snapshot.contentDigest);
    expect(verifyRunSnapshotContentDigest(mutated)).toBe(false);
  });

  test("binds an invocation only to the exact snapshot content digest", () => {
    expect(verifyInvocationSnapshotBinding(snapshot, envelope())).toBe(true);
    expect(
      verifyInvocationSnapshotBinding(snapshot, {
        ...envelope(),
        runSnapshotDigest: createRunSnapshotContentDigest("f".repeat(64)),
      })
    ).toBe(false);
  });

  test("freezes every snapshot level and carries later input through event references", () => {
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(Object.isFrozen(snapshot.assignment)).toBe(true);
    expect(Reflect.set(snapshot, "runId", "run:substitute")).toBe(false);

    const inputEventEnvelope = {
      ...envelope({ inputTokens: 800, outputTokens: 400, durationMs: 50000 }),
      trigger: { kind: "human_input" as const, eventRef: "event:human-input-1" },
      newContextEventRefs: ["event:human-input-1"],
    };
    assertValid("invocation-envelope", inputEventEnvelope);
    expect(inputEventEnvelope.trigger).toEqual({ kind: "human_input", eventRef: "event:human-input-1" });
    expect(snapshot).not.toHaveProperty("humanInput");
  });

  test("rejects cross-kind JSON substitutions at the boundary", () => {
    expect(validators["run-snapshot"]({ ...snapshot, workspaceRef: snapshot.actorRef })).toBe(false);
    expect(validators["run-snapshot"]({ ...snapshot, actorRef: snapshot.workspaceRef })).toBe(false);
    expect(validators["invocation-envelope"]({ ...envelope(), runId: snapshot.actorRef })).toBe(false);
    expect(
      validators["invocation-envelope"]({ ...envelope(), runSnapshotDigest: snapshot.contractDigests.runSnapshot })
    ).toBe(false);
    expect(
      validators["run-snapshot"]({
        ...snapshot,
        context: [{ ...snapshot.context[0], contentDigest: snapshot.contractDigests.runSnapshot }],
      })
    ).toBe(false);
  });

  test("requires cumulative remaining budget and rejects reset budgets", () => {
    const first = envelope({ inputTokens: 1000, outputTokens: 500, durationMs: 60000 });
    const continuation = {
      ...envelope({ inputTokens: 600, outputTokens: 250, durationMs: 30000 }),
      invocationId: "invocation:invocation-2",
      trigger: { kind: "continuation" as const, eventRef: "event:checkpoint-event-1" },
      newContextEventRefs: ["event:checkpoint-event-1"],
      checkpointRef: "checkpoint:checkpoint-1",
    };

    assertValid("invocation-envelope", first);
    assertValid("invocation-envelope", continuation);
    expect(continuation.remainingBudget.inputTokens).toBeLessThan(first.remainingBudget.inputTokens);
    expect(continuation.remainingBudget.outputTokens).toBeLessThan(first.remainingBudget.outputTokens);
    expect(continuation.remainingBudget.durationMs).toBeLessThan(first.remainingBudget.durationMs);
  });

  test("validates namespaced publication proposal and applied receipt variants", () => {
    const proposal = event(publicationBody(), 0);
    const applied = event(appliedConversationBody(), 1);
    assertValid("runtime-event", proposal);
    assertValid("runtime-event", applied);
    expect(proposal.body.kind).toBe("conversation_publication_observed");
    expect(proposal.body.publication.action).toBe("proposal");
    expect(applied.body.kind).toBe("conversation_publication_observed");
    expect(applied.body.publication.action).toBe("applied");

    const swapped = {
      ...applied,
      body: {
        ...applied.body,
        publication: { ...applied.body.publication, productRef: "artifact:artifact-1" },
      },
    };
    expect(validators["runtime-event"](swapped)).toBe(false);
  });

  test("bounds inline payloads and artifacts in the schema", () => {
    const oversizedPayload = event(
      {
        kind: "progress_observed",
        payload: { kind: "inline_text", contentType: "text/plain", text: "x".repeat(4097) },
        publication: { action: "observation_only" },
      },
      0
    );
    const oversizedArtifact = event(
      {
        kind: "artifact_observed",
        artifact: {
          artifactRef: createArtifactRef("artifact-2"),
          contentDigest: contentDigest("b"),
          mediaType: "text/plain",
          sizeBytes: 1048577,
        },
        publication: {
          action: "proposal",
          productKind: "artifact",
          productRef: createArtifactRef("artifact-2"),
          operationAttemptRef: createOperationAttemptRef("artifact-2"),
        },
      },
      1
    );

    expect(validators["runtime-event"](oversizedPayload)).toBe(false);
    expect(validators["runtime-event"](oversizedArtifact)).toBe(false);
  });

  test("enforces serialized UTF-8 bytes, including multibyte overhead and resolved event limits", () => {
    expect(serializedJsonByteLength("🙂")).toBe(6);
    const smallSnapshot = {
      ...snapshot,
      runtimePolicy: { ...snapshot.runtimePolicy, maxEventPayloadBytes: 32 },
    };
    const largeMultibyteEvent = event(observationBody("🙂".repeat(20)), 0);
    const failureEvent = event(
      {
        kind: "failure_observed",
        failure: { code: "runtime_error", message: "Stopped.", retryable: false },
        publication: { action: "observation_only" },
      },
      1
    );
    const result = verifyRuntimeExecution({
      manifest,
      snapshot: smallSnapshot,
      invocation: envelope(),
      events: [largeMultibyteEvent, failureEvent],
      exit: { ...exits[2], finalSequence: 1 },
      trusted: trusted(),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.some((error) => error.code === "event_payload_too_large")).toBe(true);
    }
  });

  test("validates exactly one legal runtime exit classification", () => {
    for (const exit of exits) {
      assertValid("runtime-exit", exit);
      expect(exit.authority).toBe("runtime_evidence_only");
    }

    const invalidCompletedExit = {
      ...exits[0],
      failure: { code: "runtime_error", message: "Also failed", retryable: false },
    };
    expect(validators["runtime-exit"](invalidCompletedExit)).toBe(false);

    const invalidWaitingExit = {
      ...exits[1],
      failure: { code: "runtime_error", message: "Also failed", retryable: false },
    };
    expect(validators["runtime-exit"](invalidWaitingExit)).toBe(false);
  });
});

describe("pure runtime semantic verifier", () => {
  test("accepts a receipt-correlated completed stream and rejects forged snapshot binding", () => {
    const invocation = envelope();
    const outcome = event(appliedOutcomeBody(), 0);
    const valid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [outcome],
      exit: exits[0],
      trusted: trusted(invocation, { publicationReceipts: [appliedReceipt(outcome)] }),
    });
    expect(valid).toEqual({ ok: true, state: "completed", finalSequence: 0, terminalEventCount: 1 });

    const forged = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: { ...invocation, runSnapshotDigest: createRunSnapshotContentDigest("f".repeat(64)) },
      events: [outcome],
      exit: exits[0],
      trusted: trusted(invocation, { publicationReceipts: [appliedReceipt(outcome)] }),
    });
    expect(forged.ok).toBe(false);
    if (!forged.ok) {
      expect(forged.errors.some((error) => error.code === "invocation_snapshot_binding_mismatch")).toBe(true);
    }
  });

  test("requires a trusted checkpoint and monotonic budget for continuation", () => {
    const invocation = {
      ...envelope({ inputTokens: 900, outputTokens: 450, durationMs: 50000 }),
      invocationId: createInvocationId("invocation-2"),
      trigger: { kind: "continuation" as const, eventRef: createEventRef("checkpoint-event-1") },
      newContextEventRefs: [createEventRef("checkpoint-event-1")],
      checkpointRef: createCheckpointRef("checkpoint-1"),
    };
    const failure = event(
      {
        kind: "failure_observed",
        failure: { code: "invalid_continuation", message: "unsafe", retryable: false },
        publication: { action: "observation_only" },
      },
      0
    );
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [failure],
      exit: { ...exits[3], invocationId: invocation.invocationId },
      trusted: trusted(invocation, { previousRemainingBudget: budget(800, 400, 40000) }),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.some((error) => error.code === "checkpoint_untrusted")).toBe(true);
      expect(result.errors.some((error) => error.code === "budget_increased")).toBe(true);
    }
  });

  test("rejects duplicate, out-of-order, and correlation-substituted events", () => {
    const first = event(observationBody(), 0);
    const duplicate = { ...first, eventId: first.eventId };
    const older = { ...event(observationBody("older"), 2), idempotencyKey: first.idempotencyKey };
    const failure = event(
      {
        kind: "failure_observed",
        failure: { code: "runtime_error", message: "Stopped.", retryable: false },
        publication: { action: "observation_only" },
      },
      3
    );
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: envelope(),
      events: [first, duplicate, older, failure],
      exit: { ...exits[2], finalSequence: 3 },
      trusted: trusted(),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.some((error) => error.code === "event_duplicate")).toBe(true);
      expect(result.errors.some((error) => error.code === "event_idempotency_duplicate")).toBe(true);
      expect(result.errors.some((error) => error.code === "event_sequence_invalid")).toBe(true);
    }
  });

  test("requires receipt-correlated product publication and keeps transcript evidence non-terminal", () => {
    const transcript = event({
      kind: "transcript_evidence_observed",
      payload: inlinePayload("final model text"),
      publication: { action: "observation_only" },
    });
    const invalid = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: envelope(),
      events: [transcript],
      exit: exits[0],
      trusted: trusted(),
    });
    expect(invalid.ok).toBe(false);
    if (!invalid.ok) {
      expect(invalid.errors.some((error) => error.code === "terminal_event_mismatch")).toBe(true);
    }

    const waitingInvocation = envelope({ inputTokens: 800, outputTokens: 400, durationMs: 50000 });
    const input = event(appliedInputRequestBody(), 0);
    const waitingExit = {
      ...exits[1],
      inputEventRef: input.eventId,
      finalSequence: 0,
    };
    const waiting = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation: waitingInvocation,
      events: [input],
      exit: waitingExit,
      trusted: trusted(waitingInvocation, { publicationReceipts: [appliedReceipt(input)] }),
    });
    expect(waiting.ok).toBe(true);
  });

  test("requires trusted cancellation and exactly one cancellation terminal event", () => {
    const invocation = envelope();
    const cancellation = event(
      {
        kind: "cancellation_observed",
        reason: "Cancelled by Plane.",
        publication: { action: "observation_only" },
      },
      0
    );
    const result = verifyRuntimeExecution({
      manifest,
      snapshot,
      invocation,
      events: [cancellation],
      exit: exits[4],
      trusted: trusted(invocation, { cancellation: { isCancelled: true } }),
    });
    expect(result.ok).toBe(true);
  });

  test("does not allow product publication variants to omit operation or audit receipts", () => {
    const invalid = {
      ...event(appliedConversationBody()),
      body: {
        ...event(appliedConversationBody()).body,
        publication: {
          action: "applied",
          productKind: "conversation",
          productRef: "conversation:conversation-1",
          operationAttemptRef: "operation-attempt:operation-attempt-1",
          receiptRef: "receipt:receipt-1",
          productEventRef: "product-event:product-event-1",
        },
      },
    };
    expect(validators["runtime-event"](invalid)).toBe(false);
  });

  test("can still represent a proposal without making it product-visible", () => {
    const proposal = event(publicationBody());
    assertValid("runtime-event", proposal);
  });
});

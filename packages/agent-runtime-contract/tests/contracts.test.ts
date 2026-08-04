import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, test } from "vitest";

import { freezeRunSnapshot } from "../src";
import { contentDigest, envelope, event, exits, observationBody, publicationBody, ref, snapshot } from "./fixtures";

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

describe("plane.agent-runtime/v1 schemas", () => {
  test("validates the immutable run snapshot and rejects per-invocation input", () => {
    assertValid("run-snapshot", snapshot);
    expect(snapshot).not.toHaveProperty("input");

    const withInput = { ...snapshot, input: "human answer" };
    expect(validators["run-snapshot"](withInput)).toBe(false);
  });

  test("freezes the snapshot and carries later human input through event references", () => {
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(Object.isFrozen(snapshot.assignment)).toBe(true);
    expect(Reflect.set(snapshot, "runId", ref<"run">("run-substitute"))).toBe(false);

    const inputEventEnvelope = {
      ...envelope({ inputTokens: 800, outputTokens: 400, durationMs: 50000 }),
      trigger: { kind: "human_input" as const, eventRef: ref<"event">("human-input-1") },
      newContextEventRefs: [ref<"event">("human-input-1")],
    };
    assertValid("invocation-envelope", inputEventEnvelope);
    expect(inputEventEnvelope.trigger).toEqual({ kind: "human_input", eventRef: "human-input-1" });
    expect(snapshot).not.toHaveProperty("humanInput");
  });

  test("carries cumulative remaining budget instead of resetting it per invocation", () => {
    const first = envelope({ inputTokens: 1000, outputTokens: 500, durationMs: 60000 });
    const continuation = {
      ...envelope({ inputTokens: 600, outputTokens: 250, durationMs: 30000 }),
      invocationId: ref<"invocation">("invocation-2"),
      trigger: { kind: "continuation" as const, eventRef: ref<"event">("checkpoint-event-1") },
      newContextEventRefs: [ref<"event">("checkpoint-event-1")],
      checkpointRef: ref<"checkpoint">("checkpoint-1"),
    };

    assertValid("invocation-envelope", first);
    assertValid("invocation-envelope", continuation);
    expect(continuation.remainingBudget.inputTokens).toBeLessThan(first.remainingBudget.inputTokens);
    expect(continuation.remainingBudget.outputTokens).toBeLessThan(first.remainingBudget.outputTokens);
    expect(continuation.remainingBudget.durationMs).toBeLessThan(first.remainingBudget.durationMs);
  });

  test("makes actor, workspace, run, invocation, and snapshot digest mismatches observable", () => {
    const mismatched = {
      ...envelope(),
      workspaceRef: ref<"workspace">("workspace-other"),
      actorRef: ref<"actor">("actor-other"),
      runId: ref<"run">("run-other"),
      invocationId: ref<"invocation">("invocation-other"),
      runSnapshotDigest: "f".repeat(64),
    };

    assertValid("invocation-envelope", mismatched);
    expect(mismatched.workspaceRef).not.toBe(snapshot.workspaceRef);
    expect(mismatched.actorRef).not.toBe(snapshot.actorRef);
    expect(mismatched.runId).not.toBe(snapshot.runId);
    expect(mismatched.runSnapshotDigest).not.toBe(snapshot.contractDigests.runSnapshot);
  });

  test("preserves duplicate and out-of-order sequence values for Plane ingress to reconcile", () => {
    const first = event(observationBody("first"), 1);
    const duplicate = event(observationBody("duplicate"), 1);
    const older = event(observationBody("older"), 0);

    assertValid("runtime-event", first);
    assertValid("runtime-event", duplicate);
    assertValid("runtime-event", older);
    expect(duplicate.sequence).toBe(first.sequence);
    expect(older.sequence).toBeLessThan(first.sequence);
  });

  test("distinguishes observation from an explicit Plane publication action", () => {
    const observation = event(observationBody(), 0);
    const publication = event(publicationBody(), 1);

    assertValid("runtime-event", observation);
    assertValid("runtime-event", publication);
    expect(observation.trust).toBe("untrusted");
    expect(observation.body.publication.action).toBe("observation_only");
    expect(publication.body.publication.action).toBe("explicit_plane_publication_requested");

    const receipt = event(
      {
        kind: "conversation_publication_observed",
        payload: { kind: "inline_text", contentType: "text/plain", text: "Published." },
        publication: {
          action: "plane_publication_receipt_observed",
          operationAttemptRef: ref<"operation-attempt">("operation-attempt-1"),
          receiptRef: ref<"receipt">("receipt-1"),
          productEventRef: ref<"product-event">("product-event-1"),
        },
      },
      2
    );
    assertValid("runtime-event", receipt);
    expect(receipt.body.publication.action).toBe("plane_publication_receipt_observed");
  });

  test("bounds inline payloads and artifact references", () => {
    const artifact = event(
      {
        kind: "artifact_observed",
        artifact: {
          artifactRef: ref<"artifact">("artifact-1"),
          contentDigest: contentDigest("a"),
          mediaType: "text/plain",
          sizeBytes: 1024,
        },
        publication: { action: "observation_only" },
      },
      3
    );
    const oversizedPayload = event(
      {
        kind: "progress_observed",
        payload: {
          kind: "inline_text",
          contentType: "text/plain",
          text: "x".repeat(4097),
        },
        publication: { action: "observation_only" },
      },
      4
    );
    const oversizedArtifact = event(
      {
        kind: "artifact_observed",
        artifact: {
          artifactRef: ref<"artifact">("artifact-2"),
          contentDigest: contentDigest("b"),
          mediaType: "text/plain",
          sizeBytes: 1048577,
        },
        publication: { action: "observation_only" },
      },
      5
    );

    assertValid("runtime-event", artifact);
    expect(validators["runtime-event"](oversizedPayload)).toBe(false);
    expect(validators["runtime-event"](oversizedArtifact)).toBe(false);
  });

  test("validates exactly one runtime exit classification without product acceptance", () => {
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

  test("does not mutate a snapshot when a defensive freeze is applied twice", () => {
    const frozenAgain = freezeRunSnapshot(snapshot);
    expect(frozenAgain).toBe(snapshot);
    expect(frozenAgain).toEqual(snapshot);
  });
});

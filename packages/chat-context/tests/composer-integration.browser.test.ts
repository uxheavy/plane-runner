/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it, vi } from "vitest";

import hydrationFixture from "../fixtures/v1/hydration-partial-response.json";
import regionFixture from "../fixtures/v1/region-bundle.json";
import selectionFailureFixture from "../fixtures/v1/selection-failure.json";
import {
  createSemanticContextComposerAdapter,
  isSelectionFailureContractV1,
  isSemanticContextBundleV1,
  type SemanticContextBundleV1,
  type SemanticContextHydrationRequestV1,
} from "../src";
import { DummyComposerConsumer } from "./fixtures/dummy-composer-consumer";

const fixtureBundle = (): SemanticContextBundleV1 => {
  if (!isSemanticContextBundleV1(regionFixture)) throw new Error("The region fixture is not a version 1 bundle");
  return structuredClone(regionFixture);
};

describe("composer integration contract", () => {
  it("hydrates a JSON region fixture and removes denied observations before the consumer", async () => {
    const consumer = new DummyComposerConsumer();
    let request: SemanticContextHydrationRequestV1 | undefined;
    const adapter = createSemanticContextComposerAdapter({
      hydration: {
        hydrate: async (workspaceSlug, hydrationRequest) => {
          expect(workspaceSlug).toBe("acme");
          request = hydrationRequest;
          return hydrationFixture;
        },
      },
      consumer,
    });

    const result = await adapter.attachContext(fixtureBundle());

    expect(result.ok).toBe(true);
    expect(request?.items).toHaveLength(3);
    expect(request?.items[0]?.observedEntityVersion).toBe("2026-07-29T07:59:00.000Z");
    expect(consumer.attachments).toHaveLength(1);
    const attachment = consumer.attachments[0]!;
    expect(attachment.items).toHaveLength(2);
    expect(attachment.items.map((item) => item.reference.kind)).toEqual(["entity", "editor_block"]);
    expect(attachment.items[0]?.observed.value).toEqual({ name: "Observed name", priority: "high" });
    expect(attachment.items[0]?.server.resolution).toBe("canonical");
    expect(attachment.items[0]?.server.stale).toBe(true);
    expect(attachment.hydrationWarnings.map((warning) => warning.code)).toEqual(["FORBIDDEN"]);
    expect(attachment.selectionWarnings.map((warning) => warning.code)).toEqual(["VALUE_UNAVAILABLE"]);
  });

  it("rejects reordered or malformed hydration instead of correlating the wrong values", async () => {
    const consumer = new DummyComposerConsumer();
    const reordered = {
      ...hydrationFixture,
      results: [hydrationFixture.results[1], hydrationFixture.results[0], hydrationFixture.results[2]],
    };
    const adapter = createSemanticContextComposerAdapter({
      hydration: { hydrate: async () => reordered },
      consumer,
    });

    const result = await adapter.attachContext(fixtureBundle());

    expect(result).toMatchObject({ ok: false, code: "HYDRATION_INVALID" });
    expect(consumer.attachments).toHaveLength(0);
  });

  it("rejects empty, oversized, and mixed-workspace bundles before hydration", async () => {
    const hydrate = vi.fn(async () => hydrationFixture);
    const adapter = createSemanticContextComposerAdapter({
      hydration: { hydrate },
      consumer: new DummyComposerConsumer(),
      maximumItems: 3,
    });
    const base = fixtureBundle();
    const editorItem = base.items[2]!;
    const mixedReference = editorItem.reference;
    if (mixedReference.kind !== "editor_block") throw new Error("Fixture editor reference changed");
    const mixed: SemanticContextBundleV1 = {
      ...base,
      items: [
        ...base.items.slice(0, 2),
        {
          ...editorItem,
          reference: {
            ...mixedReference,
            document: { ...mixedReference.document, workspaceSlug: "other" },
          },
        },
      ],
    };

    await expect(adapter.attachContext({ ...base, items: [] })).resolves.toMatchObject({
      ok: false,
      code: "EMPTY_CONTEXT",
    });
    await expect(adapter.attachContext({ ...base, items: [...base.items, base.items[0]!] })).resolves.toMatchObject({
      ok: false,
      code: "TOO_MANY_ITEMS",
    });
    await expect(adapter.attachContext(mixed)).resolves.toMatchObject({ ok: false, code: "MIXED_WORKSPACES" });
    expect(hydrate).not.toHaveBeenCalled();
  });

  it("honors cancellation and retains the structured selection failure fixture", async () => {
    const controller = new AbortController();
    controller.abort();
    const consumer = new DummyComposerConsumer();
    const hydrate = vi.fn(async () => hydrationFixture);
    const adapter = createSemanticContextComposerAdapter({ hydration: { hydrate }, consumer });

    const result = await adapter.attachContext(fixtureBundle(), { signal: controller.signal });

    expect(result).toMatchObject({ ok: false, code: "ABORTED" });
    expect(hydrate).not.toHaveBeenCalled();
    expect(isSelectionFailureContractV1(selectionFailureFixture.failure)).toBe(true);
    expect(selectionFailureFixture).toEqual({
      ok: false,
      failure: {
        schemaVersion: 1,
        code: "NO_TARGET",
        message: "No semantic Plane target is available here",
        retryable: false,
      },
    });
  });

  it("reports cancellation while the composer attachment is pending", async () => {
    const controller = new AbortController();
    let finishAttachment: (() => void) | undefined;
    const attachContext = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finishAttachment = resolve;
        })
    );
    const adapter = createSemanticContextComposerAdapter({
      hydration: { hydrate: async () => hydrationFixture },
      consumer: { attachContext },
    });

    const pending = adapter.attachContext(fixtureBundle(), { signal: controller.signal });
    await vi.waitFor(() => expect(attachContext).toHaveBeenCalledOnce());
    controller.abort();
    finishAttachment?.();

    await expect(pending).resolves.toMatchObject({ ok: false, code: "ABORTED" });
  });

  it("rejects entity references without project scope", () => {
    const missingProject = structuredClone(regionFixture);
    const reference = missingProject.items[0]?.reference;
    if (!reference || reference.kind !== "entity") throw new Error("Entity fixture changed");
    delete (reference as Partial<typeof reference>).projectId;

    expect(isSemanticContextBundleV1(missingProject)).toBe(false);

    const mismatchedProject = structuredClone(regionFixture);
    const projectReference = mismatchedProject.items[0]?.reference;
    if (!projectReference || projectReference.kind !== "entity") throw new Error("Entity fixture changed");
    projectReference.entityType = "project";
    expect(isSemanticContextBundleV1(mismatchedProject)).toBe(false);
  });

  it("returns a retryable failure when server hydration throws", async () => {
    const consumer = new DummyComposerConsumer();
    const adapter = createSemanticContextComposerAdapter({
      hydration: { hydrate: async () => Promise.reject(new Error("network unavailable")) },
      consumer,
    });

    await expect(adapter.attachContext(fixtureBundle())).resolves.toMatchObject({
      ok: false,
      code: "HYDRATION_FAILED",
      retryable: true,
    });
    expect(consumer.attachments).toHaveLength(0);
  });

  it("does not call the composer when hydration denies every selected item", async () => {
    const bundle = fixtureBundle();
    const failureCodes = ["FORBIDDEN", "NOT_FOUND", "UNSUPPORTED"] as const;
    const consumer = new DummyComposerConsumer();
    const adapter = createSemanticContextComposerAdapter({
      hydration: {
        hydrate: async () => ({
          schemaVersion: 1,
          results: bundle.items.map(({ reference }, index) => ({
            ok: false,
            reference,
            code: failureCodes[index],
            message: "Denied",
            retryable: false,
          })),
        }),
      },
      consumer,
    });

    await expect(adapter.attachContext(bundle)).resolves.toMatchObject({
      ok: false,
      code: "NO_AUTHORIZED_CONTEXT",
      retryable: false,
    });
    expect(consumer.attachments).toHaveLength(0);
  });

  it("returns a retryable failure when the composer rejects an authorized attachment", async () => {
    const adapter = createSemanticContextComposerAdapter({
      hydration: { hydrate: async () => hydrationFixture },
      consumer: { attachContext: async () => Promise.reject(new Error("draft unavailable")) },
    });

    await expect(adapter.attachContext(fixtureBundle())).resolves.toMatchObject({
      ok: false,
      code: "COMPOSER_FAILED",
      retryable: true,
    });
  });
});

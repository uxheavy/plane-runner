/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Editor, Extension } from "@tiptap/core";
import { StarterKit } from "@tiptap/starter-kit";
import { afterEach, describe, expect, test } from "vitest";
import {
  type ContextSource,
  type PlaneEntityStoreAccess,
  type SelectionAcquisitionAdapter,
  type SemanticReferenceV1,
  createPlaneEditorContextSource,
  createPlaneEntityContextSource,
  createSemanticContextComposerAdapter,
  createSemanticContextPicker,
} from "../src";
import { DummyComposerConsumer } from "./fixtures/dummy-composer-consumer";

const FIXTURE_ATTRIBUTE = "data-plane-context-primary-fixture";
const mounted: HTMLElement[] = [];
const editors: Editor[] = [];

const workItem = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "work_item",
  entityId: "issue-1",
} as const;
const priority = { kind: "field", entity: workItem, fieldKey: "priority" } as const;
const labels = { kind: "field", entity: workItem, fieldKey: "labels" } as const;
const project = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "project",
  entityId: "project-1",
} as const;
const page = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "page",
  entityId: "page-1",
} as const;
const editorBlock = { kind: "editor_block", document: page, blockId: "block-1" } as const;

const BlockId = Extension.create({
  name: "primary-integration-block-id",
  addGlobalAttributes: () => [{ types: ["paragraph"], attributes: { id: { default: null } } }],
});

const mount = (top: number, height: number): HTMLDivElement => {
  const element = document.createElement("div");
  element.setAttribute(FIXTURE_ATTRIBUTE, "");
  Object.assign(element.style, {
    position: "fixed",
    display: "block",
    left: "20px",
    top: `${top}px`,
    width: "240px",
    height: `${height}px`,
  });
  document.body.append(element);
  mounted.push(element);
  return element;
};

afterEach(() => {
  mounted.splice(0).forEach((element) => element.remove());
  editors.splice(0).forEach((editor) => editor.destroy());
});

describe("primary non-UI integration", () => {
  test("captures fresh region context, hydrates partial permission results, and feeds the dummy composer", async () => {
    const records = {
      workItem: {
        id: "issue-1",
        project_id: "project-1",
        sequence_id: 42,
        name: "Initial name",
        state_id: null,
        priority: "low",
        assignee_ids: [],
        label_ids: ["label-1"],
        start_date: null,
        target_date: null,
        estimate_point: null,
        cycle_id: null,
        module_ids: [],
        updated_at: "2026-07-29T08:00:00Z",
      },
      project: {
        id: "project-1",
        name: "Agent Plane",
        identifier: "AGT",
        archived_at: null,
        updated_at: "2026-07-29T08:00:00Z",
      },
    };
    const access: PlaneEntityStoreAccess = {
      getWorkItem: (id) => (id === records.workItem.id ? records.workItem : undefined),
      getProject: (id) => (id === records.project.id ? records.project : undefined),
      getCycle: () => undefined,
      getModule: () => undefined,
      getPage: () => undefined,
      getView: () => undefined,
      getState: () => undefined,
      getLabel: (id) => (id === "label-1" ? { id, name: "Bug" } : undefined),
      getMember: () => undefined,
      getEstimatePoint: () => undefined,
    };
    const entitySource = createPlaneEntityContextSource({ access, now: () => "2026-07-29T09:00:00Z" });
    const editorSource = createPlaneEditorContextSource({
      fallback: entitySource,
      now: () => "2026-07-29T09:00:01Z",
    });
    const editor = new Editor({
      extensions: [StarterKit, BlockId],
      content: {
        type: "doc",
        content: [{ type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Old" }] }],
      },
    });
    editors.push(editor);
    editorSource.registerDocument(page, editor);

    const projectElement = mount(10, 24);
    const workItemElement = mount(35, 100);
    const priorityElement = mount(45, 24);
    const detachedElement = mount(75, 24);
    const editorElement = mount(105, 24);
    let detached = false;
    const source: ContextSource = {
      getLabel: editorSource.getLabel,
      capture: (reference, options) => {
        if (!detached) {
          detached = true;
          detachedElement.remove();
        }
        return editorSource.capture(reference, options);
      },
    };
    const acquisition: SelectionAcquisitionAdapter = {
      getElementsAtPoint: () => [],
      isElementEligible: () => true,
    };
    const picker = createSemanticContextPicker({ acquisition, contextSource: source, getLocation: () => "/acme" });
    picker.register(projectElement, { reference: project });
    picker.register(workItemElement, { reference: workItem });
    picker.register(priorityElement, { reference: priority, parent: workItem });
    picker.register(detachedElement, { reference: labels, parent: workItem });
    picker.register(editorElement, { reference: editorBlock, parent: page });

    records.workItem.priority = "urgent";
    records.workItem.updated_at = "2026-07-29T08:59:59Z";
    editor.commands.setContent({
      type: "doc",
      content: [{ type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Current" }] }],
    });
    const selected = await picker.select({
      operation: "capture",
      area: { kind: "region", left: 0, top: 0, right: 300, bottom: 160 },
    });
    expect(selected).toMatchObject({
      ok: true,
      context: {
        items: [
          { reference: project },
          { reference: priority, observed: { value: "urgent" } },
          { reference: editorBlock, observed: { value: { text: "Current" } } },
        ],
        warnings: [{ code: "TARGET_GONE", reference: labels }],
      },
    });
    if (!selected.ok || selected.operation !== "capture") throw new Error("Expected captured context");

    const consumer = new DummyComposerConsumer();
    const adapter = createSemanticContextComposerAdapter({
      consumer,
      hydration: {
        hydrate: async (_workspace, request) => ({
          schemaVersion: 1,
          results: request.items.map(({ reference }, index) =>
            reference.kind === "field"
              ? { ok: false, reference, code: "FORBIDDEN", message: "Access changed", retryable: false }
              : reference.kind === "editor_block"
                ? {
                    ok: true,
                    reference,
                    resolution: "authorization_only",
                    authorizedAt: "2026-07-29T09:00:02Z",
                    stale: false,
                  }
                : {
                    ok: true,
                    reference,
                    resolution: "canonical",
                    authorizedAt: "2026-07-29T09:00:02Z",
                    stale: index === 0,
                    canonical: {
                      source: "server_canonical",
                      value: { name: "Agent Plane" },
                      resolvedAt: "2026-07-29T09:00:02Z",
                      entityVersion: "2026-07-29T09:00:01Z",
                    },
                  }
          ),
        }),
      },
    });
    const attached = await adapter.attachContext(selected.context);

    expect(attached).toMatchObject({ ok: true, attachment: { hydrationWarnings: [{ code: "FORBIDDEN" }] } });
    expect(consumer.attachments).toHaveLength(1);
    expect(consumer.attachments[0]?.items.map(({ reference }) => reference.kind)).toEqual([
      "entity",
      "editor_block",
    ] satisfies SemanticReferenceV1["kind"][]);
    expect(JSON.stringify(consumer.attachments)).not.toContain("urgent");
    picker.dispose();
  });
});

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Editor, Extension, Node } from "@tiptap/core";
import { Collaboration } from "@tiptap/extension-collaboration";
import { StarterKit } from "@tiptap/starter-kit";
import { afterEach, describe, expect, test } from "vitest";
import * as Y from "yjs";
import {
  type ContextSource,
  type EditorDocumentReferenceV1,
  type EditorRangeReferenceV1,
  type SemanticReferenceV1,
  createPlaneEditorContextSource,
} from "../src";

const observedAt = "2026-07-29T11:00:00.000Z";
const editors: Editor[] = [];
const documents: Y.Doc[] = [];

const documentReference = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "page",
  entityId: "page-1",
} satisfies EditorDocumentReferenceV1;

const BlockId = Extension.create({
  name: "plane-test-block-id",
  addGlobalAttributes() {
    return [
      {
        types: ["paragraph", "heading", "codeBlock", "issue-embed-component", "imageComponent"],
        attributes: { id: { default: null } },
      },
    ];
  },
});

const WorkItemEmbed = Node.create({
  name: "issue-embed-component",
  group: "block",
  atom: true,
  addAttributes() {
    return {
      id: { default: null },
      entity_identifier: { default: null },
      project_identifier: { default: null },
      workspace_identifier: { default: null },
      entity_name: { default: null },
      private_value: { default: null },
    };
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", HTMLAttributes];
  },
});

const ImageEmbed = Node.create({
  name: "imageComponent",
  group: "block",
  atom: true,
  addAttributes() {
    return {
      id: { default: null },
      src: { default: null },
      status: { default: null },
      alt: { default: null },
      private_value: { default: null },
    };
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", HTMLAttributes];
  },
});

const fallback: ContextSource = {
  getLabel: () => "Plane entity",
  capture: () =>
    Promise.resolve({ ok: false, code: "UNSUPPORTED", message: "Not used by editor tests", retryable: false }),
};

const createEditor = (content?: object, ydoc?: Y.Doc): Editor => {
  const editor = new Editor({
    extensions: [
      StarterKit.configure(ydoc ? { history: false } : {}),
      ...(ydoc ? [Collaboration.configure({ document: ydoc, field: "default" })] : []),
      BlockId,
      WorkItemEmbed,
      ImageEmbed,
    ],
    ...(content && !ydoc ? { content } : {}),
  });
  editors.push(editor);
  return editor;
};

const blockReference = (blockId: string): SemanticReferenceV1 => ({
  kind: "editor_block",
  document: documentReference,
  blockId,
});

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy());
  documents.splice(0).forEach((document) => document.destroy());
});

describe("Plane live editor context source", () => {
  test("captures fresh blocks and privacy-safe embed metadata", async () => {
    const editor = createEditor({
      type: "doc",
      content: [
        { type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Initial" }] },
        {
          type: "issue-embed-component",
          attrs: {
            id: "embed-block-1",
            entity_identifier: "issue-uuid-1",
            project_identifier: "AGT",
            workspace_identifier: "acme",
            entity_name: "Fix picker",
            private_value: "must-not-escape",
          },
        },
        {
          type: "imageComponent",
          attrs: {
            id: "asset-1",
            src: "https://signed.example/must-not-escape",
            status: "uploaded",
            alt: "Context diagram",
            private_value: "must-not-escape",
          },
        },
      ],
    });
    const source = createPlaneEditorContextSource({ fallback, now: () => observedAt });
    source.registerDocument(documentReference, editor);

    editor.commands.setContent({
      type: "doc",
      content: [
        { type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Current" }] },
        {
          type: "issue-embed-component",
          attrs: {
            id: "embed-block-1",
            entity_identifier: "issue-uuid-1",
            project_identifier: "AGT",
            workspace_identifier: "acme",
            entity_name: "Fix picker",
            private_value: "must-not-escape",
          },
        },
        {
          type: "imageComponent",
          attrs: {
            id: "asset-1",
            src: "https://signed.example/must-not-escape",
            status: "uploaded",
            alt: "Context diagram",
            private_value: "must-not-escape",
          },
        },
      ],
    });

    await expect(source.capture(blockReference("block-1"), { signal: new AbortController().signal })).resolves.toEqual({
      ok: true,
      observed: {
        source: "client_live",
        observedAt,
        value: { kind: "block", blockId: "block-1", nodeType: "paragraph", text: "Current", metadata: {} },
      },
    });

    const workItem = await source.capture(blockReference("embed-block-1"), { signal: new AbortController().signal });
    expect(workItem).toMatchObject({
      ok: true,
      observed: {
        value: {
          metadata: {
            embed: {
              kind: "work_item",
              entityId: "issue-uuid-1",
              projectIdentifier: "AGT",
              workspaceSlug: "acme",
              name: "Fix picker",
            },
          },
        },
      },
    });

    const image = await source.capture(blockReference("asset-1"), { signal: new AbortController().signal });
    expect(image).toMatchObject({
      ok: true,
      observed: {
        value: {
          metadata: {
            embed: { kind: "image", assetId: "asset-1", status: "uploaded", alt: "Context diagram" },
          },
        },
      },
    });
    expect(JSON.stringify([workItem, image])).not.toContain("must-not-escape");
  });

  test("creates block-relative range identity and resolves its fresh text", async () => {
    const editor = createEditor({
      type: "doc",
      content: [
        { type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Hello" }] },
        { type: "paragraph", attrs: { id: "block-2" }, content: [{ type: "text", text: "World" }] },
      ],
    });
    const source = createPlaneEditorContextSource({ fallback, now: () => observedAt });
    source.registerDocument(documentReference, editor);
    editor.commands.setTextSelection({ from: 2, to: 11 });

    const reference = source.getCurrentRange(documentReference);
    expect(reference).toEqual({
      kind: "editor_range",
      document: documentReference,
      start: { blockId: "block-1", offset: 1 },
      end: { blockId: "block-2", offset: 3 },
    });
    if (!reference) throw new Error("Expected a live editor range reference");
    const rangeReference: EditorRangeReferenceV1 = reference;

    editor.commands.setContent({
      type: "doc",
      content: [
        { type: "paragraph", attrs: { id: "block-1" }, content: [{ type: "text", text: "Hallo" }] },
        { type: "paragraph", attrs: { id: "block-2" }, content: [{ type: "text", text: "World" }] },
      ],
    });
    await expect(source.capture(rangeReference, { signal: new AbortController().signal })).resolves.toMatchObject({
      ok: true,
      observed: {
        source: "client_live",
        value: {
          kind: "range",
          text: "allo\nWor",
          start: { blockId: "block-1", offset: 1 },
          end: { blockId: "block-2", offset: 3 },
        },
      },
    });
  });

  test("observes Yjs-backed edits and keeps replacement registration safe", async () => {
    const ydoc = new Y.Doc();
    documents.push(ydoc);
    const writer = createEditor(undefined, ydoc);
    const reader = createEditor(undefined, ydoc);
    writer.commands.setContent({
      type: "doc",
      content: [{ type: "paragraph", attrs: { id: "shared-block" }, content: [{ type: "text", text: "First" }] }],
    });

    const source = createPlaneEditorContextSource({ fallback, now: () => observedAt });
    const disposeWriter = source.registerDocument(documentReference, writer);
    source.registerDocument(documentReference, reader);
    disposeWriter();
    writer.commands.setContent({
      type: "doc",
      content: [{ type: "paragraph", attrs: { id: "shared-block" }, content: [{ type: "text", text: "Second" }] }],
    });
    await Promise.resolve();

    await expect(
      source.capture(blockReference("shared-block"), { signal: new AbortController().signal })
    ).resolves.toMatchObject({ ok: true, observed: { source: "client_live", value: { text: "Second" } } });
  });

  test("fails closed for unregistered, duplicate, and destroyed editor targets", async () => {
    const source = createPlaneEditorContextSource({ fallback, now: () => observedAt });
    await expect(
      source.capture(blockReference("missing"), { signal: new AbortController().signal })
    ).resolves.toMatchObject({ ok: false, code: "VALUE_UNAVAILABLE" });

    const duplicateEditor = createEditor({
      type: "doc",
      content: [
        { type: "paragraph", attrs: { id: "duplicate" }, content: [{ type: "text", text: "One" }] },
        { type: "paragraph", attrs: { id: "duplicate" }, content: [{ type: "text", text: "Two" }] },
      ],
    });
    source.registerDocument(documentReference, duplicateEditor);
    await expect(
      source.capture(blockReference("duplicate"), { signal: new AbortController().signal })
    ).resolves.toMatchObject({ ok: false, code: "VALUE_UNAVAILABLE" });

    duplicateEditor.destroy();
    await expect(
      source.capture(blockReference("duplicate"), { signal: new AbortController().signal })
    ).resolves.toMatchObject({ ok: false, code: "VALUE_UNAVAILABLE" });
  });
});

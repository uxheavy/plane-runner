/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  ContextSource,
  ContextSourceCaptureResult,
  EditorDocumentReferenceV1,
  EditorRangePointV1,
  EditorRangeReferenceV1,
  JsonValue,
  SemanticReferenceV1,
} from "./contracts";

type TiptapNodeContextPort = {
  readonly type: { readonly name: string };
  readonly attrs: Readonly<Record<string, unknown>>;
  readonly textContent: string;
  readonly nodeSize: number;
  readonly content: { readonly size: number };
  readonly isTextblock: boolean;
  descendants(callback: (node: TiptapNodeContextPort, position: number) => boolean | void): void;
};

export type TiptapEditorContextPort = {
  readonly isDestroyed: boolean;
  readonly state: {
    readonly doc: TiptapNodeContextPort & {
      textBetween(from: number, to: number, blockSeparator?: string, leafText?: string): string;
    };
    readonly selection: { readonly from: number; readonly to: number; readonly empty: boolean };
  };
};

export type PlaneEditorContextSourceOptions = {
  fallback: ContextSource;
  now?: () => string;
};

export interface PlaneEditorContextSource extends ContextSource {
  registerDocument(document: EditorDocumentReferenceV1, editor: TiptapEditorContextPort): () => void;
  getCurrentRange(document: EditorDocumentReferenceV1): EditorRangeReferenceV1 | undefined;
}

type EditorRegistration = {
  document: EditorDocumentReferenceV1;
  editor: TiptapEditorContextPort;
};

type LocatedNode = {
  node: TiptapNodeContextPort;
  position: number;
};

const unavailable = (message: string): ContextSourceCaptureResult => ({
  ok: false,
  code: "VALUE_UNAVAILABLE",
  message,
  retryable: true,
});

const documentKey = (document: EditorDocumentReferenceV1): string =>
  [document.workspaceSlug, document.projectId ?? "", document.entityType, document.entityId].join(":");

const blockId = (node: TiptapNodeContextPort): string | undefined => {
  const id = node.attrs.id;
  return typeof id === "string" && id.length > 0 ? id : undefined;
};

const findNodesById = (editor: TiptapEditorContextPort, id: string): LocatedNode[] => {
  const matches: LocatedNode[] = [];
  editor.state.doc.descendants((node, position) => {
    if (blockId(node) === id) matches.push({ node, position });
  });
  return matches;
};

const findTextBlockAt = (
  editor: TiptapEditorContextPort,
  absolutePosition: number,
  endpoint: "start" | "end"
): LocatedNode | undefined => {
  const candidates: LocatedNode[] = [];
  editor.state.doc.descendants((node, position) => {
    if (!node.isTextblock || !blockId(node)) return;
    const contentStart = position + 1;
    const contentEnd = contentStart + node.content.size;
    if (absolutePosition >= contentStart && absolutePosition <= contentEnd) candidates.push({ node, position });
  });

  return candidates.toSorted((left, right) => {
    const leftStart = left.position + 1;
    const rightStart = right.position + 1;
    const leftEnd = leftStart + left.node.content.size;
    const rightEnd = rightStart + right.node.content.size;
    const leftBoundaryPenalty =
      endpoint === "start" ? Number(absolutePosition === leftEnd) : Number(absolutePosition === leftStart);
    const rightBoundaryPenalty =
      endpoint === "start" ? Number(absolutePosition === rightEnd) : Number(absolutePosition === rightStart);
    return leftBoundaryPenalty - rightBoundaryPenalty || left.node.nodeSize - right.node.nodeSize;
  })[0];
};

const stringAttribute = (node: TiptapNodeContextPort, name: string): string | null => {
  const value = node.attrs[name];
  return typeof value === "string" ? value : null;
};

const blockMetadata = (node: TiptapNodeContextPort): Record<string, JsonValue> => {
  switch (node.type.name) {
    case "heading": {
      const level = node.attrs.level;
      return { level: typeof level === "number" ? level : null };
    }
    case "codeBlock":
      return { language: stringAttribute(node, "language") };
    case "taskItem": {
      const checked = node.attrs.checked;
      return { checked: typeof checked === "boolean" ? checked : null };
    }
    case "issue-embed-component":
      return {
        embed: {
          kind: "work_item",
          entityId: stringAttribute(node, "entity_identifier"),
          projectIdentifier: stringAttribute(node, "project_identifier"),
          workspaceSlug: stringAttribute(node, "workspace_identifier"),
          name: stringAttribute(node, "entity_name"),
        },
      };
    case "image":
    case "imageComponent":
      return {
        embed: {
          kind: "image",
          assetId: stringAttribute(node, "id"),
          status: stringAttribute(node, "status"),
          alt: stringAttribute(node, "alt"),
        },
      };
    default:
      return {};
  }
};

const captureBlock = (
  editor: TiptapEditorContextPort,
  reference: Extract<SemanticReferenceV1, { kind: "editor_block" }>,
  observedAt: string
): ContextSourceCaptureResult => {
  const matches = findNodesById(editor, reference.blockId);
  if (matches.length !== 1) {
    return unavailable(
      matches.length === 0 ? "The editor block is not available" : "The editor block identity is ambiguous"
    );
  }
  const node = matches[0]?.node;
  if (!node) return unavailable("The editor block is not available");

  return {
    ok: true,
    observed: {
      source: "client_live",
      observedAt,
      value: {
        kind: "block",
        blockId: reference.blockId,
        nodeType: node.type.name,
        text: node.textContent,
        metadata: blockMetadata(node),
      },
    },
  };
};

const isValidRangePoint = (point: EditorRangePointV1, node: TiptapNodeContextPort): boolean =>
  Number.isInteger(point.offset) && point.offset >= 0 && point.offset <= node.content.size;

const captureRange = (
  editor: TiptapEditorContextPort,
  reference: EditorRangeReferenceV1,
  observedAt: string
): ContextSourceCaptureResult => {
  const startMatches = findNodesById(editor, reference.start.blockId);
  const endMatches = findNodesById(editor, reference.end.blockId);
  if (startMatches.length !== 1 || endMatches.length !== 1) {
    return unavailable("The editor range block identity is missing or ambiguous");
  }
  const start = startMatches[0];
  const end = endMatches[0];
  if (!start || !end || !start.node.isTextblock || !end.node.isTextblock) {
    return unavailable("The editor range endpoints are not text blocks");
  }
  if (!isValidRangePoint(reference.start, start.node) || !isValidRangePoint(reference.end, end.node)) {
    return unavailable("The editor range offsets are no longer valid");
  }

  const from = start.position + 1 + reference.start.offset;
  const to = end.position + 1 + reference.end.offset;
  if (from > to) return unavailable("The editor range endpoints are reversed");

  return {
    ok: true,
    observed: {
      source: "client_live",
      observedAt,
      value: {
        kind: "range",
        text: editor.state.doc.textBetween(from, to, "\n", "\uFFFC"),
        start: { ...reference.start },
        end: { ...reference.end },
      },
    },
  };
};

export const createPlaneEditorContextSource = ({
  fallback,
  now = () => new Date().toISOString(),
}: PlaneEditorContextSourceOptions): PlaneEditorContextSource => {
  const registrations = new Map<string, EditorRegistration>();

  const liveRegistration = (document: EditorDocumentReferenceV1): EditorRegistration | undefined => {
    const registration = registrations.get(documentKey(document));
    if (!registration || registration.editor.isDestroyed) return undefined;
    return registration;
  };

  return {
    registerDocument: (document, editor) => {
      const key = documentKey(document);
      const registration = { document: { ...document }, editor } satisfies EditorRegistration;
      registrations.set(key, registration);
      return () => {
        if (registrations.get(key) === registration) registrations.delete(key);
      };
    },
    getCurrentRange: (document) => {
      const registration = liveRegistration(document);
      if (!registration) return undefined;
      const { selection } = registration.editor.state;
      if (selection.empty) return undefined;
      const start = findTextBlockAt(registration.editor, selection.from, "start");
      const end = findTextBlockAt(registration.editor, selection.to, "end");
      const startBlockId = start ? blockId(start.node) : undefined;
      const endBlockId = end ? blockId(end.node) : undefined;
      if (!start || !end || !startBlockId || !endBlockId) return undefined;

      return {
        kind: "editor_range",
        document: { ...registration.document },
        start: { blockId: startBlockId, offset: selection.from - (start.position + 1) },
        end: { blockId: endBlockId, offset: selection.to - (end.position + 1) },
      };
    },
    getLabel: (reference) => {
      if (reference.kind === "editor_block") return `Editor block ${reference.blockId}`;
      if (reference.kind === "editor_range") return "Editor selection";
      return fallback.getLabel(reference);
    },
    capture: (reference, options) => {
      if (reference.kind !== "editor_block" && reference.kind !== "editor_range") {
        return fallback.capture(reference, options);
      }
      const registration = liveRegistration(reference.document);
      if (!registration) return Promise.resolve(unavailable("The live editor document is not registered"));
      const observedAt = now();
      return Promise.resolve(
        reference.kind === "editor_block"
          ? captureBlock(registration.editor, reference, observedAt)
          : captureRange(registration.editor, reference, observedAt)
      );
    },
  };
};

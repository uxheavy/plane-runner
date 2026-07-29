/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ViewportPoint } from "./react-grab-selection-adapter";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type EntityReferenceV1 = {
  readonly kind: "entity";
  readonly workspaceSlug: string;
  readonly projectId?: string;
  readonly entityType: "work_item" | "project" | "cycle" | "module" | "page" | "view";
  readonly entityId: string;
};

export type WorkItemContextField =
  | "name"
  | "description"
  | "state"
  | "priority"
  | "assignees"
  | "labels"
  | "start_date"
  | "target_date"
  | "estimate"
  | "cycle"
  | "module";

export type EditorDocumentReferenceV1 = EntityReferenceV1 & { readonly entityType: "page" | "work_item" };

export type EditorRangePointV1 = {
  readonly blockId: string;
  readonly offset: number;
};

export type EditorBlockReferenceV1 = {
  readonly kind: "editor_block";
  readonly document: EditorDocumentReferenceV1;
  readonly blockId: string;
};

export type EditorRangeReferenceV1 = {
  readonly kind: "editor_range";
  readonly document: EditorDocumentReferenceV1;
  readonly start: EditorRangePointV1;
  readonly end: EditorRangePointV1;
};

export type SemanticReferenceV1 =
  | EntityReferenceV1
  | {
      readonly kind: "field";
      readonly entity: EntityReferenceV1 & { readonly entityType: "work_item"; readonly projectId: string };
      readonly fieldKey: WorkItemContextField;
    }
  | EditorBlockReferenceV1
  | EditorRangeReferenceV1;

export type SemanticTarget = {
  readonly reference: SemanticReferenceV1;
  readonly parent?: SemanticReferenceV1;
};

export type SelectionArea =
  | ({ kind: "point" } & ViewportPoint)
  | { kind: "region"; left: number; top: number; right: number; bottom: number };

export type SelectionRequest = {
  operation: "preview" | "capture";
  area: SelectionArea;
  ancestorOffset?: number;
  signal?: AbortSignal;
};

export type ContextCandidateV1 = {
  schemaVersion: 1;
  reference: SemanticReferenceV1;
  label: string;
  selectableAncestors: SemanticReferenceV1[];
};

export type ContextObservationV1 = {
  source: "client_store" | "client_live";
  value: JsonValue;
  observedAt: string;
  entityVersion?: string;
};

export type ContextItemV1 = {
  reference: SemanticReferenceV1;
  observed: ContextObservationV1;
  location: { url: string };
};

export type SelectionFailureCode =
  | "NO_TARGET"
  | "TARGET_GONE"
  | "UNSUPPORTED"
  | "VALUE_UNAVAILABLE"
  | "ABORTED"
  | "TOO_MANY_TARGETS";

export type SelectionFailureV1 = {
  schemaVersion: 1;
  code: SelectionFailureCode;
  message: string;
  reference?: SemanticReferenceV1;
  retryable: boolean;
};

export type SemanticContextBundleV1 = {
  schemaVersion: 1;
  selectionKind: SelectionArea["kind"];
  items: ContextItemV1[];
  warnings: SelectionFailureV1[];
};

export type SelectionResult =
  | { ok: true; operation: "preview"; candidates: ContextCandidateV1[] }
  | { ok: true; operation: "capture"; context: SemanticContextBundleV1 }
  | { ok: false; failure: SelectionFailureV1 };

export type ContextSourceCaptureResult =
  | { ok: true; observed: ContextObservationV1 }
  | {
      ok: false;
      code: "UNSUPPORTED" | "VALUE_UNAVAILABLE";
      message: string;
      retryable: boolean;
    };

export interface ContextSource {
  getLabel(reference: SemanticReferenceV1): string;
  capture(reference: SemanticReferenceV1, options: { signal: AbortSignal }): Promise<ContextSourceCaptureResult>;
}

export interface SelectionAcquisitionAdapter {
  getElementsAtPoint(point: ViewportPoint): readonly Element[];
  isElementEligible(element: Element): boolean;
}

export type SemanticContextPickerOptions = {
  acquisition: SelectionAcquisitionAdapter;
  contextSource: ContextSource;
  getLocation: () => string;
  maxRegionTargets?: number;
};

export interface SemanticContextPicker {
  register(element: Element, target: SemanticTarget): () => void;
  select(request: SelectionRequest): Promise<SelectionResult>;
  dispose(): void;
}

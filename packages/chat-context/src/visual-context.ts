/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { SelectionArea, SemanticContextBundleV1, SemanticReferenceV1 } from "./contracts";
import { PLANE_CONTEXT_IGNORE_ATTRIBUTE } from "./react-grab-selection-adapter";

export const PLANE_CONTEXT_SENSITIVE_ATTRIBUTE = "data-plane-context-sensitive";

const REACT_GRAB_IGNORE_ATTRIBUTE = "data-react-grab-ignore";
const SENSITIVE_SELECTOR = [
  `[${PLANE_CONTEXT_SENSITIVE_ATTRIBUTE}]`,
  'input[type="password"]',
  'input[autocomplete="current-password"]',
  'input[autocomplete="new-password"]',
  'input[autocomplete="one-time-code"]',
  "iframe",
].join(",");
const IGNORED_SELECTOR = [
  `[${PLANE_CONTEXT_IGNORE_ATTRIBUTE}]`,
  `[${REACT_GRAB_IGNORE_ATTRIBUTE}]`,
  SENSITIVE_SELECTOR,
].join(",");

export type VisualCaptureRegionV1 = {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
};

export type VisualRenderRequest = {
  readonly root: HTMLElement;
  readonly region: VisualCaptureRegionV1;
  readonly signal: AbortSignal;
  readonly shouldIgnore: (element: Element) => boolean;
};

export type VisualRenderResult = {
  readonly blob: Blob;
  readonly width: number;
  readonly height: number;
};

export interface VisualRegionRendererPort {
  render(request: VisualRenderRequest): Promise<VisualRenderResult>;
}

export type VisualSnapshotPreviewV1 = {
  readonly schemaVersion: 1;
  readonly kind: "visual_snapshot";
  readonly semantic: false;
  readonly status: "pending_review";
  readonly mimeType: "image/png";
  readonly blob: Blob;
  readonly width: number;
  readonly height: number;
  readonly capturedAt: string;
  readonly region: VisualCaptureRegionV1;
  readonly references: readonly SemanticReferenceV1[];
};

export type VisualSnapshotAttachmentV1 = Omit<VisualSnapshotPreviewV1, "status"> & {
  readonly status: "confirmed";
};

export type VisualCaptureFailureCode =
  | "INVALID_REGION"
  | "SENSITIVE_CONTENT"
  | "TOO_LARGE"
  | "CAPTURE_FAILED"
  | "INVALID_CAPTURE"
  | "ABORTED"
  | "PREVIEW_EXPIRED";

export type VisualCaptureFailure = {
  readonly ok: false;
  readonly code: VisualCaptureFailureCode;
  readonly message: string;
  readonly retryable: boolean;
};

export type VisualPreviewResult =
  | { readonly ok: true; readonly preview: VisualSnapshotPreviewV1 }
  | VisualCaptureFailure;

export type VisualConfirmationResult =
  | { readonly ok: true; readonly attachment: VisualSnapshotAttachmentV1 }
  | VisualCaptureFailure;

export interface VisualContextCapture {
  capturePreview(
    area: Extract<SelectionArea, { kind: "region" }>,
    options?: { readonly semanticContext?: SemanticContextBundleV1; readonly signal?: AbortSignal }
  ): Promise<VisualPreviewResult>;
  confirm(preview: VisualSnapshotPreviewV1): VisualConfirmationResult;
  discard(preview: VisualSnapshotPreviewV1): void;
  dispose(): void;
}

export type VisualContextCaptureOptions = {
  readonly document: Document;
  readonly renderer: VisualRegionRendererPort;
  readonly now?: () => Date;
  readonly maximumPixels?: number;
  readonly maximumBlobBytes?: number;
};

const failure = (code: VisualCaptureFailureCode, message: string, retryable: boolean): VisualCaptureFailure => ({
  ok: false,
  code,
  message,
  retryable,
});

const intersects = (bounds: DOMRect, region: VisualCaptureRegionV1): boolean =>
  bounds.width > 0 &&
  bounds.height > 0 &&
  bounds.right > region.left &&
  bounds.left < region.left + region.width &&
  bounds.bottom > region.top &&
  bounds.top < region.top + region.height;

const queryElementsDeep = (root: Document | ShadowRoot, selector: string): Element[] => {
  const matches = [...root.querySelectorAll(selector)];
  root.querySelectorAll("*").forEach((element) => {
    if (element.shadowRoot) matches.push(...queryElementsDeep(element.shadowRoot, selector));
  });
  return matches;
};

const referenceKey = (reference: SemanticReferenceV1): string => JSON.stringify(reference);

const uniqueReferences = (context?: SemanticContextBundleV1): SemanticReferenceV1[] => {
  const seen = new Set<string>();
  return (context?.items ?? []).flatMap(({ reference }) => {
    const key = referenceKey(reference);
    if (seen.has(key)) return [];
    seen.add(key);
    return [structuredClone(reference)];
  });
};

const normalizeRegion = (
  area: Extract<SelectionArea, { kind: "region" }>,
  viewportWidth: number,
  viewportHeight: number
): VisualCaptureRegionV1 | undefined => {
  if (![area.left, area.top, area.right, area.bottom].every(Number.isFinite)) return undefined;
  const left = Math.max(0, Math.min(area.left, area.right, viewportWidth));
  const right = Math.max(0, Math.min(Math.max(area.left, area.right), viewportWidth));
  const top = Math.max(0, Math.min(area.top, area.bottom, viewportHeight));
  const bottom = Math.max(0, Math.min(Math.max(area.top, area.bottom), viewportHeight));
  const width = Math.round(right - left);
  const height = Math.round(bottom - top);
  if (width < 1 || height < 1) return undefined;
  return { left: Math.round(left), top: Math.round(top), width, height };
};

export const createVisualContextCapture = ({
  document,
  renderer,
  now = () => new Date(),
  maximumPixels = 4_000_000,
  maximumBlobBytes = 8_000_000,
}: VisualContextCaptureOptions): VisualContextCapture => {
  const livePreviews = new WeakSet<VisualSnapshotPreviewV1>();
  let disposed = false;

  const retire = (preview: VisualSnapshotPreviewV1): void => {
    livePreviews.delete(preview);
  };

  return {
    async capturePreview(area, options = {}) {
      if (disposed || options.signal?.aborted) {
        return failure("ABORTED", "Visual capture was cancelled", true);
      }
      const view = document.defaultView;
      const root = document.documentElement;
      if (!view || !root) return failure("CAPTURE_FAILED", "The capture document is unavailable", true);
      const region = normalizeRegion(area, view.innerWidth, view.innerHeight);
      if (!region) return failure("INVALID_REGION", "The visual region is outside the visible viewport", false);
      if (region.width * region.height > maximumPixels) {
        return failure("TOO_LARGE", "The visual region exceeds the pixel limit", false);
      }
      const sensitive = queryElementsDeep(document, SENSITIVE_SELECTOR).find((element) =>
        intersects(element.getBoundingClientRect(), region)
      );
      if (sensitive) {
        return failure("SENSITIVE_CONTENT", "The visual region intersects content that cannot be captured", false);
      }

      const controller = new AbortController();
      const abort = (): void => controller.abort();
      options.signal?.addEventListener("abort", abort, { once: true });
      try {
        const rendered = await renderer.render({
          root,
          region,
          signal: controller.signal,
          shouldIgnore: (element) => element.matches(IGNORED_SELECTOR) || element.closest(IGNORED_SELECTOR) !== null,
        });
        if (disposed || controller.signal.aborted || options.signal?.aborted) {
          return failure("ABORTED", "Visual capture was cancelled", true);
        }
        if (
          rendered.width !== region.width ||
          rendered.height !== region.height ||
          rendered.blob.type !== "image/png"
        ) {
          return failure("INVALID_CAPTURE", "The renderer returned an unexpected crop or media type", false);
        }
        if (rendered.blob.size > maximumBlobBytes) {
          return failure("TOO_LARGE", "The visual snapshot exceeds the byte limit", false);
        }
        const preview = Object.freeze({
          schemaVersion: 1,
          kind: "visual_snapshot",
          semantic: false,
          status: "pending_review",
          mimeType: "image/png",
          blob: rendered.blob,
          width: rendered.width,
          height: rendered.height,
          capturedAt: now().toISOString(),
          region,
          references: Object.freeze(uniqueReferences(options.semanticContext)),
        } as const satisfies VisualSnapshotPreviewV1);
        livePreviews.add(preview);
        return { ok: true, preview };
      } catch {
        if (disposed || controller.signal.aborted || options.signal?.aborted) {
          return failure("ABORTED", "Visual capture was cancelled", true);
        }
        return failure("CAPTURE_FAILED", "The visual region could not be captured", true);
      } finally {
        options.signal?.removeEventListener("abort", abort);
      }
    },
    confirm(preview) {
      if (disposed || !livePreviews.has(preview)) {
        return failure("PREVIEW_EXPIRED", "The visual preview is no longer available", false);
      }
      retire(preview);
      return { ok: true, attachment: { ...preview, status: "confirmed" } };
    },
    discard: retire,
    dispose: () => {
      disposed = true;
    },
  };
};

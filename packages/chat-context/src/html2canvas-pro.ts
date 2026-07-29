/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import renderHtmlToCanvas from "html2canvas-pro";

import type { VisualRegionRendererPort } from "./visual-context";

const canvasToPng = (canvas: HTMLCanvasElement): Promise<Blob | null> =>
  new Promise((resolve) => canvas.toBlob(resolve, "image/png"));

/**
 * Plane's sole production DOM screenshot adapter.
 *
 * Import this adapter from `@plane/chat-context/html2canvas-pro` so consumers
 * that only need semantic context do not pay for the renderer bundle.
 */
export const createHtml2CanvasProVisualRenderer = (): VisualRegionRendererPort => ({
  async render({ root, region, signal, shouldIgnore }) {
    if (signal.aborted) throw new DOMException("Visual capture was cancelled", "AbortError");
    const view = root.ownerDocument.defaultView;
    if (!view) throw new Error("The capture document has no browser window");

    const canvas = await renderHtmlToCanvas(root, {
      allowTaint: false,
      backgroundColor: null,
      height: region.height,
      ignoreElements: shouldIgnore,
      imageTimeout: 5_000,
      logging: false,
      removeContainer: true,
      scale: 1,
      scrollX: view.scrollX,
      scrollY: view.scrollY,
      signal,
      useCORS: false,
      width: region.width,
      windowHeight: view.innerHeight,
      windowWidth: view.innerWidth,
      x: view.scrollX + region.left,
      y: view.scrollY + region.top,
    });

    if (signal.aborted) throw new DOMException("Visual capture was cancelled", "AbortError");
    const blob = await canvasToPng(canvas);
    if (!blob) throw new Error("The rendered canvas could not be encoded as PNG");
    return { blob, width: canvas.width, height: canvas.height };
  },
});

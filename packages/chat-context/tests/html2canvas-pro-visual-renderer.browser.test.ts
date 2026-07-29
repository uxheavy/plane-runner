/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { afterEach, describe, expect, test } from "vitest";
import { PLANE_CONTEXT_IGNORE_ATTRIBUTE, createVisualContextCapture } from "../src";
import { createHtml2CanvasProVisualRenderer } from "../src/html2canvas-pro";

const FIXTURE_ATTRIBUTE = "data-plane-context-html2canvas-pro-fixture";

const nextFrame = (): Promise<void> => new Promise((resolve) => requestAnimationFrame(() => resolve()));

const readCenterPixel = async (blob: Blob): Promise<readonly [number, number, number, number]> => {
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D context is unavailable");
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const { data } = context.getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1);
  return [data[0], data[1], data[2], data[3]];
};

afterEach(() => {
  document.querySelectorAll(`[${FIXTURE_ATTRIBUTE}]`).forEach((element) => element.remove());
});

describe("html2canvas-pro visual renderer", () => {
  test("renders an exact modern-CSS crop while excluding Plane picker chrome", async () => {
    const surface = document.createElement("div");
    surface.setAttribute(FIXTURE_ATTRIBUTE, "");
    Object.assign(surface.style, {
      position: "fixed",
      display: "block",
      left: "40px",
      top: "40px",
      width: "64px",
      height: "48px",
      backgroundColor: "oklch(62% 0.19 145)",
    });
    const pickerChrome = document.createElement("div");
    pickerChrome.setAttribute(PLANE_CONTEXT_IGNORE_ATTRIBUTE, "");
    Object.assign(pickerChrome.style, {
      position: "absolute",
      inset: "0",
      backgroundColor: "rgb(255, 0, 0)",
    });
    surface.append(pickerChrome);
    document.body.append(surface);
    await nextFrame();

    const bounds = surface.getBoundingClientRect();
    const capture = createVisualContextCapture({
      document,
      renderer: createHtml2CanvasProVisualRenderer(),
    });
    const result = await capture.capturePreview({
      kind: "region",
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom,
    });

    expect(result).toMatchObject({
      ok: true,
      preview: { width: 64, height: 48, mimeType: "image/png", semantic: false },
    });
    if (!result.ok) throw new Error(`Expected a rendered preview, received ${result.code}`);
    const [red, green, blue, alpha] = await readCenterPixel(result.preview.blob);
    expect(alpha).toBe(255);
    expect(green).toBeGreaterThan(red);
    expect(green).toBeGreaterThan(blue);
  });

  test("honors an already-aborted capture without rendering", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      createHtml2CanvasProVisualRenderer().render({
        root: document.documentElement,
        region: { left: 0, top: 0, width: 20, height: 20 },
        signal: controller.signal,
        shouldIgnore: () => false,
      })
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});

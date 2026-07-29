import { afterEach, describe, expect, test, vi } from "vitest";
import {
  PLANE_CONTEXT_IGNORE_ATTRIBUTE,
  PLANE_CONTEXT_SENSITIVE_ATTRIBUTE,
  type SemanticContextBundleV1,
  type VisualRegionRendererPort,
  createVisualContextCapture,
} from "../src";

const FIXTURE_ATTRIBUTE = "data-plane-context-visual-fixture";

const reference = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "work_item",
  entityId: "issue-1",
} as const;

const semanticContext = {
  schemaVersion: 1,
  selectionKind: "region",
  items: [
    {
      reference,
      observed: { source: "client_store", value: { name: "Visible title" }, observedAt: "2026-07-29T09:00:00Z" },
      location: { url: "/acme/project-1/issue-1" },
    },
    {
      reference,
      observed: { source: "client_store", value: { name: "Duplicate" }, observedAt: "2026-07-29T09:00:01Z" },
      location: { url: "/acme/project-1/issue-1" },
    },
  ],
  warnings: [],
} satisfies SemanticContextBundleV1;

const mount = (tagName = "div", styles: Partial<CSSStyleDeclaration> = {}): HTMLElement => {
  const element = document.createElement(tagName);
  element.setAttribute(FIXTURE_ATTRIBUTE, "");
  Object.assign(element.style, { position: "fixed", display: "block", ...styles });
  document.body.append(element);
  return element;
};

const png = (width: number, height: number, bytes = 3): VisualRegionRendererPort => ({
  render: vi.fn(async () => ({ blob: new Blob([new Uint8Array(bytes)], { type: "image/png" }), width, height })),
});

afterEach(() => {
  document.querySelectorAll(`[${FIXTURE_ATTRIBUTE}]`).forEach((element) => element.remove());
});

describe("privacy-safe visual context", () => {
  test("captures only the normalized viewport crop and keeps deduplicated semantic references separate", async () => {
    const renderer = png(70, 50);
    const capture = createVisualContextCapture({
      document,
      renderer,
      now: () => new Date("2026-07-29T10:00:00Z"),
    });

    const result = await capture.capturePreview(
      { kind: "region", left: 90, top: 70, right: 20, bottom: 20 },
      { semanticContext }
    );

    expect(result).toMatchObject({
      ok: true,
      preview: {
        kind: "visual_snapshot",
        semantic: false,
        status: "pending_review",
        mimeType: "image/png",
        width: 70,
        height: 50,
        region: { left: 20, top: 20, width: 70, height: 50 },
        references: [reference],
      },
    });
    expect(renderer.render).toHaveBeenCalledTimes(1);
    if (!result.ok) throw new Error("Expected a visual preview");
    expect(capture.confirm(result.preview)).toMatchObject({
      ok: true,
      attachment: { status: "confirmed", semantic: false, references: [reference] },
    });
    expect(capture.confirm(result.preview)).toMatchObject({ ok: false, code: "PREVIEW_EXPIRED" });
  });

  test.each([
    ["Plane sensitive marker", () => mount().setAttribute(PLANE_CONTEXT_SENSITIVE_ATTRIBUTE, "")],
    ["password input", () => mount("input").setAttribute("type", "password")],
    ["authentication autocomplete", () => mount("input").setAttribute("autocomplete", "one-time-code")],
    ["iframe", () => mount("iframe")],
    [
      "open shadow-root secret",
      () => {
        const host = mount();
        const secret = document.createElement("input");
        secret.type = "password";
        Object.assign(secret.style, { display: "block", width: "100px", height: "40px" });
        host.attachShadow({ mode: "open" }).append(secret);
      },
    ],
  ])("denies %s before any pixels are rendered", async (_name, configure) => {
    const renderer = png(100, 40);
    const element = document.querySelector(`[${FIXTURE_ATTRIBUTE}]`) ?? undefined;
    element?.remove();
    configure();
    const sensitive = document.querySelector(`[${FIXTURE_ATTRIBUTE}]`) as HTMLElement;
    Object.assign(sensitive.style, { left: "20px", top: "20px", width: "100px", height: "40px" });
    const capture = createVisualContextCapture({ document, renderer });

    await expect(
      capture.capturePreview({ kind: "region", left: 10, top: 10, right: 140, bottom: 80 })
    ).resolves.toMatchObject({ ok: false, code: "SENSITIVE_CONTENT", retryable: false });
    expect(renderer.render).not.toHaveBeenCalled();
  });

  test("always excludes picker chrome and newly introduced sensitive nodes from the renderer", async () => {
    const ignored = mount();
    ignored.setAttribute(PLANE_CONTEXT_IGNORE_ATTRIBUTE, "");
    const renderer: VisualRegionRendererPort = {
      render: vi.fn(async ({ shouldIgnore, region }) => {
        const lateSecret = document.createElement("input");
        lateSecret.type = "password";
        expect(shouldIgnore(ignored)).toBe(true);
        expect(shouldIgnore(lateSecret)).toBe(true);
        return { blob: new Blob(["png"], { type: "image/png" }), width: region.width, height: region.height };
      }),
    };
    const capture = createVisualContextCapture({ document, renderer });

    await expect(
      capture.capturePreview({ kind: "region", left: 10, top: 10, right: 80, bottom: 60 })
    ).resolves.toMatchObject({ ok: true });
  });

  test("rejects invalid, oversized, and renderer-mismatched regions", async () => {
    const renderer = png(99, 40);
    const capture = createVisualContextCapture({ document, renderer, maximumPixels: 5_000 });

    await expect(
      capture.capturePreview({ kind: "region", left: Number.NaN, top: 0, right: 20, bottom: 20 })
    ).resolves.toMatchObject({ ok: false, code: "INVALID_REGION" });
    await expect(
      capture.capturePreview({ kind: "region", left: 0, top: 0, right: 100, bottom: 100 })
    ).resolves.toMatchObject({ ok: false, code: "TOO_LARGE" });
    await expect(
      capture.capturePreview({ kind: "region", left: 0, top: 0, right: 100, bottom: 40 })
    ).resolves.toMatchObject({ ok: false, code: "INVALID_CAPTURE" });
  });

  test("requires a live reviewed preview and cancels late capture", async () => {
    let finish: ((value: Awaited<ReturnType<VisualRegionRendererPort["render"]>>) => void) | undefined;
    const renderer: VisualRegionRendererPort = {
      render: () => new Promise((resolve) => (finish = resolve)),
    };
    const capture = createVisualContextCapture({ document, renderer });
    const pending = capture.capturePreview({ kind: "region", left: 0, top: 0, right: 80, bottom: 50 });
    await Promise.resolve();
    capture.dispose();
    finish?.({ blob: new Blob(["png"], { type: "image/png" }), width: 80, height: 50 });

    await expect(pending).resolves.toMatchObject({ ok: false, code: "ABORTED" });
  });
});

import { afterEach, describe, expect, test } from "vitest";
import { PLANE_CONTEXT_IGNORE_ATTRIBUTE, createReactGrabSelectionAdapter } from "../src";

const FIXTURE_ATTRIBUTE = "data-plane-context-test-fixture";
const initialUrl = window.location.href;

const mountFixture = (): HTMLDivElement => {
  const fixture = document.createElement("div");
  fixture.setAttribute(FIXTURE_ATTRIBUTE, "");
  document.body.append(fixture);
  return fixture;
};

const position = (element: HTMLElement, styles: Partial<CSSStyleDeclaration>): void => {
  Object.assign(element.style, {
    position: "fixed",
    display: "block",
    ...styles,
  });
};

const center = (element: Element): { clientX: number; clientY: number } => {
  const bounds = element.getBoundingClientRect();
  return {
    clientX: bounds.left + bounds.width / 2,
    clientY: bounds.top + bounds.height / 2,
  };
};

afterEach(() => {
  document.querySelectorAll(`[${FIXTURE_ATTRIBUTE}]`).forEach((fixture) => fixture.remove());
  window.history.replaceState(null, "", initialUrl);
});

describe("React Grab selection adapter", () => {
  test("selects the nested target while ignored overlays cannot intercept it", () => {
    const fixture = mountFixture();
    const entity = document.createElement("article");
    const field = document.createElement("button");
    const planeOverlay = document.createElement("div");
    const reactGrabOverlay = document.createElement("div");

    position(entity, { left: "40px", top: "40px", width: "240px", height: "120px" });
    position(field, { left: "80px", top: "70px", width: "100px", height: "40px" });
    position(planeOverlay, { left: "80px", top: "70px", width: "100px", height: "40px", zIndex: "20" });
    position(reactGrabOverlay, { left: "80px", top: "70px", width: "100px", height: "40px", zIndex: "30" });
    planeOverlay.setAttribute(PLANE_CONTEXT_IGNORE_ATTRIBUTE, "");
    reactGrabOverlay.setAttribute("data-react-grab-ignore", "");
    entity.append(field);
    fixture.append(entity, planeOverlay, reactGrabOverlay);

    const adapter = createReactGrabSelectionAdapter();
    const candidates = adapter.getElementsAtPoint(center(field));

    expect(
      candidates[0],
      [
        "event=context_picker.nested_selection",
        "actor=picker_core",
        "operation=acquire_point",
        "risk=ignored_overlay_intercepts_semantic_target",
        "expected=nested field is first candidate",
        `actual=${candidates[0]?.tagName ?? "none"}`,
        "suggestion=inspect composed ignore filtering and React Grab paint ordering",
      ].join(" ")
    ).toBe(field);
    expect(candidates).not.toContain(planeOverlay);
    expect(candidates).not.toContain(reactGrabOverlay);
  });

  test("discovers portal and open-shadow targets without source instrumentation", () => {
    const fixture = mountFixture();
    const portalTarget = document.createElement("button");
    const shadowHost = document.createElement("div");
    const shadowTarget = document.createElement("button");
    const shadowRoot = shadowHost.attachShadow({ mode: "open" });

    position(portalTarget, { left: "340px", top: "40px", width: "120px", height: "40px" });
    position(shadowHost, { left: "340px", top: "120px", width: "120px", height: "40px" });
    position(shadowTarget, { inset: "0", width: "120px", height: "40px" });
    fixture.append(portalTarget, shadowHost);
    shadowRoot.append(shadowTarget);

    const adapter = createReactGrabSelectionAdapter();

    expect(adapter.getElementsAtPoint(center(portalTarget))[0]).toBe(portalTarget);
    expect(adapter.getElementsAtPoint(center(shadowTarget))[0]).toBe(shadowTarget);
    expect(adapter.getElementsAtPoint({ clientX: Number.NaN, clientY: 0 })).toEqual([]);
  });

  test("cannot return detached targets after navigation and replacement", () => {
    const fixture = mountFixture();
    const staleTarget = document.createElement("button");
    position(staleTarget, { left: "40px", top: "220px", width: "120px", height: "40px" });
    fixture.append(staleTarget);

    const adapter = createReactGrabSelectionAdapter();
    const point = center(staleTarget);
    expect(adapter.getElementsAtPoint(point)[0]).toBe(staleTarget);

    staleTarget.remove();
    window.history.pushState(null, "", "/context-picker-m1-navigation");
    expect(adapter.getElementsAtPoint(point)).not.toContain(staleTarget);

    const currentTarget = document.createElement("button");
    position(currentTarget, { left: "40px", top: "220px", width: "120px", height: "40px" });
    fixture.append(currentTarget);

    expect(adapter.getElementsAtPoint(point)[0]).toBe(currentTarget);
    expect(document.documentElement.style.pointerEvents).toBe("");
  });
});

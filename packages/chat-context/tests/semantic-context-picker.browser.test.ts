import { afterEach, describe, expect, test } from "vitest";
import {
  type ContextSource,
  type ContextSourceCaptureResult,
  type EntityReferenceV1,
  type JsonValue,
  type SelectionAcquisitionAdapter,
  type SemanticReferenceV1,
  createReactGrabSelectionAdapter,
  createSemanticContextPicker,
} from "../src";

const FIXTURE_ATTRIBUTE = "data-plane-context-picker-m2-fixture";

const entityReference = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "work_item",
  entityId: "issue-1",
} satisfies EntityReferenceV1;

const priorityReference = {
  kind: "field",
  entity: entityReference,
  fieldKey: "priority",
} satisfies SemanticReferenceV1;

const stateReference = {
  kind: "field",
  entity: entityReference,
  fieldKey: "state",
} satisfies SemanticReferenceV1;

const referenceKey = (reference: SemanticReferenceV1): string => {
  switch (reference.kind) {
    case "entity":
      return `${reference.entityType}:${reference.entityId}`;
    case "field":
      return `${reference.entity.entityType}:${reference.entity.entityId}:${reference.fieldKey}`;
    case "editor_block":
      return `${reference.document.entityType}:${reference.document.entityId}:${reference.blockId}`;
    default: {
      const exhaustive: never = reference;
      return exhaustive;
    }
  }
};

class FakeAcquisitionAdapter implements SelectionAcquisitionAdapter {
  elements: readonly Element[] = [];

  getElementsAtPoint(): readonly Element[] {
    return this.elements;
  }

  isElementEligible(): boolean {
    return true;
  }
}

class FakeContextSource implements ContextSource {
  readonly captures: SemanticReferenceV1[] = [];
  readonly values = new Map<string, JsonValue>();
  readonly failures = new Map<string, ContextSourceCaptureResult>();

  getLabel(reference: SemanticReferenceV1): string {
    return referenceKey(reference);
  }

  async capture(reference: SemanticReferenceV1): Promise<ContextSourceCaptureResult> {
    this.captures.push(reference);
    const key = referenceKey(reference);
    const failure = this.failures.get(key);
    if (failure) {
      return failure;
    }

    return {
      ok: true,
      observed: {
        source: "client_store",
        value: this.values.get(key) ?? null,
        observedAt: "2026-07-29T09:00:00.000Z",
      },
    };
  }
}

const mountElement = (styles: Partial<CSSStyleDeclaration> = {}): HTMLDivElement => {
  const element = document.createElement("div");
  element.setAttribute(FIXTURE_ATTRIBUTE, "");
  Object.assign(element.style, {
    position: "fixed",
    display: "block",
    ...styles,
  });
  document.body.append(element);
  return element;
};

afterEach(() => {
  document.querySelectorAll(`[${FIXTURE_ATTRIBUTE}]`).forEach((element) => element.remove());
});

describe("semantic context picker", () => {
  test("uses production acquisition through the public contract", async () => {
    const source = new FakeContextSource();
    const element = mountElement({ left: "40px", top: "40px", width: "120px", height: "40px" });
    source.values.set(referenceKey(priorityReference), "high");
    const picker = createSemanticContextPicker({
      acquisition: createReactGrabSelectionAdapter(),
      contextSource: source,
      getLocation: () => "/acme/project-1/issue-1",
    });
    picker.register(element, { reference: priorityReference, parent: entityReference });
    const bounds = element.getBoundingClientRect();

    await expect(
      picker.select({
        operation: "capture",
        area: { kind: "point", clientX: bounds.left + bounds.width / 2, clientY: bounds.top + bounds.height / 2 },
      })
    ).resolves.toMatchObject({
      ok: true,
      context: { items: [{ reference: priorityReference, observed: { value: "high" } }] },
    });
  });

  test("previews identity without values and captures the fresh nested field", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const source = new FakeContextSource();
    const entity = mountElement();
    const field = mountElement();
    acquisition.elements = [field, entity];
    source.values.set(referenceKey(priorityReference), "low");

    const picker = createSemanticContextPicker({
      acquisition,
      contextSource: source,
      getLocation: () => "/acme/project-1/issue-1",
    });
    picker.register(entity, { reference: entityReference });
    picker.register(field, { reference: priorityReference, parent: entityReference });

    const preview = await picker.select({
      operation: "preview",
      area: { kind: "point", clientX: 10, clientY: 10 },
    });

    expect(preview).toEqual({
      ok: true,
      operation: "preview",
      candidates: [
        {
          schemaVersion: 1,
          reference: priorityReference,
          label: referenceKey(priorityReference),
          selectableAncestors: [entityReference],
        },
        {
          schemaVersion: 1,
          reference: entityReference,
          label: referenceKey(entityReference),
          selectableAncestors: [],
        },
      ],
    });
    expect(source.captures).toEqual([]);

    source.values.set(referenceKey(priorityReference), "urgent");
    const capture = await picker.select({
      operation: "capture",
      area: { kind: "point", clientX: 10, clientY: 10 },
    });

    expect(capture).toEqual({
      ok: true,
      operation: "capture",
      context: {
        schemaVersion: 1,
        selectionKind: "point",
        items: [
          {
            reference: priorityReference,
            observed: {
              source: "client_store",
              value: "urgent",
              observedAt: "2026-07-29T09:00:00.000Z",
            },
            location: { url: "/acme/project-1/issue-1" },
          },
        ],
        warnings: [],
      },
    });
  });

  test("captures a deterministic partial region without the duplicate parent entity", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const source = new FakeContextSource();
    const entity = mountElement({ left: "20px", top: "20px", width: "300px", height: "100px" });
    const priority = mountElement({ left: "30px", top: "30px", width: "80px", height: "40px" });
    const state = mountElement({ left: "130px", top: "30px", width: "80px", height: "40px" });
    source.values.set(referenceKey(priorityReference), "high");
    source.failures.set(referenceKey(stateReference), {
      ok: false,
      code: "VALUE_UNAVAILABLE",
      message: "State is not loaded",
      retryable: true,
    });

    const picker = createSemanticContextPicker({
      acquisition,
      contextSource: source,
      getLocation: () => "/acme/project-1/issue-1",
    });
    picker.register(entity, { reference: entityReference });
    picker.register(priority, { reference: priorityReference, parent: entityReference });
    picker.register(state, { reference: stateReference, parent: entityReference });

    const result = await picker.select({
      operation: "capture",
      area: { kind: "region", left: 0, top: 0, right: 400, bottom: 200 },
    });

    expect(result).toMatchObject({
      ok: true,
      operation: "capture",
      context: {
        schemaVersion: 1,
        selectionKind: "region",
        items: [{ reference: priorityReference }],
        warnings: [{ code: "VALUE_UNAVAILABLE", reference: stateReference }],
      },
    });
    expect(source.captures).toEqual([priorityReference, stateReference]);
  });

  test("keeps replacement registration safe from a stale disposer", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const source = new FakeContextSource();
    const element = mountElement();
    acquisition.elements = [element];
    const picker = createSemanticContextPicker({ acquisition, contextSource: source, getLocation: () => "/" });

    const disposeOld = picker.register(element, { reference: entityReference });
    picker.register(element, { reference: priorityReference, parent: entityReference });
    disposeOld();

    const result = await picker.select({
      operation: "preview",
      area: { kind: "point", clientX: 10, clientY: 10 },
    });

    expect(result).toMatchObject({
      ok: true,
      candidates: [{ reference: priorityReference }],
    });
  });

  test("suppresses a late capture result after disposal", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const element = mountElement();
    acquisition.elements = [element];
    let completeCapture: ((result: ContextSourceCaptureResult) => void) | undefined;
    const source: ContextSource = {
      getLabel: () => "Priority",
      capture: () =>
        new Promise((resolve) => {
          completeCapture = resolve;
        }),
    };
    const picker = createSemanticContextPicker({ acquisition, contextSource: source, getLocation: () => "/" });
    picker.register(element, { reference: priorityReference, parent: entityReference });

    const pending = picker.select({
      operation: "capture",
      area: { kind: "point", clientX: 10, clientY: 10 },
    });
    await Promise.resolve();
    picker.dispose();
    completeCapture?.({
      ok: true,
      observed: {
        source: "client_store",
        value: "urgent",
        observedAt: "2026-07-29T09:00:00.000Z",
      },
    });

    await expect(pending).resolves.toMatchObject({
      ok: false,
      failure: { code: "ABORTED" },
    });
    await expect(
      picker.select({ operation: "preview", area: { kind: "point", clientX: 10, clientY: 10 } })
    ).resolves.toMatchObject({
      ok: false,
      failure: { code: "ABORTED" },
    });
  });

  test("returns failures for an empty point and an oversized region", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const source = new FakeContextSource();
    const picker = createSemanticContextPicker({
      acquisition,
      contextSource: source,
      getLocation: () => "/",
      maxRegionTargets: 1,
    });

    await expect(
      picker.select({ operation: "preview", area: { kind: "point", clientX: 10, clientY: 10 } })
    ).resolves.toMatchObject({ ok: false, failure: { schemaVersion: 1, code: "NO_TARGET", retryable: false } });

    const priority = mountElement({ left: "10px", top: "10px", width: "40px", height: "40px" });
    const state = mountElement({ left: "60px", top: "10px", width: "40px", height: "40px" });
    picker.register(priority, { reference: priorityReference });
    picker.register(state, { reference: stateReference });

    await expect(
      picker.select({
        operation: "capture",
        area: { kind: "region", left: 0, top: 0, right: 120, bottom: 60 },
      })
    ).resolves.toMatchObject({
      ok: false,
      failure: { schemaVersion: 1, code: "TOO_MANY_TARGETS", retryable: false },
    });
    expect(source.captures).toEqual([]);
  });

  test("aborts a pending capture when a newer selection starts", async () => {
    const acquisition = new FakeAcquisitionAdapter();
    const element = mountElement();
    acquisition.elements = [element];
    let completeCapture: ((result: ContextSourceCaptureResult) => void) | undefined;
    const source: ContextSource = {
      getLabel: () => "Priority",
      capture: () =>
        new Promise((resolve) => {
          completeCapture = resolve;
        }),
    };
    const picker = createSemanticContextPicker({ acquisition, contextSource: source, getLocation: () => "/" });
    picker.register(element, { reference: priorityReference, parent: entityReference });

    const pending = picker.select({
      operation: "capture",
      area: { kind: "point", clientX: 10, clientY: 10 },
    });
    await Promise.resolve();
    await expect(
      picker.select({ operation: "preview", area: { kind: "point", clientX: 10, clientY: 10 } })
    ).resolves.toMatchObject({ ok: true, operation: "preview" });
    completeCapture?.({
      ok: true,
      observed: { source: "client_store", value: "urgent", observedAt: "2026-07-29T09:00:00.000Z" },
    });

    await expect(pending).resolves.toMatchObject({ ok: false, failure: { code: "ABORTED" } });
  });
});

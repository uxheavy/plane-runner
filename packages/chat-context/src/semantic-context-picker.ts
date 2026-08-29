/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  ContextCandidateV1,
  ContextItemV1,
  EntityReferenceV1,
  SelectionArea,
  SelectionFailureCode,
  SelectionFailureV1,
  SelectionRequest,
  SelectionResult,
  SemanticContextPicker,
  SemanticContextPickerOptions,
  SemanticReferenceV1,
  SemanticTarget,
} from "./contracts";

type Registration = {
  element: Element;
  target: SemanticTarget;
};

type CaptureOutcome = { kind: "item"; item: ContextItemV1 } | { kind: "warning"; warning: SelectionFailureV1 };

const failure = (
  code: SelectionFailureCode,
  message: string,
  retryable: boolean,
  reference?: SemanticReferenceV1
): SelectionFailureV1 => ({
  schemaVersion: 1,
  code,
  message,
  retryable,
  ...(reference ? { reference } : {}),
});

const referenceKey = (reference: SemanticReferenceV1): string => {
  switch (reference.kind) {
    case "entity":
      return [
        reference.kind,
        reference.workspaceSlug,
        reference.projectId ?? "",
        reference.entityType,
        reference.entityId,
      ].join(":");
    case "field":
      return `${referenceKey(reference.entity)}:${reference.fieldKey}`;
    case "editor_block":
      return `${referenceKey(reference.document)}:${reference.blockId}`;
    case "editor_range":
      return `${referenceKey(reference.document)}:${reference.start.blockId}:${reference.start.offset}:${reference.end.blockId}:${reference.end.offset}`;
    default: {
      const exhaustive: never = reference;
      return exhaustive;
    }
  }
};

const getComposedParent = (element: Element): Element | null => {
  if (element.parentElement) return element.parentElement;

  const root = element.getRootNode();
  if (root instanceof ShadowRoot) return root.host;

  return element.ownerDocument.defaultView?.frameElement ?? null;
};

const intersects = (bounds: DOMRect, region: Extract<SelectionArea, { kind: "region" }>): boolean =>
  bounds.width > 0 &&
  bounds.height > 0 &&
  bounds.right > region.left &&
  bounds.left < region.right &&
  bounds.bottom > region.top &&
  bounds.top < region.bottom;

const normalizeRegion = (
  region: Extract<SelectionArea, { kind: "region" }>
): Extract<SelectionArea, { kind: "region" }> => ({
  kind: "region",
  left: Math.min(region.left, region.right),
  top: Math.min(region.top, region.bottom),
  right: Math.max(region.left, region.right),
  bottom: Math.max(region.top, region.bottom),
});

const isEntityReference = (reference: SemanticReferenceV1): reference is EntityReferenceV1 =>
  reference.kind === "entity";

export const createSemanticContextPicker = ({
  acquisition,
  contextSource,
  getLocation,
  maxRegionTargets = 50,
}: SemanticContextPickerOptions): SemanticContextPicker => {
  const registrationsByElement = new WeakMap<Element, Registration>();
  const registrations = new Set<Registration>();
  let disposed = false;
  let operationRevision = 0;
  let activeController: AbortController | undefined;

  const disposeRegistration = (registration: Registration): void => {
    registrations.delete(registration);
    if (registrationsByElement.get(registration.element) === registration) {
      registrationsByElement.delete(registration.element);
    }
  };

  const eligible = (registration: Registration): boolean => {
    if (!registration.element.isConnected) {
      disposeRegistration(registration);
      return false;
    }
    return acquisition.isElementEligible(registration.element);
  };

  const registrationForElement = (element: Element): Registration | undefined => {
    let current: Element | null = element;
    while (current) {
      const registration = registrationsByElement.get(current);
      if (registration && eligible(registration)) return registration;
      current = getComposedParent(current);
    }
    return undefined;
  };

  const uniqueRegistrations = (values: readonly Registration[]): Registration[] => {
    const seen = new Set<string>();
    return values.filter(({ target }) => {
      const key = referenceKey(target.reference);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };

  const locatePoint = (area: Extract<SelectionArea, { kind: "point" }>): Registration[] =>
    uniqueRegistrations(
      acquisition
        .getElementsAtPoint(area)
        .map(registrationForElement)
        .filter((registration): registration is Registration => registration !== undefined)
    );

  const locateRegion = (area: Extract<SelectionArea, { kind: "region" }>): Registration[] => {
    const region = normalizeRegion(area);
    const matches = [...registrations]
      .filter(eligible)
      .map((registration) => ({ registration, bounds: registration.element.getBoundingClientRect() }))
      .filter(({ bounds }) => intersects(bounds, region))
      .toSorted(
        (left, right) =>
          left.bounds.top - right.bounds.top ||
          left.bounds.left - right.bounds.left ||
          referenceKey(left.registration.target.reference).localeCompare(
            referenceKey(right.registration.target.reference)
          )
      )
      .map(({ registration }) => registration);

    const childParents = new Set(
      matches
        .map(({ target }) => target.parent)
        .filter((parent): parent is SemanticReferenceV1 => parent !== undefined)
        .map(referenceKey)
    );

    return uniqueRegistrations(
      matches.filter(
        ({ target }) => !(isEntityReference(target.reference) && childParents.has(referenceKey(target.reference)))
      )
    );
  };

  const locate = (area: SelectionArea): Registration[] =>
    area.kind === "point" ? locatePoint(area) : locateRegion(area);

  const selectedRegistration = (registration: Registration, ancestorOffset: number): Registration | undefined => {
    if (ancestorOffset === 0) return registration;
    if (ancestorOffset !== 1 || !registration.target.parent) return undefined;
    const parent = registration.target.parent;
    const parentKey = referenceKey(parent);
    return (
      [...registrations].find(
        (candidate) => eligible(candidate) && referenceKey(candidate.target.reference) === parentKey
      ) ?? { element: registration.element, target: { reference: structuredClone(parent) } }
    );
  };

  const aborted = (revision: number, controller: AbortController): boolean =>
    disposed || revision !== operationRevision || controller.signal.aborted;

  const makeAbortedResult = (): SelectionResult => ({
    ok: false,
    failure: failure("ABORTED", "The selection operation was cancelled", true),
  });

  return {
    register: (element, target) => {
      if (disposed) throw new Error("Cannot register a semantic target after picker disposal");
      const current = registrationsByElement.get(element);
      if (current) disposeRegistration(current);

      const registration = { element, target: structuredClone(target) } satisfies Registration;
      registrationsByElement.set(element, registration);
      registrations.add(registration);
      return () => disposeRegistration(registration);
    },
    select: async (request: SelectionRequest): Promise<SelectionResult> => {
      if (disposed || request.signal?.aborted) return makeAbortedResult();

      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      const revision = ++operationRevision;
      const abortFromRequest = (): void => controller.abort();
      request.signal?.addEventListener("abort", abortFromRequest, { once: true });

      try {
        const ancestorOffset = request.ancestorOffset ?? 0;
        const located = locate(request.area);
        const selected = uniqueRegistrations(
          located
            .map((registration) => selectedRegistration(registration, ancestorOffset))
            .filter((registration): registration is Registration => registration !== undefined)
        );

        if (selected.length === 0) {
          return {
            ok: false,
            failure: failure("NO_TARGET", "No semantic target matched the selection", false),
          };
        }
        if (request.area.kind === "region" && selected.length > maxRegionTargets) {
          return {
            ok: false,
            failure: failure("TOO_MANY_TARGETS", "The selected region contains too many semantic targets", false),
          };
        }

        if (request.operation === "preview") {
          const candidates: ContextCandidateV1[] = selected.map(({ target }) => ({
            schemaVersion: 1,
            reference: target.reference,
            label: contextSource.getLabel(target.reference),
            selectableAncestors: target.parent ? [target.parent] : [],
          }));
          return { ok: true, operation: "preview", candidates };
        }

        const captureTargets = request.area.kind === "point" ? selected.slice(0, 1) : selected;
        const selectionLocation = getLocation();
        const outcomes = await Promise.all(
          captureTargets.map(async (registration): Promise<CaptureOutcome> => {
            if (!registration.element.isConnected) {
              return {
                kind: "warning",
                warning: failure(
                  "TARGET_GONE",
                  "The selected target is no longer mounted",
                  true,
                  registration.target.reference
                ),
              };
            }

            try {
              const result = await contextSource.capture(registration.target.reference, { signal: controller.signal });
              if (result.ok) {
                return {
                  kind: "item",
                  item: {
                    reference: registration.target.reference,
                    observed: result.observed,
                    location: { url: selectionLocation },
                  },
                };
              }
              return {
                kind: "warning",
                warning: failure(result.code, result.message, result.retryable, registration.target.reference),
              };
            } catch {
              return {
                kind: "warning",
                warning: failure(
                  "VALUE_UNAVAILABLE",
                  "The selected value could not be captured",
                  true,
                  registration.target.reference
                ),
              };
            }
          })
        );
        if (aborted(revision, controller)) return makeAbortedResult();

        const items: ContextItemV1[] = [];
        const warnings: SelectionFailureV1[] = [];
        outcomes.forEach((outcome) => {
          if (outcome.kind === "item") items.push(outcome.item);
          else warnings.push(outcome.warning);
        });
        if (items.length === 0 && warnings.length > 0) return { ok: false, failure: warnings[0] };

        return {
          ok: true,
          operation: "capture",
          context: {
            schemaVersion: 1,
            selectionKind: request.area.kind,
            items,
            warnings,
          },
        };
      } finally {
        request.signal?.removeEventListener("abort", abortFromRequest);
        if (activeController === controller) activeController = undefined;
      }
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      operationRevision += 1;
      activeController?.abort();
      activeController = undefined;
      for (const registration of registrations) disposeRegistration(registration);
    },
  };
};

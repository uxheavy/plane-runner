/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { getElementsAtPoint, isElementGrabbable } from "react-grab/primitives";

export const PLANE_CONTEXT_IGNORE_ATTRIBUTE = "data-plane-context-ignore";

export type ViewportPoint = {
  clientX: number;
  clientY: number;
};

export interface ReactGrabSelectionAdapter {
  getElementsAtPoint(point: ViewportPoint): readonly Element[];
  isElementEligible(element: Element): boolean;
}

const getComposedParent = (element: Element): Element | null => {
  if (element.parentElement) {
    return element.parentElement;
  }

  const root = element.getRootNode();
  if (root instanceof ShadowRoot) {
    return root.host;
  }

  return element.ownerDocument.defaultView?.frameElement ?? null;
};

const isInsidePlaneIgnoredSurface = (element: Element): boolean => {
  let current: Element | null = element;

  while (current) {
    if (current.hasAttribute(PLANE_CONTEXT_IGNORE_ATTRIBUTE)) {
      return true;
    }
    current = getComposedParent(current);
  }

  return false;
};

/**
 * Plane-owned boundary around the React Grab selection primitives.
 *
 * Upstream contract:
 * https://www.npmjs.com/package/react-grab?activeTab=readme#customize-hit-testing
 */
export const createReactGrabSelectionAdapter = (): ReactGrabSelectionAdapter => ({
  getElementsAtPoint: ({ clientX, clientY }) => {
    if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) {
      return [];
    }

    return getElementsAtPoint(clientX, clientY, {
      filter: (candidate) => isElementGrabbable(candidate) && !isInsidePlaneIgnoredSurface(candidate),
    });
  },
  isElementEligible: (element) => isElementGrabbable(element) && !isInsidePlaneIgnoredSurface(element),
});

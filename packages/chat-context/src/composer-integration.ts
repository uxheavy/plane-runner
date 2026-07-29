/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  ContextItemV1,
  JsonValue,
  SelectionArea,
  SelectionFailureV1,
  SemanticContextBundleV1,
  SemanticReferenceV1,
} from "./contracts";

export type SemanticContextHydrationRequestItemV1 = {
  readonly reference: SemanticReferenceV1;
  readonly observedEntityVersion?: string;
};

export type SemanticContextHydrationRequestV1 = {
  readonly schemaVersion: 1;
  readonly items: readonly SemanticContextHydrationRequestItemV1[];
};

export type ServerCanonicalObservationV1 = {
  readonly source: "server_canonical";
  readonly value: JsonValue;
  readonly resolvedAt: string;
  readonly entityVersion: string;
};

export type CanonicalHydrationSuccessV1 = {
  readonly ok: true;
  readonly reference: SemanticReferenceV1;
  readonly resolution: "canonical";
  readonly authorizedAt: string;
  readonly stale: boolean;
  readonly canonical: ServerCanonicalObservationV1;
};

export type AuthorizationOnlyHydrationSuccessV1 = {
  readonly ok: true;
  readonly reference: SemanticReferenceV1;
  readonly resolution: "authorization_only";
  readonly authorizedAt: string;
  readonly stale: false;
};

export type SemanticContextHydrationFailureV1 = {
  readonly ok: false;
  readonly reference: SemanticReferenceV1;
  readonly code: "FORBIDDEN" | "NOT_FOUND" | "UNSUPPORTED";
  readonly message: string;
  readonly retryable: boolean;
};

export type SemanticContextHydrationResultV1 =
  | CanonicalHydrationSuccessV1
  | AuthorizationOnlyHydrationSuccessV1
  | SemanticContextHydrationFailureV1;

export type SemanticContextHydrationResponseV1 = {
  readonly schemaVersion: 1;
  readonly results: readonly SemanticContextHydrationResultV1[];
};

export type ComposerContextItemV1 = ContextItemV1 & {
  readonly server: CanonicalHydrationSuccessV1 | AuthorizationOnlyHydrationSuccessV1;
};

export type ComposerContextAttachmentV1 = {
  readonly schemaVersion: 1;
  readonly selectionKind: SelectionArea["kind"];
  readonly items: readonly ComposerContextItemV1[];
  readonly selectionWarnings: readonly SelectionFailureV1[];
  readonly hydrationWarnings: readonly SemanticContextHydrationFailureV1[];
};

export type ComposerIntegrationFailureCode =
  | "EMPTY_CONTEXT"
  | "MIXED_WORKSPACES"
  | "TOO_MANY_ITEMS"
  | "HYDRATION_FAILED"
  | "HYDRATION_INVALID"
  | "NO_AUTHORIZED_CONTEXT"
  | "COMPOSER_FAILED"
  | "ABORTED";

export type ComposerIntegrationResult =
  | { readonly ok: true; readonly attachment: ComposerContextAttachmentV1 }
  | {
      readonly ok: false;
      readonly code: ComposerIntegrationFailureCode;
      readonly message: string;
      readonly retryable: boolean;
    };

type ComposerIntegrationFailure = Extract<ComposerIntegrationResult, { ok: false }>;

export interface SemanticContextHydrationPort {
  hydrate(
    workspaceSlug: string,
    request: SemanticContextHydrationRequestV1,
    options: { signal: AbortSignal }
  ): Promise<unknown>;
}

export interface ComposerContextConsumerPort {
  attachContext(attachment: ComposerContextAttachmentV1, options: { signal: AbortSignal }): Promise<void>;
}

export interface SemanticContextComposerAdapter {
  attachContext(
    bundle: SemanticContextBundleV1,
    options?: { signal?: AbortSignal }
  ): Promise<ComposerIntegrationResult>;
}

export type SemanticContextComposerAdapterOptions = {
  readonly hydration: SemanticContextHydrationPort;
  readonly consumer: ComposerContextConsumerPort;
  readonly maximumItems?: number;
};

const failure = (
  code: ComposerIntegrationFailureCode,
  message: string,
  retryable: boolean
): ComposerIntegrationFailure => ({ ok: false, code, message, retryable });

const workspaceSlug = (reference: SemanticReferenceV1): string => {
  switch (reference.kind) {
    case "entity":
      return reference.workspaceSlug;
    case "field":
      return reference.entity.workspaceSlug;
    case "editor_block":
    case "editor_range":
      return reference.document.workspaceSlug;
    default: {
      const exhaustive: never = reference;
      return exhaustive;
    }
  }
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isJsonValue = (value: unknown): value is JsonValue => {
  if (value === null || ["boolean", "number", "string"].includes(typeof value)) return true;
  if (Array.isArray(value)) return value.every(isJsonValue);
  return isRecord(value) && Object.values(value).every(isJsonValue);
};

const entityTypes = new Set(["work_item", "project", "cycle", "module", "page", "view"]);
const workItemFields = new Set([
  "name",
  "description",
  "state",
  "priority",
  "assignees",
  "labels",
  "start_date",
  "target_date",
  "estimate",
  "cycle",
  "module",
]);

const isEntityReference = (value: unknown): value is Extract<SemanticReferenceV1, { kind: "entity" }> =>
  isRecord(value) &&
  value.kind === "entity" &&
  typeof value.workspaceSlug === "string" &&
  typeof value.entityId === "string" &&
  typeof value.entityType === "string" &&
  entityTypes.has(value.entityType) &&
  (value.projectId === undefined || typeof value.projectId === "string");

const isRangePoint = (value: unknown): value is { readonly blockId: string; readonly offset: number } =>
  isRecord(value) &&
  typeof value.blockId === "string" &&
  Number.isSafeInteger(value.offset) &&
  typeof value.offset === "number" &&
  value.offset >= 0;

export const isSemanticReferenceV1 = (value: unknown): value is SemanticReferenceV1 => {
  if (isEntityReference(value)) return true;
  if (!isRecord(value) || typeof value.kind !== "string") return false;
  if (value.kind === "field") {
    return (
      isEntityReference(value.entity) &&
      value.entity.entityType === "work_item" &&
      typeof value.fieldKey === "string" &&
      workItemFields.has(value.fieldKey)
    );
  }
  if (value.kind === "editor_block") {
    return (
      isEntityReference(value.document) &&
      ["page", "work_item"].includes(value.document.entityType) &&
      typeof value.blockId === "string"
    );
  }
  if (value.kind === "editor_range") {
    return (
      isEntityReference(value.document) &&
      ["page", "work_item"].includes(value.document.entityType) &&
      isRangePoint(value.start) &&
      isRangePoint(value.end)
    );
  }
  return false;
};

export const isSelectionFailureContractV1 = (value: unknown): value is SelectionFailureV1 =>
  isRecord(value) &&
  value.schemaVersion === 1 &&
  typeof value.code === "string" &&
  ["NO_TARGET", "TARGET_GONE", "UNSUPPORTED", "VALUE_UNAVAILABLE", "ABORTED", "TOO_MANY_TARGETS"].includes(
    value.code
  ) &&
  typeof value.message === "string" &&
  typeof value.retryable === "boolean" &&
  (value.reference === undefined || isSemanticReferenceV1(value.reference));

export const isSemanticContextBundleV1 = (value: unknown): value is SemanticContextBundleV1 => {
  if (
    !isRecord(value) ||
    value.schemaVersion !== 1 ||
    !["point", "region"].includes(String(value.selectionKind)) ||
    !Array.isArray(value.items) ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every(isSelectionFailureContractV1)
  ) {
    return false;
  }
  return value.items.every(
    (item) =>
      isRecord(item) &&
      isSemanticReferenceV1(item.reference) &&
      isRecord(item.observed) &&
      ["client_store", "client_live"].includes(String(item.observed.source)) &&
      isJsonValue(item.observed.value) &&
      typeof item.observed.observedAt === "string" &&
      (item.observed.entityVersion === undefined || typeof item.observed.entityVersion === "string") &&
      isRecord(item.location) &&
      typeof item.location.url === "string"
  );
};

const sameJson = (left: JsonValue, right: JsonValue): boolean => {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => sameJson(value, right[index] ?? null));
  }
  if (isRecord(left) && isRecord(right)) {
    const leftKeys = Object.keys(left).toSorted();
    const rightKeys = Object.keys(right).toSorted();
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key, index) => key === rightKeys[index] && sameJson(left[key] ?? null, right[key] ?? null))
    );
  }
  return false;
};

const hydrationFailureCodes = new Set(["FORBIDDEN", "NOT_FOUND", "UNSUPPORTED"]);

const parseHydrationResult = (
  value: unknown,
  expectedReference: SemanticReferenceV1
): SemanticContextHydrationResultV1 | undefined => {
  if (!isRecord(value) || typeof value.ok !== "boolean" || !isJsonValue(value.reference)) return undefined;
  if (!sameJson(value.reference, expectedReference)) return undefined;
  if (!value.ok) {
    if (
      typeof value.code !== "string" ||
      !hydrationFailureCodes.has(value.code) ||
      typeof value.message !== "string" ||
      typeof value.retryable !== "boolean"
    ) {
      return undefined;
    }
    return {
      ok: false,
      reference: expectedReference,
      code: value.code as SemanticContextHydrationFailureV1["code"],
      message: value.message,
      retryable: value.retryable,
    };
  }
  if (typeof value.authorizedAt !== "string" || typeof value.stale !== "boolean") return undefined;
  if (value.resolution === "authorization_only") {
    if (value.stale) return undefined;
    return {
      ok: true,
      reference: expectedReference,
      resolution: "authorization_only",
      authorizedAt: value.authorizedAt,
      stale: false,
    };
  }
  if (value.resolution !== "canonical" || !isRecord(value.canonical)) return undefined;
  const canonical = value.canonical;
  if (
    canonical.source !== "server_canonical" ||
    !isJsonValue(canonical.value) ||
    typeof canonical.resolvedAt !== "string" ||
    typeof canonical.entityVersion !== "string"
  ) {
    return undefined;
  }
  return {
    ok: true,
    reference: expectedReference,
    resolution: "canonical",
    authorizedAt: value.authorizedAt,
    stale: value.stale,
    canonical: {
      source: "server_canonical",
      value: canonical.value,
      resolvedAt: canonical.resolvedAt,
      entityVersion: canonical.entityVersion,
    },
  };
};

export const parseSemanticContextHydrationResponse = (
  value: unknown,
  request: SemanticContextHydrationRequestV1
): SemanticContextHydrationResponseV1 | undefined => {
  if (!isRecord(value) || value.schemaVersion !== 1 || !Array.isArray(value.results)) return undefined;
  if (value.results.length !== request.items.length) return undefined;
  const results: SemanticContextHydrationResultV1[] = [];
  for (const [index, rawResult] of value.results.entries()) {
    const item = request.items[index];
    if (!item) return undefined;
    const result = parseHydrationResult(rawResult, item.reference);
    if (!result) return undefined;
    results.push(result);
  }
  return { schemaVersion: 1, results };
};

const requestFromBundle = (
  bundle: SemanticContextBundleV1,
  maximumItems: number
): { ok: true; workspaceSlug: string; request: SemanticContextHydrationRequestV1 } | ComposerIntegrationFailure => {
  if (bundle.items.length === 0) {
    return failure("EMPTY_CONTEXT", "The context bundle has no semantic items", false);
  }
  if (bundle.items.length > maximumItems) {
    return failure("TOO_MANY_ITEMS", `The context bundle exceeds the ${maximumItems}-item hydration limit`, false);
  }
  const workspace = workspaceSlug(bundle.items[0]!.reference);
  if (bundle.items.some((item) => workspaceSlug(item.reference) !== workspace)) {
    return failure("MIXED_WORKSPACES", "One hydration request cannot cross Plane workspaces", false);
  }
  return {
    ok: true,
    workspaceSlug: workspace,
    request: {
      schemaVersion: 1,
      items: bundle.items.map((item) => ({
        reference: item.reference,
        ...(item.observed.entityVersion ? { observedEntityVersion: item.observed.entityVersion } : {}),
      })),
    },
  };
};

const aborted = (): ComposerIntegrationResult => failure("ABORTED", "Semantic context integration was cancelled", true);

export const createSemanticContextComposerAdapter = (
  options: SemanticContextComposerAdapterOptions
): SemanticContextComposerAdapter => ({
  async attachContext(bundle, attachOptions = {}) {
    const signal = attachOptions.signal ?? new AbortController().signal;
    if (signal.aborted) return aborted();
    const prepared = requestFromBundle(bundle, options.maximumItems ?? 50);
    if (!prepared.ok) return prepared;

    let rawResponse: unknown;
    try {
      rawResponse = await options.hydration.hydrate(prepared.workspaceSlug, prepared.request, { signal });
    } catch {
      return signal.aborted ? aborted() : failure("HYDRATION_FAILED", "Semantic context hydration failed", true);
    }
    if (signal.aborted) return aborted();
    const response = parseSemanticContextHydrationResponse(rawResponse, prepared.request);
    if (!response) {
      return failure("HYDRATION_INVALID", "The hydration response did not match the request contract", false);
    }

    const items: ComposerContextItemV1[] = [];
    const hydrationWarnings: SemanticContextHydrationFailureV1[] = [];
    for (const [index, server] of response.results.entries()) {
      const item = bundle.items[index];
      if (!item) return failure("HYDRATION_INVALID", "The hydration response order was invalid", false);
      if (server.ok) items.push({ ...item, server });
      else hydrationWarnings.push(server);
    }
    if (items.length === 0) {
      return failure("NO_AUTHORIZED_CONTEXT", "No selected context remains authorized", false);
    }

    const attachment: ComposerContextAttachmentV1 = {
      schemaVersion: 1,
      selectionKind: bundle.selectionKind,
      items,
      selectionWarnings: bundle.warnings,
      hydrationWarnings,
    };
    try {
      await options.consumer.attachContext(attachment, { signal });
    } catch {
      return signal.aborted ? aborted() : failure("COMPOSER_FAILED", "The composer rejected context", true);
    }
    return { ok: true, attachment };
  },
});

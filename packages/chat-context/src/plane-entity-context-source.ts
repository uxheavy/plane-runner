/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  ContextObservationV1,
  ContextSource,
  ContextSourceCaptureResult,
  EntityReferenceV1,
  JsonValue,
  SemanticReferenceV1,
  WorkItemContextField,
} from "./contracts";

type Timestamp = string | Date | null | undefined;

export type PlaneWorkItemContextRecord = {
  id: string;
  project_id: string | null;
  sequence_id: number;
  name: string;
  description_html?: string;
  state_id: string | null;
  priority: string | null;
  assignee_ids: string[];
  label_ids: string[];
  start_date: string | null;
  target_date: string | null;
  estimate_point: string | null;
  cycle_id: string | null;
  module_ids: string[] | null;
  updated_at: string;
};

export type PlaneProjectContextRecord = {
  id: string;
  name: string;
  identifier: string;
  description?: string;
  archived_at: Timestamp;
  updated_at?: Timestamp;
  estimate?: string | null;
};

export type PlaneCycleContextRecord = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status?: string;
  start_date: string | null;
  end_date: string | null;
  archived_at: Timestamp;
  updated_at?: Timestamp;
};

export type PlaneModuleContextRecord = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status?: string;
  start_date: string | null;
  target_date: string | null;
  archived_at: Timestamp;
  updated_at?: Timestamp;
};

export type PlanePageContextRecord = {
  id?: string;
  name?: string;
  project_ids?: string[];
  access?: string | number;
  is_locked: boolean;
  archived_at: Timestamp;
  updated_at?: Timestamp;
};

export type PlaneViewContextRecord = {
  id: string;
  project: string;
  name: string;
  description: string;
  access: string | number;
  is_locked: boolean;
  updated_at?: Timestamp;
};

export type PlaneEntityStoreAccess = {
  getWorkItem(id: string): PlaneWorkItemContextRecord | undefined;
  getProject(id: string): PlaneProjectContextRecord | undefined;
  getCycle(id: string): PlaneCycleContextRecord | undefined;
  getModule(id: string): PlaneModuleContextRecord | undefined;
  getPage(id: string): PlanePageContextRecord | undefined;
  getView(id: string): PlaneViewContextRecord | undefined;
  getState(id: string): { id: string; name: string; group: string } | undefined;
  getLabel(id: string): { id: string; name: string } | undefined;
  getMember(id: string): { id: string; display_name: string } | undefined;
  getEstimatePoint(projectId: string, id: string): { id: string; key?: number; value?: string } | undefined;
};

export type PlaneEntityContextSourceOptions = {
  access: PlaneEntityStoreAccess;
  now?: () => string;
};

export type PlaneCoreRootStoreContextPort = {
  issue: { issues: { getIssueById(id: string): PlaneWorkItemContextRecord | undefined } };
  projectRoot: { project: { getProjectById(id: string): PlaneProjectContextRecord | undefined } };
  cycle: { getCycleById(id: string): PlaneCycleContextRecord | null | undefined };
  module: { getModuleById(id: string): PlaneModuleContextRecord | null | undefined };
  projectPages: { getPageById(id: string): PlanePageContextRecord | undefined };
  projectView: { getViewById(id: string): PlaneViewContextRecord | null | undefined };
  state: { getStateById(id: string): { id: string; name: string; group: string } | undefined };
  label: { getLabelById(id: string): { id: string; name: string } | null | undefined };
  memberRoot: { getUserDetails(id: string): { id: string; display_name: string } | undefined };
  projectEstimate: {
    getEstimateById(id: string):
      | {
          estimatePointById(pointId: string): { key: number | undefined; value: string | undefined } | undefined;
        }
      | undefined;
  };
};

export const createPlaneCoreRootStoreAccess = (store: PlaneCoreRootStoreContextPort): PlaneEntityStoreAccess => ({
  getWorkItem: (id) => store.issue.issues.getIssueById(id),
  getProject: (id) => store.projectRoot.project.getProjectById(id),
  getCycle: (id) => store.cycle.getCycleById(id) ?? undefined,
  getModule: (id) => store.module.getModuleById(id) ?? undefined,
  getPage: (id) => store.projectPages.getPageById(id),
  getView: (id) => store.projectView.getViewById(id) ?? undefined,
  getState: (id) => store.state.getStateById(id),
  getLabel: (id) => store.label.getLabelById(id) ?? undefined,
  getMember: (id) => store.memberRoot.getUserDetails(id),
  getEstimatePoint: (projectId, id) => {
    const estimateId = store.projectRoot.project.getProjectById(projectId)?.estimate;
    if (!estimateId) return undefined;
    const point = store.projectEstimate.getEstimateById(estimateId)?.estimatePointById(id);
    return point
      ? {
          id,
          ...(point.key !== undefined ? { key: point.key } : {}),
          ...(point.value !== undefined ? { value: point.value } : {}),
        }
      : undefined;
  },
});

const unavailable = (message: string): ContextSourceCaptureResult => ({
  ok: false,
  code: "VALUE_UNAVAILABLE",
  message,
  retryable: true,
});

const unsupported = (message: string): ContextSourceCaptureResult => ({
  ok: false,
  code: "UNSUPPORTED",
  message,
  retryable: false,
});

const timestamp = (value: Timestamp): string | null => {
  if (value instanceof Date) return value.toISOString();
  return value ?? null;
};

const observation = (value: JsonValue, observedAt: string, version?: Timestamp): ContextSourceCaptureResult => {
  const entityVersion = timestamp(version);
  const observed: ContextObservationV1 = {
    source: "client_store",
    value,
    observedAt,
    ...(entityVersion ? { entityVersion } : {}),
  };
  return { ok: true, observed };
};

const fieldLabel = (field: WorkItemContextField): string => {
  switch (field) {
    case "name":
      return "Name";
    case "description":
      return "Description";
    case "state":
      return "State";
    case "priority":
      return "Priority";
    case "assignees":
      return "Assignees";
    case "labels":
      return "Labels";
    case "start_date":
      return "Start date";
    case "target_date":
      return "Target date";
    case "estimate":
      return "Estimate";
    case "cycle":
      return "Cycle";
    case "module":
      return "Modules";
    default: {
      const exhaustive: never = field;
      return exhaustive;
    }
  }
};

const entityLabel = (reference: EntityReferenceV1): string => {
  const type = reference.entityType.replace("_", " ");
  return `${type[0]?.toUpperCase() ?? ""}${type.slice(1)} ${reference.entityId}`;
};

const belongsToProject = (recordProjectId: string | null | undefined, reference: EntityReferenceV1): boolean =>
  !reference.projectId || recordProjectId === reference.projectId;

const captureWorkItemField = (
  access: PlaneEntityStoreAccess,
  reference: Extract<SemanticReferenceV1, { kind: "field" }>,
  observedAt: string
): ContextSourceCaptureResult => {
  const item = access.getWorkItem(reference.entity.entityId);
  if (!item || !belongsToProject(item.project_id, reference.entity)) {
    return unavailable("The work item is not available in the expected project store");
  }

  let value: JsonValue;
  switch (reference.fieldKey) {
    case "name":
      value = item.name;
      break;
    case "description":
      value = item.description_html ?? null;
      break;
    case "state": {
      const state = item.state_id ? access.getState(item.state_id) : undefined;
      value = item.state_id ? { id: item.state_id, name: state?.name ?? null, group: state?.group ?? null } : null;
      break;
    }
    case "priority":
      value = item.priority;
      break;
    case "assignees":
      value = item.assignee_ids.map((id) => ({ id, displayName: access.getMember(id)?.display_name ?? null }));
      break;
    case "labels":
      value = item.label_ids.map((id) => ({ id, name: access.getLabel(id)?.name ?? null }));
      break;
    case "start_date":
      value = item.start_date;
      break;
    case "target_date":
      value = item.target_date;
      break;
    case "estimate": {
      const point = item.estimate_point
        ? access.getEstimatePoint(reference.entity.projectId, item.estimate_point)
        : undefined;
      value = item.estimate_point
        ? { id: item.estimate_point, key: point?.key ?? null, value: point?.value ?? null }
        : null;
      break;
    }
    case "cycle": {
      const cycle = item.cycle_id ? access.getCycle(item.cycle_id) : undefined;
      value = item.cycle_id ? { id: item.cycle_id, name: cycle?.name ?? null } : null;
      break;
    }
    case "module":
      value = (item.module_ids ?? []).map((id) => ({ id, name: access.getModule(id)?.name ?? null }));
      break;
    default: {
      const exhaustive: never = reference.fieldKey;
      return exhaustive;
    }
  }

  return observation(value, observedAt, item.updated_at);
};

const captureEntity = (
  access: PlaneEntityStoreAccess,
  reference: EntityReferenceV1,
  observedAt: string
): ContextSourceCaptureResult => {
  switch (reference.entityType) {
    case "work_item": {
      const item = access.getWorkItem(reference.entityId);
      if (!item || !belongsToProject(item.project_id, reference)) return unavailable("The work item is unavailable");
      return observation(
        {
          id: item.id,
          projectId: item.project_id,
          sequenceId: item.sequence_id,
          name: item.name,
          stateId: item.state_id,
          priority: item.priority,
          assigneeIds: item.assignee_ids,
          labelIds: item.label_ids,
          startDate: item.start_date,
          targetDate: item.target_date,
          estimatePointId: item.estimate_point,
          cycleId: item.cycle_id,
          moduleIds: item.module_ids ?? [],
          updatedAt: item.updated_at,
        },
        observedAt,
        item.updated_at
      );
    }
    case "project": {
      const project = access.getProject(reference.entityId);
      if (!project || (reference.projectId && reference.projectId !== project.id)) {
        return unavailable("The project is unavailable");
      }
      return observation(
        {
          id: project.id,
          name: project.name,
          identifier: project.identifier,
          description: project.description ?? null,
          archivedAt: timestamp(project.archived_at),
          updatedAt: timestamp(project.updated_at),
        },
        observedAt,
        project.updated_at
      );
    }
    case "cycle": {
      const cycle = access.getCycle(reference.entityId);
      if (!cycle || !belongsToProject(cycle.project_id, reference)) return unavailable("The cycle is unavailable");
      return observation(
        {
          id: cycle.id,
          projectId: cycle.project_id,
          name: cycle.name,
          description: cycle.description,
          status: cycle.status ?? null,
          startDate: cycle.start_date,
          endDate: cycle.end_date,
          archivedAt: timestamp(cycle.archived_at),
          updatedAt: timestamp(cycle.updated_at),
        },
        observedAt,
        cycle.updated_at
      );
    }
    case "module": {
      const module = access.getModule(reference.entityId);
      if (!module || !belongsToProject(module.project_id, reference)) return unavailable("The module is unavailable");
      return observation(
        {
          id: module.id,
          projectId: module.project_id,
          name: module.name,
          description: module.description,
          status: module.status ?? null,
          startDate: module.start_date,
          targetDate: module.target_date,
          archivedAt: timestamp(module.archived_at),
          updatedAt: timestamp(module.updated_at),
        },
        observedAt,
        module.updated_at
      );
    }
    case "page": {
      const page = access.getPage(reference.entityId);
      if (!page || (reference.projectId && !page.project_ids?.includes(reference.projectId))) {
        return unavailable("The page is unavailable");
      }
      return observation(
        {
          id: page.id ?? reference.entityId,
          name: page.name ?? null,
          projectIds: page.project_ids ?? [],
          access: page.access ?? null,
          isLocked: page.is_locked,
          archivedAt: timestamp(page.archived_at),
          updatedAt: timestamp(page.updated_at),
        },
        observedAt,
        page.updated_at
      );
    }
    case "view": {
      const view = access.getView(reference.entityId);
      if (!view || !belongsToProject(view.project, reference)) return unavailable("The view is unavailable");
      return observation(
        {
          id: view.id,
          projectId: view.project,
          name: view.name,
          description: view.description,
          access: view.access,
          isLocked: view.is_locked,
          updatedAt: timestamp(view.updated_at),
        },
        observedAt,
        view.updated_at
      );
    }
    default: {
      const exhaustive: never = reference.entityType;
      return exhaustive;
    }
  }
};

export const createPlaneEntityContextSource = ({
  access,
  now = () => new Date().toISOString(),
}: PlaneEntityContextSourceOptions): ContextSource => ({
  getLabel: (reference) => {
    switch (reference.kind) {
      case "entity":
        return entityLabel(reference);
      case "field":
        return fieldLabel(reference.fieldKey);
      case "editor_block":
      case "editor_range":
        return "Editor block";
      default: {
        const exhaustive: never = reference;
        return exhaustive;
      }
    }
  },
  capture: (reference) => {
    const observedAt = now();
    switch (reference.kind) {
      case "entity":
        return Promise.resolve(captureEntity(access, reference, observedAt));
      case "field":
        return Promise.resolve(captureWorkItemField(access, reference, observedAt));
      case "editor_block":
      case "editor_range":
        return Promise.resolve(unsupported("Editor content is resolved by the M4 live editor Adapter"));
      default: {
        const exhaustive: never = reference;
        return Promise.resolve(exhaustive);
      }
    }
  },
});

import { describe, expect, test } from "vitest";
import {
  type EntityReferenceV1,
  type JsonValue,
  type PlaneEntityStoreAccess,
  type SemanticReferenceV1,
  type WorkItemContextField,
  createPlaneCoreRootStoreAccess,
  createPlaneEntityContextSource,
} from "../src";

const observedAt = "2026-07-29T10:00:00.000Z";
const captureOptions = { signal: new AbortController().signal };

const workItemReference = {
  kind: "entity",
  workspaceSlug: "acme",
  projectId: "project-1",
  entityType: "work_item",
  entityId: "issue-1",
} satisfies EntityReferenceV1;

const fieldReference = (fieldKey: Extract<SemanticReferenceV1, { kind: "field" }>["fieldKey"]) =>
  ({ kind: "field", entity: workItemReference, fieldKey }) satisfies SemanticReferenceV1;

const createFixture = () => {
  const workItem = {
    id: "issue-1",
    project_id: "project-1",
    sequence_id: 42,
    name: "Fix context picker",
    description_html: "<p>Use current Plane state</p>",
    state_id: "state-1",
    priority: "low",
    assignee_ids: ["user-1", "missing-user"],
    label_ids: ["label-1", "missing-label"],
    start_date: "2026-07-20",
    target_date: "2026-08-01",
    estimate_point: "point-1",
    cycle_id: "cycle-1",
    module_ids: ["module-1", "missing-module"],
    updated_at: "2026-07-29T09:00:00.000Z",
    server_secret: "must-not-escape",
  };
  const access: PlaneEntityStoreAccess = {
    getWorkItem: (id) => (id === workItem.id ? workItem : undefined),
    getProject: (id) =>
      id === "project-1"
        ? {
            id,
            name: "Agents",
            identifier: "AGT",
            description: "Agent-native Plane",
            archived_at: null,
            updated_at: new Date("2026-07-29T08:00:00.000Z"),
            members: ["must-not-escape"],
          }
        : undefined,
    getCycle: (id) =>
      id === "cycle-1"
        ? {
            id,
            project_id: "project-1",
            name: "July",
            description: "July cycle",
            status: "current",
            start_date: "2026-07-01",
            end_date: "2026-07-31",
            archived_at: null,
            updated_at: "2026-07-29T08:00:00.000Z",
          }
        : undefined,
    getModule: (id) =>
      id === "module-1"
        ? {
            id,
            project_id: "project-1",
            name: "Chat",
            description: "Agent chat",
            status: "in-progress",
            start_date: "2026-07-01",
            target_date: "2026-08-15",
            archived_at: null,
            updated_at: "2026-07-29T08:00:00.000Z",
          }
        : undefined,
    getPage: (id) =>
      id === "page-1"
        ? {
            id,
            name: "Context design",
            project_ids: ["project-1"],
            access: 1,
            is_locked: false,
            archived_at: null,
            updated_at: new Date("2026-07-29T08:00:00.000Z"),
            description_html: "must-not-escape-before-m4",
          }
        : undefined,
    getView: (id) =>
      id === "view-1"
        ? {
            id,
            project: "project-1",
            name: "My work",
            description: "Assigned work",
            access: 1,
            is_locked: false,
            updated_at: new Date("2026-07-29T08:00:00.000Z"),
            query: { assignees: ["must-not-escape"] },
          }
        : undefined,
    getState: (id) => (id === "state-1" ? { id, name: "In progress", group: "started" } : undefined),
    getLabel: (id) => (id === "label-1" ? { id, name: "Feature" } : undefined),
    getMember: (id) => (id === "user-1" ? { id, display_name: "NQH", email: "must-not-escape" } : undefined),
    getEstimatePoint: (projectId, id) =>
      projectId === "project-1" && id === "point-1" ? { id, key: 3, value: "3 points" } : undefined,
  };
  return { access, workItem };
};

describe("Plane entity context source", () => {
  test("binds the current Plane CoreRootStore paths without copying records", () => {
    const { access, workItem } = createFixture();
    const estimatePoint = { id: "point-1", key: 3, value: "3 points" };
    const rootAccess = createPlaneCoreRootStoreAccess({
      issue: { issues: { getIssueById: access.getWorkItem } },
      projectRoot: {
        project: {
          getProjectById: (id) => {
            const project = access.getProject(id);
            return project ? { ...project, estimate: "estimate-1" } : undefined;
          },
        },
      },
      cycle: { getCycleById: access.getCycle },
      module: { getModuleById: access.getModule },
      projectPages: { getPageById: access.getPage },
      projectView: { getViewById: access.getView },
      state: { getStateById: access.getState },
      label: { getLabelById: access.getLabel },
      memberRoot: { getUserDetails: access.getMember },
      projectEstimate: {
        getEstimateById: (id) => (id === "estimate-1" ? { estimatePointById: () => estimatePoint } : undefined),
      },
    });

    expect(rootAccess.getWorkItem("issue-1")).toBe(workItem);
    expect(rootAccess.getEstimatePoint("project-1", "point-1")).toEqual(estimatePoint);
  });

  test("captures every allowlisted work-item field with related display values", async () => {
    const { access } = createFixture();
    const source = createPlaneEntityContextSource({ access, now: () => observedAt });
    const expected = [
      ["name", "Fix context picker"],
      ["description", "<p>Use current Plane state</p>"],
      ["state", { id: "state-1", name: "In progress", group: "started" }],
      ["priority", "low"],
      [
        "assignees",
        [
          { id: "user-1", displayName: "NQH" },
          { id: "missing-user", displayName: null },
        ],
      ],
      [
        "labels",
        [
          { id: "label-1", name: "Feature" },
          { id: "missing-label", name: null },
        ],
      ],
      ["start_date", "2026-07-20"],
      ["target_date", "2026-08-01"],
      ["estimate", { id: "point-1", key: 3, value: "3 points" }],
      ["cycle", { id: "cycle-1", name: "July" }],
      [
        "module",
        [
          { id: "module-1", name: "Chat" },
          { id: "missing-module", name: null },
        ],
      ],
    ] satisfies ReadonlyArray<readonly [WorkItemContextField, JsonValue]>;

    const results = await Promise.all(
      expected.map(async ([fieldKey, expectedValue]) => ({
        result: await source.capture(fieldReference(fieldKey), captureOptions),
        expectedValue,
      }))
    );
    results.forEach(({ result, expectedValue }) => {
      expect(result).toMatchObject({
        ok: true,
        observed: {
          source: "client_store",
          value: expectedValue,
          observedAt,
          entityVersion: "2026-07-29T09:00:00.000Z",
        },
      });
    });
  });

  test("reads fresh values while labels remain identity-only", async () => {
    const { access, workItem } = createFixture();
    let workItemReads = 0;
    const trackedAccess: PlaneEntityStoreAccess = {
      ...access,
      getWorkItem: (id) => {
        workItemReads += 1;
        return access.getWorkItem(id);
      },
    };
    const source = createPlaneEntityContextSource({ access: trackedAccess, now: () => observedAt });

    expect(source.getLabel(fieldReference("priority"))).toBe("Priority");
    expect(workItemReads).toBe(0);
    workItem.priority = "urgent";
    await expect(source.capture(fieldReference("priority"), captureOptions)).resolves.toMatchObject({
      ok: true,
      observed: { value: "urgent" },
    });
  });

  test("captures curated snapshots for every supported entity", async () => {
    const { access } = createFixture();
    const source = createPlaneEntityContextSource({ access, now: () => observedAt });
    const references = [
      workItemReference,
      { ...workItemReference, entityType: "project", entityId: "project-1" },
      { ...workItemReference, entityType: "cycle", entityId: "cycle-1" },
      { ...workItemReference, entityType: "module", entityId: "module-1" },
      { ...workItemReference, entityType: "page", entityId: "page-1" },
      { ...workItemReference, entityType: "view", entityId: "view-1" },
    ] satisfies EntityReferenceV1[];

    const results = await Promise.all(references.map((reference) => source.capture(reference, captureOptions)));
    results.forEach((result) => {
      expect(result).toMatchObject({ ok: true, observed: { source: "client_store", observedAt } });
      expect(JSON.stringify(result)).not.toContain("must-not-escape");
    });
  });

  test("rejects missing, cross-project, and editor records with typed failures", async () => {
    const { access, workItem } = createFixture();
    const source = createPlaneEntityContextSource({ access, now: () => observedAt });

    await expect(source.capture({ ...workItemReference, entityId: "missing" }, captureOptions)).resolves.toMatchObject({
      ok: false,
      code: "VALUE_UNAVAILABLE",
      retryable: true,
    });

    workItem.project_id = "project-2";
    await expect(source.capture(fieldReference("name"), captureOptions)).resolves.toMatchObject({
      ok: false,
      code: "VALUE_UNAVAILABLE",
    });

    await expect(
      source.capture(
        { kind: "editor_block", document: { ...workItemReference, entityType: "page" }, blockId: "block-1" },
        captureOptions
      )
    ).resolves.toMatchObject({ ok: false, code: "UNSUPPORTED", retryable: false });
  });
});

# Plane Agent Tooling Pilot Contracts

## Status

Proposed for release-manifest approval. The operation set and the coordinated release-plan scope are accepted; the exact schemas, limits, and approval effect labels in this document are not yet frozen. This document does not authorize implementation.

## Contract rules

- Every operation runs against the authenticated, request-bound workspace. Workspace identity is never an input field.
- Project and work-item references accept natural Plane identifiers, but the gateway resolves them once to immutable IDs before authorization or execution.
- The caller cannot provide credentials, actor IDs, audit IDs, attempt IDs, approval decisions, external integration IDs, timestamps, or mutation idempotency keys.
- Unknown input fields are rejected. Mutation inputs are normalized before their digest is calculated.
- UUIDs are lowercase canonical UUID strings. Dates use `YYYY-MM-DD`. Timestamps use UTC RFC 3339.
- HTML is sanitized by Plane's existing validator. Agent-visible HTML fields are limited to 64 KiB before sanitization.
- List limits apply before dispatch. Truncation is explicit and always returns a continuation cursor when more data is available.
- A read requires active membership in every referenced Plane object. A mutation additionally requires Plane's current member-or-admin mutation role for every affected project.
- Approval is evaluated only after authentication, reference resolution, input validation, and Plane authorization succeed. Approval never grants Plane permission.
- All expected outcomes use the gateway result envelope in `GATEWAY-WIRE.md`; operation-specific errors appear in its structured `error` object.

## Shared value shapes

```ts
type ProjectRef = { id: string; identifier?: never } | { id?: never; identifier: string };

type WorkItemRef =
  | { id: string; project?: never; sequence?: never }
  | { id?: never; project: ProjectRef; sequence: number };

type CycleRef = { id: string; current?: never } | { id?: never; current: true };

type Page = {
  limit?: number; // integer, 1..50; default 20
  cursor?: string; // opaque, at most 2 KiB
};
```

An identifier is case-insensitive on input and canonical uppercase on output. A reference that matches no authorized object returns `not_found`; Plane does not reveal whether an unauthorized object exists. A natural reference that resolves to multiple authorized objects returns `ambiguous_reference` with bounded authorized candidates.

## Canonical result projections

These are curated projections, not passthrough Django serializer responses.

```ts
type Project = {
  id: string;
  identifier: string;
  name: string;
  archived: boolean;
  cycle_enabled: boolean;
};

type Cycle = {
  id: string;
  project_id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
};

type WorkItem = {
  id: string;
  project_id: string;
  project_identifier: string;
  sequence: number;
  name: string;
  description_html: string;
  priority: "urgent" | "high" | "medium" | "low" | "none";
  state_id: string;
  parent_id: string | null;
  cycle_id: string | null;
  assignee_ids: string[];
  label_ids: string[];
  start_date: string | null;
  target_date: string | null;
  created_at: string;
  updated_at: string;
};

type Comment = {
  id: string;
  work_item_id: string;
  comment_html: string;
  actor_id: string;
  created_at: string;
};

type PageResult<T> = {
  items: T[];
  next_cursor: string | null;
  truncated: boolean;
};
```

## Read operations

### `plane.projects.resolve@1`

Purpose: convert an authorized project ID or identifier into one canonical project.

```ts
type Input = { id: string } | { identifier: string };

type Output = { project: Project };
```

Identifier matching is case-insensitive and exact. V1 deliberately excludes project-name resolution because names are not unique. Approval effect: `read`.

### `plane.cycles.list_current@1`

Purpose: return cycles whose start and end contain Plane's current server time.

```ts
type Input = { project: ProjectRef };
type Output = { cycles: Cycle[] }; // 0..10, ordered by start date then ID
```

This normalizes the current public endpoint's bare array response. More than one current cycle is preserved rather than guessed away. Approval effect: `read`.

### `plane.work_items.search@1`

Purpose: bounded search over names, numeric sequence IDs, and project identifiers.

```ts
type Input = {
  query: string; // trimmed, 1..256 characters
  project?: ProjectRef;
  page?: Page;
};

type Output = PageResult<
  Pick<
    WorkItem,
    "id" | "project_id" | "project_identifier" | "sequence" | "name" | "priority" | "state_id" | "updated_at"
  >
>;
```

Without `project`, results cover only projects in the bound workspace where the actor is an active member. Search does not expose raw PQL in v1. Approval effect: `read`.

### `plane.work_items.get@1`

Purpose: retrieve one work item with optionally bounded direct relations.

```ts
type Input = {
  work_item: WorkItemRef;
  include_relations?: boolean; // default true
};

type Output = {
  work_item: WorkItem;
  relations?: Array<{
    relation: string;
    work_item: Pick<WorkItem, "id" | "project_id" | "project_identifier" | "sequence" | "name">;
  }>;
  relations_truncated?: boolean;
};
```

Relations are limited to 50 and include only related work items independently visible to the actor. Approval effect: `read`.

### `plane.project_members.list@1`

Purpose: return bounded active project members for assignment and ownership choices.

```ts
type Input = { project: ProjectRef; page?: Page };
type Output = PageResult<{
  user_id: string;
  display_name: string;
  role: "guest" | "member" | "admin";
}>;
```

Email addresses and other profile data are excluded because the pilot does not need them. Approval effect: `read`.

## Mutation operations

### `plane.work_items.create@1`

Purpose: create one parent or child work item and optionally place it in a cycle.

```ts
type Input = {
  project: ProjectRef;
  name: string; // trimmed, 1..255 characters
  description_html?: string; // default "<p></p>"
  priority?: "urgent" | "high" | "medium" | "low" | "none";
  state_id?: string;
  parent?: WorkItemRef;
  cycle?: CycleRef;
  assignee_ids?: string[]; // unique, at most 20
  label_ids?: string[]; // unique, at most 20
  start_date?: string | null;
  target_date?: string | null;
};

type Output = { work_item: WorkItem };
```

The parent, cycle, state, assignees, and labels must belong to the resolved project and pass current Plane authorization. `start_date` cannot follow `target_date`. The gateway claims idempotency before creation; public `external_source` and `external_id` are not exposed as a substitute. Proposed approval effect: `work_item.write`.

### `plane.work_items.update@1`

Purpose: patch one work item and optionally change its current cycle placement.

```ts
type Input = {
  work_item: WorkItemRef;
  patch: {
    name?: string;
    description_html?: string;
    priority?: "urgent" | "high" | "medium" | "low" | "none";
    state_id?: string;
    parent?: WorkItemRef | null;
    cycle?: CycleRef | null;
    assignee_ids?: string[];
    label_ids?: string[];
    start_date?: string | null;
    target_date?: string | null;
  };
};

type Output = { work_item: WorkItem; changed_fields: string[] };
```

`patch` must contain at least one field. Arrays replace their corresponding complete set. `cycle: null` removes current cycle placement. Plane validates every changed reference and the final date range. Proposed approval effect: `work_item.write`.

### `plane.comments.create@1`

Purpose: create one source-linked comment on a work item.

```ts
type Input = {
  work_item: WorkItemRef;
  comment_html: string; // sanitized, 1 byte..64 KiB
  source?: {
    label: string; // 1..120 characters
    url: string; // HTTPS, at most 2 KiB
  };
};

type Output = { comment: Comment };
```

When `source` is supplied, Plane appends one canonical sanitized link block to the comment. The operation requires the same member-or-admin mutation role as work-item mutation even though the current public comment endpoint permits any active project member; v1 intentionally closes that mismatch. Proposed approval effect: `comment.write`.

### `plane.release_plans.create@1`

Purpose: atomically create the mandatory pilot planning artifact with one parent, exactly three children, one source-linked comment, and optional current-cycle placement.

```ts
type Input = {
  project: ProjectRef;
  cycle?: CycleRef;
  parent: {
    name: string;
    description_html?: string;
    priority?: "urgent" | "high" | "medium" | "low" | "none";
    state_id?: string;
    assignee_ids?: string[];
    label_ids?: string[];
    start_date?: string | null;
    target_date?: string | null;
  };
  children: [
    { name: string; description_html?: string; priority?: "urgent" | "high" | "medium" | "low" | "none" },
    { name: string; description_html?: string; priority?: "urgent" | "high" | "medium" | "low" | "none" },
    { name: string; description_html?: string; priority?: "urgent" | "high" | "medium" | "low" | "none" },
  ];
  source_comment: {
    comment_html: string;
    source: { label: string; url: string };
  };
};

type Output = {
  parent: WorkItem;
  children: [WorkItem, WorkItem, WorkItem];
  comment: Comment;
};
```

The gateway resolves and validates all references, checks authorization for the complete write set, evaluates approval policy once, and claims one durable idempotency record before any side effect. The autonomous default continues immediately; an administrator-configured `release_plan.write` prompt produces at most one decision for the whole composition. Database changes commit in one transaction; activity and webhook delivery use post-commit/outbox behavior. A failed transaction creates none of the five requested objects. A lost response is reconciled from the invocation record and returns the original five object IDs. Proposed approval effect: `release_plan.write`.

## Error codes

| Code                   | Meaning                                                             | Retry                             |
| ---------------------- | ------------------------------------------------------------------- | --------------------------------- |
| `invalid_input`        | Schema, field, date, HTML, or limit validation failed               | `never` until input changes       |
| `not_found`            | No authorized matching object exists                                | `never` until context changes     |
| `ambiguous_reference`  | A natural reference matched multiple authorized objects             | `never` until input becomes exact |
| `permission_denied`    | Plane authorization rejected the bound actor without object leakage | `never` until permission changes  |
| `approval_required`    | No side effect ran and a decision is required                       | resume the same invocation only   |
| `approval_rejected`    | A trusted decision rejected the exact input digest                  | `never` for that invocation       |
| `approval_expired`     | The pending decision expired before execution                       | `new_invocation`                  |
| `idempotency_conflict` | The invocation key was reused with different normalized input       | `never`                           |
| `catalog_stale`        | The caller's catalog digest is incompatible                         | `new_invocation` after refresh    |
| `conflict`             | Current Plane state prevents the requested change                   | depends on refreshed state        |
| `result_too_large`     | Result exceeded the approved inline and artifact policy             | narrower input or artifact read   |
| `outcome_unknown`      | A mutation outcome cannot yet be proven                             | `reconcile` only                  |

Validation errors may include bounded field paths and safe corrective hints. Authorization errors never include inaccessible object names, IDs, counts, or candidate lists.

## Source alignment and intentional differences

- `IssueSerializer` currently validates project-local states, parents, assignees, labels, dates, and HTML. The semantic contracts preserve those checks while excluding server-owned fields.
- The public current-cycle endpoint returns an unpaginated array; the semantic operation returns a named, bounded `cycles` field.
- The public issue and comment create endpoints use check-then-create external IDs. The gateway instead owns durable idempotency and reconciliation because check-then-create is not a concurrency guarantee.
- The public comment endpoint uses `ProjectLitePermission`, while work-item mutation uses `ProjectEntityPermission`. The semantic comment mutation adopts the stricter work-item mutation role for a consistent agent policy.
- The public API represents cycle placement through separate add and delete cycle-work-item endpoints. The semantic create, update, and release-plan operations make placement part of one contract and one invocation lifecycle.
- The public search endpoint returns a small ad hoc projection. The semantic search result uses the same canonical identifiers and bounded pagination as other pilot reads.

## Freeze requirements

Before these contracts can be approved and frozen:

1. Resolve who is authorized to answer optional administrator-configured prompts and how the same invocation resumes.
2. Confirm or revise the proposed approval effect labels and administrator matching rules.
3. Generate machine-readable JSON Schemas from the frozen catalog and pin their digest.
4. Add positive, denial, ambiguity, stale-reference, idempotency, lost-response, and size-bound fixtures for every operation.
5. Verify each authorization mapping against executable Plane permission tests.
6. Record every official MCP tool that maps to a pilot operation without changing its public MCP schema or behavior.

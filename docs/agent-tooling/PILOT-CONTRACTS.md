# Plane Agent Tooling Pilot Contracts

## Status

Proposed for release-manifest approval. The operation set and the coordinated release-plan scope are accepted; the exact schemas and limits in this document are not yet frozen. This document does not authorize implementation.

## Contract rules

- Every operation runs against the authenticated, request-bound workspace. Workspace identity is never an input field.
- Project and work-item references accept natural Plane identifiers, but the gateway resolves them once to immutable IDs before authorization or execution.
- The caller cannot provide credentials, actor IDs, audit IDs, attempt IDs, external integration IDs, timestamps, or mutation idempotency keys.
- Unknown input fields are rejected. Mutation inputs are normalized before their digest is calculated.
- UUIDs are lowercase canonical UUID strings. Dates use `YYYY-MM-DD`. Timestamps use UTC RFC 3339.
- HTML is parsed and sanitized at the semantic operation boundary with Plane's canonical rich-text validator. Agent-visible HTML fields are limited to 64 KiB before sanitization. Handlers may not rely on a public serializer path that omits that validator.
- List limits apply before dispatch. Truncation is explicit and always returns a continuation cursor when more data is available.
- A read requires active membership in every referenced Plane object. A mutation additionally requires Plane's current member-or-admin mutation role for every affected project.
- Plane authorization is the final runtime decision. Authorized operations continue immediately; unauthorized operations return a non-leaking denial with no side effect.
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
  start_date: string | null; // UTC RFC 3339 timestamp
  end_date: string | null; // UTC RFC 3339 timestamp
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

Identifier matching is case-insensitive and exact. V1 deliberately excludes project-name resolution because names are not unique.

### `plane.cycles.list_current@1`

Purpose: return cycles whose start and end contain Plane's current server time.

```ts
type Input = { project: ProjectRef; page?: Page };
type Output = PageResult<Cycle>; // ordered by start timestamp then ID
```

This normalizes the current public endpoint's bare array response. A cycle is current when `start_date <= now <= end_date` using Plane's UTC server instant. More than one current cycle is preserved rather than guessed away. The gateway uses a Plane-owned paginated query module that applies the shared page default and bounds before materializing results, orders by start timestamp then ID, and returns opaque cursor continuation with explicit truncation. It does not fetch the public endpoint's complete array and then page it in memory.

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

Without `project`, results cover only projects in the bound workspace where the actor is an active member. Search does not expose raw PQL in v1.

The current public search view's unordered limit-only response cannot satisfy this contract. The gateway uses a Plane-owned query module with stable sort keys, opaque cursor continuation, explicit truncation, and hydration of every curated output field. It does not expose direct database access to callers.

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

Relations are limited to 50 and include only related work items independently visible to the actor.

Authorization and hydration run independently for the base work item and every related work item. Omitted inaccessible relations reveal no related ID, project, name, count, or candidate data.

### `plane.project_members.list@1`

Purpose: return bounded active project members eligible for work-item assignment.

```ts
type Input = { project: ProjectRef; page?: Page };
type Output = PageResult<{
  user_id: string;
  display_name: string;
  role: "member" | "admin";
}>;
```

Guests, inactive members, bots, email addresses, and other profile data are excluded because they are not valid assignee choices for the pilot.

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

The parent, cycle, state, assignees, and labels must belong to the resolved project and pass current Plane authorization. Invalid mixed arrays reject the complete request rather than silently filtering elements. A parent cannot be the item itself or any descendant. `start_date` cannot follow `target_date`. The gateway claims idempotency before creation; public `external_source` and `external_id` are not exposed as a substitute.

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

`patch` must contain at least one field. Arrays replace their corresponding complete set. Invalid mixed arrays reject the complete patch rather than silently filtering elements. A parent cannot be the item itself or any descendant. `cycle: null` removes current cycle placement. Plane validates every changed reference and the final date range after merging the patch with stored dates.

Removing an already-unplaced work item is a successful idempotent no-op. `changed_fields` contains only fields whose stored semantic value changed, uses the canonical order `name`, `description_html`, `priority`, `state_id`, `parent`, `cycle`, `assignee_ids`, `label_ids`, `start_date`, `target_date`, and is empty for a no-op. Reordering an input set without changing its members is not a change.

### `plane.comments.create@1`

Purpose: create one comment on a work item, optionally with a canonical source link.

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

Omitting `source` creates the sanitized comment without a source block. When `source` is supplied, Plane escapes its label and appends exactly one canonical sanitized HTTPS link block after sanitizing the comment. The operation requires the same member-or-admin mutation role as work-item mutation even though the current public comment endpoint permits any active project member; v1 intentionally closes that mismatch.

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

The gateway resolves and validates all references, checks authorization for the complete write set, and commits one durable intent/idempotency record before any side effect. Authorized execution continues immediately. The four issues, four `IssueSequence` rows, one comment, one `Description` backing row, four cycle bridges, terminal-success audit fact, and invocation result transition commit through one named PostgreSQL connection and transaction. Failure of the success-audit insert or result transition, any failure before the commit request, or a server commit rejection that proves the transaction did not commit rolls back all application effects; after proven rollback and before responding, the gateway appends exactly one correlated `failed` outcome and moves the invocation to `retryable`. Loss of the commit acknowledgement is never treated as proven rollback: it returns `outcome_unknown` and requires reconciliation without blind retry. The frozen gateway/application-service path must register every initial activity/webhook publication with `transaction.on_commit()`; direct `.delay()` inside the transaction is forbidden. The complete path and publication multiset remain release-manifest inputs. A failed transaction executes zero registered callbacks and publishes zero tasks. Broker publications and eventual activity readback are verified separately and are not modeled as transactional outbox rows. A lost response after a known commit is reconciled from the invocation result and returns the original five object IDs.

When `cycle` is present, the parent and all three children are placed in that cycle. Child fields absent from the v1 input use Plane's ordinary create defaults: the project's default state, no assignees or labels, and null start and target dates. A workflow that needs richer child fields must use a later compatible contract version rather than smuggling unsupported fields into v1.

## Error codes

| Code                   | Meaning                                                             | Retry                             |
| ---------------------- | ------------------------------------------------------------------- | --------------------------------- |
| `invalid_input`        | Schema, field, date, HTML, or limit validation failed               | `never` until input changes       |
| `not_found`            | No authorized matching object exists                                | `never` until context changes     |
| `ambiguous_reference`  | A natural reference matched multiple authorized objects             | `never` until input becomes exact |
| `permission_denied`    | Plane authorization rejected the bound actor without object leakage | `never` until permission changes  |
| `idempotency_conflict` | The invocation key was reused with different normalized input       | `never`                           |
| `catalog_stale`        | The caller's catalog digest is incompatible                         | `new_invocation` after refresh    |
| `conflict`             | Current Plane state prevents the requested change                   | depends on refreshed state        |
| `result_too_large`     | Result exceeded the approved inline and artifact policy             | narrower input or artifact read   |
| `outcome_unknown`      | A mutation outcome cannot yet be proven                             | `reconcile` only                  |

Validation errors may include bounded field paths and safe corrective hints. Authorization errors never include inaccessible object names, IDs, counts, or candidate lists.

## Source alignment and intentional differences

- `IssueSerializer` currently validates several project-local references and rich text, but it silently filters invalid assignee/label rows and only compares dates supplied together. The semantic contracts deliberately reject the complete mutation on any invalid reference and validate the merged final date range.
- The public comment-create serializer does not invoke the richer comment HTML validator. The semantic comment operation invokes canonical sanitization at its own boundary and does not inherit that omission.
- The public current-cycle endpoint returns an unpaginated array; the semantic operation returns a named, bounded `cycles` field.
- The public issue and comment create endpoints use check-then-create external IDs. The gateway instead owns durable idempotency and reconciliation because check-then-create is not a concurrency guarantee.
- The public comment endpoint uses `ProjectLitePermission`, while work-item mutation uses `ProjectEntityPermission`. The semantic comment mutation adopts the stricter work-item mutation role for a consistent agent policy.
- The public API represents cycle placement through separate add and delete cycle-work-item endpoints. The semantic create, update, and release-plan operations make placement part of one contract and one invocation lifecycle.
- The public search endpoint returns an unordered limit-only ad hoc projection. The semantic query module owns deterministic cursor pagination and hydration of the curated search fields.

## Freeze requirements

Before these contracts can be approved and frozen:

1. Generate machine-readable JSON Schemas from the frozen catalog and pin their digest.
2. Add positive, denial, ambiguity, stale-reference, idempotency, lost-response, and size-bound fixtures for every operation.
3. Verify each authorization mapping against executable Plane permission tests.
4. Record every official MCP tool that maps to a pilot operation without changing its public MCP schema or behavior.

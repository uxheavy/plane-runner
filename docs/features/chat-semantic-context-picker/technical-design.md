# Technical Design: Chat Semantic Context Picker

## Stack decisions

| Layer             | Technology                                  | Reason                                                            |
| ----------------- | ------------------------------------------- | ----------------------------------------------------------------- |
| Selection engine  | TypeScript DOM module                       | Matches Plane and can remain independent of React presentation.   |
| Framework adapter | React                                       | Matches `apps/web` and the future composer UI.                    |
| Entity values     | Existing MobX stores                        | Provides current normalized Plane state.                          |
| Editor context    | Existing Tiptap and Yjs interfaces          | Preserves stable block IDs and client-live collaborative content. |
| Server resolution | Existing Django/Python API                  | Reuses Plane permission and entity-query behavior.                |
| Tests             | Existing TypeScript and Django test tooling | Avoids parallel infrastructure.                                   |

## Public core module

```ts
interface SemanticContextPicker {
  register(element: Element, target: SemanticTarget): () => void;
  select(request: SelectionRequest): Promise<SelectionResult>;
  dispose(): void;
}
```

| Operation         | Responsibility                                           | Excludes                                        |
| ----------------- | -------------------------------------------------------- | ----------------------------------------------- |
| `register`        | Associate a mounted element with typed Plane identity    | Values, records, permissions, and DOM metadata  |
| `select: preview` | Locate and rank candidates                               | MobX/editor value reads                         |
| `select: capture` | Resolve current allowlisted values and serialize context | Treating client data as authorized or canonical |
| `dispose`         | Cancel work and release browser resources                | UI state ownership                              |

React convenience hooks and an overlay session controller are thin Adapters. The
registry, React Grab integration, resolvers, serializer, and lifecycle state remain
private Implementations of the core Module.

## Plane reference contract

```ts
type EntityReferenceV1 = {
  kind: "entity";
  workspaceSlug: string;
  projectId?: string;
  entityType: "work_item" | "project" | "cycle" | "module" | "page" | "view";
  entityId: string;
};

type WorkItemContextField =
  | "name"
  | "description"
  | "state"
  | "priority"
  | "assignees"
  | "labels"
  | "start_date"
  | "target_date"
  | "estimate"
  | "cycle"
  | "module";

type SemanticReferenceV1 =
  | EntityReferenceV1
  | {
      kind: "field";
      entity: EntityReferenceV1 & { entityType: "work_item"; projectId: string };
      fieldKey: WorkItemContextField;
    }
  | {
      kind: "editor_block";
      document: EntityReferenceV1 & { entityType: "page" | "work_item" };
      blockId: string;
    }
  | {
      kind: "editor_range";
      document: EntityReferenceV1 & { entityType: "page" | "work_item" };
      start: { blockId: string; offset: number };
      end: { blockId: string; offset: number };
    };
```

Field keys are explicit allowlists grouped by entity type, never arbitrary property
paths. Other entity field unions are added with their adapters. Editor blocks use
Plane's existing `UniqueID` values. Ranges use start/end block IDs plus ProseMirror
offsets relative to each block's content. See
[ADR 0003](./decisions/0003-live-editor-identity.md).

## Selection contract

```ts
type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

type SemanticTarget = {
  reference: SemanticReferenceV1;
  parent?: SemanticReferenceV1;
};

type SelectionRequest = {
  operation: "preview" | "capture";
  area:
    | { kind: "point"; clientX: number; clientY: number }
    | { kind: "region"; left: number; top: number; right: number; bottom: number };
  ancestorOffset?: number;
  signal?: AbortSignal;
};

type ContextCandidateV1 = {
  schemaVersion: 1;
  reference: SemanticReferenceV1;
  label: string;
  selectableAncestors: SemanticReferenceV1[];
};

type ContextItemV1 = {
  reference: SemanticReferenceV1;
  observed: {
    source: "client_store" | "client_live";
    value: JsonValue;
    observedAt: string;
    entityVersion?: string;
  };
  location: { url: string };
};

type SemanticContextBundleV1 = {
  schemaVersion: 1;
  selectionKind: "point" | "region";
  items: ContextItemV1[];
  warnings: SelectionFailureV1[];
};

type SemanticContextBundle = SemanticContextBundleV1;

type SelectionResult =
  | { ok: true; operation: "preview"; candidates: ContextCandidateV1[] }
  | { ok: true; operation: "capture"; context: SemanticContextBundle }
  | { ok: false; failure: SelectionFailureV1 };
```

Preview does not expose values. Capture returns only JSON-safe data. Input and
output types are separate even when their fields overlap.

## Context envelope

```json
{
  "schemaVersion": 1,
  "selectionKind": "point",
  "items": [
    {
      "reference": {
        "kind": "field",
        "entity": {
          "kind": "entity",
          "workspaceSlug": "acme",
          "projectId": "project-uuid",
          "entityType": "work_item",
          "entityId": "work-item-uuid"
        },
        "fieldKey": "priority"
      },
      "observed": {
        "value": "high",
        "observedAt": "ISO-8601 timestamp",
        "source": "client_store"
      },
      "location": {
        "url": "/acme/projects/project-uuid/issues/work-item-uuid"
      }
    }
  ],
  "warnings": []
}
```

Editor captures use `source: "client_live"`. Region captures contain multiple
items and may succeed with structured warnings.

Visual fallback is a separate in-memory contract. It produces an exact PNG crop
with `semantic: false`, known Plane references, and `pending_review` status. Only
a live preview confirmed exactly once becomes a visual attachment. It never
serializes the semantic observations into visual metadata and performs no upload
or persistent storage. See [ADR 0006](./decisions/0006-visual-fallback-boundary.md).

## Failure contract

```ts
type SelectionFailureV1 = {
  schemaVersion: 1;
  code: "NO_TARGET" | "TARGET_GONE" | "UNSUPPORTED" | "VALUE_UNAVAILABLE" | "ABORTED" | "TOO_MANY_TARGETS";
  message: string;
  reference?: SemanticReferenceV1;
  retryable: boolean;
};
```

| Code                | Meaning                                                            | Retryable |
| ------------------- | ------------------------------------------------------------------ | --------- |
| `NO_TARGET`         | Nothing semantic matched the selection                             | No        |
| `TARGET_GONE`       | The registered target detached before capture                      | Yes       |
| `UNSUPPORTED`       | The target has no approved resolver                                | No        |
| `VALUE_UNAVAILABLE` | Identity is known but its value cannot be read                     | Yes       |
| `ABORTED`           | Navigation, cancellation, or a newer selection ended the operation | Yes       |
| `TOO_MANY_TARGETS`  | A region exceeded its bounded result limit                         | No        |

Permission, missing, and stale failures from server hydration use the same
structured result convention but remain a separate server output type.

## Server hydration contract

The composer submits 1-50 ordered references to:

```text
POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/
```

Each request item contains a `reference` and may include the client's
`observedEntityVersion`. Each valid item returns either:

- `resolution: canonical` with an allowlisted `server_canonical` observation
  and explicit `stale` flag; or
- `resolution: authorization_only` for a live editor reference whose parent
  document is still visible to the acting user.

Failures use `FORBIDDEN`, `NOT_FOUND`, or `UNSUPPORTED`. Malformed batches fail
as HTTP 400 before resolution. Valid item failures stay inside an HTTP 200 batch
so one deleted region target does not discard the rest. See
[ADR 0004](./decisions/0004-server-hydration-boundary.md).

## Freshness rules

| Source               | Treatment                                                                               |
| -------------------- | --------------------------------------------------------------------------------------- |
| MobX entity          | Capture the immediate observed value and entity `updated_at` when available.            |
| Django entity        | Re-fetch under the acting user when the message is submitted or used.                   |
| Collaborative editor | Capture selected content from the live Tiptap/Yjs state and identify it as client-live. |
| Conflict             | Preserve the observed value and canonical value with separate timestamps.               |

## Permission and privacy rules

- Server hydration uses existing Plane project, workspace, and private-page permission paths.
- Client references are identifiers, not proof of authorization.
- Field resolvers expose allowlisted context only.
- Picker UI, secrets, tokens, password inputs, and designated sensitive surfaces are ignored.
- Snapshot previews show the exact crop before attachment.
- Stored context follows chat retention, sharing, deletion, and audit behavior.
- Selected user content is treated as untrusted agent input.

## Integration boundary

The composer implementation is not present in this checkout. The core branch therefore provides:

- Versioned types for selection requests and context results.
- A callback- or adapter-based composer interface.
- Fixtures demonstrating entity, field, editor, region, and failure results.
- Contract tests that a future composer adapter can reuse.

The exported `SemanticContextComposerAdapter` composes two caller-owned ports:
authenticated hydration and verified attachment consumption. It validates
unknown server JSON, requires exact ordered reference echoes, strips denied
observations, and preserves canonical/client values separately. See
[ADR 0005](./decisions/0005-composer-integration-interface.md).

The missing composer does not block core implementation. It blocks final end-to-end verification only.

See [Interface design](./interface-design.md) and
[ADR 0002](./decisions/0002-picker-core-interface.md) for the alternatives and
the stable contract decision.

## Open-source references

| Project                                                              | Use                                                                           | License  | Decision                                          |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------- | ------------------------------------------------- |
| [React Grab](https://github.com/aidenybai/react-grab)                | Hit-testing, ignored subtrees, page-freezing, and picker lifecycle primitives | MIT      | Primary foundation behind a Plane-owned adapter   |
| [React Dev Inspector](https://github.com/zthxxx/react-dev-inspector) | Inspector activation, hover, click, and cleanup reference                     | MIT      | Secondary reference                               |
| [stagewise](https://github.com/stagewise-io/stagewise)               | Selected-browser-context-to-agent product model                               | AGPL-3.0 | Product reference; do not import the full toolbar |
| [html2canvas](https://github.com/niklasvh/html2canvas)               | Historical DOM-rendering lineage                                              | MIT      | Reference only; not a production dependency       |
| [html2canvas-pro](https://github.com/yorickshan/html2canvas-pro)     | DOM pixels, exact crops, cancellation, and modern CSS colors                  | MIT      | Sole production renderer, pinned at 2.3.2         |

## Dependency rule

React Grab and `html2canvas-pro` are isolated behind Plane-owned Adapters. The
renderer uses a separate package subpath so the semantic core does not load it.
Plane-specific references, values, permissions, privacy policy, and serialization
remain Plane-owned because external inspector tools resolve pixels or source-code
context rather than Plane domain objects.

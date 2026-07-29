# Technical Design: Chat Semantic Context Picker

## Stack decisions

| Layer | Technology | Reason |
| --- | --- | --- |
| Selection engine | TypeScript DOM module | Matches Plane and can remain independent of React presentation. |
| Framework adapter | React | Matches `apps/web` and the future composer UI. |
| Entity values | Existing MobX stores | Provides current normalized Plane state. |
| Editor context | Existing Tiptap and Yjs interfaces | Preserves stable block IDs and client-live collaborative content. |
| Server resolution | Existing Django/Python API | Reuses Plane permission and entity-query behavior. |
| Tests | Existing TypeScript and Django test tooling | Avoids parallel infrastructure. |

## Core modules

| Module | Responsibility | Excludes |
| --- | --- | --- |
| Selection adapter | Hit-test a point, ignore picker UI, and normalize browser events | Plane entity knowledge |
| Context target registry | Register visible semantic targets and select point/region candidates | Rendering overlays or chips |
| Context resolver | Convert a registered target into allowlisted current context | Authorization decisions |
| Editor adapter | Resolve page, block, embed, and text-range context | Generic entity-store lookup |
| Serializer | Produce a versioned composer-safe context envelope | Fetching authoritative values |
| Server hydrator | Reauthorize references and resolve canonical current values | Trusting client-supplied values |
| Composer adapter | Convert core results to the composer attachment interface | Composer presentation |

## Context envelope

```json
{
  "version": 1,
  "reference": {
    "workspaceSlug": "acme",
    "projectId": "project-uuid",
    "entityType": "work_item",
    "entityId": "work-item-uuid",
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
```

Editor selections may add page ID, block IDs, text ranges, selected content, and `source: "client_live"`. Region selections may contain multiple references and an optional snapshot attachment.

## Freshness rules

| Source | Treatment |
| --- | --- |
| MobX entity | Capture the immediate observed value and entity `updated_at` when available. |
| Django entity | Re-fetch under the acting user when the message is submitted or used. |
| Collaborative editor | Capture selected content from the live Tiptap/Yjs state and identify it as client-live. |
| Conflict | Preserve the observed value and canonical value with separate timestamps. |

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

The missing composer does not block core implementation. It blocks final end-to-end verification only.

## Open-source references

| Project | Use | License | Decision |
| --- | --- | --- | --- |
| [React Grab](https://github.com/aidenybai/react-grab) | Hit-testing, ignored subtrees, page-freezing, and picker lifecycle primitives | MIT | Primary foundation behind a Plane-owned adapter |
| [React Dev Inspector](https://github.com/zthxxx/react-dev-inspector) | Inspector activation, hover, click, and cleanup reference | MIT | Secondary reference |
| [stagewise](https://github.com/stagewise-io/stagewise) | Selected-browser-context-to-agent product model | AGPL-3.0 | Product reference; do not import the full toolbar |
| [html2canvas](https://github.com/niklasvh/html2canvas) | Possible later visual fallback | MIT | Evaluate separately; not foundational |

## Dependency rule

React Grab is isolated behind the selection adapter. Plane-specific references, values, permissions, and serialization remain Plane-owned because external inspector tools resolve source-code context rather than Plane domain objects.

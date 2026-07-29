# Product Specification: Chat Semantic Context Picker

## Outcome and evidence

| Question | Decision |
| --- | --- |
| User problem | Describing visible Plane content to an agent is slow and loses object identity. |
| Outcome | Point at visible content and attach structured, current context to a message. |
| Idea validation | Complete through sustained use of inspector modes in Cursor and Codex. |
| Validation still required | Plane-specific accuracy, privacy, editor freshness, and integration quality. |
| Primary user | Repository owner; staged rollout and broad adoption analytics are unnecessary. |

## User workflow

1. Activate context-picking mode from the composer.
2. Hover to preview the smallest meaningful selectable target.
3. Click an artifact or field, or drag over a visible region.
4. Review removable context chips and any visual preview.
5. Send the message with the selected context.
6. Plane rechecks access and resolves authoritative values before agent use.

## Coverage boundary

| Coverage | Targets | Required result |
| --- | --- | --- |
| First-class | Work-item rows/cards, work-item fields, projects, cycles, modules, pages, views | Structured entity and optional field reference |
| Editor | Page blocks, issue-description blocks, selected text, work-item embeds | Page or work-item reference plus block/range content |
| Region | Multiple visible registered targets | Deduplicated structured references |
| Visual fallback | Charts, Gantt regions, images, PDFs, complex or unregistered regions | Explicitly labeled snapshot plus known intersecting references |
| Unsupported | Hidden or unmounted content, cross-origin internals, sensitive denied surfaces | No selection or a clear visual-only result |

## First release boundary

The first usable release includes:

- Point selection for routed entities, common rows/cards, work-item fields, and editor blocks.
- Structured context chips with a clear sharing preview.
- Client-observed values plus server-authorized resolution.
- Permission denial and stale/deleted-object handling.
- An integration contract for the unavailable Plane AI composer.

Region selection and snapshots follow after point selection is reliable. Their contracts belong in the core from the start, but they do not block the first usable release.

## Acceptance criteria

| Area | Criterion |
| --- | --- |
| Selection | A supported visible target resolves to the correct Plane entity and field without DOM-ID guessing. |
| Nesting | The default is the smallest meaningful target; the user can choose its containing object. |
| Freshness | Context records the client-observed value and distinguishes it from server-resolved data. |
| Editor | Unsynced collaborative content is labeled as client-live and remains tied to page/block IDs. |
| Permissions | Every server resolution and later agent action rechecks the acting user's access. |
| Privacy | Object selection sends allowlisted fields only; snapshots require an explicit preview. |
| Failure | Deleted, stale, inaccessible, or unsupported targets fail visibly and safely. |
| Integration | The composer can consume the package without depending on Plane UI implementation details. |
| Tests | Core contracts, hit-testing adapters, resolvers, serialization, and permission behavior are covered. |

## Product constraints

- Do not attach entire MobX records.
- Do not treat DOM visibility as durable authorization.
- Do not place current values or sensitive metadata in DOM attributes.
- Do not claim semantic meaning for arbitrary pixels.
- Do not require a new language, browser extension, or independent service.
- Do not add staged-rollout infrastructure for a single-user release.

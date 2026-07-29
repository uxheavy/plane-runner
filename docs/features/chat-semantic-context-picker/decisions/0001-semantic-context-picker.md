# ADR 0001: Semantic Context Picker Boundaries

- Status: Accepted
- Date: 2026-07-29

## Context

Plane needs a browser inspector-style interaction that preserves domain identity,
fresh collaborative content, and authorization. The target composer UI is not in
this checkout, so the reusable core cannot depend on its presentation or state.
Some visible regions have no complete semantic representation and require a
pixel fallback with a stricter privacy boundary.

## Decision

Build one TypeScript package and one Django hydration endpoint with these
boundaries:

- Use the pinned `react-grab` primitives only for hit testing. Keep registration,
  Plane identity, lifecycle, and values behind a Plane-owned adapter.
- Expose a small picker interface: `register`, `select`, and `dispose`. References
  are versioned, typed, and contain identifiers rather than values.
- Resolve work-item and entity observations from current Plane stores at capture
  time. Use existing Tiptap block IDs and block-relative offsets for live editor
  blocks and ranges; do not serialize Yjs documents or arbitrary node attributes.
- Treat every browser value as an observation, never authorization. Before agent
  use, batch references through the authenticated workspace hydration endpoint,
  which applies active membership, project scope, guest visibility, private-object,
  and soft-deletion rules.
- Connect the absent composer through hydration and consumer ports. Runtime-parse
  the server response, preserve request order, and remove denied client values
  before invoking the consumer.
- Use `html2canvas-pro` as the sole optional screenshot renderer. Deny passwords,
  authentication fields, iframes, and marked sensitive surfaces before rendering;
  keep the PNG in memory and require explicit preview confirmation.

## Rejected alternatives

- DOM text, paths, or attributes as semantic identity: unstable and unsafe.
- Trusting authenticated browser values: authentication does not prove object
  visibility or freshness.
- Existing full API serializers: broader than the context allowlist.
- Cached editor HTML or serialized Yjs state: stale or tightly coupled.
- A custom DOM-to-canvas implementation or multiple production renderers: high
  complexity and inconsistent privacy behavior.
- Coupling the core to React presentation or the unavailable composer: blocks
  independent verification and the separate UI branch.

## Consequences

- Plane renderers must explicitly register meaningful targets.
- New entity fields and editor embeds require an allowlisted projector and tests.
- Client-live editor content remains labeled as an observation while the server
  authorizes its containing document.
- Visual capture stays optional and separately bundled.
- The UI owns activation, highlighting, review, removal, and send behavior.

## Reconsider when

Revisit the boundary if Plane adopts another selection engine, needs durable editor
anchors, adds snapshot storage or retention, or exposes a composer contract that
cannot be represented by the current consumer port.

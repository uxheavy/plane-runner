# ADR 0003: Use Plane Block IDs and Block-Relative Range Offsets

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

Plane's Tiptap editors already apply the `UniqueID` extension to semantic block
nodes and render the value as `data-id`. Collaborative page documents update the
same Tiptap state through Yjs. The picker needs identity that survives DOM layout
changes without serializing editor internals or stale cached HTML.

## Decision

| Concern         | Decision                                                                            |
| --------------- | ----------------------------------------------------------------------------------- |
| Block identity  | Use the existing node `id` assigned by Plane's `UniqueID` extension.                |
| Range identity  | Store start/end block IDs and ProseMirror offsets relative to each block's content. |
| Range value     | Capture current plain text from live Tiptap state immediately.                      |
| Embed identity  | Keep `editor_block`; select an allowlisted projector by node type.                  |
| Work-item embed | Emit approved entity, project, workspace, and display fields.                       |
| Image embed     | Emit asset ID, upload status, and alt text; never emit `src`.                       |
| Yjs             | Read the Yjs-updated Tiptap document; never serialize the Y.Doc or provider.        |
| Composition     | Delegate entity and field references to the M3 `ContextSource`.                     |

Offsets use ProseMirror content positions, not Unicode character indexes. They
identify an immediate client-live observation; they are not canonical server
anchors after later collaborative edits.

## Invariants

- Missing or duplicate block IDs fail with `VALUE_UNAVAILABLE`.
- Invalid, reversed, atom-based, or stale ranges fail instead of widening.
- Preview labels do not read editor content.
- Editor registration is replacement-safe and returns an unmount disposer.
- Arbitrary node attributes, image URLs, provider state, and whole documents never
  enter the semantic bundle.

## Rejected alternatives

| Alternative                         | Reason                                                                       |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| DOM text and element paths          | Layout-dependent and disconnected from Yjs state.                            |
| Document-wide absolute positions    | Any preceding edit shifts the identity.                                      |
| Yjs relative-position serialization | Couples the wire contract to a Y.Doc the composer and server do not possess. |
| Cached `description_html`           | Can lag collaborative state and bypass block identity.                       |
| Arbitrary node attributes           | Exposes signed URLs and future fields without review.                        |

## Consequences

| Positive                                                    | Cost                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------------------------------ |
| UI branch registers an existing Tiptap editor with one call | Registration must follow editor mount/unmount.                           |
| Captures observe local and remote Yjs edits immediately     | Saved ranges are snapshot identity, not durable bookmarks.               |
| No Tiptap runtime dependency enters the picker bundle       | The structural editor Interface must track required ProseMirror methods. |
| Embed privacy is centralized                                | New embed node types require an explicit projector and test.             |

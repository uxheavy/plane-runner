# M4 Evidence Contract: Live Plane Editor Context

## Non-visual exception

M4 is a non-UI Tiptap/Yjs Adapter. Evidence uses real Tiptap editors in Chrome,
Yjs-backed updates, Plane-compatible block IDs, range references, and allowlisted
embed projections.

## Selected evidence

| Scenario        | Acceptance proof                                                           | Prevention proof                                                       |
| --------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Live block      | Capture returns current block type and text after an editor mutation       | Cached page or work-item HTML is never read                            |
| Text range      | Current selection becomes block-relative start/end identity and fresh text | Invalid offsets and ambiguous block IDs fail explicitly                |
| Work-item embed | Approved workspace, project, entity, and name fields are present           | Arbitrary node attributes are excluded                                 |
| Image embed     | Asset ID, status, and alt text are present                                 | Signed or private `src` values never enter context                     |
| Yjs update      | Capture observes a change made through another editor on the same Y.Doc    | The Adapter does not serialize the Y.Doc or provider                   |
| Lifecycle       | Replacement registration survives a stale disposer                         | Missing, duplicate, destroyed, and unregistered editors cannot capture |

## Contract boundary

| Decision       | Boundary                                                               |
| -------------- | ---------------------------------------------------------------------- |
| Block identity | Existing Plane `UniqueID` `id` attribute rendered as `data-id`         |
| Range identity | Start/end block IDs plus ProseMirror offsets relative to block content |
| Embed identity | `editor_block` reference; node type selects an allowlisted projector   |
| Freshness      | Immediate live Tiptap state with `source: client_live`                 |
| Composition    | Editor source delegates entity and field references to the M3 source   |

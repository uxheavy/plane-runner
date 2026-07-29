# ADR 0006: Keep Visual Fallback In Memory Behind a Privacy Gate

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

| Constraint                                                     | Evidence                                                      |
| -------------------------------------------------------------- | ------------------------------------------------------------- |
| Charts and images lack complete semantic representations       | Pixels are a required fallback.                               |
| Pixels may include credentials or private embeds               | Capture needs a pre-render privacy gate.                      |
| Preview UI belongs to another branch                           | Core must expose state, not presentation.                     |
| Original `html2canvas` is old and lacks modern `oklch` support | Maintained MIT fork `html2canvas-pro` supports modern colors. |

## Decision

- Export Plane-owned `VisualContextCapture` and `VisualRegionRendererPort` contracts.
- Normalize and bound every crop to the visible viewport.
- Deny a crop before rendering when it intersects passwords, authentication-code
  fields, iframes, or `data-plane-context-sensitive` surfaces, including open
  shadow roots.
- Always exclude picker chrome, React Grab ignored content, and sensitive nodes
  inside the renderer as a second defense against DOM changes during capture.
- Disable tainted and cross-origin image capture in the provided
  html2canvas-compatible Adapter.
- Keep PNG data in memory as a `Blob`; do not upload or persist it.
- Return `semantic: false` and carry known Plane references separately.
- Require a live `pending_review` preview to be explicitly confirmed exactly once
  before it becomes an attachment.

- Accept an html2canvas-compatible function without importing its package.
- Let the UI branch pin `html2canvas-pro` after testing final application styles.

## Rejected alternatives

| Alternative                               | Reason                                                            |
| ----------------------------------------- | ----------------------------------------------------------------- |
| Build a custom DOM-to-canvas renderer     | Browser rendering is not trivial and has proven open-source work. |
| Bundle original `html2canvas` 1.4.1       | It is stale and fails on CSS used by modern applications.         |
| Capture the whole viewport then crop      | Denied pixels would exist in memory before policy enforcement.    |
| Automatically attach a successful capture | The product requires exact-crop review before sharing.            |
| Upload snapshots from the core            | Storage, retention, and transport are outside the approved scope. |

## Consequences

| Positive                                                   | Cost                                                            |
| ---------------------------------------------------------- | --------------------------------------------------------------- |
| Privacy policy is renderer-independent and browser-tested  | UI integration must provide and verify one renderer function.   |
| The renderer never runs for intersecting sensitive content | Marking non-standard secret surfaces remains a caller duty.     |
| Visual evidence cannot be mistaken for semantic context    | Composer transport must model visual and semantic parts.        |
| No new persistent store or service is introduced           | Previews disappear when their owning page/session is discarded. |

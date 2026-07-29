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
- Pin `html2canvas-pro` 2.3.2 as the only production DOM screenshot engine and
  expose its Adapter from `@plane/chat-context/html2canvas-pro`.
- Disable tainted and cross-origin image capture in that Adapter and pass the
  capture cancellation signal into the renderer.
- Keep PNG data in memory as a `Blob`; do not upload or persist it.
- Return `semantic: false` and carry known Plane references separately.
- Require a live `pending_review` preview to be explicitly confirmed exactly once
  before it becomes an attachment.

- Keep the renderer in a package subpath so semantic-only consumers do not bundle it.
- Keep `VisualRegionRendererPort` as the test and host seam, not as an invitation
  to ship a second production renderer.

## Rejected alternatives

| Alternative                               | Reason                                                            |
| ----------------------------------------- | ----------------------------------------------------------------- |
| Build a custom DOM-to-canvas renderer     | Browser rendering is not trivial and has proven open-source work. |
| Bundle original `html2canvas` 1.4.1       | It is stale and fails on CSS used by modern applications.         |
| Let each host choose its own renderer     | It recreates compatibility and privacy decisions in every caller. |
| Capture the whole viewport then crop      | Denied pixels would exist in memory before policy enforcement.    |
| Automatically attach a successful capture | The product requires exact-crop review before sharing.            |
| Upload snapshots from the core            | Storage, retention, and transport are outside the approved scope. |

## Consequences

| Positive                                                   | Cost                                                            |
| ---------------------------------------------------------- | --------------------------------------------------------------- |
| Privacy policy is renderer-independent and browser-tested  | DOM rendering adds a separately loaded 66,950-byte gzip bundle. |
| The renderer never runs for intersecting sensitive content | Marking non-standard secret surfaces remains a caller duty.     |
| Visual evidence cannot be mistaken for semantic context    | Composer transport must model visual and semantic parts.        |
| No new persistent store or service is introduced           | Previews disappear when their owning page/session is discarded. |

## Proven reference boundary

The public Codex app-server source exposes protocol and configuration rather
than its proprietary browser annotation implementation. The installed Codex
browser contracts nevertheless confirm the useful separation: element metadata
and DOM snapshots are acquired independently from viewport or element pixels.
Plane follows that architecture but cannot reuse Codex's privileged native
capture backend, so the web-safe pixel implementation is `html2canvas-pro`.

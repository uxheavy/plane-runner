# M8 Evidence: Privacy-Safe Visual Fallback

## Delivered boundary

- `createVisualContextCapture` for bounded region policy, preview, confirmation,
  cancellation, and disposal;
- `VisualRegionRendererPort` as a narrow host and test seam;
- `createHtml2CanvasProVisualRenderer` from
  `@plane/chat-context/html2canvas-pro`, backed directly by pinned
  `html2canvas-pro` 2.3.2; and
- `PLANE_CONTEXT_SENSITIVE_ATTRIBUTE` for Plane surfaces that must never become
  pixels.

| Snapshot property | Contract                                                    |
| ----------------- | ----------------------------------------------------------- |
| Data              | In-memory PNG `Blob`                                        |
| Meaning           | Always `semantic: false`                                    |
| References        | Deduplicated IDs without copies of observed semantic values |

The renderer is a separate package entry, so semantic-only consumers do not
load screenshot code. It is the single production renderer; the port remains
for deterministic core tests and host lifecycle composition.

```ts
import { createVisualContextCapture } from "@plane/chat-context";
import { createHtml2CanvasProVisualRenderer } from "@plane/chat-context/html2canvas-pro";

const visualCapture = createVisualContextCapture({
  document,
  renderer: createHtml2CanvasProVisualRenderer(),
});
```

## Privacy behavior

| Case                             | Result                                             |
| -------------------------------- | -------------------------------------------------- |
| Password or authentication input | Denied before renderer invocation                  |
| Plane-marked sensitive surface   | Denied before renderer invocation                  |
| Iframe                           | Denied rather than attempting cross-origin capture |
| Open shadow-root secret          | Denied by composed-tree inspection                 |
| Picker or React Grab chrome      | Ignored by renderer predicate                      |
| Sensitive node introduced late   | Ignored by renderer predicate as a second defense  |
| Crop exceeds pixel/blob limits   | Structured non-retryable failure                   |
| Wrong dimensions or media type   | Rejected as an invalid capture                     |
| Unreviewed or reused preview     | Cannot produce a confirmed attachment              |
| Cancelled or disposed operation  | Late pixels are discarded                          |

## Verification

| Verifier        | Result                                                       |
| --------------- | ------------------------------------------------------------ |
| Runtime         | Real headless Chrome through production contracts            |
| Pixel proof     | Exact 64×48 PNG from `oklch`; ignored red overlay absent     |
| Browser suite   | 40 tests across eight files                                  |
| Package gates   | TypeScript, OxLint, Oxfmt, declarations, and build pass      |
| Core bundle     | 20,803 gzip bytes of 30,000; no forbidden inspector markers  |
| Renderer bundle | 66,955 gzip bytes of 100,000; pinned renderer marker present |

```text
Test Files  8 passed (8)
Tests       40 passed (40)
```

See [ADR 0006](./decisions/0006-visual-fallback-boundary.md).

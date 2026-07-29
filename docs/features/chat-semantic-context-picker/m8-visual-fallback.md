# M8 Evidence: Privacy-Safe Visual Fallback

## Delivered boundary

- `createVisualContextCapture` for bounded region policy, preview, confirmation,
  cancellation, and disposal;
- `VisualRegionRendererPort` for a caller-owned DOM renderer;
- `createHtml2CanvasVisualRenderer` for safe, exact-region configuration of an
  html2canvas-compatible implementation; and
- `PLANE_CONTEXT_SENSITIVE_ATTRIBUTE` for Plane surfaces that must never become
  pixels.

| Snapshot property | Contract                                                    |
| ----------------- | ----------------------------------------------------------- |
| Data              | In-memory PNG `Blob`                                        |
| Meaning           | Always `semantic: false`                                    |
| References        | Deduplicated IDs without copies of observed semantic values |

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

| Verifier       | Result                                      |
| -------------- | ------------------------------------------- |
| Runtime        | Real headless Chrome through public exports |
| Browser suite  | 34 tests across seven files                 |
| Package gates  | TypeScript, OxLint, Oxfmt, and build pass   |
| Bundle ceiling | 21,120 gzip bytes of 30,000; no bad markers |

```text
Test Files  7 passed (7)
Tests       34 passed (34)
```

See [ADR 0006](./decisions/0006-visual-fallback-boundary.md).

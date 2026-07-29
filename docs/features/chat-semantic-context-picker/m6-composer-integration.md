# M6 Evidence: Composer Integration Kit

## Public seam

```ts
const adapter = createSemanticContextComposerAdapter({
  hydration: {
    hydrate: (workspaceSlug, request, { signal }) =>
      planeApi.post(`/api/workspaces/${workspaceSlug}/chat-context/hydrate/`, request, { signal }),
  },
  consumer: {
    attachContext: (attachment) => composer.attachPlaneContext(attachment),
  },
});

const result = await adapter.attachContext(capturedBundle, { signal });
```

These are the only callbacks the future composer integration must provide. The
package has no Plane UI import and does not assume React, MobX, or a transport
library at this boundary.

## Attachment contract

| Field               | Meaning                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------ |
| `items`             | Authorized client observations paired with canonical or authorization-only server evidence |
| `selectionWarnings` | Capture-time region or value failures                                                      |
| `hydrationWarnings` | Permission, deletion, or unsupported failures returned by Django                           |
| `selectionKind`     | Original point or region acquisition                                                       |

Denied items are absent from `items`, including their client-observed content.
If every item is denied, the Adapter returns `NO_AUTHORIZED_CONTEXT` and never
calls the composer.

## Runtime boundary

The hydration port deliberately returns `unknown`. The Adapter verifies schema
version, result count, exact ordered reference identity, result mode, canonical
source, JSON-safe value, timestamps, and failure codes before creating an
attachment. JSON bundle and selection-failure guards are also exported for
fixture and transport boundaries.

## Fixtures and proof

| Fixture                                       | Coverage                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| `fixtures/v1/region-bundle.json`              | Entity, field, editor, region, observed freshness, and selection warning |
| `fixtures/v1/hydration-partial-response.json` | Canonical stale value, permission failure, and editor authorization      |
| `fixtures/v1/selection-failure.json`          | Structured no-target failure                                             |

Four Chrome cases prove successful partial attachment, response-reorder denial,
empty/oversized/mixed-workspace rejection, cancellation, and fixture parsing.
The full package regression is five files and 23 tests. Strict types, lint,
format, declarations/build, and the production bundle guard pass.

## UI-branch handoff

1. Register supported Plane surfaces and call the picker's `select` operation.
2. Render the returned preview or capture state in the composer UI.
3. Pass a successful `SemanticContextBundleV1` to this Adapter.
4. Implement the hydration port with Plane's authenticated API client.
5. Store the verified attachment in the composer draft and submit transport.
6. Show staleness and both warning groups without restoring removed items.

See [ADR 0005](./decisions/0005-composer-integration-interface.md) for the
dependency and filtering decisions.

# M4 Evidence: Live Editor Adapter

## Delivered Interface

```ts
const editorSource = createPlaneEditorContextSource({ fallback: entitySource });
const unregister = editorSource.registerDocument(documentReference, tiptapEditor);
const rangeReference = editorSource.getCurrentRange(documentReference);
```

The Tiptap editor satisfies a structural Interface. Tiptap and Yjs are test-only
dependencies of `@plane/chat-context`; production consumers retain Plane's
existing editor instances and packages.

## Supported capture

| Reference                      | Live output                                                                  |
| ------------------------------ | ---------------------------------------------------------------------------- |
| `editor_block` text node       | Block ID, node type, current text, and approved structural metadata          |
| `editor_block` work-item embed | Work-item ID, identifier, project identifier, workspace slug, and name       |
| `editor_block` image           | Asset ID, status, and alt text                                               |
| `editor_range`                 | Current plain text plus start/end block IDs and relative ProseMirror offsets |

Heading level, code language, and task completion are allowlisted when those node
types are captured. All observations use `source: client_live`.

## Verification

| Gate          | Result                                                                            |
| ------------- | --------------------------------------------------------------------------------- |
| TDD RED       | Real Tiptap/Yjs suite failed because the editor source export was absent          |
| Live block    | Mutation after registration was captured instead of initial content               |
| Range         | Cross-block selection produced identity and fresh text after mutation             |
| Yjs           | A second editor observed and captured an edit through the shared Y.Doc            |
| Privacy       | Signed image URL and arbitrary private attributes were absent                     |
| Lifecycle     | Stale disposer, duplicate ID, missing document, and destroyed editor cases passed |
| Regression    | Four files and 19 browser tests passed in stable Google Chrome                    |
| Package gates | Strict types, lint, format, ESM/declaration build, and bundle guard passed        |

## Pragmatic boundary

| Included                               | Deferred or excluded                                       |
| -------------------------------------- | ---------------------------------------------------------- |
| Current block and text-range semantics | Durable collaborative bookmarks after message submission   |
| Work-item and image embed identity     | Image pixels and visual fallback, owned by M8              |
| Plain selected text                    | Arbitrary HTML, marks, signed URLs, and complete Yjs state |
| Page and work-item documents           | Title editor, comments, and unsupported editor families    |

See [ADR 0003](./decisions/0003-live-editor-identity.md) for identity trade-offs.

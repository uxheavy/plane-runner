# Result: Chat Semantic Context Picker

## Completion state

| Item               | State                                                |
| ------------------ | ---------------------------------------------------- |
| Branch             | `chat-semantic-context-picker-core`                  |
| Non-UI milestones  | M1-M6, M8, and core release verification complete    |
| External milestone | M7 presentation and actual composer transport wiring |

## Delivered contracts

| Boundary        | Delivered contract                                                         |
| --------------- | -------------------------------------------------------------------------- |
| Selection       | `SemanticContextPicker.register`, `select`, and `dispose`                  |
| Identity        | Version 1 entity, field, editor block, and editor range references         |
| Client values   | Fresh allowlisted MobX and Tiptap/Yjs observations                         |
| Server values   | Authenticated batch hydration with canonical or authorization-only results |
| Composer        | Runtime-validated hydration and attachment ports plus JSON fixtures        |
| Visual fallback | In-memory preview/confirm lifecycle and non-semantic PNG attachment        |
| Renderer        | `@plane/chat-context/html2canvas-pro`, pinned to `html2canvas-pro` 2.3.2   |

The Django endpoint is:

```text
POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/
```

| Consumer        | Import                                                  |
| --------------- | ------------------------------------------------------- |
| Semantic only   | `@plane/chat-context`                                   |
| Visual fallback | Root package plus `@plane/chat-context/html2canvas-pro` |

## Verification evidence

Fresh verification completed on `2026-07-29 23:26 +07` after the API dogfood
and QUI-001 repair.

The release verifier also checks the implementation fingerprint in `LESSONS.md`,
so feature implementation and its durable documentation cannot drift silently.

### Primary cross-stack verifier

```bash
pnpm verify:chat-context
```

```text
TypeScript: passed
OxLint: 0 warnings, 0 errors
Oxfmt: passed
Documentation contract: passed; 39 implementation files and 17 required documents
Test Files  8 passed (8)
Tests       40 passed (40)
Declarations/build: passed
Core bundle: 20,803 gzip bytes <= 30,000; forbidden markers: none
Renderer bundle: 66,955 gzip bytes <= 100,000; html2canvas marker present
Django/PostgreSQL: 57 passed in 15.78s
Docker test containers and network: removed
```

| Browser proof       | Coverage                                                                        |
| ------------------- | ------------------------------------------------------------------------------- |
| Primary integration | Entity, field, live editor, detached, region, partial hydration, dummy composer |
| Renderer            | Real decoded 64×48 PNG from modern CSS                                          |

### Repository gate

```bash
pnpm check
```

```text
Tasks: 63 successful, 63 total
Cached: 60 cached, 63 total
```

- Flaky checks: none; the three-pass rule was not triggered.

### API dogfood

- Three persistent personas completed two routed API waves.
- Wave 1: Maya 3 passed, Ravi 7 passed, Quinn 25 passed and 6 exposed QUI-001.
- QUI-001 fixed malformed top-level payloads returning 500 instead of 400.
- Wave 2: all 41 persona cases passed with no permission or privacy regression.
- The persona suites are now part of `pnpm verify:chat-context`, not disposable
  test artifacts.

## Privacy and permission evidence

| Requirement             | Proof                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| No whole client records | Six entity projectors and 11 field projectors are explicit allowlists.                           |
| No editor secrets       | Tests exclude signed URLs, arbitrary attributes, marks, HTML, and Yjs state.                     |
| Server reauthorization  | Active workspace/project roles are checked for every submitted reference.                        |
| Private and guest scope | Private pages, guest feature access, revoked links, and cross-project IDs are tested.            |
| Deleted data            | Soft-deleted objects and relationship rows resolve as unavailable.                               |
| Denied observations     | Composer tests prove denied client values are removed before attachment.                         |
| Denied pixels           | Password, authentication, iframe, marked, and open-shadow content stop capture before rendering. |
| Late sensitive nodes    | The renderer ignore predicate excludes newly introduced sensitive content.                       |
| Explicit sharing        | A visual preview must be confirmed once; discard, reuse, or disposal retires it.                 |

| Completion audit      | Result                                                                 |
| --------------------- | ---------------------------------------------------------------------- |
| P0/P1 findings        | None unresolved                                                        |
| Missing direct proofs | Five public failure branches found and added before the final verifier |
| API dogfood findings  | QUI-001 closed; no blocker or high-severity friction remains           |

## Known limitations

- Presentation UI and actual composer wiring belong to the user-owned UI branch.
- Only registered Plane surfaces are semantic. Current coverage is six entities,
  11 work-item fields, and page/work-item Tiptap blocks and ranges.
- Closed shadow-root content cannot be inspected; its host must carry
  `data-plane-context-sensitive` when capture is unsafe.
- Cross-origin or tainted images are deliberately absent from DOM snapshots.
- Visual previews are memory-only and disappear with their owning page session.
- Editor ranges are fresh block-relative selections, not durable collaborative
  bookmarks after submission.
- The missing composer prevents a true UI-to-model end-to-end test in this branch.

## UI branch handoff

1. Add activation, hover/crosshair, drag-region, chip, and preview presentation.
2. Register entity-aware Plane surfaces using the root package contract.
3. Call `select` for semantic context; call `createVisualContextCapture` only for
   a requested visual fallback.
4. Import `createHtml2CanvasProVisualRenderer` from the renderer subpath; do not
   add another production screenshot engine.
5. Implement the hydration port with Plane's authenticated API client.
6. Implement the composer consumer port and transport the verified attachment.
7. Show selection and hydration warnings without restoring denied items.
8. Mark non-standard secret hosts with `data-plane-context-sensitive` and picker
   chrome with `data-plane-context-ignore`.
9. Add the final UI-to-composer test for activation, review, removal, and send.

- Compatibility fixtures: `packages/chat-context/fixtures/v1`.
- External actions performed: none; no merge, push, deployment, or UI-branch modification.

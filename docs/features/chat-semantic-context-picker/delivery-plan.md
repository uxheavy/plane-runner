# Delivery Plan: Chat Semantic Context Picker

## Milestone status

| ID  | Milestone                         | Scope                                                               | Owner          | Status   | Completion evidence                                     |
| --- | --------------------------------- | ------------------------------------------------------------------- | -------------- | -------- | ------------------------------------------------------- |
| M0  | Product and architecture baseline | Scope, boundaries, ADR, branch, tracking                            | Codex          | Complete | Feature dossier merged on feature branch                |
| M1  | Selection-foundation spike        | Pin and validate React Grab primitives in Plane                     | Codex          | Complete | Real Chrome tests and production bundle verifier pass   |
| M2  | Core contracts and registry       | Types, registry, point/region result model                          | Codex          | Complete | Ten browser contract tests and package gates pass       |
| M3  | Plane entity adapters             | Work items, projects, cycles, modules, pages, views, fields         | Codex          | Complete | Live getter Adapter and 15-test browser regression pass |
| M4  | Editor adapter                    | Page blocks, issue descriptions, ranges, embeds, client-live values | Codex          | Complete | Real Tiptap/Yjs tests and privacy allowlist pass        |
| M5  | Server hydration                  | Permission-safe canonical resolution and stale/deleted handling     | Codex          | Complete | 11 hydration and five page-scope Django tests pass      |
| M6  | Composer integration kit          | Versioned adapter, fixtures, contract tests, integration guide      | Codex          | Complete | Dummy consumer and 23-test browser regression pass      |
| M7  | UI integration                    | Activation, overlay, context chips, preview, composer wiring        | User UI branch | External | End-to-end workflow passes                              |
| M8  | Region and visual fallback        | Drag regions, deduplication, snapshot evaluation                    | Shared         | Next     | Region and privacy acceptance tests                     |
| M9  | Release verification              | Full single-user workflow and regression pass                       | Shared         | Pending  | Acceptance checklist complete                           |

The active durable goal covers M1-M6, the non-UI portion of M8, and core release
verification. M7 and composer end-to-end wiring remain external to this branch.

## M1 checklist

- [x] Select and pin React Grab 0.1.50.
- [x] Review package exports, bundle impact, and transitive dependencies.
- [x] Verify production point hit-testing without source instrumentation.
- [x] Verify Plane and React Grab ignored subtrees.
- [x] Verify the stateless adapter retains no detached target or global pointer state.
- [x] Verify portals, open shadow roots, and nested interactive elements.
- [x] Move Escape, confirmation, navigation ownership, and disposal to M2 because
      the accepted adapter installs no listeners and does not freeze the page.
- [x] Record findings and narrow ADR 0001 to stateless acquisition primitives.

## M2 accepted boundary

- Public core Module exposes `register`, `select`, and `dispose`.
- Preview and capture share one discriminated request/result Interface.
- Plane call sites register typed identity only.
- React Grab, registry, state machine, resolvers, and serialization stay private.
- A fake acquisition Adapter and production React Grab Adapter share contract tests.
- Server hydration and composer transport remain separate Adapters.

## M2 checklist

- [x] Export versioned reference, request, context, and failure contracts.
- [x] Register copied semantic identities without storing values in the DOM.
- [x] Preview nested point candidates without resolving values.
- [x] Capture the fresh top point target without silently falling back.
- [x] Capture deterministic, bounded, deduplicated regions with partial warnings.
- [x] Abort superseded, externally cancelled, and disposed operations.
- [x] Verify lifecycle behavior in stable Google Chrome.
- [x] Pass strict types, lint, format, build, and production bundle gates.

## M3 checklist

- [x] Map the current `CoreRootStore` entity and related-value owners.
- [x] Bind store paths through live getters without importing MobX.
- [x] Resolve all six accepted entity types into curated JSON snapshots.
- [x] Resolve every allowlisted work-item field at capture time.
- [x] Exclude whole records, member email, view queries, and editor bodies.
- [x] Return typed missing, mismatched, and editor-handoff failures.
- [x] Pass the full M1-M3 browser regression suite and package gates.

## M4 checklist

- [x] Reuse Plane's existing `UniqueID` block identity.
- [x] Add block-relative editor range references without changing prior variants.
- [x] Resolve blocks and ranges from live Tiptap state.
- [x] Observe remote updates through a shared Yjs document.
- [x] Project work-item and image embeds through explicit privacy allowlists.
- [x] Fail closed for missing, duplicate, stale, and destroyed editor state.
- [x] Keep Tiptap and Yjs out of production runtime dependencies.
- [x] Pass the full 19-test browser regression suite and package gates.

## M5 checklist

- [x] Add a bounded, versioned, workspace-scoped batch endpoint.
- [x] Validate reference shape at the HTTP and service boundaries.
- [x] Recheck active workspace, project, private object, and guest access.
- [x] Resolve all six entities and 11 work-item fields through allowlists.
- [x] Preserve canonical values, versions, resolution time, and staleness.
- [x] Return authorization-only success for live editor references.
- [x] Exclude soft-deleted objects and relationship rows.
- [x] Pass the focused hydration and existing page-scope regressions.

## M6 checklist

- [x] Export versioned hydration request, response, and attachment types.
- [x] Provide hydration and composer consumer ports without UI dependencies.
- [x] Parse unknown hydration responses and verify ordered reference identity.
- [x] Remove denied observations before the composer consumer runs.
- [x] Preserve client observations, canonical values, staleness, and warnings.
- [x] Reject empty, oversized, and mixed-workspace bundles structurally.
- [x] Ship JSON fixtures for entity, field, editor, region, hydration, and failure.
- [x] Pass the dummy consumer contract and full package gates.

## Cross-branch contract

| Core branch provides                   | UI branch provides                      |
| -------------------------------------- | --------------------------------------- |
| Selection engine lifecycle             | Composer activation control             |
| Target registration and resolution     | Hover and selection overlays            |
| Context and failure result types       | Context chips and previews              |
| Editor/entity/server adapters          | User-facing errors and removal controls |
| Composer adapter contract and fixtures | Actual composer transport wiring        |
| Core and permission tests              | End-to-end interaction tests            |

## Risks and responses

| Risk                                                     | Response                                                                 | Status         |
| -------------------------------------------------------- | ------------------------------------------------------------------------ | -------------- |
| React Grab primitives assume development source metadata | Use hit-testing primitives only and prove production behavior in M1.     | Mitigated      |
| Generic Plane UI loses owning entity/field identity      | Register context at entity-aware call sites or shared semantic wrappers. | Open           |
| Client values differ from server state                   | Preserve observed and canonical values separately.                       | Designed       |
| Private or cross-project data leaks                      | Reauthorize on the server and allowlist fields.                          | Designed       |
| Composer contract differs when its code appears          | Keep a versioned adapter and contract fixtures.                          | Open           |
| Visual capture leaks unrelated content                   | Require preview, denied surfaces, and explicit visual-only labeling.     | Deferred to M8 |

## Definition of done

- Supported targets satisfy the product acceptance criteria.
- Core, editor, and server tests pass.
- The composer adapter contract is documented and demonstrated.
- The UI branch completes the end-to-end workflow.
- Permission and privacy cases pass.
- This plan and all relevant ADRs reflect the shipped result.

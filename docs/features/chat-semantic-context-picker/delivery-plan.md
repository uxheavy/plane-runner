# Delivery Plan: Chat Semantic Context Picker

## Milestone status

| ID | Milestone | Scope | Owner | Status | Completion evidence |
| --- | --- | --- | --- | --- | --- |
| M0 | Product and architecture baseline | Scope, boundaries, ADR, branch, tracking | Codex | Complete | Feature dossier merged on feature branch |
| M1 | Selection-foundation spike | Pin and validate React Grab primitives in Plane | Codex | Next | Tests or harness prove hit-test, ignore, cleanup, portals |
| M2 | Core contracts and registry | Types, registry, point/region result model | Codex | Designed | ADR 0002 accepted; implementation and tests pending |
| M3 | Plane entity adapters | Work items, projects, cycles, modules, pages, views, fields | Codex | Pending | Adapter tests with current store values |
| M4 | Editor adapter | Page blocks, issue descriptions, ranges, embeds, client-live values | Codex | Pending | Tiptap/Yjs adapter tests |
| M5 | Server hydration | Permission-safe canonical resolution and stale/deleted handling | Codex | Pending | Django tests for roles, projects, private pages, failures |
| M6 | Composer integration kit | Versioned adapter, fixtures, contract tests, integration guide | Codex | Pending | Dummy consumer passes contract suite |
| M7 | UI integration | Activation, overlay, context chips, preview, composer wiring | User UI branch | External | End-to-end workflow passes |
| M8 | Region and visual fallback | Drag regions, deduplication, snapshot evaluation | Shared | Pending | Region and privacy acceptance tests |
| M9 | Release verification | Full single-user workflow and regression pass | Shared | Pending | Acceptance checklist complete |

## M1 checklist

- [ ] Select and pin a React Grab version.
- [ ] Review package exports, bundle impact, and transitive dependencies.
- [ ] Verify point hit-testing inside the Plane app container.
- [ ] Verify ignored picker/composer subtrees.
- [ ] Verify cleanup after Escape, selection, navigation, and unmount.
- [ ] Verify portals and nested interactive elements.
- [ ] Record findings and update ADR 0001 if the dependency boundary changes.

## M2 accepted boundary

- Public core Module exposes `register`, `select`, and `dispose`.
- Preview and capture share one discriminated request/result Interface.
- Plane call sites register typed identity only.
- React Grab, registry, state machine, resolvers, and serialization stay private.
- A fake acquisition Adapter and production React Grab Adapter share contract tests.
- Server hydration and composer transport remain separate Adapters.

## Cross-branch contract

| Core branch provides | UI branch provides |
| --- | --- |
| Selection engine lifecycle | Composer activation control |
| Target registration and resolution | Hover and selection overlays |
| Context and failure result types | Context chips and previews |
| Editor/entity/server adapters | User-facing errors and removal controls |
| Composer adapter contract and fixtures | Actual composer transport wiring |
| Core and permission tests | End-to-end interaction tests |

## Risks and responses

| Risk | Response | Status |
| --- | --- | --- |
| React Grab primitives assume development source metadata | Use hit-testing primitives only and prove production behavior in M1. | Open |
| Generic Plane UI loses owning entity/field identity | Register context at entity-aware call sites or shared semantic wrappers. | Open |
| Client values differ from server state | Preserve observed and canonical values separately. | Designed |
| Private or cross-project data leaks | Reauthorize on the server and allowlist fields. | Designed |
| Composer contract differs when its code appears | Keep a versioned adapter and contract fixtures. | Open |
| Visual capture leaks unrelated content | Require preview, denied surfaces, and explicit visual-only labeling. | Deferred to M8 |

## Definition of done

- Supported targets satisfy the product acceptance criteria.
- Core, editor, and server tests pass.
- The composer adapter contract is documented and demonstrated.
- The UI branch completes the end-to-end workflow.
- Permission and privacy cases pass.
- This plan and all relevant ADRs reflect the shipped result.

# Worklog: Chat Semantic Context Picker

## Current state

| Item                    | Value                                                             |
| ----------------------- | ----------------------------------------------------------------- |
| Active phase            | M8: non-UI region and visual fallback                             |
| Last completed evidence | M6 versioned ports, runtime guards, fixtures, and dummy consumer  |
| Next action             | Define privacy-safe visual fallback ownership and denial contract |
| Blocking condition      | None                                                              |

## Evidence log

| Date       | Milestone | Attempt or decision                                                                    | Evidence                                                                   | Next action                      |
| ---------- | --------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------- |
| 2026-07-29 | M0        | Defined scope, coverage, stack, delivery plan, and React Grab boundary                 | Commit `cee89fd332`                                                        | Design public core Interface     |
| 2026-07-29 | M2 design | Compared four Interfaces and accepted the three-operation deep Module                  | Commit `14131165c6`                                                        | Run M1 before implementation     |
| 2026-07-29 | M1 RED    | Real Chrome runner collected the suite and failed because the Plane adapter was absent | `pnpm --filter @plane/chat-context test`                                   | Implement the minimal adapter    |
| 2026-07-29 | M1 GREEN  | Nested, ignored, portal, shadow, navigation, and unmount behaviors passed in Chrome    | `packages/chat-context/tests/react-grab-selection-adapter.browser.test.ts` | Verify production bundle         |
| 2026-07-29 | M1 bundle | Consumer bundle measured 13,217 gzip bytes with no forbidden inspector or CLI markers  | `pnpm --filter @plane/chat-context verify:bundle`                          | Start M2 contracts and registry  |
| 2026-07-29 | M2 RED    | Public contract suite failed because the core picker export was absent                 | `packages/chat-context/tests/semantic-context-picker.browser.test.ts`      | Implement the accepted Module    |
| 2026-07-29 | M2 fix    | First pass captured a point field and its parent instead of the top target only        | Browser assertion diff                                                     | Narrow point capture             |
| 2026-07-29 | M2 GREEN  | Ten browser tests plus strict types, lint, format, build, and bundle guard passed      | `m2-core-contracts.md`                                                     | Start M3 store mapping           |
| 2026-07-29 | M3 map    | Mapped entities and related fields to current `CoreRootStore` owners                   | `packages/chat-context/tests/M3_EVIDENCE.md`                               | Write resolver tests             |
| 2026-07-29 | M3 RED    | Resolver and CoreRootStore binding tests failed on their absent exports                | `plane-entity-context-source.browser.test.ts`                              | Implement live getter Adapter    |
| 2026-07-29 | M3 GREEN  | Five M3 tests and the 15-test browser regression suite passed                          | `m3-plane-entity-adapter.md`                                               | Start M4 editor source mapping   |
| 2026-07-29 | M4 map    | Chose existing Plane block IDs and block-relative ProseMirror offsets                  | `decisions/0003-live-editor-identity.md`                                   | Write live editor tests          |
| 2026-07-29 | M4 RED    | Real Tiptap/Yjs suite failed because the editor source export was absent               | `packages/chat-context/tests/M4_EVIDENCE.md`                               | Implement editor Adapter         |
| 2026-07-29 | M4 GREEN  | Four editor tests and the 19-test browser regression suite passed                      | `m4-live-editor-adapter.md`                                                | Start M5 permission mapping      |
| 2026-07-29 | M5 map    | Mapped active roles, private pages/views, guest rules, and scoped entity queries       | `decisions/0004-server-hydration-boundary.md`                              | Write Django contract tests      |
| 2026-07-29 | M5 RED    | Eight endpoint cases failed while the route and hydration service were absent          | `apps/api/plane/tests/contract/api/M5_EVIDENCE.md`                         | Implement the hydration Module   |
| 2026-07-29 | M5 fix    | RED exposed duplicate test usernames and an unauthenticated owner client               | Focused pytest failure output                                              | Correct fixtures, keep criteria  |
| 2026-07-29 | M5 GREEN  | 11 hydration and five existing page-scope cases passed with Ruff clean                 | `m5-server-hydration.md`                                                   | Start M6 integration kit         |
| 2026-07-29 | M6 RED    | Composer contract tests failed while the public Adapter export was absent              | `packages/chat-context/tests/M6_EVIDENCE.md`                               | Implement integration Adapter    |
| 2026-07-29 | M6 fix    | Type and lint gates rejected a broad failure return and mutating sort                  | Strict TypeScript and OxLint output                                        | Narrow types and remove mutation |
| 2026-07-29 | M6 GREEN  | Four integration cases and the 23-test browser regression passed                       | `m6-composer-integration.md`                                               | Start non-UI M8 boundary         |

## Recording rules

- Add one row for each meaningful attempt, verifier result, correction, or decision.
- Link commits, commands, paths, and test output instead of writing progress claims.
- Update `Current state` whenever the active milestone or next action changes.
- Route durable architecture decisions to an ADR; keep transient investigation here.

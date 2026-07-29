# Worklog: Chat Semantic Context Picker

## Current state

| Item                    | Value                                                                |
| ----------------------- | -------------------------------------------------------------------- |
| Active phase            | M5: server hydration                                                 |
| Last completed evidence | M4 live blocks, ranges, Yjs freshness, and embed privacy             |
| Next action             | Map Django entity permission paths and define the hydration contract |
| Blocking condition      | None                                                                 |

## Evidence log

| Date       | Milestone | Attempt or decision                                                                    | Evidence                                                                   | Next action                     |
| ---------- | --------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------- |
| 2026-07-29 | M0        | Defined scope, coverage, stack, delivery plan, and React Grab boundary                 | Commit `cee89fd332`                                                        | Design public core Interface    |
| 2026-07-29 | M2 design | Compared four Interfaces and accepted the three-operation deep Module                  | Commit `14131165c6`                                                        | Run M1 before implementation    |
| 2026-07-29 | M1 RED    | Real Chrome runner collected the suite and failed because the Plane adapter was absent | `pnpm --filter @plane/chat-context test`                                   | Implement the minimal adapter   |
| 2026-07-29 | M1 GREEN  | Nested, ignored, portal, shadow, navigation, and unmount behaviors passed in Chrome    | `packages/chat-context/tests/react-grab-selection-adapter.browser.test.ts` | Verify production bundle        |
| 2026-07-29 | M1 bundle | Consumer bundle measured 13,217 gzip bytes with no forbidden inspector or CLI markers  | `pnpm --filter @plane/chat-context verify:bundle`                          | Start M2 contracts and registry |
| 2026-07-29 | M2 RED    | Public contract suite failed because the core picker export was absent                 | `packages/chat-context/tests/semantic-context-picker.browser.test.ts`      | Implement the accepted Module   |
| 2026-07-29 | M2 fix    | First pass captured a point field and its parent instead of the top target only        | Browser assertion diff                                                     | Narrow point capture            |
| 2026-07-29 | M2 GREEN  | Ten browser tests plus strict types, lint, format, build, and bundle guard passed      | `m2-core-contracts.md`                                                     | Start M3 store mapping          |
| 2026-07-29 | M3 map    | Mapped entities and related fields to current `CoreRootStore` owners                   | `packages/chat-context/tests/M3_EVIDENCE.md`                               | Write resolver tests            |
| 2026-07-29 | M3 RED    | Resolver and CoreRootStore binding tests failed on their absent exports                | `plane-entity-context-source.browser.test.ts`                              | Implement live getter Adapter   |
| 2026-07-29 | M3 GREEN  | Five M3 tests and the 15-test browser regression suite passed                          | `m3-plane-entity-adapter.md`                                               | Start M4 editor source mapping  |
| 2026-07-29 | M4 map    | Chose existing Plane block IDs and block-relative ProseMirror offsets                  | `decisions/0003-live-editor-identity.md`                                   | Write live editor tests         |
| 2026-07-29 | M4 RED    | Real Tiptap/Yjs suite failed because the editor source export was absent               | `packages/chat-context/tests/M4_EVIDENCE.md`                               | Implement editor Adapter        |
| 2026-07-29 | M4 GREEN  | Four editor tests and the 19-test browser regression suite passed                      | `m4-live-editor-adapter.md`                                                | Start M5 permission mapping     |

## Recording rules

- Add one row for each meaningful attempt, verifier result, correction, or decision.
- Link commits, commands, paths, and test output instead of writing progress claims.
- Update `Current state` whenever the active milestone or next action changes.
- Route durable architecture decisions to an ADR; keep transient investigation here.

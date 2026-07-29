# Worklog: Chat Semantic Context Picker

## Current state

| Item                    | Value                                                       |
| ----------------------- | ----------------------------------------------------------- |
| Active phase            | Non-UI core and API dogfood complete                        |
| Last completed evidence | 40 browser tests, 57 Django tests, and 63 repo tasks passed |
| Next action             | Resume the user-owned M7 UI handoff                         |
| Blocking condition      | None                                                        |

## Evidence log

| Date       | Milestone     | Attempt or decision                                                                                          | Evidence                                                                      | Next action                              |
| ---------- | ------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- | ---------------------------------------- |
| 2026-07-29 | M0            | Defined scope, coverage, stack, delivery plan, and React Grab boundary                                       | Commit `cee89fd332`                                                           | Design public core Interface             |
| 2026-07-29 | M2 design     | Compared four Interfaces and accepted the three-operation deep Module                                        | Commit `14131165c6`                                                           | Run M1 before implementation             |
| 2026-07-29 | M1 RED        | Real Chrome runner collected the suite and failed because the Plane adapter was absent                       | `pnpm --filter @plane/chat-context test`                                      | Implement the minimal adapter            |
| 2026-07-29 | M1 GREEN      | Nested, ignored, portal, shadow, navigation, and unmount behaviors passed in Chrome                          | `packages/chat-context/tests/react-grab-selection-adapter.browser.test.ts`    | Verify production bundle                 |
| 2026-07-29 | M1 bundle     | Consumer bundle measured 13,217 gzip bytes with no forbidden inspector or CLI markers                        | `pnpm --filter @plane/chat-context verify:bundle`                             | Start M2 contracts and registry          |
| 2026-07-29 | M2 RED        | Public contract suite failed because the core picker export was absent                                       | `packages/chat-context/tests/semantic-context-picker.browser.test.ts`         | Implement the accepted Module            |
| 2026-07-29 | M2 fix        | First pass captured a point field and its parent instead of the top target only                              | Browser assertion diff                                                        | Narrow point capture                     |
| 2026-07-29 | M2 GREEN      | Ten browser tests plus strict types, lint, format, build, and bundle guard passed                            | `m2-core-contracts.md`                                                        | Start M3 store mapping                   |
| 2026-07-29 | M3 map        | Mapped entities and related fields to current `CoreRootStore` owners                                         | `packages/chat-context/tests/M3_EVIDENCE.md`                                  | Write resolver tests                     |
| 2026-07-29 | M3 RED        | Resolver and CoreRootStore binding tests failed on their absent exports                                      | `plane-entity-context-source.browser.test.ts`                                 | Implement live getter Adapter            |
| 2026-07-29 | M3 GREEN      | Five M3 tests and the 15-test browser regression suite passed                                                | `m3-plane-entity-adapter.md`                                                  | Start M4 editor source mapping           |
| 2026-07-29 | M4 map        | Chose existing Plane block IDs and block-relative ProseMirror offsets                                        | `decisions/0003-live-editor-identity.md`                                      | Write live editor tests                  |
| 2026-07-29 | M4 RED        | Real Tiptap/Yjs suite failed because the editor source export was absent                                     | `packages/chat-context/tests/M4_EVIDENCE.md`                                  | Implement editor Adapter                 |
| 2026-07-29 | M4 GREEN      | Four editor tests and the 19-test browser regression suite passed                                            | `m4-live-editor-adapter.md`                                                   | Start M5 permission mapping              |
| 2026-07-29 | M5 map        | Mapped active roles, private pages/views, guest rules, and scoped entity queries                             | `decisions/0004-server-hydration-boundary.md`                                 | Write Django contract tests              |
| 2026-07-29 | M5 RED        | Eight endpoint cases failed while the route and hydration service were absent                                | `apps/api/plane/tests/contract/api/M5_EVIDENCE.md`                            | Implement the hydration Module           |
| 2026-07-29 | M5 fix        | RED exposed duplicate test usernames and an unauthenticated owner client                                     | Focused pytest failure output                                                 | Correct fixtures, keep criteria          |
| 2026-07-29 | M5 GREEN      | 11 hydration and five existing page-scope cases passed with Ruff clean                                       | `m5-server-hydration.md`                                                      | Start M6 integration kit                 |
| 2026-07-29 | M6 RED        | Composer contract tests failed while the public Adapter export was absent                                    | `packages/chat-context/tests/M6_EVIDENCE.md`                                  | Implement integration Adapter            |
| 2026-07-29 | M6 fix        | Type and lint gates rejected a broad failure return and mutating sort                                        | Strict TypeScript and OxLint output                                           | Narrow types and remove mutation         |
| 2026-07-29 | M6 GREEN      | Four integration cases and the 23-test browser regression passed                                             | `m6-composer-integration.md`                                                  | Start non-UI M8 boundary                 |
| 2026-07-29 | M8 source     | Rejected stale html2canvas coupling; selected a renderer port and maintained fork model                      | `decisions/0006-visual-fallback-boundary.md`                                  | Implement privacy gate                   |
| 2026-07-29 | M8 GREEN      | Ten visual cases and the full 34-test browser regression passed                                              | `m8-visual-fallback.md`                                                       | Start release verification               |
| 2026-07-29 | M8 audit      | User correction exposed that the first renderer test injected a simulation                                   | `visual-context.browser.test.ts` before correction                            | Inspect Codex and choose one stack       |
| 2026-07-29 | M8 source     | Codex keeps semantic element data separate from pixels; native capture is proprietary                        | Public app-server and installed browser contracts                             | Implement a web renderer                 |
| 2026-07-29 | M8 fix        | Pinned `html2canvas-pro` 2.3.2 and removed the simulated production Adapter                                  | `@plane/chat-context/html2canvas-pro`                                         | Prove actual pixels                      |
| 2026-07-29 | M8 GREEN      | Exact modern-CSS crop, ignored overlay, 35 tests, and both bundle gates passed                               | `m8-visual-fallback.md`                                                       | Run clean release verifier               |
| 2026-07-29 | M9 audit      | Completion audit found five public failure branches without direct contract proof                            | `GOAL.md` result-variant requirement                                          | Add missing verifier cases               |
| 2026-07-29 | M9 GREEN      | All public result variants, 40 Chrome tests, and 16 Django cases passed                                      | `pnpm verify:chat-context`                                                    | Run repository gate                      |
| 2026-07-29 | M9 GREEN      | Repository-wide types, lint, format, and builds completed as 63 successful tasks                             | `pnpm check`                                                                  | Write final handoff                      |
| 2026-07-29 | M9 recheck    | Fresh full rerun passed; registry signature preflight required network-enabled retries                       | 40 browser, 16 Django, and 63 repository tasks passed                         | Preserve UI handoff boundary             |
| 2026-07-29 | Lessons RED   | Missing and post-format fingerprints failed the new gate as designed                                         | `verify-feature-docs.mjs` mismatch output                                     | Record reviewed final fingerprint        |
| 2026-07-29 | Lessons fix   | Pre-commit rejected serial file reads in the new documentation verifier                                      | `no-await-in-loop` lint output                                                | Parallelize reads and reverify           |
| 2026-07-29 | Lessons GREEN | Parallel verifier, full ledger, 40 browser, 16 Django, and 63 repo tasks passed                              | `LESSONS.md`, `pnpm verify:chat-context`, and `pnpm check`                    | Commit the structural safeguards         |
| 2026-07-29 | Simplify      | Replaced tuple configuration, top-level hashing, and exception-driven probes                                 | Named configuration; full feature and 63-task repository gates passed         | Commit the behavior-neutral cleanup      |
| 2026-07-29 | API Wave 1    | Three persistent personas ran 41 routed API cases; ordinary top-level errors exposed one HTTP 500 root cause | Maya 3 passed; Ravi 7 passed; Quinn 25 passed and 6 failed                    | Fix QUI-001 at the serializer boundary   |
| 2026-07-29 | API fix       | Normalized top-level strict-key errors and stopped reflecting unknown client key names                       | Quinn 31 passed; existing hydration contracts 11 passed                       | Complete the inter-wave delay and retest |
| 2026-07-29 | API Wave 2    | The same personas reran all normal, restricted, and skeptical integration lanes                              | 41 of 41 routed persona cases passed                                          | Run final combined release verification  |
| 2026-07-29 | API GREEN     | Added persona regressions to the structural verifier and ran the exact formatted tree                        | 40 browser tests, 57 Django tests, Ruff clean, and 63 repository tasks passed | Resume the M7 UI handoff                 |
| 2026-07-30 | Review GREEN  | Fixed guest hydration, reverse drags, and URL attribution                                                    | 42 browser; 11 API; focused gates passed                                      | Resume the M7 UI handoff                 |

## Recording rules

- Add one row for each meaningful attempt, verifier result, correction, or decision.
- Link commits, commands, paths, and test output instead of writing progress claims.
- Update `Current state` whenever the active milestone or next action changes.
- Route durable architecture decisions to an ADR; keep transient investigation here.

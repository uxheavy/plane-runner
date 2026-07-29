# Worklog: Chat Semantic Context Picker

## Current state

| Item                    | Value                                                               |
| ----------------------- | ------------------------------------------------------------------- |
| Active phase            | M3: Plane entity adapters                                           |
| Last completed evidence | M2 real-browser contract, lifecycle, build, and bundle verification |
| Next action             | Map supported Plane stores and write resolver evidence contracts    |
| Blocking condition      | None                                                                |

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

## Recording rules

- Add one row for each meaningful attempt, verifier result, correction, or decision.
- Link commits, commands, paths, and test output instead of writing progress claims.
- Update `Current state` whenever the active milestone or next action changes.
- Route durable architecture decisions to an ADR; keep transient investigation here.

# Worklog: Chat Semantic Context Picker

## Current state

| Item                    | Value                                                                        |
| ----------------------- | ---------------------------------------------------------------------------- |
| Active phase            | M2: core contracts and registry                                              |
| Last completed evidence | M1 real-browser and production-bundle verification                           |
| Next action             | Write the M2 contract tests against production and fake acquisition adapters |
| Blocking condition      | None                                                                         |

## Evidence log

| Date       | Milestone | Attempt or decision                                                                    | Evidence                                                                   | Next action                     |
| ---------- | --------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------- |
| 2026-07-29 | M0        | Defined scope, coverage, stack, delivery plan, and React Grab boundary                 | Commit `cee89fd332`                                                        | Design public core Interface    |
| 2026-07-29 | M2 design | Compared four Interfaces and accepted the three-operation deep Module                  | Commit `14131165c6`                                                        | Run M1 before implementation    |
| 2026-07-29 | M1 RED    | Real Chrome runner collected the suite and failed because the Plane adapter was absent | `pnpm --filter @plane/chat-context test`                                   | Implement the minimal adapter   |
| 2026-07-29 | M1 GREEN  | Nested, ignored, portal, shadow, navigation, and unmount behaviors passed in Chrome    | `packages/chat-context/tests/react-grab-selection-adapter.browser.test.ts` | Verify production bundle        |
| 2026-07-29 | M1 bundle | Consumer bundle measured 13,217 gzip bytes with no forbidden inspector or CLI markers  | `pnpm --filter @plane/chat-context verify:bundle`                          | Start M2 contracts and registry |

## Recording rules

- Add one row for each meaningful attempt, verifier result, correction, or decision.
- Link commits, commands, paths, and test output instead of writing progress claims.
- Update `Current state` whenever the active milestone or next action changes.
- Route durable architecture decisions to an ADR; keep transient investigation here.

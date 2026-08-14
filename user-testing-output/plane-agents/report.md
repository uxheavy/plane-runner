# User Testing Report: Plane Agents

| Field          | Value                                                            |
| -------------- | ---------------------------------------------------------------- |
| Date started   | 2026-08-13                                                       |
| Target         | Isolated local Plane stack from `codex/agent-functional-dogfood` |
| Scope          | Every supported non-UI Plane Agent capability and boundary       |
| Personas       | 3: Maya, Elena, Omar                                             |
| Persona source | New, derived from Plane Agent product roles and ADR scope        |
| Provider/model | ChatGPT subscription, GPT-5.6 Luna, no fallback                  |

## Current summary

| Metric            | Count |
| ----------------- | ----: |
| Routes discovered |    27 |
| Clean             |     0 |
| Dirty             |     1 |
| Blocked           |     0 |
| Untested          |    27 |
| Blocker issues    |     2 |
| Friction issues   |     0 |
| Annoyances        |     0 |

## Completion evidence

Wave 0AO ran one exact, non-UI primary from Plane
`b83a94f61a141a8a1eb00d616d4288899236739e` with Hermes
`d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20`. Config-only preflight passed with
the canonical provider-relay projection present in both authority and config.
The primary reached the real GPT-5.6 Luna ChatGPT subscription route with
fallback disabled and recorded 13 completed upstream `2xx` provider attempts,
one submit, one applied publication, and one visible `outcome_submission`.
However, the evaluator was `unavailable` once rather than `NOT_AUTHORIZED`, and
RuntimeExit was `failed` with `runtime_error` / `host_operation_failure` at
final sequence 23. The ordered `s00Gate` failed at
`runtime_exit_completed`; the conditional provider-disabled replay was not
eligible and did not run. S00 remains dirty and UT-018/UT-019 remain open. No
source fix, rerun, or Hermes change was made.

The owner-only bounded failure receipt was `0600`, `6015` bytes, SHA-256
`0805a26d1ce73bc2d55475709879a82702c240a7fcb81890e4543356a2e12b36`, and
semantic digest
`357392642e3e99aba24c6b60e981da201d7c868a22c2112c91ebbffa0bd34ed9`. Its
wrapper and JSON body passed standalone validation before deletion.

## Cross-persona heatmap

| Issue | Personas affected | Severity | Status |
| ----- | ----------------- | -------- | ------ |

## Final risks and decision

Decision: `FAIL`. The journey is not clean enough to close S00 or unlock W/M/O.
The remaining blocker is the runtime terminal failure: `host_operation_failure`
prevented `RuntimeExit.completed`, and the required evaluator denial was not
observed. The provider-relay handoff itself passed preflight and standalone
receipt validation. The failed primary means replay-equivalence deltas are not
applicable; UT-018 and UT-019 remain open.

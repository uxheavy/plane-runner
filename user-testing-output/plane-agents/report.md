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

Wave 0AP ran one exact, non-UI primary from Plane
`891a1aed20344ba5a445c515bc23acd76693c93d` with Hermes
`1d9818e7df007d2ea4f1e3df373aaa812e022e6a`. Config-only preflight passed with
the canonical provider-relay projection present in both authority and config.
The primary reached the real GPT-5.6 Luna ChatGPT subscription route with
fallback disabled and recorded ten completed upstream `2xx` provider attempts,
one exact `NOT_AUTHORIZED` evaluator denial, one submit, one applied
publication, and one visible `outcome_submission`. The ordered `s00Gate`
passed through terminal binding but failed at `runtime_exit_completed`:
RuntimeExit was `failed` with non-retryable `budget_exhausted` at final sequence 22. The conditional provider-disabled replay was not eligible and did not run.
S00 remains dirty and UT-018/UT-019 remain open. No source fix, rerun, or Hermes
change was made.

The runner receipt was `0600`, `5683` bytes, SHA-256
`a5eb2c596c91a98702f3e8697cfc24f77fdc08b865bca4747058d0ccfc1f6855`. Its
standalone JSON body was `0600`, `5563` bytes, SHA-256
`681de547b72b9e773b3a0d0876b2c06ca1f5b93e50e232420476120cbadcbbf4`, passed
standalone validation, and carried semantic digest
`fb3e69b5e206ea7236a6cd719944a29b8f4ab22d3ab69b7d7a6f9846689cd6b4`, which
recomputed exactly. Both were deleted after validation and hashing.

## Cross-persona heatmap

| Issue | Personas affected | Severity | Status |
| ----- | ----------------- | -------- | ------ |

## Final risks and decision

Decision: `FAIL`. The journey is not clean enough to close S00 or unlock W/M/O.
Wave 0AP proved the exact denied `NOT_AUTHORIZED` audit and the applied
publication/terminal binding, but non-retryable `budget_exhausted` prevented
`RuntimeExit.completed`. The provider-relay handoff and failure receipt passed
standalone validation. The failed primary means replay-equivalence deltas are
not applicable; UT-018 and UT-019 remain open.

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

Wave 0AN completed one exact, non-UI primary from Plane
`f8e4c98fe6e44577465c317fb75b61ba43c4fb36` with Hermes
`d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20`. The product lifecycle passed its
ordered internal `s00Gate`, with ten completed upstream `2xx` provider attempts,
one `NOT_AUTHORIZED` evaluator denial, one submit, one applied publication, one
visible `outcome_submission` terminal, and `RuntimeExit.completed`. The helper's
one same-invocation provider-disabled replay passed with zero durable and
semantic deltas. Standalone receipt validation then failed with
`evidence_provider_relay_mismatch` because the fresh authority/config omitted
the provider-relay projection present in the receipt. S00 remains dirty and
UT-018/UT-019 remain open. No source fix, rerun, or Hermes change was made.

## Cross-persona heatmap

| Issue | Personas affected | Severity | Status |
| ----- | ----------------- | -------- | ------ |

## Final risks and decision

Decision: `FAIL`. The journey is not clean enough to close S00 or unlock W/M/O.
The remaining blocker is the fresh handoff contract. Wave 0AN's receipt had the
ordered `s00Gate`, authority-derived canaries, and semantic digest, but the
authority/config descriptors did not declare the provider-relay projection that
the receipt carried. The failed standalone validation keeps UT-018 and UT-019
open.

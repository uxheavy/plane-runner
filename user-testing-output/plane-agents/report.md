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

Wave 0AQ ran one exact, non-UI primary from Plane
`131c3f73cc894ff429c45f837eb20a236e1c69de` with Hermes
`326bc3deb5c1a15468a3104343e97e0b539dec76`. Config-only preflight passed with
the canonical providerRelay projection in both authority and config. The
primary reached the real GPT-5.6 Luna ChatGPT subscription route with fallback
disabled and recorded 11 completed upstream `2xx` provider attempts, one exact
`NOT_AUTHORIZED` evaluator denial, one submit, and three publish audit rows.
The visible terminal was one `outcome_submission`, but the ordered `s00Gate`
failed first at `one_applied_outcome_publication` because the applied
publication count was three and its refs were unavailable. RuntimeExit was
`failed` with non-retryable `runtime_error / host_operation_failure` at final
sequence 21. The conditional provider-disabled replay was not eligible and did
not run. S00 remains dirty and UT-018/UT-019 remain open. No source fix,
rerun, or Hermes change was made.

The runner receipt was `0600`, `5557` bytes, SHA-256
`7f2d0745b7518e2bcb0be34896f90db667495c8e07b05049414bb4597f4273c3`. Its
standalone JSON body was `0600`, `5437` bytes, SHA-256
`e99c5cca3869b91a6f96b262c685be075c551b417cc5222048b1d2f9a7a3df8e`, and
passed standalone failure-receipt validation. Its semantic digest was
`41c8c71650958ce868fe18c94bfd09726a2bff3ded517c6104ae1003abffc997`, which
recomputed exactly. The authority was `s00-live-0aq-20260815`; permitted and
denied canaries were `s00-0aq-permitted-20260815` and
`s00-0aq-denied-20260815`. The providerRelay was the integrated AF_UNIX
`plane.agent-runtime/provider-relay/v1` projection. The receipt and
standalone body were deleted after validation and hashing.

## Cross-persona heatmap

| Issue | Personas affected | Severity | Status |
| ----- | ----------------- | -------- | ------ |

## Final risks and decision

Decision: `FAIL`. The journey is not clean enough to close S00 or unlock W/M/O.
Wave 0AQ proved the exact denied `NOT_AUTHORIZED` audit and the visible
outcome terminal, but three publish audit rows with unavailable applied refs
failed the publication predicate, and non-retryable `runtime_error /
host_operation_failure` prevented `RuntimeExit.completed`. The providerRelay
handoff and failure receipt passed standalone validation. The failed primary
means replay-equivalence deltas are not applicable; UT-018 and UT-019 remain
open.

## Wave 0AR preflight result

0AR is `FAIL`, not a provider or product result. The prior task used the saved-
project Plane repository, where the requested branch input
`codex/agent-functional-dogfood` at
`10eb8033ff9a01d67f5a4cf85772c2f5b464903f` was absent and resolved instead to
`fdb2fd516dfa9b01e89d70cab0d5eb81f741af62`. The original 0AR evidence commit is
`3ed36e4383598cb8f367d21b0ac5efcd3c557bb1`. It was preserved by hash and
reapplied onto exact base `10eb8033ff9a01d67f5a4cf85772c2f5b464903f`.

The requested Hermes `main` input was clean at
`4d9d4b2c76014bd74c69c79d419356f69667986d`. The stop occurred before the
disposable stack, owner-only credential access, or provider relay. Provider
attempts were `0` with status `not-started`. Durable operations and audits were
`0`; no run, invocation, runtime event/exit, gateway receipt, outcome,
publication, terminal event, semantic digest, or replay existed for 0AR.

This preflight mismatch is historical evidence only. S00 remains dirty from
Wave 0AQ. Wave 0AS is the next fresh primary on the exact imported base.

## Wave 0AS result

0AS is `FAIL`. The exact Plane source input was
`10eb8033ff9a01d67f5a4cf85772c2f5b464903f`, parent
`131c3f73cc894ff429c45f837eb20a236e1c69de`; the preserved 0AR evidence
`3ed36e4383598cb8f367d21b0ac5efcd3c557bb1` was reapplied as
`fa66855454093cdccc533e8587729d4f94fb2df4`, parent `10eb...`. Hermes `main`
was clean at `4d9d4b2c76014bd74c69c79d419356f69667986d`. No source, test, or
configuration file was changed.

One fresh non-UI primary used the real ChatGPT subscription route
`openai-codex/gpt-5.6-luna` with fallback disabled. One isolated workspace and
`G4 Live Issue` were created. Run
`run:ff56d973-8133-4b13-8c61-8f7a5dcd6c65` and invocation
`invocation:528d8da8-a8a6-4e27-a34f-3d3c1f9c2f0f` both succeeded. The journey
recorded permitted reads (`search_workspace=2`, `work_item.read=1`), exactly
one durable evaluator denial (`agent.outcome.evaluate=1`, `NOT_AUTHORIZED`),
one submit, one publish, one applied publication, one visible
`outcome_submission`, matching durable refs/binding, and `RuntimeExit.completed`
at final sequence `15`. The six-predicate projected S00 gate passed.

The full primary still failed because the runner requires transcript evidence
separate from publication. Runtime ingress recorded
`progress_observed:14`, `outcome_submission_observed:1`, and
`usage_observed:1`, but no `transcript_evidence_observed` event. The runner
returned `RuntimeError`, phase `api-invocation`, exit `1`, and bounded reason
`unavailable`. Provider attempt count was `7`, sequences `1..7`, all completed
upstream `2xx`; fallback and unknown attempts were absent. Because the full
primary failed, the exact same-invocation provider-disabled replay was not
eligible and did not run.

The owner-only result was `0600`, `5362` bytes, SHA-256
`4025352ae9000db7437161ff7747f977643e435fa367f02df1aaabc74d9665ee`. The
standalone JSON body SHA-256 was
`8b07132f659597da04ee9884eda80ccc8991a5694ba3559be752db00c8077672` and the
semantic digest was
`24d0e954791747457beccd0d37b974edc0bc83fe7a3e9d7f445730cf80b2fe8b`.
Authority/config/manifest SHA-256 values were
`49372ce96914b1b5a68da4dfcdee5f831f1b8b1997917da4a054376aaeccfb0b` /
`18a41a64c557b1bfbf3c5b441b9e32a8bd7f1ef1c278f1c039a020a2dc8e0e9c` /
`836d34c90eef51a382146bd1726f6f40c1d1f96117466ce2635ba5014f7220db`.
The bounded failure receipt validated against the exact authority, canaries,
providerRelay, permissions, redaction, ordering, and manifest bindings; its
failure summary is `collected:0`, `passed:0`.

Cleanup removed the task containers, networks, volumes, provider staging, run
artifacts, result, descriptor files, and disposable API/runtime images. The
owner credential source and authoritative clones were untouched. UT-020 is
open; S00 remains dirty and W/M/O remain locked. No replay or retry occurred.

## Wave 0AT final report

0AT is `PASS` for the S00 non-UI functional user-testing wave. This record supersedes the historical stale S00 failure above; the prior failure was the now-corrected unconditional transcript assertion, not a live lifecycle or authorization failure.

Primary and replay:

- Exactly one fresh primary used the existing ChatGPT subscription with `openai-codex/gpt-5.6-luna`; fallback was disabled. Exactly one eligible same-invocation/same-idempotency-key replay used provider access disabled. No retry or second primary ran.
- Exact clean Plane commit: `577ab42b2712b78d96a46ac224f72005115f94f7`. Exact clean Hermes main: `bc7f13d2ab392752f2667b176c646339c49405f9`.
- Run `6a0d0f49-098f-403d-b91e-b934d7b3f049`; invocation `invocation:0a2717b1-9db8-4399-a29a-a6641f960dbf`; terminal `product-event:f12e8a0e-eb12-4f6d-bd63-8b07dd495d70`; outcome `outcome-submission:830be5e4-de4c-4948-a9d0-c37ab8fd3adb`.
- Provider count/status: `10`, sequences `1..10`, all `completed`, upstream-initiated, `2xx`; fallback `0`; unknown `0`.
- Operation/audit counts: `search_workspace=3` success, `work_item.read=2` success, `catalog.search=0`, `catalog.describe=0`, `agent.outcome.evaluate=1` denied `NOT_AUTHORIZED`, `agent.outcome.submit=1`, `agent.outcome.publish=1`, audit events `18`.
- Gates: invocation `succeeded`; run `succeeded`; one visible outcome terminal; one applied publication; terminal binding passed; `RuntimeExit.completed`, final sequence `22`.
- Transcript expectation/status: `requirement=not_required`, `status=not_observed`, `count=0`, `eventIds=[]`. No actual assistant text existed in evidence, and no synthetic or inferred text was used.
- Replay status: `passed`; provider access `disabled`; all new deltas were zero for provider attempts, children, invocations, receipts, audits, usage, outcomes, publications, terminal events, and semantic side effects.

Evidence and cleanup:

- Owner-only result permissions were `0600`; size `8183` bytes; result SHA-256 `9dd5bdf263a01d06927e3a07961539f3c1dca51c4a05a713899c803c8c5fac8e`; semantic digest `c8aa562cff351c86863098df47ed145df829b8c486ec1a7b6eee9eeb033d0807`. Standalone validation passed.
- Canonical relay was `plane.agent-runtime/provider-relay/v1` over `AF_UNIX`, with child network policy `none`, external egress owner `agent-runtime`, host gateway separate `true`, and Hermes hook `integrated`.
- Cleanup passed for staged credentials, receipts, descriptors, result, run artifacts, containers, networks, volumes, and disposable images. Authoritative clones and owner credential were untouched. No source/config/test edits followed the live result.

Final truth: `PASS`. S00 passed all required lifecycle, authorization-boundary, publication, terminal, transcript-truth, idempotency, evidence, and cleanup predicates. W/M/O are unlocked.

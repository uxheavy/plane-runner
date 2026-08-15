# Plane Agent dogfood wave log

## Baseline — 2026-08-13

- Candidate branch: `codex/agent-functional-dogfood`
- Candidate baseline: `3f2a478209fb94049376f781d33ddd4b63a038de`
- Source baseline: `1d1012f71c48615bb28b7988ce74c82421aa1d53`
- Product scope: complete non-UI Plane Agent system; no chat UI
- Provider/model: ChatGPT subscription route, `openai-codex/gpt-5.6-luna`, no fallback
- Accepted evidence: G0–G3 and offline G4 baseline
- Functional gap: no successful live provider-backed invocation; the existing
  live test covers only read, denied evaluator canary, submit, and publish
- Rollout: explicitly outside this goal; no G5 stage has executed
- Goal-tool note: the pre-existing Codex goal is paused and points to a GOAL.md
  path absent from the old `preview` checkout. Execution follows the corrected
  GOAL.md on this named candidate branch until integration.

## Wave 0AM — exact 4ba604571d / Hermes d9037d5 single fresh S00

- Overall decision: `FAIL`. Exactly one fresh primary ran; there was no retry,
  second primary, fallback, UI, G4/G5 verifier, source fix, Hermes change, or
  additional replay. The runner's internal S00 gate passed and permitted its
  one provider-disabled same-invocation replay, but the final bounded-evidence
  contract did not pass post-run validation, so UT-018 and UT-019 remain open.
- Plane was clean at exact HEAD
  `4ba604571d9582c8fabaf96f7bd457e67511b076` on
  `codex/agent-functional-dogfood`; Hermes was clean at exact HEAD
  `d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` on `main`. Neither source was
  modified by this journey.
- The disposable API artifact was
  `plane-agent-api:s00-4ba604571d`, digest
  `sha256:37385c05fa8bd54f57e8833858051a27dc595ded5d6469014451f5110efd23e5`.
  The runtime artifact was
  `plane-agent-runtime:s00-4ba604571d-hermes-d9037d5`, digest
  `sha256:88357114efe790a9de8312d864f7914a0842769e7524ba3fa29209939f9945a5`.
  Runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667` and
  Hermes tree digest was
  `7de6ace3830c9280302b49cf4266a59f24d91cbeb3ff9c65ed51e10f1381dc89`.
- Fresh manifest, authority, and config SHA-256 values were
  `6df440fa8e45dd05d4d1cc82b69e9975056af0489b37ebe8c93c644e16fb95d1`,
  `6d2dbb92c790bbe20288d608b7f4aac25d7c8bc4a898273b52d28e7ab74ae4c3`, and
  `8a116f2354a34408f383f49428ae74e8e183c8ecba08ae37d432a875179321af`.
  Config-only validation passed before the owner-only credential source was
  accessed. The provider binding was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the AF_UNIX
  `plane.agent-runtime/provider-relay/v1` contract. The exact command hash was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- The fresh absolute result path
  `/tmp/plane-agent-s00-0am.s2aWOI/result.json` was absent before start under
  a `0700` owner-only parent. The runner created one isolated workspace and
  the `G4 Live Issue` journey. Fresh run
  `c7cea1bc-d11d-41be-a2dc-c49dd67974fe` and invocation
  `invocation:e9c1c597-c3fc-4261-aaaa-f4db2ed00014` read back as succeeded.
- The bounded functional readback proved the requested product path:
  `search_workspace` success `3`, `work_item.read` success `1`,
  `catalog.search` and `catalog.describe` absent, exactly one deliberate
  `agent.outcome.evaluate` denial with `NOT_AUTHORIZED`, exactly one successful
  `agent.outcome.submit`, and exactly one successful `agent.outcome.publish`.
  The applied publication binding had one `outcome-submission` product ref,
  one `operation:agent.outcome.publish` ref, and matching receipt, audit,
  application-service, operation-attempt, and product-event refs. One visible
  terminal was `outcome_submission`; ordinary transcript evidence was one
  separate event, not the publication. Runtime ingress counted
  `progress_observed:18`, `transcript_evidence_observed:1`, and
  `usage_observed:1`; no late frame was observed. RuntimeExit was
  `completed`, final sequence `19`, with no failure.
- The runner's ordered internal `s00Gate` predicates all passed, in order:
  `invocation_succeeded`, `run_succeeded`,
  `one_visible_outcome_terminal`, `one_applied_outcome_publication`,
  `terminal_binding`, and `runtime_exit_completed`. There were `9` provider
  attempts, sequences `1..9`, all `completed`, upstream initiated, and `2xx`;
  none was `outcome_unknown`.
- The permitted replay used the same invocation and idempotency key with
  provider access disabled. It passed with zero new children, provider
  attempts, invocations, receipts, audits, usage rows, outcomes, applied
  publications, visible terminals, or semantic side effects.
- The owner-only bounded success receipt was mode `0600`, `6141` bytes,
  schema `plane-agent-g4/live-evidence/v1`, and SHA-256
  `a8fc92228be09d67353a4dc277564ce54c1d9001eb72342672c27ece87f75a7f`.
  Post-run standalone validation rejected it as
  `evidence_permitted_canary_failed`: the fresh authority carried unique
  canary IDs while the runner emitted fixed `live-permitted-read` and
  `live-denied-evaluate` IDs. The success receipt also omitted the ordered
  `s00Gate` projection and semantic digest required by this journey, although
  the internal gate and replay used those checks. This is an evidence-contract
  failure; no product-source cause or fix is claimed.
- Cleanup removed the runner's task-labeled containers, networks, and volumes;
  the owner credential source was not modified or printed. The receipt,
  disposable manifest/authority/config, temporary API/runtime images, and
  temporary stdout/stderr were retained only until this evidence update and
  then deleted and absence-checked. Colima remained running.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; W/M/O remain
  locked.

## Wave 0AO — exact b83a94f6 / Hermes d9037d5 single fresh S00

- Overall decision: `FAIL`. Exactly one fresh provider-backed primary ran. The
  primary failed at the runtime terminal boundary, so the conditional replay
  was not eligible and did not run. There was no retry, second primary,
  fallback, UI, G4/G5 verifier, source fix, or Hermes change. UT-018 and
  UT-019 remain open; W/M/O remain locked.
- Plane was clean at exact HEAD
  `b83a94f61a141a8a1eb00d616d4288899236739e` on
  `codex/agent-functional-dogfood`. Hermes was clean at exact HEAD
  `d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` on `main`. Neither source was
  modified by this journey.
- The exact candidate artifacts were `plane-agent-api:s00-b83a94f6`, digest
  `sha256:97a8348a5bd2b82688b5a833f3b73e9dce80b2a32191e9ac17fd2c78cac59b3e`,
  and `plane-agent-runtime:s00-b83a94f6-hermes-d9037d5`, digest
  `sha256:6b868f9a08422f531d8297670f252841af540ca3b985ac7fd3a10d60d8fa750f`.
  Runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667` and
  Hermes tree digest was
  `7de6ace3830c9280302b49cf4266a59f24d91cbeb3ff9c65ed51e10f1381dc89`.
- Fresh manifest, authority, and config SHA-256 values were
  `e8e5c37866e57e13677f99fe034a20676038c0232607507c2cf22a0798384bb4`,
  `8f88bdc5996d148b04284f9c57ca1ac0c7a5d15d8783c41ad8150bdd6bceb321`, and
  `28ae0f95ef97892bd7c5726704841502f766a0331cfd50e6ef04b0763144f200`.
  Config-only preflight passed before the owner-only provider source was
  accessed. The authority was `s00-live-0ao-20260815` with fresh permitted
  canary `s00-0ao-permitted-20260815` and denied canary
  `s00-0ao-denied-20260815`.
- The provider binding was the real ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the exact canonical
  `providerRelay` in both authority and config:
  `protocol=plane.agent-runtime/provider-relay/v1`, `transport=AF_UNIX`,
  `childNetworkPolicy=none`, `externalEgressOwner=agent-runtime`,
  `hostGatewaySeparate=true`, and `hermesHookStatus=integrated`.
- The fresh absolute result path
  `/tmp/plane-agent-s00-0ao.9EeB7D/result.json` was absent before start under
  a `0700` owner-only parent. The primary produced run
  `e31db362-ba83-4f40-a931-f65ed4fdacd7` and invocation
  `invocation:92e29f6e-8a00-47d9-8423-207f6d39ecda`. The run and invocation
  states were `succeeded`, but RuntimeExit was present with
  `kind=failed`, `code=runtime_error`, `retryable=false`,
  `cause=host_operation_failure`, and final sequence `23`. The outer bounded
  failure was `phase=api-invocation`, exit `1`, with no raw error material
  retained.
- There were exactly 13 ordered provider attempts, sequences `1..13`, all
  `completed`, upstream initiated, and `2xx`; none was unknown and no
  fallback was used. Runtime ingress counted
  `progress_observed=24`. Operation audit counts were
  `search_workspace=success/4`, `work_item.read=success/2`,
  `catalog.search=absent/0`, `catalog.describe=absent/0`,
  `agent.outcome.evaluate=unavailable/1`,
  `agent.outcome.submit=success/1`, and
  `agent.outcome.publish=success/1`. The required evaluator denial was not
  proven: the observed status was `unavailable`, not `NOT_AUTHORIZED`.
- The failed result retained one visible `outcome_submission` terminal and one
  applied publication binding with product ref
  `outcome-submission:c5b5f0dc-3f7e-472a-b2e8-55f31cb6f0a4`, operation ref
  `operation:agent.outcome.publish`, operation-attempt ref
  `operation-attempt:18a9c1da-5717-42ed-bf8c-88115197012d`, gateway receipt
  ref `gateway-receipt:e6ca67a5-a0b2-4607-bfea-05c8e112d58e`, audit receipt
  ref `audit-receipt:e6ca67a5-a0b2-4607-bfea-05c8e112d58e`, receipt ref
  `receipt:18a9c1da-5717-42ed-bf8c-88115197012d`, and product event ref
  `product-event:4d8a01e8-b2d5-403e-aa16-9f71710616ab`. The ordered gate
  failed only at `runtime_exit_completed`; the other five predicates passed.
- The owner-only failure receipt was mode `0600`, full wrapper size `6015`
  bytes, and SHA-256
  `0805a26d1ce73bc2d55475709879a82702c240a7fcb81890e4543356a2e12b36`.
  Its JSON body was `5895` bytes with SHA-256
  `aca33fb027874efca85997e636cca6debc095073b89d1c0751e47d0c1aead735`.
  The bounded failure line and body both validated, semantic digest
  recomputation matched
  `357392642e3e99aba24c6b60e981da201d7c868a22c2112c91ebbffa0bd34ed9`, and
  the standalone validator passed on the JSON body. The receipt was deleted
  only after validation and hashing.
- Because the primary was not a full pass, no provider-disabled replay was
  attempted; replay deltas are therefore `not eligible`, not zero. The exact
  result, run directory, authority/config, disposable manifest, task images,
  and runner resources were cleaned up and absence-checked. The ChatGPT
  credential source was untouched. No Plane product-source or Hermes change
  was made.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; W/M/O remain
  locked.

## Wave 0AN — exact f8e4c98f / Hermes d9037d5 single fresh S00

- Overall decision: `FAIL`. Exactly one fresh primary ran. There was no retry,
  second primary, fallback, UI, G4/G5 verifier, source fix, Hermes change, or
  second command. The primary product path and the helper's one exact same-
  invocation provider-disabled replay passed internally, but standalone receipt
  validation failed. UT-018 and UT-019 remain open.
- Plane was clean at exact HEAD
  `f8e4c98fe6e44577465c317fb75b61ba43c4fb36` on
  `codex/agent-functional-dogfood`. Hermes was clean at exact HEAD
  `d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` on `main`. Neither source was
  modified by this journey.
- The disposable API artifact was
  `plane-agent-api:s00-f8e4c98fe6`, image digest
  `sha256:7e2198f8ed9ab4d0d25997c85f9cbf3bfbe26fe3aa48d10f3fdc0e37473eec64`.
  The runtime artifact was
  `plane-agent-runtime:s00-f8e4c98fe6-hermes-d9037d5`, image digest
  `sha256:ce446f38672070e40f6e0c90857ba944db812d652a56390dbc9c9146d36f3ebe`.
  Runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667` and
  Hermes tree digest was
  `7de6ace3830c9280302b49cf4266a59f24d91cbeb3ff9c65ed51e10f1381dc89`.
- Fresh manifest, authority, and config SHA-256 values were
  `67b174561220d9023297ac38ff2ffebc983cc8fc8b969755db726029f8eb4485`,
  `a52a50fee2ad91cd25037a9dc4483b974e323b2e4d1312fe1372812f347e2274`, and
  `796204e6c843db4eb08b696e4b2cb109517cfd5376e3c5fed8978ce97c954c1e`.
  Config-only validation passed before the owner-only credential source was
  accessed. The authority was `s00-live-0an-20260815` with fresh permitted
  canary `s00-0an-permitted-20260815` and denied canary
  `s00-0an-denied-20260815`. The route was ChatGPT subscription
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the AF_UNIX
  `plane.agent-runtime/provider-relay/v1` contract.
- The fresh absolute result path
  `/tmp/plane-agent-s00-0an.V5p5OI/result.json` was absent before start under
  a `0700` owner-only parent. The persisted receipt was mode `0600`, `8179`
  bytes, and SHA-256
  `08cf95cbf8c2ffc6e9ed32ce9cad15e73b3c24e82fc85fac5160b9c9f1ecd39`.
- Fresh actor `aadc02f4-7635-46ae-840d-305325e47b1a`, run
  `run:41069c5e-8f16-4879-bcd0-6c2003176df0`, invocation
  `invocation:cf2a01e5-e8df-4e94-bc82-205995e56dc4`, outcome
  `outcome-submission:e0895d38-cd5b-4fec-a769-a6293f4da7bd`, and terminal
  product event `product-event:4d03a1d8-d5c5-453b-845a-b400fbb4edba` read back
  successfully. The path proved three workspace searches, one permitted
  `work_item.read`, one `NOT_AUTHORIZED` `agent.outcome.evaluate`, one submit,
  one applied publish, one visible `outcome_submission`, separate transcript
  evidence, and `RuntimeExit.completed` at final sequence `19`.
- There were exactly ten provider attempts, sequences `1..10`, all completed,
  upstream initiated, and `2xx`; none was `outcome_unknown`. The ordered
  internal `s00Gate` predicates all passed: `invocation_succeeded`,
  `run_succeeded`, `one_visible_outcome_terminal`,
  `one_applied_outcome_publication`, `terminal_binding`, and
  `runtime_exit_completed`.
- The one same-invocation provider-disabled replay passed with
  `sameInvocation=true`, `sameIdempotencyKey=true`, and zero new children,
  provider attempts, invocations, receipts, audits, usage rows, outcomes,
  applied publications, terminal events, or semantic side effects.
- The bounded receipt carried semantic digest
  `e5b4ac2dcdd56a63455406ac3a2fcef650e24ce47142a2bb8f97d89b0086122b`, and
  direct recomputation matched its full body. Standalone validation returned
  `evidence_provider_relay_mismatch` because the fresh authority/config
  descriptors omitted `providerRelay` while the receipt included it. This
  handoff failure invalidates the S00 close even though the product path,
  internal gate, and replay passed. No rerun or descriptor repair was made.
- Runner cleanup removed task-labeled containers, networks, and volumes. The
  owner-only credential source was not modified or printed. The receipt,
  authority, config, manifest, disposable run directory, and task images were
  deleted after validation and hashing, then absence-checked. Source trees
  remained clean.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; W/M/O remain
  locked.

## Wave 0A — fast provider smoke

- Status: dirty — UT-001
- Scope: S00 only
- Rule: do not run the full G3/G4 verifier before this smoke
- Result: fresh live contract validated, but the runner stopped in `0.77s`
  before credential staging because a clean checkout had no `tmp/` parent
- Provider/Plane actions: zero
- Cleanup: clean
- Next: Luna root-fixes UT-001 in the established runner, then the same Maya
  task reruns S00 only; a clean smoke unlocks the three parallel journeys

## Wave 0B — runner-fix retest

- Status: dirty — UT-002
- Candidate: `b414ad6672dd79815ae17ab19b436f2a1b45a173`
- UT-001: closed; clean checkout advanced through credential staging
- Plane lifecycle reached: one run, one invocation, and one visible
  `run_blocker`
- Failure: `runtime_transport_pre_dispatch_failure` / `unclassified_exception`
- Provider attempts and requested Plane operations: zero
- Cleanup: clean
- Next: Luna diagnoses and fixes the established runtime transport owner, then
  the same Maya task reruns S00 only

## Wave 0C — credential fix with temporary API artifact

- Status: dirty — UT-003
- Candidate: `5872cf9664ae0266e661454601d56ade5fab9579`
- UT-002: closed; failure is now correctly classified as configuration
- Temporary fixed-source API artifact built successfully; runtime unchanged
- Plane lifecycle reached: one run, one invocation, one visible `run_blocker`
- Failure: amended source was copied to `/workspace/apps/api`, but the command
  resolver likely imported stale prepared-base code from `/code`
- Provider attempts and requested product operations: zero
- Cleanup: clean; temporary API artifact removed
- Next: Luna fixes the established API artifact executable-source boundary,
  then Maya reruns S00 only

## Wave 0D — API artifact path proof

- Status: dirty — UT-004
- Candidate: `1793f338342b93f8a1655f5131aab461d2b68b65`
- UT-003: closed; all three runtime modules load from candidate source
- Failure: configured `/usr/local/bin/plane-agent-runtime-credential-resolver`
  is absent from the candidate API artifact
- Live authority, provider attempts, and Plane product actions: zero
- Cleanup: clean; temporary API artifact removed
- Next: Luna installs and proves the established resolver in the artifact, then
  Maya reruns the network-isolated proof and S00

## Wave 0E — packaged resolver retest

- Status: dirty — UT-005
- Candidate: `0ae680f418afe1da78fc697cf83e53a9d8d280df`
- UT-004: closed; candidate imports and the installed resolver's provenance,
  permissions, byte identity, and synthetic Codex-document behavior passed
- Plane lifecycle reached: one run, one invocation, one visible `run_blocker`
- Failure: the real credential handoff still returns
  `runtime_configuration_pre_dispatch_failure / dispatch_rejected`
- Provider attempts and requested product operations: zero
- Cleanup: clean; temporary API image removed
- Next: Luna traces and root-fixes the broker/lease/resolver configuration
  boundary, then Maya runs one fresh S00 Wave 0F

## Wave 0F — accepted credential, rejected runtime lease

- Status: dirty — UT-006
- Candidate: `5a1e5bfa93eb971fa4138aa8b9b94a7d61a63a90`
- UT-005: closed; current resolver accepts the real Codex document and rejects
  ambiguous input with a redacted classified error
- Plane lifecycle reached: one actor, profile, assignment, run, invocation, and
  lifecycle `run_blocker`
- Failure: the downstream live runtime lease/configuration handoff still returns
  `runtime_configuration_pre_dispatch_failure / dispatch_rejected`
- Provider attempts and requested product operations: zero
- Cleanup: clean; temporary API image removed
- Next: Luna root-fixes the established supervisor/broker/relay lease boundary,
  then Maya runs one fresh S00 Wave 0G

## Wave 0G — unshared credential-revocation state

- Status: dirty — UT-007
- Candidate: `e5b5e626fc69380ed6c02468565f56837de8fcaa`
- UT-006: closed; canonical run binding passed its network-disabled proof
- Failure: API and runtime use different revocation-state paths with no shared
  mount, so runtime-side lease validation cannot observe Plane control state
- Provider attempts and Plane product resources: zero
- Cleanup: clean; temporary API image removed
- Next: Luna reuses the established shared state mechanism in live-runner
  topology, then Maya runs one fresh S00 Wave 0H

## Wave 0H — shared-state and approved live retest

- Status: dirty — UT-008
- Candidate: `fc662d3f3521b44b719c08a57edcbdf402b0dfd5`
- UT-007: closed; the real API-RW/runtime-RO state volume and revocation
  visibility passed, with no runtime secret exposure and exact cleanup
- One user-approved fresh synthetic S00 lifecycle reached a run, invocation, and
  visible `run_blocker`, but still failed pre-provider with unavailable
  phase/detail
- Provider attempts and requested product operations: zero; no replay
- Cleanup: clean; temporary image and handoff removed
- Next: Luna reproduces the exact cross-process path with a local fake provider,
  restores safe classification, and root-fixes the first concrete rejection

## UT-008 pinned-runtime closure

- Candidate: `735f79bb32` after integrating source fix `21bf76c781`
- Root causes: the packaged resolver imported eager Plane/Django state despite
  its intentionally minimal environment; the Hermes child lacked the existing
  non-secret HOME/HERMES_HOME defaults
- Exact pinned runtime path passed HTTP, launcher, Hermes/bootstrap, callback
  socket, and AF_UNIX relay with one fake 2xx attempt
- Callback sequence: intent → started → completed, sequence 1; no secret crossed
- Cleanup: zero labeled containers, networks, or credential-state volumes
- Next: one user-approved real GPT-5.6 Luna Wave 0I lifecycle, then provider-free
  replay proof if the product journey succeeds

## Wave 0I — exact-candidate manifest binding

- Status: dirty — UT-009
- Candidate: `735f79bb32fe9934a98e01b2772232109d546ec7`
- Temporary API image: `sha256:47f806e823ad871f472da9d53d814c6c4edbf5611935a2d395880eece36c8d25`
- Focused resolver, child-environment, diagnostics, shared-state, and cleanup
  proofs passed
- The one live command failed in about 0.36 seconds with
  `authority_apiArtifact_mismatch` before credential read, Plane state, runtime,
  or provider dispatch; provider attempts remained zero and no replay occurred
- Root cause: the runner hardcodes its checkout's frozen manifest while the
  approved authority/config bind the disposable exact-candidate artifact
- Cleanup: clean; temporary API image and handoff removed, pinned images retained
- Next: add one validated manifest-path input that preserves the frozen default,
  then Maya runs one fresh Wave 0J

## Wave 0J — exact-candidate API invocation

- Status: dirty — UT-010; UT-009 closed
- Candidate: `96bb2649f6356f1614a8ba2315089091b12ee938`
- Temporary API image:
  `sha256:76e31ae82eafcaa96cb16e8cf20576fc3e739fd622197011cd022ce073a50b73`
- The checkout-owned manifest and config-only proof passed before side effects
- One fresh run `6ae053c0-2583-4032-8d08-6d2216b283ea` and invocation
  `invocation:58ec752a-8aba-4a41-9368-cedd47394be4` failed at
  `api-invocation` with an unclassified runtime error
- Provider attempts: zero; no replay or downstream product operation ran
- Cleanup: clean; temporary image and all Wave 0J artifacts removed
- Next: reproduce the API/runtime path without external provider traffic,
  expose the first concrete cause, fix only its owner, then run fresh Wave 0K

## Wave 0K — consumer classification retest

- Status: dirty — UT-010 remains open
- Candidate: `0f855f864b2448e0d943996c2f9dc977328244f4`
- Temporary API image:
  `sha256:4ef7acb423f7bc84ce2ead1c160f41d35b697aad4bec62ce80d6b9dbceb231a3`
- Direct network-disabled projection proof passed; the focused pytest wrapper
  was blocked before its body by the absent test database fixture
- One fresh run `7c90f4d3-ac59-4361-8f2f-36d2533a1f59` and invocation
  `invocation:ad89fbc3-3d09-461d-ba65-d08c8f1075b8` still failed at
  `api-invocation`; provider attempts remained zero and no replay ran
- Interpretation: the consumer no longer throws `KeyError`, but the real
  lifecycle producer still supplies an incomplete resolved runtime policy
- Cleanup: clean; temporary image and Wave 0K artifacts removed
- Next: fix the lifecycle/snapshot policy producer, then run fresh Wave 0L

## Wave 0L — execution-dependent lifecycle proof

- Status: dirty — UT-011; UT-010 closed by the fake cross-process path
- Candidate: `0afb4cc9bbf9be96be979c79d7802c2610898128`
- Temporary API image:
  `sha256:4ed5eddf1024e876d38b4ee14b0eba29e8b4f55d82bab97c20ea071a08895aff`
- Focused result: one pass, one failure
- Passed: canonical profile policy flowed through the fake cross-process route
  with exactly one `intent → started → completed` provider attempt and cleanup
- Failed: direct database update of `RunAttempt.snapshot` did not raise the
  expected `DatabaseError`; the immutable run-contract invariant is not enforced
- Live S00 did not start; provider/subscription attempts remained zero
- Cleanup: internal Compose services/network, temporary image, checkout, and
  task files removed; pinned images retained
- Next: enforce snapshot/envelope immutability in lifecycle persistence, rerun
  the two focused tests, then run fresh Wave 0M

## Wave 0M — live entry-point retest

- Status: dirty — UT-012; UT-011 closed as a migration-test false negative
- Candidate: `cb75a6474129d87b3edb077a0760f6aef03c9d68`
- Temporary API image:
  `sha256:b1949914f33d0600790fe0715c64727c9abae4b4e6d1b11881befb700252711a`
- Fresh authority/config validation passed
- One fresh run `5c7936da-5b38-408d-98b5-7a3e22a6ed62` and invocation
  `invocation:014b8a05-869b-400d-86dd-2eca6404f5ec` failed at the
  opaque `api-invocation` boundary; provider attempts remained zero
- Canonical lifecycle policy and database invariants pass independently, so the
  live entry point must be traced for a bypass/override or hidden rejection
- Cleanup: clean; temporary image and all Wave 0M artifacts removed
- Next: compare the live persisted snapshot/envelope with canonical output,
  expose the bounded cause, fix only that entry-point seam, then Wave 0N

## Wave 0N — live budget retest

- Status: dirty — UT-013; UT-012 closed by literal-command fake path
- Candidate: `8702d282bc89c9f474fde51fe15d2382bb92f959`
- Temporary API image:
  `sha256:c8b5a7920ed1a8c67fbd9bda9c02923d9395a70a8f3748b797b19107f3e98855`
- Fresh authority/config validation passed
- One fresh run `a7828d3e-5cc2-4660-b644-f4d53215e77c` and invocation
  `invocation:b008822a-5531-4f88-9135-9166bd14ffe3` failed before provider
  attempt; no replay ran
- Current-source literal command passes offline, while live S00 retains the old
  runtime image; compare runtime-image source/hashes before another call
- Cleanup: clean; temporary API image and Wave 0N artifacts removed
- Next: prove runtime artifact parity, build the current runtime artifact if
  stale, then run fresh Wave 0O

## UT-013 prerequisite — current-source runtime artifact parity

- Status: clean prerequisite; UT-013 remains open until Maya retests S00 in
  Wave 0O
- Candidate: `125b75641b` (imported sealed-donor fix from verified commit
  `772cdb3958fe40c6febcc13a7862e8a59745264d`)
- One matched API/runtime pair was built from exact source
  `772cdb3958fe40c6febcc13a7862e8a59745264d`
- API digest: `sha256:408a979b088d6a2f5eb6688d5a41b94a569bd7fe8fec02420c0b2799e946fa96`
- Runtime digest: `sha256:081e9c1c0d7a23bcf5df38bcdd703db1986fc5178afd462968e7e34a4f9ea192`
- The runtime contains the sealed, create-only-exported Hermes donor attested
  as commit `d2e655101f263329359e7d0de9d0b856202a3e4b`; no local Git-object claim is
  made
- Donor digest: `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`
- Donor inventory: 8,092 regular files; deterministic tree digest
  `9485115c76b71c47b08d14ec4a1df7cb615301f8e151959c00a80382bdb61bbc`
- Eight focused builder/validator tests passed
- The existing bounded real HTTP→launcher→fake-provider path passed in the
  final API artifact: HTTP 200, exactly one `intent → started → completed`
  provider attempt, revoked credential, and relay cleanup
- All disposable images, containers, networks, temporary manifests, and test
  resources were removed; no external provider request ran
- Next: one fresh GPT-5.6 Luna ChatGPT-subscription Wave 0O, stopping at its
  first failure; only a clean Wave 0O closes UT-013 and S00

## Wave 0O — matched current-source live retest

- Status: dirty — UT-014; UT-013 closed because both live artifacts were bound
  to exact candidate `4ec33bb637d4ce7e60c29e0afc50ffb503e43574`
- Fresh authority/config validation passed with ChatGPT subscription routing,
  `openai-codex/gpt-5.6-luna`, and fallback disabled
- One fresh run `6fb4bcc4-503a-4aa7-b7ec-e44dfe86954f` and invocation
  `invocation:65b99651-a21c-4752-aaa7-b4368f342e8a` failed at
  `api-invocation` before any provider-attempt intent
- Plane recorded one visible `run_failure`; provider attempts were zero, and
  no read, denied evaluator operation, outcome, publication, or replay ran
- Cleanup was clean: zero task-labeled containers, networks, or volumes; all
  disposable images and checkout/config artifacts were removed
- Next: Luna exposes and root-fixes only the API→runtime failure owner with a
  provider-free focused proof, then Maya runs one fresh S00 retest

## Wave 0P — provider-audit propagation retest

- Status: dirty — UT-014 remains open
- Candidate: `d3fd5a87f2af7a82231fe771d5ce1f0f0c1f3b24`
- Matched disposable API/runtime artifacts and fresh authority/config validation
  passed with ChatGPT subscription, `openai-codex/gpt-5.6-luna`, and no fallback
- One fresh run `c0bf548b-5a80-47f7-b02c-0cd2def8ef43` and invocation
  `invocation:ba0a1736-fe8c-4f3e-af1b-0b69befe19ec` failed at the same
  `api-invocation` boundary before any provider-attempt intent
- The runtime's new `provider_attempt_evidence_rejected` marker did not reach
  the bounded live receipt; Plane still returned an unspecified `run_failure`
- No read, denied evaluator operation, outcome, publication, replay, or second
  provider invocation ran; cleanup was clean
- Next: fix only the parent/API propagation of the existing structured runtime
  rejection, prove it provider-free, then Maya runs one fresh S00 retest

## Wave 0Q — bounded result handoff retest

- Status: dirty — UT-014 remains open
- Candidate: `c1d7e28b8c7d21605388751140a5cacc38cbb5a7`
- Matched disposable artifacts and fresh GPT-5.6 Luna subscription config passed
- One fresh run `372c6bb8-143d-4876-a9ba-2f019369b5b7` and invocation
  `invocation:dc439242-1556-4749-8505-7c9e72700cde` failed before any
  provider-attempt intent; the receipt remained unspecified
- Code trace after the run showed the new bounded result path is bypassed when
  `call_command("agent_supervisor")` raises during supervisor setup before
  `run_runtime_invocation()` returns
- No read, denied evaluator operation, outcome, publication, replay, or second
  provider invocation ran; cleanup was clean
- Next: provider-free classification of supervisor setup failures, preserving a
  finite safe category in Plane control state and the live receipt, then Maya
  runs one fresh S00 retest

## Wave 0R — supervisor terminalization retest

- Status: dirty — UT-014 remains open
- Candidate: `afe98be81d6feee9856c89f1a001c02be4ecf1c0`
- Before the live run, 11 focused central Django cases passed in 5.27s for
  setup success, bounded terminalization, idempotency, outcome-unknown safety,
  durable readback, and zero provider attempts
- One fresh run `0ff0a87b-a0a5-4a4e-910f-883d87a31e5a` and invocation
  `invocation:df4bb8e5-3537-4932-aaf0-70d1424313b7` still failed before
  provider-attempt intent with an unspecified receipt
- No read, denied evaluator operation, outcome, publication, replay, or second
  provider invocation ran; cleanup was clean
- Next: provider-free exact live-helper test with a fake remote runtime returning
  a finite HTTP rejection. Only after that propagation passes can the remaining
  failure be assigned to real Hermes/bootstrap rather than Plane handoff

## Wave 0T — live subscription retest

- Status: dirty — UT-014 remains open
- Candidate: `ecfacc0ea4712fca3cb24b37d96ca893113b5bad`; matched disposable API
  and sealed-donor runtime artifacts were built once from this exact source
- Fresh authority/config validation passed for ChatGPT subscription routing,
  `openai-codex/gpt-5.6-luna`, and fallback disabled
- One fresh run `dce717b3-d27e-48de-ad85-a9baa50a174e` and invocation
  `invocation:81185303-1f62-46db-b48b-f79d51d346a7` reached the provider but
  blocked at `api-invocation` with finite
  `runtime_configuration_pre_dispatch_failure / runtime_configuration /
dispatch_rejected / provider_attempt_evidence_rejected`
- Eight completed upstream-initiated `2xx` provider-attempt rows were returned,
  so the exactly-one-attempt assertion failed; no read, denial, outcome,
  publication, successful terminal event, or replay ran
- First owner is the trusted Plane host provider-attempt callback seam; the
  raw callback exception is intentionally unavailable in the bounded receipt
- Cleanup removed task resources; prepared base and pinned Hermes donor remain
- Next: diagnose and fix only the live provider-attempt notice contract at the
  trusted host/lifecycle seam, then run one new bounded S00; do not replay this
  invocation

## Wave 0U — provider-audit budget retest

- Status: dirty — UT-014 remains open
- Candidate: `e6d82f05453aec0f866b96be7b952136ec6a1a3e`; matched disposable API
  and sealed-donor runtime artifacts were built once from this exact source
- One fresh run `084b544f-3131-4d94-ac22-80748b654b2f` and invocation
  `invocation:e96056cf-b3d8-4edc-a7f6-ca2171957263` failed at
  `api-invocation` with `reasonCode=unspecified`
- Provider exchanges were sixteen contiguous sequences `1..16`, all completed
  `2xx` and audited, proving the separate provider-audit quota live
- No read, denial, outcome, publication, successful terminal event, or replay
  ran. Cleanup removed task resources; prepared base and pinned Hermes donor
  remain
- Next: expose a finite reason for the post-exchange failure provider-free
  before any new live retest; do not replay this invocation

## Wave 0V — patched-Hermes runtime provenance retest

- Status: blocked before S00; UT-014 remained open.
- Candidate: `cd2cba9472bb8950828fc52d46104513a05565dc`; patched Hermes:
  `21826c256bc1fc8f56e6469e752cb2a5b991ac58`.
- The exact API artifact built once, but the matched runtime artifact failed
  network-disabled source parity: the image had 8,092 Hermes files versus
  8,091 in Git because a tracked dotenv shim was copied again at
  `/opt/hermes/dotenv/__init__.py`.
- No authority/config, credential read, Plane resource, provider attempt,
  product event, or replay occurred. Cleanup was clean.
- The Plane-owned assembly fix now keeps the compatibility dependency outside
  `/opt/hermes`; exact parity, bootstrap, OpenAI Responses, and bounded-budget
  probes passed before Wave 0W.

## Wave 0W — exact patched-Hermes live S00

- Status: dirty — UT-014 remains open; S00 does not unlock W/M/O journeys.
- Exact Plane candidate:
  `ae82d0eaea5799c5fa4e44198bc35e18c6f00c0d`; exact Hermes candidate:
  `21826c256bc1fc8f56e6469e752cb2a5b991ac58`.
- The matched API/runtime pair passed exact-source parity with the dotenv
  dependency outside `/opt/hermes`.
- One fresh ChatGPT subscription journey using
  `openai-codex/gpt-5.6-luna`, with no fallback, persisted 16 contiguous
  completed audited `2xx` provider exchanges, then failed at `api-invocation`
  with `RuntimeError / reasonCode=unspecified`. Run
  `f652c272-0e9a-4b56-a107-a6f57415731b` and invocation
  `invocation:40c71402-b1af-4a1d-8753-a281deb78ef5` ended in `run_failure`.
- No permitted read, denied evaluator operation, outcome, publication,
  successful terminal event, or replay was evidenced. The first owner is the
  runtime-to-Plane finite terminal classification/result handoff after the
  provider budget boundary.
- Cleanup completed with zero task-labeled resources; no second provider call,
  broad verifier, rollout, or source edit ran.

## Wave 0X — exact current-source live retest

- Scope: one fresh S00 journey only; no subthreads, retry, replay, or broad
  verification.
- Candidate: Plane `2fe13301a142e836f810b72a279f81cad3bba644`; Hermes
  `21826c256bc1fc8f56e6469e752cb2a5b991ac58`.
- Artifacts: one API image `sha256:d74fd1b016fd4eb67232119f6f963feca0554b30d7805ca999297fb126eab65b`; reused exact runtime image `sha256:4814122994a680f488248c6a601a90dca5c3d89ff8bdc9369a5102c9e635730f`.
- Config-only candidate binding passed for ChatGPT subscription
  `openai-codex/gpt-5.6-luna`, fallback disabled. The real owner-only source
  was accessed only after validation and no credential value was exposed.
- Fresh run `0729d393-e453-40d3-9bd1-a3b4f5b11d3b` and invocation
  `invocation:b1a7d0d8-fe8b-4101-9df3-a856455f25b0` failed at
  `api-invocation` with `RuntimeError`, `reasonCode=unspecified`, and one
  visible `run_failure`.
- Provider reached: 16 contiguous completed audited `2xx` exchanges, sequences
  `1..16`, upstream initiated; no provider-free lifecycle actions followed.
- Distinction status: durable `RuntimeExitEvidence`, `SupervisorResult`,
  terminal code/reason, ingress kinds/count, and model/tool progress were not
  retained after the runner's temporary database cleanup. Source says the
  observed receipt shape favors a completed exit without explicit outcome
  (`missing_outcome`) over a lost `budget_exhausted` failed exit, but does not
  prove it. The next finite owner is the runtime-exit/supervisor result seam.
- Stop decision: S00 remains dirty and UT-014 remains open. No speculative
  source fix or additional provider call ran.
- Cleanup: zero labeled containers/networks/credential-state volumes; the
  disposable API image and clone were removed; prepared base/runtime images
  preserved. Evidence is the only intended durable change from this wave.

## Wave 0Y — exact c3fc/Hermes 21826 single fresh S00

- Status: blocked at the first finite live boundary; S00 remains dirty and
  does not unlock W/M/O journeys. Exactly one fresh journey ran, with no
  retry, replay, subthread, source fix, or broad verification.
- Exact Plane source: `c3fc708e5292214fe8a7a773703a78450d5d2df7` on
  `codex/agent-functional-dogfood`. Exact Hermes source:
  `21826c256bc1fc8f56e6469e752cb2a5b991ac58`.
- Matched API image: `sha256:29410e7516ec2b8c6e36dc0c4404d9248d12524f9067db37b3cdc810011eaf11`.
  Matched runtime image:
  `sha256:27ebd1f41138d9fa651fac4fcbe58de920f7e0590ca75dbca1e57f478dc7bb8e`.
  Runtime Hermes tree digest:
  `2b3c5ca66f93c1cdbb413c5d60b43dd92674dffc5f6d8b10b6b5b3d89e9287ef`;
  runtime source digest:
  `97139c416cdd952e67e44345dea7a57aff722b8ef0bb1671c0204463f828490d`.
- Fresh manifest SHA-256:
  `07dfd16f53e5823283720815aa99def23ba4ed002f40ad6c92577735a3175bac`.
  Fresh authority/config SHA-256:
  `146917e805eb43adbd322246418b6226f928de52deb09f917badf0dc2e877c86` /
  `ce550480f858d314bf70083f0d269ee023f8d003233383410203619563b6c5ea`.
- Provider route was ChatGPT subscription `openai-codex/gpt-5.6-luna`, with
  fallback disabled. The owner-only source was accessed only after
  config-only validation; no credential value entered evidence.
- Provider-free preflight passed on the exact runtime: the focused relay
  bootstrap completed with one synthetic provider exchange, and the bounded
  budget proof produced 16 successful exchanges followed by a rejected 17th
  with `failure.code=budget_exhausted`, `retryable=false` (29 ordered frames,
  final sequence 29).
- Redacted command: `PLANE_G4_EXPECTED_CANDIDATE=<c3fc...>
PLANE_G4_LIVE_AUTHORITY=<tmp>/authority.json
PLANE_G4_LIVE_CONFIG=<tmp>/config.json PLANE_G4_LIVE_MANIFEST=<tmp>/manifest.json
PLANE_G4_LIVE_COMMAND='bash tools/agent-g4-live.sh'
PLANE_G4_PROVIDER_SECRET_SOURCE=<existing-owner-only-chatgpt-codex-source>
bash tools/agent-g4-live.sh`. Command SHA-256:
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- Fresh live result: runner exit `125`, stdout
  `event=agent.g4.live-runner.failure phase=credential-bind-preflight
error_class=unavailable exit_code=125`, stderr empty. Preserved bounded
  runner receipt SHA-256:
  `62c79b15a5da9221fa9d5739a54c1d639a3ce1482dbb5a350645e27d1b7205f5`.
- Provider exchange count: `0`. Run refs/counts: none; no Plane workspace,
  issue, actor, profile, assignment, run, invocation, or product lifecycle
  record was created. `RuntimeExitEvidence`: not created. Runtime event
  count/kinds: not created. Terminal code/reason: not created. Plane host
  gateway receipts, including the deliberate evaluator denial: not created.
  Outcome, publication, terminal product event, and transcript/publication
  readback: not reached. Exact dispatch replay: not run.
- First owner: live runner / local Colima Docker bind visibility for the
  staged owner-only provider source at `credential-bind-preflight`, before
  Plane application state. No product-source fault is claimed.
- Cleanup: the runner left zero task-labeled containers, networks, and
  volumes. After evidence commit, remove only the task-owned exact Plane and
  Hermes clones, temporary manifest/authority/config/capture, and the two
  task-tagged images; retain no secret or owner credential source.

## Wave 0Z — exact 1a771e4355 / Hermes 21826 single fresh S00

- Status: failed at the first API-container start boundary; S00 remains dirty
  and W/M/O stay locked. Exactly one fresh live S00 journey ran. No retry,
  replay, subthread, source fix, broad verifier, rollout, deployment, UI, or
  unrelated suite ran.
- Exact Plane source: `1a771e43550ed0e67321129fa6e9dc7fd3480599`; parent
  `fdb2fd516dfa9b01e89d70cab0d5eb81f741af62`. Exact Hermes source:
  `21826c256bc1fc8f56e6469e752cb2a5b991ac58`, canonical remote
  `https://github.com/uxheavy/hermes-agent.git`.
- Matched API artifact: `plane-agent-api:s00-1a771e4355`, image digest
  `sha256:97a9893cc0ec099ee561a50cf750b75080f6f2821ba93a4818eda9c7a443aceb`,
  source `1a771e43550ed0e67321129fa6e9dc7fd3480599`, contract
  `plane.operation/v1`. Matched runtime artifact:
  `plane-agent-runtime:s00-1a771e4355-hermes-21826c256b`, image digest
  `sha256:79010ba2e353864e95baad008c11d0fb20c3c69294f818a42c1c30c6def02b33`,
  runtime source `1a771e43550ed0e67321129fa6e9dc7fd3480599`, contract
  `plane.agent-runtime/v1`.
- Runtime provenance: Hermes tree digest
  `2b3c5ca66f93c1cdbb413c5d60b43dd92674dffc5f6d8b10b6b5b3d89e9287ef`;
  Plane runtime source digest
  `97139c416cdd952e67e44345dea7a57aff722b8ef0bb1671c0204463f828490d`.
  Fresh disposable manifest SHA-256:
  `461acf9abad18f8666de808daba2fb9149f4acb272690c6eaecf9175802a9268`.
  Fresh authority/config SHA-256:
  `6515428feaa242c79138a8f807ae5391c16cf265b0f085d8bb8d978d71085cc5` /
  `104fc8f01793cebd5c6a6290d1d20160018d49a5089764427daf32ad75deef74`.
- Provider binding was ChatGPT subscription `openai-codex/gpt-5.6-luna`,
  fallback disabled. Config-only validation passed before the owner-only
  source was read; no credential value was retained. Redacted command:
  `PLANE_G4_EXPECTED_CANDIDATE=<1a771e4355...> PLANE_G4_LIVE_AUTHORITY=<tmp>/authority.json PLANE_G4_LIVE_CONFIG=<tmp>/config.json PLANE_G4_LIVE_MANIFEST=<tmp>/manifest.json PLANE_G4_LIVE_COMMAND='bash tools/agent-g4-live.sh' PLANE_G4_PROVIDER_SECRET_SOURCE=<existing-owner-only-chatgpt-codex-source> bash tools/agent-g4-live.sh`.
  Command SHA-256:
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- The runner returned exit `125` at `api-invocation` with the sole preserved
  bounded line `event=agent.g4.live-runner.failure phase=api-invocation
error_class=unspecified exit_code=125`. Receipt SHA-256:
  `8557b165a4c8976da7195249249925d087e0cc8e9e420ec8110f64ca1fc29f78`.
  Inspecting only the preserved capture and non-secret Docker metadata found
  no retained raw error, no matching historical create/die event, and no more
  specific mount/path/flag reason.
- Live provider exchange count: `0`. Plane workspace, `G4 Live Issue`, actor,
  profile, assignment, run, invocation, gateway receipt, outcome, publication,
  terminal product event, and transcript/publication readback refs/counts:
  none/zero. `RuntimeExitEvidence`: absent. Runtime event kind counts: absent
  (`{}`). Terminal code/reason: not created. Plane host gateway receipt
  presence: `false`. The permitted read, denied `agent.outcome.evaluate`,
  explicit `OutcomeSubmission`, explicit publication, durable readback, and
  exact dispatch replay were not reached.
- First owner: live runner / Docker API-container start boundary at
  `api-invocation`; no Plane source fault is claimed. Cleanup completed with
  zero task-labeled containers, networks, credential-state volumes, or
  provider-secret volumes. The two task-tagged images, exact Plane/Hermes
  clones, and fresh authority/config/manifest were removed after the bounded
  receipt was recorded; the owner credential source was untouched.

## Wave 0AA — exact 336156 / Hermes 21826 single fresh S00

Status: failed at the live API-invocation boundary. The corrected provider-free
start probe passed, then exactly one fresh live S00 was run. No retry, replay,
second live call, source fix, broad verifier, rollout, deployment, UI, or
unrelated suite ran.

- Plane source: `33615620246784a50f7804ff6768fee318cb343f`.
- Hermes source: `21826c256bc1fc8f56e6469e752cb2a5b991ac58`, disposable clone
  origin normalized to `https://github.com/uxheavy/hermes-agent.git`.
- API image: `plane-agent-api:s00-3361562024`, digest
  `sha256:6b2a4d6870cd40e0cdd78c9208108e6f5edc75d291998ee5f57488a41c315096`.
- Runtime image: `plane-agent-runtime:s00-3361562024-hermes-21826`, digest
  `sha256:4d0c159efee287944301fbe443838c33a39807298cb2428d93baae5731801636`.
- Hermes tree digest: `2b3c5ca66f93c1cdbb413c5d60b43dd92674dffc5f6d8b10b6b5b3d89e9287ef`.
- Plane runtime source digest:
  `97139c416cdd952e67e44345dea7a57aff722b8ef0bb1671c0204463f828490d`.
- Fresh manifest/authority/config SHA-256:
  `4918e94264f69a758b878e00e2bf3c5b0abd3b2cbff605e918b47ef55f946471` /
  `60bde4faf86e6fd36c203a946ac0e7fc146cf48f8a2694b878b292288346a014` /
  `1cca0d90200baee566d85524dcfa47afb1fe9b9492a90e7fbc027ad0d96a8264`.
- Provider binding: ChatGPT subscription, `openai-codex/gpt-5.6-luna`, fallback
  disabled. Live command SHA-256:
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- Corrected provider-free final-shape probe printed
  `PLANE_S00_PROVIDER_FREE_START_PROBE=passed` under `--network none`, with
  sibling `/run/plane-agent-runtime-secret`, read-only `/run/secrets`, and
  stdin-fed Python; labeled container/volume/network/temp cleanup verified
  empty.
- The one live API container exited `1` at `api-invocation`; Docker metadata
  shows the runtime was killed by the runner cleanup with exit `137`. The
  runner's bounded JSON was not retained by the desktop shell session before
  cleanup. Provider exchange count, Plane refs/counts, runtime exit/event
  kinds, terminal code/reason, gateway receipts, outcome, publication, and
  transcript/publication separation are therefore unavailable and are not
  inferred. Exact replay was not run.
- Cleanup removed the task-labeled containers, networks, volumes, run files,
  temporary descriptors, exact clones, and two task-tagged images; the owner
  credential source was untouched. Colima was left running.

## Wave 0AC — exact 4f8d341518 / Hermes 21826 single fresh S00

- Status: failed at the first finite live API-invocation result. S00 remains
  dirty and W/M/O stay locked. Exactly one fresh S00 ran; no retry, replay,
  second live call, source fix, broad verifier, rollout, deployment, UI, or
  unrelated suite ran.
- Exact Plane source: `4f8d3415189f6767daf991b50343fd8884e93918`.
- Exact Hermes source: `21826c256bc1fc8f56e6469e752cb2a5b991ac58`; disposable
  clone origin was normalized only to
  `https://github.com/uxheavy/hermes-agent.git`.
- API image: `plane-agent-api:s00-4f8d341518`, digest
  `sha256:f52077589af029e7e1c2b8fd7962c731d119a8fc92ff92b0aba7cc3f25953ce4`;
  source label was the exact Plane SHA, artifact `plane-agent-api-g4`, and
  contract `plane.operation/v1`.
- Runtime image: `plane-agent-runtime:s00-4f8d341518-hermes-21826`, digest
  `sha256:1061c48002e56c575e804a5ec58922b34034b599ed67736bc9d07a81590b7d99`;
  Hermes tree digest
  `2b3c5ca66f93c1cdbb413c5d60b43dd92674dffc5f6d8b10b6b5b3d89e9287ef`, Plane
  runtime source digest
  `f55d6ee5260b49bc396f42b18840e5fcf60e9252b09a1ac8409964073e673dac`, and
  contract `plane.agent-runtime/v1`.
- Fresh manifest/authority/config SHA-256:
  `d83215ad40072bc16f1f9ea4ddeb420a4df1d896c938d4a777f13a5aa24bf0f2` /
  `62f4a927bb19d86c48f9b66a02ee24fc626e0f53ee422680405ea116a831330a` /
  `22c685d27638066731d8950efeb28268cc673cffdb06ea8d7e1752a7775162c0`.
- Provider binding was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, with the integrated AF_UNIX
  `plane-agent-runtime/provider-relay/v1` contract. Config-only validation
  passed before the owner-only credential source was accessed. Redacted
  command:
  `PLANE_G4_EXPECTED_CANDIDATE=<4f8d...> PLANE_G4_LIVE_AUTHORITY=<tmp>/s00-wave0ac-authority.json PLANE_G4_LIVE_CONFIG=<tmp>/s00-wave0ac-config.json PLANE_G4_LIVE_MANIFEST=<tmp>/s00-wave0ac-manifest.json PLANE_G4_LIVE_RESULT_PATH=<tmp>/s00-wave0ac-live-result.json PLANE_G4_LIVE_COMMAND='bash tools/agent-g4-live.sh' PLANE_G4_PROVIDER_SECRET_SOURCE=<owner-only-chatgpt-subscription-source> bash tools/agent-g4-live.sh`.
  Exact command SHA-256:
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- The exact built-API provider-free final-shape start probe passed with output
  `PLANE_S00_PROVIDER_FREE_START_PROBE=passed` under `--network none`,
  read-only `/run/secrets`, sibling `/run/plane-agent-runtime-secret`, and
  stdin-fed Python. Its synthetic volume and secret were removed before the
  owner-only credential source was used.
- Exactly one isolated live run was configured for issue `G4 Live Issue`.
  Fresh run `69933c8b-6897-40b8-acbd-5c83fa6bd086` and invocation
  `invocation:2f2ccdc4-e5e7-4966-8a77-c20dda01d546` were created. The bounded
  receipt retained no actor/profile/assignment refs or durable workspace,
  project, or issue counts.
- Provider attempts were exactly 16, sequences `1..16`; every attempt was
  `completed`, upstream initiated, status class `2xx`, with an empty error
  code, and no fallback. Runtime event ingress was
  `{"progress_observed":33}`.
- RuntimeExit was present with kind `failed`, failure code `runtime_error`,
  and `retryable=false`; its failure phase/detail/subreason were
  `runtime_process` / `process_exit` / `runtime_execution_failed`. The
  terminal event was one `run_failure` with code `runtime_error` and reason
  category `runtime_execution_failed`.
- `planeHostOperationReceipts=true`, but no operation-specific permitted-read
  receipt, denied `agent.outcome.evaluate` receipt, OutcomeSubmission,
  publication, durable readback, or transcript/publication separation refs
  were retained. The required read, denial, outcome, publication, and replay
  assertions are therefore unproven; no dispatch replay ran.
- The explicit result path was asserted absent before start. After exit, its
  bounded JSON was mode `0600`, size `3260` bytes, validated, and hashed as
  `5a03b57b21351c3687b2959eb7db297ab9fd0d6892fb8e6cd54cbe33565968ba`; it
  was then deleted and absence acknowledged. Raw `ERROR_FILE` was never read
  or retained.
- Cleanup removed the live task containers, networks, volumes, run directory,
  staged source, runtime secret, exact disposable clones, task images, and
  fresh config artifacts; post-run task-resource checks were empty. The owner
  credential source was untouched and Colima was left running.
- First owner: runtime/Hermes execution after provider exchange. No Plane
  source fault is claimed because the finite classification survived through
  `SupervisorResult`, durable terminal state, and the bounded receipt.
- Decision: S00 is `FAIL` and does not unlock W/M/O.

## Wave 0AR — exact-input preflight stop

- Status: `FAIL` at setup. The prior task stopped before provider access because its saved-project Plane repository did not contain the required exact input.
- Required Plane input: branch `codex/agent-functional-dogfood` at `10eb8033ff9a01d67f5a4cf85772c2f5b464903f`. The object was absent there and that branch resolved to `fdb2fd516dfa9b01e89d70cab0d5eb81f741af62`. The original 0AR evidence commit is `3ed36e4383598cb8f367d21b0ac5efcd3c557bb1`; it is preserved by hash and was reapplied onto exact base `10eb8033ff9a01d67f5a4cf85772c2f5b464903f`.
- Required Hermes input: clean `main` at `4d9d4b2c76014bd74c69c79d419356f69667986d`.
- Provider/model: ChatGPT subscription route `openai-codex/gpt-5.6-luna`, fallback disabled by authorization, but provider access was not reached. Provider attempts `0`; status `not-started`.
- Durable counts for 0AR: operations `0`; audits `0`; workspaces/issues/actors/profiles/assignments/runs/invocations `0`; runtime events/exits `0`; outcomes/publications/terminal product events `0`.
- Terminal/exit/gate truth: no terminal event, no `RuntimeExit`, no invocation exit, no receipt, no semantic digest, and no replay. S00 gate `FAIL` at the exact Plane input check. Replay was ineligible and not run.
- Receipt and digest truth: none exist for 0AR. No provider content or credential value entered evidence.
- Cleanup: no 0AR stack, runtime, database, container, network, volume, image, result destination, or auth staging was created. No cleanup deletion was needed.
- Stop decision: no retry, replay, or provider attempt was made. Wave 0AS proceeds only from the imported exact local Plane base and exact clean Hermes main.

## Wave 0AP — exact 891a1aed / Hermes 1d9818 single fresh S00

- Overall decision: `FAIL`. Exactly one fresh primary ran; there was no retry,
  second primary, fallback, UI, G4/G5 verifier, source fix, Hermes change, or
  provider-disabled replay. The primary stopped before replay because the
  ordered S00 gate failed at `runtime_exit_completed`.
- Exact Plane source: `891a1aed20344ba5a445c515bc23acd76693c93d`.
- Exact Hermes source: `1d9818e7df007d2ea4f1e3df373aaa812e022e6a`; Hermes was not
  modified.
- API image: `plane-agent-api:s00-0ap-891a1aed`, digest
  `sha256:2d278f86cb70549cb7078dd2ac7e61e584d1d94d121425a8ed5ed5b444ff75ab`.
- Runtime image: `plane-agent-runtime:s00-0ap-891a1aed-hermes-1d9818e7`,
  digest
  `sha256:09e0d793463f71379dcb3b3de1d9b2a0b5a31ac49c054bce5cc4d95f2d496a38`.
  Hermes tree digest:
  `5effc5267e2a3536b0318734f651ac20841fd80008eb1a767408594706c9492`; Plane
  runtime source digest:
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667`.
- Provider binding was the real ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, with canonical
  `plane.agent-runtime/provider-relay/v1` / `AF_UNIX` transport,
  `childNetworkPolicy=none`, `externalEgressOwner=agent-runtime`,
  `hostGatewaySeparate=true`, and `hermesHookStatus=integrated`.
- Config-only preflight passed before the provider source was read. The fresh
  owner-only authority was `s00-live-0ap-20260815` with canaries
  `s00-0ap-permitted-20260815` and `s00-0ap-denied-20260815`; the result path
  was absent before start. The bounded redacted runner command used the exact
  candidate, manifest, descriptors, result path, and
  `PLANE_G4_PROVIDER_SECRET_SOURCE=/Users/nqh/.codex/auth.json` without
  transmitting repository files, raw transcripts, or credentials.
- One fresh run `0c78d15e-9509-4ec9-a5f2-f01740be9088` and invocation
  `invocation:fb54f115-a7e8-4624-8dd1-72548fdba8d4` reached the real provider.
  The receipt recorded ten ordered provider attempts, sequences `1..10`, all
  `completed`, upstream initiated, and `2xx`; no fallback or unknown attempt
  occurred. RuntimeExit was `present=true`, `kind=failed`, final sequence `22`,
  failure `budget_exhausted`, `retryable=false`.
- Bounded Plane operation audit proved `search_workspace` success `3`,
  `work_item.read` success `1`, exactly one `agent.outcome.evaluate` with
  `status=denied`, `errorCode=NOT_AUTHORIZED`, and `count=1`, one submit
  success, and one publish success. The S00 gate proved one visible
  `outcome_submission`, one applied outcome publication, and matching terminal
  binding refs. Its first failed predicate was only `runtime_exit_completed`.
- The persisted two-line runner receipt was owner-only `0600`, `5683` bytes,
  SHA-256
  `a5eb2c596c91a98702f3e8697cfc24f77fdc08b865bca4747058d0ccfc1f6855`.
  The standalone JSON body was owner-only `0600`, `5563` bytes, SHA-256
  `681de547b72b9e773b3a0d0876b2c06ca1f5b93e50e232420476120cbadcbbf4`, and
  passed `validate_agent_g4_live.py` as a bounded failure receipt. Its
  semantic digest was
  `fb3e69b5e206ea7236a6cd719944a29b8f4ab22d3ab69b7d7a6f9846689cd6b4`, and
  independent recomputation matched. Canaries were correctly retained as
  `not_evaluated` for this failed receipt; the provider-relay projection was
  exact.
- Because the primary gate failed, the conditional same-invocation
  provider-disabled replay was not eligible; replay deltas are not applicable,
  and no replay attempt was made.
- Cleanup removed the receipt, standalone body, descriptors, manifest, exact
  temporary API/runtime images, and owner-only temporary directory. Post-run
  checks found zero labeled containers, networks, and volumes and no exact
  temporary image tags. Plane and Hermes remained at their exact source
  commits; the provider credential source metadata remained unchanged.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain open and W/M/O stay locked.

## Wave 0AQ: exact 131c3f73 / Hermes 326bc3de single fresh S00

- Overall decision: `FAIL`. Exactly one fresh primary ran. There was no retry,
  second primary, fallback, UI, G4/G5 verifier, source fix, Hermes change, or
  provider-disabled replay. The primary stopped before replay because the
  ordered S00 gate failed at `one_applied_outcome_publication`.
- Exact clean Plane source was
  `131c3f73cc894ff429c45f837eb20a236e1c69de`. Exact clean Hermes source was
  `326bc3deb5c1a15468a3104343e97e0b539dec76`. Hermes was not modified.
- The disposable API artifact was `plane-agent-api:s00-0aq-131c3f73`, digest
  `sha256:9a38e8f0d829c54b4bcfd11fe7171004d82a19f0a1bb585121ae63e519a02f1f`.
  Its source label was the exact Plane SHA, contract `plane.operation/v1`, and
  artifact label `plane-agent-api-g4`.
- The matched runtime artifact was
  `plane-agent-runtime:s00-0aq-131c3f73-hermes-326bc3de`, digest
  `sha256:75ea7d08067cf26ac58774114415ae96fc6572e4dcb6798b05dfd412aec26abe`.
  Its runtime source was the exact Plane SHA, Hermes commit was the exact
  `326bc3de` SHA, Hermes tree digest was
  `7b9e107fed730e89e0427c9d41f941c2b75c400b15601ee73043acbf5a6662f6`, Plane
  runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667`, and
  contract was `plane.agent-runtime/v1`.
- Disposable manifest, authority, and config SHA-256 values were
  `726e06039fa0bd9ccc32cc3279f262d3e358d61378453eab11ebc89cc5be2337`,
  `976f0e0af056d63be24559375e53b1c4879fd67f06752f8509033d6172966c0c`, and
  `dabcd1a1fd5aab30fc39e31ce30a8c1bfc4e508a6d5955f05f7356f0fa3cab3e`.
  Config-only validation passed before the owner-only provider source was
  read. The provider was ChatGPT subscription `openai-codex/gpt-5.6-luna`,
  fallback disabled. The exact command hash was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
  The authority was `s00-live-0aq-20260815` with permitted and denied canaries
  `s00-0aq-permitted-20260815` and `s00-0aq-denied-20260815`. The providerRelay
  projection was the integrated AF_UNIX
  `plane.agent-runtime/provider-relay/v1` contract with child network policy
  `none`, external egress owner `agent-runtime`, separate host gateway, and
  integrated Hermes hook.
- The fresh absolute result destination
  `/tmp/plane-agent-s00-0aq.tPdH0a/result.json` was absent before start under
  a `0700` owner-only parent. One isolated workspace and one `G4 Live Issue`
  assignment were created. Fresh run
  `e7e4dcb6-16f1-4466-92c5-85f4708d0e87` and invocation
  `invocation:63226705-7cef-4121-84ae-9a044a910fa5` were created.
- Provider attempts were exactly 11, sequences `1..11`. Every attempt was
  completed, upstream initiated, and `2xx`; no fallback or unknown attempt
  occurred. Runtime ingress counted `progress_observed:21` and
  `outcome_submission_observed:1`. RuntimeExit was present with kind `failed`,
  final sequence `21`, failure code `runtime_error`, retryable `false`, and
  cause `host_operation_failure`.
- Plane operation audit proved `search_workspace` success `2`,
  `work_item.read` success `1`, exactly one `agent.outcome.evaluate` denial
  with `NOT_AUTHORIZED`, one `agent.outcome.submit` success, and three
  `agent.outcome.publish` successes. The product readback had one visible
  `outcome_submission` terminal. The first failed S00 predicate was
  `one_applied_outcome_publication`: count `3`, action and all applied refs
  unavailable. `terminal_binding` and `runtime_exit_completed` were also
  false. No replay ran, so replay deltas are not applicable.
- The persisted two-line failure receipt was owner-only `0600`, `5557` bytes,
  SHA-256
  `7f2d0745b7518e2bcb0be34896f90db667495c8e07b05049414bb4597f4273c3`.
  Its standalone JSON body was owner-only `0600`, `5437` bytes, SHA-256
  `e99c5cca3869b91a6f96b262c685be075c551b417cc5222048b1d2f9a7a3df8e`, and
  passed `validate_agent_g4_live.py` as
  `plane-agent-g4/live-failure/v1`. Its semantic digest was
  `41c8c71650958ce868fe18c94bfd09726a2bff3ded517c6104ae1003abffc997`; an
  independent recomputation matched exactly. The receipt and standalone body
  were deleted after validation and hashing.
- The runner cleanup removed the task-labeled containers, networks, volumes,
  provider staging, runtime secret, and run directory. Post-run checks found
  zero task-labeled containers, networks, and volumes. The exact temporary API
  and runtime images, disposable manifest, authority, config, and owner-only
  run directory were removed during final cleanup. Plane and Hermes remained
  at their exact source commits, and provider credential metadata was
  unchanged.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain open and W/M/O stay locked.

## Wave 0AL — exact 35a129bf / Hermes d9037d5 single fresh S00

- Status: `FAIL` at the pre-replay live product lifecycle assertion. S00
  remains dirty and W/M/O stay locked. Exactly one fresh primary ran through
  Plane runtime service and hidden Hermes. There was no retry, fallback,
  second provider call, replay, source edit, UI test, broad verifier, or
  unrelated suite.
- Plane was clean at exact HEAD
  `35a129bf7c1c55cef3319e492c51046d909959e9` on
  `codex/agent-functional-dogfood`. Hermes was clean at exact HEAD
  `d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` on `main`.
- The API artifact was `plane-agent-api:s00-35a129bf7c`, digest
  `sha256:aefd7208c28b747765c4fe549c4dbac6685b29ecbff7800870c1111fa211eaf2`.
  The runtime artifact was
  `plane-agent-runtime:s00-35a129bf7c-hermes-d9037d5`, digest
  `sha256:8fba6852424c9a39eb9df189fb94988e7af2d58cb4f249842bfedad671ba9030`.
  Runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667`;
  Hermes tree digest was
  `7de6ace3830c9280302b49cf4266a59f24d91cbeb3ff9c65ed51e10f1381dc89`.
  Both artifacts were bound to the same candidate and
  `plane.agent-runtime/v1`.
- Disposable manifest, authority, and config hashes were
  `c656776e0d9aaf3e3e9528b0ebd4c594eb31650f29389d70b1c31e877b3f499a`,
  `6e41133e37ac8af4811dbe5374343ba4395f29d0695e6b92870927faa16ebd70`,
  and `af7f3f4ba62c1751c09cf54c623f2349ce3cff2710fa891d1896211b43278fce`.
  Config-only validation passed before the owner-only provider source was
  read. The route was ChatGPT subscription
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the integrated
  `plane.agent-runtime/provider-relay/v1` AF_UNIX contract.
- The caller used the fresh absolute nonexistent result path
  `/tmp/plane-agent-s00-0al.jzBSOd/result.json` under a `0700` parent.
  The persisted receipt was mode `0600`, size `3311` bytes, schema
  `plane-agent-g4/live-failure/v1`, redacted, and SHA-256
  `303478fa8bad6365a2e29ede26fe629f0398d2734c9963484df4ec99817ba947`.
- Fresh run `e8ea6b83-ecf8-47db-9953-3109b58f35e5` and invocation
  `invocation:cf1bdf9f-4133-44ed-b2b8-f7fe098e8c1f` read back as
  `succeeded`. The operation audit was `search_workspace` success `3`,
  `work_item.read` success `1`, `catalog.search` absent, `catalog.describe`
  absent, `agent.outcome.evaluate` denied `NOT_AUTHORIZED` `1`,
  `agent.outcome.submit` success `1`, and `agent.outcome.publish` success
  `1`. Provider attempts were exactly `10`, sequences `1..10`, all
  `completed`, upstream initiated, and `2xx`; no attempt was
  `outcome_unknown`. Runtime ingress counted `progress_observed:19`,
  `transcript_evidence_observed:1`, and `usage_observed:1`. One visible
  terminal kind was `outcome_submission`; RuntimeExit was present,
  `completed`, with final sequence `20` and no failure.
- The first broken boundary was the in-process API invocation lifecycle gate
  immediately before `before_replay`. The bounded failure receipt does not
  retain the predicate-level result for explicit applied-publication
  separation or terminal source/product-ref binding, so no narrower cause is
  claimed. Late-frame classification, ordinary final-text/publication
  separation, semantic digest, owner-only receipt details beyond the bounded
  receipt, and receipt/result equivalence were not proven. No replay was
  eligible after this failed primary.
- Runner cleanup removed the task Compose resources, provider staging,
  runtime secret, run directory, and receipt after acknowledgment. Post-run
  checks found zero task-labeled containers, networks, or volumes. The
  disposable exact images, manifest, authority, and config were removed after
  this evidence update. The owner-only ChatGPT source was not changed or
  printed. Plane and Hermes remained clean at their required commits.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; W/M/O remain
  locked. No Plane or Hermes source was changed.

## Wave 0AK — exact c0edcab5 / Hermes 5c8a265f single fresh S00

- Status: `FAIL` at the post-publication runtime boundary. S00 remains dirty;
  UT-018 and UT-019 remain open; W/M/O remain locked. Exactly one fresh primary
  ran. There was no retry, second primary, fallback, replay, source fix, UI,
  broad G4/G5 verifier, or unrelated suite.

### Exact binding and provider-free preflight

- Plane was clean at exact HEAD
  `c0edcab5577c659a3617ab2946553742f37a532e` on
  `codex/agent-functional-dogfood`; Hermes was clean at exact HEAD
  `5c8a265f0a90ff198b82b5bbdefe5db328b60295` on `main`. No provider access was
  attempted before the exact source, manifest binding, config-only contract,
  and fresh result-path checks passed.
- The disposable API artifact was
  `plane-agent-api:s00-c0edcab5577c`, digest
  `sha256:f5c0d5171882ab5cdd087a7f4d95e536a28b06ec66242324f4b717025082579b`.
  The runtime artifact was
  `plane-agent-runtime:s00-c0edcab5577c-hermes-5c8a`, digest
  `sha256:142d38e39140dd4fc96380823da292b128ba20a684b742979545f879c08120ff`.
  The manifest bound both artifacts to Plane `c0edcab5`, Hermes `5c8a265f`,
  contract `plane.operation/v1` for the API and `plane.agent-runtime/v1` for
  the runtime. The provider descriptor was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the integrated
  `plane.agent-runtime/provider-relay/v1` path.
- Config-only validation passed before the owner-only provider source was
  staged. The exact command hash was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
  The fresh absolute result destination was
  `/tmp/plane-agent-s00-0ak.4aGIgc/result.json`; its parent was `0700` and the
  destination was absent before the primary.

### One primary and bounded failure

- The single primary dispatched through the Plane runtime service with hidden
  Hermes and created the isolated workspace plus `G4 Live Issue` journey.
  The bounded receipt retained `search_workspace` success `2`,
  `work_item.read` success `1`, `agent.outcome.evaluate` denied with
  `NOT_AUTHORIZED` exactly `1`, `agent.outcome.submit` success `1`, and
  `agent.outcome.publish` success `2`. The required publish exactly-once
  assertion therefore failed. `catalog.search` and `catalog.describe` were
  absent.
- Provider attempts were exactly `10`, sequences `1..10`; every attempt was
  `completed`, upstream initiated, `2xx`, with an empty error code. No attempt
  was unknown and no sequence `11` or later was retained, so the bounded
  evidence shows Hermes stopped before provider attempt N+1.
- Runtime ingress counted `progress_observed:19` and
  `outcome_submission_observed:1`. A terminal observation was present as
  `outcome_submission`, but it carried `runtime_error`; this is not accepted
  as a successful visible terminal product event. RuntimeExit was present but
  `failed`, final sequence `19`, with
  `failure.code=runtime_error`, `cause=host_operation_failure`, and
  `retryable=false`, so the clean completed RuntimeExit assertion failed.
  Late-frame classification, ordinary-final-text versus publication
  separation, owner receipt application details, and semantic digest were
  not retained by this bounded failure schema and are not inferred.
- The first failed exact-once assertion is the publish audit count `2`; the
  independent outer failure boundary is `api-invocation` / runtime process
  exit. The root hypothesis is limited to the post-terminal runtime/host
  operation termination or publication-coordination boundary; no causal
  source diagnosis or fix was made during the journey.

### Receipt, replay, cleanup, and decision

- The owner-only result handoff used the runner's documented failure format:
  one bounded failure event line followed by one JSON object. Before deletion
  it validated as schema `plane-agent-g4/live-failure/v1`, status `failed`,
  redacted, regular, owner-only mode `0600`, parent mode `0700`, and `3421`
  bytes. SHA-256 was
  `8a759a859e02e4d2cd7c6506f9c4e15f2e2283e732f7c451e25c64bca5601416`.
- Because the primary failed, the exact same-invocation replay predicate was
  not met. No provider-disabled replay ran, and no replay-side zero-provider,
  zero-effect, or receipt/result-equivalence claim is made.
- Cleanup removed the runner's task containers, networks, volumes, staged
  provider credential, runtime secret, and run directory. Exact post-run
  checks found no task-labeled Docker resources or runner temporary artifacts;
  the task's two disposable images, generated manifest, descriptors, and
  result receipt were then removed. The source
  `/Users/nqh/.codex/auth.json` remained owner-only and was not modified;
  Plane and Hermes remained clean at their requested heads.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; no Plane product
  source or Hermes source was changed.

## Wave 0AH — exact f285842598 / Hermes b39be101 single fresh S00

### Exact binding and provider-free preflight

- The authoritative Plane checkout was clean at
  `f2858425984c2ee038fad56e88eca5ee0aa2a0ea` on
  `codex/agent-functional-dogfood`; Hermes was clean at
  `b39be1013fd24fe05db006dc90ffc9cd05b0ca12` on `main`. No provider call was
  made until these identities and cleanliness checks passed.
- The disposable API image was bound to Plane source
  `f2858425984c2ee038fad56e88eca5ee0aa2a0ea`, tag
  `plane-agent-api:s00-f2858425984c`, digest
  `sha256:79efb23152368a0e61431237ff3f801fa8fb620af0d751a3bc8ef513b1628ceb`.
  The disposable runtime image was bound to the same Plane revision and Hermes
  `b39be1013fd24fe05db006dc90ffc9cd05db0ca12`, tag
  `plane-agent-runtime:s00-f2858425984c-hermes-b39be101`, digest
  `sha256:6c1c522e6cfa9b262012bc463c78a2c552161768612405c2b08ba241ac1ab496`.
  The runtime contract was `plane.agent-runtime/v1`; the Hermes tree digest was
  `f8cc0961f7d6fa1a8ee0be1ed52df437a0083c2abf890058932d8d677e41b68b`.
- Fresh disposable manifest, authority, config, workspace, actor, profile,
  assignment, run, invocation, and idempotency binding were used. Config-only,
  source/image, and exact contract preflight passed before provider use. The
  owner-only ChatGPT subscription source was staged only for the isolated run,
  was not printed or retained, and remained unchanged.

### One fresh primary and bounded failure

- The route was `openai-codex/gpt-5.6-luna`, fallback disabled, through
  `plane.agent-runtime/provider-relay/v1`; exact command SHA-256 was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- Exactly one primary process was started and waited to completion. It returned
  exit `1` with bounded failure `phase=api-invocation`,
  `error_class=RuntimeError`, and `reason_category=unavailable`. The fresh run
  was `2fab01a5-7751-495f-9db8-ba3627e72873`; invocation was
  `invocation:0973f573-1b0d-49d6-8c42-a85c0528eee5`; both retained
  `succeeded` state in the bounded handoff, with terminal kind
  `outcome_submission` and `planeHostOperationReceipts=true`.
- The permitted eager/progressive read path was observed: `search_workspace`
  succeeded `3` times and `work_item.read` succeeded once. The deliberate
  `agent.outcome.evaluate` was denied with recoverable `NOT_AUTHORIZED` once;
  `agent.outcome.submit` succeeded once; and
  `agent.outcome.publish` succeeded once. The bounded runtime ingress retained
  `progress_observed=20`, `transcript_evidence_observed=1`, and
  `usage_observed=1`; RuntimeExit was present as `completed` with final sequence
  `21`. The terminal kind and publish operation were observed, but the full
  exactly-one visible terminal-event assertion is not accepted because the
  primary handoff was a failure/unknown result.
- Provider attempts were `12`: sequences `1..4` and `6..12` were
  `completed`/upstream-initiated/`2xx`; sequence `5` was
  `outcome_unknown`. This is the first bounded failure for this run. No raw
  prompts, model text, tool payloads, provider secrets, or credentials were
  retained.

### Replay, cleanup, and decision

- Because the primary contained `outcome_unknown`, the exact same-invocation
  replay predicate was not met. No retry and no replay occurred; therefore no
  replay-side zero-delta claim is made.
- Before deletion, the owner-only bounded failure receipt was validated for
  schema, binding, bounded fields, permissions, size, and sensitivity. It was
  mode `0600`, `3529` bytes, schema
  `plane-agent-g4/live-failure/v1`, SHA-256
  `74bc53ffdad3f11bb7f8ebba705029eedefbcebdf9aad3995cea380489d60b70`.
- Cleanup removed the run's task containers, network, volumes, staged source,
  runtime secret, temporary descriptors, receipt, and the two disposable exact
  images. Post-cleanup checks found no task-labeled Docker resources or task
  temporary artifacts; unrelated resources were preserved. Plane and Hermes
  remained clean at their expected commits.
- Decision: S00 is `FAIL`; UT-018 remains `open`; W/M/O remain locked. No
  product source was changed.

## Wave 0AI — exact ab6d2058 / Hermes b2f1990d single fresh S00

### Exact binding and provider-free preflight

- The authoritative Plane checkout was clean at
  `ab6d2058cdda89a8b11f873dc3b80daab51b5638` on
  `codex/agent-functional-dogfood`; Hermes was clean at
  `b2f1990dcf8fb9ca5a7d811fe1645420e9dafeec` on `main`. Both identities and
  cleanliness were rechecked immediately before the primary process.
- Exact disposable images were prepared only because they were absent: API
  `plane-agent-api:s00-ab6d2058`, digest
  `sha256:8f99583aa3133a12d7a06196dd8f1367ee2b8a3a35b839e8158bb5bce04c7323`,
  and runtime `plane-agent-runtime:s00-ab6d2058-hermes-b2f1990d`, digest
  `sha256:5e0d6e92053c2aba739bb1bbf217b5eeed9c92dec873ec586f0d2e8acd1fc8e2`.
- Fresh disposable manifest, authority, and config SHA-256 values were
  `d48bd2c4be5c0082b69635a54a5c535cc3daec8bac559724a20a506303ec4f22`,
  `c3e0a1a63dfba9451e2605d31b5195a8dd1b535f6441a2625c4ff5e7fff6b069`, and
  `0d09be730da922f7bfe84d4fb4588773834fde0734c96d7678cc8381a89460ce`.
  Config-only validation and the owner-only auth-source mode check passed
  before the primary process; the auth source was not printed or changed.
- The configured route was `openai-codex/gpt-5.6-luna`, ChatGPT subscription,
  fallback disabled, through `plane.agent-runtime/provider-relay/v1`.

### One primary and bounded failure

- Exactly one primary process was started and waited to completion. It
  returned the bounded runner event:
  `event=agent.g4.live-runner status=failed expected=fresh-owner-only-result-path actual=unsafe-or-colliding-path`.
- The supplied `PLANE_G4_LIVE_RESULT_PATH` was relative
  (`tmp/s00-exact-ab6d2058/result.json`). The runner rejected it before
  creating the run directory, staging credentials, starting Docker, reading
  the provider source, or contacting `chatgpt.com`.
- Counts before cleanup were provider attempts `0`, child processes `0`, and
  Plane actor/profile/assignment/run/invocation/receipt/audit/usage/outcome/
  publication/terminal/semantic effects `0`. No permitted read, evaluator
  denial, submit, publish, terminal event, or transcript observation was
  reached. The exact invocation command hash was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.

### Replay, receipt, cleanup, and decision

- Because the primary failed at the pre-provider boundary, no retry and no
  replay was attempted. The same-invocation zero-delta replay predicate was
  not eligible.
- No bounded receipt was generated: the runner rejected the result path
  before result persistence. Receipt hash/mode/bytes are therefore
  `not generated` / `not applicable` / `not applicable`.
- Cleanup removed only the exact disposable API/runtime images and the fresh
  manifest, authority, and config directory. No task-labeled containers,
  networks, or volumes existed. The owner-only credential source was
  untouched, Colima remained running, and no unrelated state was removed.
- Decision: S00 is `FAIL`; UT-018 and UT-019 remain `open`; W/M/O remain
  locked. No Plane or Hermes source was changed.

## Wave 0AJ — exact b00e5e5b / Hermes b2f1990d single fresh S00

- Status: failed at the bounded runtime model-call budget boundary. S00
  remains dirty; UT-018 and UT-019 remain open; W/M/O remain locked. Exactly
  one fresh primary ran. No retry, replay, second provider call, source fix,
  G4/G5 journey, rollout, or unrelated suite ran.
- Exact Plane source was clean at `b00e5e5b47c10fb2c40733ccc63dee9dd980ac85`
  on `codex/agent-functional-dogfood`; Hermes was clean at
  `b2f1990dcf8fb9ca5a7d811fe1645420e9dafeec` on `main`. The exact disposable
  API image was `plane-agent-api:s00-b00e5e5b47c1`, digest
  `sha256:38a42c0976ad0ae9584951ce8067ffce7e54ecebc4fdadf21e22c2d5b954df5e`.
  The exact disposable runtime image was
  `plane-agent-runtime:s00-b00e5e5b47c1-hermes-b2f1990d`, digest
  `sha256:a1ce26bac6ea8e33a3568f4c0a934f2778439f90e4e45a0370c890d8e3e73adc`.
  Hermes tree digest was
  `251d200eb421954afb6843c8b2be697af39e9720425a175db767650541a14c12` and
  Plane runtime source digest was
  `3dbd31d22bca27c722f972b2610a45d3e48ee18110457be9ec3ab668e89c7669`.
- Fresh authority/config binding passed config-only validation before the
  owner-only source was read. The route was the ChatGPT subscription
  `openai-codex/gpt-5.6-luna`, fallback disabled, through
  `plane.agent-runtime/provider-relay/v1`. The command hash was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
  The result destination was the fresh absolute
  `/tmp/plane-agent-s00-0aj.s44tr8/result.json`; its parent was mode `0700`
  and the destination was absent before start.
- Exactly one primary process ran to completion. It returned exit `1` with
  bounded `phase=api-invocation`, `error_class=unspecified`, and
  `reason_category=unavailable`. The bounded failure reason was
  `budget_exhausted / runtime_process / process_exit /
model_call_budget_exhausted`. Run
  `d4f5136d-6654-416f-af0f-595e2d886e8d` and invocation
  `invocation:3599842d-20ca-4127-bc4a-27f4722f6cf8` both read back as
  `succeeded` before the outer bounded failure.
- Provider attempts were exactly `13`, sequences `1..13`; every row was
  `completed`, upstream initiated, `2xx`, and had an empty error code. No
  attempt was `outcome_unknown`. RuntimeExit was present as `failed`, final
  sequence `24`, with `failure.code=budget_exhausted` and `retryable=false`.
  Runtime ingress counted `progress_observed:25`.
- The bounded audit summary proved `search_workspace=success x5`,
  `work_item.read=success x1`, evaluator denial
  `agent.outcome.evaluate=denied / NOT_AUTHORIZED x1`, submit success x1,
  and publish success x1. The visible terminal readback was present as one
  `outcome_submission` with `code=budget_exhausted`; no replay was eligible.
  The failed receipt did not retain transcript/publication separation fields,
  so that assertion is not claimed as independently proven by this wave.
- The owner-only bounded failure receipt was validated before deletion. It was
  schema `plane-agent-g4/live-failure/v1`, mode `0600`, parent mode `0700`,
  size `3621` bytes, and SHA-256
  `037c724c2e901d8fc350c44cd70cba7e17896dd0564e91a3b64034cad5cc79ef`.
  No sensitive field was present. The exact result path was absent after
  acknowledgment. The disposable manifest, authority/config descriptors,
  exact images, and temporary decision log were removed after capture.
- Cleanup found zero task-labeled containers, networks, or volumes. The
  owner-only source was not changed. Plane and Hermes remained clean at their
  exact requested heads. Decision: S00 is `FAIL`; no retry/replay, UT-018 and
  UT-019 stay open, and W/M/O stay locked.

## Wave 0AG — exact 053ce18c / Hermes b39be101 single fresh S00

Status: primary live lifecycle passed, but S00 remains dirty because the
bounded pass receipt did not retain the complete ordered operation/provider
evidence and no exact no-provider replay was available after runner teardown.
UT-018 remains open and W/M/O stay locked. Exactly one primary provider
invocation ran; no retry, second provider call, or outcome-unknown replay ran.

### Exact binding and provider-free preflight

- Plane was clean at exact HEAD
  `053ce18c8b0b29cba7115ca9411e61f54bc3a285`, branch
  `codex/agent-functional-dogfood`. Hermes was clean at exact `main` HEAD
  `b39be1013fd24fe05db006dc90ffc9cd05b0ca12`.
- API image `plane-agent-api:s00-053ce18c8b` digest
  `sha256:872f985463c8aa604066f99c14dcd2084c4cae4975d8d16aa89d05986a426ba7`;
  runtime image `plane-agent-runtime:s00-053ce18c8b-hermes-b39` digest
  `sha256:bca62591058b44eb093f054bdddf06b01569c6bd5427e94e741f811d7f1c2247`.
  Labels bound Plane `053ce18c...`, Hermes `b39be101...`, Hermes tree digest
  `f8cc0961f7d6fa1a8ee0be1ed52df437a0083c2abf890058932d8d677e41b68b`, Plane
  runtime source digest `c5a1665e598d9d72b151a8042049250de978b6300a66358053f0816eb1509060`,
  and contract `plane.agent-runtime/v1`.
- Disposable manifest/authority/config SHA-256 values were
  `795c5939fc72ba34c7960fab44645399f7c64ff8e476cb1ef28de688c117b64d`,
  `94f1092ac605c17be53e269dab430f896564c8cd5bd315a0bce4580db265ab2a`, and
  `536ca82ff88ff1ead0bf2a1ee52d048ca899caec04848e4e927f267c76766f02`.
- Both contract manifests were byte-identical at
  `714f63844ad84370e0ec467dac19fef3f79b3c47a3c4bae8493437f283913bc0`; the
  RunSnapshot schema digest was
  `308101c6a2c9f56e7deb5c6a07c8bc74b59831b92cbbb5b07c5a7eefc21f4947`.
  The isolated eager-schema probe passed for `work_item.read` with canonical
  `project_id` and `issue_id`. Authority/config validation passed before the
  owner-only provider source was read.

### One fresh primary and bounded pass

- Route was `openai-codex/gpt-5.6-luna`, fallback disabled, through
  `plane.agent-runtime/provider-relay/v1`; exact command SHA-256 was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- The primary exited `0` with bounded `status=passed`. Refs were actor
  `0f08003d-909c-4d95-9208-1783bacd306a`, run
  `f46fe053-ea7f-47bc-b171-bb919d533240`, invocation
  `invocation:0afe8909-5e4f-46d3-9c1d-0b40620f9dc7`, and terminal
  `product-event:f91cd7ae-42e6-4170-984f-8b2e5b793cad`. Invocation state was
  `succeeded`, terminal kind `outcome_submission`, outcome count `1`, runtime
  event count `22`, and provider HTTP class `2xx`.
- The bounded receipt was mode `0600`, size `3508` bytes, schema
  `plane-agent-g4/live-evidence/v1`, and SHA-256
  `f7b771481396e7591cd5a6bc860a22cb2888437ee95e35c8b63979d3ece5588c`.
  Readback retained audit event count `16`; permitted/denied/submit/publish
  outcomes were all reported as passing and observed thresholds were
  permitted `1.0`, denied rejection `1.0`, error `0.0`, latency p95
  `58376.915ms`. No raw prompt, model output, tool payload, provider secret,
  or credential was retained.
- The in-process lifecycle gate confirmed a permitted read path, recoverable
  `agent.outcome.evaluate` denial with `NOT_AUTHORIZED`, one explicit outcome
  submission, one explicit publication, one outcome, and a terminal event.
  The bounded pass schema did not retain the exact read operation ID, ordered
  provider-attempt rows/sequences, runtime event-kind counts, RuntimeExit
  kind/category, per-operation audit rows, or transcript/publication refs; the
  missing fields are not inferred.

### Replay, cleanup, and decision

The primary passed, but the existing isolated runner destroys the local
database during its exit cleanup and exposes no post-primary exact replay
hook. No safe exact no-provider replay was run; no replay result is claimed.
The receipt was validated before deletion. S00 is therefore `FAIL` at the
evidence/replay boundary; UT-018 remains open and W/M/O stay locked. No
product source was changed.

## Wave 0AF — exact 7b538491 / Hermes b39be101 single fresh S00

Status: failed at the first finite API-invocation boundary. S00 remains dirty;
UT-018 remains open and W/M/O stay locked. Exactly one fresh primary S00
invocation ran. No retry, no replay, no second provider invocation, no source
change, and no broad verifier, rollout, deployment, or unrelated test ran.

- Exact clean Plane source was
  `7b5384912ab85df5638b7059f49a7d68df2f3bf0`, branch
  `codex/agent-functional-dogfood`; exact clean Hermes source was
  `b39be1013fd24fe05db006dc90ffc9cd05b0ca12`, branch `main`.
- The provider-free binding proof used disposable API image
  `plane-agent-api:s00-7b5384912a`, digest
  `sha256:337e4e76f6576f2209d19b36594e2308e1d8f46ec10a0f4d18280d77ec9107cc`,
  and runtime image
  `plane-agent-runtime:s00-7b5384912a-hermes-b39be101`, digest
  `sha256:a28ad2a6000070f11d43fcb0f90c80c1e27b7ead1389c42b3ffe885a90f515a3`.
  The Hermes tree digest was
  `f8cc0961f7d6fa1a8ee0be1ed52df437a0083c2abf890058932d8d677e41b68b` and
  the Plane runtime source digest was
  `ed823d3b79c64484a9989aa78e7a865a80a0d100c6eabf991fd2b2ed4ec9b217`.
- The disposable manifest, authority, and config SHA-256 values were
  `418ffd741e0be33c864ebdd6f926ff6a8981ff77b75b3e5e9201e55b76764040`,
  `cb2b2636109aee31058582cefe47e19c05ee295dd59c23aa5306ec0cb8f2e63b`, and
  `5815eaff5d291dddf04e7f409608019e391b257766abaa39b671e0af6e541869`.
  Authority/config validation passed before provider-source access.
- Contract manifests were byte-identical at SHA-256
  `714f63844ad84370e0ec467dac19fef3f79b3c47a3c4bae8493437f283913bc0`.
  The provider-free schema digests were run snapshot
  `308101c6a2c9f56e7deb5c6a07c8bc74b59831b92cbbb5b07c5a7eefc21f4947`,
  invocation envelope `b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995`,
  runtime event `78da5ce9d112b6545ea471e5fcae25ff5dfeb2e5db74a8d5796d0ee026823a27`,
  runtime exit `86b5acaa14271b1c5f0f0fadc30f48bc5cd24ac8db0ff03ba8a91d02bceecf65`,
  and durable state `444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da`.
  The built API probe confirmed eager `inputSchema` with `project_id` and
  `issue_id`; image/source parity and exact cleanup-path probes passed.
- The configured route was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, through
  `plane.agent-runtime/provider-relay/v1`. The live command SHA-256 was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
  The primary stopped before making a provider request: provider attempts
  `0`, runtime ingress `kindCounts={}`, and `runtimeExit.present=false`.
- The bounded owner-only receipt had schema
  `plane-agent-g4/live-failure/v1`, status `failed`, mode `0600`, 2110 bytes,
  and SHA-256
  `e59655625dfda461f785cd9cb48a33be21aedb005138db8b949a5bb185dcdf71`.
  Its finite first failure was `phase=api-invocation`, `exitCode=1`,
  `errorClass=RuntimeError`, `reasonCode=runtime_process_failed`,
  `reasonPhase=runtime_process`, `reasonSubreason=unavailable`,
  `reasonDetail=process_exit`; terminal was one run blocker with code
  `runtime_process_failed` and reason category `process_exit`.
- The bounded receipt retained run
  `9ab8e880-a62a-421c-8645-7f10d33f895d` and invocation
  `invocation:cccc4be3-70ac-4fb0-89c7-1f7e9fe83fae`, both `blocked`; it did
  not retain workspace, assignment, actor, profile, or product-outcome refs.
  `planeHostOperationReceipts=false`. The five retained operation audit rows
  were all `absent`/count `0`; the fixed six-operation view is:
  `search_workspace` not reached/0, `work_item.read` absent/0,
  `catalog.search` absent/0, `agent.outcome.evaluate` absent/0,
  `agent.outcome.submit` absent/0, and `agent.outcome.publish` absent/0.
  Durable counts were run `1` blocked, invocation `1` blocked, provider
  attempts `0`, host receipts `0`, operation counts `0`, outcomes `0`, and
  publications `0`. No model final text/transcript was retained and no
  publication occurred; ordinary final text therefore was not publication.
- The primary failed, so exact no-provider replay was not eligible and was not
  run. The receipt was validated before deletion; the exact result, run
  directory, authority/config/manifest, task-owned images, containers,
  networks, and volumes were then removed. The owner credential source was
  untouched (mode `0600`, owner `nqh:staff`, 4211 bytes). Post-cleanup
  checks found no task resources or task images and Plane/Hermes remained at
  the expected commits and clean worktrees.

Decision: S00 is `FAIL`; UT-018 remains open and W/M/O stay locked. The first
safe owner is API/runtime process availability before provider dispatch. No
product source was changed.

## Wave 0AE — exact 2ef6123f / Hermes eb45db95 single fresh S00

- Status: `FAIL` at the first finite live API-invocation result. S00 remains
  dirty and W/M/O stay locked. Exactly one fresh S00 ran; there was no retry,
  replay, second live call, source edit, broad verifier, rollout, deployment,
  UI test, or unrelated suite.
- Exact clean Plane source: `2ef6123f7d21ee52058d2cc0a0b42c067dee3e3c`, parent
  `10d063feb2a6581678c27aa81d2e759ef359e96c`, branch
  `codex/agent-functional-dogfood`. Exact clean Hermes source:
  `eb45db95fd165e3d7f4cd45db720fb667a245b5c`, parent
  `cfe4237f87f8b9ef83243cdab1bd52ed8769556f`, branch `main`.
- Disposable exact Plane clone:
  `/Users/nqh/Documents/Codex/2026-08-14/plane-agent-s00-wave-0ae/work/plane-s00-exact-2ef6123f`.
  Disposable exact Hermes clone:
  `/Users/nqh/Documents/Codex/2026-08-14/plane-agent-s00-wave-0ae/work/hermes-s00-exact-eb45db95`.
- API image: `plane-agent-api:s00-2ef6123f7d21`, digest
  `sha256:6e075ea5871eff1485dfd072efd00586ebe57c51a78f97e5d87cacac13e3ccc1`.
  Runtime image: `plane-agent-runtime:s00-2ef6123f7d21-hermes-eb45db95`,
  digest
  `sha256:bc107e74ccd859a754c792b9204c1c54f0ca4005a49f1998a47f446a2ab9ec19`.
  Hermes tree digest:
  `1d979741558d131895f98fd641968d9c5251beb1600de3a5e9baa566c76aeb92`;
  Plane runtime source digest:
  `ed823d3b79c64484a9989aa78e7a865a80a0d100c6eabf991fd2b2ed4ec9b217`.
- Fresh manifest, authority, config, and bounded receipt SHA-256 values:
  `593c294877c224abf8c9dc63d1faca93dfa1ddf0b60190ce56e9adb03c29584f`,
  `f4888a2e196a8a04798ec62ea5cbb7644e5c6a732278c172405fb83e24c3eddc`,
  `696c3a4960a16cd9862325da0ae11c0c32bfcae5162f203eeb5db8f3cd6dece5`,
  and
  `5b00f153a8dd5f1e896bf162f565501636ce444b6fdb30daf3fe98928a737462`.
  The receipt was owner-only mode `0600`, size `3737` bytes, and passed the
  bounded receipt validation script. Raw provider/runtime errors, prompts,
  model output, tool payloads, credentials, and raw audit rows were not read
  or retained.
- Provider binding was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, with the integrated AF_UNIX
  `plane-agent-runtime/provider-relay/v1` contract. Config-only validation
  passed before the owner-only source was read. Command SHA-256:
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- One isolated disposable workspace and one `G4 Live Issue` assignment were
  created through the existing invocation path. Fresh run
  `151a54a1-f41f-4aea-aca7-22e985a4089b` and invocation
  `invocation:d39ee653-2926-4ed0-b3af-97050f8b77c2` were created. The bounded
  receipt retained run and invocation refs but no actor, profile, assignment,
  or outcome refs; those unavailable readbacks are not inferred.
- Provider-attempt readback contained exactly 16 rows, sequences `1..16`, all
  completed, upstream initiated, and `2xx`. No fallback or second external
  provider request was used. Runtime ingress counted
  `progress_observed:35`. RuntimeExit was present with `kind=failed`,
  `code=budget_exhausted`, `retryable=false`; the visible terminal product
  state was exactly one `run_failure` with reason category
  `model_call_budget_exhausted`.
- The fixed five-operation summary was:

  | Operation                | Status        | Error              | Count |
  | ------------------------ | ------------- | ------------------ | ----: |
  | `work_item.read`         | `unavailable` | `VALIDATION_ERROR` |     8 |
  | `catalog.search`         | `success`     | none               |     2 |
  | `agent.outcome.evaluate` | `absent`      | none               |     0 |
  | `agent.outcome.submit`   | `absent`      | none               |     0 |
  | `agent.outcome.publish`  | `absent`      | none               |     0 |

- Gateway audit summary contained 10 rows, represented by the five operation
  counts above. `OutcomeSubmission` count was `0`; explicit publication count
  was `0`; visible terminal event count was `1` and was the failure event.
  The permitted read, denied `agent.outcome.evaluate`, explicit submit, and
  explicit publish success criteria were not reached. No semantic mutation or
  publication duplicate was possible in this failed journey.
- Exact dispatch replay was not eligible and was not run because the primary
  invocation failed before the full successful terminal product state.
- Cleanup removed the runner's task-labeled containers, networks, volumes,
  provider staging, runtime secret, run directory, and disposable config,
  manifest, and receipt after this evidence was recorded. The task-tagged API
  and runtime images and exact Hermes clone were removed. Post-cleanup label
  checks found zero task-labeled containers, networks, or volumes and no
  task-tagged images. Colima remained running and credential metadata was
  unchanged. The committed Plane evidence clone remains intact.
- First safe owner: runtime/Hermes execution after the provider boundary. No
  Plane source fault is claimed and no product source was changed. Decision:
  S00 is `FAIL` and does not unlock W/M/O.

## Wave 0AD — exact c137306c2d / Hermes 1a82685 single fresh S00

- Status: `FAIL` at the first finite live API-invocation result. S00 remains
  dirty and W/M/O stay locked. Exactly one fresh S00 ran; there was no retry,
  replay, second live call, source edit, broad verifier, rollout, deployment,
  UI test, or unrelated suite.
- Exact clean Plane source: `c137306c2d9771c3705e3629de5474a2f09396fb`,
  parent `0a45fb1596c031ee63bfac54afba269c51ed7ca6`, branch
  `codex/agent-functional-dogfood`. Exact clean Hermes source:
  `1a82685d1f55719216d292c37de9f90638a44cd9`, parent
  `f1c1df9153728e3252d6213a21bb725f28b11580`, with the local clone remote
  normalized to `https://github.com/uxheavy/hermes-agent.git`.
- API artifact: `plane-agent-api:s00-c137306c2d97`, digest
  `sha256:cd35033eedd27d1ea4a185e9b14e3e541b3b1c4963321369d9b8f9e44fed1338`,
  source label exact Plane SHA, contract `plane.operation/v1`, artifact
  `plane-agent-api-g4`. Runtime artifact:
  `plane-agent-runtime:s00-c137306c2d97-hermes-1a82685d`, digest
  `sha256:feba1e54b87898f13945a2c900a132ddc130965fa24940c0c050fb8a947cae0d`,
  runtime source digest
  `ed823d3b79c64484a9989aa78e7a865a80a0d100c6eabf991fd2b2ed4ec9b217`,
  Hermes tree digest
  `0492ab05f64105efdd7eb8ded72adca557a9b1c378bb5743b1bd3ba19631bab1`,
  contract `plane.agent-runtime/v1`.
- Fresh disposable manifest, authority, and config SHA-256:
  `4707337456ed2d43b07f25c41ea0e55b0002a81d91aa8ef8d0c608f9343b31bb`,
  `35ac89989ab3ae6dcbf4dc3e9efb2eb7c163b3663b44cf8d15278fbdae316ad6`,
  `64e6fe11bc77bb5888135db9765c5f1a01fbff97071e18f45937daeebbe1d753`.
  The authority/config gate passed before the owner-only credential source
  was accessed. Provider route was ChatGPT subscription,
  `openai-codex/gpt-5.6-luna`, fallback disabled, through the integrated
  `plane.agent-runtime/provider-relay/v1` AF_UNIX contract.
- One isolated workspace and `G4 Live Issue` assignment were created. Fresh
  run `cbb50c57-e95a-426b-a717-bd8325bc84b6` and invocation
  `invocation:01fd5f56-3156-4f01-9592-7ead56e3397c` were created. The bounded
  live result retained run/invocation state and gateway summary, but did not
  retain workspace/project/issue, actor/profile/assignment, outcome, or
  publication refs; those absent fields are not inferred.
- Provider-attempt readback contained 17 rows: 16 completed, upstream
  initiated, `2xx` exchanges (sequences `1..16`) and one non-sent row at
  sequence `17`. No second external provider request is claimed. Runtime
  ingress counted `progress_observed:31`.
- RuntimeExit was present with `kind=failed`, `code=runtime_error`,
  `retryable=false`, safe `cause=host_operation_failure`. The terminal
  product state was one `run_failure` with code `runtime_error` and reason
  category `host_operation_failure`. The bounded failure prefix was
  `phase=api-invocation`, exit `1`, with no raw error material retained.
- The fixed five-operation summary was:

  | Operation                | Status        | Error              | Count |
  | ------------------------ | ------------- | ------------------ | ----: |
  | `work_item.read`         | `unavailable` | `VALIDATION_ERROR` |     8 |
  | `catalog.search`         | `success`     | none               |     2 |
  | `agent.outcome.evaluate` | `absent`      | none               |     0 |
  | `agent.outcome.submit`   | `absent`      | none               |     0 |
  | `agent.outcome.publish`  | `absent`      | none               |     0 |

- The successful `catalog.search` is the permitted read/discovery evidence.
  The required denied evaluator canary, explicit `OutcomeSubmission`, and
  explicit publication were not reached. Because all mutation/publication
  entries were absent, no duplicate semantic side effect was evidenced; exact
  dispatch replay was not run after the failure.
- The owner-only bounded receipt was mode `0600`, size `3902` bytes, validated
  against `plane-agent-g4/live-failure/v1`, and retained as
  `e92b8e89274f796d2b553d84b1ea9b9b05d6d065d0412b4b753fb10f50f1d0f2` until
  ledger commit. Raw provider/runtime error logs, model output, credentials,
  prompts, and audit rows were not read or retained.
- Runner cleanup proved zero task-labeled containers, networks, or volumes;
  provider staging and run directory were removed. Colima remained running.
  Disposable config/manifest, runtime image, and exact local clones were
  removed after the evidence commit. Credential metadata was unchanged.
- Decision: S00 is `FAIL`; UT-018 remains open and W/M/O stay locked. First
  safe owner is runtime/Hermes execution after provider exchange; this task
  made no product-source change.

## Wave 0AB — exact d2e8d541 / Hermes 21826 single fresh S00

- Status: failed at the first finite live API-invocation result. S00 remains
  dirty and W/M/O stay locked. Exactly one fresh S00 ran; no retry, replay,
  second live call, source fix, broad verifier, rollout, deployment, UI, or
  unrelated suite ran.
- Exact Plane source: `d2e8d541c7cee50815425120e76fd53aebf8b2b3`.
- Exact Hermes source: `21826c256bc1fc8f56e6469e752cb2a5b991ac58`; disposable
  clone origin was normalized only to
  `https://github.com/uxheavy/hermes-agent.git`.
- API image: `plane-agent-api:s00-d2e8d541`, digest
  `sha256:f79dbf92701652ab8ed159d4320475d27a932494cea76587fad8f7465b9744d9`.
- Runtime image: `plane-agent-runtime:s00-d2e8d541-hermes-21826`, digest
  `sha256:9d36a4fbdefe2525c3eda3fa6134c190e2f02d105a004ee57cf12bb439079218`.
  Hermes tree digest:
  `2b3c5ca66f93c1cdbb413c5d60b43dd92674dffc5f6d8b10b6b5b3d89e9287ef`;
  Plane runtime source digest:
  `97139c416cdd952e67e44345dea7a57aff722b8ef0bb1671c0204463f828490d`.
- Fresh disposable manifest/authority/config SHA-256:
  `af6e97a6a86d1ddde0ea7bc97719e2bdc1de6c4b60b566e6f61dd2097d671553` /
  `c7e5d968f203b9a148285f91b8fc98bc995680549af8654ba407fc58a6888168` /
  `dd0889a7c450914e4748f760fea4ec5d9bbd6e4361dc281136c25a5441a4d377`.
- Provider binding was the ChatGPT subscription route
  `openai-codex/gpt-5.6-luna`, fallback disabled, with the integrated AF_UNIX
  `plane-agent-runtime/provider-relay/v1` contract. Config-only validation
  passed before the owner-only source was read. Redacted command:
  `PLANE_G4_EXPECTED_CANDIDATE=<d2e8...> PLANE_G4_LIVE_AUTHORITY=<tmp>/authority.json PLANE_G4_LIVE_CONFIG=<tmp>/config.json PLANE_G4_LIVE_MANIFEST=<tmp>/manifest.json PLANE_G4_LIVE_RESULT_PATH=<tmp>/s00-wave0ab-result.json PLANE_G4_LIVE_COMMAND='bash tools/agent-g4-live.sh' PLANE_G4_PROVIDER_SECRET_SOURCE=<owner-only-chatgpt-subscription-source> bash tools/agent-g4-live.sh`.
  Exact command SHA-256:
  `dd3c370ffe33e29b0fd940536e67d95de57be761248d5bbd5fc1fb08a95c98c7`.
- The exact API final-shape provider-free probe passed under `--network none`
  with the sibling runtime-secret mount, read-only `/run/secrets`, and
  stdin-fed Python. Its disposable volume and secret file were removed.
- One fresh run `67f3f55d-bf30-4e34-8cd0-32c644925ce5` and invocation
  `invocation:a4629a45-ff2a-4383-9655-a6dc630079e2` reached the real provider.
  The bounded result recorded 16 ordered provider exchanges, sequences `1..16`,
  all `completed`, upstream initiated, and `2xx`; no fallback was used. It
  recorded `runtimeEventIngress.kindCounts={"progress_observed":33}`,
  `runtimeExit.present=true`, `runtimeExit.kind=failed`,
  `runtimeExit.failure.code=unavailable`, `retryable=false`, and one terminal
  `run_failure` with code/reason category `unavailable`.
- The bounded result's `planeHostOperationReceipts` flag was `true`, but its
  bounded schema retained no operation-specific permitted-read, denied
  evaluator, outcome-submission, publication, or durable readback references.
  Therefore the required S00 product journey was not proven. Exact dispatch
  replay was not run.
- The explicit owner-only result path was asserted absent before start. After
  exit, the result was read, size/mode/schema/binding/sequence/content checks
  passed, and its SHA-256 was
  `f998e593c8cf967c1e884756322dbbb094c3711e8522e782c2054d9af648863d`.
  The exact result was then deleted and acknowledged; raw `ERROR_FILE` was
  never read or retained.
- First owner: the runtime-to-Plane terminal classification/result seam after
  the provider exchange. No Plane source fault is claimed by this run; the
  bounded result now proves the evidence handoff, while the finite terminal
  code/reason remains unavailable.
- Cleanup: the live runner removed its task containers, networks, volumes, run
  directory, staged source, and runtime secret; post-run label checks were
  empty. The two task-tagged images, exact disposable Plane/Hermes clones, and
  fresh manifest/authority/config were removed. The owner credential source
  was untouched, and Colima was left running.
- Decision: S00 is `FAIL` and does not unlock W/M/O.

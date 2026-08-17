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

## Wave 0AS — exact 10eb8033 / Hermes 4d9d4b2 single fresh S00

- Status: `FAIL`. Exactly one fresh non-UI primary ran; no retry, provider-disabled replay, second primary, source/config/test change, G4/G5 verifier, UI, deployment, rollout, or external mutation ran. S00 remains dirty and W/M/O stay locked.
- Plane source was imported locally from the authoritative exact clone at
  `10eb8033ff9a01d67f5a4cf85772c2f5b464903f`, parent
  `131c3f73cc894ff429c45f837eb20a236e1c69de`. Preserved 0AR commit
  `3ed36e4383598cb8f367d21b0ac5efcd3c557bb1` was reapplied as evidence commit
  `fa66855454093cdccc533e8587729d4f94fb2df4`, whose parent is the exact
  `10eb...` base. The authoritative Hermes `main` was clean at
  `4d9d4b2c76014bd74c69c79d419356f69667986d`.
- API artifact was `plane-agent-api:s00-0as-fa668554`, digest
  `sha256:e0926a1244918544161de26fa9e9429a1ecef362278a9a173c88676d5875b343`.
  Runtime artifact was
  `plane-agent-runtime:s00-0as-fa668554-hermes-4d9d4b2c`, digest
  `sha256:627fd4809c8e5b93c5974f773da3e7896d814cc06c4db6e1a04ac4603f073f8a`.
  Hermes tree digest was
  `60f07ec87122fe5d154af978e7a5c70bb84b4d7ff49814462c83152ee082c76e`,
  runtime source digest was
  `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667`, and
  runtime contract was `plane.agent-runtime/v1`.
- Fresh manifest, authority, and config SHA-256 values were
  `836d34c90eef51a382146bd1726f6f40c1d1f96117466ce2635ba5014f7220db`,
  `49372ce96914b1b5a68da4dfcdee5f831f1b8b1997917da4a054376aaeccfb0b`, and
  `18a41a64c557b1bfbf3c5b441b9e32a8bd7f1ef1c278f1c039a020a2dc8e0e9c`.
  Config-only validation passed before the owner-only credential source was
  accessed. Authority was `s00-live-0as-20260815`; canaries were
  `s00-0as-permitted-20260815` and `s00-0as-denied-20260815`. Provider binding
  was ChatGPT subscription `openai-codex/gpt-5.6-luna`, fallback disabled,
  through `plane.agent-runtime/provider-relay/v1` over AF_UNIX. The exact
  runner command SHA-256 was
  `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- Preflight proved clean exact source trees, canonical providerRelay /
  authority / config equality, owner-only staged credential metadata, an
  absent fresh owner-only result destination, and zero pre-existing task
  cleanup-label containers, networks, and volumes. One isolated workspace and
  `G4 Live Issue` were created. The bounded receipt retained no workspace,
  issue, assignment, or profile refs; those absent fields are not inferred.
- One run `run:ff56d973-8133-4b13-8c61-8f7a5dcd6c65` and invocation
  `invocation:528d8da8-a8a6-4e27-a34f-3d3c1f9c2f0f` reached the real provider.
  The provider attempt count was exactly `7`: ordered sequences `1..7`, all
  `completed`, upstream initiated, `2xx`, with no fallback and no unknown
  outcome. Operation/audit counts were:

  | Operation                | Status  | Error            | Count |
  | ------------------------ | ------- | ---------------- | ----: |
  | `search_workspace`       | success | none             |     2 |
  | `work_item.read`         | success | none             |     1 |
  | `catalog.search`         | absent  | none             |     0 |
  | `catalog.describe`       | absent  | none             |     0 |
  | `agent.outcome.evaluate` | denied  | `NOT_AUTHORIZED` |     1 |
  | `agent.outcome.submit`   | success | none             |     1 |
  | `agent.outcome.publish`  | success | none             |     1 |

- The projected S00 gate had status `passed`, first failed predicate `null`,
  and all six predicates true: invocation/run succeeded, exactly one visible
  `outcome_submission`, exactly one applied publication, terminal binding, and
  `RuntimeExit.completed` with final sequence `15` and no failure. The applied
  publication was `outcome-submission:b297e84b-8e1f-49e7-b953-7b412f326ce2`,
  operation `operation:agent.outcome.publish`, attempt
  `operation-attempt:5feb1f96-8f75-4438-8fae-f410b6b7a424`, gateway receipt
  `gateway-receipt:d9e933d3-0e91-4521-a3ea-ce6fa7acb6a3`, receipt
  `receipt:5feb1f96-8f75-4438-8fae-f410b6b7a424`, audit receipt
  `audit-receipt:d9e933d3-0e91-4521-a3ea-ce6fa7acb6a3`, and product event
  `product-event:7e90d59e-4182-4e4f-876f-5b57944efe50`; terminal refs matched
  the same run, invocation, outcome, and product event.
- The full primary contract failed after that projection. The runner returned
  exit `1` with `RuntimeError`, phase `api-invocation`, reason code
  `unspecified`, reason detail/phase/subreason `unavailable`. Its assertion
  requires at least one `transcript_evidence_observed` event, but runtime
  ingress contained only `progress_observed:14`,
  `outcome_submission_observed:1`, and `usage_observed:1`. Ordinary model
  final text was therefore not proven transcript-only. No replay was eligible
  and no provider-disabled replay was attempted.
- The owner-only persisted result was `0600`, `5362` bytes, and SHA-256
  `4025352ae9000db7437161ff7747f977643e435fa367f02df1aaabc74d9665ee`.
  Its standalone JSON body SHA-256 was
  `8b07132f659597da04ee9884eda80ccc8991a5694ba3559be752db00c8077672` and
  semantic digest was
  `24d0e954791747457beccd0d37b974edc0bc83fe7a3e9d7f445730cf80b2fe8b`.
  The bounded failure body validated against the exact manifest, authority,
  config, canaries, providerRelay, bindings, permissions, redaction, and
  attempt ordering. Failure receipts correctly report `collected:0` and
  `passed:0`; this is validation of the failed result, not a passing S00
  evidence result.
- Cleanup removed the runner's task-labeled containers, networks, volumes,
  provider staging, run directory, disposable result, descriptor files, and
  both task image tags. Post-cleanup label checks were empty. The owner-only
  credential source and authoritative Plane/Hermes clones were untouched.
- Decision: S00 is `FAIL`; UT-020 is open. The first safe owner is the
  runtime/Hermes-to-Plane transcript-evidence ingress/readback seam. No source
  fix was made.

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

## 0AT — S00 live functional user-testing addendum

- Result: `PASS`. One fresh primary ran through the isolated runtime service and the real existing ChatGPT subscription using only `openai-codex/gpt-5.6-luna`; fallback was disabled. One exact same-invocation/same-idempotency-key replay ran only after the primary passed, with provider access disabled.
- Preflight: Plane was exact clean `577ab42b2712b78d96a46ac224f72005115f94f7`; Hermes was exact clean `bc7f13d2ab392752f2667b176c646339c49405f9`. Authority was `s00-live-0at-20260815`; permitted and denied canaries were `s00-0at-permitted-20260815` and `s00-0at-denied-20260815`. Manifest, authority, and config hashes were `077f6fc3a3d2be06ebd8c86c46984c621860bd4cdbcb8aed9155d72311255fd1`, `1ee5c9fe895779f643ab7056cee6d6e7f09ea3f726cc420186ecfda81742f72f`, and `649757463d9a72f35655be8ba23b29ec16478e00e7f863c2dfa33ccae0936c7e`.
- Lifecycle: one isolated workspace and one `G4 Live Issue`; run `6a0d0f49-098f-403d-b91e-b934d7b3f049`; invocation `invocation:0a2717b1-9db8-4399-a29a-a6641f960dbf`; outcome `outcome-submission:830be5e4-de4c-4948-a9d0-c37ab8fd3adb`; visible terminal `product-event:f12e8a0e-eb12-4f6d-bd63-8b07dd495d70`.
- Provider: exactly 10 attempts, ordered sequences `1..10`, all `completed`, upstream-initiated, status class `2xx`; no fallback or unknown attempt. Relay was `plane.agent-runtime/provider-relay/v1` over `AF_UNIX`, child network policy `none`, external egress owner `agent-runtime`, host gateway separate `true`, Hermes hook `integrated`.
- Operations: permitted Plane reads were `search_workspace` success `3` and `work_item.read` success `2`; `catalog.search` and `catalog.describe` were absent. Exactly one durable `agent.outcome.evaluate` denial occurred with `NOT_AUTHORIZED` and zero unauthorized side effect, followed by exactly one explicit `agent.outcome.submit` and one explicit `agent.outcome.publish`. There was one applied publication and one matching visible terminal. Audit event count was `18`.
- Gates: invocation and run succeeded; one visible outcome terminal and one applied outcome publication passed; terminal binding passed; `RuntimeExit.completed` passed at final sequence `22`.
- Transcript: actual assistant text was not observed. Evidence explicitly recorded `requirement=not_required`, `status=not_observed`, `count=0`, and `eventIds=[]`; no text was synthesized or inferred.
- Replay: passed with provider access disabled and all required deltas zero: provider attempts, children, invocations, receipts, audits, usage, outcomes, publications, terminal events, and semantic side effects.
- Evidence: result mode `0600`, size `8183`, SHA-256 `9dd5bdf263a01d06927e3a07961539f3c1dca51c4a05a713899c803c8c5fac8e`; semantic digest `c8aa562cff351c86863098df47ed145df829b8c486ec1a7b6eee9eeb033d0807`; standalone validation passed.
- Cleanup: all disposable result, descriptor, credential-staging, run, image, container, network, and volume artifacts were removed. Owner credential and authoritative clones were untouched. No source/config/test changes were made after the result. S00 is clean; W/M/O are unlocked.

## Current campaign reconciliation — PF1 and O02 — 2026-08-15

- Current exact candidate: Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`; Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`. S00 remains clean from Wave 0AT at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` / Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`: ten ordered upstream `2xx` attempts, required reads, exact denial, submit, applied publication, matching terminal, `RuntimeExit.completed`, zero replay semantic deltas, and cleanup passed.
- Provider-free PF1 support passed unchanged for Worker W01–W08 (35 real Django/API/DB/CLI/socket/isolation tests), Manager M01–M08 (33 tests after Plane `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1` and `2105fb9e21687103939a77b7e26a0959f1d50f51`), and tested Operator contracts O01 and O03–O09 (with Plane `8c9b20bf544355b20b0c9e69b0ad1ee5b48e905e` and `76e26ce5de1f300eab93505a2c885b984f60fcd0`). PF1 does not make W/M routes clean; the final exact-image red team remains pending.
- O02 is clean from the real external-client product journey at Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`: read, update, replay, archive, unarchive, search, delete, denial, durable audit/idempotency, unsupported-before-HTTP, stable bindings, SDK bearer identity, result bounds, and cleanup passed. MCP archive/unarchive fix `b9581fc71dbab8d408d196a237c109e9cd61e153` is included in that evidence.
- Initial provider-backed W/M/O tasks stopped without route claims because the accepted live runner hardcodes the S00 Worker and prompt. A typed scenario input is being added to that existing runner before the live routes resume; no W/M/O result is inferred. Final image/G4/Sol remain pending, and G5 is out of scope.

## Wave 0AU — exact ca4237d1 / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `ca4237d17e0da87fe7aeb2a7aa3cb8427296cb44`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-ca4237d1`, digest `sha256:300ced0857e1e0d1ae79a01e2ff74d9bd3d05690521361c23f45321aac4fe99b`; runtime image was `plane-agent-runtime:g4-v6-ca4237d1`, digest `sha256:842f382d35dbc4ae19f9bac465d003b9ffca7d0186561c761ffbdd3fc23d2319`. Manifest SHA-256 was `24286e4770115ef102e558c7b1bf07d84c944bbd6d648f1280b160bf1c4dd954`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. Run `95b61d42-45b4-45f4-9f78-744a37be2ac6` and invocation `invocation:f189286e-125b-4c64-a96a-4489a4f6a522` ended `failed` with non-retryable `budget_exhausted` at the API-invocation boundary.
- Bounded operation readback recorded `search_workspace` success count `5`, `catalog.search` success count `2`, `catalog.describe` success count `1`, and one `work_item.read` denial with `NOT_AUTHORIZED`. `agent.context.read`, Code Mode, `work_item.rename`, evaluator denial, submit, publish, terminal outcome, and replay were not reached; no semantic mutation or publication is claimed. The exact provider result is retained owner-only at `tmp/persona-wave-v6/worker-live-ca4237d1/result.json`, mode `0600`, SHA-256 `d4952fc8435099eefde37f9bbc8e11b7b0d6594f15af84f2b4de9ef9ab2090`.
- Root cause: the live Worker descriptor stated the goals but did not bind the typed search-to-read handoff. The model repeated discovery and supplied a non-canonical reference shape. Existing Plane tests already proved that `search_workspace.workItemReadInput` is the authorized raw-UUID input for `work_item.read`; no gateway or Hermes source fault is claimed.
- Fix commit `a46bc09abc` adds a reusable exact sequence, unique-title bounded search, verbatim `workItemReadInput` handoff, raw-UUID guidance, and regression assertions. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.

## Wave 0AV — exact 89f05859 / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `89f058590ef5f40292999ec8bda6354450874404`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-89f05859`, digest `sha256:edb0970534ac40d6910cbc724e347db0e1750d3daff32ee7c476c7e6068fd00e`; runtime image was `plane-agent-runtime:hermes-bc7f13d2-g4-v5`, digest `sha256:d3bff36256b3727a8c5650687ad16709356f95913841b0764f9c118a8650f976`. Manifest SHA-256 was `2d97bdc3f84e4e09545de377fd2cc2872beb90e59496b481a6a160ede710fcfe`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. Run `6af22d37-683c-409c-83a8-1975642eee96` and invocation `invocation:d3ee46f1-4c1e-4338-acda-595b8a80fcb6` ended `failed` with non-retryable `runtime_error / host_operation_failure` at final sequence 25.
- The immutable failure projection retained host operation `catalog.describe`, `UNKNOWN_OPERATION`, attempt `operation-attempt:f1bae9c9-08a3-4786-aa3d-b3dc8cd3775f`, and receipt `audit-receipt:72ace551-bfa5-4caf-a872-2cf5aa12d01d`. The bounded audit readback showed successful `search_workspace` count `1`, `work_item.read` count `1`, `catalog.search` count `1`, and `catalog.describe` count `3` alongside the failed attempt; no route evidence, complete scenario gate, Code Mode callback, mutation, evaluator denial, outcome, publication, or replay was retained. The exact result is retained owner-only at `tmp/persona-wave-v6/worker-live-89f05859/result.json`, mode `0600`, SHA-256 `1702644ee843596fd63b7d269d83b0f8bca8f982324599ce27be4f6ae5195fed`.
- Root cause: the Worker descriptor did not bind the catalog's exact nested input shape. Existing Plane schema requires the field `operation_id` and the complete value `agent.context.read`; `operationRef` and `operation:agent.context.read` are not valid `catalog.describe` inputs. No gateway or Hermes source fault is claimed.
- Fix commit `a43f124285` adds the exact JSON input and regression assertions. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.

## Wave 0AW — exact b06fe7aa / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `b06fe7aa8b45b89c5b651789c32114f299875808`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-b06fe7aa`, digest `sha256:d1dded90ce315c5d057438fa7bef518b307e3bcce2078129fdcfcd084a5a8a3b`; runtime image was `plane-agent-runtime:hermes-bc7f13d2-g4-v5`, digest `sha256:21b39567ab484a45ab9f260bd15e8e5ccd0a6c488a9b2b488f3c7c0421f2dca1`. Manifest SHA-256 was `19bf8001ea8010d67f129e3fcb36b200eb20e6ec44d3dfb5ccf488d36833b08c`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. Run `ecd74260-e94e-40ad-a26c-bc328bdf8e06` and invocation `invocation:bfbcbe25-7d5d-4910-82bc-2daaf8668264` ended `failed` with non-retryable `budget_exhausted` at final sequence 25.
- Bounded audit readback recorded successful `search_workspace` count `1`, `work_item.read` count `1`, `catalog.search` count `2`, and `catalog.describe` count `1`. It recorded no `agent.context.read`, Code Mode callback, `work_item.rename`, evaluator denial, submit, publish, complete scenario gate, or replay. The exact result is retained owner-only at `tmp/persona-wave-v6/worker-live-b06fe7aa/result.json`, mode `0600`, SHA-256 `65b15a23ba880e7b9afce75bfd8f23bdf9bb0c9b2f357da8c0da6e9503ea66c0`.
- Root cause: the descriptor named `agent.context.read` but did not bind its strict nested input strongly enough; the model spent the finite budget after discovery/read without creating the context receipt. No gateway or Hermes source fault is claimed.
- Fix commit `113a67fb76` adds the exact substituted `{"subject_user_ref":"{{subjectUserRef}}"}` input and regression assertions. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.

## Wave 0AX — exact acc770f2 / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `acc770f25e5f1796656cf70c17ee615d7f65220b`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-acc770f2`, digest `sha256:26d9d0c8302648a8757ac51db95c3902d2b74b77cb76364fa2b80cee0fde1776`; runtime image was `plane-agent-runtime:hermes-bc7f13d2-g4-v5`, digest `sha256:8c52ab80fe0b6c17499c16d5cad9ed565ba9e4c0d8e126f8868175907b2dfa06`. Manifest SHA-256 was `8878f8818d046b00ddde79776e15b88f2964c41132aa914b20054945e52ab60e`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. Run `d154de5a-ccc0-4522-91a5-b37df244d3d2` and invocation `invocation:6c48f615-8ade-4ad7-b2de-2b5f647c85ed` ended `failed` with non-retryable `budget_exhausted` at final sequence 24.
- Bounded audit readback recorded successful `search_workspace` count `1`, `work_item.read` count `1`, `catalog.search` count `1`, and `catalog.describe` count `1`. It recorded no `agent.context.read`, Code Mode callback, `work_item.rename`, evaluator denial, submit, publish, complete scenario gate, or replay. The exact result is retained owner-only at `tmp/persona-wave-v6/worker-live-acc770f2/result.json`, mode `0600`, SHA-256 `a696ec4eb8c6aecd75557f90abeb4ab7393b8f8944dbe1b4934814595fabe3e2`.
- Root cause: the descriptor had exact input prose, but no explicit eager presentation through Plane's adaptive tool-disclosure owner; the universal eager workspace search remained the model's most salient first tool. No gateway, authorization, or Hermes source fault is claimed.
- Fix commit `1dcf284cc7` adds the typed profile presentation field, passes it through the established `create_profile` seam, and eagerly presents catalog, context, read, rename, evaluator, submit, and publish schemas. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.

## Wave 0AY — exact a0c3854e / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `a0c3854e5d4d9d8e46fa07e165b01a972d60bc41`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-a0c3854e`, digest `sha256:a50ebdb2c56d70e66389d765fd2a5674e58a733c396253e5bffad104b531c466`; runtime image was `plane-agent-runtime:hermes-bc7f13d2-g4-v5`, digest `sha256:d8d17937cb0b6efd3a1615f0a9797a2b7c0592e7ed23c4c26436677de4313e1f`. Manifest SHA-256 was `60391c06ea49e2c34130d8cb255b1d7d751ce8c66e9794b19d0c0a09c4719f1e`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. The bounded run `a3a32d07-35bc-4488-90eb-6b8ccf95e2fe` and invocation `invocation:c83d4760-0328-41cd-95ba-31ff1d549a5c` ended `failed` with non-retryable `budget_exhausted` at final sequence 23.
- Bounded audit readback recorded successful `catalog.search`, `catalog.describe`, `search_workspace`, and `work_item.read` operations, but no `agent.context.read`, Code Mode callback, `work_item.rename`, evaluator denial, submit, publish, complete scenario gate, or replay. No semantic mutation or publication is claimed. The exact result is retained owner-only at `tmp/persona-wave-v6/worker-live-a0c3854e/result.json`, mode `0600`, SHA-256 `df2aae47df54da5967cd347813b95705c3e69c0fdaacb41ca64c7ef4187c639a`.
- Root cause: the explicit route was eagerly exposed through the existing profile presentation seam, but `search_workspace` remained first in the composed catalog. The model selected the universal work core before the route-specific context/mutation sequence and exhausted the finite budget. No gateway, authorization, Hermes, or provider fault is claimed.
- Fix commit `c0890279c1` orders explicit eager Worker operations before the universal work core and adds a focused API regression. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.
- Workflow correction: two malformed launch-path attempts exited `127` before runner/provider access and consumed no provider attempts. `e8d861d02a` adds `tools/agent-g4-live-launch.py`, which derives authority/config/descriptor/result paths from one owner-only run directory and validates all regular-file inputs before invoking the canonical runner; focused launch-path regressions passed.

## Wave 0AZ — exact 88ec3f3b / Hermes bc7f13d2 single fresh Worker

- Status: `FAIL`; W01-W08 remain `untested` at provider-backed route level. Exactly one fresh Worker primary ran. No fallback, retry, replay, second provider primary, broad verifier, rollout, deployment, UI test, or unrelated suite ran.
- Exact Plane source was `88ec3f3bedbcf289d4e34ce1ad6db2f4831af092`; Hermes was the required clean `bc7f13d2ab392752f2667b176c646339c49405f9`. API image was `plane-agent-api:g4-v6-88ec3f3`, digest `sha256:aaea613b0035cb95a5385b4e2a6c8a10f0d1219a3d1ca979ec2a58fc06e5992f`; runtime image was `plane-agent-runtime:hermes-bc7f13d2-g4-v5`, digest `sha256:9da4f110acc8b8d7a361b1b2cbde1d782b4e038dfa29b39985d97a4244bf0e0c`. Manifest SHA-256 was `4158b1e12c6f97946a4f68e15a5e205709a850b5e4002740c36dfff7308d3b45`; descriptor SHA-256 was `fb7d60735ff018f050baeb38d495ea9d83da39a5eb07bb5857069abb64afd4a4`; config-only validation passed before provider access.
- Provider binding was the required `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback disabled, max 16 calls, through the existing validated relay. All 16 attempts were completed, upstream-initiated, and `2xx`; no fallback or unknown attempt occurred. Run `4f4fa5b3-1e88-4631-9849-98431fe03613` and invocation `invocation:3b7a8ee9-4ef3-4b6f-a469-a1254327c107` ended `failed` with non-retryable `runtime_error / host_operation_failure` at final sequence 24.
- The bounded failure retained `catalog.describe`, `UNKNOWN_OPERATION`, attempt `operation-attempt:d515ed05-b826-405f-9307-69e233272840`, and receipt `audit-receipt:51aafeab-e3a8-4c5e-b3f8-86a47a0ae888`. Audit readback recorded successful `search_workspace` count `1`, `work_item.read` count `1`, `catalog.search` count `1`, and `catalog.describe` unavailable count `3`; no `agent.context.read`, Code Mode callback, `work_item.rename`, evaluator denial, submit, publish, complete scenario gate, or replay was retained. The exact result remains owner-only at `tmp/persona-wave-v6/worker-live-88ec3f3/result.json`, mode `0600`, SHA-256 `cf54d308349e78b85d075e4d8fa6f0c45a2f362d36b2fb8565009fb7d10a774f`.
- Root cause disposition: the exact bounded fact is catalog target resolution failure. The built API artifact independently registered `catalog.describe` and `agent.context.read`, and a no-provider image check successfully described the context operation. The retained result intentionally omits raw model input; the non-secret model-facing inference is that the model confused the catalog row's `operationRef` with its `operationId` when filling `catalog.describe.operation_id`.
- Fix commit `969337e948` projects the next route operation's exact `operationId` into the reusable route guidance and explicitly tells the Worker to copy `operationId`, never `operationRef` or an `operation:` prefix; descriptor and route-guidance regressions passed. A new exact-image rebuild and fresh Worker primary are required before any W01-W08 route claim or replay.

## Wave 0BA diagnosis addendum — exact ca42e598 / Hermes bc7f13d2

Root-fix source checkpoint: Plane `4cba0fd647`; the documentation checkpoint
records this diagnosis without changing the retained receipts.

- Two independent fresh Maya identity commissions reached the required
  `openai-codex/gpt-5.6-luna` route with fallback disabled. Each retained nine
  completed upstream `2xx` provider attempts, succeeded run/invocation state,
  `RuntimeExit.completed`, one visible terminal, and one applied publication.
  Neither old commission was replayed or continued; later commissions were
  not started.
- The exact owner-only receipts remain dirty evidence:
  `tmp/persona-wave-v6/worker-live-de9189b5/result.json` mode `0600`, SHA-256
  `dc0c1cbe9ff0e71e630db320e86c5bd1ce631b63c329db0928200b5fbbcc7edb`, and
  `tmp/persona-wave-v6/worker-live-ca42e598/result.json` mode `0600`, SHA-256
  `c798cfa136000d7dd37084ac2c3c3f8d89280075112227979693a6c357aa9004`.
- Both final receipts were labeled `outcome_unknown / provider_relay /
  upstream_result_unavailable / reconciliation_required`, but the durable
  attempt rows were all completed. The later local identity scenario-gate
  failure was therefore misclassified by the invoker's fallback that treated
  any upstream-started attempt as unknown. No external/provider prerequisite
  is established, and W01/W02 remain dirty pending a fresh post-fix primary
  and eligible replay.
- Independent runtime tracing found a second local race: bounded provider
  response delivery and required terminal audit could finish on daemon relay
  handlers while the runtime closed the Plane host callback first. The root
  fix buffers the bounded upstream body before completed audit, gracefully
  drains relay handlers, force-classifies unresolved started calls as terminal
  unknown, performs a second forced-path drain, and preserves late audit
  failure across dispatch cleanup. Focused provider-free owner regressions
  must pass before a fresh provider commission.

## Wave 0BB — exact f63f2c2e / Hermes bc7f13d2 callback-binding checkpoint

- Status: `HOLD`; W01/W02 remain dirty. One fresh identity commission reached
  the required `openai-codex/gpt-5.6-luna` route with fallback disabled and
  persisted 12 completed upstream `2xx` attempts. Its run and invocation
  succeeded and it retained one visible terminal plus one applied publication,
  but the runtime later failed at `agent.outcome.submit` with
  `CALLBACK_BINDING_INVALID` after the model supplied a conflicting redundant
  payload `run_ref`. The owner-only result remains
  `tmp/persona-wave-v6/worker-live-f63f2c2e/result.json`, mode `0600`, SHA-256
  `ff7776421e278ee560c26d42b1c5a0e072e7bf6829399754085deaed8ccbc9d4`; it was
  not replayed or continued.
- Plane fix `8681f2e7dbb652bff27c4374c47638f5f65dc6df` keeps the callback
  envelope's run/invocation identity fail-closed, normalizes redundant model
  payload `run_ref` to the bound run, runs catalog/binding/budget/cancellation
  preflight before terminal observations, returns exact duplicate submit as a
  replay-only success, returns different terminal submits and late semantic
  mutations as wire-valid `conflict / PLANE_CONFLICT`, and blocks mutations
  after `OUTCOME_UNKNOWN`. The focused G2 wire contract passed `2/2`; the
  provider-free live/tool contract suite passed `143/143` before this small
  guard amendment, and the amended G2 contract passed `2/2`.
- The exact pinned Hermes checkout remains clean at
  `bc7f13d2ab392752f2667b176c646339c49405f9`. Its current
  `HostCallResult` disposition table treats `conflict / PLANE_CONFLICT` as a
  poison invocation; the matching Hermes owner change to treat this expected
  terminal conflict as an ordinary nonfatal tool result is not integrated.
  No image was rebuilt and no provider attempt was spent after this finding;
  a fresh primary and eligible replay wait for that exact Hermes commit.

## Wave 0BC — exact 579d5f04 / Hermes cc3e444e bounded Worker attempt

- The authoritative clean Hermes checkout is now
  `cc3e444ee25e6c19fee77b6e1fbe3d95aef1a3ea` (parent `bc7f13d2...`). Its owner
  checks passed: 44 tests plus 9 subtests in the incremental persistence and
  host-port suites. The focused Plane owner suite passed 58 tests, including
  the wire-valid exact-replay/conflict contract and the unknown-state mutation
  guard.
- Final artifacts were built from Plane `579d5f045d0419ce3444cd9288acb63a20f93611`:
  API `plane-agent-api:g4-v6-579d5f04`, digest
  `sha256:458fbd165c59704a9853fa4001463dbf8ef3ada2ffcde8e85f42c9f4bd4650a3`;
  runtime `plane-agent-runtime:hermes-cc3e444e-g4-v6-579d5f04`, digest
  `sha256:35c329ca3272ca14b5b5f360fb614615134b7e9db76016a25d539edac6832cb9`;
  manifest `tmp/plane-agent-g4-disposable-579d5f04.json`. MCP and SDK were
  `c04974ed6624f17b41e63ef8182661929e77e0d3` and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The launch helper and
  config-only/descriptor preflights passed.
- One fresh Maya Agent/profile run was launched with exactly the three
  commission descriptor, GPT-5.6 Luna xhigh, fallback disabled, and the
  existing authorized subscription. Commission A reached the provider and
  persisted 11 completed upstream `2xx` attempts. Its Plane lifecycle was
  durable-successful: run `338cbce5-3b9d-43f3-96a2-5e95b6dcbb46`, invocation
  `invocation:33784bd9-74ae-45cf-a462-f1a0f89c05db`, RuntimeExit completed at
  sequence 21, one exact `NOT_AUTHORIZED` evaluator denial, one submit, one
  applied publication, one visible terminal, and the terminal/run/invocation
  bindings matched. Commission A then failed locally before route evidence
  and replay when the W08 readback probe requested limit 8 and exceeded
  Plane's established 8-KiB bounded readback projection. Commissions B/C
  did not start; replay was not eligible and was not attempted.
- The first helper correction to request limit 1 was insufficient because the
  content-bearing full admin projection still exceeded the 8-KiB ceiling. The
  reusable helper is now narrowed to the established limit-1 correlation
  readback owner, and `_run_single` invokes it only for commissions owning
  W08; focused regressions cover both boundaries. The focused provider-free
  tool suite previously passed `136/136`, and a new exact-image build plus
  fresh three-commission primary are required.
- Owner-only result: `tmp/persona-wave-v6/worker-live-579d5f04/result.json`,
  mode `0600`, SHA-256
  `ad476f7bd45ea25e34c77e0b33d375a94288c82cdaaa8ee96a29dc3200a08c2d`.
  Canonical validation passed. The retained f63, ca42, de9189, and 579d5f04
  receipts are dirty evidence; none was replayed or continued.
- The second fresh owner-only result is
  `tmp/persona-wave-v6/worker-live-82b468de/result.json`, mode `0600`, SHA-256
  `b472d81bc7c5b9b1a17f7cfd8cfa26462e7cc7608f72cfe8cb9751f7244712e7`.
  It persisted run `09fc4b0c-3d42-4677-8843-53a4a50c08eb`, invocation
  `invocation:2e709c9c-f0d8-4cd3-b202-8286faeeecd2`, RuntimeExit completed at
  sequence 16, 7 completed upstream `2xx` attempts, the same exact denial,
  submit, publication, and terminal binding, then failed at the same local
  readback boundary. No replay or B/C commission ran.

## Wave 0BD — exact 1d4bf351 / Hermes cc3e444e bounded Worker attempt

- The fresh primary used Plane source `1d4bf3510120fe44634f84341efc342f5bb7f865`,
  exact Hermes `cc3e444ee25e6c19fee77b6e1fbe3d95aef1a3ea`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. API image
  `plane-agent-api:g4-v6-1d4bf351` had digest
  `sha256:19da3c9df6beba6f63cdaccfadd2933fb14ef2a6801cd43c6e6f6328ad236bfd`;
  runtime image `plane-agent-runtime:hermes-cc3e444e-g4-v6-1d4bf351` had
  digest `sha256:2fd954fa8b7e19faa7b76ea30f7ba72716bb02e8de4ff0898a9c278490825488`.
  The disposable manifest was
  `tmp/plane-agent-g4-disposable-1d4bf351.json`, SHA-256
  `0b5b7931bea773e8855f326c6395e04680be8e09fc306bd9b6ac01c1c7ac138a`,
  mode `0600`; the owner-only run directory was mode `0700` and its result
  mode `0600`.
- One fresh three-commission Maya descriptor was launched through the
  canonical derived-path helper with `openai-codex/gpt-5.6-luna`, xhigh
  reasoning, fallback disabled, and the 16-call bound. Commission A reached
  13 completed upstream `2xx` attempts with no fallback or unknown attempt.
  Run `88412be2-9b33-4f28-b1e4-1ffe59cc0911` and invocation
  `invocation:5db7def4-df61-4768-9426-e8a5c3d78206` reached the explicit
  submit/publication lifecycle and one exact `NOT_AUTHORIZED` evaluator
  denial. RuntimeExit failed at final sequence 23 with bounded
  `budget_exhausted` / `model_call_budget_exhausted` after publication.
- The pre-fix scenario projection queried `OperationGatewayPublication`,
  which is the delivery-intent table for activity/notification/webhook work,
  and therefore reported publication `0` despite the validated explicit
  outcome publication receipt/audit/product-event binding. Plane fix
  `adff362456` now reuses that existing explicit-publication projection for
  scenario and replay readback. This receipt remains dirty; the provider-
  disabled replay was not attempted, and commissions B/C did not start.
- Owner-only result: `tmp/persona-wave-v6/worker-live-1d4bf351/result.json`,
  SHA-256 `f810b3c05a155ea6344ee97f377ddd57a23805d0d65f0ce8d92c7f91313e8ea3`.
  Canonical validation passed. Cleanup passed, and no provider retry was
  spent after the receipt. The separate Hermes terminal-action/budget owner
  fix is required before a fresh primary.

## Wave 0BE — exact 1d002581 / Hermes f8cda105 identity verification

- This checkpoint used Plane artifact source `1d0025816b`, host-side harness
  commits `1d0025816b`, `45e6f1f9b4`, and `b4c05d9b93`, exact Hermes
  `f8cda105e3e14ace7c12f4840ec86c036fade9ad`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Existing API image
  `plane-agent-api:g4-v6-1d002581` digest
  `sha256:ea08468fcef3f29c24500cc1141751e944a548fa5aef000db8776ed2a7cd400c`
  and runtime image
  `plane-agent-runtime:hermes-f8cda105-g4-v6-1d002581` digest
  `sha256:1aeebc3ad85469ff495e8fc1a36495cbcac487ba8d213c2b57a535654e1c4472`
  were reused without rebuilding. The disposable manifest is
  `tmp/plane-agent-g4-disposable-1d002581.json`, mode `0600`, SHA-256
  `731a29b69a9722ba184e9e58ac2c26a318742289776f29bc45f8742f48e9bc40`.
- The earlier `worker-live-1d002581` receipt retained a coherent completed
  provider/lifecycle segment: 9 upstream `2xx` attempts, all seven expected
  operations exactly once, one exact `NOT_AUTHORIZED` denial, one applied
  publication/terminal, `RuntimeExit.completed`, and the bounded Hermes
  `hermes.terminal-lifecycle/v1` observation. The local wrapper failed while
  parsing an unowned empty W05 projection, before identity substitution,
  route readback, or eligible replay. `45e6f1f9b4` fixes that commission
  scoping; the receipt remains dirty and was never replayed.
- One fresh corrected identity primary then ran with
  `openai-codex/gpt-5.6-luna`, xhigh reasoning, fallback disabled, and the
  16-call bound. Its owner-only result is
  `tmp/persona-wave-v6/worker-live-45e6f1f9/result.json`, mode `0600`,
  SHA-256 `ee2981b521b95f2d4814d6bd2c361f7fa8b436e35c8fa0fb2769b9f20b46902`.
  The first upstream-started attempt terminated as bounded
  `outcome_unknown / provider_relay / upstream_result_unavailable /
  upstream_channel_closed`; no terminal-lifecycle observation, route
  evidence, or replay was retained. This is not the earlier completed-2xx
  invoker misclassification, but it does not yet prove an external
  prerequisite. No provider retry, fallback, replay, or B/C commission ran.
- Canonical result validation passed for the retained receipts. Focused
  provider-free tools tests passed `148`; the focused Plane owner suite passed
  `58/58`; `bash -n tools/agent-g4-live.sh`, `git diff --check`, and the
  redacted `gitleaks` scan passed. Disposable Docker resources were cleaned
  and the focused compose project had no remaining containers.

## Wave 0BF — exact 1d002581 / Hermes f8cda105 W01-W02 closure

- Before this primary, the prior `worker-live-45e6f1f9` invocation was
  reconciled from Plane-owned evidence: run
  `ecb6689e-1890-4eac-bbc2-6ce0dfbcffb2` and invocation
  `invocation:73472170-618f-426c-98ad-909b52be93cb` were terminal failed, with
  one visible unavailable failure terminal, no runtime exit, no host receipts,
  all seven gateway operation audits absent, zero outcome/publication/terminal
  counts, and no artifact-bearing outcome. That unknown invocation was never
  replayed. The focused relay/lifecycle owner suite passed `58/58` and its
  disposable stack was removed.
- One deliberate fresh AssignmentContract/RunAttempt then used the existing
  API image `plane-agent-api:g4-v6-1d002581` digest
  `sha256:ea08468fcef3f29c24500cc1141751e944a548fa5aef000db8776ed2a7cd400c`
  and runtime image
  `plane-agent-runtime:hermes-f8cda105-g4-v6-1d002581` digest
  `sha256:1aeebc3ad85469ff495e8fc1a36495cbcac487ba8d213c2b57a535654e1c4472`,
  without rebuilding or refreezing. Hermes was
  `f8cda105e3e14ace7c12f4840ec86c036fade9ad`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The manifest remained
  `tmp/plane-agent-g4-disposable-1d002581.json`, mode `0600`, SHA-256
  `731a29b69a9722ba184e9e58ac2c26a318742289776f29bc45f8742f48e9bc40`.
- The owner-only result is
  `tmp/persona-wave-v6/worker-live-45e6f1f9b/result.json`, run directory mode
  `0700`, result mode `0600`, SHA-256
  `4aab33d7e5c3eb577ccbd15d17a993132698a5dfc87016c85134b127c85cd53d`.
  Descriptor SHA-256 is
  `faa01a8eda57838e6d4af85f9a82ef0b818121c3e2b262a0d199468c2cbd35c8`.
  Durable run/invocation refs are
  `run:2798ed55-a557-411e-baf2-0d4d8c5b2ddf` /
  `invocation:d9140ee4-8e74-4295-9231-805b5867573b`.
- GPT-5.6 Luna xhigh ran with fallback disabled and produced 9 completed
  upstream `2xx` attempts. `catalog.search`, `catalog.describe`,
  `search_workspace`, `work_item.read`, `agent.outcome.submit`, and
  `agent.outcome.publish` each succeeded exactly once; the one
  `agent.outcome.evaluate` call was denied exactly as `NOT_AUTHORIZED`.
  W01 substitution was denied with zero side effects; W02 ordering, bounded
  read/search, and hidden-object exclusion passed. One applied publication and
  one matching `outcome_submission` terminal were read back, with
  `RuntimeExit.completed` and the bounded
  `hermes.terminal-lifecycle/v1` observation (`terminal_armed=true`).
- The eligible same-invocation provider-disabled replay passed with
  `sameIdempotencyKey=true`; new children, provider attempts, invocations,
  receipts, audits, usage, outcomes, publications, terminal events, and
  semantic side effects were all `0`. Canonical validation passed after
  `6087b791a4` recognized the established bounded observation-profile alias;
  focused tools tests passed `149`. No fallback, additional primary, B/C
  commission, or broad verifier ran. Docker cleanup and final worktree checks
  passed.

## Wave 0BG — exact 8dae97f4 / Hermes f8cda105 standalone B stop

- The provider-free catalog owner fix was committed as
  `8dae97f4abc060b8a4023afea79ec768f4350ba0`. The exact candidate API image
  was `plane-agent-api:g4-v6-8dae97f4`, digest
  `sha256:e74be5de63d87d9ab84ac115598a82b81e94a01b27a0502eaebf547754ade412`;
  the exact runtime image was
  `plane-agent-runtime:hermes-f8cda105-g4-v6-8dae97f4`, digest
  `sha256:c369d04714c2dc6d81a79db76c0e1409c16b8060ad245a71c963a3e0b7c89fb8`.
  Hermes was `f8cda105e3e14ace7c12f4840ec86c036fade9ad`, MCP was
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK was
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The disposable manifest was
  `tmp/plane-agent-g4-disposable-8dae97f4.json`, mode `0600`, SHA-256
  `66a2dcd896051e1a0f9c1f9087a6012e4b1bf1463097568e04b7067a2a37db44`.
- One fresh standalone B run directory was derived by the owner-only launch
  helper with mode `0700`; its descriptor was mode `0600`, SHA-256
  `8978a65e75377dae67824c35de2d200cfdaecd6afba20ab1785a2277eb6b94bd`.
  It used only a fresh synthetic Plane fixture and bounded public operation
  schemas; no existing object, user text, memory, skill package, environment,
  auth material, or secret was hydrated into provider input. A relative-path
  launcher preflight was rejected before execution; the corrected
  absolute-path launch created the one authorized provider primary. No
  fallback was used.
- The primary persisted run `5751be56-00ef-46b8-8728-11f3af2fc264` and
  invocation `invocation:31ae2052-556c-416f-b94a-b3f818678d5b`. It recorded
  exactly 16 completed, upstream-initiated provider attempts, all `2xx`, with
  no fallback or unknown attempt. The run and invocation rows were
  `succeeded`, but RuntimeExit was `failed` at final sequence `29` with
  non-retryable `budget_exhausted` / `model_call_budget_exhausted` after the
  finite 16-call allowance. The bounded lifecycle observation retained
  `hook_installed=true`, no terminal action observed, API/provider counts
  `16/16`, max/used/remaining budget `16/13/3`, and exit mapping
  `unknown -> max_iterations_reached`.
- Redacted operation readback observed one `search_workspace`, one
  `work_item.read`, two `catalog.search`, four `catalog.describe`, one exact
  evaluator `NOT_AUTHORIZED` denial, and one successful
  `agent.outcome.submit`; `agent.outcome.publish` was absent. There was one
  visible outcome terminal but zero applied publication/product-publication
  records, so W03/W04/W07/W08 did not pass and no provider-disabled replay
  was eligible. Owner-only result:
  `tmp/persona-wave-v6/worker-live-8dae97f4-b7/result.json`, mode `0600`,
  SHA-256 `fa7b274b0540cf1570d4b272ee8f2be0fdca6ffe7e08e4ac0e7496ab471eb3f5`.
- This is a functional runtime capability finding, not a prompt-only retry
  and not an external provider prerequisite. The pinned Hermes runtime's
  established `execute_code` path is Python PTC; it is not the required Plane
  restricted TypeScript Code Mode bridge. W04 therefore remains blocked, and
  W03/W07/W08 remain dirty because no complete route evidence, publication, or
  replay was proven. No C descriptor was launched and no C provider input was
  created. Further B/provider work is held for the integrated Plane/Hermes
  TypeScript bridge commits and `b533c10fc7`; no route was retroactively made
  clean.
## Wave 0BH — exact 713fb8c685 synthetic W05-W08 primary

- One fresh synthetic-only C context-governance commission used Plane
  `713fb8c685c7298cbb7fdd2b3fe965c60ba413e9`, exact Hermes
  `f8cda105e3e14ace7c12f4840ec86c036fade9ad`, GPT-5.6 Luna xhigh, fallback
  disabled, max 16, and the host-only provider relay. It created only a new
  disposable synthetic workspace, users/Agents, issue, memory, preference,
  skill, and exclusion canaries.
- The retained owner-only result is
  `tmp/persona-wave-v6/context-governance-primary-receipt/result.json`, mode
  `0600`, SHA-256
  `2bfa9d0f9518226dcd248d9b14e24bed178e458f46862c7aa24d40e6c889aade`.
  Run `160011e2-f0af-4758-8199-88650d20b2d2`, invocation
  `invocation:542c9b59-dd06-4a2e-909a-fb2b8729bf40`, outcome
  `outcome-submission:6659a17e-d2fb-4970-a001-6d8db0329545`, and terminal
  `product-event:f927cf01-156d-4781-9454-9467a21ff35c` were retained. There
  were 9 completed upstream `2xx` attempts, no fallback, no unknown attempt,
  a passed lifecycle gate, one applied publication, and completed runtime
  exit. The scenario gate failed only `operation:agent.context.read`: actual
  success count was 2 instead of 1. No replay ran.
- Provider-free root correction `c7e41e85df` strengthened ordered route
  guidance and explicitly made one context response complete; the focused
  tools tests passed `57/57`.

## Wave 0BI — exact c7e41e85df post-fix W05-W08 primary

- The single deliberate fresh post-fix C reused the synthetic-only scope and
  ran on rebuilt API `plane-agent-api:g4-v6-c7e41e85`, digest
  `sha256:f6afa1836f41ce912ae57df27744253f43e778ef0920789abde38800e0b31132`,
  and runtime `plane-agent-runtime:hermes-f8cda105-g4-v6-c7e41e85`, digest
  `sha256:fbef6225ef6297f60c018355ea5ad83cacda4418c4120755bc285a771907a662`.
- The retained owner-only result is
  `tmp/persona-wave-v6/context-governance-rerun/result.json`, mode `0600`,
  SHA-256
  `f380048cdb0be65806fd557b828851daa36ed2fe10eb10479ca743bbac7a1196`.
  Run `197624b5-e1f7-4087-a789-f858f5e85739`, invocation
  `invocation:d435fa62-e476-48d0-a129-df2a00864a76`, outcome
  `outcome-submission:15b0b98b-0bf2-4407-9902-a19a13cacf28`, and terminal
  `product-event:2256a307-1732-45c1-ba4e-037e01847553` were retained. There
  were 7 completed upstream `2xx` attempts, no fallback, no unknown attempt,
  exactly one `agent.context.read`, exact catalog/context/submit/publish
  counts, one applied publication, one visible terminal, and
  `RuntimeExit.completed`. The local route gate failed only `route:W07`:
  the outcome did not carry the required artifact. No replay ran.
- Provider-free root correction `62fd6193a0` now requires exactly one
  artifact and exactly one evidence item in the canonical commission and
  regression. Focused tools tests remained `57/57`. Final exact attestations
  were built without another live run: API
  `plane-agent-api:g4-v6-62fd6193`, digest
  `sha256:89a6b406a12965958e550d6520a97a21935fe8d86b8c058cf372c3586f73d575`,
  and runtime `plane-agent-runtime:hermes-f8cda105-g4-v6-62fd6193`, digest
  `sha256:b050fbf8343f2945a2a4991ff8971e9653a0e0b141d5d623c8a7533120d77620`.
- Both isolated Compose runs cleaned their containers, networks, volumes,
  provider staging, and runtime resources. W05-W08 remain dirty because no
  primary passed the full route plus replay gate; W03-W04 were not run.

## Wave 0BJ — exact 7a6983ed68 / Hermes 292e866374 fresh B failure

- Manager root fix `e3628d6f457fdb4ac5ee0e649d88f4d566bdbb72` integrated; the
  container-safe focused regression landed as `7a6983ed68`. Combined host
  checks passed `163/163`; the migration-backed Manager regression passed
  `1/1` using the read-only mounted route fixture.
- Final exact artifacts: API `plane-agent-api:g4-v6-7a6983ed` digest
  `sha256:c6ead3bfbbe96cfbabe3288e1f8605f55884a050da6f81cbac0b937be87d129b`;
  runtime `plane-agent-runtime:hermes-292e8663-g4-v6-7a6983ed` digest
  `sha256:10835bb00225e4869a857c67535e27f6df4e555819831a7df56f703cf2ccd3a9`;
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`.
- One fresh synthetic-only B primary ran with GPT-5.6 Luna xhigh, fallback
  disabled, max 16. It recorded 9 completed upstream `2xx` attempts, then
  failed at `CODE_MODE_FAILED` / `host_callback`; RuntimeExit was failed and
  non-retryable at sequence 17. Run `fd9e4584-a2f8-4614-8598-9a2a31cc8bb3`
  and invocation `invocation:ad9df00e-97db-41ae-aa48-22b70d4abb32` are
  retained in the owner-only receipt
  `tmp/persona-wave-v6/worker-live-7a6983ed-b3/result.json` (mode `0600`,
  SHA-256 `4eb7b8c7ed5fec3e542e4d573afc2d22567f380a7af0d947ad8988696e732345`).
- No `work_item.rename`, applied publication, complete W08 readback, or
  replay was proven. All labeled disposable resources were cleaned. UT-038
  is open; W03/W04/W07/W08 remain dirty and further provider use is stopped.

## Wave 0BK — exact c561bdfe89 / fresh launch commission-shape stop

- Integrated provider-free root fix `76ecdd120748c66e08cf07708e237291aace3e19`
  as Plane `c561bdfe89fb7413877b910900b5675b9f4b779d`. Focused verification
  passed: descriptor `53/53`, Plane cross-process `24/24`, Hermes bridge and
  host-port `8/8`, and migration-backed Manager `1/1`. Exact API/runtime
  refreeze used Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`; image
  labels, imports, and real bootstrap readiness passed.
- One fresh owner-only GPT-5.6 Luna xhigh launch ran with fallback disabled
  and max 16. Receipt:
  `tmp/persona-wave-v6/worker-live-c561bdfe-b4/result.json`, mode `0600`,
  SHA-256 `f0a9b26e18b8ab9034558638f4e67c24cc5bfd84d928ba1e5914c32e1c16ec33`.
  The current descriptor contains all three bounded Worker commissions, so
  identity ran first and passed with 11 completed upstream `2xx` attempts plus
  an eligible provider-disabled zero-delta replay. The mutation B commission
  then stopped before run/invocation creation with `runRef=unavailable` and
  zero B provider attempts. This is a commission-selection workflow failure,
  not live evidence of typed Code Mode behavior. No second primary, replay, or
  further provider use occurred; UT-039 is open and W03/W04/W07/W08 remain
  dirty.

## Wave 0BK follow-up — aggregate failure envelope reconciliation

- The retained raw receipt remains owner-only and unchanged. Its pre-fix
  aggregate wrapper copied the successful identity envelope, set aggregate
  status to `failed`, and omitted the failed commission's bounded failure
  fields; the B commission itself had no run/invocation/provider attempt or
  Plane semantic side effect.
- Provider-free fix `aef02407a4` now uses the failed commission's
  `plane-agent-g4/live-failure/v1` envelope for a failed aggregate, retaining
  both commission rows. The focused behavior regression constructs the
  aggregate and runs the canonical validator. The combined harness passed
  `149/149`.
- No provider retry, replay, image rebuild, or new disposable resource was
  created. W03/W04/W07/W08 remain dirty; UT-039 remains open.

## Wave 0BL — exact 8d94fcc1 / sequential Worker runtime failure

- Provider-free preparation integrated sequential-commission root fix
  `7029b52ca13e26bbd3d95d94bf382b39cf8f1d40` as Plane
  `8d94fcc16e5ff161b1e128fd3fd22f6a4f851071`. Host checks passed `180/180`.
  The migration-backed API clump passed `297` tests; 13 failures were retained
  as known environment-bound setup/test prerequisites (container repo-root or
  fixture mounts, runtime checkout mount, host CPU threshold, and Docker CLI
  unavailable inside the API test container), with no production source change
  made for them.
- Exact refreeze used API
  `plane-agent-api:g4-v6-8d94fcc1`, digest
  `sha256:428bdbab5945250fcd5ae3056f0a519cac8b0a0ecc8d03b948ecf26842abf752`,
  and runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-8d94fcc1`, digest
  `sha256:6feabe70129e61d9de9c11045180bd839ea709f9a3d2b390f417fc3de71988ed`,
  bound to Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`. Imports and the
  network-disabled real bootstrap passed. Manifest mode was `0600`, SHA-256
  `d8d0ee728974ca6847adb840240e59e44d0478735c25a97e5320b674a09748f5`.
- One fresh full descriptor journey used GPT-5.6 Luna xhigh, fallback disabled,
  max 16 per commission, and the host-only relay. The identity commission
  passed W01/W02 and its eligible provider-disabled same-invocation replay
  recorded zero children, provider attempts, invocations, receipts, audits,
  usage, outcomes, publications, terminal events, and semantic side effects.
- The next mutation commission created a terminally failed run and invocation,
  then stopped at `runtime_error / runtime_process / process_exit /
  runtime_execution_failed` after two progress events. Its seven expected
  gateway operations were absent with count zero; provider attempts were zero
  for that failed commission; no outcome, publication, artifact, terminal
  success event, or semantic mutation was recorded. No replay was eligible or
  run. The bounded receipt exposes no narrower runtime cause, so this remains a
  real local failure rather than an external-provider prerequisite.
- Owner-only receipt:
  `tmp/persona-wave-v6/worker-live-8d94fcc1-complete/result.json`, mode `0600`,
  SHA-256 `c0f869c8ceae591ce46cf5b6be4661a729f912ecb2caf842a849f76bf8fbdcbf`.
  First commission run/invocation refs were
  `69069a56-4d9f-4ec1-b4fd-c74a3959b3e3` /
  `invocation:1e77f8ed-1b1f-444a-bcbe-1ef440d81715`; failed commission
  refs were retained as `66eb272a-f95b-4071-8f72-c85da959bf68` /
  `invocation:cf7f9151-a0e6-4f69-8514-1be7e8d8824a`. W03-W08 remain dirty;
  further provider use is stopped.

## Wave 0BM — exact 94ed3da998 / runtime-isolation retest

- Provider-free runtime isolation fix `15ab1c7f45` was integrated as Plane
  `69601e97fb`; the runtime evidence pin was refreshed in `94ed3da998`. Host
  checks passed `165/165`, the sequential real-Hermes-child regression passed
  `1/1`, cross-process isolation passed `24/24`, and the canonical migration
  checks passed `3/3`. The network-disabled runtime import gate passed. No
  source correction was made after the live result.
- Exact refrozen artifacts: API
  `plane-agent-api:g4-v6-94ed3da9`, digest
  `sha256:e056369b525483e1111b3c8e878143d550626be041744dd73d654f7fcec78f21`;
  runtime `plane-agent-runtime:hermes-292e8663-g4-v6-94ed3da9`, digest
  `sha256:ccd2114f411b152495413079557c6eae1128a23af872417524e924c2670cff07`;
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`; MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`; SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The owner-only manifest is
  mode `0600`, SHA-256
  `81445b1808f586be212e2a9d0154c26c045f702a123fa84e78fa284aa05a87ba`.
- One fresh synthetic-only three-commission Worker journey used
  `openai-codex/gpt-5.6-luna` xhigh, fallback disabled, max 16, and the
  authorized host-only relay. Identity/discovery passed W01/W02. Its
  same-invocation provider-disabled replay was eligible and recorded zero
  children, provider attempts, invocations, receipts, audits, usage,
  outcomes, publications, terminal events, and semantic side effects.
- The mutation-composition commission then created a failed run and
  invocation and stopped before W03/W04/W07/W08 execution at
  `runtime_error / runtime_process / process_exit /
  runtime_execution_failed`; runtime ingress recorded two progress events,
  the seven expected gateway-operation counts were zero, provider attempts
  were zero, and no outcome, publication, artifact, terminal-success event, or
  semantic mutation was recorded. Failed run:
  `9c2eb4cf-9bb8-49a2-a9c6-7863a0187aab`; failed invocation:
  `invocation:72aae4f2-a351-432b-9a07-10767632778e`.
- Canonical owner-only receipt:
  `tmp/persona-wave-v6/worker-live-94ed3da9/result.json`, mode `0600`,
  SHA-256 `fac0e62ee92e42d0bba32698ec91f5661405ad8b9edbbcbe82483aa0b13c1a44`;
  standalone live validator passed. The receipt is the only retained
  result/log artifact: the runner's internal `sanitized-error.log` and
  transient run directory are removed by the owner-only cleanup trap, so no
  separate log file exists to hash. Task-owned containers, volumes, and
  networks were absent after cleanup; the disposable Hermes clone and the
  incidental core dump were removed. No credential contents were read,
  printed, copied, or recorded. W01/W02 remain clean; W03-W08 remain dirty;
  UT-041 remains open for the dedicated runtime debugger. No replay or
  further provider use occurred after the bounded failure.

## Wave 0BN — exact 587f2272cf / compiler-backed Code Mode retest

- Validated commits `c21fa19c0590ec1d9471b62be72e83c4b0dc619b` and
  `da2bae9b9c43d47e52444b2bb1c5bdaf9514f840` were cherry-picked in order as
  `e6962c3923` and `587f2272cf`. Source builder checks passed `6/6`; exact
  Hermes provider-free gateway/real-child/sequential/Node checks passed `4/4`.
- The retained prepared base `plane-g3-external-client-api-tests:prepared-codemode-fb78`
  passed the canonical compiler/pytest/ruff/source guards. Exact artifacts:
  API `plane-agent-api:g4-v6-587f2272`, digest
  `sha256:58068e1a811239ccb44cae0b24fdec9ab47d09003f76316051df90ae31ee6d14`;
  runtime `plane-agent-runtime:hermes-292e8663-g4-v6-587f2272`, digest
  `sha256:e28c51e321bfcfc5631ead6cf9c1b58dcd4922f66f9f35564a0f622fada5d593`;
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`.
- One fresh synthetic B/C descriptor used GPT-5.6 Luna xhigh, fallback
  disabled, max 16, and the existing host-only relay. W01/W02 were not rerun.
  B reached `search_workspace=1`, `work_item.read=1`, exact
  `agent.outcome.evaluate=denied/NOT_AUTHORIZED`, one submit, and one applied
  publish/terminal event, but no typed `execute_code` or `work_item.rename`.
  RuntimeExit completed at sequence 16 and S00 publication/terminal gates
  passed; the Worker scenario gate failed at the mutation commission, so C did
  not start. This is the first causal boundary; no compiler, isolate, or
  host-RPC crash is inferred.
- Provider attempts: 7, all completed/upstream-initiated/`2xx`; no fallback and
  no replay. Run `518bd156-9c8a-43cf-ba81-7f6c3a033fa6`, invocation
  `invocation:ab6f5bf3-91d9-4c8f-9037-3823d329cfde`, outcome
  `outcome-submission:63678b35-d993-4f69-a758-231756d020b9`, and product event
  `product-event:215713e2-e7d6-442d-a031-287e1f688016` are retained.
- Owner-only result:
  `tmp/persona-wave-v6/worker-live-587f2272/result.json`, mode `0600`, SHA-256
  `d74dfab1277780f750f3c9e0a5f68c8aa8c0d9cdfe5a24a39d8e4a5115b89b91`;
  canonical validator passed with `evidence_sha256` equal to that hash. No
  separate launcher log file was persisted. W03-W08 remain dirty and UT-042
  is open; no provider use continues after this bounded stop.

## Wave 0BO — exact C commission boundary stop

- The one fresh single-commission `context-governance` journey used the
  existing Plane/Hermes runner with GPT-5.6 Luna xhigh, fallback disabled, and
  no chat UI. Artifact source was
  `0d6a239a49064bba3e903d7bc41fa5e78467cbc7`; the host wrapper was
  `3d0fd4b91fc956d8ddd75d269b3ff5d1d633f408`; Hermes was
  `292e866374ca9e9615473fc9bf5dda1913b672e1`; MCP was
  `c04974ed6624f17b41e63ef8182661929e77e0d3`; SDK was
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- The exact API/runtime tags, image digests, runtime/Hermes source digests,
  manifest hash, raw bounded receipt hash, and provider-attempt count are
  retained in the tracked redacted extract
  `user-testing-output/plane-agents/evidence/w05-w06-c-provider-stop.json`,
  SHA-256 `f757ea66823b01d7828f2248adc4e8c3406f336ba393af212340eb4c8008ff33`.
  The raw owner-only failure receipt is SHA-256
  `13d2394b78f3e5306ca2ac4d0f5e8c1b747a131abc579a5ae3f524829cc94dd3`.
- The authorized run stopped at `api-invocation` with the bounded
  `ImproperlyConfigured` / exit `1` / `unavailable` receipt. Provider attempt
  count was zero. Per the shared-owner protocol, no launcher/config patch was
  made in this lane after the stop, no `outcome_unknown` was replayed, and no
  further provider use occurred.
- A provider-free reserializer check initially found and fixed an omitted
  metadata/content newline; commit `601749ee8f` now has 14/14 Django
  W05/W06 memory/skill tests and 63/63 focused scenario/launch tests passing.
  W05 and W06 remain dirty pending the shared boundary fix and one fresh
  corrected C journey.
- Cleanup was verified after the failed run: zero containers, volumes, and
  networks remained for the observed disposable Compose identifiers. No
  credential contents were read, printed, sourced, copied into tracked output,
  or recorded.

## Wave 0BP — exact corrected C commission boundary stop

- Shared fix `e312633e08856123f5b64cd9ed6b3dddabb501ca` was integrated as
  `6636f3dd11f23be2a0da302f31b611a4756dca61`. The exact live candidate was
  `383c8cb15b5236ffca9ec72795b6fea0db332a1d`; contract regressions passed
  `160/160` and the provider-free Django memory/skill regression passed
  `14/14`.
- The API image was `plane-agent-api:g4-v6-383c8cb`, digest
  `sha256:96464ed75a750df729634f235db5c7ca5e5f8f62e43813d272a98f7b1bd13926`;
  the runtime image was
  `plane-agent-runtime:hermes-292e8663-g4-v6-383c8cb`, digest
  `sha256:e93b6d3e77d43a918072ca3c7c1db284a1eac62ab0f8b9c99541947ec06204d8`.
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889` were exact.
- The one fresh `context-governance` commission used GPT-5.6 Luna xhigh,
  fallback disabled, and stopped at `api-invocation` with
  `unspecified` / `unavailable`, exit `1`. Raw result SHA-256:
  `4f485a0a582f963b9632fabcaf6db45723fe1428fc471e769b6d47351f516b90`;
  durable redacted evidence:
  `user-testing-output/plane-agents/evidence/w05-w06-c-corrected-stop.json`,
  SHA-256 `e2e648bc5e2fcb1ea5d2e3290a0abe46aa8e968a4e6b8a825126956cf478da89`.
  Provider attempts were `0`; no W05/W06 receipts, audit, publication, or
  replay were observed. Run `4b851f81-b555-4f65-9875-eabfdc432065` and
  invocation `invocation:8c5c87f7-4d7d-4ed3-adad-8881dd0b863b` are retained in
  the redacted extract.
- The provider-disabled same-invocation replay was ineligible because the
  primary stopped before a commission result. No replay, retry, or
  `outcome_unknown` replay was made. Cleanup was verified at zero disposable
  containers, volumes, and networks. W05/W06 remain dirty, and the reopened
  shared debugger owns the next correction.

## Wave 0BQ — exact second-fix C commission boundary stop

- The second shared fix `3c4209340c7f219be76258083a595b8fba14c05c` was
  integrated on top of the existing e312 integration as Plane
  `b002211f0db8d04fe13c639a026502f0a0ea2618`. Host contracts passed `161/161`
  and the provider-free Django memory/skill regression passed `14/14`.
- Exact artifacts: API `plane-agent-api:g4-v6-b002211`, digest
  `sha256:12888071f9606b84135c20682a4e1479753091870f3a0853a4b4cec2c0184ffd`;
  runtime `plane-agent-runtime:hermes-292e8663-g4-v6-b002211`, digest
  `sha256:5735f8a6a13260843e3d95f783696ca15b5eab2633baf19da59e80ff72a4e9f9`;
  manifest SHA-256
  `c3bdf383cc6fb0a6c264d84f54c6bc71283b093474975dca00f5dfe634f2cf7b`.
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889` were exact.
- The one fresh `context-governance` commission used GPT-5.6 Luna xhigh,
  fallback disabled, and stopped at `api-invocation` with
  `unspecified` / `unavailable`, exit `1`. Raw result SHA-256:
  `bd65e1fd64fbb5ba77a68bc7aa3b577a49acf48bedf488d7c1e57c76e5ad517d`;
  durable redacted evidence:
  `user-testing-output/plane-agents/evidence/w05-w06-c-second-fix-stop.json`,
  SHA-256 `27721c95b2c17d352f38fa0e8ed798babda6d9a5e9341b4b8af3fdd92fc2c3fe`.
  Provider attempts were `0`; no W05/W06 receipts, audit, publication, or
  replay were observed. Run `b5f5b8e2-def6-4066-bb00-ebe0a7cc96db` and
  invocation `invocation:b66f5437-9931-47ce-90b6-4aca07d02e9f` are retained
  in the redacted extract.
- The provider-disabled same-invocation replay was ineligible because the
  primary stopped before a commission result. No replay, retry, or
  `outcome_unknown` replay was made. Cleanup was verified at zero disposable
  containers, volumes, and networks. W05/W06 remain dirty; the shared
  debugger owns the next correction.

## Wave 0BR — capacity-gated exact C compose boundary stop

- Capacity-gate commit `be3eecea9c335b05f2ae1389d036e281b6475f8f` was
  integrated at Plane `2e7ce806b60d74045073544660c36feb2cf56c0c`. Provider-free
  checks passed: `178` focused host tests and `14` Django memory/projection
  tests. Config-only live contract preflight and absolute descriptor
  validation passed. No setup script was run; the copied env metadata matched
  source/target mode `0644`, size `1466` without exposing values.
- Exact API/runtime images were bound to the candidate: API
  `sha256:5cc4090672c2adb53b7be9c54707f60007d377d8a929ad78c578d5fa65e5fe63`,
  runtime
  `sha256:23b68142e410ea6c2d409dba1c8afe6d97361ba12d44522a49a4181fba4cf61d`;
  manifest SHA-256
  `ce92f3190e946985c8c909c2f5f1052983a56b58d29cddc9be39448ece87a073`.
- One fresh C journey used GPT-5.6 Luna xhigh with fallback disabled and
  stopped at `compose` with `unspecified` / `unavailable`, exit `1`. Provider
  attempts/effects were `0`; no replay occurred. Raw result SHA-256:
  `8f1f533251657b60b87549f9c5d8e5fad82d013d8af748520a2f2787b032227a`;
  durable redacted extract:
  `user-testing-output/plane-agents/evidence/w05-w06-c-capacity-compose-stop.json`,
  SHA-256 `f9ab6c461cb03e055c0219a92f8153757b897d24802e1d602ecd9c54c705a8e6`.
- W05/W06 feature receipts were not observed because the compose boundary
  failed. Capacity lease release and Docker cleanup were verified at zero
  remaining containers, volumes, networks, and lease. No provider retry or
  replay was made.

## Wave 0BS — exact integrated C API-invocation boundary stop

- Integrated commits in the required order: `200d1fdb7d`, `488390ba21`, and
  `855f4e6686`. Clean candidate:
  `b2a2b50c8c904adda2c287b3780e514c46d90ca8`. Hermes, MCP, and SDK pins:
  `292e866374ca9e9615473fc9bf5dda1913b672e1`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- Focused provider-free checks passed: RabbitMQ tmpfs `1/1`, capacity
  support/result `16/16`, W05/W06 route/descriptor `6/6`, config-only
  preflight, descriptor validation, and live-receipt validation. The broader
  fake-Docker contract run had `179` passes and two fixture timeouts; root
  dispositioned them as non-blocking test-harness debt, and this lane did not
  patch them.
- Exact API/runtime artifacts were
  `plane-agent-api:g4-v6-b2a2b50c` (`sha256:b5a33a42a569f83e4a067f58fa3a8427986084d1b35e57b53aa5e8e953b5a521`) and
  `plane-agent-runtime:hermes-292e8663-g4-v6-b2a2b50c` (`sha256:cc8fb6743077327c7b45ff13f48e36d264c243fddc7da6a38a537e81ec9aa074`);
  manifest SHA-256:
  `17c7e667df484302677159fb1bcb556a18b7788a947a6c7ce9f6b76398889585`.
- Exactly one fresh single-commission `context-governance` journey used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled. It reached healthy
  dependencies, then stopped at `api-invocation` with bounded `unspecified` /
  exit `1` / `unavailable` before a commission result. Provider attempts and
  effects were `0`; no W05/W06 context/memory/skill receipts, audit,
  publication, or replay were produced. Raw owner-only result:
  `tmp/persona-wave-v6/w05-w06-c-final-b2a2b50c/result.json`, mode `0600`,
  5031 bytes, SHA-256
  `a5e78e674787ecad5dc623bf693331c03c9c5aedbb0de3a0b858acd98c3330b1`.
- Durable redacted evidence:
  `user-testing-output/plane-agents/evidence/w05-w06-c-api-invocation-stop.json`,
  SHA-256
  `988404c2029b6e301e9fa5caf4b79a8dc4ff9bab91adb0e970d74f691444fbe1`.
  Run `de7c79bb-2387-4b8a-8af8-0e03e381b9e5` and invocation
  `invocation:3cbbf662-2291-4e13-ac06-214f7ad1eaea` are retained in the
  redacted extract. The provider-disabled replay was ineligible and was not
  run; no `outcome_unknown` replay occurred. Cleanup verified zero
  containers, volumes, networks, and capacity leases. W05/W06 remain open.

## Wave 0BT — exact a50834fa replacement C API-invocation boundary stop

- The replacement executor started exactly from clean Plane source
  `a50834fa0427600d236e9c7eafee151c1184c0a6`. It copied the existing
  credential-bearing `.env` files byte-for-byte without reading, printing, or
  sourcing values, and did not run `setup.sh`. The six tracked `.env.example`
  files copied from the machine checkout were restored to the exact candidate
  commit before image refreeze so the source binding remained truthful.
- Exact refreeze used API
  `plane-agent-api:g4-v6-a50834fa` / digest
  `sha256:0f29e02417505b3b761cad6b4af753c697e6f0d09660b8ec34933ad755456d3a`
  and runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-a50834fa` / digest
  `sha256:68835901f97cc9671f8de722b6214ab2ef6e7a2177a164dbee969840f9563c4d`.
  Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889` were exact. Manifest SHA-256 is
  `4bd47b4ef864c70ff6a5456c40fce100eb8050b6c338d0576d74704ec5e375f0`.
- Exactly one fresh single-commission `context-governance` journey used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled under the
  host-wide capacity gate. It reached healthy runtime dependencies, then
  stopped at `api-invocation` with bounded `unspecified` / `unavailable`, exit
  `1`, before the commission result. Run
  `5c154173-ad50-44b7-abe1-7207033644ed` and invocation
  `invocation:33559520-3592-4650-93d8-d5a9809d5f61` are retained in the
  redacted extract. Provider attempts and effects were `0`, runtime events
  were `0`, and no W05/W06 context, memory, preference, skill, outcome, or
  publication receipt was observed.
- The provider-disabled replay was ineligible because the primary failed
  before a commission result. No retry or `outcome_unknown` replay occurred.
  Cleanup verified zero task containers, volumes, networks, and no remaining
  capacity lease. W05 and W06 remain dirty; this is a local API-invocation
  boundary stop, not provider-backed route closure.

## Wave 0BU — exact d748 runtime-binding probe and API-invocation stop

- The corrected executor resumed from clean Plane `d748ecbc6dd6ddba30e8de78c154f8e78af3a82c`, copied the required machine `.env` files byte-for-byte without reading, printing, or sourcing values, and did not run `setup.sh`. Exact API/runtime artifacts were reused only after clean-candidate and digest verification: API `sha256:55992ebbd2a818c0e234176ecbf98b3161a7b3f727243d977283840b79f0cca7`, runtime `sha256:8a675fad25b559d82d63ed50321832af365e8afec441286b566d0d981d23fcba`, and manifest SHA-256 `7b81499031595b4ff35c48fc94f2efd3dd00f627a7d714ce31416edf9160137c`.
- Exactly one fresh capacity-gated `context-governance` journey used `openai-codex/gpt-5.6-luna` xhigh with fallback disabled and the checked-in ChatGPT subscription destination. Before API invocation, the exact API-container binding probe passed with `settingsSource=django`, secret target `/run/plane-agent-runtime-secret`, mode `0600`, readable owner-only secret, runtime host alias `agent-runtime`, `transportKind=remote`, and `transportClass=RemoteRuntimeTransport`. The bounded retained projection is `user-testing-output/plane-agents/evidence/w05-w06-c-d748-runtime-binding-probe.json`, SHA-256 `ad03cf8f22765516f4e246dcbb3cdbe4b3f78604b94096debf04782a0bdcc8eb`.
- The journey then stopped at `api-invocation` with bounded `unspecified` / `unavailable`, exit `1`, before the commission result. Provider attempts/effects were `0`, runtime events were `0`, and no W05/W06 receipt, outcome, publication, or replay was produced. Run `bdc59a54-ef76-4982-bb1f-431e4eb048d9` and invocation `invocation:686e3a8a-567c-4311-994c-995d0440d06d` are retained in the owner-only result `tmp/persona-wave-v6/w05-w06-fresh-d748ecbc-r2/result.json`, mode `0600`, SHA-256 `c1c89a7363353931b74ce0475a22557adb18c3e5e58b603d928e7e057c0fe9b`; durable redacted failure evidence is `user-testing-output/plane-agents/evidence/w05-w06-c-d748-api-invocation-stop.json`, SHA-256 `0eac3da74b4c5232954773c0d59b55c596bfd48cd316f45058121f1c70e7bdb0`.
- The provider-disabled same-invocation replay was ineligible because the primary failed before a commission result. No retry or `outcome_unknown` replay occurred. Capacity-lease release and exact-owned Docker cleanup verified zero remaining containers, volumes, networks, and lease. W05/W06 remain dirty; this is local API-invocation evidence, not route closure.

## Wave 0BV — UT-049 provider-free root-cause correction

- The provider-free debugger reproduced the exact API invocation boundary in
  the immutable d748 API image (`sha256:55992ebbd2a818c0e234176ecbf98b3161a7b3f727243d977283840b79f0cca7`)
  on a disposable debug network with a deterministic fake runtime at the
  `agent-runtime` alias. The original failure was narrowed to
  `AuditRoleBoundaryError` in `plane.operation_gateway.role_boundary` before
  runtime dispatch; no provider attempts, effects, or runtime requests were
  observed.
- The launcher seam correction provisions the existing distinct Operation
  Gateway roles, uses the migration role for migrations, binds production API
  containers to the runtime role/database URL, and enables enforced audit
  bootstrap before and after migrations. The focused red regression was
  failing before the source correction and passes after it:
  `G4ContractTests.test_live_runner_binds_production_audit_runtime_to_api_container`.
- The exact production-Django binding probe passed with settings source
  `django`, secret target `/run/plane-agent-runtime-secret`, mode `0600`,
  root ownership/readability, runtime host `agent-runtime`, `remote`, and
  `RemoteRuntimeTransport`. The actual checked-in invocation helper reached
  the fake runtime and stopped at the intentionally synthetic runtime failure
  with bounded `RuntimeError / runtime_process / process_exit /
  runtime_execution_failed`, runtime exit present, and provider attempts/effects
  `0`. Durable evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-d748-ut049-provider-free-fix.json`,
  SHA-256 `25a8688e8ad4946091f80dec1dd8054f73c2e99b333469d7c0f610d5b4b22afc`.
- No live/provider journey, retry, replay, or `outcome_unknown` replay was run.
  The exact debug containers, volume, network, and temporary probe artifacts
  are cleaned before handoff; W05/W06 remain open pending one separately
  authorized fresh live retest of the committed fix.

## Wave 0BW — exact 64d1 W05/W06 journey and binding-probe correction

- Clean source was `64d1ea7fe76944fffc8f66cf4738bb556f02fa94`; required machine
  env files were copied byte-for-byte without reading, printing, or sourcing
  values, and `setup.sh` was not run. Fresh exact artifacts were API
  `plane-agent-api:g4-v6-64d1ea7f` /
  `sha256:5ad0e9d874099b5b45a99607ddc04fba1b8f93c8a2931827b309c54b0d66685e`
  and runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-64d1ea7f` /
  `sha256:b53453bf8f5239ff31624bad8a685b4e102b842dda2505379304f659f9205943`.
  Manifest SHA-256:
  `5bc6fbe42879e2a5c77230dc2ca1d4a750d5550f07035fa8c3dcb30b04930297`.
- Exactly one fresh capacity-gated `context-governance` journey used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled. Run
  `c161a8be-0afe-4f1a-b41d-0c045553759e` and invocation
  `invocation:ed1c1c45-5e0c-4ad9-9304-398ecfb6e09c` completed with 9 upstream
  `2xx` provider attempts, 20 runtime events, one outcome, one publication,
  and a completed runtime. The owner-only result is
  `tmp/persona-wave-v6/w05-w06-fresh-64d1ea7f-live/live-result.json`, SHA-256
  `9a1eaf8106ed98b4d187c8b7ffd3d61c601d2631ed80efd03216cfd993ab006a`.
- A provider-free exact reproduction proved the live candidate's
  `api-runtime-binding` probe was vacuous: the launcher omitted Docker `-i`,
  so Python read no stdin and exited `0` without running the probe. The live
  pre-dispatch proof is therefore invalidated, even though the route result
  passed. The smallest fix adds `-i` and a focused regression; the red test
  failed before the fix and the corrected G4 contract/live-result suites pass
  `115/115`.
- The corrected exact API-image probe against a unique fake `agent-runtime`
  alias passed with `settingsSource=django`, secret path
  `/run/plane-agent-runtime-secret`, mode `0600`, root ownership/readability,
  `runtimeHost=agent-runtime`, `transportKind=remote`, and
  `transportClass=RemoteRuntimeTransport`. Bounded evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-64d1-runtime-binding-probe.json`,
  SHA-256 `227a70fff344ea2682d088ecaba61a31d2db6dc0987a5283c91d433d49269cbb`;
  live evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-64d1-live.json`,
  SHA-256 `a58bd6186c28be09caccfef8b54f5b8422c7391a68590ea5b0cb84daf7873203`.
- The enforced DB command gate ran migration ownership through
  `plane_migrator`, bound production API invocation to `plane_runtime`, kept
  `plane` as the bootstrap provisioner, and enabled role separation before
  dispatch. No passwords or URLs were retained. No second provider/live
  journey, retry, old invocation replay, or `outcome_unknown` replay was run;
  no W07/Manager/Operator journey was started. W05/W06 remain dirty and
  route closure is withheld pending a separately authorized fresh run with
  the corrected pre-dispatch gate.

## Wave 0BX — exact 7466 W05/W06 replacement with valid binding proof

- Clean source was `74668f6d855fbea63fd57265b66410373d679d8f`; required machine
  env files were copied byte-for-byte without reading, printing, or sourcing
  values, and `setup.sh` was not run. Fresh exact artifacts were API
  `plane-agent-api:g4-v6-74668f6d` /
  `sha256:381fe4444f5b2c29b5b8d6793df15bcf090c957a54e7d47a4b713a2c31f965a7`
  and runtime `plane-agent-runtime:hermes-292e8663-g4-v6-74668f6d` /
  `sha256:2807188c1527b88a9fdaa0439ee61297e1f7c698a7a52d74c691114d4fbeb1a1`.
  Manifest SHA-256:
  `cc89e45b72fc60d86f62052558111ad465585804dba21600b6a233c0dfe408cc`.
- Exactly one fresh capacity-gated `context-governance` journey used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled. The corrected
  exact API-container probe executed before dispatch and passed with
  `settingsSource=django`, `/run/plane-agent-runtime-secret`, mode `0600`,
  root ownership/readability, `runtimeHost=agent-runtime`,
  `transportKind=remote`, and `transportClass=RemoteRuntimeTransport`.
  The enforced DB command gate used `plane_migrator` for migrations,
  `plane_runtime` for production API connections, `plane_audit_owner` for
  governance, `plane` only for bootstrap provisioning, and role separation.
- Run `25966a40-bbf5-4690-af74-61124e1e798f` and invocation
  `invocation:ebaedd9e-48e8-447b-8afb-b746cb9f4384` completed with 8 upstream
  `2xx` attempts, 18 runtime events, one outcome, one publication, and a
  completed runtime. Durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-7466-live.json`; the
  bounded probe is
  `user-testing-output/plane-agents/evidence/w05-w06-c-7466-runtime-binding-probe.json`.
- The provider-disabled same-fresh replay had zero provider attempts and zero
  semantic deltas. No separate W07, Manager, or Operator journey was started.
  Capacity release and exact-owned Docker cleanup passed. This valid 7466
  replacement supersedes the vacuous 64d1 claim; W05/W06 route closure is
  recorded for this journey.

## Wave 0BY — exact W07/W08 D provider stop

- The authoritative corrected Worker chain was reconciled at `f033a0054a239814e518a6854a41beab0171f3c0`; the W07/W08-only candidate added the runtime-boundary fixture correction and the tracked Worker D contract, ending at Plane `e9fad58037d539a65b453bdc64fecc387c209fb7`. The authoritative runtime/DB-role changes and W05/W06 evidence were not duplicated or reverted. Provider-free focused checks included the runtime boundary (`1 passed, 33 deselected`) and live/contract harness (`95 passed, 82 deselected`).
- The fresh D descriptor SHA-256 was `472caab0a49cd5b1e11cd7e6213e3091b926270b00b4d247e4ff05e09d892708`; its single commission used `openai-codex` / `gpt-5.6-luna` xhigh, fallback disabled, one synthetic schedule, and route checks `W03,W04,W07,W08`. Exact artifacts were API `plane-agent-api:g4-w07-w08-e9fad5` / `sha256:732ee2fc168d27833d8d82fe375f102daee4d0157bd98cd03a00508471b7f643` and runtime `plane-agent-runtime:hermes-292e8663-g4-w07-w08-e9fad5` / `sha256:ad4b66ce76bd759656373c63e7585686b88f86aec1f75b408b78d2f192b1cfd1`; manifest SHA-256 `1ffda90e0da71a4ee279bb6287a15e4ec36ea681c9711e28b4304b3c21cf044e`.
- Exactly one fresh capacity-gated provider-capable journey ran against `https://chatgpt.com/backend-api/codex/responses` with the pinned Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The non-vacuous runtime binding gate passed (`settingsSource=django`, `/run/plane-agent-runtime-secret`, mode `0600`, `agent-runtime`, `remote`, `RemoteRuntimeTransport`); the runner progressed through DB bootstrap/migrate and stopped at API invocation with one upstream-initiated `provider_error`, then bounded `runtime_error / runtime_process / process_exit / runtime_execution_failed`.
- The owner-only raw result is `tmp/persona-wave-v6/worker-live-w07-w08-d-e9fad5-20260817-05a00b39/result.json`, mode `0600`, size `5553`, SHA-256 `00fe2c436cac264f23aa4bf57957ddccf0151287a3653088e68a193d1f65fa5a`; canonical validator passed. No Plane operation, artifact, outcome, publication, product terminal event, ordinary transcript evidence, W08 readback, or eligible replay was observed. Durable redacted evidence is `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-stop.json`, SHA-256 `dc8f39c19d8cb6a041b8b606ab150eb1ac33c9954cd7aacae6667da085528528`.
- Provider use stopped at the first genuine failure: no retry, blind `outcome_unknown` replay, or provider-disabled replay was run. Post-stop provider-free lifecycle regressions passed for ordinary-text transcript-only behavior (`1 passed, 40 deselected`) and missing-publication failure (`1 passed, 7 deselected`); the fixture correction is `d9d258715b`. Capacity lease release and exact runner-labeled container/volume/network cleanup were verified absent. W07/W08 remain dirty; no feature pass is claimed.

## Wave 0BZ — W07/W08 provider-free diagnosis

- The durable redacted diagnosis extract is `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-diagnosis.json`, SHA-256 `1272718d80a96c2c3c9978f117eeb170bd0826a1161fb565da8cc994627730c0`. It retains only bounded failure class/code/status, lifecycle counts, raw-result digest/size/mode, and provider-free check statuses; no raw provider response, prompt, model text, credential, or secret was persisted.
- The existing pinned Hermes relay regressions passed `6` with `8` deselected. The deterministic local D-shaped request probe completed with valid native request shape, valid tool schema, `store=false`, no relay secret, and a terminal completion. Existing outcome-unknown and midstream-failure cases remained no-fallback and no-replay. The bounded live `provider_error` is therefore a coarsened error-class projection, not evidence of a local relay/request-shape defect; the retained receipt does not distinguish remote rejection from transient upstream failure.
- No provider/live journey, replay, or fresh assignment was run in this diagnosis. The provider-free failure-projection regressions passed `2/2`; W07/W08 remain dirty, and a fresh assignment is not authorized from the available evidence.

## Wave 0CA — W07/W08 provider-free status-family repair

- The existing `statusClass` field was the sole bounded provider-attempt
  family contract; the relay had collapsed 4xx/5xx to `error` and transport or
  midstream ambiguity to `unknown`. Commit
  `cf9d2b8a205d78e0c30250464a5b4c70df90169d` preserves only `2xx`, `4xx`,
  `5xx`, and `transport`, keeps legacy values valid, and leaves the existing
  Plane attempt/readback authority and idempotency path unchanged.
- Red regressions cover real 4xx, real 5xx, transport/midstream failure, and
  successful 2xx; they also verify lifecycle replay identity, Plane readback,
  body/status/header/credential/prompt/model-output redaction, and bounded
  live validation. The committed provider-free results are relay `35/35`,
  selected API relay/lifecycle `28/28`, and bounded contract `106/106`.
- Durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-status-family-fix.json`,
  SHA-256 `272785ec43879f85e53c43abb96b62570423950b3ed0084cf3ad745bd426ec35`.
  No provider/live journey, retry, or replay was run; provider attempts/effects
  were `0`. Test Compose cleanup verified zero containers, volumes, and
  networks. W07/W08 remain dirty and this local fix alone does not make a
  fresh assignment safe.

## Wave 0CB — exact corrected W07/W08 D provider stop

- The single authorized fresh D assignment used clean Plane
  `989a159cf3fa093702d6c3d61dfd3b705b6bb6a0`, parent
  `cf9d2b8a205d78e0c30250464a5b4c70df90169d`, exact API
  `plane-agent-api:g4-v6-989a159c` /
  `sha256:36c8cd6b47357a78f2d49946cc5e09aed6cca368ed8880eeee7e78ef2d54c0b9`,
  and exact runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-989a159c` /
  `sha256:2c9484c58103964a1d033998ecd3f9dae4e10676c00698348ced79d77364dc4a`.
  Hermes was `292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP was
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK was
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Manifest SHA-256 was
  `eb49fea15cd69eb203430df7ea8fb13d286a01db9892db73c76dad46410059b5`.
- The fresh scenario descriptor SHA-256 was
  `472caab0a49cd5b1e11cd7e6213e3091b926270b00b4d247e4ff05e09d892708`.
  It selected the sole commission
  `w07-w08-artifact-publication-readback` for Maya Worker D with synthetic
  W07/W08 acceptance criteria, GPT-5.6 Luna xhigh, fallback disabled, and no
  fault injection. The non-vacuous runtime binding and DB role preflight
  passed before the live phase.
- Exactly one capacity-gated provider-capable journey ran against
  `https://chatgpt.com/backend-api/codex/responses`. Run
  `ecd2b743-3059-40fd-a126-0f9cde45f8c4` and invocation
  `invocation:adbb571f-ee73-44bf-afc3-8238a816d536` stopped at
  `api-invocation` after one upstream-initiated provider attempt. The
  bounded receipt recorded generic `provider_error`, then
  `runtime_error / runtime_process / process_exit / runtime_execution_failed`.
  It also recorded legacy `statusClass=error` instead of the required bounded
  `4xx|5xx|transport` family. No W07/W08 operation, artifact, evidence item,
  outcome, publication, product event, or readback was observed.
- The owner-only bounded result SHA-256 is
  `d5d9452a08cfed4af544317951ae9d05d463e6de480fc6b5c440ab0b2cb565b5`.
  Durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w07-w08-d-989a159c-failure-extract.json`,
  SHA-256 `80112e72911b526ac1f2dcdad1a31643285c86c73e9b5fc32861df113263afc9`.
  The exact result, manifest, scenario, authority, and config are also
  promoted under `user-testing-output/plane-agents/evidence/` with their
  individual hashes recorded in the extract.
- Provider-free diagnosis showed synthetic 400 and 500 responses through the
  pinned `PinnedProviderHTTPSClient` both raise generic `ProviderRelayError`
  with an empty status family. The bounded projection tests passed `3/3` with
  `103` deselected. This is a local status-loss finding at the existing
  provider adapter seam. No provider retry, blind `outcome_unknown` replay,
  or provider-disabled replay was run because the primary was terminally
  failed and the stop policy made replay ineligible.
- Cleanup verified zero runner-labeled containers, networks, credential/state/
  scenario volumes, and no capacity lease. W07/W08 remain dirty; no feature
  pass or readback closure is claimed.

## Wave 0CC — exact 51c5ed07 W07/W08 D first-provider stop

- The one fresh W07/W08-only D commission used clean source
  `51c5ed07e6d5d46fda7acb9794805de45231b2f7`, with no W01-W06 route in the
  descriptor. The owner-only scenario SHA-256 was
  `c49924959c1b5f7a33e5b70173d0e89cf4c1b16fb2126d8a71f013003f86cedb`.
  The exact API image was `plane-agent-api:g4-v6-51c5ed07` /
  `sha256:0751aac75e3953a785f3e0fab3571aa4ccaf2460cfa6727efb1e58a67af93c06`;
  the separate runtime was
  `plane-agent-runtime:hermes-292e8663-g4-v6-51c5ed07` /
  `sha256:abb390bb88ff99b73c31aa1a4fed39815a50073371dfbaa5517bfacb12c27972`.
  Manifest SHA-256 was
  `b39baa1e3b935107e591964322eaa3f40f740fcc3e53182e214e1ecdc563c4a5`.
  Hermes, MCP, and SDK were pinned to
  `292e866374ca9e9615473fc9bf5dda1913b672e1`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- Required runtime env files were copied byte-for-byte from the authoritative
  checkout without reading, printing, or sourcing values; `setup.sh` was not
  run. Descriptor/config/manifest validation passed, the non-vacuous runtime
  binding and DB-role gates passed, and the scheduled fixture was created in
  the fresh isolated workspace.
- Exactly one capacity-gated provider-capable journey ran against
  `https://chatgpt.com/backend-api/codex/responses` with
  `openai-codex/gpt-5.6-luna` xhigh and fallback disabled. Run
  `06d74a6c-f0ee-467e-930a-ecaa1bab4a70` and invocation
  `invocation:f6b4649a-05e4-4b8d-ab5e-12f96761d409` stopped at
  `api-invocation` after one upstream-initiated attempt. The bounded result
  recorded generic `provider_error` and `statusClass=4xx`, followed by
  `runtime_error / runtime_process / process_exit / runtime_execution_failed`.
- No Plane operation, artifact, evidence item, outcome, explicit publication,
  product terminal event, ordinary transcript evidence, or W08 readback was
  observed. W07 and W08 are both `dirty`; no feature pass is claimed. The
  owner-only result is
  `user-testing-output/plane-agents/evidence/w07-w08-d-51c5ed07-result.json`,
  SHA-256 `2bd1eb282ab8aedf65776e640b5d170395d7d3eb699ddebd6ada4c10869bd461`.
  The deterministic redacted extract is
  `user-testing-output/plane-agents/evidence/w07-w08-d-51c5ed07-failure-extract.json`,
  SHA-256 `69a303c1168fdb654b9c73bd72b071255d47eaf58f719fc6133efee1be06ed2a`.
- Provider use stopped at the first genuine failure. No retry, fallback,
  blind `outcome_unknown` replay, or provider-disabled replay occurred.
  Provider attempts/effects were `1` / `0` Plane product effects. Focused
  provider-free harness checks passed `179`; Docker API/runtime/lifecycle
  checks passed `115` with one known repository-root mount-path test
  deselected. The focused test stack was torn down successfully; capacity
  lease release and exact-owned live Docker cleanup were verified at zero.

## Wave 0CD — W07/W08 provider-free bounded reasonSubreason repair

- From clean parent `45966c9c4e39e63d9b6ea99bbc92fa104424650f`, the smallest
  existing-contract fix was committed as
  `e46635f6727c39f15ee0915e452ebc2aa2c21e28`. The serial lifecycle failure
  was classified as local fixture/assertion friction: a terminal 4xx fixture
  expected transport and omitted the required provider-relay reason phase.
- The existing typed `reasonSubreason` field now carries only allowlisted
  request-rejection, auth, rate-limited, upstream-unavailable, and established
  transport diagnostics. The public attempt remains `provider_error` with
  bounded `2xx|4xx|5xx|transport`; numeric status, body, headers, URL,
  credentials, prompts, and model output are excluded. API and CLI readback
  preserve the bounded field and validator compatibility remains backward
  compatible.
- Provider-free host contract/evidence suites passed `180`; the serial Docker
  relay/runtime/lifecycle/attempt/API selection passed `185` with `4`
  environment-bound cases deselected. Provider attempts, provider calls, and
  replays were `0`. The durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w07-w08-provider-reason-subreason-45966c9c.json`,
  SHA-256 `7639bf93b520c76b5e16d29d49499b20c1f12f48123770576a9c517346c9cb2c`.
- Compose teardown returned exit `0`; the test network and runner containers
  were removed, with no live provider resources or capacity lease. This wave
  made no W07/W08 product claim and does not make a fresh live assignment safe
  without external provider disposition. A future root-authorized attempt
  must be a new assignment, never a replay.

## Wave 0CE — reconciled Operator O04/O06 provider-free readiness

- Reconciled the Operator candidate onto current functional-chain tip
  `358de27c956cfa52a8fa47c6d1b8114c87b0b83a`; applied the O04/O06-only
  descriptor as `808e042b0ef3cdef77cfc0b0a86eb65beeacf85c`.
- Current chain commit `a50834fa0427600d236e9c7eafee151c1184c0a6` is
  patch-equivalent to requested transport fix
  `7a08dd2611f9b5a6c5d35ac3887573d649b7a4d4`. Pure transport boundary probe
  passed; native pytest collection stopped at missing `celery` (exit `4`).
- Provider-free readiness: support/result `16 passed`, launch `7 passed`,
  descriptor `4 passed, 52 deselected`. The first support run had one
  transient scheduler ordering failure; a focused rerun and ten repetitions
  passed, followed by a fresh full `16/16` pass. No provider, live, Compose,
  setup, O02, or clean-route execution occurred.
- Fresh workspace:
  `/Users/nqh/.codex/worktrees/dfba/plane/tmp/plane-agent-o04o06-reconciled-ready.20OL89`;
  `106/106` source `.env*` copies were byte-for-byte verified without reading,
  printing, sourcing, or synthesizing values. Reserved project:
  `plane-agent-o04o06-reconciled-20260817-r1`.
- Durable redacted receipt:
  `evidence/operator-o04-o06-reconciled-ready-20260817.md`, SHA-256
  `e0a04a4bbc1b38218360db5f96d72746ba82f124876d249fb8d662782e9e72ee`.
  O04/O06 remain partial and ready-to-run only; the serialized capacity gate
  remains closed.

## Manager M01-M08 reconciliation — 2026-08-17

- The Manager source/test/runtime changes and redacted evidence from
  `e9281196b8e7a89466155f66c0d4d3bafdc95d6f` are integrated as a merge parent;
  the current branch does not adopt the Manager branch's historical
  candidate pins as its live candidate.
- Provider-free M01-M08 route evidence remains supporting-only. The durable
  receipt records assignment count `8`, child assignment count `3`, outcome
  count `2`, artifact-backed outcome count `2`, terminal event count `3`, and
  replay state mutations `0`.
- The two retained fresh Manager attempts stopped before provider use: one at
  `api-invocation` with `errorClass=unspecified`, and one at `migrate` with
  `errorClass=unavailable`. Both recorded zero Plane run/invocation creation,
  zero provider attempts, zero route mutations, and no replay. The full
  Compose/live phase was not entered for the readiness checkpoints; the
  transport checkpoint also records the RabbitMQ tmpfs permission stop.
- Durable extracts are retained at
  `user-testing-output/plane-agents/evidence/manager-m01-m08-provider-free-receipt.json`,
  `manager-m01-m08-fresh-live-failure.json`,
  `manager-m01-m08-fresh-live-failure-02.json`,
  `manager-m01-m08-capacity-ready-20260817-01.json`,
  `manager-m01-m08-capacity-ready-20260817-02.json`, and
  `manager-m01-m08-transport-ready-20260817-03.json`; exact hashes are in
  the issue ledger.
- No Manager route pass, provider attempt, retry, fallback, or blind
  `outcome_unknown` replay is claimed. M01-M08 remain untested at the
  provider-backed route level and the capacity gate remains closed.

## Worker W07/W08 fresh-assignment reconciliation — 2026-08-17

- The exact Worker/W07 head `81023308257903d09582f2190d82c73f93368bb5` is
  integrated. Its provider-free config, descriptor, runtime/DB, capacity, and
  focused `163/163` gates passed before the single authorized assignment.
- The assignment used the pinned ChatGPT Responses route with
  `openai-codex/gpt-5.6-luna` xhigh and fallback disabled. It stopped at
  `api-invocation` after one upstream-initiated attempt with bounded
  `provider_error`, `statusClass=4xx`, and `reasonSubreason=auth`.
- No Plane operation receipt, audit, artifact, evidence item, outcome,
  publication, product event, ordinary transcript, or W08 readback was
  observed. No fallback, retry, provider-disabled replay, or blind
  `outcome_unknown` replay occurred. W07/W08 remain dirty and unproven.
- Durable result, redacted extract, and decision receipt are retained at
  `user-testing-output/plane-agents/evidence/w07-w08-d-81023308-result.json`,
  `w07-w08-d-81023308-failure-extract.json`, and
  `w07-w08-d-81023308-decisions.tsv`; exact hashes are in the issue ledger.
  The fresh-assignment decision is `NO_GO` pending authoritative external
  acceptance/credential disposition plus clean candidate, runtime/DB, and
  capacity gates.

## Wave 0CG — exact integrated W07/W08 live stop — 2026-08-17

- Candidate binding: host wrapper `c1b51b2126defa83fcafab2f576bc4930bdd5265`,
  artifact source `1fd640da20b9f0be3d480f1a3a2788826f458b82`, API image
  `plane-agent-api:g4-v6-1fd640da` digest
  `sha256:876934c5cfe73388a008d8028316093dfaf090d853c954e49f23366618500129`,
  runtime image `plane-agent-runtime:hermes-9eafcb9e-g4-v7-1fd640da` digest
  `sha256:012557645c18299af575148567aea59a2f775dca4c038e9d7943e1a2de6d7b03`,
  manifest SHA-256 `7f9e46f75289b5c51190d02b908932c9959cacbaa1432c4b34c04f48c7d9d99b`.
- The exact integrated provider-free red-team passed and the focused contract
  suite passed `30` tests (`78` deselected). The fresh assignment used the
  supported ChatGPT Responses policy with `openai-codex`, `gpt-5.6-luna`,
  `xhigh`, and fallback disabled. It passed preflight and stopped at the first
  genuine local product failure after eight completed provider attempts.
- Run `db0c3e98-1df8-462c-a3dd-9d12b24c2de7` and invocation
  `invocation:d912fca6-18a9-4f94-a021-8231b013ecdd` ended at
  `CODE_MODE_FAILED` / `runtime_execution_failed`, phase `host_callback`,
  operation unavailable, with bounded cause `host_operation_failure`.
  Provider status counts were `2xx=8`, `4xx=0`, `5xx=0`, `transport=0`,
  fallback `false`, replay `0`. Search succeeded; work-item read and outcome
  evaluation were intentionally denied; submit/publish host receipts were
  present, but the exact W07/W08 lifecycle gates did not pass.
- W07/W08 feature closure, W08 readback, duplicate-effect proof, and the
  provider-disabled replay are not claimed. No further provider use was made.
  Durable redacted evidence is retained in the six `w07-w08-c1b51-*` files;
  the canonical result hash is
  `5cc3a928042ade4de9cf0b56b4a49bad3b8b7a52050e8cc7d8f741b5eea39112` and the
  bounded extract hash is
  `6481d2bd034d7a3882099acb5f1e9c9b3607b45c0f5ec6950e633a2ca58a56e`.
- Cleanup proof: capacity marker absent; observed disposable containers,
  volumes, and networks were all zero. The owner disposition is a separate
  provider-free fix at the existing Code Mode host-callback seam.

## Wave 0CH — exact corrected W07/W08 live stop — 2026-08-17

- Exact candidate binding: branch
  `codex/plane-agent-functional-integration-20260817`, wrapper
  `139897ac356762563d8e14648712f78685eb5019`, sole parent/source
  `78e02a20b4b0649ce1d4844d1cb9cf39526b362a`, manifest SHA-256
  `d23c6d9972a54b0bc9d69e33dfbae078eb92d05cd12d0183e6ff431451cac728`.
  API `plane-agent-api:g4-v11-78e02a` digest
  `sha256:700c98e8cfe8737068d7a24347169603158490171815fa381a96df833bfacb01`;
  runtime `plane-agent-runtime:hermes-6c460f10-g4-v11-78e02a` digest
  `sha256:2f11b340652a1d1e8fccaeb2514a6069deed2c0f9794b255ed886c038092a6af`.
- Hermes/MCP/SDK pins were `6c460f10fe215718dce36dd73cda94155a9a34f8`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Provider policy was ChatGPT
  Responses, `openai-codex/gpt-5.6-luna`, xhigh, fallback disabled. The
  exact runtime red-team passed; the full contract suite passed `108` tests.
- Fresh authority `authority-w07-w08-139897-20260817-r3` ran commission
  `w07-w08-artifact-publication-readback-20260818-r2`. Run
  `1195a796-e2a0-46d2-ba3d-4043b158fbb3`, invocation
  `invocation:4b962fbe-1621-46d5-9c1f-f90477b6d047`. Provider counts:
  `2xx=7`, `4xx=0`, `5xx=0`, `transport=0`, fallback `false`, replay `0`.
- The first genuine failure was the local Plane operation boundary:
  `work_item.read` expected `success`, actual `denied`, error `NOT_AUTHORIZED`.
  `search_workspace` succeeded once; evaluator was intentionally denied once;
  outcome submit and publish each succeeded once. S00 bounded exactly one
  terminal and one applied publication, but the scenario gate failed and no
  artifact exactness, authorized readback, cross-workspace denial, missing
  publication test, or replay proof is claimed.
- Canonical result SHA-256
  `e2ac431c2ffa34b45b951b57c2856d726f9f909e728acd7dddb94b15da176c12`;
  authority `c741336b77bfa558a474773c751f93fd5558626763910aab47263bf5f4d18527`;
  config `09ffb9b574b77cae3cb926fd393566832db19e77cc18feb91552e29247441385`;
  scenario `1e643ec885cc62226ef4ab272bb772f1bc544090bf2d2dd03d137226accf3074`;
  redacted extract `99a6dc012f806c6c7836ff707bf031429840b4c3756754eded39955c57783c97`.
- Cleanup proof: shared capacity marker absent; exact live labels showed zero
  containers, volumes, and networks. No further provider use was made. The
  owner disposition is provider-free diagnosis of the Plane work-item
  authorization/fixture-binding seam.

## Wave 0CI — exact structurally corrected W07/W08 live stop — 2026-08-17

- Candidate: wrapper `376c5f1d0ab954b3035853193fcbfc475d064851`, sole
  parent/source `9480f5868cd2b37e20b34aa53e2b0995fe02487c`, source/evidence
  parent `b9ec4264ad0cec91a55e84213ac2717fb3d96048`; branch
  `codex/plane-agent-functional-integration-20260817`.
- Exact images were API
  `plane-agent-api:g4-v12-9480f5@sha256:65489299ef2b41e6c3173d2f281285453e8b1c6522a9610f2b59bf3d1d46f62f`
  and runtime
  `plane-agent-runtime:hermes-6c460f10-g4-v12-9480f5@sha256:b19117765f8ec9b4fa88d3f45fb3afbc8c47bf6d042eac7c44693227efc38aaf`.
  Manifest SHA-256 was
  `c53b1cf52b7802a69c7f0c50186224906024e4b5c099adf178ac0a11626f19d4`;
  Hermes/MCP/SDK pins were
  `6c460f10fe215718dce36dd73cda94155a9a34f8`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- Exactly one fresh serialized live assignment used the ChatGPT Responses
  route with `openai-codex/gpt-5.6-luna`, xhigh, fallback disabled, and
  commission `w07-w08-artifact-publication-readback-20260819-r3`. Scenario
  SHA-256 was
  `f8573106e8b401fd39ff40964fc459bd46d20014f27fcf90ee3f55b8007e42e6`.
  Run `e4717a19-5070-4b3e-9d7b-039f0f649567`; invocation
  `invocation:c541cbc6-674e-4d82-a8a2-67c9e0a33e11`.
- Provider attempts/effects: `8` upstream-initiated completed `2xx`
  attempts, `4xx=0`, `5xx=0`, `transport=0`, fallback `false`, replay `0`.
  Search succeeded once; the assigned-target `work_item.read` failed closed
  with `NOT_AUTHORIZED`; the intentional evaluator denial occurred once; host
  submit and publish each reported success once. The first genuine lifecycle
  failure was `CODE_MODE_FAILED` at `host_callback`, bounded as
  `runtime_error/runtime_process/runtime_execution_failed` with cause
  `host_operation_failure`.
- S00 gate outcome: zero applied publications and zero visible outcome
  terminals were proven. W07/W08 artifact exactness, one-to-one artifact to
  outcome, explicit human-visible terminal publication, ordinary transcript
  final text, authorized/API/CLI readback, isolation denial, missing-publication
  rejection, and provider-disabled replay are not claimed. The replay was
  ineligible and was not run; no `outcome_unknown` was replayed.
- Durable deterministic redacted evidence:
  `user-testing-output/plane-agents/evidence/w07-w08-376c5f-failure-extract.json`,
  SHA-256 `94d9bb71a54d1d7ea7ce20afb8d50f81db7ae0bd9523990b626e29aafe330028`.
  Raw result SHA-256 is
  `3d5bec35e65728d84e90dd6c96863327395f3fe4bed5de20aee8e9767c835e66`;
  authority SHA-256 is
  `f4cfe455a80b1c22b84af8bc9fdedd6f6361b863d425745bf2004b827ae3f9e4`;
  config SHA-256 is
  `3a5b7989b0b5002e22ff828ad768ca5546abf1e11548313bdd5acd13fbc4c8d5`.
- Cleanup proof: capacity marker absent and exact observed disposable
  containers, volumes, and networks were zero. W07/W08 remain dirty and
  unproven. No product source was changed during live collection and no
  further provider call was made.

## Wave 0CJ — exact deeper-corrected W07/W08 live stop — 2026-08-18

- Candidate: wrapper `19e514f6024a8b8fa9b563c153f60454d97e8eaf`, sole
  parent/source `ef014eac67323f91c02c73bc9e0ab38e083c1460`, branch
  `codex/plane-agent-functional-integration-20260817`.
- Exact images were API
  `plane-agent-api:g4-v13-ef014eac6@sha256:424f75846d398d7e9256933617dcecb685d65c40b059033dd9f378c594a9774e`
  and runtime
  `plane-agent-runtime:hermes-6c460f10-g4-v13-ef014eac6@sha256:ede43c620b231998391e1878f2d18a28c53e10f9b3f06320b86b65b953a9dfed`.
  Manifest SHA-256 was
  `b2624b60bfed5851ff0181ca5ae8ee198bf4dc10cc07e648f41d73171235dc8e`;
  Hermes/MCP/SDK pins were
  `6c460f10fe215718dce36dd73cda94155a9a34f8`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- Exactly one fresh serialized provider-backed assignment used
  `openai-codex/gpt-5.6-luna`, xhigh, fallback disabled, and commission
  `w07-w08-artifact-publication-readback-20260820-r4`. Scenario SHA-256 was
  `13bb571f54261edab311cec379c0a0c59c1527cb179d9762f689dee5e9924dc2`.
  Run `7324c15a-1ce6-41d2-8794-c990f8de8edb`; invocation
  `invocation:852dd5fd-d3ca-4f89-b171-76eb0a5c7e0f`.
- Search succeeded once, but the assigned `work_item.read` returned
  `NOT_AUTHORIZED` instead of success. The separate cross-project denial and
  targetDigest correlation were not reached/proven. The provider relay then
  recorded four completed upstream `2xx` attempts followed by attempt five as
  `outcome_unknown`, `statusClass=transport`,
  `reasonSubreason=upstream_channel_closed`; the terminal event was a bounded
  `run_failure/unavailable`.
- Provider counts/effects: `5` upstream-initiated attempts,
  `2xx=4`, `4xx=0`, `5xx=0`, `transport=1`, fallback `false`, replay `0`.
  No outcome submission, artifact, publication, terminal product event,
  W08 readback, or duplicate effect was observed. The provider-disabled
  same-invocation replay was ineligible and not run; no `outcome_unknown`
  receipt was replayed.
- Durable deterministic redacted evidence:
  `user-testing-output/plane-agents/evidence/w07-w08-19e514-failure-extract.json`,
  SHA-256 `8d0b144b29a595cf22fae4bda931ed4922319904c14532684b3e854301cb0a61`.
  Raw result SHA-256 is
  `130603982bd858b2648144c9b61e136e7fa575bf99e03b09d79a11b3efb4d2de`;
  authority SHA-256 is
  `9c450daecdb7c998f36765226c74a1af02778180e54d6eab47db60f942b2c3ac`;
  config SHA-256 is
  `0580db33325a9123117a6621eb2c16a1546e66485fb664d5ffc4f40158fb7c93`.

## Wave 0CK — exact v14 W07/W08 authority-window repair — 2026-08-18

- Root classified the earlier `authority_expired_or_invalid_window` as
  pre-provider workflow friction. The existing
  `tools/prepare-agent-g4-live-inputs.py` seam now derives a current UTC
  authority window with a one-minute backdate and 24-hour TTL; no hard-coded
  expired date remains. `tools/tests/test_agent_g4_live_launch.py` adds two
  date-advancement regressions.
- Fixed config-only preflight passed for wrapper
  `11ea756e31f6cb55a61895cd461fd808903be95e`, source
  `d4316b79272254b61d038a65cba6a9860a6afeeb`, and manifest SHA-256
  `9bd54c851430fc1b3efe29992c59db5ac4e8c291ebce05be21a81d2d12c8f714`.
  Focused tests passed `192`; exact-image red-team passed. Provider attempts,
  provider effects, and Plane product effects were all `0`.
- Canonical redacted fix receipt:
  `user-testing-output/plane-agents/evidence/w07-w08-v14-authority-window-fix.json`,
  SHA-256 `3711d62ac0f080e5ae12201841d8a8da1fdc53827ff4d4ecd0149300c9f5d715`.
  Cleanup remained exact-zero for capacity marker, verifier lock, and runner
  labels. No provider launch was made after the fix; root must integrate this
  commit before another live slot.
- Cleanup proof: capacity markers, verifier lock, and exact observed
  disposable containers, volumes, and networks were absent/zero. The first
  launcher scope rejection was pre-provider and produced no provider attempt;
  no product source was changed and no further provider call was made.

## Wave 0CK — Operator O01/O03-O09 provider-free readiness — 2026-08-18

- Source was `d4316b79272254b61d038a65cba6a9860a6afeeb`; the lane-owned commit
  is `6bf7d25cd6344ff61363d29a54b1872c045fa8ca`. The Operator descriptor
  SHA-256 is `5594c150048dc824c3ce84a1cccd163f30d9753a25d53303316bf6b45a52f6c6`.
  Its exact route set is O01 and O03-O09; O02 was preserved as clean and O10
  is outside this lane. The tested descriptor policy remains
  `openai-codex/gpt-5.6-luna`, xhigh, fallback disabled.
- Provider-free checks passed on the lane commit: Operator scenario `4
  passed, 53 deselected`, support/result/launch `23 passed`, and contract
  `110 passed`. Fresh clone checks passed full scenario `57`,
  support/result/launch `23`, and contract `110`. Native API/runtime pytest
  collection was attempted but blocked by missing `celery`; no false pass was
  recorded.
- Fresh synthetic workspace was
  `/private/tmp/plane-agent-operator-o01-o09-provider-free-ready.qwaomK`,
  checked out at the lane commit. Thirteen existing source `.env*` files were
  copied byte-for-byte to identical relative paths and compared without
  displaying values; descriptor mode was `0600`. `setup.sh` was not run.
- This batch boundary intentionally stopped before capacity acquisition,
  Compose/image work, live execution, and provider use. Provider attempts and
  effects were `0`; no O02 rerun and no `outcome_unknown` replay occurred.
  The route matrix is in the durable redacted receipt
  `user-testing-output/plane-agents/evidence/operator-o01-o09-provider-free-ready-20260818.md`,
  SHA-256 `7ebfd06c0948e00a7a5bfdbaab458dfd6db99cca2f9e8ed9dbf898a83bf139bb`.
- Handoff: `READY_WITH_COMMIT`. Root’s remaining proof is one serialized
  exact-candidate Operator journey covering O01/O03-O09 against real
  Plane/API/database/CLI/runtime contracts, with capacity lease, trusted host
  credential handling, authorization, lifecycle/replay, budget, ingress,
  concurrency/readback, and cleanup receipts.

## Manager M01-M08 provider-free batch readiness — 2026-08-18

- Source reconciliation: fast-forwarded to `d4316b79272254b61d038a65cba6a9860a6afeeb`; no Manager-owned source fix was required.
- Fresh provider-free checks: Manager/capacity contracts `8 passed`; Manager scenario contracts `7 passed`; live result/capacity support `16 passed`; direct transport probe `transport-boundary=passed remote-selection=passed fail-closed-cases=2`.
- The host unit import lacked `celery`, and the isolated container pytest setup could not resolve `test-db`; both are setup boundaries, not product/provider failures. No database-backed lifecycle rerun is claimed.
- Durable redacted receipt: `user-testing-output/plane-agents/evidence/manager-m01-m08-provider-free-ready-20260818-d431.json`, SHA-256 `38499ca381ddfe86d4a7aff6dad6f554150f20a48c72a2790d9155d7bae9c260`.
- Policy remained `openai-codex/gpt-5.6-luna`, xhigh, fallback disabled. Provider calls/live-runner attempts `0`; no Compose, live journey, replay, or `outcome_unknown` replay. Status: `READY_NO_PATCH`; root must publish the shared exact candidate before serialized live release.
## Wave 0CL — immutable v15 W03/W04 live stop and shared handoff repair — 2026-08-18

- Exactly one fresh serialized assignment used wrapper `389b25e76375d105120962ea548f8b8faaef04c3`, source `2d349c29353fc80dc0ef181cea9736b9eef8e829`, manifest SHA-256 `474f1898b1abedb29925e57cea7356434215de3484902dd8fa8234b3649c0a4a`, and descriptor SHA-256 `d32092431b2d5f5ac1cc52a5b8ef5c2e1a8433d86af2b39291e3a0afca873c8f`. No image or pin was changed.
- Run `2c576840-5fd2-4432-84a4-07d5712b416e` and invocation `invocation:95c8a5a1-70a6-4ef0-8fe1-7db94212225e` completed after eight upstream `2xx` attempts. Search succeeded once, but the assigned `work_item.read` returned `VALIDATION_ERROR`; no `work_item.rename`, Code Mode mutation, or replay was eligible. The intentional evaluator denial, one submit, one applied publication, and one visible terminal were retained, but the W03/W04 scenario gate correctly failed.
- The correlated W07/W08 failure reached the same search-to-read seam with `NOT_AUTHORIZED`. Provider-free diagnosis found that `search_workspace` returned canonical UUID input but still made the model reconstruct the outer generic `plane_operation` arguments. The owning fix adds a schema-declared `workItemReadCall` ready for the existing tool and compiles a copy-the-whole-call route instruction. The compatibility input and live gateway authorization remain unchanged; no parallel tool or authorization model was added.
- Provider-free proof passed: scenario/lease `63`, API/gateway/host/Code Mode/replay/confinement `10`, and extended contracts `173`, with zero provider attempts. Cleanup found zero live-labeled containers, networks, or volumes and no capacity lease. Durable redacted receipt: `user-testing-output/plane-agents/evidence/w03-w04-v15-389b25e7-live-stop.json`. Status: `READY_WITH_COMMIT`; W03/W04 and W07/W08 remain dirty pending root integration and a separately authorized future candidate/run.

## Wave 0CF — exact shared-v15 W05/W06 live closure

- The immutable candidate was wrapper `389b25e76375d105120962ea548f8b8faaef04c3`
  over source `2d349c29353fc80dc0ef181cea9736b9eef8e829`, using API
  `sha256:fa5aa7aabe13aa528bb15a4c10effb69c40ed98c88de88d795f23acce88f3ab1`
  and runtime
  `sha256:4f1d52367fb2175e23a9e8c278f5a3edf2795bce99cd698cca6db5194182f559`.
  Required `.env` files were copied byte-for-byte without inspecting values;
  `setup.sh` was not run. One capacity wait timed out before Compose, Plane
  assignment, or provider access and is retained as zero-value workflow
  evidence.
- Exactly one fresh `context-governance` assignment then ran under the shared
  capacity lease with `openai-codex/gpt-5.6-luna` xhigh and fallback disabled.
  Run `11483892-9a44-493c-84c4-419b5c3ba40b` and invocation
  `bd4afa32-1095-408a-8590-660ad2ba09f5` succeeded after eight completed
  upstream `2xx` attempts. The scenario and S00 gates passed with one context
  read, one outcome, one applied publication, one terminal event, and a
  provider-disabled same-invocation replay with zero new records or semantic
  effects. W05 and W06 route predicates all passed.
- The immutable receipt is owner-only at
  `tmp/persona-wave-v6/w05-w06-live-v15-389b25e7-r2/result.json`, mode `0600`,
  SHA-256 `22f961a42708e2d6df172426d967f0b146758b8f50d1de3aeb72532243f03185`.
  The post-run canonical validator found a harness-only
  `evidence_approved_thresholds_mismatch`: the invoker hardcoded an approval
  object instead of using the authority-validated thresholds. The structural
  correction forwards and parses the validated object fail-closed; focused
  provider-free checks passed `2/2` and the complete contract/scenario suite
  passed `168/168`. A provider-free reserialization changing only
  `thresholds.approved` and its derived `semanticDigest` then passed canonical
  validation `1/1`, SHA-256
  `56fa0027fa93d4390942d97caa02170d56159e1ca325b26334b446a7ceb4be58`.
  No provider rerun occurred.
- Capacity lease release and cleanup were verified with zero labeled
  containers, volumes, and networks. The bounded tracked extract is
  `user-testing-output/plane-agents/evidence/w05-w06-v15-389b25e7-live.json`.

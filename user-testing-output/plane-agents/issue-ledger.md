# Plane Agent dogfood issue ledger

Severity: `blocker`, `friction`, `annoyance`, `positive`.

| Issue  | Severity | Persona/routes | Evidence                                                                                                                                                                                                                                                                                                                                                                         | Root cause                                                                                                                                                                                                                                                                                                                                                                                                                                 | Fix owner/commit                                                                                                                                                                                                         | Retest                                                                                                                                                                                                                                                                                                                              | Status |
| ------ | -------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| UT-001 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Clean checkout has no `tmp/`; live runner creates its child without first creating the owned parent.                                                                                                                                                                                                                                                                                                                                       | `b414ad6672dd79815ae17ab19b436f2a1b45a173`                                                                                                                                                                               | Wave 0B passed this boundary                                                                                                                                                                                                                                                                                                        | closed |
| UT-002 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Resolver accepted only legacy XAI material and reduced credential failure to an unclassified transport exception.                                                                                                                                                                                                                                                                                                                          | `5872cf9664ae0266e661454601d56ade5fab9579`                                                                                                                                                                               | Wave 0C classified boundary                                                                                                                                                                                                                                                                                                         | closed |
| UT-003 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | G4 API artifact copied fixed source to `/workspace/apps/api`, but the resolver imported stale prepared-base source from `/code`.                                                                                                                                                                                                                                                                                                           | `1793f338342b93f8a1655f5131aab461d2b68b65`                                                                                                                                                                               | Wave 0D module paths passed                                                                                                                                                                                                                                                                                                         | closed |
| UT-004 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Candidate API artifact did not install `plane-agent-runtime-credential-resolver` at its configured `/usr/local/bin` path.                                                                                                                                                                                                                                                                                                                  | `642f3eebb4755a7b203f235cd9261b26d18a57ab`                                                                                                                                                                               | Wave 0E artifact proof passed                                                                                                                                                                                                                                                                                                       | closed |
| UT-005 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Resolver required a legacy nullable top-level field instead of accepting the current Codex document shape directly.                                                                                                                                                                                                                                                                                                                        | `bf39565d365b01d5ee399faa3dda3a9c938f353f`                                                                                                                                                                               | Wave 0F resolver proof passed                                                                                                                                                                                                                                                                                                       | closed |
| UT-006 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Runtime sent canonical run references while Plane's provider-attempt callback compared them with bare UUIDs.                                                                                                                                                                                                                                                                                                                               | `df7c7fb7048b1ee41577770f1ec5c07008c66824`                                                                                                                                                                               | Wave 0G binding proof passed                                                                                                                                                                                                                                                                                                        | closed |
| UT-007 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Live runner bound Plane and runtime to different credential-revocation state paths without a shared mount.                                                                                                                                                                                                                                                                                                                                 | `0467b13287043b30482213d434bf576ec77347d5`                                                                                                                                                                               | Wave 0H topology proof passed                                                                                                                                                                                                                                                                                                       | closed |
| UT-008 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Resolver imported eager Plane runtime state under a minimal child environment; Hermes child also lacked its established home defaults.                                                                                                                                                                                                                                                                                                     | `21bf76c781b4287d870475b7965c4ce9f31e5b7c`                                                                                                                                                                               | Pinned fake-provider path passed                                                                                                                                                                                                                                                                                                    | closed |
| UT-009 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Live runner hardcoded the durable frozen manifest, so a disposable exact-candidate API artifact could not share one validated binding with authority/config.                                                                                                                                                                                                                                                                               | `e26bf86cdfcda02e6a0659fc1792c8fdec665eb9`                                                                                                                                                                               | Wave 0J passed manifest boundary                                                                                                                                                                                                                                                                                                    | closed |
| UT-010 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Fresh exact-candidate runs supplied an incomplete Hermes policy because lifecycle policy resolution was permissive and supplied snapshots were not profile-bound.                                                                                                                                                                                                                                                                          | consumer `c37b17bece0b856a34894a7f0d8b54d48c7fcc71`; producer `15e3c11da2a5fd70c679a0b2d59a8ca225d1c8fd`                                                                                                                 | Wave 0L fake path passed                                                                                                                                                                                                                                                                                                            | closed |
| UT-011 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Global `--nomigrations` omitted the existing Postgres immutability triggers from the test schema, producing a false lifecycle failure.                                                                                                                                                                                                                                                                                                     | `8fac2b772911a6705ad9f500e8af54336a33ff21`                                                                                                                                                                               | migration-backed Postgres passed                                                                                                                                                                                                                                                                                                    | closed |
| UT-012 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | The live helper overrode the shared host-callback budget to zero, so first discovery failed `BUDGET_EXCEEDED` and was collapsed to opaque `RuntimeError`.                                                                                                                                                                                                                                                                                  | `7cd802caf0320b1d8698d1e539373631e835d665`                                                                                                                                                                               | literal command fake path passed                                                                                                                                                                                                                                                                                                    | closed |
| UT-013 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Live dogfood rebuilt current API source but retained a runtime image bound to old Plane source, so current-source runtime fixes may not execute in S00.                                                                                                                                                                                                                                                                                    | `125b75641b`; matched sealed-donor API/runtime build and bounded HTTP→launcher→fake-provider proof passed                                                                                                                | Wave 0O used matched artifacts                                                                                                                                                                                                                                                                                                      | closed |
| UT-014 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Wave 0AB matched the exact d2e8d541/Hermes 21826 API/runtime pair and reached the real provider with 16 contiguous completed audited `2xx` exchanges, then the live API invocation still surfaced an unspecified terminal result; no permitted read, denial, outcome, or publication was proven.                                                                                                                                           | Runtime-to-Plane terminal classification/result seam: the real post-exchange path still did not expose a finite failure code/reason through the live supervisor/command result and bounded receipt.                      | Wave 0AC exact 4f8d/Hermes 21826 bounded receipt retained and validated `runtime_error` / `runtime_execution_failed` with terminal `run_failure`; no source fix in this task.                                                                                                                                                       | closed |
| UT-015 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`                                                                                                                                                                                                                                                                                                                                                 | Wave 0Y stopped at the live runner's `credential-bind-preflight` with exit 125 before the composed Plane stack, provider relay, or product lifecycle was created.                                                                                                                                                                                                                                                                          | Live runner / local Colima Docker bind visibility for the staged owner-only provider source; no Plane source fix was made                                                                                                | Wave 0AC passed config-only validation, credential staging/bind preflight, and reached the real provider; no retry or replay.                                                                                                                                                                                                       | closed |
| UT-016 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`; bounded receipt `s00-wave0z-live-receipt.log` SHA-256 `8557b165a4c8976da7195249249925d087e0cc8e9e420ec8110f64ca1fc29f78`                                                                                                                                                                                                                       | The one fresh Wave 0Z live runner stopped at `api-invocation` with Docker exit `125`; the preserved bounded capture retained only `error_class=unspecified`, and no matching Docker create/die event exposed a more specific non-secret mount/path/flag reason.                                                                                                                                                                            | Live runner / Docker API-container start boundary. No Plane product-source fault is claimed; no API process, provider relay, or Plane lifecycle evidence was emitted.                                                    | Wave 0AC API invocation started and completed 16 provider exchanges before the finite runtime failure; no retry or replay.                                                                                                                                                                                                          | closed |
| UT-017 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`; Wave 0AA result-retention gap                                                                                                                                                                                                                                                                                                                  | Wave 0AA did not retain its bounded JSON before cleanup, so that run could not prove provider-attempt count or durable readback.                                                                                                                                                                                                                                                                                                           | Evidence handoff seam only; no product-source fault claimed.                                                                                                                                                             | Wave 0AB exact d2e8 run wrote an owner-only bounded result, hash `f998e593c8cf967c1e884756322dbbb094c3711e8522e782c2054d9af648863d`, validated it, and acknowledged deletion.                                                                                                                                                       | closed |
| UT-018 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`; Wave 0AG receipt SHA-256 `f7b771481396e7591cd5a6bc860a22cb2888437ee95e35c8b63979d3ece5588c` (0600, 3508 bytes); Wave 0AK receipt SHA-256 `8a759a859e02e4d2cd7c6506f9c4e15f2e2283e732f7c451e25c64bca5601416` (0600, 3421 bytes); Wave 0AL receipt SHA-256 `303478fa8bad6365a2e29ede26fe629f0398d2734c9963484df4ec99817ba947` (0600, 3311 bytes) | Wave 0AL proved ten completed `2xx` provider attempts, the permitted reads, one `NOT_AUTHORIZED` evaluator denial, one submit, one publish audit success, one visible `outcome_submission`, and completed RuntimeExit, but the in-process lifecycle gate failed before replay. The bounded failure schema omitted explicit applied-publication and terminal source/ref fields, so the complete publication/terminal handoff is not proven. | Conditional transcript-evidence assertion fix `577ab42b2712b78d96a46ac224f72005115f94f7`; current 0AT retest is recorded at `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6`.                                                  | 0AT passed at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` / Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`: ten ordered upstream `2xx`, required reads, exact denial, submit/applied publication/matching terminal, `RuntimeExit.completed`, eligible replay with zero semantic deltas, standalone validation, and cleanup. | closed |
| UT-019 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md`; Wave 0AI bounded runner event; Wave 0AK receipt SHA-256 `8a759a859e02e4d2cd7c6506f9c4e15f2e2283e732f7c451e25c64bca5601416`; Wave 0AL receipt SHA-256 `303478fa8bad6365a2e29ede26fe629f0398d2734c9963484df4ec99817ba947`                                                                                                                        | Wave 0AI's relative result path was rejected before execution. Waves 0AK and 0AL used fresh absolute nonexistent owner-only paths, passed that boundary, and reached API invocation; S00 remains incomplete because the Wave 0AL lifecycle gate failed before replay.                                                                                                                                                                      | The absolute owner-only result-path boundary remained accepted; current replay and cleanup evidence is recorded at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` / Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`. | 0AT persisted and validated the owner-only receipt, completed the eligible same-invocation replay with zero semantic deltas, and passed cleanup.                                                                                                                                                                                    | closed |

| UT-027 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-de9189b5/result.json` mode `0600`, SHA-256 `dc0c1cbe9ff0e71e630db320e86c5bd1ce631b63c329db0928200b5fbbcc7edb` | This fresh, isolated identity commission persisted 9 completed upstream `2xx` attempts, a succeeded run/invocation, `RuntimeExit.completed` at sequence 19, one visible `outcome_submission`, and one applied publication. Its later local scenario-gate failure was mislabeled `outcome_unknown / provider_relay / upstream_result_unavailable / reconciliation_required` by the invoker's “any initiated attempt” fallback. | Invoker evidence masking: completed provider attempts were treated as unresolved. A separate valid runtime finding is relay shutdown/audit ordering: provider body delivery and daemon handler completion could race Plane host closure. | Canonical validator passed; the old receipt remains owner-only dirty evidence and was never replayed or continued. The root fix narrows unknown classification, buffers completed provider bodies, drains relay handlers before host close, and preserves late audit failure. | open |
| UT-028 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-ca42e598/result.json` mode `0600`, SHA-256 `c798cfa136000d7dd37084ac2c3c3f8d89280075112227979693a6c357aa9004` | A second fresh isolated identity commission on the exact ca42e598 artifacts independently persisted 9 completed upstream `2xx` attempts, a succeeded run/invocation, one visible terminal, and one applied publication. It received the same later local scenario-gate failure, but the invoker again serialized `outcome_unknown / provider_relay / upstream_result_unavailable / reconciliation_required`. | Same invoker masking defect, with the independent relay shutdown/audit race retained as a separate local runtime finding; no external/provider prerequisite is established. | Canonical validation passed; the old receipt remains owner-only dirty evidence, with no replay or continuation. A fresh post-fix commission and eligible replay are still required for W01/W02. | open |
| UT-029 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-f63f2c2e/result.json` mode `0600`, SHA-256 `ff7776421e278ee560c26d42b1c5a0e072e7bf6829399754085deaed8ccbc9d4` | The first fresh post-relay-fix identity commission persisted 12 completed upstream `2xx` attempts and a succeeded run/invocation, but the runtime later failed at `agent.outcome.submit` with `CALLBACK_BINDING_INVALID` after the model supplied a conflicting redundant payload `run_ref`; no replay was eligible. | The trusted callback envelope already carried the durable run binding, but the adapter incorrectly treated untrusted model payload `run_ref` as a second binding boundary. | Plane root fix `8681f2e7db` normalizes outcome payload `run_ref` to the trusted binding, runs preflight before terminal observations, makes exact duplicate submit replay-only, returns wire-valid `PLANE_CONFLICT` for different terminal submissions/late mutations, and blocks later same-batch mutations. Hermes `cc3e444ee25e6c19fee77b6e1fbe3d95aef1a3ea` now integrates the expected conflict disposition; provider-free owner tests passed and a fresh three-commission primary is ready. | open |
| UT-030 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-579d5f04/result.json` mode `0600`, SHA-256 `ad476f7bd45ea25e34c77e0b33d375a94288c82cdaaa8ee96a29dc3200a08c2d`; `tmp/persona-wave-v6/worker-live-82b468de/result.json` mode `0600`, SHA-256 `b472d81bc7c5b9b1a17f7cfd8cfa26462e7cc7608f72cfe8cb9751f7244712e7` | Wave 0BC reached the real Luna route with fallback disabled, completed lifecycle/audit/publication evidence, and then failed before route evidence/replay because the reusable W08 probe called Plane's full admin readback projection. The first correction reduced the bound to limit 1, but a second fresh primary reproduced the bounded failure: the full projection can still exceed the established 8-KiB ceiling when it carries the outcome/admin payload. Both receipts remain dirty; B/C never started and neither primary was replayed. | Local harness/readback-boundary failure; provider and lifecycle evidence is complete, but the probe duplicated a content-bearing admin projection when W08 needs only bounded run/invocation/gateway linkage. | The reusable `tools/agent_g4_worker_route.py` probe now uses only the established limit-1 correlation readback owner, and `_run_single` calls it only for commissions whose route checks include W08; focused regressions cover both boundaries. No provider content is retained. | open |

| UT-031 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-1d4bf351/result.json` mode `0600`, SHA-256 `f810b3c05a155ea6344ee97f377ddd57a23805d0d65f0ce8d92c7f91313e8ea3` | Fresh pre-`adff362456` identity commission on API image `sha256:19da3c9df6beba6f63cdaccfadd2933fb14ef2a6801cd43c6e6f6328ad236bfd` and runtime image `sha256:2fd954fa8b7e19faa7b76ea30f7ba72716bb02e8de4ff0898a9c278490825488` persisted 13 completed upstream `2xx` attempts, a succeeded run/invocation, one exact `NOT_AUTHORIZED` evaluator denial, one submit, and one applied explicit publication. RuntimeExit then failed `budget_exhausted` / `model_call_budget_exhausted` after publication; the scenario gate additionally reported zero publication because it queried delivery-intent rows, so no replay or B/C commission was eligible. | Two distinct owners: Hermes terminal-action propagation did not stop the model loop after the applied publication, and the local harness treated `OperationGatewayPublication` delivery intents as the explicit Agent publication. The latter is not a product/provider failure. | Plane fix `adff362456` projects the validated explicit publication receipt/audit/product-event binding into scenario and replay readback, with a 139-test provider-free clump. The Hermes terminal-action/budget issue is retained as a separate owner prerequisite; no provider retry is permitted until that owner fix is integrated. | open |

| UT-032 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-1d002581/result.json` mode `0600`, SHA-256 `0f8220479186e17ff08b4ff2456b3f708ebcaf85cb7170b6ca3efc3b479f18ed` | The first fresh identity commission on the exact `1d0025816b` artifact and Hermes `f8cda105` persisted 9 completed upstream `2xx` attempts, all seven expected operations, the exact `NOT_AUTHORIZED` denial, one applied publication/terminal, `RuntimeExit.completed`, and the bounded Hermes terminal-lifecycle observation. The local wrapper then failed before W01/W02 route evidence and eligible replay because identity-only readback still parsed an empty W05 memory projection. | Commission-scoped harness readback unconditionally parsed an unowned context projection. This was local workflow logic, not a provider or Plane lifecycle failure. | Fixed by `45e6f1f9b4`, which scopes route evidence/readback to declared commission routes and adds provider-free regressions. Wave 0BF completed substitution/readback/replay; this old receipt remains dirty historical evidence and was never replayed. | closed |
| UT-033 | blocker | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-45e6f1f9/result.json` mode `0600`, SHA-256 `ee2981b521b95f2d4814d6bd2c361f7fa8b436e35c8fa0fb2769b9f20b46902` | One fresh corrected identity commission using the existing `1d0025816b` API/runtime images, Hermes `f8cda105`, and GPT-5.6 Luna xhigh with fallback disabled reached exactly one upstream-started provider attempt, which terminated as `outcome_unknown / provider_relay / upstream_result_unavailable / upstream_channel_closed`. Reconciliation proved zero gateway audits/receipts, zero outcome/publication/terminal side effects, and a visible failed/unknown terminal state. | Isolated upstream channel loss before a terminal provider result; it was distinct from the earlier completed-2xx invoker misclassification and was not reproduced by the next deliberate fresh assignment. No external prerequisite remains established. | Owner relay/lifecycle suite passed `58/58`; the old receipt was never replayed. Wave 0BF succeeded with a new AssignmentContract/RunAttempt and provider-disabled replay. | closed |
| UT-034 | positive | Maya / W01-W02 commission | `tmp/persona-wave-v6/worker-live-45e6f1f9b/result.json` mode `0600`, SHA-256 `4aab33d7e5c3eb577ccbd15d17a993132698a5dfc87016c85134b127c85cd53d` | One deliberate fresh identity commission on the exact `1d0025816b` API/runtime images and Hermes `f8cda105` passed 9 upstream `2xx` attempts, all seven expected operations exactly once, exact evaluator `NOT_AUTHORIZED`, one applied publication/terminal, `RuntimeExit.completed`, and the bounded `hermes.terminal-lifecycle/v1` observation. W01 substitution/readback and W02 discovery/readback passed; same-invocation provider-disabled replay reported zero children, attempts, invocations, receipts, audits, usage, outcomes, publications, terminal events, and semantic side effects. | Existing owner path; the only post-run local correction was validator support for the established bounded observation profile in `6087b791a4`. | Canonical validator passed with `evidence_sha256=4aab33d7e5c3eb577ccbd15d17a993132698a5dfc87016c85134b127c85cd53d`; no B/C commission ran. | closed |
| UT-035 | blocker | Maya / W03-W04/W07-W08 B commission | `tmp/persona-wave-v6/worker-live-8dae97f4-b7/result.json` mode `0600`, SHA-256 `fa7b274b0540cf1570d4b272ee8f2be0fdca6ffe7e08e4ac0e7496ab471eb3f5`; descriptor `8978a65e75377dae67824c35de2d200cfdaecd6afba20ab1785a2277eb6b94bd`; manifest `tmp/plane-agent-g4-disposable-8dae97f4.json` mode `0600`, SHA-256 `66a2dcd896051e1a0f9c1f9087a6012e4b1bf1463097568e04b7067a2a37db44` | One standalone synthetic-only B primary used API `sha256:e74be5de63d87d9ab84ac115598a82b81e94a01b27a0502eaebf547754ade412`, runtime `sha256:c369d04714c2dc6d81a79db76c0e1409c16b8060ad245a71c963a3e0b7c89fb8`, Hermes `f8cda105e3e14ace7c12f4840ec86c036fade9ad`, GPT-5.6 Luna xhigh, fallback disabled, and max 16. All 16 provider attempts completed upstream `2xx`; the run/invocation were persisted, but RuntimeExit failed non-retryably with `budget_exhausted` / `model_call_budget_exhausted` before `agent.outcome.publish`. No route evidence or replay was eligible. The bounded owner/runtime contract inspection proves W04 cannot be claimed: pinned Hermes exposes Python `execute_code`, not Plane's required restricted TypeScript Code Mode bridge. | Plane/Hermes runtime capability gap; this is not a prompt-only failure and no provider prerequisite is claimed. The next owner integration must provide the established TypeScript bridge and preserve the shared typed host callback/gateway controls. | Pending the promised Plane/Hermes TypeScript bridge commits and `b533c10fc7`; no further B/provider work or C launch is authorized until those owners are integrated and proven. | open |

## Historical wave addenda

UT-018 / Wave 0AH addendum: the exact f2858425984c2ee038fad56e88eca5ee0aa2a0ea
Plane checkout with Hermes b39be1013fd24fe05db006dc90ffc9cd05b0ca12 reached
the real `openai-codex/gpt-5.6-luna` route with fallback disabled. Fresh run
`2fab01a5-7751-495f-9db8-ba3627e72873` and invocation
`invocation:0973f573-1b0d-49d6-8c42-a85c0528eee5` retained successful Plane
run/invocation state, `search_workspace` success `3`, `work_item.read` success
`1`, evaluator denial `NOT_AUTHORIZED` `1`, submit success `1`, publish success
`1`, and terminal kind `outcome_submission`. Provider attempt sequence `5`
was `outcome_unknown` among `12` total attempts; the bounded runner failed at
`api-invocation`. Receipt SHA-256 was
`74bc53ffdad3f11bb7f8ebba705029eedefbcebdf9aad3995cea380489d60b70`
(`0600`, `3529` bytes). No retry or replay occurred because the primary was
unknown; cleanup and source cleanliness passed. UT-018 remains open and W/M/O
remain locked.

An issue is closed only after the same persona retests the real journey and the
affected route-map cells are clean. Test-only failures without user-visible or
contract impact remain verifier diagnostics rather than dogfood issues.

UT-018 / Wave 0AJ addendum: the exact b00e5e5b47c10fb2c40733ccc63dee9dd980ac85
Plane checkout with Hermes b2f1990dcf8fb9ca5a7d811fe1645420e9dafeec reached the
real `openai-codex/gpt-5.6-luna` route with fallback disabled. The fresh primary
created run `d4f5136d-6654-416f-af0f-595e2d886e8d` and invocation
`invocation:3599842d-20ca-4127-bc4a-27f4722f6cf8`, both read back as
`succeeded`, and proved `search_workspace` success `5`, `work_item.read`
success `1`, evaluator denial `NOT_AUTHORIZED` `1`, submit success `1`, publish
success `1`, and terminal kind `outcome_submission`. Provider attempts were
exactly `13`, sequences `1..13`, all completed/upstream-initiated/`2xx` with no
`outcome_unknown`. RuntimeExit was `failed` with `budget_exhausted`,
`retryable=false`, and final sequence `24`; the outer runner returned a bounded
`api-invocation` failure. The owner-only failure receipt was mode `0600`,
`3621` bytes, SHA-256
`037c724c2e901d8fc350c44cd70cba7e17896dd0564e91a3b64034cad5cc79ef`, validated,
and deleted. No retry or replay occurred because the primary was not fully
successful. The receipt did not retain transcript/publication separation
fields, so UT-018 remains open and W/M/O remain locked.

UT-019 / Wave 0AJ retest: the runner accepted the new absolute fresh
owner-only result path `/tmp/plane-agent-s00-0aj.s44tr8/result.json` with parent
mode `0700`, and the path was absent before start. The primary crossed the
result-path boundary and reached the provider, so the Wave 0AI relative-path
failure was not repeated. Per the wave gate, UT-019 remains open until the
full S00 success and replay predicate are satisfied; no retry was made after
the bounded primary failure.

UT-018 / Wave 0AM addendum: the exact Plane `4ba604571d9582c8fabaf96f7bd457e67511b076`
checkout with exact Hermes `d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` ran one
fresh primary through the real `openai-codex/gpt-5.6-luna` ChatGPT subscription
route with fallback disabled. The run and invocation read back as succeeded;
the journey created the isolated workspace and `G4 Live Issue`, proved three
workspace searches, one permitted work-item read, one `NOT_AUTHORIZED`
evaluator denial, one submit, one applied publish binding, one visible
`outcome_submission`, ordinary transcript evidence separate from publication,
and `RuntimeExit.completed`. There were nine provider attempts, all completed
upstream `2xx`, with none unknown. The ordered internal `s00Gate` passed and
the one exact same-invocation provider-disabled replay passed with every
requested durable and semantic delta at zero. The owner-only success receipt
was `0600`, `6141` bytes, SHA-256
`a8fc92228be09d67353a4dc277564ce54c1d9001eb72342672c27ece87f75a7f`.
However, standalone live-evidence validation rejected the receipt as
`evidence_permitted_canary_failed` because the fresh authority used unique
canary IDs while the runner emitted fixed IDs. The receipt also did not retain
the ordered `s00Gate` projection or semantic digest required for this journey.
UT-018 remains open; no source fix, rerun, or Hermes modification was made.

UT-019 / Wave 0AM retest: the fresh absolute result path
`/tmp/plane-agent-s00-0am.s2aWOI/result.json` was absent before start under a
`0700` owner-only parent, and the persisted receipt was `0600` and bounded.
The receipt was validated for shape and hash, then deleted and absence was
acknowledged after the evidence update. Because the final S00 evidence
contract failed, UT-019 remains open; no retry or second replay was made.

UT-018 / Wave 0AN addendum: the exact Plane
`f8e4c98fe6e44577465c317fb75b61ba43c4fb36` checkout with exact Hermes
`d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` ran one fresh primary through the
real `openai-codex/gpt-5.6-luna` ChatGPT subscription route with fallback
disabled. The run and invocation succeeded and proved the permitted reads,
one `NOT_AUTHORIZED` evaluator denial, one submit, one applied publish binding,
one visible `outcome_submission`, separate transcript evidence, and
`RuntimeExit.completed`. There were ten completed upstream `2xx` attempts with
none unknown. The ordered internal `s00Gate` passed, and the one exact
same-invocation provider-disabled replay passed with all durable and semantic
deltas at zero. The owner-only receipt was `0600`, `8179` bytes, SHA-256
`08cf95cbf8c2ffc6e9ed32ce9cad15e73b3c24e82fc85fac5160b9c9f1ecd39`, with
semantic digest
`e5b4ac2dcdd56a63455406ac3a2fcef650e24ce47142a2bb8f97d89b0086122b`.
Standalone validation failed `evidence_provider_relay_mismatch` because the
fresh authority/config omitted the provider-relay projection present in the
receipt. UT-018 remains open. No source fix, descriptor repair, or rerun was
made.

UT-019 / Wave 0AN retest: the fresh absolute result path
`/tmp/plane-agent-s00-0an.V5p5OI/result.json` was absent before start under a
`0700` owner-only parent. The persisted receipt was owner-only and under the
16 KiB bound. Hashing completed, but standalone receipt validation failed at
the provider-relay binding predicate, so the handoff and full S00 close are
not proven. Cleanup removed the receipt and all disposable artifacts after
validation and hashing. UT-019 remains open; no retry or second replay was
made.

UT-018 / Wave 0AO addendum: the exact Plane
`b83a94f61a141a8a1eb00d616d4288899236739e` checkout with exact Hermes
`d9037d5ceb17ce8f12d7abf28cfe6ee734adcb20` ran one fresh primary through the
real `openai-codex/gpt-5.6-luna` ChatGPT subscription route with fallback
disabled. Config-only preflight passed with the canonical provider-relay
projection in both authority and config. The primary reached the provider
with 13 completed upstream `2xx` attempts and no unknown attempt, and it
retained one applied publication and one visible `outcome_submission`, but
RuntimeExit was `failed` with `runtime_error` / `host_operation_failure` at
final sequence 23. The evaluator operation was `unavailable` once rather
than the required `NOT_AUTHORIZED` denial, so the complete S00 product
journey was not proven. UT-018 remains open; no retry or replay occurred.

UT-019 / Wave 0AO retest: the fresh absolute result path
`/tmp/plane-agent-s00-0ao.9EeB7D/result.json` was absent before start under a
`0700` owner-only parent. The bounded failure wrapper and JSON body passed
validation; the full owner-only receipt was `0600`, `6015` bytes, and SHA-256
`0805a26d1ce73bc2d55475709879a82702c240a7fcb81890e4543356a2e12b36`, with
semantic digest
`357392642e3e99aba24c6b60e981da201d7c868a22c2112c91ebbffa0bd34ed9`. The
receipt was deleted after validation and hashing. Because the primary failed,
the conditional replay was not eligible; UT-019 remains open and no retry or
second replay was made.

UT-018 / Wave 0AP addendum: the exact Plane
`891a1aed20344ba5a445c515bc23acd76693c93d` checkout with exact Hermes
`1d9818e7df007d2ea4f1e3df373aaa812e022e6a` ran exactly one fresh primary
through the real `openai-codex/gpt-5.6-luna` ChatGPT subscription route with
fallback disabled. The isolated workspace and `G4 Live Issue` path completed;
the bounded evidence recorded permitted `search_workspace` count `3`,
`work_item.read` count `1`, exactly one durable `agent.outcome.evaluate`
denial with `NOT_AUTHORIZED`, one submit, one applied publish, and one visible
`outcome_submission` with matching terminal/publication refs. There were ten
completed upstream `2xx` provider attempts, all provider attempts were
completed, and no fallback or unknown attempt occurred. The ordered `s00Gate`
passed invocation, run, visible terminal, applied publication, and terminal
binding, then failed only at `runtime_exit_completed`: RuntimeExit was
`failed` at final sequence `22` with non-retryable `budget_exhausted`.
Therefore the full S00 journey did not pass and no replay was eligible.
UT-018 remains open; no source fix or Hermes modification was made.

UT-019 / Wave 0AP retest: the fresh absolute result path
`/tmp/plane-agent-s00-0ap.Eor6eh/result.json` was absent before start under a
`0700` owner-only parent. The persisted two-line runner receipt was `0600`,
`5683` bytes, and SHA-256
`a5eb2c596c91a98702f3e8697cfc24f77fdc08b865bca4747058d0ccfc1f6855`.
Its standalone JSON body was `0600`, `5563` bytes, and SHA-256
`681de547b72b9e773b3a0d0876b2c06ca1f5b93e50e232420476120cbadcbbf4`; the
standalone validator passed with the exact authority, canary IDs, and
provider-relay contract. Its semantic digest was
`fb3e69b5e206ea7236a6cd719944a29b8f4ab22d3ab69b7d7a6f9846689cd6b4` and
recomputed exactly. The receipt and all disposable artifacts were deleted
after validation and hashing. Because the primary gate failed, replay deltas
are not applicable; UT-019 remains open and no retry or second primary/replay
was made.

| UT-016 | blocker | Maya / S00 | `user-testing-output/plane-agents/wave-log.md` Wave 0AR addendum | The prior task used the saved-project repository instead of the authoritative exact local clone, so the required Plane input `codex/agent-functional-dogfood` at `10eb8033ff9a01d67f5a4cf85772c2f5b464903f` was absent there and the branch resolved to `fdb2fd516dfa9b01e89d70cab0d5eb81f741af62`. | External task input/repository selection; no product-source fix authorized or attempted | Preserved by hash and reapplied onto the exact 10eb base before Wave 0AS; subsequent 0AT used the authoritative candidate. | closed |

UT-018 / Wave 0AQ addendum: the exact Plane
`131c3f73cc894ff429c45f837eb20a236e1c69de` checkout with exact Hermes
`326bc3deb5c1a15468a3104343e97e0b539dec76` ran exactly one fresh primary
through the real `openai-codex/gpt-5.6-luna` ChatGPT subscription route with
fallback disabled. The isolated workspace and `G4 Live Issue` path completed;
the bounded evidence recorded two `search_workspace` successes, one
`work_item.read` success, exactly one durable `agent.outcome.evaluate` denial
with `NOT_AUTHORIZED`, one submit, and one visible `outcome_submission`. There
were 11 completed upstream `2xx` provider attempts with no fallback or unknown
attempt. The ordered S00 gate failed first at
`one_applied_outcome_publication`: publish audit count was three and applied
publication refs were unavailable. RuntimeExit was `failed` at final sequence
21 with non-retryable `runtime_error / host_operation_failure`. No replay was
eligible. UT-018 remains open; no source fix or Hermes modification was made.

UT-019 / Wave 0AQ retest: the fresh absolute result path
`/tmp/plane-agent-s00-0aq.tPdH0a/result.json` was absent before start under a
`0700` owner-only parent. The persisted failure receipt was `0600`, `5557`
bytes, and SHA-256
`7f2d0745b7518e2bcb0be34896f90db667495c8e07b05049414bb4597f4273c3`. Its
standalone JSON body was `0600`, `5437` bytes, and SHA-256
`e99c5cca3869b91a6f96b262c685be075c551b417cc5222048b1d2f9a7a3df8e`; the
standalone validator passed with authority `s00-live-0aq-20260815`, fresh
canaries, and the canonical providerRelay. Semantic digest
`41c8c71650958ce868fe18c94bfd09726a2bff3ded517c6104ae1003abffc997`
recomputed exactly. The receipt and all disposable artifacts were deleted
after validation and hashing. Because the primary gate failed, replay deltas
are not applicable; UT-019 remains open and no retry or second primary/replay
was made.

| UT-020 | blocker | Maya / S00 | `user-testing-output/plane-agents/wave-log.md` Wave 0AS addendum | The exact live primary satisfied the projected six-predicate lifecycle gate, but the runner's full primary assertion failed because no `transcript_evidence_observed` ingress was recorded; the bounded ingress had only progress, outcome-submission, and usage events. | Runtime-to-Plane transcript-evidence ingress/readback seam after the provider exchange | Conditional assertion fix `577ab42b2712b78d96a46ac224f72005115f94f7`; 0AT retest at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` / Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`. | 0AT accepted explicit `requirement=not_required`, `status=not_observed`, `count=0`, and `eventIds=[]` without synthetic transcript text; fresh primary and eligible replay passed. | closed |
| UT-021 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-ca4237d1/result.json` mode `0600`, SHA-256 `d4952fc8435099eefde37f9bbc8e11b7b0d6594f15af84f2b4de9ef9ab2090` | The fresh real Worker reached the provider for all 16 allowed calls but exhausted its budget after repeating catalog/workspace discovery and issuing a `work_item.read` that was denied. The established `search_workspace` contract returns raw UUIDs in `workItemReadInput`; the descriptor did not require copying that object, so the model could use prefixed refs and never reached mutation, Code Mode, governance, outcome, or publication. | Worker descriptor contract and scenario regression; no gateway, Hermes, or authorization-source fault claimed | `a46bc09abc` encodes exact call order, bounded unique-title search, verbatim `workItemReadInput`, and raw-UUID guidance. Fresh exact-image Worker retest pending; no replay was eligible. | open |
| UT-022 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-89f05859/result.json` mode `0600`, SHA-256 `1702644ee843596fd63b7d269d83b0f8bca8f982324599ce27be4f6ae5195fed` | The fresh exact-image Worker reached the provider for all 16 allowed calls but terminated on a `catalog.describe` host-operation failure: `UNKNOWN_OPERATION`. The gateway's typed input requires `{"operation_id":"agent.context.read"}` exactly; the descriptor did not state the field/value and prefix rules, so the model issued a non-canonical operation identifier. The run never reached the complete W01-W08 route proof or replay. | Worker descriptor contract and scenario regression; no gateway, Hermes, or authorization-source fault claimed | `a43f124285` encodes the exact `catalog.describe` JSON shape and rejects `operationRef`/`operation:` variants in regression assertions. Fresh exact-image Worker retest pending; no replay was eligible. | open |
| UT-023 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-b06fe7aa/result.json` mode `0600`, SHA-256 `65b15a23ba880e7b9afce75bfd8f23bdf9bb0c9b2f357da8c0da6e9503ea66c0` | The fresh exact-image Worker reached the provider for all 16 allowed calls and exhausted its budget after successful catalog discovery and work-item read, without producing an `agent.context.read` receipt. The descriptor named the operation but did not bind its exact subject-user JSON input strongly enough for the model to invoke W05/W06; no complete route proof or replay was reached. | Worker descriptor contract and scenario regression; no gateway, Hermes, or authorization-source fault claimed | `113a67fb76` binds `agent.context.read` to exactly `{"subject_user_ref":"{{subjectUserRef}}"}` after descriptor substitution and adds regression assertions. Fresh exact-image Worker retest pending; no replay was eligible. | open |
| UT-024 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-acc770f2/result.json` mode `0600`, SHA-256 `a696ec4eb8c6aecd75557f90abeb4ab7393b8f8944dbe1b4934814595fabe3e2` | The fresh exact-image Worker reached the provider for all 16 allowed calls and exhausted its budget after successful `catalog.search`, `catalog.describe`, `search_workspace`, and `work_item.read`; no `agent.context.read` receipt was created. The universal eager work-core presentation let the model choose workspace/read before the prose-ordered context step because the scenario did not explicitly present its route operations. | Existing Plane profile `tool_presentation` / adaptive disclosure seam; no authorization-source, gateway, or Hermes fault claimed | `1dcf284cc7` adds typed `profile.toolPresentation.eagerOperations` to the scenario descriptor and passes it through the existing `create_profile` presentation path. Fresh exact-image Worker retest pending; no replay was eligible. | open |
| UT-025 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-a0c3854e/result.json` mode `0600`, SHA-256 `df2aae47df54da5967cd347813b95705c3e69c0fdaacb41ca64c7ef4187c639a` | The fresh exact-image Worker reached the provider for all 16 allowed calls and exhausted its budget after successful `catalog.search`, `catalog.describe`, `search_workspace`, and `work_item.read`; explicit eager operations were present but the universal work-core operation still appeared first, so the model did not reach mutation, Code Mode, governance, outcome, or publication. | Existing Plane adaptive-disclosure presentation order; no authorization-source, gateway, Hermes, or provider fault claimed | `c0890279c1` presents the explicit Worker route before the universal work core through the existing profile seam and adds a regression. Fresh exact-image Worker retest pending; no replay was eligible. | open |
| UT-026 | blocker | Maya / W01-W08 | `tmp/persona-wave-v6/worker-live-88ec3f3/result.json` mode `0600`, SHA-256 `cf54d308349e78b85d075e4d8fa6f0c45a2f362d36b2fb8565009fb7d10a774f` | The fresh exact-image Worker used all 16 upstream `2xx` provider attempts and failed at `catalog.describe` with the bounded host error `UNKNOWN_OPERATION` after three attempts. The built API artifact independently registered and successfully described both `catalog.describe` and `agent.context.read`; retained evidence does not expose the nested model input, so the exact bounded fact is target-resolution failure, with the model-facing `operationRef` versus `operationId` confusion as the non-secret root-cause inference. No context, Code Mode, mutation, evaluator, outcome, publication, or replay evidence was reached. | Model-facing catalog target handoff; no gateway registration, authorization, Hermes, or provider-route fault claimed | `969337e948` projects the next route operation's exact `operationId` into the bounded route guidance and tells the Worker to copy `operationId`, never `operationRef` or an `operation:` prefix; descriptor regressions cover the wording. Fresh exact-image Worker retest pending; no replay was eligible. | open |

UT-020 / Wave 0AS addendum: the exact rebased Plane candidate
`fa66855454093cdccc533e8587729d4f94fb2df4` (base
`10eb8033ff9a01d67f5a4cf85772c2f5b464903f`, parent
`131c3f73cc894ff429c45f837eb20a236e1c69de`) and Hermes
`4d9d4b2c76014bd74c69c79d419356f69667986d` ran one fresh primary through
the real `openai-codex/gpt-5.6-luna` ChatGPT subscription route with fallback
disabled. Seven provider attempts completed with upstream `2xx` status,
sequences `1..7`, and no unknown attempt. The bounded failure receipt passed
standalone validation and retained the exact permitted reads, one durable
`NOT_AUTHORIZED` evaluator denial, one submit, one publish, one applied
publication, one visible terminal, matching refs, and `RuntimeExit.completed`.
The runner nevertheless returned `RuntimeError` / `api-invocation` /
`unavailable` because transcript evidence was absent. No replay or retry was
run. The receipt and all disposable artifacts were deleted after validation
and hashing; UT-020 remains open.

## Wave 0AT addendum

| Issue / retest                                  | Status   | Evidence                                                                                                                                               | Disposition                                                             |
| ----------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| UT-020 stale unconditional transcript assertion | resolved | 0AT primary passed with explicit `requirement=not_required`, `status=not_observed`, `count=0`, and `eventIds=[]` when no actual assistant text existed | Close; no synthetic transcript text or product authority was introduced |

0AT is a fresh S00 `PASS`. It used one primary and one eligible provider-disabled replay. The primary had exactly 10 ordered completed `openai-codex/gpt-5.6-luna` attempts, one `NOT_AUTHORIZED` outcome-evaluate denial, one submit, one publish, one applied publication, one matching visible terminal, and `RuntimeExit.completed`. Replay deltas were zero for provider attempts, children, invocations, receipts, audits, usage, outcomes, publications, terminals, and semantic side effects. Cleanup and owner-only permissions passed. No new issue was opened.

## PF1 supporting-evidence dispositions

These commit-scoped findings are supporting evidence, not new UT issue IDs. No
new issue IDs are assigned because PF1 is provider-free evidence rather than a
provider-backed route closure.

| Finding                      | Exact evidence                                                                                                                                    | Disposition                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Dynamic-plan rationale       | Plane `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1`; M01–M08 passed 33 tests.                                                                        | Closed as PF1 supporting evidence; M01–M08 remain provider-backed pending.    |
| Schedule controls/due-fire   | Plane `2105fb9e21687103939a77b7e26a0959f1d50f51`; M01–M08 passed 33 tests.                                                                        | Closed as PF1 supporting evidence; M01–M08 remain provider-backed pending.    |
| MCP archive/unarchive        | MCP `b9581fc71dbab8d408d196a237c109e9cd61e153`; O02 external closure covered archive and unarchive.                                               | Closed in O02 route evidence.                                                 |
| MCP nested search            | MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`; O02 external closure covered search.                                                              | Closed in O02 route evidence.                                                 |
| Header/caller-binding oracle | Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`; MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`; SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. | Closed in O02 route evidence; stable bindings and SDK bearer identity passed. |

## Wave 0BH/0BI live blocker addendum

| Issue | Severity | Persona/routes | Evidence | Root cause | Fix owner/commit | Retest | Status |
| ----- | -------- | -------------- | -------- | ---------- | --------------- | ------ | ------ |
| UT-036 | blocker | Maya / W05-W08 | `tmp/persona-wave-v6/context-governance-primary-receipt/result.json` mode `0600`, SHA-256 `2bfa9d0f9518226dcd248d9b14e24bed178e458f46862c7aa24d40e6c889aade` | The synthetic-only primary on exact candidate `713fb8c685c7298cbb7fdd2b3fe965c60ba413e9` reached a coherent terminal publication with 9 completed upstream `2xx` attempts, but the local scenario gate observed two successful `agent.context.read` calls where the commission required one. No fallback, unknown attempt, replay, or production mutation occurred. | Provider-facing ordered route contract did not make the post-success transition and single complete context projection explicit enough. | Root-fixed in established scenario owner `c7e41e85dfd50398338fecbfce28b9350b229f60`; focused tools tests passed `57/57`. The receipt remains dirty evidence and was never replayed. | closed |
| UT-037 | blocker | Maya / W05-W08 | `tmp/persona-wave-v6/context-governance-rerun/result.json` mode `0600`, SHA-256 `f380048cdb0be65806fd557b828851daa36ed2fe10eb10479ca743bbac7a1196` | The one deliberate fresh post-fix C on exact `c7e41e85dfd50398338fecbfce28b9350b229f60` reached exactly one context read, all expected operation counts, one applied publication, one visible terminal, and `RuntimeExit.completed` after 7 completed upstream `2xx` attempts. The local W07 gate failed because the submitted outcome lacked the required artifact; no replay was eligible. | Commission prose required one evidence item but did not explicitly require one artifact, while the owner-side W07 gate requires both. | Root-fixed in canonical commission owner `62fd6193a0660ec2acca81e61fd91bf2af852de5`; focused tools tests remained `57/57`, and final exact API/runtime attestations were built. No additional live run was authorized; W05-W08 remain dirty. | closed |
| UT-038 | blocker | Maya / W03-W04/W07-W08 | `tmp/persona-wave-v6/worker-live-7a6983ed-b3/result.json` mode `0600`, SHA-256 `4eb7b8c7ed5fec3e542e4d573afc2d22567f380a7af0d947ad8988696e732345` | Fresh synthetic-only B reached 9 completed upstream `2xx` attempts and then failed at the real Code Mode host callback with bounded `CODE_MODE_FAILED`; RuntimeExit was non-retryable `runtime_error` at sequence 17. The receipt records no `work_item.rename`, no applied publication, and no complete readback/replay proof. | Plane Code Mode bridge/host callback path; exact failing operation receipt was unavailable, so no narrower owner is inferred. | Retain and reconcile the terminal failure; no replay or further provider use. The typed bridge root fix `76ecdd1207` passed provider-free verification, but live B proof remains pending because the next fresh launch stopped at the separate commission-selection boundary recorded as UT-039. | open |
| UT-039 | blocker | Maya / W03-W04/W07-W08 | `tmp/persona-wave-v6/worker-live-c561bdfe-b4/result.json` mode `0600`, SHA-256 `f0a9b26e18b8ab9034558638f4e67c24cc5bfd84d928ba1e5914c32e1c16ec33` | After provider-free integration of `76ecdd1207`, the one fresh launch ran the descriptor's identity commission first: it passed with 11 completed upstream `2xx` attempts and an eligible zero-delta provider-disabled replay. The requested mutation B commission then stopped before creating a run/invocation (`runRef=unavailable`) and made zero B provider attempts. | Canonical Worker descriptor/launcher executes all commissions sequentially and has no B-only selection boundary; this is workflow evidence, not a Code Mode result. | Retain receipt; no second primary or replay. W03/W04/W07/W08 remain dirty. Future B proof requires a B-only launch shape and a fresh authorized candidate. | open |

## Wave 0BK follow-up

| Issue | Severity | Persona/routes | Evidence | Root cause | Fix owner/commit | Retest | Status |
| ----- | -------- | -------------- | -------- | ---------- | --------------- | ------ | ------ |
| UT-040 | friction | Maya / W03-W04/W07-W08 | Same retained owner-only receipt, mode `0600`, SHA-256 `f0a9b26e18b8ab9034558638f4e67c24cc5bfd84d928ba1e5914c32e1c16ec33` | The multi-commission wrapper copied the first successful `live-evidence/v1` envelope into an aggregate with `status=failed`, omitting the failed commission's bounded failure contract; canonical validation rejected the bounded local stop. | Aggregate owner in `tools/agent-g4-live-invoke.py` treated the first commission as the top-level envelope regardless of aggregate status. | Fixed provider-free in `aef02407a4`; 149 harness tests passed, including a behavior-level aggregate construction plus canonical validator assertion. Raw live evidence was preserved unchanged; no provider attempt or replay was consumed. | closed |

## Wave 0BL follow-up

| Issue | Severity | Persona / routes | Evidence | Root cause / bounded disposition | Fix / retest | Status |
| ----- | -------- | ---------------- | -------- | ------------------------------- | ----------- | ------ |
| UT-041 | blocker | Maya / W03-W04/W07-W08 | `tmp/persona-wave-v6/worker-live-8d94fcc1-complete/result.json`, mode `0600`, SHA-256 `c0f869c8ceae591ce46cf5b6be4661a729f912ecb2caf842a849f76bf8fbdcbf`; manifest SHA-256 `d8d0ee728974ca6847adb840240e59e44d0478735c25a97e5320b674a09748f5` | The first identity commission passed W01/W02 and its eligible provider-disabled replay reported zero deltas. The next fresh commission created a terminally failed run/invocation, then stopped with `runtime_error / runtime_process / process_exit / runtime_execution_failed` after only two progress events. Its seven expected gateway operations all had count zero, provider attempts were zero, and no outcome, publication, artifact, terminal-success event, or semantic mutation was recorded. The retained bounded envelope exposes no narrower runtime cause; no external/provider prerequisite is inferred. | Exact functional source was `8d94fcc16e5ff161b1e128fd3fd22f6a4f851071`, API digest `sha256:428bdbab5945250fcd5ae3056f0a519cac8b0a0ecc8d03b948ecf26842abf752`, runtime digest `sha256:6feabe70129e61d9de9c11045180bd839ea709f9a3d2b390f417fc3de71988ed`, Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`. Canonical validator passed; the failed commission was not replayed and further provider use stopped. | open |

## Wave 0BM retest — runtime-isolation candidate

UT-041 remains the same bounded blocker after provider-free integration of
`15ab1c7f45` as `69601e97fb` and manifest-pin correction `94ed3da998`; no new
issue is opened. The fresh owner-only receipt is
`tmp/persona-wave-v6/worker-live-94ed3da9/result.json`, mode `0600`, SHA-256
`fac0e62ee92e42d0bba32698ec91f5661405ad8b9edbbcbe82483aa0b13c1a44`. It
records identity W01/W02 success plus a zero-delta provider-disabled replay,
then a mutation commission failure before W03/W04/W07/W08 execution with
`runtime_error / runtime_process / process_exit / runtime_execution_failed`,
two progress events, zero provider attempts, and no semantic side effect.
The failed run is `9c2eb4cf-9bb8-49a2-a9c6-7863a0187aab` and invocation is
`invocation:72aae4f2-a351-432b-9a07-10767632778e`. The canonical validator
passed; no blind replay or further provider use occurred. The dedicated
runtime debugger owns the source correction.

## Wave 0BN follow-up

| Issue | Severity | Persona/routes | Evidence | Root cause | Fix owner/commit | Retest | Status |
| ----- | -------- | -------------- | -------- | ---------- | --------------- | ------ | ------ |
| UT-042 | blocker | Maya / W03-W04/W07-W08 | `tmp/persona-wave-v6/worker-live-587f2272/result.json`, mode `0600`, SHA-256 `d74dfab1277780f750f3c9e0a5f68c8aa8c0d9cdfe5a24a39d8e4a5115b89b91`; manifest SHA-256 `def69f5b2e18ac3b77e66907f7fa316c220ff8dd7f455d5a704caebae884ae45` | Fresh B on exact candidate `587f2272cf` and Hermes `292e866374` recorded 7 completed upstream `2xx` attempts, successful search/read, exact evaluator denial, one submit, one applied publication, a completed runtime, and one terminal product event, but no `execute_code` or `work_item.rename`. The Worker scenario gate failed at the mutation commission; W05-W08 did not continue. | First causal boundary is the provider-facing Worker commission route terminating after outcome publication without the required typed Code Mode semantic mutation. Provider-free compiler/child/host tests passed; no compiler, isolate, or host-RPC failure is inferred from the receipt. | Commits `e6962c3923` and `587f2272cf` are integrated and the exact pair is retained. Canonical validator passed; no replay or further provider use is permitted for this receipt. | open |

| UT-043 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-provider-stop.json`, SHA-256 `f757ea66823b01d7828f2248adc4e8c3406f336ba393af212340eb4c8008ff33`; raw bounded receipt SHA-256 `13d2394b78f3e5306ca2ac4d0f5e8c1b747a131abc579a5ae3f524829cc94dd3` | The one fresh single-commission C attempt stopped at `api-invocation` with bounded `ImproperlyConfigured` / `unavailable` before a commission result; provider attempts were `0`, fallback was disabled, and no replay was run. | Shared launcher/configuration boundary assigned to the common debugger/fixer. This lane does not patch that owner or make another provider attempt. | Provider-free W05/W06 checks passed 14/14 Django tests and 63/63 focused scenario/launch tests after the deterministic projection newline fix in `601749ee8f`; await the shared fix, then one fresh corrected C journey. | open |
| UT-044 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-corrected-stop.json`, SHA-256 `e2e648bc5e2fcb1ea5d2e3290a0abe46aa8e968a4e6b8a825126956cf478da89`; raw bounded receipt SHA-256 `4f485a0a582f963b9632fabcaf6db45723fe1428fc471e769b6d47351f516b90` | After integrating shared fix `e312633e08856123f5b64cd9ed6b3dddabb501ca`, the one fresh corrected C attempt still stopped at `api-invocation` with bounded `unspecified` / exit `1` / `unavailable` before a commission result. Provider attempts were `0`; W05/W06 receipts and the eligible replay were not produced. | Reopened shared launcher/runtime/config debugger. This lane performs only provider-free cleanup and ledger work and makes no second provider attempt or shared-owner patch. | Exact API/runtime refreeze, focused `160/160` host contracts, and `14/14` Django W05/W06 regression passed. The failure is retained as new owner-safe evidence; no replay or `outcome_unknown` replay occurred. | open |
| UT-045 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-second-fix-stop.json`, SHA-256 `27721c95b2c17d352f38fa0e8ed798babda6d9a5e9341b4b8af3fdd92fc2c3fe`; raw bounded receipt SHA-256 `bd65e1fd64fbb5ba77a68bc7aa3b577a49acf48bedf488d7c1e57c76e5ad517d` | After integrating second shared fix `3c4209340c7f219be76258083a595b8fba14c05c` on top of e312, the one fresh C attempt still stopped at `api-invocation` with bounded `unspecified` / exit `1` / `unavailable` before a commission result. Provider attempts were `0`; W05/W06 receipts and replay were not produced. | Shared live-migration/launcher boundary remains with the shared debugger. This lane makes no shared-owner patch, retry, or replay. | Exact API/runtime refreeze, focused `161/161` host contracts, and `14/14` Django W05/W06 regression passed. Durable owner-safe evidence is committed; W05/W06 remain open. | open |
| UT-046 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-capacity-compose-stop.json`, SHA-256 `f9ab6c461cb03e055c0219a92f8153757b897d24802e1d602ecd9c54c705a8e6`; raw bounded receipt SHA-256 `8f1f533251657b60b87549f9c5d8e5fad82d013d8af748520a2f2787b032227a` | The one fresh capacity-gated C journey stopped at the `compose` boundary with bounded `unspecified` / exit `1` / `unavailable` before provider invocation. Provider attempts/effects were `0`; W05/W06 feature receipts and replay were not produced. | Shared compose/live boundary debugger. This lane makes no shared-owner patch and no retry/replay. | Capacity integration and clean readiness passed; focused provider-free checks were `178` host and `14` Django, exact images/manifest were prepared, and cleanup was verified with no remaining lease/resources. | open |
| UT-047 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-api-invocation-stop.json`, SHA-256 `988404c2029b6e301e9fa5caf4b79a8dc4ff9bab91adb0e970d74f691444fbe1`; raw bounded receipt SHA-256 `a5e78e674787ecad5dc623bf693331c03c9c5aedbb0de3a0b858acd98c3330b1` | The one fresh C journey on the corrected integrated candidate reached healthy dependencies and stopped at `api-invocation` with bounded `unspecified` / exit `1` / `unavailable` before the context-governance commission result. Provider attempts/effects were `0`, runtime events were `0`, and no W05/W06 feature evidence or replay was produced. The retained bounded envelope exposes no narrower non-secret cause; no provider fault is inferred. | Shared API-invocation/live runner boundary. This lane makes no shared-owner patch, no provider retry, and no replay. | Exact candidate-bound images and manifest were refrozen; RabbitMQ `1/1`, capacity/result `16/16`, W05/W06 route/descriptor `6/6`, config-only preflight, descriptor validation, and receipt validation passed. Cleanup verified zero resources and no capacity lease. | open |
| UT-048 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-a50834fa-api-invocation-stop.json`; raw bounded receipt `tmp/persona-wave-v6/w05-w06-fresh-a50834fa/result.json`, mode `0600`, SHA-256 `198f8cec5a249037044d0c434e5e202ca8a0d502f150b85fc9eff61ef5f85748` | The one fresh replacement C journey on clean source `a50834fa0427600d236e9c7eafee151c1184c0a6`, exact refrozen API/runtime images, and Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1` reached `api-invocation` and stopped with bounded `unspecified` / `unavailable`, exit `1`, before the commission result. Provider attempts/effects were `0`; the fresh run and invocation failed, with no runtime events, W05/W06 receipts, outcome, publication, or replay. | Shared API-invocation/live runner boundary remains the first genuine local product failure. This replacement lane makes no source patch, no provider retry, and no replay. | Config-only preflight, descriptor validation, runtime import/health, host-wide capacity acquisition/release, and zero-resource cleanup passed. W05/W06 remain dirty. | open |
| UT-049 | blocker | Maya / W05-W06 C commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w05-w06-c-d748-api-invocation-stop.json` SHA-256 `0eac3da74b4c5232954773c0d59b55c596bfd48cd316f45058121f1c70e7bdb0`; bounded runtime-binding probe `user-testing-output/plane-agents/evidence/w05-w06-c-d748-runtime-binding-probe.json` SHA-256 `ad03cf8f22765516f4e246dcbb3cdbe4b3f78604b94096debf04782a0bdcc8eb`; raw owner-only result SHA-256 `c1c89a7363353931b74ce0475a22557adb18c3e5e58b603d928e7e057c0fe9b` | The one fresh capacity-gated C journey on clean `d748ecbc6dd6ddba30e8de78c154f8e78af3a82c`, exact API/runtime images, and Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1` passed the exact Django runtime-binding probe: custom secret target `/run/plane-agent-runtime-secret`, owner-only mode/readability, `agent-runtime` alias, `remote`, and `RemoteRuntimeTransport`. It then stopped at `api-invocation` with bounded `unspecified` / `unavailable`, exit `1`, before the commission result. Provider attempts/effects were `0`; runtime events were `0`; no W05/W06 receipts or replay were produced. | Shared API-invocation/live runner boundary remains the first genuine local product failure after the transport binding correction. No provider fault is inferred; this lane makes no source patch, provider retry, or replay. | Capacity lease, config-only preflight, descriptor validation, runtime import/health, live receipt validation, and exact-owned Docker cleanup passed. W05/W06 remain dirty. | open |
| UT-050 | blocker | Maya / W07-W08 D commission | Durable redacted extract `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-stop.json`, SHA-256 `dc8f39c19d8cb6a041b8b606ab150eb1ac33c9954cd7aacae6667da085528528`; raw owner-only result `tmp/persona-wave-v6/worker-live-w07-w08-d-e9fad5-20260817-05a00b39/result.json`, mode `0600`, size `5553`, SHA-256 `00fe2c436cac264f23aa4bf57957ddccf0151287a3653088e68a193d1f65fa5a` | The one fresh D journey on candidate `e9fad58037d539a65b453bdc64fecc387c209fb7`, exact API digest `sha256:732ee2fc168d27833d8d82fe375f102daee4d0157bd98cd03a00508471b7f643`, and runtime digest `sha256:ad4b66ce76bd759656373c63e7585686b88f86aec1f75b408b78d2f192b1cfd1` passed config/descriptor/runtime-binding and progressed through the DB bootstrap/migrate gate, then stopped at `api-invocation` with one upstream-initiated `provider_error` and bounded `runtime_execution_failed`. Zero Plane operation receipts, artifact, outcome, publication, visible product terminal event, ordinary-text transcript observation, and W08 readback were observed. | First genuine provider/runtime failure boundary; provider use stopped immediately. No retry, blind `outcome_unknown` replay, or provider-disabled replay was run because the primary was not coherent. The provider-free invoker guard fix is separately committed as `e9fad58037`, and the missing-publication fixture correction is `d9d258715b`; no provider-facing code fix is claimed. | Owner-only result validator passed; capacity lease and exact runner-labeled container/volume/network cleanup were verified absent. W07/W08 remain dirty and unproven. | open |

UT-050 diagnosis follow-up: the durable provider-free extract is `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-diagnosis.json`, SHA-256 `1272718d80a96c2c3c9978f117eeb170bd0826a1161fb565da8cc994627730c0`. The bounded `provider_error` is a coarsened error-class projection; the exact pinned Hermes relay/Responses seam, D-shaped request probe, no-fallback outcome-unknown path, and midstream-failure path passed without proving a local Plane/Hermes defect. The retained receipt cannot distinguish remote rejection from transient upstream failure, so no fresh assignment is authorized and no source fix is claimed.

### UT-049 provider-free root-cause correction — 2026-08-17

Durable redacted evidence `user-testing-output/plane-agents/evidence/w05-w06-c-d748-ut049-provider-free-fix.json` SHA-256 `25a8688e8ad4946091f80dec1dd8054f73c2e99b333469d7c0f610d5b4b22afc` records the provider-free correction from clean candidate `d748ecbc6dd6ddba30e8de78c154f8e78af3a82c`. The exact API image reached production Django with `/run/plane-agent-runtime-secret` at mode `0600`, root ownership, `agent-runtime`, `remote`, and `RemoteRuntimeTransport` (`53776256d00d6b2c4eec108065d7a881236316fa403511aa60764c92261541e8`).

The original exit-1 boundary was proven as `AuditRoleBoundaryError` in `plane.operation_gateway.role_boundary` before runtime dispatch. The launcher had left API invocation on the privileged bootstrap database role, migrations on the bootstrap role, and post-migration audit bootstrap without enforced role separation. The smallest seam correction now gives bootstrap/migration/runtime phases their existing distinct roles and URLs, enables enforced audit bootstrap, and adds a focused contract regression. The exact checked-in invocation helper then reached the deterministic fake runtime and stopped with the expected bounded synthetic `RuntimeError / runtime_process / process_exit / runtime_execution_failed`; provider attempts/effects remained `0`, and the fake receipt proved request and credential handoff without provider contact.

Provider/live retest is still pending and no provider journey, replay, or outcome-unknown replay was run in this correction lane. The source/evidence commit is reported with the handoff.

### UT-049 fresh 64d1 W05/W06 journey and binding-probe seam — 2026-08-17

The one fresh capacity-gated `context-governance` journey started from clean
Plane `64d1ea7fe76944fffc8f66cf4738bb556f02fa94` with newly built exact API
and runtime images. Its retained owner-only result is
`tmp/persona-wave-v6/w05-w06-fresh-64d1ea7f-live/live-result.json`, mode
`0600`, 13,483 bytes, SHA-256
`9a1eaf8106ed98b4d187c8b7ffd3d61c601d2631ed80efd03216cfd993ab006a`.
The run was `c161a8be-0afe-4f1a-b41d-0c045553759e`, invocation
`invocation:ed1c1c45-5e0c-4ad9-9304-398ecfb6e09c`, and it recorded 9
completed upstream `2xx` provider attempts, 20 runtime events, one outcome,
one publication, and a completed runtime. The same commission's W05/W06
route gate passed; no separate W07, Manager, or Operator journey was started.

The required live runtime-binding proof is not accepted for this result. The
exact API-container binding command in the `64d1` launcher omitted Docker's
`-i`; an exact provider-free reproduction therefore exited `0` with empty
output without executing `agent_g4_runtime_binding_probe.py`. The bounded
reproduction and diagnosis are in
`user-testing-output/plane-agents/evidence/w05-w06-c-64d1-runtime-binding-probe.json`,
SHA-256 `227a70fff344ea2682d088ecaba61a31d2db6dc0987a5283c91d433d49269cbb`.
The corrected provider-free exact probe then passed with Django settings,
`/run/plane-agent-runtime-secret`, mode `0600`, root ownership/readability,
`agent-runtime`, `remote`, and `RemoteRuntimeTransport`. The durable live
extract is
`user-testing-output/plane-agents/evidence/w05-w06-c-64d1-live.json`, SHA-256
`a58bd6186c28be09caccfef8b54f5b8422c7391a68590ea5b0cb84daf7873203`.

The smallest root fix adds `-i` to the existing binding-probe Docker command
and adds a focused contract assertion. The red regression failed before the
fix; the focused G4 contract/live-result suites pass `115/115`. No second
provider/live journey, retry, old invocation replay, or `outcome_unknown`
replay was run. W05/W06 route closure remains withheld until a separately
authorized fresh journey validates the corrected pre-dispatch proof.

### UT-049 corrected 7466 replacement journey — 2026-08-17

The one fresh capacity-gated `context-governance` journey started from clean
Plane `74668f6d855fbea63fd57265b66410373d679d8f`, superseding the vacuous
64d1 claim. Required machine env files were copied byte-for-byte without
reading, printing, or sourcing values, and `setup.sh` was not run. Fresh exact
artifacts were API `plane-agent-api:g4-v6-74668f6d` /
`sha256:381fe4444f5b2c29b5b8d6793df15bcf090c957a54e7d47a4b713a2c31f965a7`
and runtime `plane-agent-runtime:hermes-292e8663-g4-v6-74668f6d` /
`sha256:2807188c1527b88a9fdaa0439ee61297e1f7c698a7a52d74c691114d4fbeb1a1`.
The disposable manifest SHA-256 is
`cc89e45b72fc60d86f62052558111ad465585804dba21600b6a233c0dfe408cc`.

The exact pre-dispatch API-container probe executed non-vacuously with
`settingsSource=django`, `/run/plane-agent-runtime-secret`, mode `0600`, root
ownership/readability, `runtimeHost=agent-runtime`, `transportKind=remote`,
and `transportClass=RemoteRuntimeTransport`. Durable bounded probe evidence
is `user-testing-output/plane-agents/evidence/w05-w06-c-7466-runtime-binding-probe.json`,
SHA-256 `34e8339eebc7b7e0c3281eb46645ba0926d6327fe49440648ddfdb4402f5ae4f`.
The enforced DB gate used `plane_migrator` for migration ownership,
`plane_runtime` for the production API, `plane_audit_owner` for governance,
`plane` only for bootstrap provisioning, and role separation before dispatch;
the migration leaf was `db.0144_provider_attempt_diagnostics`.

The single fresh journey used `openai-codex` / `gpt-5.6-luna` xhigh with
fallback disabled at the checked-in ChatGPT subscription destination. Run
`25966a40-bbf5-4690-af74-61124e1e798f` and invocation
`invocation:ebaedd9e-48e8-447b-8afb-b746cb9f4384` completed with 8 upstream
`2xx` provider attempts, 18 runtime events, one outcome, one publication, and
a completed runtime. The durable redacted extract is
`user-testing-output/plane-agents/evidence/w05-w06-c-7466-live.json`; its
SHA-256 is `44c0d8285e0170d61be574a3e0d5864fd8547557dba55354326952f17e649172`.
The owner-only raw result is
`tmp/persona-wave-v6/w05-w06-fresh-74668f6d-live/live-result.json`, mode
`0600`, 13,387 bytes, SHA-256
`21f457e9cd9a20d897b0111ede0ac25614550283a451e3e877d0f3225b6d72fd`.

W05 and W06 route checks passed in the single commission. No separate W07,
Manager, or Operator journey was started; the provider-disabled same-fresh
replay had zero provider attempts and zero semantic deltas. Capacity release
and exact-owned Docker cleanup passed. This supersedes the vacuous 64d1
route claim; no additional journey or replay was run.

### UT-050 W07/W08 provider-free status-family repair — 2026-08-17

The provider relay, runtime observation, Plane `RuntimeProviderAttempt`, and
readback path already used the bounded `statusClass` field. The defect was a
local projection loss: upstream 4xx/5xx responses became `error`, transport or
midstream ambiguity became `unknown`, and the bounded helper could not retain
the safe family. The smallest fix preserves `2xx`, `4xx`, `5xx`, and
`transport`, keeps legacy values accepted, and maps upstream status errors to
the existing generic `provider_error`; raw response data remains excluded.

The durable redacted provider-free result is
`user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-status-family-fix.json`,
SHA-256 `272785ec43879f85e53c43abb96b62570423950b3ed0084cf3ad745bd426ec35`.
The source fix is `cf9d2b8a205d78e0c30250464a5b4c70df90169d`; the red
regressions cover successful 2xx, real 4xx, real 5xx, transport/midstream
failure, lifecycle idempotency, Plane readback, redaction, and bounded live
validation. The committed provider-free checks passed 35 relay tests, 28
selected API relay/lifecycle tests, and 106 bounded contract tests.

No provider/live journey, provider retry, replay, or `outcome_unknown` replay
was run. Provider attempts/effects were zero. Test Compose cleanup verified
zero containers, volumes, and networks. The new contract does not make a
fresh assignment safe by itself; provider acceptance remains unverified.

### UT-051 fresh corrected W07/W08 D provider stop — 2026-08-17

The one authorized fresh D assignment started from clean Plane
`989a159cf3fa093702d6c3d61dfd3b705b6bb6a0`, whose parent is the status-family
fix `cf9d2b8a205d78e0c30250464a5b4c70df90169d`. Required env files were copied
byte-for-byte without reading, printing, or sourcing values, and `setup.sh`
was not run. The exact API/runtime images are bound by manifest
`eb49fea15cd69eb203430df7ea8fb13d286a01db9892db73c76dad46410059b5`.

The run used the authorized ChatGPT subscription route with
`openai-codex/gpt-5.6-luna` xhigh and fallback disabled. It created one fresh
run `ecd2b743-3059-40fd-a126-0f9cde45f8c4` and invocation
`invocation:adbb571f-ee73-44bf-afc3-8238a816d536`. The first and only provider
attempt was upstream-initiated, generic `provider_error`, and the lifecycle
stopped with `runtime_error / runtime_process / process_exit /
runtime_execution_failed`. The bounded attempt readback observed legacy
`statusClass=error`, so the required `4xx|5xx|transport` family was not
preserved. This is a provider-free follow-up finding at the existing
`PinnedProviderHTTPSClient` to relay classification seam, not a successful
W07/W08 result.

The bounded result is durable at
`user-testing-output/plane-agents/evidence/w07-w08-d-989a159c-result.json`,
SHA-256 `d5d9452a08cfed4af544317951ae9d05d463e6de480fc6b5c440ab0b2cb565b5`.
The deterministic redacted extract is
`user-testing-output/plane-agents/evidence/w07-w08-d-989a159c-failure-extract.json`,
SHA-256 `80112e72911b526ac1f2dcdad1a31643285c86c73e9b5fc32861df113263afc9`.
It records one attempt, zero host-operation receipts/audits, zero artifacts,
zero evidence items, zero outcomes, zero publications, zero product events,
one run-failure terminal event, and no replay. The raw result is retained only
as the owner-safe bounded receipt with SHA-256
`d5d9452a08cfed4af544317951ae9d05d463e6de480fc6b5c440ab0b2cb565b5`.

The provider-free adapter probe returned generic `ProviderRelayError` with an
empty status family for synthetic 400 and 500 responses. Focused projection
tests passed `3/3` (`103` deselected). No additional provider use, retry, or
replay occurred. Cleanup verified zero runner-labeled containers, networks,
credential/state/scenario volumes, and no capacity lease. W07/W08 remain
dirty and unproven.

| UT-052 | blocker | Maya / W07-W08 D commission | `user-testing-output/plane-agents/evidence/w07-w08-d-51c5ed07-failure-extract.json` SHA-256 `69a303c1168fdb654b9c73bd72b071255d47eaf58f719fc6133efee1be06ed2a`; raw bounded result SHA-256 `2bd1eb282ab8aedf65776e640b5d170395d7d3eb699ddebd6ada4c10869bd461` | The one deliberate fresh W07/W08-only assignment reached the real provider route after runtime binding and DB-role gates, then stopped at the first upstream-initiated generic `provider_error`. The existing bounded adapter contract now preserved `statusClass=4xx`; the run failed before any Plane operation or W07/W08 product effect. | Present evidence supports a provider-side or external 4xx rejection, with no local Plane lifecycle defect established. Do not retry or replay this terminal failure. | Retain the owner-safe result and redacted extract; a future fresh assignment requires new authorization after provider/service disposition. No feature pass is claimed. | open |
| UT-053 | repair | Maya / W07-W08 provider-free contract | `user-testing-output/plane-agents/evidence/w07-w08-provider-reason-subreason-45966c9c.json` SHA-256 `7639bf93b520c76b5e16d29d49499b20c1f12f48123770576a9c517346c9cb2c`; source fix `e46635f6727c39f15ee0915e452ebc2aa2c21e28` | Reused the existing typed `reasonSubreason` seam to distinguish bounded request rejection, auth, rate limiting, upstream unavailability, and existing transport diagnostics while preserving `provider_error`, status-family redaction, lifecycle idempotency, and API/CLI readback. The serial lifecycle failure was fixture/assertion friction, not a provider or product failure. Provider attempts/calls/replays were `0`. | Provider-free contract and runtime checks are green, but prior live W07/W08 ended in an external/provider 4xx and remains unresolved. Do not start or replay a live assignment from this task. | Keep W07/W08 unproven/dirty; root may authorize exactly one new assignment only after external provider disposition and clean gates. | open |

## Operator O04/O06 reconciliation — 2026-08-17

The lane is based on current functional-chain tip
`358de27c956cfa52a8fa47c6d1b8114c87b0b83a`; descriptor commit
`808e042b0ef3cdef77cfc0b0a86eb65beeacf85c` contains only O04/O06. Requested
transport fix `7a08dd2611f9b5a6c5d35ac3887573d649b7a4d4` is patch-equivalent to
current-chain commit `a50834fa0427600d236e9c7eafee151c1184c0a6`. The pure
transport probe passed; native pytest collection was blocked by missing
`celery`. Focused readiness passed `16 + 7 + 4`, with the support suite's
transient ordering result cleared by focused rerun, ten repetitions, and a
fresh full pass. No provider/live/Compose/setup/O02/clean-route run occurred.
Durable receipt:
`evidence/operator-o04-o06-reconciled-ready-20260817.md`, SHA-256
`e0a04a4bbc1b38218360db5f96d72746ba82f124876d249fb8d662782e9e72ee`.
O04/O06 remain dirty/partial and ready-only.

## Manager M01-M08 reconciliation — 2026-08-17

No new UT issue is opened. The integrated Manager evidence preserves the
provider-free M01-M08 route receipt and the two historical pre-provider stops:

- `manager-m01-m08-provider-free-receipt.json`, SHA-256
  `f1708324491a15274062c3a2632622598c68b766ffde2796e2df9576225cd9e5`;
  M01-M08 supporting predicates passed and replay mutations were `0`.
- `manager-m01-m08-fresh-live-failure.json`, SHA-256
  `f393de463dbe7d7f0987a56168bdc2a719c8b40770c4079665970cd14c838037`;
  the fresh attempt stopped at `api-invocation` with zero provider attempts
  and zero route mutations.
- `manager-m01-m08-fresh-live-failure-02.json`, SHA-256
  `425af754560420a924a7f5de8d6100bf8653c3dfece73ccd5185d02003cb4014`;
  the second fresh attempt stopped at `migrate` with the same zero-effect
  disposition.

Capacity, shared-fix, and transport readiness extracts are also retained:
`manager-m01-m08-capacity-ready-20260817-01.json` (SHA-256
`2d9cd6be63ff5c5c88a739e1297514499a14668f4f15a396c4b0251a227f1a98`),
`manager-m01-m08-capacity-ready-20260817-02.json` (SHA-256
`3e641870eef94553833fd9fb459df74271cea679ecde647d1bebac5c2a62d09c`), and
`manager-m01-m08-transport-ready-20260817-03.json` (SHA-256
`2ca8145210d924f1c28d4a94490dec28bda693086505fbf6b2c38723d8c41e92`).
They are provider-free readiness evidence, do not replace the existing
W05/W06 or W07/W08 issue IDs, and do not close the Manager route. M01-M08
remain provider-backed pending; no retry, replay, or new provider attempt is
authorized by this integration.

## Worker W07/W08 reconciliation — 2026-08-17

The exact Worker/W07 evidence is integrated without reopening or replacing
the existing W07/W08 issue records:

| Issue | Severity | Persona / routes | Durable evidence | Root cause / bounded disposition | Retest / status |
| ----- | -------- | ---------------- | ---------------- | ------------------------------- | --------------- |
| UT-054 | decision | Maya / W07-W08 fresh-assignment gate | `user-testing-output/plane-agents/evidence/w07-w08-fresh-assignment-gate-358de27c.json` SHA-256 `7ee48318fd710596492a16704e384a47b81688d179862e79d70d6dc9f194ea9f` | Provider-free request-shape and bounded `reasonSubreason` checks passed; the prior terminal 4xx remains an unresolved external acceptance/credential disposition. | `NO_GO`; exactly one new assignment is permitted only after external disposition, clean refreeze, and non-vacuous gates. Never replay the prior invocation. / open |
| UT-055 | blocker | Maya / W07-W08 fresh serialized D commission | `user-testing-output/plane-agents/evidence/w07-w08-d-81023308-failure-extract.json` SHA-256 `82c45b9e9fb1d6251c6b40a0b4dc0c71ac43fcd9eeffabf66ea788adbe1703ca`; bounded result SHA-256 `cc174a868b4e38620976ee00e47e63a1fd12dc3f12375625c0443eb690ef3bfe`; decisions SHA-256 `207c3cedd8284957e4de6cd0df15806a6c95d6f15e8bd6edf50e3a5254c0c3f4` | One fresh candidate-bound assignment reached the authorized route and stopped on the first upstream `provider_error` with `statusClass=4xx` and `reasonSubreason=auth`; provider authorization remains external. | W07/W08 remain dirty/unproven; no fallback, retry, blind replay, or provider-disabled replay. / open |

No Manager, W05/W06, Operator, or existing W07/W08 issue was closed by this
merge. No further provider attempt is authorized by this integration.

## Worker W07/W08 live disposition — Wave 0CG — 2026-08-17

| Issue | Severity | Persona / route | Durable evidence | Root cause / bounded disposition | Retest / status |
| ----- | -------- | --------------- | ---------------- | ------------------------------- | --------------- |
| UT-056 | blocker | Maya / W07-W08 fresh serialized assignment | `w07-w08-c1b51-failure-extract.json` SHA-256 `6481d2bd034d7a3882099acb5f1e9c9b3607b45c0f5ec6950e633a2ca58a56e`; bounded result SHA-256 `5cc3a928042ade4de9cf0b56b4a49bad3b8b7a52050e8cc7d8f741b5eea39112`; manifest SHA-256 `7f9e46f75289b5c51190d02b908932c9959cacbaa1432c4b34c04f48c7d9d99b`; scenario SHA-256 `e9d81aed86c2ade4aa17973d19b3ee48b1193c6de4c103dcaf85736e86f147b2` | One fresh candidate-bound assignment reached eight completed upstream 2xx attempts and Plane callbacks, then stopped at `CODE_MODE_FAILED` / `runtime_execution_failed` in the `host_callback` phase with operation unavailable. This is a local Plane/Hermes host-callback failure, not a provider failure. | No retry, fallback, replay, or provider-disabled replay. W07/W08 dirty and unproven; await provider-free host-callback owner fix. / open |

The run was `db0c3e98-1df8-462c-a3dd-9d12b24c2de7` and the invocation was
`invocation:d912fca6-18a9-4f94-a021-8231b013ecdd`. Provider attempts were
`8`, all `2xx`, with fallback disabled and replay count `0`. Bounded host
receipts observed one successful workspace search, intentional denials for
work-item read and outcome evaluation, and submit/publish host receipts; the
exact lifecycle gates did not pass after the Code Mode failure. No W08
readback or duplicate-effect claim is made. The capacity marker and all
observed disposable Docker resources are absent/zero after cleanup.

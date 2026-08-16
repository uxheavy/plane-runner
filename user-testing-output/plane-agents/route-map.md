# Plane Agent functional coverage map

Target: functional image candidate `8d94fcc16e5ff161b1e128fd3fd22f6a4f851071`; the current host-side
aggregate-reconciliation tip is `aef02407a4`; the current Wave 0BL evidence is
recorded below, with Hermes
`292e866374ca9e9615473fc9bf5dda1913b672e1`. No chat UI is in scope.
Use existing Plane object/settings pages only where they already exist; the
authoritative evidence is Plane product-state and gateway/audit readback.

Status values: `untested`, `clean`, `dirty`, `blocked`, `not-supported`.

For S00, a provider attempt means one upstream model exchange. The journey
requires one fresh Plane invocation with bounded, ordered, audited provider
exchanges; a tool-using loop may legitimately contain several exchanges.

Every route must retain the assignment/run/invocation refs, provider attempt,
gateway receipts, durable product records, terminal product event, denial or
failure evidence, replay result, and cleanup result. A fixture or unit test does
not change a route to `clean`.

Latest S00 route result: Wave 0AT is `clean` / `PASS` at Plane
`dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` with Hermes
`bc7f13d2ab392752f2667b176c646339c49405f9`. One fresh GPT-5.6 Luna primary
recorded ten ordered upstream `2xx` attempts, `search_workspace` three times,
`work_item.read` twice, one exact `NOT_AUTHORIZED` evaluator denial, one
submit, one applied publication, one matching terminal, and
`RuntimeExit.completed`. One eligible same-invocation provider-disabled replay
passed with zero semantic deltas, and cleanup passed. Initial W/M/O tasks found
that the accepted runner exposes only the fixed S00 commission; the runner is
gaining one typed persona-scenario input before those routes resume. No W/M/O
result is inferred.

Latest Maya Worker campaign: Wave 0BA used the preceding exact candidate and
the three bounded commissions. Two independent fresh identity commissions
reached the real `openai-codex/gpt-5.6-luna` route with fallback disabled and
persisted nine completed upstream `2xx` attempts each; their later local
scenario-gate failure was misclassified by the invoker and remains dirty
evidence. The first fresh post-relay-fix W01/W02 commission on `f63f2c2e` also
reached the provider (12 completed upstream `2xx` attempts), but its local
runtime failed when the old adapter treated a model-supplied redundant
`input.run_ref` as a binding error. Plane checkpoint `8681f2e7db` now binds
run identity from the trusted callback envelope, normalizes payload `run_ref`,
preflights before terminal observations, returns truthful terminal conflicts,
and blocks later same-batch mutations. Hermes owner
`cc3e444ee25e6c19fee77b6e1fbe3d95aef1a3ea` now treats the expected terminal
`conflict` / `PLANE_CONFLICT` disposition as a nonfatal tool result. W03-W04
remain `dirty` and unreached; W05-W08 were attempted in the current delegated
C addendum below and remain `dirty` pending a full route-plus-replay proof; no
old receipt is retroactively clean. Wave 0BC's identity
commissions completed their durable lifecycle but exposed local bounded
readback failures. The fresh `1d4bf351` identity primary reached one applied
explicit publication after 13 completed upstream `2xx` attempts, then ended
`budget_exhausted` after publication; its scenario projection also used the
wrong delivery-intent table. `adff362456` fixes that projection by reusing
the validated explicit-publication readback. The standalone B commission in
Wave 0BG then used only synthetic fixture data and reached 16 completed
upstream `2xx` attempts, but terminated at the finite model-call budget before
publication. Its retained evidence proves a runtime capability gap for W04:
the pinned Hermes path exposes Python `execute_code`, not the required Plane
TypeScript Code Mode bridge. B remains dirty and had no eligible replay; the
separate C addendum below also remains dirty after two failed primaries. Further
provider work is held after Wave 0BJ's bounded `CODE_MODE_FAILED` /
`host_callback` failure; no replay or further provider use is authorized.

Current delegated C addendum (2026-08-16): the exact synthetic-only
context-governance commission was attempted once on candidate
`713fb8c685c7298cbb7fdd2b3fe965c60ba413e9` and once as the single deliberate
post-fix fresh C on candidate `c7e41e85dfd50398338fecbfce28b9350b229f60`,
both with GPT-5.6 Luna xhigh, fallback disabled, max 16, and the host-only
provider relay. The first receipt is
`tmp/persona-wave-v6/context-governance-primary-receipt/result.json`, mode
`0600`, SHA-256 `2bfa9d0f9518226dcd248d9b14e24bed178e458f46862c7aa24d40e6c889aade`;
it had 9 completed upstream `2xx` attempts and a coherent terminal
publication, but the scenario gate found two successful `agent.context.read`
calls instead of one. The provider-free route-contract fix is `c7e41e85df`.
The post-fix receipt is
`tmp/persona-wave-v6/context-governance-rerun/result.json`, mode `0600`,
SHA-256 `f380048cdb0be65806fd557b828851daa36ed2fe10eb10479ca743bbac7a1196`;
it had 7 completed upstream `2xx` attempts, exactly one context read, exact
operation/durable terminal counts, and `RuntimeExit.completed`, but failed
only `route:W07` because the model submitted no artifact required by the
owner-side W07 gate. Neither receipt was replayed, and neither marks W05-W08
clean. The provider-free contract correction is `62fd6193a0`; final exact
attestations were built without another live run: API
`plane-agent-api:g4-v6-62fd6193`, digest
`sha256:89a6b406a12965958e550d6520a97a21935fe8d86b8c058cf372c3586f73d575`,
and runtime `plane-agent-runtime:hermes-f8cda105-g4-v6-62fd6193`, digest
`sha256:b050fbf8343f2945a2a4991ff8971e9653a0e0b141d5d623c8a7533120d77620`.
W05, W06, W07, and W08 remain dirty pending a separately authorized fresh
proof; W03 and W04 remain unreached.

Architecture checkpoint for W05/W06: `agent.context.read` remains the narrowest
existing owner seam. Plane's immutable run snapshot carries context references,
revisions, and digests, while the Hermes adapter injects only those references
and bounded guidance; it has no subject-bound projection injection seam. The
existing gateway operation binds actor/workspace/run/subject, calls
`assemble_agent_context`, and returns separate private-memory, user-preference,
and skill projections with live authorization and audit. Its existing contract
test covers the positive binding and actor substitution denial.

Latest sequential Worker attempt (Wave 0BL, 2026-08-16): Plane `8d94fcc16e5ff161b1e128fd3fd22f6a4f851071`, API
`plane-agent-api:g4-v6-8d94fcc1` / `sha256:428bdbab5945250fcd5ae3056f0a519cac8b0a0ecc8d03b948ecf26842abf752`, runtime
`plane-agent-runtime:hermes-292e8663-g4-v6-8d94fcc1` / `sha256:6feabe70129e61d9de9c11045180bd839ea709f9a3d2b390f417fc3de71988ed`, and Hermes
`292e866374ca9e9615473fc9bf5dda1913b672e1`. The fresh full descriptor used GPT-5.6 Luna xhigh, fallback disabled, max 16 per commission, and the host-only relay. Identity/discovery W01/W02 passed in the first commission and its provider-disabled same-invocation replay had zero deltas. The second mutation commission then reached a terminal `runtime_error / runtime_process / process_exit / runtime_execution_failed` with only two progress events, zero provider attempts, zero gateway-operation counts, and no outcome/publication/semantic side effect; its run and invocation were terminally failed. The owner-only aggregate receipt is `tmp/persona-wave-v6/worker-live-8d94fcc1-complete/result.json`, mode `0600`, SHA-256 `c0f869c8ceae591ce46cf5b6be4661a729f912ecb2caf842a849f76bf8fbdcbf`; manifest SHA-256 `d8d0ee728974ca6847adb840240e59e44d0478735c25a97e5320b674a09748f5`. The bounded receipt does not expose a narrower runtime cause, so this is retained as a real local failure, not an external-provider prerequisite; no retry or replay is eligible and W03-W08 remain dirty.

| ID  | Persona | Real journey and entry surface                                                                                                      | Required capabilities and visible outcome                                                                                                                                                   | Boundary/replay proof                                                                                                                                   | Status                                                                                                                                                                                                                                                                                                                                                                                                   |
| --- | ------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S00 | All     | Start the local API, worker, database, runtime image, and real Hermes service; dispatch one fresh issue assignment through API/CLI. | GPT-5.6 Luna performs a permitted read, receives a denied evaluator operation, explicitly submits one outcome, and publishes one visible terminal event.                                    | No fallback; one fresh invocation with bounded ordered provider-exchange audit; replay creates no child or semantic duplicate; task resources clean up. | clean — Wave 0AT at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` and Hermes `bc7f13d2ab392752f2667b176c646339c49405f9` passed ten ordered upstream `2xx` attempts, `search_workspace=3`, `work_item.read=2`, one exact `NOT_AUTHORIZED` denial, one submit, one applied publication, one matching terminal, `RuntimeExit.completed`, zero replay semantic deltas, standalone validation, and cleanup |
| W01 | Maya    | Create or select a worker Agent, immutable profile version, and issue assignment.                                                   | Actor identity/permissions remain separate from profile/tool presentation; run snapshots the resolved profile and assignment.                                                               | Unauthorized actor/profile substitution is denied without side effects.                                                                                 | clean — Wave 0BF fresh AssignmentContract/RunAttempt `run:2798ed55-a557-411e-baf2-0d4d8c5b2ddf` / `invocation:d9140ee4-8e74-4295-9231-805b5867573b` retained exact actor/profile/assignment separation and snapshot binding; substitution was `NOT_AUTHORIZED` with zero side effects; provider-disabled same-invocation replay had zero deltas |
| W02 | Maya    | Ask the Agent to discover and understand its assigned work across Plane objects.                                                    | Progressive catalog discovery plus bounded `search_workspace` and native reads find only authorized objects.                                                                                | Cross-project/private-page search does not leak; disclosure is not a second permission system.                                                          | clean — the same Wave 0BF primary performed `catalog.search` before `catalog.describe`, bounded `search_workspace`/`work_item.read`, and retained `hiddenObjectsAbsent=true`; all seven expected operations passed exactly once and replay had zero deltas |
| W03 | Maya    | Complete the issue with one explicit Plane mutation.                                                                                | Native semantic mutation crosses the Operation Gateway with live authorization, idempotency, bounded result, and audit.                                                                     | Exact replay returns the stable receipt and creates no duplicate mutation.                                                                              | dirty — Wave 0BJ reached `work_item.read` but recorded no `work_item.rename`; the primary failed during Code Mode before mutation proof and no replay was eligible |
| W04 | Maya    | Compose several reads and a mutation using restricted TypeScript Code Mode.                                                         | Credential-free generated TypeScript reaches Plane only through typed host callbacks and the same gateway.                                                                                  | Import, filesystem, network, process, actor-substitution, cancellation, and budget escape attempts fail closed.                                         | dirty — Wave 0BJ reached the real bridge boundary but failed with bounded `CODE_MODE_FAILED` / `host_callback`; no complete callback or negative-control proof was retained |
| W05 | Maya    | Use relevant prior context while respecting the current human subject.                                                              | Agent-private memory and subject-bound user preferences project separately into deterministic files; no cross-user or cross-Agent leakage.                                                  | Deleted/unauthorized/stale memory is excluded; projection and parse round-trip losslessly.                                                              | dirty — C addendum reached the context projection across two synthetic primaries, but neither primary passed the full route plus replay gate |
| W06 | Maya    | Use a private skill, propose an improvement, and restore a prior revision.                                                          | Plane owns skill definition/revisions; Hermes receives a projection; gardener proposal, human promotion, and rollback are visible.                                                          | Unreviewed candidate cannot enter workspace/org scope; concurrent replay is idempotent.                                                                 | dirty — C addendum retained synthetic governance evidence, but neither primary passed the full route plus replay gate |
| W07 | Maya    | Produce an artifact and finish the commissioned work.                                                                               | Artifact/evidence attaches to exactly one `OutcomeSubmission`; explicit publication creates one human-visible terminal product event while ordinary final text remains transcript evidence. | Missing publication is a lifecycle failure; replay creates no second outcome/message/event.                                                             | dirty — Wave 0BJ recorded submit/publish audit observations but zero applied publication and no eligible replay |
| W08 | Maya    | Inspect the result using API, CLI, issue page, and any reused settings/admin surface.                                               | The same actor/profile/assignment/run/invocation/outcome/artifact/event/audit state is visible and redacted appropriately.                                                                  | Cross-workspace and unprivileged readback fail closed.                                                                                                  | dirty — Wave 0BJ terminated at Code Mode host failure before complete publication/readback correlation |
| M01 | Elena   | Give a planner Agent a multi-part objective and acceptance criteria.                                                                | Agent creates an explicit dynamic plan without introducing a saved workflow-definition product.                                                                                             | Stale or unauthorized plan updates are rejected.                                                                                                        | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M02 | Elena   | Delegate bounded sub-work to another Agent.                                                                                         | Delegation records responsibility, lineage, scope, budget, assignee, and child assignment/run independently.                                                                                | Cross-scope lineage, recursive excess, and replay are denied or stable.                                                                                 | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M03 | Elena   | Cancel the parent while child work is queued and active.                                                                            | Cancellation reconciles queued descendants and signals active runtime controls without losing terminal visibility.                                                                          | A late child callback cannot revive or duplicate cancelled work.                                                                                        | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M04 | Elena   | Schedule recurring Agent work in a non-UTC timezone.                                                                                | Plane-owned schedule definition creates normal assignments/runs with timezone and DST semantics.                                                                                            | Concurrent fire, pause, retry exhaustion, and unknown outcome never blindly replay.                                                                     | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M05 | Elena   | Route an Agent outcome through evaluator review and then human review.                                                              | Evaluator evidence precedes human accept/revise; revision produces a deliberate fresh run while preserving earlier submission/history.                                                      | Agent cannot self-accept; stale reviewer or membership state fails closed.                                                                              | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M06 | Elena   | Propose an Agent role/profile or membership change through HR governance.                                                           | Durable proposal requires an active authorized human decision and preserves attribution.                                                                                                    | Self-approval, stale approval, and replay do not apply a second change.                                                                                 | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M07 | Elena   | Provision a chief-of-staff Agent for an authorized human.                                                                           | Exactly one role-bearing Plane Agent is created with only current scoped membership and a versioned profile.                                                                                | No copied stale/cross-workspace membership; denial leaves no partial Agent.                                                                             | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| M08 | Elena   | Inspect the complete delegated result and request a revision.                                                                       | Parent/child lineage, artifacts, outcomes, evaluator evidence, human decision, and terminal events agree across API/CLI/readback.                                                           | Revision does not mutate the frozen prior run snapshot.                                                                                                 | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O01 | Omar    | Compare a worker's exposed tools with its live Plane permissions.                                                                   | Profile affects presentation only; catalog remains complete as designed and Plane authorization is final.                                                                                   | A hidden/non-eager operation is discoverable but still denied when actor lacks authority.                                                               | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O02 | Omar    | Use external Plane MCP for representative read, mutation, search, archive/delete, denial, and unsupported actions.                  | Supported actions converge on the same gateway while preserving external human/integration identity.                                                                                        | Replay is stable; unsupported and denied actions have no semantic side effect.                                                                          | clean — real external MCP/API/database closure at Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`; read, update, replay, archive, unarchive, search, delete, denial, unsupported-before-HTTP, durable audit/idempotency, stable bindings, bearer identity, result bounds, and cleanup passed        |
| O03 | Omar    | Use the supported SDK client over bearer identity.                                                                                  | SDK result and audit boundary match native/MCP gateway semantics.                                                                                                                           | Invalid, expired, wrong-workspace, and substituted identities fail closed.                                                                              | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O04 | Omar    | Rotate/revoke/expire an Agent runtime credential while invocations are queued or active.                                            | Credential remains host-only; Plane-owned state controls lease/invocation access and redacted readback.                                                                                     | Revoked/expired credential cannot dispatch or callback; generated code never receives it.                                                               | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O05 | Omar    | Repeat dispatch, callback, gateway mutation, submission, and publication requests.                                                  | Idempotency keys produce stable receipts and exactly-once semantic effects across each boundary.                                                                                            | Mismatched replay payload or actor binding is rejected.                                                                                                 | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O06 | Omar    | Cancel, timeout, or kill the runtime before and after a provider request begins.                                                    | Pre-send failure may safely resume; post-send ambiguity becomes `outcome_unknown`; Plane/supervisor records one visible terminal product event.                                             | Unknown outcome is never blindly replayed in the same or a new run.                                                                                     | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O07 | Omar    | Exhaust model, tool, Code Mode, and total run budgets.                                                                              | Cumulative budgets span invocations and fail with bounded, inspectable product state.                                                                                                       | New invocation/container cannot reset the run budget.                                                                                                   | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O08 | Omar    | Send malformed, oversized, duplicate, out-of-order, and cross-bound runtime events.                                                 | Plane ingress validates schema, sequence, idempotency, binding, limits, authority, and legal transitions.                                                                                   | Runtime-side validation cannot bypass Plane's authoritative application rules.                                                                          | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O09 | Omar    | Run bounded concurrent gateway workload and inspect health/readback.                                                                | Error/latency/saturation thresholds, append-only audit, health, version, and rollback pins are observable.                                                                                  | Quota cleanup and safety controls preserve authority and do not delete audit history.                                                                   | untested                                                                                                                                                                                                                                                                                                                                                                                                 |
| O10 | Omar    | Roll back runtime/API artifacts and reconcile in-flight work.                                                                       | Independent last-known-good control/artifact revisions restore service without changing durable Plane ownership.                                                                            | Incompatible/cross-mixed provenance is rejected and no run depends on one container lifetime.                                                           | untested                                                                                                                                                                                                                                                                                                                                                                                                 |

## Manager M01-M08 addendum — 2026-08-16

The durable provider-free receipt
`user-testing-output/plane-agents/evidence/manager-m01-m08-provider-free-receipt.json`
(SHA-256 `f1708324491a15274062c3a2632622598c68b766ffde2796e2df9576225cd9e5`)
proves all eight Manager route predicates through the existing Plane
lifecycle/application contracts in a fresh synthetic workspace. It records
eight assignments, three child assignments, two outcomes, two artifact-backed
outcomes, three terminal events, the governance readback digest, and zero
replay state mutations. M01-M08 remain `dirty`/not provider-backed because the
one fresh post-fix live attempt stopped before Plane run/invocation creation;
the redacted failure receipt is
`user-testing-output/plane-agents/evidence/manager-m01-m08-fresh-live-failure.json`
(SHA-256 `f393de463dbe7d7f0987a56168bdc2a719c8b40770c4079665970cd14c838037`).

| Route | Current disposition |
| ----- | ------------------- |
| M01–M08 | Provider-free supporting evidence passed; provider-backed closure not established. |

The live attempt used the exact candidate-bound API/runtime pair, Hermes
`292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP
`c04974ed6624f17b41e63ef8182661929e77e0d3`, SDK
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`, Luna xhigh, and fallback disabled.
It was not replayed. The shared launcher/runtime owner retains the next
diagnosis; this lane made no shared patch.

## Manager M01-M08 second shared-fix attempt — 2026-08-16

The second fresh, non-replayed attempt used candidate
`07706d8cbf3c46cda50e25e7658d70ce970524b8` after integrating shared fix
`3c4209340c7f219be76258083a595b8fba14c05c`. It stopped in the established
runner's `migrate` phase with `errorClass=unavailable`, exit `1`, before any
Plane run/invocation or provider attempt. The durable redacted result is
`user-testing-output/plane-agents/evidence/manager-m01-m08-fresh-live-failure-02.json`
(SHA-256 `425af754560420a924a7f5de8d6100bf8653c3dfece73ccd5185d02003cb4014`);
the owner-only raw result SHA-256 is
`ebe435782d41445482b35bab585bfd6cd9ebfdc09b153cddbf70d17f97a8ac2a`.
M01-M08 therefore remain provider-free-supporting / not provider-backed
closed. No replay, blind `outcome_unknown` handling, or lane patch followed.

## PF1 supporting-evidence addendum

PF1 is provider-free supporting evidence for the pending provider-backed W/M/O
wave. It does not make W/M routes clean. The route contract still requires a
real persona journey with Plane readback, authorization evidence, replay, and
cleanup.

| Coverage                 | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                      | Route disposition                                                                 |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Worker W01–W08           | 35 real Django/API/DB/CLI/socket/isolation tests passed unchanged.                                                                                                                                                                                                                                                                                                                                                            | Supporting evidence only; W01–W08 remain dirty pending a reconciled provider-backed route. |
| Manager M01–M08          | 33 tests passed after dynamic-plan rationale fix `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1` and schedule-control/due-fire fix `2105fb9e21687103939a77b7e26a0959f1d50f51`.                                                                                                                                                                                                                                                     | Supporting evidence only; M01–M08 remain untested at provider-backed route level. |
| Operator O01 and O03–O09 | Targeted real service/API/database/CLI contracts passed. Cumulative-budget/current external-client fixtures bound at `8c9b20bf544355b20b0c9e69b0ad1ee5b48e905e` and `76e26ce5de1f300eab93505a2c885b984f60fcd0`.                                                                                                                                                                                                               | Supporting evidence only; final exact-image red team remains pending.             |
| O02 external clients     | Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Real MCP/API/database contracts covered read, update, replay, archive, unarchive, search, delete, denial, unsupported-before-HTTP, durable audit/idempotency, stable caller bindings, SDK bearer identity, and 8192 accepted / 8193 rejected result bounds; cleanup passed. | clean                                                                             |

## Wave 0AR preflight addendum

0AR did not enter S00. The required Plane input was `codex/agent-functional-dogfood` at `10eb8033ff9a01d67f5a4cf85772c2f5b464903f`, but that object was absent from the saved-project repository used by the prior task and its branch resolved to `fdb2fd516dfa9b01e89d70cab0d5eb81f741af62`. The prior writable evidence worktree was clean at that latter commit. Hermes `main` was clean at the requested `4d9d4b2c76014bd74c69c79d419356f69667986d`.

The S00 route remained `dirty`. Provider attempt count was `0` and status was `not-started`. No workspace, issue, assignment, run, invocation, runtime evidence, gateway receipt, audit row, outcome, publication, terminal event, RuntimeExit, or replay was created. Credential staging, result-destination, cleanup-label, and downstream journey predicates were not evaluated because the Plane input mismatch was a setup stop. No disposable resource was created by 0AR.

## Wave 0AS addendum

0AS used the exact local Plane source input `10eb8033ff9a01d67f5a4cf85772c2f5b464903f` with parent `131c3f73cc894ff429c45f837eb20a236e1c69de`. The preserved 0AR evidence commit `3ed36e4383598cb8f367d21b0ac5efcd3c557bb1` was reapplied as `fa66855454093cdccc533e8587729d4f94fb2df4`, whose parent is the exact `10eb...` base. Hermes `main` was clean at `4d9d4b2c76014bd74c69c79d419356f69667986d`. The resulting S00 route remains `dirty` / `FAIL`.

One non-UI primary used the real ChatGPT subscription route `openai-codex/gpt-5.6-luna` with fallback disabled and the canonical `plane.agent-runtime/provider-relay/v1` / AF_UNIX relay. One isolated workspace and `G4 Live Issue` were created. The bounded receipt retained no workspace, issue, assignment, or profile refs; those fields are not inferred. The primary recorded permitted `search_workspace` count `2` and `work_item.read` count `1`, exactly one durable `agent.outcome.evaluate` denial with `NOT_AUTHORIZED`, one explicit submit, and one explicit publish. It recorded exactly one applied publication and one visible `outcome_submission` terminal with matching run, invocation, outcome, operation-attempt, gateway-receipt, audit-receipt, receipt, and product-event refs. RuntimeExit was `completed` at final sequence `15`; run and invocation were both `succeeded`.

The primary still failed the full contract: the runner returned `1` with `RuntimeError`, phase `api-invocation`, and bounded reason `unavailable`. Its independent lifecycle assertion requires at least one `transcript_evidence_observed` event, but ingress contained only `progress_observed:14`, `outcome_submission_observed:1`, and `usage_observed:1`; ordinary model final text therefore was not proven transcript-only. There were exactly `7` provider attempts, sequences `1..7`, all completed/upstream-initiated/`2xx`, with no fallback and no unknown attempt. The provider-disabled same-invocation replay was not eligible and was not run.

The owner-only result was mode `0600`, `5362` bytes, result SHA-256 `4025352ae9000db7437161ff7747f977643e435fa367f02df1aaabc74d9665ee`; its standalone failure body SHA-256 was `8b07132f659597da04ee9884eda80ccc8991a5694ba3559be752db00c8077672`, and semantic digest was `24d0e954791747457beccd0d37b974edc0bc83fe7a3e9d7f445730cf80b2fe8b`. Authority/config/manifest SHA-256 values were `49372ce96914b1b5a68da4dfcdee5f831f1b8b1997917da4a054376aaeccfb0b` / `18a41a64c557b1bfbf3c5b441b9e32a8bd7f1ef1c278f1c039a020a2dc8e0e9c` / `836d34c90eef51a382146bd1726f6f40c1d1f96117466ce2635ba5014f7220db`. Validation accepted the bounded failure schema and exact authority/config/relay bindings. Cleanup removed the result, descriptors, run directory, task images, containers, networks, and volumes; the owner credential and authoritative clones were untouched.

## Wave 0AT addendum

0AT is `PASS` for S00. Exactly one fresh primary and one conditional same-invocation provider-disabled replay ran. No retry, second primary, verifier, rollout, deployment, UI flow, external product mutation, or source/config/test edit ran.

- Exact clean preflight: Plane `577ab42b2712b78d96a46ac224f72005115f94f7`; Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`; both authoritative trees remained untouched.
- Disposable builds: API `plane-agent-api:g4-577ab42b`, digest `sha256:456dd6545342604b264bd4958cca478890930ba7f4778b6da1f904a93ffdb7fb`; runtime `plane-agent-runtime:hermes-bc7f13d2-g4-577ab42b`, digest `sha256:663686ef7554e5f944deb56eb0b8df1c6699be24c08343acaf74cec01930a3f2`; Hermes tree digest `dfa3698f61755b288d2045684c18b9e19ff39d87440835cdf35dc37a9dd16da0`; Plane runtime source digest `1d8186a36447ea5dba5ba6cb55db48073a3be0dc976cec4ff2887418c0e33667`.
- Fresh descriptor hashes: manifest `077f6fc3a3d2be06ebd8c86c46984c621860bd4cdbcb8aed9155d72311255fd1`; authority `1ee5c9fe895779f643ab7056cee6d6e7f09ea3f726cc420186ecfda81742f72f`; config `649757463d9a72f35655be8ba23b29ec16478e00e7f863c2dfa33ccae0936c7e`. Authority `s00-live-0at-20260815`; canaries `s00-0at-permitted-20260815` and `s00-0at-denied-20260815`.
- One isolated workspace and one `G4 Live Issue` were used. Run `6a0d0f49-098f-403d-b91e-b934d7b3f049`; invocation `invocation:0a2717b1-9db8-4399-a29a-a6641f960dbf`; terminal `product-event:f12e8a0e-eb12-4f6d-bd63-8b07dd495d70`; outcome `outcome-submission:830be5e4-de4c-4948-a9d0-c37ab8fd3adb`.
- Provider was exactly the existing ChatGPT subscription route `openai-codex/gpt-5.6-luna`, fallback disabled, through `plane.agent-runtime/provider-relay/v1`, `AF_UNIX`, child network policy `none`, external egress owner `agent-runtime`, host gateway separate `true`, Hermes hook `integrated`. Exactly 10 provider attempts ran, sequences `1..10`, all completed, upstream-initiated, `2xx`, with no fallback or unknown attempts.
- Operation/audit truth: `search_workspace` success `3`; `work_item.read` success `2`; `catalog.search` and `catalog.describe` absent; exactly one durable `agent.outcome.evaluate` denial `NOT_AUTHORIZED`; one explicit submit; one explicit publish; one applied publication; one matching visible terminal; audit event count `18`. All S00 gates passed, including `RuntimeExit.completed` at final sequence `22`.
- Transcript truth: `status=not_observed`, `requirement=not_required`, `count=0`, `eventIds=[]`. No assistant text was claimed, synthesized, inferred, or granted product authority.
- The eligible exact same-invocation/same-idempotency-key replay ran with provider access disabled and passed with zero new provider attempts, children, invocations, receipts, audits, usage, outcomes, publications, terminal events, or semantic side effects.
- Owner-only result: mode `0600`, `8183` bytes, SHA-256 `9dd5bdf263a01d06927e3a07961539f3c1dca51c4a05a713899c803c8c5fac8e`; semantic digest `c8aa562cff351c86863098df47ed145df829b8c486ec1a7b6eee9eeb033d0807`. Standalone validator passed.
- Cleanup assertions passed: result, descriptors, run artifacts, staged credential, containers, networks, volumes, and disposable images were removed; no authoritative clone or owner credential was modified. S00 is clean and W/M/O may unlock.

## Wave 0BJ — exact 7a6983ed68 / Hermes 292e866374 fresh B failure

The Manager profile-refresh root fix `e3628d6f457fdb4ac5ee0e649d88f4d566bdbb72`
was integrated as Plane `9648e5181c`; its container-safe migration regression
was committed as `7a6983ed68519e8a267748998b4e8189f0fdae78`. The final exact
API image was `plane-agent-api:g4-v6-7a6983ed`, digest
`sha256:c6ead3bfbbe96cfbabe3288e1f8605f55884a050da6f81cbac0b937be87d129b`;
runtime was `plane-agent-runtime:hermes-292e8663-g4-v6-7a6983ed`, digest
`sha256:10835bb00225e4869a857c67535e27f6df4e555819831a7df56f703cf2ccd3a9`.
The manifest was mode `0600`, SHA-256
`998376b4f8d89488a5cc8bcc7e8770ee59b7d5fe4e1f79a9b67c660858c7e229`;
runtime imports, real bootstrap readiness, labels, config, and descriptor
preflight passed. Host checks were `163` passed and the focused Manager
migration regression was `1` passed.

One fresh synthetic-only B primary used GPT-5.6 Luna xhigh, fallback disabled,
and max 16 through the host-only relay. Owner-only receipt:
`tmp/persona-wave-v6/worker-live-7a6983ed-b3/result.json`, mode `0600`,
SHA-256 `4eb7b8c7ed5fec3e542e4d573afc2d22567f380a7af0d947ad8988696e732345`.
Run `fd9e4584-a2f8-4614-8598-9a2a31cc8bb3` and invocation
`invocation:ad9df00e-97db-41ae-aa48-22b70d4abb32` reached the provider and
recorded exactly 9 completed upstream `2xx` attempts, with no fallback or
unknown attempt. `search_workspace`, `work_item.read`, exact evaluator
`NOT_AUTHORIZED`, submit, and publish audit observations were present, but the
runtime ended non-retryably at sequence 17 with `runtime_error` caused by the
bounded `CODE_MODE_FAILED` / `host_callback` failure. No `work_item.rename`,
complete Code Mode receipt, applied publication, or complete W08 readback was
proven. No replay was eligible or run. The failed B receipt remains dirty
evidence; further provider use is stopped pending root-fix review.

## Wave 0BK — exact c561bdfe89 / typed Code Mode candidate commission-shape stop

Provider-free verification passed 53 descriptor tests, 24 Plane cross-process
tests, 8 Hermes bridge/host-port tests, and 1 migration-backed Manager
regression. Exact API/runtime images bound Plane `c561bdfe89` and Hermes
`292e866374`; imports and real bootstrap readiness passed.

The one fresh owner-only launch used GPT-5.6 Luna xhigh, fallback disabled, and
max 16. Receipt:
`tmp/persona-wave-v6/worker-live-c561bdfe-b4/result.json`, mode `0600`,
SHA-256 `f0a9b26e18b8ab9034558638f4e67c24cc5bfd84d928ba1e5914c32e1c16ec33`.
The descriptor still contains the three bounded Worker commissions, so the
launcher ran identity first: W01/W02 passed with 11 completed upstream `2xx`
attempts and an eligible provider-disabled zero-delta replay. The requested
mutation-composition B commission then stopped before run/invocation creation
with `runRef=unavailable` and zero B provider attempts. This is a workflow
commission-selection failure, not evidence for or against the typed Code Mode
bridge. No second primary, replay, or further provider use occurred. W03/W04/
W07/W08 remain dirty; UT-039 remains open pending a future B-only launch shape
and fresh authorized proof.

## Wave 0BK follow-up — aggregate failure envelope reconciliation

The retained raw receipt above is unchanged and remains owner-only evidence.
Its aggregate wrapper was invalid because the pre-fix launcher copied the
identity commission's successful envelope, changed only the top-level status,
and omitted the failed commission's bounded failure fields. The failed
mutation commission itself created no run, invocation, provider attempt, or
Plane semantic side effect. Provider-free root fix `aef02407a4` now promotes
the failed commission's `live-failure/v1` envelope and retains both commission
rows; the canonical validator regression passed. No provider retry, replay, or
image rebuild occurred. W03/W04/W07/W08 remain dirty and UT-039 remains open.

## Wave 0BM — exact 94ed3da998 / runtime-isolation retest

Provider-free runtime isolation fix `15ab1c7f45` was integrated as Plane
`69601e97fb`; the manifest evidence pin was refreshed in `94ed3da998`. Host
checks passed `165/165`, the sequential real-Hermes-child regression passed
`1/1`, cross-process isolation passed `24/24`, and the fresh canonical
migration checks passed `3/3`. The network-disabled runtime import gate also
passed. Exact API/runtime image bindings and owner-only input hashes are
retained in `tmp/persona-wave-v6/worker-live-94ed3da9/`.

One fresh synthetic-only three-commission Worker journey used GPT-5.6 Luna
xhigh through the authorized host-only relay, fallback disabled, and max 16
per commission. Identity/discovery passed W01/W02; its eligible
same-invocation provider-disabled replay had zero children, attempts,
invocations, receipts, audits, usage, outcomes, publications, terminal events,
and semantic side effects. The next mutation commission failed before any
W03/W04/W07/W08 operation with `runtime_error / runtime_process /
process_exit / runtime_execution_failed`, two progress events, zero provider
attempt rows, and no semantic side effect. The canonical failure receipt
passed validation. W01/W02 remain clean; W03-W08 remain dirty and
UT-041 remains open for the dedicated runtime debugger's root correction.

## Wave 0BN — exact 587f2272cf / compiler-backed Code Mode retest

Validated source commits `c21fa19c05` and `da2bae9b9c` were cherry-picked as
Plane `e6962c3923` and `587f2272cf`. The typed TypeScript child/compiler path
passed the focused source checks (`6/6`) and the exact-Hermes provider-free
gateway, real-child, sequential-isolation, and Node-resolution checks (`4/4`).
The final API artifact is `plane-agent-api:g4-v6-587f2272`, digest
`sha256:58068e1a811239ccb44cae0b24fdec9ab47d09003f76316051df90ae31ee6d14`,
with compiler label `5.4.5`; the runtime is
`plane-agent-runtime:hermes-292e8663-g4-v6-587f2272`, digest
`sha256:e28c51e321bfcfc5631ead6cf9c1b58dcd4922f66f9f35564a0f622fada5d593`,
bound to Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`. The retained
prepared base `plane-g3-external-client-api-tests:prepared-codemode-fb78`
passed the canonical compiler/pytest/ruff/source guards.

One fresh synthetic Worker journey used GPT-5.6 Luna xhigh, fallback disabled,
max 16, and the host-only relay. W01/W02 were not rerun. The mutation
commission reached `search_workspace` once, `work_item.read` once, the exact
`agent.outcome.evaluate` denial (`NOT_AUTHORIZED`), one submit, and one
applied publish/terminal event, but never produced the required typed
`execute_code` callback or `work_item.rename`. The runtime completed at
sequence 16 and the S00 lifecycle/publication gates passed, while the Worker
scenario gate failed at the mutation commission. W05/W06/W07/W08 did not run
as a clean continuation. The first causal boundary is the provider-facing
commission route ending in publication before the required mutation route;
the evidence does not establish a compiler, child-isolate, or host-RPC crash.

The owner-only receipt is
`tmp/persona-wave-v6/worker-live-587f2272/result.json`, mode `0600`, SHA-256
`d74dfab1277780f750f3c9e0a5f68c8aa8c0d9cdfe5a24a39d8e4a5115b89b91`;
canonical validation passed. Run `518bd156-9c8a-43cf-ba81-7f6c3a033fa6`,
invocation `invocation:ab6f5bf3-91d9-4c8f-9037-3823d329cfde`, publication
`outcome-submission:63678b35-d993-4f69-a758-231756d020b9`, and terminal event
`product-event:215713e2-e7d6-442d-a031-287e1f688016` are retained. There were
7 completed upstream `2xx` provider attempts, no fallback, and no eligible
replay. W03-W08 remain dirty; UT-042 is open.

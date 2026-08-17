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
| W07 | Maya    | Produce an artifact and finish the commissioned work.                                                                               | Artifact/evidence attaches to exactly one `OutcomeSubmission`; explicit publication creates one human-visible terminal product event while ordinary final text remains transcript evidence. | Missing publication is a lifecycle failure; replay creates no second outcome/message/event.                                                             | dirty — the one fresh D journey on `e9fad58037` stopped at `api-invocation` after one provider error; zero Plane operations, artifact, outcome, publication, or product terminal event were observed. Durable bounded evidence: `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-stop.json` SHA-256 `dc8f39c19d8cb6a041b8b606ab150eb1ac33c9954cd7aacae6667da085528528`; diagnosis extract: `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-diagnosis.json` SHA-256 `1272718d80a96c2c3c9978f117eeb170bd0826a1161fb565da8cc994627730c0`; no retry/replay. |
| W08 | Maya    | Inspect the result using API, CLI, issue page, and any reused settings/admin surface.                                               | The same actor/profile/assignment/run/invocation/outcome/artifact/event/audit state is visible and redacted appropriately.                                                                  | Cross-workspace and unprivileged readback fail closed.                                                                                                  | dirty — the same D journey failed before owner readback, with no correlated outcome/artifact/publication state to inspect; cross-workspace and unprivileged readback remain unproven. Durable bounded evidence: `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-stop.json` SHA-256 `dc8f39c19d8cb6a041b8b606ab150eb1ac33c9954cd7aacae6667da085528528`; diagnosis extract: `user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-provider-diagnosis.json` SHA-256 `1272718d80a96c2c3c9978f117eeb170bd0826a1161fb565da8cc994627730c0`; no retry/replay. |

## Wave 0BT — exact a50834fa replacement C stop

The single fresh `context-governance` journey used the clean corrected Plane
source `a50834fa0427600d236e9c7eafee151c1184c0a6`, API
`plane-agent-api:g4-v6-a50834fa` with digest
`sha256:0f29e02417505b3b761cad6b4af753c697e6f0d09660b8ec34933ad755456d3a`,
and runtime `plane-agent-runtime:hermes-292e8663-g4-v6-a50834fa` with digest
`sha256:68835901f97cc9671f8de722b6214ab2ef6e7a2177a164dbee969840f9563c4d`.
The runtime was bound to Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`,
MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Manifest SHA-256 is
`4bd47b4ef864c70ff6a5456c40fce100eb8050b6c338d0576d74704ec5e375f`.

Exactly one fresh provider-capable journey ran under the host-wide capacity
gate with `openai-codex/gpt-5.6-luna` xhigh and fallback disabled. It reached
`api-invocation` and stopped with bounded `unspecified` / `unavailable`, exit
`1`, before the commission result. Run
`5c154173-ad50-44b7-abe1-7207033644ed` and invocation
`invocation:33559520-3592-4650-93d8-d5a9809d5f61` are retained in the
redacted extract
`user-testing-output/plane-agents/evidence/w05-w06-c-a50834fa-api-invocation-stop.json`.
Provider attempts and effects were `0`; outcome and publication receipts were
absent; W05 and W06 feature results are `not_observed`.

The provider-disabled replay was ineligible because the primary failed before
a commission result. No retry or `outcome_unknown` replay occurred. Cleanup
verified zero containers, volumes, networks, and no remaining capacity lease.
W05 and W06 remain dirty.

## Wave 0BO — fresh C boundary stop and provider-free W05/W06 proof

The one fresh single-commission `context-governance` journey was bound to
artifact source `0d6a239a49064bba3e903d7bc41fa5e78467cbc7`, host wrapper
`3d0fd4b91fc956d8ddd75d269b3ff5d1d633f408`, Hermes
`292e866374ca9e9615473fc9bf5dda1913b672e1`, MCP
`c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The exact API/runtime image
digests and disposable manifest are recorded in the durable redacted evidence
at `user-testing-output/plane-agents/evidence/w05-w06-c-provider-stop.json`,
SHA-256 `f757ea66823b01d7828f2248adc4e8c3406f336ba393af212340eb4c8008ff33`.

The authorized provider-capable run stopped at the shared API-invocation
boundary with `ImproperlyConfigured`, exit `1`, reason `unavailable`; the
bounded owner-only receipt is hashed there as
`13d2394b78f3e5306ca2ac4d0f5e8c1b747a131abc579a5ae3f524829cc94dd3`.
Provider attempt count was `0`, fallback was disabled, and no replay was run.
The shared debugger/fixer owns this boundary; W05 and W06 remain `dirty` and
no route result is inferred from this failed setup.

Provider-free lane checks passed after the reserializer newline correction:
14/14 Django memory/skill tests and 63/63 focused scenario/launch tests. The
serializer correction is committed in `601749ee8f`; the durable extract also
records post-exit zero container, volume, and network counts for the observed
disposable Compose identifiers.
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

## Wave 0BP — exact corrected 383c8cb15b / C commission boundary stop

- Shared configuration fix `e312633e08856123f5b64cd9ed6b3dddabb501ca` was
  integrated as Plane `6636f3dd11f23be2a0da302f31b611a4756dca61`; the exact
  candidate also refreshed the current runtime evidence pin and contract
  assertion as `383c8cb15b5236ffca9ec72795b6fea0db332a1d`. Focused host
  checks passed `160/160`, and the provider-free W05/W06 Django regression
  passed `14/14`.
- One fresh single-commission `context-governance` journey used the existing
  Plane/Hermes runner with `openai-codex/gpt-5.6-luna` xhigh and fallback
  disabled. The exact API artifact was
  `plane-agent-api:g4-v6-383c8cb`, digest
  `sha256:96464ed75a750df729634f235db5c7ca5e5f8f62e43813d272a98f7b1bd13926`;
  runtime was `plane-agent-runtime:hermes-292e8663-g4-v6-383c8cb`, digest
  `sha256:e93b6d3e77d43a918072ca3c7c1db284a1eac62ab0f8b9c99541947ec06204d8`.
  Hermes, MCP, and SDK remained pinned to
  `292e866374ca9e9615473fc9bf5dda1913b672e1`,
  `c04974ed6624f17b41e63ef8182661929e77e0d3`, and
  `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`.
- The corrected run stopped at `api-invocation` with the bounded
  `unspecified` / exit `1` / `unavailable` receipt before a commission result.
  Provider attempts were `0`; no W05/W06 receipt, audit, publication, memory
  projection, preference projection, skill promotion, or rollback was
  observed. Run `4b851f81-b555-4f65-9875-eabfdc432065` and invocation
  `invocation:8c5c87f7-4d7d-4ed3-adad-8881dd0b863b` are bound in the durable
  redacted extract
  `user-testing-output/plane-agents/evidence/w05-w06-c-corrected-stop.json`,
  SHA-256 `e2e648bc5e2fcb1ea5d2e3290a0abe46aa8e968a4e6b8a825126956cf478da89`;
  the owner-only raw result SHA-256 is
  `4f485a0a582f963b9632fabcaf6db45723fe1428fc471e769b6d47351f516b90`.
- The provider-disabled same-invocation replay was not eligible because the
  primary stopped before a commission result. It was not run, and no
  `outcome_unknown` receipt was replayed. Per the reopened shared-debugger
  boundary, this lane makes no launcher/runtime/config patch and no further
  provider attempt. Cleanup was verified at zero containers, volumes, and
  networks for all observed disposable project identifiers.
- W05 and W06 remain dirty; this is provider-free boundary evidence, not route
  closure.

## UT-053 W07/W08 provider-free reasonSubreason contract repair — 2026-08-17

The latest serial lifecycle failure was local workflow/test friction: a
terminal 4xx fixture expected transport and omitted the required
`reasonPhase=provider_relay`. The fixture and assertion were corrected without
provider use. The bounded `reasonSubreason` field already present in the
Plane/Hermes lifecycle contract was reused; no new field, mutation path, or
runtime authority was introduced.

The fix is committed as
`e46635f6727c39f15ee0915e452ebc2aa2c21e28`, parent
`45966c9c4e39e63d9b6ea99bbc92fa104424650f`. It maps only safe families:
request rejection, authorization rejection, and rate limiting remain 4xx;
upstream unavailability remains 5xx; transport retains the existing bounded
diagnostic and outcome-unknown semantics. Public `errorCode` remains
`provider_error`; raw status, body, headers, URL, credentials, prompts, and
model output are not retained. API and CLI readback now preserve the existing
bounded reason field, while legacy evidence remains accepted and unbounded
values are rejected.

Durable redacted evidence is
`user-testing-output/plane-agents/evidence/w07-w08-provider-reason-subreason-45966c9c.json`,
SHA-256
`7639bf93b520c76b5e16d29d49499b20c1f12f48123770576a9c517346c9cb2c`.
Provider attempts, provider calls, and replays were `0`. Host evidence and
contract suites passed `180`; the serial Docker provider/runtime/lifecycle
selection passed `185` with `4` environment-bound cases deselected. Compose
cleanup returned exit `0` and removed the test network and runner containers.

This provider-free repair does not prove W07/W08 product behavior and does not
make a fresh live assignment safe by itself. A root-authorized future run
requires external provider disposition and clean runtime/DB gates, must use a
new assignment, and must never replay a prior invocation.

## UT-054 W07/W08 fresh-assignment gate decision — 2026-08-17

The exact-request proof and the bounded `reasonSubreason` contract reconcile
without a local request/auth/config defect. The deterministic D-shaped probe
matched the native path, validated request and tool schemas, enforced
`store=false`, observed no relay secret, and completed against the fake runtime
without provider dispatch. The W05/W06 reference used the same
`openai-codex`/`gpt-5.6-luna` xhigh policy, ChatGPT Responses route, and
fallback-disabled setting.

Fresh provider-free verification passed host contract/evidence suites `180/180`
and serial relay/lifecycle/API checks `17/17` (`87` deselected). No provider
call, attempt, or replay occurred. Durable redacted evidence is
`user-testing-output/plane-agents/evidence/w07-w08-fresh-assignment-gate-358de27c.json`,
SHA-256
`7ee48318fd710596492a16704e384a47b81688d179862e79d70d6dc9f194ea9f`.

Decision: `NO_GO` for a new assignment now. The smallest missing condition is
one current authoritative external disposition that the exact pinned route,
model policy, and credential/subscription authorization are accepted. After
that disposition, the candidate must be refrozen and pass non-vacuous
runtime/DB/capacity gates before exactly one new assignment. The prior terminal
4xx run is not `outcome_unknown`, but it cannot be retrospectively classified
by the new reason field and must never be replayed.

## Current W07/W08 D route — 2026-08-17

- W07 and W08 remain `dirty`. One fresh single-commission W07/W08-only
  assignment from Plane `51c5ed07e6d5d46fda7acb9794805de45231b2f7` reached the
  real provider path after the non-vacuous runtime binding and DB-role gates.
  It stopped on the first upstream-initiated `provider_error` with bounded
  `statusClass=4xx`; no Plane operation, artifact, outcome, publication,
  terminal product event, transcript evidence, or W08 readback was observed.
- No retry, fallback, blind `outcome_unknown` replay, or provider-disabled
  replay was attempted because the primary was terminally failed. Durable
  bounded evidence is
  `user-testing-output/plane-agents/evidence/w07-w08-d-51c5ed07-failure-extract.json`
  (SHA-256 `69a303c1168fdb654b9c73bd72b071255d47eaf58f719fc6133efee1be06ed2a`).

## Wave 0CB — exact corrected W07/W08 D provider stop

- The fresh W07/W08-only candidate was clean Plane
  `989a159cf3fa093702d6c3d61dfd3b705b6bb6a0`, directly on status-family fix
  `cf9d2b8a205d78e0c30250464a5b4c70df90169d`. Required env files were copied
  byte-for-byte from the designated Plane source without reading, printing, or
  sourcing values, and `setup.sh` was not run. Exact artifacts were API
  `plane-agent-api:g4-v6-989a159c` /
  `sha256:36c8cd6b47357a78f2d49946cc5e09aed6cca368ed8880eeee7e78ef2d54c0b9`
  and runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-989a159c` /
  `sha256:2c9484c58103964a1d033998ecd3f9dae4e10676c00698348ced79d77364dc4a`.
  The disposable manifest SHA-256 is
  `eb49fea15cd69eb203430df7ea8fb13d286a01db9892db73c76dad46410059b5` and
  the Worker D descriptor SHA-256 is
  `472caab0a49cd5b1e11cd7e6213e3091b926270b00b4d247e4ff05e09d892708`.
- Exactly one fresh capacity-gated assignment used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled through
  `https://chatgpt.com/backend-api/codex/responses`. Run
  `ecd2b743-3059-40fd-a126-0f9cde45f8c4` and invocation
  `invocation:adbb571f-ee73-44bf-afc3-8238a816d536` stopped at
  `api-invocation` after one upstream-initiated attempt. The bounded result
  recorded generic `provider_error`, `runtime_error / runtime_process /
  process_exit / runtime_execution_failed`, and observed legacy
  `statusClass=error`; the required `4xx|5xx|transport` family was not
  preserved. No W07/W08 operation, artifact, outcome, publication, product
  event, or readback claim is made.
- Durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w07-w08-d-989a159c-failure-extract.json`,
  SHA-256 `80112e72911b526ac1f2dcdad1a31643285c86c73e9b5fc32861df113263afc9`.
  The bounded result is
  `user-testing-output/plane-agents/evidence/w07-w08-d-989a159c-result.json`,
  SHA-256 `d5d9452a08cfed4af544317951ae9d05d463e6de480fc6b5c440ab0b2cb565b5`.
- Provider-free diagnosis showed synthetic 400 and 500 responses through the
  pinned `PinnedProviderHTTPSClient` both raise generic `ProviderRelayError`
  with no status family, while the three focused bounded projection tests
  pass. No provider retry, replay, or `outcome_unknown` replay was run.
  Cleanup verified zero runner-labeled containers, networks, credential/state/
  scenario volumes, and no capacity lease. W07/W08 remain dirty.

### UT-050 W07/W08 provider-free status-family repair — 2026-08-17

The existing `statusClass` projection was repaired at the provider relay to
runtime observation to Plane attempt/readback seam. It now preserves only the
safe allowlisted families `2xx`, `4xx`, `5xx`, and `transport`; legacy values
remain accepted, upstream status errors remain the generic `provider_error`,
and raw provider response data is not retained. Durable redacted evidence is
`user-testing-output/plane-agents/evidence/w07-w08-d-e9fad5-status-family-fix.json`,
SHA-256 `272785ec43879f85e53c43abb96b62570423950b3ed0084cf3ad745bd426ec35`.

Provider-free verification passed the full relay module (35/35), committed
relay/lifecycle/readback selection (28/28), and bounded contract suite
(106/106). No provider/live attempt or replay was run; test Compose cleanup
verified zero containers, volumes, and networks. W07/W08 remain dirty and a
fresh assignment is not safe from this local fix alone.

## Wave 0BX — corrected 7466 W05/W06 replacement

- The one fresh capacity-gated `context-governance` journey used clean Plane
  `74668f6d855fbea63fd57265b66410373d679d8f`, exact API/runtime images,
  `openai-codex/gpt-5.6-luna` xhigh, fallback disabled, and the checked-in
  ChatGPT subscription destination. It supersedes the vacuous 64d1 route
  claim; no old invocation was replayed.
- The exact `api-runtime-binding` command attached stdin and executed the
  bounded probe before API invocation. It passed with Django settings,
  `/run/plane-agent-runtime-secret` mode `0600`, root ownership/readability,
  `agent-runtime`, `remote`, and `RemoteRuntimeTransport`. The enforced DB
  gate passed with migration owner `plane_migrator`, API runtime role
  `plane_runtime`, governance role `plane_audit_owner`, bootstrap provisioner
  `plane`, and role separation enabled. Bounded evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-7466-live.json` and
  `user-testing-output/plane-agents/evidence/w05-w06-c-7466-runtime-binding-probe.json`.
- Run `25966a40-bbf5-4690-af74-61124e1e798f` and invocation
  `invocation:ebaedd9e-48e8-447b-8afb-b746cb9f4384` completed with 8 upstream
  `2xx` provider attempts, 18 runtime events, one outcome, one publication,
  and `RuntimeExit.completed`. W05/W06 route checks passed in the one
  commission. No separate W07, Manager, or Operator journey was started.
- The provider-disabled same-fresh replay recorded zero provider attempts and
  zero semantic deltas. Capacity release and exact-owned Docker cleanup
  passed. W05/W06 are validly closed for this replacement journey; the 64d1
  vacuous proof remains historical and superseded.

## Wave 0BW — exact 64d1 W05/W06 result with binding-gate correction

- One fresh capacity-gated `context-governance` journey started from clean
  Plane `64d1ea7fe76944fffc8f66cf4738bb556f02fa94`, using API
  `plane-agent-api:g4-v6-64d1ea7f` /
  `sha256:5ad0e9d874099b5b45a99607ddc04fba1b8f93c8a2931827b309c54b0d66685e`
  and runtime
  `plane-agent-runtime:hermes-292e8663-g4-v6-64d1ea7f` /
  `sha256:b53453bf8f5239ff31624bad8a685b4e102b842dda2505379304f659f9205943`.
  Manifest SHA-256 is
  `5bc6fbe42879e2a5c77230dc2ca1d4a750d5550f07035fa8c3dcb30b04930297`.
- The primary recorded run
  `c161a8be-0afe-4f1a-b41d-0c045553759e` and invocation
  `invocation:ed1c1c45-5e0c-4ad9-9304-398ecfb6e09c`, with 9 upstream `2xx`
  provider attempts, 20 runtime events, one outcome, one publication, and a
  completed runtime. The same context-governance commission reported W05,
  W06, W07, and W08 predicates; no separate W07/Manager/Operator journey
  ran.
- The runner's runtime-binding probe gate is invalidated: its exact Docker
  command omitted `-i`, and provider-free reproduction showed an empty,
  zero-exit stdin-less Python invocation. The supplemental corrected exact
  API-image probe passed and is retained in
  `user-testing-output/plane-agents/evidence/w05-w06-c-64d1-runtime-binding-probe.json`
  (SHA-256
  `227a70fff344ea2682d088ecaba61a31d2db6dc0987a5283c91d433d49269cbb`).
  The bounded live extract is
  `user-testing-output/plane-agents/evidence/w05-w06-c-64d1-live.json`, SHA-256
  `a58bd6186c28be09caccfef8b54f5b8422c7391a68590ea5b0cb84daf7873203`.
- The smallest launcher correction adds `-i` and a focused regression. The
  corrected provider-free suites passed `115/115`. No second provider
  journey, retry, old invocation replay, or `outcome_unknown` replay was run;
  W05/W06 remain dirty and route closure is withheld pending a separately
  authorized fresh journey with the corrected gate.

## Wave 0BU — d748 W05/W06 boundary evidence

- The one fresh `context-governance` journey used the exact d748 API/runtime
  images, GPT-5.6 Luna xhigh, fallback disabled, and the host-wide capacity
  lease. The exact API-container binding probe passed before dispatch:
  `settingsSource=django`, `/run/plane-agent-runtime-secret`, owner-only
  `0600` readable binding, `runtimeHost=agent-runtime`, `transportKind=remote`,
  and `transportClass=RemoteRuntimeTransport`. Redacted probe evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-d748-runtime-binding-probe.json`,
  SHA-256 `ad03cf8f22765516f4e246dcbb3cdbe4b3f78604b94096debf04782a0bdcc8eb`.
- The API invocation then failed locally with exit `1` at
  `api-invocation`; provider attempts/effects and runtime events were `0`.
  W05/W06 context, preference, memory, skill, promotion, rollback, outcome,
  publication, and replay route evidence were not observed. The owner-only
  result is `tmp/persona-wave-v6/w05-w06-fresh-d748ecbc-r2/result.json`,
  SHA-256 `c1c89a7363353931b74ce0475a22557adb18c3e5e58b603d928e7e057c0fe9b`;
  durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-d748-api-invocation-stop.json`,
  SHA-256 `0eac3da74b4c5232954773c0d59b55c596bfd48cd316f45058121f1c70e7bdb0`.
- No replay or retry was run. W05/W06 remain `dirty`; this evidence does not
  close any route.

## Wave 0BS — exact integrated C API-invocation boundary stop

- Commits `200d1fdb7d`, `488390ba21`, and `855f4e6686` were integrated in
  order, producing clean candidate `b2a2b50c8c904adda2c287b3780e514c46d90ca8`.
  RabbitMQ tmpfs `1/1`, capacity support/result `16/16`, W05/W06
  route/descriptor `6/6`, config-only preflight, descriptor validation, and
  live-receipt validation passed. Two broad fake-Docker fixture timeouts are
  recorded as non-blocking harness debt; no fixture patch was made in this
  lane.
- API artifact:
  `plane-agent-api:g4-v6-b2a2b50c` /
  `sha256:b5a33a42a569f83e4a067f58fa3a8427986084d1b35e57b53aa5e8e953b5a521`.
  Runtime artifact:
  `plane-agent-runtime:hermes-292e8663-g4-v6-b2a2b50c` /
  `sha256:cc8fb6743077327c7b45ff13f48e36d264c243fddc7da6a38a537e81ec9aa074`.
  Manifest SHA-256:
  `17c7e667df484302677159fb1bcb556a18b7788a947a6c7ce9f6b76398889585`.
- Exactly one fresh `context-governance` journey used
  `openai-codex/gpt-5.6-luna` xhigh with fallback disabled. It stopped at
  `api-invocation` with bounded `unspecified` / exit `1` / `unavailable` before
  a commission result. Provider attempts/effects were `0`; no W05/W06
  receipts, context projections, skill candidate/promotion/rollback, outcome,
  publication, or replay were observed. Raw owner-only result SHA-256:
  `a5e78e674787ecad5dc623bf693331c03c9c5aedbb0de3a0b858acd98c3330b1`.
- Durable redacted evidence:
  `user-testing-output/plane-agents/evidence/w05-w06-c-api-invocation-stop.json`,
  SHA-256
  `988404c2029b6e301e9fa5caf4b79a8dc4ff9bab91adb0e970d74f691444fbe1`.
  Run `de7c79bb-2387-4b8a-8af8-0e03e381b9e5` and invocation
  `invocation:3cbbf662-2291-4e13-ac06-214f7ad1eaea` are retained as bounded
  lifecycle bindings. Cleanup verified zero containers, volumes, networks, and
  capacity leases. W05/W06 remain `dirty`; this is not route closure.

## Wave 0BR — capacity-gated exact C compose boundary stop

- Capacity-gate commit `be3eecea9c335b05f2ae1389d036e281b6475f8f` was
  integrated at Plane `2e7ce806b60d74045073544660c36feb2cf56c0c`. The clean
  ready state passed the focused provider-free checks (`178` host tests and
  `14` Django memory/projection tests), config-only contract preflight, and
  descriptor validation. The copied `apps/api/.env` source and target both
  remained mode `0644`, size `1466`; values were not read or sourced.
- One fresh single-commission `context-governance` journey used the exact
  candidate-bound API/runtime images with GPT-5.6 Luna xhigh and fallback
  disabled. API digest:
  `sha256:5cc4090672c2adb53b7be9c54707f60007d377d8a929ad78c578d5fa65e5fe63`;
  runtime digest:
  `sha256:23b68142e410ea6c2d409dba1c8afe6d97361ba12d44522a49a4181fba4cf61d`;
  manifest SHA-256
  `ce92f3190e946985c8c909c2f5f1052983a56b58d29cddc9be39448ece87a073`.
- The journey stopped before provider invocation at `compose` with bounded
  `unspecified` / exit `1` / `unavailable`. Provider attempts and provider
  effects were `0`; no replay was run. Durable redacted evidence is
  `user-testing-output/plane-agents/evidence/w05-w06-c-capacity-compose-stop.json`,
  SHA-256 `f9ab6c461cb03e055c0219a92f8153757b897d24802e1d602ecd9c54c705a8e6`;
  raw owner-only result SHA-256 is
  `8f1f533251657b60b87549f9c5d8e5fad82d013d8af748520a2f2787b032227a`.
- Subject-bound preferences, Plane-owned memory/skill projections,
  agent-scoped candidate learning, deterministic context assembly, outcome,
  and publication were not observed because the compose boundary failed.
  Cleanup and capacity-lease release were verified at zero containers,
  volumes, networks, and no remaining lease. W05/W06 remain dirty; no replay
  or provider retry was made.

## Wave 0BQ — exact second-fix b002211f0d / C commission boundary stop

- The second shared fix `3c4209340c7f219be76258083a595b8fba14c05c` was
  integrated on top of the e312 chain as Plane `b002211f0db8d04fe13c639a026502f0a0ea2618`.
  Focused host checks passed `161/161`; the provider-free W05/W06 Django
  regression passed `14/14`.
- One fresh single-commission `context-governance` journey used the existing
  Plane/Hermes runner with `openai-codex/gpt-5.6-luna` xhigh and fallback
  disabled. The exact API artifact was
  `plane-agent-api:g4-v6-b002211`, digest
  `sha256:12888071f9606b84135c20682a4e1479753091870f3a0853a4b4cec2c0184ffd`;
  runtime was `plane-agent-runtime:hermes-292e8663-g4-v6-b002211`, digest
  `sha256:5735f8a6a13260843e3d95f783696ca15b5eab2633baf19da59e80ff72a4e9f9`.
  The disposable manifest SHA-256 was
  `c3bdf383cc6fb0a6c264d84f54c6bc71283b093474975dca00f5dfe634f2cf7b`.
- The fresh C run stopped at `api-invocation` with bounded `unspecified` /
  exit `1` / `unavailable` before a commission result. Provider attempts were
  `0`; no W05/W06 receipt, audit, publication, memory projection, preference
  projection, skill promotion, or rollback was observed. Run
  `b5f5b8e2-def6-4066-bb00-ebe0a7cc96db` and invocation
  `invocation:b66f5437-9931-47ce-90b6-4aca07d02e9f` are bound in the durable
  redacted extract
  `user-testing-output/plane-agents/evidence/w05-w06-c-second-fix-stop.json`,
  SHA-256 `27721c95b2c17d352f38fa0e8ed798babda6d9a5e9341b4b8af3fdd92fc2c3fe`;
  the owner-only raw result SHA-256 is
  `bd65e1fd64fbb5ba77a68bc7aa3b577a49acf48bedf488d7c1e57c76e5ad517d`.
- The provider-disabled same-invocation replay was ineligible because the
  primary stopped before a commission result. It was not run, and no
  `outcome_unknown` receipt was replayed. No shared launcher/runtime/config
  patch was made in this lane. Cleanup was verified at zero containers,
  volumes, and networks for all observed disposable project identifiers.
- W05 and W06 remain dirty; this is provider-free boundary evidence, not route
  closure.

# Goal: Complete the non-UI Plane Agent system

## Objective

Build and independently verify one functionally complete non-UI Plane Agent system, conforming to [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) through [ADR-0010](../decisions/0010-plane-runtime-contract.md), for backend assignments, runs, artifacts, conversations, outcomes, reviews, product events, and every supported Plane integration/action. The system must be operable and verifiable through real provider-backed Plane Agent journeys using Plane APIs, CLI/fixtures, ordinary Plane object pages, operator surfaces, and reused settings surfaces.

This goal covers the full Plane Agent control plane and the hidden execution service. It does not require chat, composer, thread, inbox, sidecar, transcript, or conversation-navigation UI.

Functional completion and controlled rollout are separate outcomes. This goal ends when the non-UI product passes the complete live dogfood matrix, the production-candidate checks, and integration into a named Plane branch. Development, allowlisted-workspace, expanded-cohort, and GA rollout are a successor goal requiring their own deployment authority; they are not evidence that the product implementation works and are not a completion condition here.

### Current v31 functional-completion plan (2026-08-18)

The named integration branch is
`codex/plane-agent-functional-v31-20260818` at source
`34e9d4dee7a7f53b7c342009161482cb6ff793eb`. Its exact API artifact is
`plane-agent-api:g4-v31-34e9d4de` at
`sha256:c5ef5cfea8da44571da6ac4e9bee3dea84f23dcba801611ccc3c4cc41a8b4c2b`,
and its exact runtime artifact is
`plane-agent-runtime:hermes-b8e2d884-g4-v31-34e9d4de` at
`sha256:5c022cf613570db4c218d5d80743ac9aba2d479ef97a750ccbb2ab9d46e1bbc5`.
No current-candidate persona route
is claimed passed. Earlier provider-backed waves are history and do not replace
the matrix below. The unchanged O02 exact external-client proof is the sole
retained live exception.

Functional completion now requires exactly one current-candidate journey for
each internal persona: Worker W01–W08, Manager M01–M08, and Operator
O01/O03–O09. These are consolidated user journeys, not one provider journey
per route-map cell. Each journey must include its own permitted and denied
canary, explicit outcome submission, publication and terminal state, plus
bounded replay or idempotency and durable readback wherever the route applies.
Deterministic destructive and failure boundaries remain provider-free tests;
they do not justify additional model journeys.

A standalone provider smoke is required only when the first final journey has
not already proved provider authentication and preflight. It may be the first
bounded segment of that journey and must not duplicate it. After the three
persona journeys pass on one current candidate, run one production-candidate
verifier and one consolidated Sol Medium review. There is no second duplicate
“final clean wave.” G5 remains a separate rollout goal.

### Historical delegated live disposition (2026-08-16)

The synthetic-only Maya C context-governance commission was attempted once on
the exact `713fb8c685c7298cbb7fdd2b3fe965c60ba413e9` artifacts and once as the
single deliberate post-fix fresh C on `c7e41e85dfd50398338fecbfce28b9350b229f60`.
Both used `openai-codex/gpt-5.6-luna`, xhigh reasoning, fallback disabled, and
the 16-call bound through the host-only provider relay. The first owner-only
receipt, `tmp/persona-wave-v6/context-governance-primary-receipt/result.json`,
validates with SHA-256
`2bfa9d0f9518226dcd248d9b14e24bed178e458f46862c7aa24d40e6c889aade` and
failed its local gate only because `agent.context.read` succeeded twice
instead of once. The provider-free route guidance fix is `c7e41e85df`.

The post-fix owner-only receipt,
`tmp/persona-wave-v6/context-governance-rerun/result.json`, validates with
SHA-256 `f380048cdb0be65806fd557b828851daa36ed2fe10eb10479ca743bbac7a1196`.
It recorded exactly one context read, all expected operation and durable
terminal counts, and `RuntimeExit.completed`, but failed only W07 because the
provider submitted no artifact. The provider-free commission correction
`62fd6193a0` now requires exactly one artifact and exactly one evidence item.
No replay was run for either failed primary, and no further live run is
authorized in this task. W05-W08 therefore remain dirty; W03-W04 remain
unreached. Final exact API/runtime attestations for `62fd6193a0` were built
without another provider run.

The subsequent Worker B primary in Wave 0BJ used exact Plane
`7a6983ed68519e8a267748998b4e8189f0fdae78` and Hermes
`292e866374ca9e9615473fc9bf5dda1913b672e1`; its owner-only receipt is
`tmp/persona-wave-v6/worker-live-7a6983ed-b3/result.json`, mode `0600`,
SHA-256
`4eb7b8c7ed5fec3e542e4d573afc2d22567f380a7af0d947ad8988696e732345`.
It reached nine completed upstream `2xx` attempts, failed at the real Code
Mode host callback, and had no eligible replay; further provider use is
stopped pending root-fix review.

### Historical Wave 0BK disposition

The typed Code Mode root fix `76ecdd120748c66e08cf07708e237291aace3e19` is
integrated as Plane `c561bdfe89fb7413877b910900b5675b9f4b779d`. Provider-free
verification passed descriptor `53/53`, Plane cross-process `24/24`, Hermes
bridge/host-port `8/8`, and migration-backed Manager `1/1`; exact image labels,
imports, and real bootstrap readiness passed. One fresh launch then ran the
identity commission first and passed with 11 completed upstream `2xx` attempts
plus a zero-delta provider-disabled replay, but stopped before creating the B
mutation run/invocation with `runRef=unavailable` and zero B provider attempts.
This is workflow commission-selection evidence, not a typed Code Mode result.
Receipt `tmp/persona-wave-v6/worker-live-c561bdfe-b4/result.json` is mode
`0600`, SHA-256
`f0a9b26e18b8ab9034558638f4e67c24cc5bfd84d928ba1e5914c32e1c16ec33`.
No second primary or further provider use occurred; W03/W04/W07/W08 remain
dirty and UT-039 is open.

The retained raw aggregate receipt is unchanged. Its pre-fix wrapper omitted
the failed commission's bounded failure envelope, even though that commission
created no run, invocation, provider attempt, or Plane semantic side effect.
Provider-free host fix `aef02407a4` now emits a `live-failure/v1` aggregate from
the failed commission and retains both commission rows; the behavior-level
canonical-validator regression is included in the `149/149` harness pass. No
provider retry, replay, image rebuild, or new disposable resource occurred.

### Historical Wave 0BL disposition

The exact functional candidate is Plane
`8d94fcc16e5ff161b1e128fd3fd22f6a4f851071`, API
`plane-agent-api:g4-v6-8d94fcc1` / digest
`sha256:428bdbab5945250fcd5ae3056f0a519cac8b0a0ecc8d03b948ecf26842abf752`,
and runtime
`plane-agent-runtime:hermes-292e8663-g4-v6-8d94fcc1` / digest
`sha256:6feabe70129e61d9de9c11045180bd839ea709f9a3d2b390f417fc3de71988ed`,
bound to Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`. Host checks passed
`180/180`; the migration-backed provider-free clump passed `297` tests, with
13 known environment-bound failures (container repo-root/fixture mounts,
runtime checkout mount, host CPU threshold, and Docker CLI availability inside
the API test container). Runtime imports and the network-disabled real
bootstrap passed.

One fresh full three-commission Worker descriptor used GPT-5.6 Luna xhigh,
fallback disabled, max 16, and the host-only relay. The first identity
commission passed W01/W02; its eligible provider-disabled same-invocation
replay reported zero children, attempts, invocations, receipts, audits, usage,
outcomes, publications, terminal events, and semantic side effects. The next
mutation commission reached a terminally failed run/invocation and stopped at
bounded `runtime_error / runtime_process / process_exit /
runtime_execution_failed` after two progress events. All seven expected
gateway-operation counts were zero, provider attempts were zero for that
failed commission, and no outcome/publication/artifact/semantic mutation was
recorded. The canonical validator passed the aggregate receipt, which is
retained at `tmp/persona-wave-v6/worker-live-8d94fcc1-complete/result.json`,
mode `0600`, SHA-256
`c0f869c8ceae591ce46cf5b6be4661a729f912ecb2caf842a849f76bf8fbdcbf`.
Manifest SHA-256 is
`d8d0ee728974ca6847adb840240e59e44d0478735c25a97e5320b674a09748f5`.
The bounded envelope exposes no narrower cause, so this is a real local
runtime failure rather than an external-provider prerequisite. The failed
commission was not replayed and all W03-W08 remain dirty.

### Historical Wave 0BJ disposition

The integrated Plane/Hermes TypeScript bridge was exercised by one fresh
synthetic-only B primary on exact Plane `7a6983ed68519e8a267748998b4e8189f0fdae78`
and Hermes `292e866374ca9e9615473fc9bf5dda1913b672e1`. It reached nine
completed upstream `2xx` attempts, then failed non-retryably at the real Code
Mode host callback with bounded `CODE_MODE_FAILED` / `host_callback`; no
mutation, applied publication, complete W08 readback, or eligible replay was
proven. UT-038 remains open, W03/W04/W07/W08 remain dirty, and no further
provider use is authorized pending root-fix review.

## Historical v22 status and authorization

The v22 source candidate is `c9174ae7d585d55659c447ba8fe4d7e0d2e5380a`.
Its provider-free exact API image is
`plane-agent-api:g4-v22-c9174ae7` at
`sha256:e4d143327dff4f8299d846cd23059964bf922135c7d639dbe380d093d4389f69`;
its exact runtime image is
`plane-agent-runtime:hermes-d4b32a3-g4-v22-c9174ae7` at
`sha256:3654ce1aba475c10c78fc05203b0af9e9ebce9fdd72d08520a5bbe32af36af21`.
The final v22 wrapper is created only after the manifest-bound gates pass and
will be the sole child of this source. Hermes remains
`d4b32a3e0ac9b528eb6e513274227e18a279906c`; MCP remains
`c04974ed6624f17b41e63ef8182661929e77e0d3`; SDK remains
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. W03/W04 and W07/W08 remain dirty
after v19 `PREPARED_CALL_INVALID` stops, and Manager remains dirty after its
v19 opaque `api-invocation` stop. Fresh serialized reruns are required.

## Historical status and authorization

| Historical item    | Recorded state                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Delivery candidate | Exact shared provider-free source `fe72bcefe5ffc13c43212d48c2c47f4006d85ae5`; its final candidate is the sole metadata-wrapper child; API `plane-agent-api:g4-v19-fe72bce` / `sha256:59abfaec97cd82b74995b7cf7c64cb0bd37973bd8bf528ab07143dc4fd4472f7`; runtime `plane-agent-runtime:hermes-6c460f10-g4-v19-fe72bce` / `sha256:120e8f51a8193512c3be9d38e1a2b958eb9339178ce59c655e2b3f2bef03480e`; Hermes `6c460f10fe215718dce36dd73cda94155a9a34f8`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The source includes the exact `preparedCallRef` model guidance, typed work-item handoff, authority-threshold forwarding, retained W03/W04 and W07/W08 live-stop evidence, W05/W06 immutable live success, Operator O01/O03-O09 scope, Manager readiness evidence, bounded authority-window generation, Manager setup diagnostics, corrected cross-project denial fixture, and Compose env isolation. Exact-image and focused authorization/idempotency regressions remain provider-free gates; raw work-item IDs are absent. |
| Functional gate    | S00 Wave 0AT is clean at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` with Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`: ten ordered upstream `2xx` attempts, three searches, two reads, one exact `NOT_AUTHORIZED` denial, one submit, one applied publication, one matching terminal, and `RuntimeExit.completed`; replay semantic deltas were zero and cleanup passed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Provider-free PF1  | Worker W01–W08 passed 35 real Django/API/DB/CLI/socket/isolation tests unchanged. Manager M01–M08 passed 33 tests after `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1` and `2105fb9e21687103939a77b7e26a0959f1d50f51`. Operator O01 and O03–O09 passed targeted real service/API/database/CLI contracts; the final exact-image red team passed with one applied publication and zero labeled-resource leftovers.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Live W/M/O wave    | W01/W02 remain clean from Wave 0BF. W05/W06 are live-clean from immutable v15 run `11483892-9a44-493c-84c4-419b5c3ba40b`, invocation `bd4afa32-1095-408a-8590-660ad2ba09f5`, eight upstream `2xx` attempts, one context read/outcome/applied publication/terminal, and a provider-disabled zero-delta same-invocation replay; the threshold mismatch was harness-only and is structurally corrected in v16 without another provider call. W03/W04 remain dirty after their v15 `VALIDATION_ERROR` stop, and W07/W08 remain dirty after their v15 assigned-read `NOT_AUTHORIZED` / `CODE_MODE_FAILED` stop. Both dirty lanes require fresh serialized v16 runs. O02 remains separately clean from its real external-client closure.                                                                                                                                                                                                                                                                                                                                                |
| Final verification | Provider-free exact-image, typed search-to-read, threshold forwarding, rollback, manifest, and cleanup checks bind the final wrapper as the sole child of source `fe72bcefe5ffc13c43212d48c2c47f4006d85ae5`. Fresh serialized W03/W04 and W07/W08 provider journeys remain separately authorized work.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| G5                 | Out of scope. Rollout starts only under a separate authorized goal after G4 functional completion.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

The table below preserves accepted gate history and older frozen artifact
bindings. Its G4/dogfood rows are historical evidence and do not override the
active execution status above.

| Item                                | Recorded state                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G0                                  | Complete as a lightweight start condition: ADRs 0001–0010 exist and cohere, scope and non-goals are explicit here, and local implementation is authorized.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| G1                                  | Complete at Plane commit `44edd3a6e94b4c7ab6efb2e92e516699a0cb2d12`, independently accepted by the G1 gate reviewer. Fresh PostgreSQL proved the linear 0122→0130 migration chain, 0130 reverse/reapply cleanup, serialized concurrent replay, and UPDATE/DELETE/TRUNCATE denial on both append-only runtime-evidence tables. The exact no-model/no-UI G1 body crossed canonical-JSON dispatch and ingress, kept runtime completion evidence-only, then used the authorized/idempotent/audited gateway and explicit `OutcomeSubmission` to record exactly one terminal product event. Durable counts were one runtime event, one runtime exit, one outcome, one terminal event, two gateway records, and eight audit records. Packaged lifecycle schemas matched the accepted L1 manifest digests.                                                                                                                                                                                                                            |
| G2                                  | Complete at Plane commit `c6d12931aefcafe9abc9fcc6775fd24ea91c3e5f` with Hermes commit `e573a46611e2cb988f1ab43ad34cd8cc3b2cb659`, independently accepted by the single consolidated G2 reviewer. The committed proof begins at the production `agent_supervisor` command, launches the separate trusted Hermes bootstrap with a loopback deterministic provider, executes progressive discovery, native read, restricted Code Mode, one gateway mutation, explicit outcome submission/publication, transcript-only final text, and matching API/CLI readback. Durable counts were one actor, profile, assignment, run, invocation, outcome, and visible terminal event; six gateway receipts across five operations; and twelve correlated audit rows. Exact replay created no child, usage, receipt, audit row, outcome, publication, terminal event, or semantic side effect. Cancellation, timeout/process death, malformed evidence, budget failure, and `outcome_unknown` reconcile through Plane without blind replay. |
| G3                                  | Complete at Plane commit `7c9d35f4c324865c27c84da5016be2c84e460bcc`, independently accepted by the consolidated G3 reviewer in Codex task `019fd6ab-bfb0-7322-8bc4-f6e6609f6bee`. The accepted offline baseline reran the G3 prerequisite at `256/256`, with reversible migrations through leaf `0140`, the complete `177 = 86 gateway + 90 unsupported + 1 local` action disposition, exact candidate-derived Hermes/MCP/SDK revisions, read-only host-resolved community credential topology, no-chat-UI checks, and isolated cleanup.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| G4 offline candidate                | The recorded shared source candidate was `fe72bcefe5ffc13c43212d48c2c47f4006d85ae5` with API `plane-agent-api:g4-v19-fe72bce` / `sha256:59abfaec97cd82b74995b7cf7c64cb0bd37973bd8bf528ab07143dc4fd4472f7` and runtime `plane-agent-runtime:hermes-6c460f10-g4-v19-fe72bce` / `sha256:120e8f51a8193512c3be9d38e1a2b958eb9339178ce59c655e2b3f2bef03480e`, all bound to Hermes `6c460f10fe215718dce36dd73cda94155a9a34f8`, MCP `c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK `7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. Accepted G3 baseline remains `7c9d35f4c324865c27c84da5016be2c84e460bcc`; W05/W06 live acceptance was retained from v15, while W03/W04 and W07/W08 required fresh serialized proof.                                                                                                                                                                                                                                                                                                                |
| Dogfood branch                      | `codex/agent-functional-dogfood` starts from wrapper `3f2a478209fb94049376f781d33ddd4b63a038de` and source `1d1012f71c48615bb28b7988ce74c82421aa1d53`. Dogfood evidence and documentation may advance the branch without refreezing images. Functional fixes must extend the established Plane or Hermes owner and receive targeted verification; images and immutable provenance are rebuilt once from the final clean source before the final G4 verifier.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Provider egress seam                | The trusted runtime owns an invocation-bound AF_UNIX relay and the sole external-egress network; Hermes commit `6c460f10fe215718dce36dd73cda94155a9a34f8` is wired through the existing bootstrap/service chain and the candidate image is pinned below. The live authority/config contract admits only the typed ChatGPT subscription descriptor `openai-codex/gpt-5.6-luna` at `https://chatgpt.com/backend-api/codex/responses`, with fallback disabled, and validates it before credential read, relay startup, DNS, or provider request. Separately authorized live provider proof remains pending and requires a fresh run.                                                                                                                                                                                                                                                                                                                                                                                             |
| Live functional dogfood             | The retained explicitly authorized live failure receipt SHA-256 is `2013336c367397263ea1d5fdf41e46dfda5ed449c8f0be39913f5c6d5c727861`; it failed at `api-invocation` with Docker exit 125 because the runner directly mounted the caller-owned provider source under `/private/tmp`, which was not bind-visible to Colima. No Plane run, invocation, or evidence object was created and no provider request occurred. The source correction stages the credential in a Docker-visible, owner-only location. At the time, live dogfood remained unproven; current completion is governed by the v25 matrix above. An older live canary receipt `20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a` remains historical `outcome_unknown` evidence and must not be replayed.                                                                                                                                                                                                                                      |
| Controlled rollout                  | Out of scope for this goal. Historical G5 branches contain rollout-control schemas and offline evidence tooling, but no rollout stage was executed or promoted. Do not restore or extend that work until the functionally complete candidate is integrated and a separate rollout goal is authorized.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Retained pre-live lifecycle failure | The earlier pre-live root failure retained receipt SHA-256 `4e2a96a9fcaa5dccf5a8a1994b008016bf45aa7b8cc5c163f32aabb4cb4f958c` and failure-log SHA-256 `a412273116e90263dabade32d29e1a2b856e8dde64fe8c047c88850a5bf7bc52`; it made no provider request, live invocation, credential mutation, or G5 action and is not `outcome_unknown`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Source authorization                | Codex task `019fc7db-e8bf-7f92-8f2b-b2346e5eeeb8`, 2026-08-04.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

The recorded G4 remediation binds the final wrapper through the external
operator input `PLANE_G4_EXPECTED_CANDIDATE`; the committed manifest binds only
the wrapper's approved source parent. G3 and G4 share a process-lifetime
advisory lock whose inherited descriptor is path-checked rather than caller
controlled by a boolean, and the offline verifier retains a sanitized, hashed
receipt outside disposable evidence cleanup. G3/G4/API-migration behavior now
executes the exact immutable API image containing the remediated source; the
wrapper binding carries the exact image digest and source revision recorded
above. These changes are not live acceptance. The accepted offline baseline and
the permanently `outcome_unknown` live history remain evidence inputs; only a
clean provider-backed dogfood wave can close the functional gap.

Durable authorization statement:

> Implementation and live functional evaluation are authorized to proceed within this goal. Pilot, production, staged rollout, deployment, and destructive/external actions remain separately governed and must not be inferred from this candidate.

This authorization removes the obsolete implementation-blocking approval-manifest requirement. It does not authorize pilot, production, deployment, destructive data changes, credential changes, purchases, external writes, public incompatible changes, or other actions that require a separate approval.

### Accepted offline G4 evidence

| Binding or proof   | Accepted evidence                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runtime artifact   | Candidate image `plane-agent-runtime:hermes-114eabf9-g4-c47ddfe`; digest `sha256:b4a701905bae50bef643ef67c3883ef74d8f6ddcde2cf669d1dab50c44999b0c`; runtime/source revision `c47ddfe6174ecd6d66257d8fedbd5d425c7f3172`; Hermes `114eabf9d807b659e36d767e4de46ca056297ccb`; remote `github.com/uxheavy/hermes-agent`; contract `plane.agent-runtime/v1`. The prior detached-worker image remains rollback/history evidence only. |
| Offline proof      | Fresh G3 prerequisite `279/279`; runtime contracts `13/13`; cross-process `15/15`; service `9/9`; focused provider-egress reconciliation `19/19`; exact-image genuine-Hermes red-team `1/1`; the bounded 128-request load threshold passed with `0.0` error rate; migration leaf `0142`; rollback/readback/config pass; installed resolver fails closed without leakage; final secret scan clean; zero labeled resources.       |
| Live guard         | An unconfigured `--live` run exits `2` as `external_required`, with `offline=not_run` and no provider call.                                                                                                                                                                                                                                                                                                                     |
| Independent review | Consolidated Sol Medium reviewer task `019fd8e8-b562-7cf3-a20b-bb5307a65e66` accepted the earlier offline G4 baseline with no actionable P0/P1/P2 remaining. The recorded provider-reconciliation/resolver correction had complete Luna verification but awaited the single consolidated current-candidate review after live G4 evidence became available.                                                                      |

## Durable authority

Use the smallest authority set:

1. [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) through [ADR-0010](../decisions/0010-plane-runtime-contract.md) are the durable product and architecture source of truth.
2. This `GOAL.md` is the concise execution objective, scope, success proof, phase map, and worker protocol.
3. [README.md](./README.md) is only the index and current status.
4. Repository and nested [AGENTS.md](../../AGENTS.md) files govern implementation boundaries and local verification.
5. Current Plane and Hermes source, tests, generated contracts, and runtime evidence become authoritative for the behavior they implement; prose cannot replace executable proof.

The deleted planning documents, manifests, generated mirrors, inventories, fixtures, and G0 harnesses are not required inputs. Git history preserves their historical context. Do not restore them or recreate a parallel documentation package.

### ADR map for task routing

Every future task packet must name each applicable ADR by number, title, and path. “Follow the ADRs” or “follow the architecture” alone is insufficient.

| ADR      | Title and lane-relevant purpose                                                                                                         | Path                                                                |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| ADR-0001 | Shared Plane operation gateway with native Hermes tools and external MCP compatibility; common operation boundary and catalog approach. | [0001](../decisions/0001-plane-agent-tooling-architecture.md)       |
| ADR-0002 | Plane agent operations execute autonomously within Plane authorization; live authorization and no runtime operation approval.           | [0002](../decisions/0002-autonomous-agent-operations.md)            |
| ADR-0003 | Plane Agent is a native Plane product; Plane-owned product boundary, one model, and Buzz reference-only role.                           | [0003](../decisions/0003-plane-agent-native-product-boundary.md)    |
| ADR-0004 | Fork Hermes as the hidden Plane Agent execution kernel; reuse and narrow runtime adapter seam.                                          | [0004](../decisions/0004-fork-hermes-as-hidden-execution-kernel.md) |
| ADR-0005 | Plane owns one role-bearing Agent model; actor authorization, versioned profiles, one role per Agent, and role governance.              | [0005](../decisions/0005-plane-owned-agent-profiles.md)             |
| ADR-0006 | Plane owns assignment and run lifecycle; five independent records, invocations, recovery, publication, review, and terminal events.     | [0006](../decisions/0006-assignment-and-run-lifecycle.md)           |
| ADR-0007 | Expose Plane-native tools adaptively; separates authorization, availability, and disclosure with complete discoverability.              | [0007](../decisions/0007-adaptive-plane-tool-exposure.md)           |
| ADR-0008 | Keep Agent memory and skills private and governable; Agent-private scope, provenance, gardener changes, and rollback.                   | [0008](../decisions/0008-scoped-memory-and-context.md)              |
| ADR-0009 | Use dynamic planning and delegation, not saved workflows; delegator role, normal child assignments, schedules, and lineage.             | [0009](../decisions/0009-workflows-and-agent-delegation.md)         |
| ADR-0010 | Use one versioned Plane runtime contract; cross-process seam, snapshots, invocations, events, trust, and isolation.                     | [0010](../decisions/0010-plane-runtime-contract.md)                 |

## Product model and non-goals

- There is one Plane Agent product and one Plane Agent runtime mode. Each configured Agent has exactly one role at a time; roles are profile data and governance on the shared Agent model, not separate runtime classes or permission systems.
- Plane owns Agent identity, permissions, profiles, assignments, runs, conversations, artifacts, private memory and skills, schedules, delegation, evaluator review, outcomes, publication, audit, and recovery state.
- Hermes is the hidden, replaceable execution kernel behind one narrow versioned Plane runtime adapter. Hermes sessions, files, transcripts, and checkpoints are mechanisms or operational projections, never Plane product authority.
- Buzz is a reference and code donor for useful conversation, ACP, inspectability, or isolation patterns only. It is not a Plane runtime dependency, product authority, or durable-state source.
- Authorized Agent operations execute autonomously inside live Plane authorization. Unauthorized calls deny without leakage or side effects. Runtime operation confirmation prompts, approval brokers, pending approval records, and approval-resume protocols are out of scope.
- Human approval remains required where product or delivery governance requires it: HR proposals, evaluator review followed by human acceptance, release and rollout promotion, deployment, credentials, destructive changes, incompatible public contracts, and external or paid actions.
- API and CLI administration comes before UI. Any later settings/admin UI must extend Plane's existing settings routes, layouts, forms, tables, drawers/modals, services, stores, permissions, and `@plane/ui`; no chat UI, custom agent UI, settings framework, or parallel design system is in scope.

## Original-design reuse principle

- Extend existing Plane and Hermes owners, modules, interfaces, and seams.
- Reject parallel domain, configuration, runtime, deployment, or UI frameworks unless an existing owner is proven unable to carry the behavior.
- Encode reuse through shared code, contracts, and tests.
- Every implementation lane must identify the existing owners it extends before adding code. A new module is justified only when it forms a deep internal boundary that concentrates otherwise duplicated policy, limits, or lifecycle behavior behind an existing public seam.
- Apply the deletion test during integration: if removing a new abstraction would not force meaningful policy or lifecycle duplication into established owners, remove it. Convenience wrappers, duplicate adapters, alternate verifiers, and parallel evidence formats do not pass this test.

## Independent Plane lifecycles

These five records are independently meaningful and must not be collapsed into a Hermes session or one aggregate lifecycle:

| Record               | Authority and meaning                                                                                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AgentActor`         | Durable Plane principal, assignee, identity, credential, memberships, roles, and object permissions. It is the sole live entitlement source.                                          |
| `ProfileVersion`     | Immutable Plane-owned behavioral configuration: one role, instructions, model/runtime defaults, skills, context references, and presentation defaults.                                |
| `AssignmentContract` | Durable commission with target, objective, acceptance criteria/context, assignee, lineage, and review state.                                                                          |
| `RunAttempt`         | Plane-owned execution attempt with a frozen resolved snapshot, context, model, tool presentation, budget, and lifecycle state. One run may span many runtime invocations or restarts. |
| `OutcomeSubmission`  | Result, artifacts, evidence, evaluator review, and human accept/return decision produced from a run.                                                                                  |

Each runtime invocation has its own lease and disposable process/container. Plane persists the immutable run snapshot, input/context events, cumulative budget, and terminal product state. The kernel's completion is evidence only: every terminal invocation must produce exactly one visible Plane terminal event: submission, failure, blocker, or cancellation. An `outcome_unknown` operation is reconciled or escalated and is never blindly replayed.

## Ownership boundaries

| Concern               | Owner and contract                                                                                                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product/control state | Plane owns the domain records above, permissions, profiles, assignment/run/outcome lifecycles, conversations, artifacts, memory/skills governance, schedules, delegation, evaluator/human review, recovery, and audit.                                                                                              |
| Operation Gateway     | One shared Plane application boundary for native Hermes tools, credential-free TypeScript host callbacks, runtime lifecycle mutations, and external MCP compatibility. It authenticates the caller, applies live authorization, idempotency, bounded results, semantic application services, and append-only audit. |
| Runtime service       | A separate co-located service owns dispatch, leases, cancellation, event ingress, and safe continuation through the versioned `plane.agent-runtime/v1` contract and deterministic adapter. It has no direct Plane database or product-model authority.                                                              |
| Hermes                | Executes model loops, context/retrieval, tool dispatch, transcripts, checkpoints, concurrency, and recovery mechanisms behind the narrow adapter. Plane concepts do not leak into unrelated kernel modules.                                                                                                         |
| External MCP          | Remains a supported compatibility surface and converges incrementally on the same gateway; external human/integration identity is preserved and is not represented as an internal Agent.                                                                                                                            |
| Buzz                  | Reference only; no runtime import, product dependency, or durable-state ownership.                                                                                                                                                                                                                                  |
| UI                    | No chat/composer/thread/transcript/navigation UI. Required administration reuses existing Plane settings/admin UI primitives after API/CLI parity exists.                                                                                                                                                           |

## Functional user-testing loop

The primary verifier is a backend-first dogfood campaign, not another repeated
gate-script replay. Three persistent personas use the same native Plane Agent
product/runtime mode with different Plane-owned profiles and roles. Every
implementation, debugging, preparation, build, and review thread uses GPT-5.6
Luna by default (xhigh where the lane requires it). GPT-5.6 Sol Medium is never
the default and may be used only once, when explicitly justified, for one
high-stakes cross-judge/final review after the final matrix and production
verifier pass.

The target is an isolated local Plane stack and disposable workspace. Personas
act through real assignments, Plane APIs and CLI commands, the separate Hermes
runtime service, ordinary Plane object pages, and reused settings/admin
surfaces. There is no chat UI. Browser evidence is required only for existing
object and settings pages; backend behavior is proven by product-state,
gateway, audit, provider-attempt, and terminal-event readback.

### Workflow-only obstacles have zero delivery weight

Do not spend a product dogfood cycle, provider invocation, or independent
review on an obstacle that a deterministic operational step removes. Encode
the step in the existing setup, preflight, runbook, or verifier; execute it;
then continue the functional journey.

Use one classification test: if resolving the obstacle changes only how the
work is prepared or executed, and does not change Plane Agent product behavior,
it is workflow friction. Fix it in the same execution turn whenever possible.
It must not become a product issue, persona route, phase gate, completion
percentage item, or reason to wait for a separate review. Record only the
workflow change and the successful retry evidence needed to prevent recurrence.

- All delegated tasks use standard mode with GPT-5.6 Luna. Keep them bounded to the smallest decisive check and avoid broad archaeology or repeated gates; safety, auth, and `outcome_unknown` invariants remain unchanged.

Workflow-only obstacles are not findings and carry zero delivery weight. They
do not consume a provider retry, create a blocker status, trigger a reviewer,
reduce the reported completion percentage, or justify spawning a separate
investigation. The task owner prepares the environment, obtains the ordinary
execution permission available to the task, corrects the command or harness,
and resumes the same functional route. Escalate only when the required change
would alter product behavior, weaken a security boundary, require unavailable
authority, or perform an external, destructive, or paid action.

| Obstacle                                                                                                                                                                 | Required treatment                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Local `.env` files, required services, Docker-visible paths, checkout provenance, generated local prerequisites, or an ordinary platform execution approval              | Treat as workflow setup. Make the prerequisite and failure message explicit, automate it in the existing owner where practical, and do not count it as a Plane Agent product defect. |
| Missing command authorization, sandbox approval, executable bit, local port selection, dependency preparation, command spelling, timeout, or equivalent runner mechanics | Resolve through the normal execution workflow, encode a preflight or safe default when recurrence is plausible, and resume the same route without opening a product investigation.   |
| The same setup obstacle reappears after its workflow is explicit                                                                                                         | Treat the missing or ineffective preflight as a harness defect and fix it structurally once.                                                                                         |
| Plane membership, role, object permission, credential validity, live authorization, or a denied semantic operation                                                       | Treat as product behavior. Exercise the real authorization path and never bypass or weaken it to advance a test.                                                                     |

Routine environment and execution authorization must therefore be resolved
before a live invocation is spent. The delegator and workers should proceed
through such fixes autonomously within their granted permissions instead of
stopping for a product decision. A test route starts only after its operational
preconditions pass; an actual Plane authorization result remains part of the
route evidence.

### Disposable checkout environment rule

Create every disposable checkout, build tree, prep directory, and live-run
directory under `/private/tmp`. Never create generated Plane Agent work under
`/Users/nqh/Desktop` or a repository `tmp/` directory. Durable source,
committed evidence, and the authoritative environment-file source remain in
their canonical repositories; disposable execution state does not.

Before running setup, tests, verifiers, or a live journey in any disposable
Plane clone or worktree, copy the existing local `.env` files from
`/Users/nqh/Desktop/CODES/plane` into the same relative paths in that checkout.
The only intended repository-relative source locations are `.env`,
`apps/admin/.env`, `apps/api/.env`, `apps/live/.env`, `apps/space/.env`,
`apps/web/.env`, and `external/plane-mcp-server/.env.test`; copy each only when
present. Never recursively discover or copy environment files from `tmp/`,
nested clones or worktrees, `.git/`, dependency trees, or generated evidence.
The authoritative checkout is the environment-file source; do not independently
regenerate a disposable checkout's environment when the corresponding source
file exists. Copy bytes and file modes without reading, sourcing, printing, or
recording values, and keep the copies ignored and outside commits. Never modify
the source files. If a command needs an environment file that is absent from the
authoritative checkout, stop at the setup boundary and report the missing
relative path instead of synthesizing different configuration.

| Persona                           | Real job                                                                                   | Capability ownership                                                                                                                                                                                                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Working Agent                     | Complete an assigned Plane issue and publish a reviewable result.                          | Actor/profile binding; assignment/run/invocation; discovery; native reads and mutations; restricted TypeScript Code Mode; artifacts; scoped memory and user preferences; private skills; explicit outcome submission and publication.                                                                           |
| Manager and Delegator             | Turn a larger objective into governed work and accept or revise the result.                | Dynamic planning; bounded delegation and lineage; schedules as normal assignments; gardener proposals and revision rollback; evaluator-before-human review; revision; cancellation propagation; HR proposals; chief-of-staff provisioning.                                                                      |
| Skeptical Operator and Integrator | Attempt normal integration and operational failure paths without gaining excess authority. | Live authorization denial; workspace/project isolation; progressive disclosure versus permissions; MCP and SDK convergence; credential boundaries; quotas and cumulative budgets; replay/idempotency; cancellation, timeout, process death and `outcome_unknown`; audit/readback; rollback and safety controls. |

Maintain the durable campaign state under `user-testing-output/plane-agents/`:

- `personas-plane-agents.md`: the three persistent profiles;
- `route-map.md`: every feature journey, entry surface, auth state, and edge case;
- `issue-ledger.md`: observed problem, severity, evidence, root cause, owner, fix, and retest state;
- `wave-log.md`: wave scope, exact candidate, provider/model, findings, fixes, and stop decision;
- `report.md`: final coverage and evidence summary.

Every route-map cell must name a realistic user objective, entry point,
operation sequence, expected visible result, expected durable records,
authorization/audit evidence, failure or denial case, replay expectation, and
cleanup result. A unit test, fixture, schema, count, prompt, or generated file
alone cannot mark a cell clean.

### Minimal final functional matrix

The final live proof is deliberately limited to this matrix. A route-map cell
is covered inside its persona's consolidated journey; it does not require a
separate provider run.

| Matrix row      | Current-candidate live proof | Required coverage                                                                                                                                                                                                                                                                      |
| --------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Worker          | One journey                  | W01–W08, including one permitted and one denied canary, explicit outcome/publication/terminal state, bounded replay or idempotency, and durable readback.                                                                                                                              |
| Manager         | One journey                  | M01–M08, including dynamic planning, delegation lineage and budgets, cancellation, schedule/DST behavior, evaluation and human revision, HR governance, chief-of-staff provisioning, explicit outcome/publication/terminal state, bounded replay or idempotency, and durable readback. |
| Operator        | One journey                  | O01/O03–O09, including one permitted and one denied canary, isolation and operational controls, explicit outcome/publication/terminal state, bounded replay or idempotency, and durable readback.                                                                                      |
| External client | No new journey               | Retain the unchanged O02 exact external MCP/SDK client proof.                                                                                                                                                                                                                          |

#### Provider-free boundaries and provider smoke

Run deterministic destructive and failure boundaries provider-free. This
includes cancellation propagation, timeout or process death, malformed,
oversized, duplicate or out-of-order events, exhausted budgets, stale
revisions, `outcome_unknown`, credential revocation, quota/load limits,
rollback, and safety-stop behavior. These tests prove system behavior without
spending extra model journeys on predetermined outcomes.

Run a separate provider smoke only if provider authentication and preflight
have not already been proved by the first final journey. The smoke may be the
first bounded segment of that journey and must not become a second assignment
or duplicate journey. Stop at the first genuine product or provider failure.

### Current evidence checkpoint (2026-08-24)

The cleaned Agent-era source references are now published and remotely
reachable. The current Plane source is `b655d4ca92c63433d3f44b69cfbb6b2485178579`;
its external gitlinks are plane-mcp `d65df7c94bcd41a3c7795c40c1227e2199889d71`
and the Plane Python SDK `4403116b3601a29d7a2c507c8bef1db768574142`. The
corresponding cleaned Hermes Agent pin is
`283fabf72c0a9c48f231596e6639b65994b5c105`. These pins are provenance inputs,
not evidence that the live matrix has passed.

The V53 current-candidate live matrix is **0/3**: Worker, Manager, and Operator
have no passing current-candidate journey. The V54 diagnostic observed the
correct required tool and search callback through `before_host_call`, followed
by `upstream_channel_closed`; no product fix was proven. The attempted offline
verifier is **0/1**: it stopped at stale configured MCP preflight, before the
functional stages. G0–G3 remain closed; G4 remains open.

Pause live reruns until provider/preflight state is stable. The next acceptance
unit is exactly three consolidated current-candidate persona journeys—Worker,
Manager, and Operator—followed by one production-candidate verifier. Preserve
the existing no-fallback, no-blind-replay, same-candidate evidence rules. Do
not create another duplicate final wave; no ADR changed at this checkpoint.

#### Failure handling and completion

A failed journey returns to its original code owner. Run the affected
provider-free regressions, then rerun only that persona's unreconciled journey
under the established replay rules. Once all three journeys pass on the same
candidate and the retained O02 proof remains applicable, run exactly one full
G4 production-candidate verifier and one consolidated Sol Medium review. Do
not run a second duplicate final wave.

Do not rebuild, refreeze, or create a metadata wrapper merely because evidence
text changed. During dogfood iterations, use targeted tests and the affected
journey. Preserve receipts outside the source commit and bind them to its hash.
The full G3/G4 verifier runs once on the final functionally clean source, not
before every provider attempt or individual fix.

The dogfood loop stops only when the three matrix journeys pass on one current
candidate, every route-map cell is covered by its journey or the retained O02
proof, the deterministic boundary suite passes, no blocker or high-severity
friction remains, replay creates no duplicate semantic side effect, cleanup is
complete, and the source is on a named integration branch. An unavailable
external provider or credential may block provider-backed cells, but ordinary
product defects never do; they return to the fix loop.

## Gates

G0 is complete under the lightweight condition above. Later gates are implementation and delivery checkpoints, not documentation seals:

Current status is G0–G3 **closed** and G4 **open**; the checkpoint above is the
authoritative current evidence summary, while the historical rows below remain
unchanged evidence.

| Gate                                 | Exit condition                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1 — deterministic domain spine      | Fixtures and contract tests create the five Plane records, run snapshot, invocation, and terminal outcome without a model or UI; the deterministic runtime crosses the intended dispatch/event seam; one authorized semantic mutation proves gateway authorization, idempotency, bounded output, and audit.                                                                                                                                                                      |
| G2 — real single-Agent slice         | A real forked-Hermes process completes one assigned outcome through native tools and restricted TypeScript composition; Plane publishes exactly one visible terminal event; denials, stable replay, host-only credentials, and API/CLI readback pass.                                                                                                                                                                                                                            |
| G3 — non-UI breadth                  | Full supported Plane integration/action coverage, memory/skills, schedules, delegation, artifacts, evaluator review, HR governance, chief-of-staff provisioning, MCP convergence, and API/CLI administration satisfy their contracts; settings reuse is proven and no chat UI exists.                                                                                                                                                                                            |
| G4 — functional production candidate | Exactly three current-candidate provider-backed journeys—one Worker, one Manager, and one Operator—cover the full persona matrix with no model fallback; the unchanged O02 exact external-client proof remains applicable; deterministic destructive/failure boundaries pass provider-free; then the candidate passes one clean-checkout contract, authorization, isolation, mutation, compatibility, load, recovery, observability, credential, runbook, and rollback verifier. |

Controlled rollout is intentionally not a gate in this goal. A successor G5 goal may begin only after G4 is complete, the candidate is integrated into a named Plane branch, and rollout/deployment authority is separately granted.

## Implementation phases

Each phase has one accountable lane. A lane may run in parallel with the lanes listed below after its start gate; it must not consume another lane's unfinished contract as if it were complete.

| Phase | Outcome                                                                                                                                                | Lane(s) | Start/dependency                       | Gate  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------- | -------------------------------------- | ----- |
| P0    | Reconcile ADR authority, scope, non-goals, ownership, and the implementation authorization.                                                            | L0      | None                                   | G0    |
| P1    | Generate and freeze the implementation contracts, catalog inputs, fixtures, and verification interfaces needed by later lanes.                         | L1      | G0                                     | G1    |
| P2    | Implement Plane Agent actors, exactly-one-role profiles, assignments, runs, outcomes, and lifecycle governance.                                        | L2      | G0; consumes P1 contracts as available | G1    |
| P3    | Implement the shared operation catalog/gateway, live authorization, idempotency, bounded results, audit, and full-action foundation.                   | L3      | G0; consumes P1 catalog contracts      | G1/G3 |
| P4    | Implement the separate runtime service, leases, events, checkpoints, and narrow Hermes adapter.                                                        | L4      | G0; consumes the runtime contract      | G2    |
| P5    | Implement native Plane tools, progressive discovery, credential-free TypeScript composition, and isolation.                                            | L5      | G1                                     | G2    |
| P6    | Implement private memory/skills, gardeners, immutable revisions/rollback, and schedules as normal assignments.                                         | L6      | G1                                     | G3    |
| P7    | Implement dynamic planning, delegation lineage, HR proposals, chief-of-staff provisioning, and evaluator-before-human review.                          | L7      | G2                                     | G3    |
| P8    | Converge the supported external MCP/SDK surface on the shared gateway with explicit per-action disposition.                                            | L8      | G1                                     | G3    |
| P9    | Implement platform isolation, credentials, quotas, observability, reliability, incident response, and reused settings/admin surfaces.                  | L9, L10 | L9 after G0; L10 after G1              | G4    |
| P10   | Run the conditional provider smoke, one consolidated journey per persona, targeted root-fix/retest loops, and one final production-candidate verifier. | L11     | G2                                     | G4    |

## Parallel lane map

| Lane | Responsibility                                                                                                                                                 | Start → finish | Parallel with                                |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------------------------------- |
| L0   | Product, architecture, and contract control; maintain ADR/GOAL coherence and scope decisions.                                                                  | — → G0         | L1                                           |
| L1   | Verification and release engineering; deterministic contracts, fixtures, evidence, compatibility, and final candidate proof.                                   | G0 → G4        | L0, L2, L3, L4, L5, L6, L7, L8, L9, L10, L11 |
| L2   | Plane Agent domain and lifecycle; actors, profiles, assignments, runs, outcomes, roles, HR, chief-of-staff, and review state.                                  | G0 → G3        | L1, L3, L4, L10                              |
| L3   | Operation catalog, gateway, authorization, idempotency, and audit; all native, runtime, Code Mode, and MCP paths share the seam.                               | G0 → G3        | L1, L2, L4, L10                              |
| L4   | Separate runtime service and Hermes kernel adapter; dispatch, leases, cancellation, event ingress, checkpoints, and recovery.                                  | G0 → G2        | L1, L2, L3, L5, L6, L9                       |
| L5   | Native tools, progressive discovery, and restricted TypeScript isolation; credential-free host callbacks and cumulative budgets.                               | G1 → G2        | L1, L4, L6, L9, L10                          |
| L6   | Private memory, skills, gardeners, and schedules; strict Agent walls, provenance, revisions, rollback, and normal assignment triggers.                         | G1 → G3        | L1, L4, L5, L7, L10                          |
| L7   | Dynamic planning and delegation; dedicated delegator, lineage, scope/budget, HR governance, chief-of-staff, and evaluator integration.                         | G2 → G3        | L1, L6, L8, L10, L11                         |
| L8   | External MCP and SDK convergence; preserve compatibility while routing supported actions through the gateway.                                                  | G1 → G3        | L1, L7, L9, L10, L11                         |
| L9   | Platform, security, reliability, and operations; isolation, credentials, limits, telemetry, runbooks, kill switches, and rollback.                             | G0 → G4        | L1, L4, L5, L8, L10, L11                     |
| L10  | Minimal administration and settings; API/CLI first, then extend existing Plane settings primitives only.                                                       | G1 → G3        | L1, L2, L3, L5, L6, L7, L8, L9, L11          |
| L11  | Functional dogfood and production proof; three consolidated persona journeys, requirement-level evidence, live readback, canaries, and one final verification. | G2 → G4        | L1, L7, L8, L9, L10                          |

## Worker and review protocol

- Use GPT-5.6 Luna xhigh workers for implementation, debugging, preparation, builds, bounded verification, and review work.
- Use Arena only when an implementation has multiple plausible, high-impact designs whose choice could materially change an architecture, trust boundary, or durable contract. Routine root-cause fixes, generated-contract synchronization, builds, tests, integrations, and evidence updates proceed directly with GPT-5.6 Luna workers. When Arena is warranted, use isolated candidates, a gradeable rubric, one compact synthesis note, and archive its tasks after integration. Sol Medium remains reserved for the one explicitly justified final review below.
- Delegate implementation and review through separate Codex tasks owned and routed by the coordinator. Workers and reviewers must not create nested subagents or an alternate delegation tree.
- Let Luna iterate within its lane until the complete lane verifier is green and the coordinator judges its commit and evidence ready for integration. Luna owns routine remediation, mechanical follow-ups, environment reruns, and documentation/status corrections without a Sol review.
- The coordinator may accept and integrate a lane after inspecting its scope, verifier output, requirement evidence, unresolved risks, and exact commit. A lane does not receive a standalone Sol review by default.
- GPT-5.6 Sol Medium is never a default worker or reviewer. Use it at most once, only when the coordinator explicitly records a high-stakes cross-judge/final-review justification after the final matrix and production verifier pass. Do not use Sol for individual fixes, commits, partial finding sets, or repeated closure passes.
- Archive each implementation task after its accepted commit and evidence have been integrated into a consolidated candidate. Preserve the handoff in the parent task; do not maintain a second narrative worklog for routine progress.
- Every future task packet must list its applicable ADRs by number, title, and path, along with the lane's objective, files/surfaces, dependencies, verifier, stop condition, and expected evidence.
- Every implementation handoff must include an original-design reuse map naming the established owners extended, any new internal module, and its deletion-test result.
- Keep lane ownership disjoint. Reviewers may report boundary conflicts or missing proof, but they do not widen the lane without an explicit coordinator decision.

## Requirement-level completion proof

The full outcome is complete only when every row below has executable evidence from the actual implementation, coordinator readback, and the applicable independent gate review. Documentation, a fixture, or a generated artifact alone is not proof.

| Requirement                  | Passing proof                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One native Plane Agent model | API/domain tests prove one product/runtime mode, exactly one role per Agent, live permission authority, HR governance, evaluator review, and chief-of-staff provisioning without a second authorization model.                                                                                                                                                                                                                                                                                                                                                                  |
| Independent lifecycles       | Contract and migration tests prove independent `AgentActor`, `ProfileVersion`, `AssignmentContract`, `RunAttempt`, and `OutcomeSubmission` state, immutable run snapshots, multi-invocation continuation, revision history, and no Hermes-session authority.                                                                                                                                                                                                                                                                                                                    |
| Gateway authority            | Native tools, TypeScript host callbacks, runtime lifecycle mutations, and external MCP traces all cross the shared gateway with caller binding, live authorization, idempotency/reconciliation, bounded results, structured denial, and append-only audit.                                                                                                                                                                                                                                                                                                                      |
| Runtime safety               | Deterministic and real Hermes adapters pass event ordering, duplicate/out-of-order, lease death, cancellation, checkpoint, budget, `outcome_unknown`, host-only credential, network/filesystem/process isolation, and exactly-one-terminal-event tests.                                                                                                                                                                                                                                                                                                                         |
| Full action breadth          | The supported Plane integration/action catalog and external MCP surface are generated or explicitly dispositioned per action, with representative real-client coverage and no count-only or wildcard claim.                                                                                                                                                                                                                                                                                                                                                                     |
| Context and delegation       | Agent-private memory/skills, gardener revisions/rollback, schedules, dynamic plans, delegation lineage, cancellation, and permissions pass leakage, provenance, replay, and recovery tests. No saved workflow-definition product is introduced.                                                                                                                                                                                                                                                                                                                                 |
| Non-UI operability           | API, CLI, fixtures, operator surfaces, ordinary Plane object pages, and reused settings/admin primitives configure and inspect the required system. No chat, composer, thread, inbox, sidecar, transcript, or conversation-navigation UI is required.                                                                                                                                                                                                                                                                                                                           |
| Functional production proof  | One current-candidate Worker journey covers W01–W08, one Manager journey covers M01–M08, and one Operator journey covers O01/O03–O09; the unchanged O02 exact external-client proof remains applicable. Each live journey records permitted/denied canaries, explicit outcome/publication/terminal state, bounded replay or idempotency, and audit/version readback as applicable. Deterministic destructive/failure boundaries and clean-checkout static/contract/security/reliability/load/recovery/observability checks pass provider-free once on the same final candidate. |

Completion requires all rows, G1–G4, the three current-candidate matrix journeys, the retained O02 proof, the deterministic boundary suite, one final full production-candidate verifier, one consolidated Sol Medium review, a named integration branch, a clean final worktree, and no unresolved blocker or high-severity friction, security-critical failure, credential disclosure, authorization bypass, duplicate committed mutation, missing audit event, unsafe replay, or isolation escape. A second duplicate “final clean wave” is explicitly not required. Controlled rollout and GA evidence are explicitly not required by this goal.

## Controlling minimal-live amendment (2026-08-25)

Status: **active**. This section supersedes and pauses every earlier instruction
in this file that requires three provider-backed Worker, Manager, and Operator
journeys, per-route provider commissions, or progress measured by historical
route cells. Those passages remain as decision history only. The product scope,
ADRs, non-UI boundary, G1–G3 evidence, and requirement-level contracts remain
unchanged.

The shortest complete G4 proof is two provider-backed flows and one
provider-free operational package on one immutable candidate:

| Acceptance unit    | Model          | Unique behavior                                                                                                                                               |
| ------------------ | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Worker             | GPT-5.6 family | Restricted Code Mode composition, private skill and subject-bound context use, one semantic mutation, outcome, publication, and terminal readback             |
| Delegator          | GPT-5.6 family | Standard native-tool loop, progressive discovery, case-specific planning, bounded delegation, lineage and budget, outcome, publication, and terminal readback |
| Operations package | None           | Authorization, lifecycle, schedules, recovery, replay, isolation, hostile ingress, load, audit, rollback, and every deterministic companion assertion         |

Retain O02 as the exact external MCP/SDK proof when its source, contract, and
digest applicability still bind to the final candidate. Operator is a
verification persona, not a distinct Plane Agent role or runtime path in
ADR-0005. Its unique obligations are deterministic; its previous model work
duplicated behavior now proved by Worker and Delegator.

### Provider-backed acceptance flows

The Worker runs one fresh `code_mode_only` assignment. One bounded TypeScript
module performs this logical sequence through credential-free host callbacks
and the shared Operation Gateway:

```text
catalog.search
catalog.describe(exact returned operationId)
search_workspace
work_item.read(opaque preparedCallRef)
agent.context.read(bound subject)
work_item.rename
agent.outcome.submit(one artifact, one evidence item)
plane_publish(content only)
```

Its receipt proves the private skill projection was consumed, no raw identifier
was reconstructed, exactly one semantic mutation occurred, and outcome,
publication, terminal event, audit, and durable readback agree. Its evidence
package also owns Code Mode confinement, malformed and cross-bound prepared
calls, cross-user context denial, one permitted canary, one exact denied canary
with zero effects, and zero-delta replay. Deterministic companions do not add
model runs.

The Delegator runs one fresh standard native-tool assignment. It performs exact
`catalog.search -> catalog.describe` progressive discovery for one non-eager
operation, executes one permitted operation, produces a case-specific plan,
creates one bounded child assignment with an explicit reason, and submits and
publishes one terminal outcome. Its receipt proves no saved workflow product,
parent lineage, bounded scope and budget, an independent child run, audit, and
durable readback. Its evidence package also owns one exact denied canary,
cancellation propagation, schedules and DST, evaluator-before-human revision,
HR approval and denial, chief-of-staff scoping, and terminal-parent denial.
M08 closes only when revision, evaluator and human decisions, lineage, and
immutable prior-run readback agree. Deterministic companions do not add model
runs.

The earlier W01–W08, M01–M08, and O01/O03–O09 labels remain a coverage taxonomy,
not provider-run units. Every label maps exactly once to the Worker package,
Delegator package, operations package, or retained O02 proof.

### Provider-free operational package

Run once against the same candidate with `providerAttempts=0` and exact owner
test IDs. It must cover:

- actor, workspace, object, and SDK caller authorization, permitted and denied
  canaries, and absence of any second operation-approval system;
- Code Mode confinement, callback binding, idempotency, and zero-delta replay
  for dispatch, mutation, submit, and publication;
- cancellation, schedules/DST, evaluator and human revision, HR denials,
  chief-of-staff scoping, private memory, subject isolation, skill promotion,
  and rollback;
- lease rotation, revocation and expiry; cumulative budgets; safe checkpoints;
  waiting-for-input and Plane-owned continuation across replacement invocations;
- distinct provider-request, runtime-invocation, and gateway-mutation
  `outcome_unknown` handling;
- malformed, oversized, duplicate, out-of-order, forged, cross-bound, illegal
  lifecycle, incompatible-version, and bounded artifact/payload rejection;
- bounded load, health, quota, safety stop, append-only audit, forward-only
  API/runtime rollback, full catalog disposition, and retained O02 applicability.

Nondisruptive checks may run in parallel with the live flows. Load, credential
or lease revocation, safety-stop, and rollback use a separate stack or run after
both live flows because they intentionally disturb shared dependencies.

### Execution and completion

All implementation tasks use Arena unless the task is a mechanical generated
artifact synchronization, build, evidence update, or exact rerun with no design
choice. Arena candidates use GPT-5.6 Luna; GPT-5.6 Sol Medium is reserved for a
single justified cross-judge or the consolidated final review. Disposable work
uses `/private/tmp`. Environment inputs are copied byte-for-byte from exactly
the seven approved files in `/Users/nqh/Desktop/CODES/plane`; `setup.sh` is not
run and file contents are not printed. Provider-backed work uses the existing
authorized source without copying credentials into generated code or runtime
environment.

After one read-only candidate/image/environment preflight, run the Worker,
Delegator, and nondisruptive provider-free units concurrently only if their
workspaces, actors, assignments, work items, idempotency namespaces, leases,
runtime processes/sockets, result paths, and cleanup labels are isolated. If
the provider relay admits only one model flow, run each complete provider flow
serially; never start two invocations merely to queue their provider sends.

Pre-provider workflow friction has zero delivery weight: fix the workflow and
continue the not-yet-started unit. Once a provider request begins, preserve the
first genuine result for that flow. Never fallback, blindly retry, or replay
`outcome_unknown`. An already-started sibling may finish. Changed bound source
or image bytes invalidate prior live receipts unless an explicit digest-level
applicability contract proves otherwise.

Resume in four units:

1. Replace the current repeated persona commissions with one composite Worker
   descriptor, one composite Delegator descriptor, and one provider-free
   operations descriptor.
2. Freeze one exact candidate and pass its provider-free packages and preflight.
3. Run the two provider-backed flows under the concurrency rule above; fix only
   the failing owner seam and rerun only the invalidated flow on a new exact
   candidate.
4. Run one production-candidate verifier and one consolidated review, integrate
   the named branch, and leave the worktree clean.

G4 and this goal are complete only when:

```text
live = passed(Worker) + passed(Delegator) = 2/2
and operator_provider_free_package = passed
and retained_O02 = applicable
and final_production_candidate_verifier = passed
and consolidated_review = passed
and integration_branch_and_worktree = clean
```

Route-cell totals, provider-attempt counts, historical candidates, and repeated
verification waves are not progress metrics. No third provider-backed Operator
journey, duplicate provider smoke, or second final clean wave is required.

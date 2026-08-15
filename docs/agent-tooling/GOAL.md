# Goal: Complete the non-UI Plane Agent system

## Objective

Build and independently verify one functionally complete non-UI Plane Agent system, conforming to [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) through [ADR-0010](../decisions/0010-plane-runtime-contract.md), for backend assignments, runs, artifacts, conversations, outcomes, reviews, product events, and every supported Plane integration/action. The system must be operable and verifiable through real provider-backed Plane Agent journeys using Plane APIs, CLI/fixtures, ordinary Plane object pages, operator surfaces, and reused settings surfaces.

This goal covers the full Plane Agent control plane and the hidden execution service. It does not require chat, composer, thread, inbox, sidecar, transcript, or conversation-navigation UI.

Functional completion and controlled rollout are separate outcomes. This goal ends when the non-UI product passes the complete live dogfood matrix, the production-candidate checks, and integration into a named Plane branch. Development, allowlisted-workspace, expanded-cohort, and GA rollout are a successor goal requiring their own deployment authority; they are not evidence that the product implementation works and are not a completion condition here.

The older G4 artifact bindings and Wave 0X evidence below are historical, not
the active delivery state. The current exact Plane candidate is
`dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`, with Hermes
`bc7f13d2ab392752f2667b176c646339c49405f9`. S00 Wave 0AT passed at Plane
`dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` with one fresh Luna primary and one
eligible provider-disabled replay. Provider-free PF1 evidence is complete for
W01–W08, M01–M08, and the tested Operator contracts. The first broader persona
attempts proved that the accepted runner exposes only the fixed S00 commission;
the existing runner is gaining one typed W/M/O scenario seam before those live
routes resume. No provider-backed W/M/O result is inferred here. The final
candidate image, exact-image red team, G4 verifier, and consolidated Sol review
remain pending. G5 remains a separate rollout goal.

## Status and authorization

| Active item        | Current truth                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Delivery candidate | Exact Plane `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`; exact Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`; supporting PF1 fixes/tests include `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1`, `2105fb9e21687103939a77b7e26a0959f1d50f51`, `8c9b20bf544355b20b0c9e69b0ad1ee5b48e905e`, and `76e26ce5de1f300eab93505a2c885b984f60fcd0`.                                            |
| Functional gate    | S00 Wave 0AT is clean at Plane `dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` with Hermes `bc7f13d2ab392752f2667b176c646339c49405f9`: ten ordered upstream `2xx` attempts, three searches, two reads, one exact `NOT_AUTHORIZED` denial, one submit, one applied publication, one matching terminal, and `RuntimeExit.completed`; replay semantic deltas were zero and cleanup passed. |
| Provider-free PF1  | Worker W01–W08 passed 35 real Django/API/DB/CLI/socket/isolation tests unchanged. Manager M01–M08 passed 33 tests after `f621fdd89797db2d1b74205c6ce6d5b0bd4725d1` and `2105fb9e21687103939a77b7e26a0959f1d50f51`. Operator O01 and O03–O09 passed targeted real service/API/database/CLI contracts; the final exact-image red team remains pending.                               |
| Live W/M/O wave    | The initial persona tasks stopped without route claims because the accepted live runner hardcodes the S00 Worker and prompt. One typed scenario input is being added to that existing runner; PF1 tests do not make W/M routes clean. O02 is separately clean from the real external-client closure recorded at product source `dfcd3ea543e58109b0d314e3bdfd6375c65b35ff`.         |
| Final verification | Pending clean provider-backed W/M/O routes, the final candidate image, exact-image red team, one full G4 verifier, and one consolidated Sol Medium review.                                                                                                                                                                                                                         |
| G5                 | Out of scope. Rollout starts only under a separate authorized goal after G4 functional completion.                                                                                                                                                                                                                                                                                 |

The table below preserves accepted gate history and older frozen artifact
bindings. Its G4/dogfood rows are historical evidence and do not override the
active execution status above.

| Item                                | Current state                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G0                                  | Complete as a lightweight start condition: ADRs 0001–0010 exist and cohere, scope and non-goals are explicit here, and local implementation is authorized.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| G1                                  | Complete at Plane commit `44edd3a6e94b4c7ab6efb2e92e516699a0cb2d12`, independently accepted by the G1 gate reviewer. Fresh PostgreSQL proved the linear 0122→0130 migration chain, 0130 reverse/reapply cleanup, serialized concurrent replay, and UPDATE/DELETE/TRUNCATE denial on both append-only runtime-evidence tables. The exact no-model/no-UI G1 body crossed canonical-JSON dispatch and ingress, kept runtime completion evidence-only, then used the authorized/idempotent/audited gateway and explicit `OutcomeSubmission` to record exactly one terminal product event. Durable counts were one runtime event, one runtime exit, one outcome, one terminal event, two gateway records, and eight audit records. Packaged lifecycle schemas matched the accepted L1 manifest digests.                                                                                                                                                                                                                            |
| G2                                  | Complete at Plane commit `c6d12931aefcafe9abc9fcc6775fd24ea91c3e5f` with Hermes commit `e573a46611e2cb988f1ab43ad34cd8cc3b2cb659`, independently accepted by the single consolidated G2 reviewer. The committed proof begins at the production `agent_supervisor` command, launches the separate trusted Hermes bootstrap with a loopback deterministic provider, executes progressive discovery, native read, restricted Code Mode, one gateway mutation, explicit outcome submission/publication, transcript-only final text, and matching API/CLI readback. Durable counts were one actor, profile, assignment, run, invocation, outcome, and visible terminal event; six gateway receipts across five operations; and twelve correlated audit rows. Exact replay created no child, usage, receipt, audit row, outcome, publication, terminal event, or semantic side effect. Cancellation, timeout/process death, malformed evidence, budget failure, and `outcome_unknown` reconcile through Plane without blind replay. |
| G3                                  | Complete at Plane commit `7c9d35f4c324865c27c84da5016be2c84e460bcc`, independently accepted by the consolidated G3 reviewer in Codex task `019fd6ab-bfb0-7322-8bc4-f6e6609f6bee`. The accepted offline baseline reran the G3 prerequisite at `256/256`, with reversible migrations through leaf `0140`, the complete `177 = 86 gateway + 90 unsupported + 1 local` action disposition, exact candidate-derived Hermes/MCP/SDK revisions, read-only host-resolved community credential topology, no-chat-UI checks, and isolated cleanup.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| G4 offline candidate                | Sol P1 closure remains offline-only. The current one-source-commit/one-metadata-wrapper candidate is source `1d1012f71c48615bb28b7988ce74c82421aa1d53` with API `plane-agent-api:g4-1d1012f7` / `sha256:0a350d4619c9edd55769ed8efdaa2dc740de551689ec41abd682e73565b6c3f2` and runtime `plane-agent-runtime:hermes-d2e65510-g4-1d1012f7` / `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`, all bound to Hermes `d2e655101f263329359e7d0de9d0b856202a3e4b`. Accepted G3 baseline remains `7c9d35f4c324865c27c84da5016be2c84e460bcc`; no live acceptance is claimed.                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Dogfood branch                      | `codex/agent-functional-dogfood` starts from wrapper `3f2a478209fb94049376f781d33ddd4b63a038de` and source `1d1012f71c48615bb28b7988ce74c82421aa1d53`. Dogfood evidence and documentation may advance the branch without refreezing images. Functional fixes must extend the established Plane or Hermes owner and receive targeted verification; images and immutable provenance are rebuilt once from the final clean source before the final G4 verifier.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Provider egress seam                | The trusted runtime owns an invocation-bound AF_UNIX relay and the sole external-egress network; Hermes commit `d2e655101f263329359e7d0de9d0b856202a3e4b` is wired through the existing bootstrap/service chain and the candidate image is pinned below. The live authority/config contract admits only the typed ChatGPT subscription descriptor `openai-codex/gpt-5.6-luna` at `https://chatgpt.com/backend-api/codex/responses`, with fallback disabled, and validates it before credential read, relay startup, DNS, or provider request. Separately authorized live provider proof remains pending and requires a fresh run.                                                                                                                                                                                                                                                                                                                                                                                             |
| Live functional dogfood             | The retained explicitly authorized live failure receipt SHA-256 is `2013336c367397263ea1d5fdf41e46dfda5ed449c8f0be39913f5c6d5c727861`; it failed at `api-invocation` with Docker exit 125 because the runner directly mounted the caller-owned provider source under `/private/tmp`, which was not bind-visible to Colima. No Plane run, invocation, or evidence object was created and no provider request occurred. The source correction stages the credential in a Docker-visible, owner-only location. It remains unproven until the fast provider smoke and complete dogfood matrix run successfully. An older live canary receipt `20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a` remains historical `outcome_unknown` evidence and must not be replayed.                                                                                                                                                                                                                                           |
| Controlled rollout                  | Out of scope for this goal. Historical G5 branches contain rollout-control schemas and offline evidence tooling, but no rollout stage was executed or promoted. Do not restore or extend that work until the functionally complete candidate is integrated and a separate rollout goal is authorized.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Retained pre-live lifecycle failure | The earlier pre-live root failure retained receipt SHA-256 `4e2a96a9fcaa5dccf5a8a1994b008016bf45aa7b8cc5c163f32aabb4cb4f958c` and failure-log SHA-256 `a412273116e90263dabade32d29e1a2b856e8dde64fe8c047c88850a5bf7bc52`; it made no provider request, live invocation, credential mutation, or G5 action and is not `outcome_unknown`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Source authorization                | Codex task `019fc7db-e8bf-7f92-8f2b-b2346e5eeeb8`, 2026-08-04.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

The current G4 remediation binds the final wrapper through the external
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
| Independent review | Consolidated Sol Medium reviewer task `019fd8e8-b562-7cf3-a20b-bb5307a65e66` accepted the earlier offline G4 baseline with no actionable P0/P1/P2 remaining. The current provider-reconciliation/resolver correction has complete Luna verification but awaits the single consolidated current-candidate review after live G4 evidence is available.                                                                            |

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
product/runtime mode with different Plane-owned profiles and roles. All model
execution uses the GPT-5.6 family: GPT-5.6 Luna for Plane Agent journeys and
Luna xhigh for routine diagnosis and implementation; one GPT-5.6 Sol Medium
review occurs only after the complete final wave and production verifier pass.

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

### Wave order

1. **Fast provider smoke:** before any broad suite, start the real runtime and
   complete one fresh read, denied canary, submit, and publish journey. Stop at
   the first real boundary failure and diagnose it directly.
2. **Happy-path coverage:** the three personas execute every feature journey
   assigned in the route map using GPT-5.6 Luna.
3. **Boundary coverage:** repeat the journeys with denial, cross-scope access,
   invalid input, interruption, replay, cancellation, restart, timeout,
   exhausted budget, stale revision, and external-client edge cases.
4. **Root-fix and retest:** batch observed blocker and friction findings, fix
   the original code owner, run only affected regression tests, and send dirty
   route-map cells back to the same personas.
5. **Final clean wave:** after all cells are clean, run the complete dogfood
   matrix once, then run one full G4 production-candidate verifier and one
   consolidated Sol Medium review.

Do not rebuild, refreeze, or create a metadata wrapper merely because evidence
text changed. During dogfood iterations, use targeted tests and the affected
journey. Preserve receipts outside the source commit and bind them to its hash.
The full G3/G4 verifier runs once on the final functionally clean source, not
before every provider attempt or individual fix.

The dogfood loop stops only when every route-map cell is clean with real
evidence, no blocker or high-severity friction remains, replay creates no
duplicate semantic side effect, cleanup is complete, and the source is on a
named integration branch. An unavailable external provider or credential may
block provider-backed cells, but ordinary product defects never do; they return
to the fix loop.

## Gates

G0 is complete under the lightweight condition above. Later gates are implementation and delivery checkpoints, not documentation seals:

| Gate                                 | Exit condition                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1 — deterministic domain spine      | Fixtures and contract tests create the five Plane records, run snapshot, invocation, and terminal outcome without a model or UI; the deterministic runtime crosses the intended dispatch/event seam; one authorized semantic mutation proves gateway authorization, idempotency, bounded output, and audit.                       |
| G2 — real single-Agent slice         | A real forked-Hermes process completes one assigned outcome through native tools and restricted TypeScript composition; Plane publishes exactly one visible terminal event; denials, stable replay, host-only credentials, and API/CLI readback pass.                                                                             |
| G3 — non-UI breadth                  | Full supported Plane integration/action coverage, memory/skills, schedules, delegation, artifacts, evaluator review, HR governance, chief-of-staff provisioning, MCP convergence, and API/CLI administration satisfy their contracts; settings reuse is proven and no chat UI exists.                                             |
| G4 — functional production candidate | Three real provider-backed persona journeys cover every supported Plane Agent capability and failure boundary, with no model fallback; the final clean candidate then passes clean-checkout contract, authorization, isolation, mutation, compatibility, load, recovery, observability, credential, runbook, and rollback checks. |

Controlled rollout is intentionally not a gate in this goal. A successor G5 goal may begin only after G4 is complete, the candidate is integrated into a named Plane branch, and rollout/deployment authority is separately granted.

## Implementation phases

Each phase has one accountable lane. A lane may run in parallel with the lanes listed below after its start gate; it must not consume another lane's unfinished contract as if it were complete.

| Phase | Outcome                                                                                                                               | Lane(s) | Start/dependency                       | Gate  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------- | ------- | -------------------------------------- | ----- |
| P0    | Reconcile ADR authority, scope, non-goals, ownership, and the implementation authorization.                                           | L0      | None                                   | G0    |
| P1    | Generate and freeze the implementation contracts, catalog inputs, fixtures, and verification interfaces needed by later lanes.        | L1      | G0                                     | G1    |
| P2    | Implement Plane Agent actors, exactly-one-role profiles, assignments, runs, outcomes, and lifecycle governance.                       | L2      | G0; consumes P1 contracts as available | G1    |
| P3    | Implement the shared operation catalog/gateway, live authorization, idempotency, bounded results, audit, and full-action foundation.  | L3      | G0; consumes P1 catalog contracts      | G1/G3 |
| P4    | Implement the separate runtime service, leases, events, checkpoints, and narrow Hermes adapter.                                       | L4      | G0; consumes the runtime contract      | G2    |
| P5    | Implement native Plane tools, progressive discovery, credential-free TypeScript composition, and isolation.                           | L5      | G1                                     | G2    |
| P6    | Implement private memory/skills, gardeners, immutable revisions/rollback, and schedules as normal assignments.                        | L6      | G1                                     | G3    |
| P7    | Implement dynamic planning, delegation lineage, HR proposals, chief-of-staff provisioning, and evaluator-before-human review.         | L7      | G2                                     | G3    |
| P8    | Converge the supported external MCP/SDK surface on the shared gateway with explicit per-action disposition.                           | L8      | G1                                     | G3    |
| P9    | Implement platform isolation, credentials, quotas, observability, reliability, incident response, and reused settings/admin surfaces. | L9, L10 | L9 after G0; L10 after G1              | G4    |
| P10   | Run the provider smoke, complete persona dogfood waves, targeted root-fix/retest loops, and one final production-candidate verifier.  | L11     | G2                                     | G4    |

## Parallel lane map

| Lane | Responsibility                                                                                                                          | Start → finish | Parallel with                                |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------------------------------- |
| L0   | Product, architecture, and contract control; maintain ADR/GOAL coherence and scope decisions.                                           | — → G0         | L1                                           |
| L1   | Verification and release engineering; deterministic contracts, fixtures, evidence, compatibility, and final candidate proof.            | G0 → G4        | L0, L2, L3, L4, L5, L6, L7, L8, L9, L10, L11 |
| L2   | Plane Agent domain and lifecycle; actors, profiles, assignments, runs, outcomes, roles, HR, chief-of-staff, and review state.           | G0 → G3        | L1, L3, L4, L10                              |
| L3   | Operation catalog, gateway, authorization, idempotency, and audit; all native, runtime, Code Mode, and MCP paths share the seam.        | G0 → G3        | L1, L2, L4, L10                              |
| L4   | Separate runtime service and Hermes kernel adapter; dispatch, leases, cancellation, event ingress, checkpoints, and recovery.           | G0 → G2        | L1, L2, L3, L5, L6, L9                       |
| L5   | Native tools, progressive discovery, and restricted TypeScript isolation; credential-free host callbacks and cumulative budgets.        | G1 → G2        | L1, L4, L6, L9, L10                          |
| L6   | Private memory, skills, gardeners, and schedules; strict Agent walls, provenance, revisions, rollback, and normal assignment triggers.  | G1 → G3        | L1, L4, L5, L7, L10                          |
| L7   | Dynamic planning and delegation; dedicated delegator, lineage, scope/budget, HR governance, chief-of-staff, and evaluator integration.  | G2 → G3        | L1, L6, L8, L10, L11                         |
| L8   | External MCP and SDK convergence; preserve compatibility while routing supported actions through the gateway.                           | G1 → G3        | L1, L7, L9, L10, L11                         |
| L9   | Platform, security, reliability, and operations; isolation, credentials, limits, telemetry, runbooks, kill switches, and rollback.      | G0 → G4        | L1, L4, L5, L8, L10, L11                     |
| L10  | Minimal administration and settings; API/CLI first, then extend existing Plane settings primitives only.                                | G1 → G3        | L1, L2, L3, L5, L6, L7, L8, L9, L11          |
| L11  | Functional dogfood and production proof; persona journeys, requirement-level evidence, live readback, canaries, and final verification. | G2 → G4        | L1, L7, L8, L9, L10                          |

## Worker and review protocol

- Use Luna xhigh workers for implementation lanes and bounded verification work.
- Delegate implementation and review through separate Codex tasks owned and routed by the coordinator. Workers and reviewers must not create nested subagents or an alternate delegation tree.
- Let Luna iterate within its lane until the complete lane verifier is green and the coordinator judges its commit and evidence ready for integration. Luna owns routine remediation, mechanical follow-ups, environment reruns, and documentation/status corrections without a Sol review.
- The coordinator may accept and integrate a lane after inspecting its scope, verifier output, requirement evidence, unresolved risks, and exact commit. A lane does not receive a standalone Sol review by default.
- Use Sol Medium only for consolidated, independently verifiable system gates: the combined G2 real-Agent slice, the combined G3 non-UI breadth candidate, and the final clean G4 functional production candidate. Batch all dogfood fixes and compatible seams before that review. Rollout review belongs to a separate authorized goal.
- A standalone pre-gate Sol review is exceptional. Use one only when a security- or authority-critical boundary cannot reasonably wait for its consolidated gate and the unresolved decision blocks further integration. The coordinator must record why the exception was necessary.
- One Sol reviewer owns each consolidated gate from initial assessment through closure. Return all findings as one batch to Luna workers, accumulate every remediation, rerun the complete gate verifier, and request one closure review from the same reviewer. Do not request review for individual fixes, commits, or partial finding sets.
- Limit a normal consolidated gate to two Sol passes: one full assessment and one closure pass. If closure still fails, Luna and the coordinator must finish the entire remaining finding set and produce fresh complete evidence before the same reviewer is asked again; repeated reviewer polling is forbidden.
- Archive each implementation task after its accepted commit and evidence have been integrated into a consolidated candidate. Preserve the handoff in the parent task; do not maintain a second narrative worklog for routine progress.
- Every future task packet must list its applicable ADRs by number, title, and path, along with the lane's objective, files/surfaces, dependencies, verifier, stop condition, and expected evidence.
- Every implementation handoff must include an original-design reuse map naming the established owners extended, any new internal module, and its deletion-test result.
- Keep lane ownership disjoint. Reviewers may report boundary conflicts or missing proof, but they do not widen the lane without an explicit coordinator decision.

## Requirement-level completion proof

The full outcome is complete only when every row below has executable evidence from the actual implementation, coordinator readback, and the applicable independent gate review. Documentation, a fixture, or a generated artifact alone is not proof.

| Requirement                  | Passing proof                                                                                                                                                                                                                                                                                             |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One native Plane Agent model | API/domain tests prove one product/runtime mode, exactly one role per Agent, live permission authority, HR governance, evaluator review, and chief-of-staff provisioning without a second authorization model.                                                                                            |
| Independent lifecycles       | Contract and migration tests prove independent `AgentActor`, `ProfileVersion`, `AssignmentContract`, `RunAttempt`, and `OutcomeSubmission` state, immutable run snapshots, multi-invocation continuation, revision history, and no Hermes-session authority.                                              |
| Gateway authority            | Native tools, TypeScript host callbacks, runtime lifecycle mutations, and external MCP traces all cross the shared gateway with caller binding, live authorization, idempotency/reconciliation, bounded results, structured denial, and append-only audit.                                                |
| Runtime safety               | Deterministic and real Hermes adapters pass event ordering, duplicate/out-of-order, lease death, cancellation, checkpoint, budget, `outcome_unknown`, host-only credential, network/filesystem/process isolation, and exactly-one-terminal-event tests.                                                   |
| Full action breadth          | The supported Plane integration/action catalog and external MCP surface are generated or explicitly dispositioned per action, with representative real-client coverage and no count-only or wildcard claim.                                                                                               |
| Context and delegation       | Agent-private memory/skills, gardener revisions/rollback, schedules, dynamic plans, delegation lineage, cancellation, and permissions pass leakage, provenance, replay, and recovery tests. No saved workflow-definition product is introduced.                                                           |
| Non-UI operability           | API, CLI, fixtures, operator surfaces, ordinary Plane object pages, and reused settings/admin primitives configure and inspect the required system. No chat, composer, thread, inbox, sidecar, transcript, or conversation-navigation UI is required.                                                     |
| Functional production proof  | Every dogfood route-map cell has real provider-backed journey evidence; clean-checkout static/contract/security/reliability/load/recovery/observability checks pass once on the final candidate; live permitted/denied canaries, audit/version readback, rollback, and safety-stop behavior are recorded. |

Completion requires all rows, G1–G4, a clean final dogfood wave, one final full production-candidate verifier, one consolidated Sol Medium review, a named integration branch, a clean final worktree, and no unresolved blocker or high-severity friction, security-critical failure, credential disclosure, authorization bypass, duplicate committed mutation, missing audit event, unsafe replay, or isolation escape. Controlled rollout and GA evidence are explicitly not required by this goal.

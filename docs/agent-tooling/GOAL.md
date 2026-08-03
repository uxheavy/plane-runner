# Durable Ultragoal: Complete the non-UI Plane Agent system

## Active objective

Complete and independently verify the objective defined in /Users/nqh/Desktop/CODES/plane/docs/agent-tooling/GOAL.md.

When this goal is activated with `create_goal`, use that exact objective and omit `token_budget`.

This is the durable program state for later unattended delegation. It is intentionally compact at the active-objective line and detailed below so another coordinator can resume from any interruption without treating a narrative claim as progress.

## Observable outcome and audience

The outcome is one complete, production-ready Plane Agent system for backend conversations, assignments, runs, artifacts, outcomes, reviews, and product events. It includes the full Plane Agent control plane and every supported Plane integration/action required for completion. It does not include chat, composer, thread, inbox, sidecar, transcript, or conversation-navigation UI.

The system must be operable and verifiable through Plane APIs, CLI/fixtures, ordinary Plane object pages, operator surfaces, and reused settings surfaces. Every required administration workflow reuses Plane's existing settings routes, forms, tables, drawers/modals, services, stores, permissions, and `@plane/ui` components. No new settings framework or parallel design system is created.

The audience is:

- Plane users and workspace administrators who assign work and review outcomes.
- Operators responsible for credentials, limits, observability, rollout, incident response, and rollback.
- Plane maintainers who own product state, permissions, application services, and the Operation Gateway.
- Hermes maintainers who own the hidden execution kernel and its narrow Plane adapter.
- External agents and clients using Plane's supported Python MCP compatibility surface.

Plane is the product and control plane and the sole source of truth for Agent identity, permissions, product lifecycle, backend conversations, events, assignments, runs, memory/skills governance, schedules, delegation, outcomes, review, audit, and recovery. Hermes is a hidden, replaceable execution kernel behind a narrow versioned runtime adapter. Buzz is a donor/reference for useful conversation, ACP, inspectability, or isolation patterns only; it is not a Plane runtime dependency, product authority, or source of durable state.

Full Plane integration/action coverage is a completion requirement. Adaptive disclosure keeps the complete supported catalog discoverable while exposing only a small universal core plus role- and assignment-relevant eager schemas to the model. A discoverable operation is not an authorization grant.

## Accepted product model

There is one underlying Plane Agent system. Every configured Agent has exactly one role at a time. Roles are Plane-owned profile data, governance, skills, and presentation defaults over the shared lifecycle; they are not separate runtime classes, permission systems, or products.

Built-in roles are:

- `worker`: complete an assigned outcome.
- `delegator`: dynamically plan a case, automatically assign unclaimed work to humans or Agents, and record the rationale. Worker and ordinary specialist Agents do not freely delegate.
- `gardener`: maintain multiple Agents across sessions and apply private memory/skill improvements within each target Agent's wall.
- `chief_of_staff`: the automatically provisioned Agent for one human.
- `hr`: propose Agent creation, change, or retirement.
- `evaluator`: review every Agent outcome before human acceptance or return.

Workspace administrators may define custom roles, but each custom role remains exactly one role on the same Agent model and cannot bypass Plane authorization, delegated-assignment rules, private-memory walls, HR governance, evaluator review, or final human review.

Every human automatically receives exactly one chief-of-staff Agent. Its effective authority is exactly that human's current live Plane permissions and can never be broader. Provisioning is a product invariant, not a shortcut around membership, project roles, object permissions, or credential revocation.

The dedicated delegator plans each case dynamically, assigns unclaimed work to humans or Agents through normal assignment contracts, and records why each assignment was made. Specialist Agents execute their assignments and do not gain free delegation merely from receiving a skill or discovering an operation. There is no saved or versioned workflow-definition product, workflow-definition package, reusable workflow graph, or workflow DSL in scope.

Approved schedules create normal Plane assignments and runs through the ordinary lifecycle. A schedule is a trigger and control record, not a separate execution authority or workflow-definition system.

Gardeners may maintain multiple Agents across sessions, but strict Agent-private walls prevent copying knowledge, memory, or skills between Agents. Plane-governed storage is authoritative. Gardener improvements are automatically applicable only within the selected target Agent's private scope and are immutable, versioned, provenance-bearing, auditable, and rollback-capable. Rollback creates a new revision; it never rewrites history.

HR may propose Agent creation, change, or retirement. A workspace administrator must approve each proposal before Agent state changes. This is product governance, not a runtime confirmation prompt for an already-authorized operation.

An evaluator reviews every Agent outcome before a human accepts it or returns it for revision. Human acceptance or return is the final product decision. Evaluator feedback is evidence and guidance, not a substitute for the human decision.

Authorized Agent operations execute autonomously within the Agent's live Plane permissions. Unauthorized operations return a non-leaking denial and have no effect. There are no runtime human-confirmation prompts, approval brokers, decision tokens, pending approval records, or approval-resume paths for otherwise-authorized operations. Human approvals remain for product governance, release/rollout/deployment, destructive changes, incompatible public contracts, credentials, and other explicit safety gates.

After verification, staged rollout is allowed even though there are no current users. The absence of users does not waive canaries, observation windows, automated safety stops, rollback readiness, or post-rollout readback.

## Normative invariants

- AgentActor identity/authorization is the sole live entitlement source and is not versioned profile content.
- ProfileVersion is versioned behavioral configuration snapshotted/resolved for a run.
- Tool availability is supplied by installed and enabled Plane features or integrations and represented in the shared operation catalog.
- Tool disclosure/presentation determines which available schemas are eager versus progressively disclosed for the resolved profile and assignment.
- Availability and disclosure are not a second permission system; every operation remains subject to live Plane authorization.
- AssignmentContract is the durable commission, RunAttempt is the durable execution attempt, OutcomeSubmission is the submitted artifacts/evidence/result; they have independent lifecycles.
- a run may span RuntimeInvocations/restarts; RunSnapshot is immutable per run; InvocationEnvelope is per dispatch and carries new Plane-owned event refs/remaining cumulative budget.
- explicit publication only; ordinary model final text remains transcript evidence; semantic Plane mutations use the Operation Gateway and publication carries/correlates authoritative receipts.
- outcome_unknown is never blindly replayed.
- If a lease expires or the container dies before a terminal observation arrives, Plane/supervisor reconciles the authoritative cause and synthesizes exactly one visible failure, blocker, or cancellation product event for the terminal invocation.
- Plane owns durable run/conversation/history; Hermes operational sessions/checkpoints are projections/mechanisms only.

## Current baseline and evidence

The baseline below is observed at the reviewed pre-P0 reconciliation state and must be refreshed by the coordinator when a new repository baseline is intentionally selected. Abbreviated hashes are included for quick recognition; full hashes are the evidence values. The reviewed Plane baseline for this package is `dac96b0ff9a3adb6bfcc3fea235ab4a697ae5acd`.

| Repository or fact       | Current evidence                                                                                                                                                                                                                                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Plane                    | `/Users/nqh/Desktop/CODES/plane`, branch `codex/agent-tooling-architecture`; reviewed pre-P0 reconciliation baseline `dac96b0ff9a3adb6bfcc3fea235ab4a697ae5acd` (`dac96b0ff9`). Earlier `f2be7a...` and `eaeb220...` values are historical checkpoints, not current evidence.                                                                   |
| Hermes                   | `/Users/nqh/Desktop/CODES/hermes-agent`, branch `main`, commit `112f51a5543d490768931514d48a780ad964a868` (`112f51a55`).                                                                                                                                                                                                                        |
| Plane implementation     | Only the thin scaffold at `apps/api/plane/agent/`: root package, `lifecycle`, and `adapters` seams plus their local `AGENTS.md` instructions. There are no Agent models, migrations, routes, application services, runtime implementation, or verification implementation yet.                                                                  |
| Plane scaffold authority | `apps/api/plane/agent/AGENTS.md`, `apps/api/plane/agent/__init__.py`, `apps/api/plane/agent/lifecycle/AGENTS.md`, `apps/api/plane/agent/lifecycle/__init__.py`, `apps/api/plane/agent/adapters/AGENTS.md`, and `apps/api/plane/agent/adapters/__init__.py`. The scaffold is not a Django app and marker-only future packages must not be added. |
| Hermes runtime boundary  | `plane_runtime/` is installed and discoverable in Hermes; `python3 -c 'import plane_runtime; print(plane_runtime.__file__)'` resolves `/Users/nqh/Desktop/CODES/hermes-agent/plane_runtime/__init__.py`. It is a marker-only adapter package, not implementation.                                                                               |
| Hermes runtime authority | `/Users/nqh/Desktop/CODES/hermes-agent/plane_runtime/AGENTS.md` and `plane_runtime/README.md`; the logical `plane_runtime.execute` interface remains inside the separate runtime service.                                                                                                                                                       |
| External MCP source      | Plane's `external/plane-mcp-server` submodule, pinned at `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`, maintained as the `uxheavy/plane-mcp-server` fork.                                                                                                                                                                       |
| Python SDK source        | Plane's `external/plane-python-sdk` submodule, pinned at `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426`, tag `v0.2.20`, maintained as the `uxheavy/plane-python-sdk` fork.                                                                                                                                                                          |
| MCP inventory            | `docs/agent-tooling/inventories/plane-mcp-v0.2.11.json` and its 177-row disposition companion; inventory digest is `2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1`.                                                                                                                                                          |
| Implementation status    | Work beyond the Plane and Hermes scaffolds has not started. Documentation, contracts, fixtures, and verifiers are design/evidence inputs until the applicable implementation gate is recorded.                                                                                                                                                  |
| Exploratory mind         | `/private/tmp/plane-runner.pdf`, the Freeform `Plane-runner` board (`8208a432-a415-434c-9f06-5731a6185db4`), and top-down historical task `019fa696-357f-79d0-8dbb-bfe4fa722241` are exploratory context only. They do not override this goal, accepted ADRs, current source evidence, or controlling approval records.                         |

The baseline says what exists, not what is complete. Documentation, a scaffold, a generated plan, a fixture, a model response, or an imported package is never counted as implemented behavior without an executable verifier and authoritative readback.

## Normative resource catalog and authority

The coordinator uses the following order when sources disagree:

1. The accepted product model and explicit current steering in the task.
2. Accepted ADRs `0001` through `0010` and the accepted rows in `docs/agent-tooling/decision-register.md`.
3. The current canonical contracts and controlling approval records in `docs/agent-tooling/`, including `APPROVAL-MANIFEST.md` where its current authority applies. `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` are evidence inputs to that authority, not competing implementation-start gates.
4. Current Plane and Hermes source behavior, official OpenAPI output, pinned MCP/SDK sources, generated catalogs, fixtures, and immutable verifier evidence.
5. The generated coordination plan and overview, which must be regenerated from their source and cannot override the preceding authorities.
6. Exploratory boards, PDFs, historical tasks, donor repositories, and model suggestions.

### Repository authorities

- Plane: `/Users/nqh/Desktop/CODES/plane`. Plane application services, authentication, live authorization, object permissions, product state, and audit are authoritative for Plane behavior.
- Hermes: `/Users/nqh/Desktop/CODES/hermes-agent`. Hermes is the hidden execution-kernel source and adapter donor; its product vocabulary, sessions, files, profiles, and UI are not Plane product authority.
- Buzz: the Buzz repository/source named by the current architecture and implementation plan. It is a reference/code donor only and must not become a runtime dependency or durable-state authority.
- `/Users/nqh/Desktop/CODES/plane-mcp`: the local official MCP source checkout used for source inspection and compatibility evidence. The Plane delivery target remains the pinned `external/plane-mcp-server` `uxheavy` fork.
- Plane `external/plane-mcp-server`: official Python MCP adapter host and 177-tool compatibility surface; handlers migrate incrementally rather than being rewritten as 177 Plane modules.
- Plane `external/plane-python-sdk`: shared SDK transport seam at `BaseResource`; ordinary MCP handlers continue to use existing resources while the optional gateway transport is introduced.

### Canonical Plane Agent documents

The canonical documentation set includes these exact files and directories:

- `docs/agent-tooling/README.md`, `GOAL.md`, `WORKLOG.md`, `RESULT.md`.
- `docs/agent-tooling/product-requirements.md`, `architecture.md`, `delivery-plan.md`, and `decision-register.md`.
- `docs/agent-tooling/APPROVAL-MANIFEST.md`, `RELEASE-MANIFEST.md`, `VERIFICATION-MANIFEST.md`, and `REQUIREMENT-COVERAGE.md`.
- `docs/agent-tooling/NON-UI-IMPLEMENTATION-PLAN.json` and generated `NON-UI-IMPLEMENTATION-OVERVIEW.md`.
- `docs/agent-tooling/GATEWAY-WIRE.md`, `PILOT-CONTRACTS.md`, `INTERFACE-DESIGN.md`, and `RUNTIME-DESIGN.md`.
- `docs/agent-tooling/MCP-COMPATIBILITY.md`, `MCP-MAPPING-CONTRACT.md`, `SOURCE-INVENTORY.md`, and `ADR-SYNTHESIS.md`.
- `docs/agent-tooling/EVALUATION-SCENARIOS.md`, `EVALUATION-FIXTURE-CONTRACT.md`, and `SAFETY-EVALUATION-DESIGN.md`.
- `docs/agent-tooling/fixtures/planning-v1.json`, `planning-v1.schema.json`, `planning-v1.predicates.json`, and `planning-v1.predicates.schema.json`; later safety fixtures must follow `SAFETY-EVALUATION-DESIGN.md`.
- `docs/agent-tooling/verifiers/render-non-ui-implementation-plan.mjs` and `verifiers/validate-planning-fixtures.mjs`.
- `docs/agent-tooling/verifiers/verify-g0-preflight.mjs`.
- `docs/agent-tooling/ownership-map.json`, `integration-lock.schema.json`, `integration-lock.g0.json`, `g0-readiness.schema.json`, and `g0-readiness.json`.
- `docs/agent-tooling/inventories/plane-mcp-v0.2.11.json` and `inventories/plane-mcp-v0.2.11-dispositions.md`.
- `docs/decisions/0001-plane-agent-tooling-architecture.md` through `docs/decisions/0010-plane-runtime-contract.md`.

### Source, catalog, fixture, and evidence authorities

- The official Plane public interface is `/api/v1/`, with DRF Spectacular as the OpenAPI generator when enabled. At the baseline no generated OpenAPI document is checked in; the source-inventory facts and the generated artifact produced from the exact Plane commit must be captured before catalog qualification.
- The supported catalog is generated from the public OpenAPI surface and a curated overlay. The overlay owns agent descriptions, examples, aliases, safety and result policies, idempotency metadata, semantic compositions, and disclosure metadata. Private UI/session routes are not automatically catalog operations.
- `SOURCE-INVENTORY.md` records observed Plane, Hermes, MCP, SDK, authentication, transport, and current authorization facts. Current source behavior is rechecked whenever a contract or verifier depends on it.
- The 177-tool machine inventory and 177-row dispositions are the external compatibility baseline. Exact handler-branch and SDK method/path mapping in `MCP-MAPPING-CONTRACT.md` is required; a count, category, wildcard, or generic adapter label is not proof.
- Planning fixture inputs and predicates are `fixtures/planning-v1.*` and are validated by `verifiers/validate-planning-fixtures.mjs`. Safety trial inputs, probes, evidence, and independent predicates must be generated and digest-bound before safety qualification.
- `EVALUATION-SCENARIOS.md`, `EVALUATION-FIXTURE-CONTRACT.md`, `SAFETY-EVALUATION-DESIGN.md`, `REQUIREMENT-COVERAGE.md`, `VERIFICATION-MANIFEST.md`, `RESULT.md`, and the immutable evidence index define how behavior becomes qualifying evidence. Evidence must be independently acquired, content-addressed, and bound to the exact repository/build/configuration state.

## Integration gates (G0–G5)

The generated gate text in [NON-UI-IMPLEMENTATION-OVERVIEW.md — Integration gates](./NON-UI-IMPLEMENTATION-OVERVIEW.md#integration-gates) and the delivery dependencies in [delivery-plan.md — Workstreams and gates](./delivery-plan.md#workstreams-and-gates) are coordination definitions. They do not override accepted ADRs, the decision register, or the controlling approval manifest; naming `G0`–`G5` without satisfying the corresponding definition is not evidence of promotion.

### G0 — Implementation contract frozen

- ADR-0008, ADR-0009, and ADR-0010 are accepted before their implementation lanes, and `APPROVAL-MANIFEST.md` is explicitly approved before any runtime, application, or verification implementation starts.
- The logical `plane.agent-runtime/v1` contract, dispatch semantics, versioned runtime events, publication operation/receipt, catalog names, limits, retention, idempotency, and audit-failure policy are frozen for v1. The physical durable queue/RPC transport remains implementation-defined under ADR-0010; retired-name and stale UI-dependent language is reconciled with the non-UI boundary.
- Owners and repositories are assigned, and the cross-repository integration-lock format is agreed.

### G1 — Deterministic domain spine

- A fixture creates an Agent actor, profile version, assignment, run snapshot, invocation, and terminal outcome without a model or UI.
- The deterministic runtime adapter crosses the same dispatch and event-ingress contracts intended for Hermes.
- Pilot reads and one semantic mutation cross the gateway with live authorization, idempotency, bounded results, and append-only audit; shared contract fixtures pass in Plane and the runtime service.

### G2 — Real single-agent vertical slice

- A real forked-Hermes process completes the assigned planning outcome through native tools and progressive TypeScript composition.
- The runtime publishes exactly one visible terminal product event through Plane APIs; raw model text remains run-inspection evidence only.
- Authorized work succeeds, inaccessible project access is denied without leakage, stable replay creates no duplicate mutation, credentials remain host-only, and the slice is operable through API, CLI, and fixtures with no chat UI.

### G3 — Non-UI feature breadth complete

- Full Plane integration/action coverage, private memory/skills, schedules, dynamic delegation, artifacts, evaluator review, and outcome APIs satisfy their accepted contracts.
- HR proposes Agent creation/change/retirement with workspace-admin approval; every human has one chief-of-staff Agent restricted to that human's live permissions.
- Gardener application is automatic, versioned, and rollback-capable across sessions while strict per-Agent walls prevent knowledge copying; the approved external MCP inventory is migrated or explicitly dispositioned through the shared gateway.
- Minimal administration uses existing Plane settings primitives with no chat UI or parallel design system, and all supported behavior has contract, permission, failure, and compatibility tests.

### G4 — Production candidate verified

- The clean-checkout primary verifier passes static, contract, authorization, isolation, mutation, compatibility, load, recovery, and operator checks.
- The mandatory live pilot and retained evaluation suite meet approved thresholds with no provider/model fallback.
- Integration locks, artifacts, migrations, observability, runbooks, kill switches, credential lifecycle, retention, and rollback evidence are complete.

### G5 — Controlled rollout complete

- After verification, development, allowlisted-workspace, expanded-cohort, and approved general-availability stages have recorded evidence and approval even though there are no current users.
- Production canaries prove one permitted and one denied Plane scenario, audit correlation, version readback, and rollback readiness.
- No unresolved security-critical failure, duplicate mutation, missing audit event, credential disclosure, or sandbox escape remains; automated safety stops are mandatory at every stage.

## Durable phase plan

Each phase has one accountable integrator. Implementation may proceed in parallel only across disjoint ownership lanes and only after its dependency gate. A phase is complete only when its exit evidence is recorded and its verifier passes from the required clean state. A failure stops promotion of dependent phases but does not justify weakening the verifier.

| Phase | Outcome                                                                                                 | Dependencies                                   | Parallel lanes                                                              | Integrator and gate                                       |
| ----- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------- |
| P0    | Durable contracts and approval baseline are coherent, owned, and resumable.                             | Current ADRs, source inventory, product model. | Documentation, authority reconciliation, ownership mapping.                 | Root coordinator; G0.                                     |
| P1    | Generated contracts, catalog inputs, fixtures, and cross-repository integration lock are deterministic. | P0.                                            | Contract generation, fixture/oracle work, lock tooling.                     | Contract/release integrator; G1 entry.                    |
| P2    | Plane owns the Agent domain, lifecycle, and exactly-one-role governance.                                | P0; P1 schemas/fixtures.                       | Domain models/services and deterministic lifecycle tests.                   | Plane domain integrator; G1.                              |
| P3    | Operation Gateway, security, idempotency, audit, and full-catalog foundation are real and shared.       | P0; P1; Plane application-service facts.       | Gateway, authorization matrix, audit/evidence, catalog generation.          | Plane API integrator; G1/G3.                              |
| P4    | Separate runtime service and Hermes narrow adapter execute immutable snapshots and invocations.         | P0; P1; P2 lifecycle contract.                 | Runtime service, deterministic fake, Hermes adapter.                        | Runtime integrator; G2 entry.                             |
| P5    | Restricted TypeScript composition and adaptive tool discovery work through host callbacks.              | P1, P3, P4; deterministic runtime seam.        | Native adapters, Tool Search/disclosure, TypeScript isolate.                | Runtime security/tooling integrator; G2.                  |
| P6    | Private memory, skills, gardeners, and schedules are Plane-governed and recoverable.                    | P2; P3; P4; P5 context seam.                   | Memory/skill governance, gardener revisions, schedule triggers.             | Knowledge/automation integrator; G3.                      |
| P7    | Delegation, chief-of-staff, HR, and evaluator product behavior is complete.                             | P2; P3; P4; P6 where private context is used.  | Dynamic planning, auto-provisioning, HR proposals, evaluation review.       | Plane product-lifecycle integrator; G3.                   |
| P8    | Full Plane action coverage and MCP/SDK compatibility converge on the shared gateway.                    | P1, P3, P5; stable catalog and gateway.        | Full action adapters, MCP mapping, SDK transport, real-client tests.        | Integration/compatibility integrator; G3.                 |
| P9    | Reused settings administration, operations, observability, credentials, and runbooks are complete.      | P2–P8 contracts; P3 audit; P4 runtime.         | Settings/API/CLI, deployment, dashboards, credential drills, runbooks.      | Operations integrator; G4 entry.                          |
| P10   | Deterministic and live evaluation, security, load, recovery, and rollback proof passes.                 | P3–P9; pinned artifact lock.                   | Independent verifier, live trials, hostile probes, load/recovery, rollback. | Quality/release integrator with independent reviewer; G4. |
| P11   | Staged rollout, post-deploy readback, rollback readiness, and GA completion are evidenced.              | P10 and explicit rollout authority.            | Canaries, observation windows, production readback, rollback.               | Root coordinator and operations authority; G5.            |

### P0 — Durable contracts and approval baseline

Outcome: one internally consistent, durable source of truth exists for the accepted product model, repository ownership, current approval authority, runtime/no-UI boundary, full-action completion rule, and evidence contract. P0 records the current approval state from the authoritative record and does not copy superseded runtime-approval claims into the goal.

Work:

- Reconcile ADRs `0001`–`0010`, `decision-register.md`, `architecture.md`, `product-requirements.md`, `APPROVAL-MANIFEST.md`, and the generated plan/overview.
- Freeze ownership, repository/lane boundaries, review authority, change-control rules, runtime contract versions, catalog authority, and evidence authority.
- Confirm that runtime operations are autonomous within live Plane permissions and that HR approval, evaluator review, human acceptance, release approval, rollout promotion, and deployment approval are distinct product/delivery controls.
- Confirm the no-chat/composer/thread UI boundary and the reuse-existing-settings rule.
- Resolve only decisions that change the first contract; record any remaining open question with owner, impact, verifier, and decision deadline.

Verifier and gate: link/path validation, ADR/status consistency, source-digest comparison, ownership-overlap check, and a coordinator-approved G0 record. Stop if an accepted product boundary, role, authority, trust boundary, or safety rule contradicts another canonical source.

### P1 — Generated contracts, catalog, fixtures, and integration lock

Outcome: Plane and runtime-service lanes consume the same versioned generated contracts and golden fixtures. Catalog generation from OpenAPI plus the curated overlay is deterministic, searchable, and digest-bound. The lock names exact Plane, Hermes, MCP, SDK, catalog, adapter, runtime, fixture, and configuration revisions.

Work:

- Generate `RunSnapshot`, `InvocationEnvelope`, `RuntimeEvent`, `RuntimeExit`, Operation Gateway envelopes, errors, result/artifact descriptors, audit references, and lifecycle fixtures.
- Generate the complete supported operation/action catalog with adaptive-disclosure metadata. Keep global visibility complete and model context selective.
- Freeze planning and safety fixture schemas, independent predicates, negative controls, and evidence-index fields.
- Generate exact MCP handler-call and SDK method/path-to-operation mapping inputs; no 177-tool mapping may remain category-only.
- Make the integration lock fail on missing, changed, unpinned, or silently substituted revisions.

Verifier and gate: repeated generation byte/digest equality; strict schema and semantic fixture validators; route/mapping set joins; lock provenance check; intentional mutation checks for omitted catalog rows, changed schema, and changed digest. Stop if a downstream lane would need handwritten duplicate contract definitions.

### P2 — Plane domain, lifecycle, and roles

Outcome: Plane durably owns Agent actors, exactly-one-role profiles, assignments, runs, invocations, outcomes, evaluator review, human decision state, conversations, artifacts, and legal transitions as separate concepts with independent lifecycles.

Work:

- Implement Plane application services, persistence, serializers, APIs, and migrations using existing Plane conventions only after the approved contract gate.
- Keep actor authorization facts separate from behavioral profile versions and tool presentation. A run pins the resolved profile/context/tool/runtime snapshot.
- Implement assignment → run → outcome submission → evaluator review → human accept/return, including waiting, failed, blocked, cancelled, revision, recovery, and `outcome_unknown` states.
- Treat runtime observations as untrusted until Plane validates binding, schema, sequence, limits, receipts, and legal transitions.
- Keep backend conversations and product events authoritative in Plane; raw kernel final text is inspection evidence and is not an implicit product message.

Verifier and gate: domain invariants, migration tests, API contract tests, state-machine/property tests, forged/duplicate/out-of-order event tests, lease-death terminal-event synthesis, and deterministic fixture execution without model or UI. Stop if a session, transcript, checkpoint, or runtime process becomes the Plane record.

### P3 — Operation Gateway, security, idempotency, audit, and catalog foundation

Outcome: native Plane tools, TypeScript host callbacks, runtime lifecycle mutations, and migrated MCP calls share one typed Plane Operation Gateway around existing application services.

Work:

- Authenticate internal calls as the dedicated Plane Agent identity and preserve the authenticated human/integration principal for external MCP calls.
- Run live Plane authorization for every operation. Tool availability and disclosure never replace authorization.
- Validate typed inputs, structured errors, reference visibility, idempotency, concurrency, result budgets, version metadata, and append-only audit.
- Implement safe replay for known success, retry only for known pre-commit failure, explicit `outcome_unknown` for ambiguous non-idempotent mutation, and reconciliation without blind retry.
- Keep the gateway inside Plane's API service initially and use the accepted versioned JSON HTTP adapter; do not create a second business-logic implementation, internal MCP hop, or direct database path.
- Build the catalog/full-action foundation so P8 can expand breadth without 177 shallow prompt/runtime modules.

Verifier and gate: three-entry-path traces, complete role/object authorization matrix, credential revocation, non-leaking denial, idempotency/replay/race/fault tests, result/artifact bounds, audit intent/outcome completeness, audit-failure policy, and direct-database bypass inventory. Stop on any authorization bypass, credential exposure, missing audit record, duplicate committed mutation, or unsupported fallback.

### P4 — Separate runtime service, Hermes adapter, and snapshot/invocation protocol

Outcome: a separately deployed, co-located runtime service executes immutable Plane invocations through one narrow `plane_runtime.execute` adapter while Hermes remains hidden and replaceable.

Work:

- Implement cross-process dispatch, leases, cancellation, event ingress, checkpoints, durable continuation, and terminal-event synthesis against the deterministic fake first.
- Keep all Plane translation in `plane_runtime/`; do not import Hermes `AIAgent`, profile loaders, session databases, registry globals, cron, delegation, workflow state, or chat types into Plane API modules or unrelated Hermes core modules.
- Map Hermes progress, questions, usage, artifacts, transcripts, failures, exits, and tool observations into bounded versioned observations; Plane ingress remains authoritative.
- Scope containers and processes to invocations, not durable runs. Recreate infrastructure from Plane snapshots, input events, safe checkpoints, and remaining cumulative budget.

Verifier and gate: cross-process contract tests, snapshot immutability, accumulated-budget tests, restart/continuation tests, forged/duplicate/out-of-order event tests, real adapter tests, and one visible terminal Plane event per terminal invocation. Stop if an infrastructure restart resets budgets, bypasses receipts, or makes Hermes session state authoritative.

### P5 — Restricted TypeScript composition and adaptive tool discovery

Outcome: Plane Agents use a small universal Plane work core, assignment/profile-relevant eager tools, and progressively discoverable long-tail operations; model-written TypeScript can compose authorized calls only through a credential-free host callback.

Work:

- Build thin native adapters from generated contracts and reuse Hermes registry, Tool Search, middleware, tool-call IDs, concurrency, ordered result projection, and bounded-result mechanisms.
- Freeze final names/schemas/promotions through the catalog decision rather than importing old fixed tool-name proposals or the default Hermes product catalog.
- Implement the restricted child TypeScript isolate, verified parser/transpiler/engine boundary, generated client, host callback binding, cumulative budgets, result spill, bounded artifact reads, and clean replacement.
- Deny credentials, arbitrary network, direct Plane HTTP, DNS, filesystem, subprocess, package installation, module loading, persistence surfaces, sibling/cross-run callbacks, forged authority, and replayed frames.

Verifier and gate: catalog disclosure tests, generated-code credential/network/filesystem/process/package probes with liveness controls, host-bound callback tests, nested authorization/audit traces, output/call/CPU/memory/wall-time boundaries, artifact expiry/cleanup, and post-probe clean-isolate health. Stop on a policy bypass, vacuous probe, leaked secret, unbounded result, or silent model/provider fallback.

### P6 — Private memory, skills, gardeners, and schedules

Outcome: Plane governs typed private context, memory, skills, gardener revisions, and schedules; the kernel supplies only reusable execution/retrieval mechanisms behind adapters.

Work:

- Store target Agent, owner, source/provenance, visibility, version, lifecycle, retention, and authorization for every memory/skill entry and revision.
- Assemble context deterministically from authorized references and lossless runtime projections such as `MEMORY.md`, subject-bound `USER.md`, and skill packages; files are never the source of truth.
- Apply gardener improvements automatically within one target Agent's private wall, record immutable predecessor/rationale/revision history, and support rollback without rewriting history.
- Make approved schedules trigger ordinary assignments and runs with recovery, idempotency, limits, and audit through the same lifecycle.

Verifier and gate: scope/leakage matrix, cross-Agent negative controls, projection round-trip/provenance tests, gardener automatic-apply/version/rollback tests, retention tests, schedule trigger/recovery tests, and audit readback. Stop if any knowledge crosses Agent walls, if runtime files become authoritative, or if a schedule introduces a workflow-definition execution path.

### P7 — Dynamic delegation, chief-of-staff, HR, and evaluation

Outcome: the complete role governance and outcome-review product works through normal Plane assignments and backend events.

Work:

- Implement the dedicated delegator's case-specific dynamic plan, normal child assignment contracts, rationale, lineage, scope, budget, authorization, completion, cancellation, and failure semantics.
- Automatically provision exactly one chief-of-staff Agent per human and reconcile its authority to the human's current live permissions.
- Implement HR proposal lifecycle for Agent creation/change/retirement and workspace-admin approval, without turning it into runtime operation confirmation.
- Require evaluator review before every human accept/return decision and preserve the human as final decision-maker.
- Include backend conversation/publication/product-event receipts and run inspection APIs while leaving chat/composer/thread UI out of scope.

Verifier and gate: delegation-role authorization and non-delegator denial tests, rationale/lineage/replay tests, one-per-human provisioning tests, permission-revocation tests, HR approval tests, evaluator-before-human invariant tests, outcome revision tests, and backend event readbacks. Stop if specialist agents can freely delegate, if HR changes state without admin approval, or if an outcome bypasses evaluator review or human finality.

### P8 — Full Plane action and MCP/SDK compatibility convergence

Outcome: every supported Plane integration/action is represented in the global catalog and backed by a tested gateway path or an explicit approved compatibility disposition. The official Python MCP surface remains usable while converging incrementally on the same gateway.

Work:

- Complete full Plane action/integration coverage before declaring the program finished; adaptive disclosure controls context, not coverage.
- Use Plane application services and generated catalog metadata; add custom code only at unavoidable Plane-owned semantic, security, runtime, or compatibility seams.
- Route the pinned official MCP server through the optional SDK `BaseResource` gateway transport where applicable, preserve local PQL behavior where explicitly retained, and harden attachment/transfer paths against unsafe destinations.
- Prove exact one-to-one disposition and mapping for all 177 pinned tools, supported schemas/transitions, client/auth/transport modes, route branches, SDK method/path calls, and gateway traces.
- Preserve additive compatibility unless an explicit approved compatibility/deprecation decision says otherwise.

Verifier and gate: generated catalog diff, complete MCP inventory/disposition/mapping join, real stdio/OAuth/PAT/legacy-SSE client tests where supported, attachment SSRF tests, SDK route tests, schema transition tests, shadow comparison, rollback test, and no-unmapped-route negative control. Stop on an omitted action, generic mapping, public contract regression, direct gateway bypass, or unapproved deprecation.

### P9 — Reused settings, operations, observability, credentials, and runbooks

Outcome: administrators and operators can configure, inspect, limit, stop, recover, and roll back the system without chat UI or a new settings architecture.

Work:

- Complete API and CLI administration first; extend existing Plane settings UI only for the required Agent, role, credential, HR, gardener, schedule, evaluator, operation-presentation, limit, and kill-switch workflows.
- Package the runtime service with invocation-scoped leases, quotas, cancellation, cleanup, replacement, and deployment configuration.
- Add metrics, traces, alerts, audit lookup, redaction, retention, feature flags, mutation and Code Mode kill switches, credential issue/rotate/revoke drills, incident response, and operator runbooks.
- Define last-known-good artifact/configuration, migration, rollback, rollout, and readback procedures.

Verifier and gate: API/UI parity, settings reuse review, permission tests, operational smoke tests, alert and kill-switch exercises, credential lifecycle evidence, retention/readback checks, load/soak prerequisites, incident-runbook rehearsal, and rollback rehearsal. Stop on an operator control that changes authorization unexpectedly, exposes a secret, cannot kill the declared surface, or lacks a readback.

### P10 — Deterministic/live evaluation, security, load, recovery, and rollback

Outcome: the exact release artifact passes independent proof from clean checkouts and clean state, including real Plane+Hermes behavior and qualified negative controls.

Required proof:

- A version-controlled primary verifier fails non-zero for contract, lifecycle, gateway, authorization, sandbox, mutation safety, runtime, MCP, operations, load, recovery, provenance, or rollout-readiness failure.
- The mandatory live Hermes acceptance uses the real Plane server and gateway, a dedicated Plane Agent credential held host-side, provider `openai-codex`, exact model `gpt-5.6-luna`, no fallback, native tools, TypeScript composition, allowed and denied project readback, exactly one parent/three children/one source-linked comment, idempotent replay, correlated audit evidence, credential isolation, network isolation, and cleanup.
- The retained evaluation set contains at least 50 qualifying scenarios and at least 50 authenticated Hermes/Luna runs: ten materially different planning fixtures at three independent runs each plus 20 safety trials, with every attempt retained in the denominator.
- Complete live success is at least 90%; authorization bypasses, credential disclosures, sandbox escapes, duplicate committed mutations, and missing required audit records are zero-tolerance failures.
- Deterministic contract/security/compatibility checks pass at 100% with zero skips or xpasses; the complete deterministic suite passes twice from clean state; the exact release artifact passes three consecutive final verification runs.
- Security negative controls prove the verifier detects documentation, authorization, audit, mapping, provider/model-fallback, aggregation, and other declared mutations for the intended reason.
- Load, latency, interruption, outcome reconciliation, artifact expiry, credential revocation, kill-switch, clean-state rollback, and post-recovery proofs meet the approved numeric gates.

Verifier and gate: independent verifier principal and immutable evidence index. Every record binds the repository commit, worktree, integration-lock digest, catalog/adapter/runtime/configuration digests, command, environment, UTC timestamps, exit code, artifact hashes, negative controls, and reviewer. Stop on any missing, borrowed, unsigned, unbound, skipped, fallback, or model-claimed evidence.

### P11 — Staged rollout, post-deploy proof, and GA completion

Outcome: the verified release is promoted through controlled stages and production readback proves the enabled version, permitted path, denied path, audit correlation, and rollback readiness.

Stages are development/internal, one allowlisted workspace, expanded approved workspaces, and general availability. Each stage has a declared artifact/configuration, cohort, observation window, thresholds, approver, immutable evidence, last-known-good target, and rollback trigger. Because there are no current users, staged rollout may proceed after P10; that fact does not permit skipping safety stops.

Verifier and gate: real permitted and denied canaries, audit readback, version/configuration readback, alert/kill-switch exercise, observation-window metrics, post-deploy smoke checks, rollback rehearsal, and explicit stage authority. Immediate rollback is mandatory for auth bypass, credential exposure, isolation escape, duplicate mutation, missing audit, unsafe `outcome_unknown` handling, or any other declared security-critical violation. Stop if any stage lacks evidence, approval, readback, or a tested last-known-good path.

## Skill-routing catalog

This is a routing inventory, not a promise that every named skill or linked workflow will be invoked. A worker loads the complete `SKILL.md` for every selected skill before acting, resolves any referenced instructions itself, and follows the user's direct instruction when it conflicts with a generic routing suggestion. The coordinator chooses the smallest set that covers the lane; a skill is not silently carried across phases.

| Phase or use                                      | Skills and when they are loaded                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0 goal/authority grounding                       | `ultragoal` when reading, revising, resuming, or validating this durable goal; `documentation-and-adrs` when reconciling durable product/technical decisions and canonical docs; the already-applied `architect` and `codebase-design` grounding resources for system ownership and repository/module seams; `agents-md` before entering a repository or nested path with local instructions; `interrogate` when a factual ambiguity could change scope, authority, or a verifier.                                                                                                                                                                                                                                                    |
| P0 principles and subtraction                     | `principle-outcome-oriented-execution` at each phase/gate to keep work tied to observable outcomes; `principle-boundary-discipline` when defining Plane/Hermes/Buzz/MCP ownership; `principle-build-the-lever` when deciding whether a generator, contract, or mechanism should replace repeated manual work; `principle-subtract-before-you-add` before introducing a package, protocol, tool, or UI surface; `principle-encode-lessons-in-structure` after a correction, failure, or repeated gotcha; `principle-never-block-on-the-human` when safe evidence gathering or a bounded alternative can proceed without a preference decision; `principle-model-the-domain` when product concepts or state ownership are being shaped. |
| P1 contracts and schemas                          | `context-engineering` when preparing bounded worker context and evidence packets; `domain-modeling` for lifecycle/state/invariant modeling; `api-and-interface-design` for the Gateway, runtime, catalog, and cross-process seams; `typed-service-contracts` for generated schemas, versions, structured errors, receipts, and event envelopes; `tool-design` when choosing native/adaptive/composition tool contracts; `principle-make-operations-idempotent` for invocation keys, replay, reconciliation, and retry semantics.                                                                                                                                                                                                      |
| P2–P4 domain, gateway, runtime                    | `domain-modeling` when ownership or durable state changes; the already-applied `architect` and `codebase-design` grounding resources remain references, not future workflow invocations; `api-and-interface-design` and `typed-service-contracts` for public/cross-process contracts; `build-audit-logs` for append-only intent/outcome evidence; `implementing-security-layers` for identity, authorization, host binding, isolation, and trust boundaries; `principle-boundary-discipline` and `principle-make-operations-idempotent` for gateway/runtime seams; `principle-prove-it-works` and `principle-sequence-verifiable-units` when a verifiable vertical slice or gate is assembled.                                        |
| P5–P8 tools, knowledge, delegation, compatibility | `tool-design` for adaptive disclosure, native adapters, composition, and MCP ergonomics; `context-engineering` for private context and bounded model-visible results; `domain-modeling` for memory/skills/gardener/schedule/delegation/evaluator records; `api-and-interface-design` and `typed-service-contracts` for catalog, SDK, MCP, and event evolution; `build-audit-logs` and `implementing-security-layers` for traceability and isolation; `principle-subtract-before-you-add`, `principle-boundary-discipline`, and `principle-encode-lessons-in-structure` for reuse and systemic fixes.                                                                                                                                  |
| P9–P11 verification and delivery                  | `expert-testing` when designing broad, adversarial, integration, and load coverage; `test-systematically` when executing deterministic/live matrices, retries, recovery, and clean-state passes; `principle-prove-it-works` for independent observable proof; `principle-sequence-verifiable-units` for phase/gate ordering; `git-workflow-and-versioning` for branch/commit/integration-lock provenance and clean worktrees; `build-audit-logs` for evidence indexes and reviewer traceability; `implementing-security-layers` for rollout safety and stop triggers; `interrogate` when evidence conflicts or a gate decision needs a bounded fact-finding pass.                                                                     |

The exact named routing catalog is: `ultragoal`, `documentation-and-adrs`, `architect`, `codebase-design`, `agents-md`, `principle-build-the-lever`, `principle-outcome-oriented-execution`, `principle-boundary-discipline`, `principle-encode-lessons-in-structure`, `principle-make-operations-idempotent`, `principle-model-the-domain`, `principle-never-block-on-the-human`, `principle-prove-it-works`, `principle-sequence-verifiable-units`, `principle-subtract-before-you-add`, `context-engineering`, `domain-modeling`, `api-and-interface-design`, `typed-service-contracts`, `tool-design`, `build-audit-logs`, `implementing-security-layers`, `expert-testing`, `test-systematically`, `git-workflow-and-versioning`, and `interrogate`.

The named `architect` and `codebase-design` resources are retained because their grounding, vocabulary, and approved design comparisons already shaped the architecture recorded in [ADR-SYNTHESIS.md — Architect arena](./ADR-SYNTHESIS.md#architect-arena) and [INTERFACE-DESIGN.md — Accepted v1 core boundary](./INTERFACE-DESIGN.md#accepted-v1-core-boundary). Their linked workflows can require arena/subagent execution: `architect` Phase B uses arena runners, and `codebase-design` links `DESIGN-IT-TWICE.md`, which mandates sub-agents. Skill instructions that mandate subagents are incompatible with this goal's task-only execution contract and must not be invoked during autonomous delivery. Future design changes route only through a threads-compatible process; equivalent independent proposals and reviews use separate user-visible Codex tasks/threads, never subagents. This catalog does not claim that those incompatible workflows will be invoked.

## Delegation operating contract

The root thread is the delegator/coordinator, not a feature implementer. It owns product scope, source authority, task decomposition, integration, conflict resolution, integration-lock updates, gate decisions, and final proof.

- Implementation and work threads use GPT-5.6 Luna xhigh.
- Review threads use GPT-5.6 Sol Medium, following the latest user override.
- Every delegated unit is a separate user-visible Codex task/thread; no delegated unit is a subagent.
- Every task packet contains: objective, repository/lane ownership, non-goals, dependencies, exact files or surfaces, skill-routing requirements, verifier command/oracle, stop condition, expected evidence, and commit SHA requirement.
- One writer owns each repository/lane at a time. No two threads edit overlapping files or integration-lock entries. Documentation-only changes do not grant permission to edit code, ADRs, plans, or external repositories outside the packet.
- The coordinator waits patiently without rushing; workers and reviewers may take as long as their task needs. Do not interrupt or reassign solely because a task/thread has been running for a long time.
- Integrate only reviewed commits whose evidence and ownership boundary are clear. The root coordinator performs integration and conflict resolution; it does not silently take an unreviewed patch.
- If Sol Medium finds an issue, route a fresh bounded Luna remediation task to the issue, then a fresh independent Sol Medium review task is mandatory for the resulting commit. Do not ask the original review task to self-approve a changed implementation.
- Archive tasks only after their outputs are incorporated and no follow-up is needed. Preserve each task's objective, verdict, commit, and verifier evidence in the worklog or evidence index before archive.
- Local commits are progress checkpoints. A commit is not proof until the relevant verifier and clean-state status are recorded.
- The root owns final integration, conflict resolution, lock/digest updates, gate decisions, production proof, result assembly, cleanup, and final repository-status checks.

## Reuse and subtraction rules

1. Inspect and reuse existing Plane application services, identity, permissions, settings, API/CLI, pagination, serializers, activities, assets, feature flags, deployment, tests, and monitoring before adding a Plane seam.
2. Reuse Hermes registry, Tool Search, middleware, tool-call IDs, concurrency, ordered results, session/checkpoint mechanisms, memory/skill/schedule execution, and bounded-result/artifact mechanisms where their boundaries fit. Adapt behind `plane_runtime`; do not expose Hermes as the product.
3. Use Buzz only as a reference/code donor. Never add a Buzz runtime dependency or make Buzz state authoritative.
4. Reuse the official MCP server, its FastMCP host, its existing handlers, the official SDK resources, and the `BaseResource` transport seam. Add mapping/gateway code only where necessary.
5. Custom production code is allowed only at an unavoidable Plane-owned domain seam, cross-process contract, security boundary, catalog/adapter seam, or missing compatibility adapter. Every new seam records the inspected donor, rejected reuse, narrow need, and verifier.
6. Do not create a duplicate permission model, chat/composer/thread UI, general workflow-definition DSL, second workflow engine, broad Hermes product vocabulary, internal MCP hop, direct database path, or 177 shallow prompt/runtime modules.
7. Remove marker-only scaffold packages that do not yet own behavior; retain only the current root, lifecycle, and adapters seams until a child package has real behavior, tests, and ownership.
8. Subtract before adding: delete obsolete compatibility layers after callers migrate and the verifier proves they are unnecessary. Do not preserve an intermediate seam as permanent architecture merely because it is convenient.

## Goal loop and durable state

On every resume or continuation:

1. Read this `GOAL.md`, the latest appended `WORKLOG.md` entry, applicable `AGENTS.md` files, repository statuses, current integration lock, and the next unsatisfied phase gate.
2. Refresh volatile facts from the exact local repositories and canonical source documents. Treat missing evidence as unknown, not as success.
3. Select one smallest meaningful phase increment and dispatch only disjoint bounded lanes.
4. Require the worker to run the strongest relevant verifier, record failures and negative controls, and commit one logical checkpoint.
5. Send the commit and evidence to the independent reviewer when the lane is reviewable.
6. Integrate only the reviewed commit, resolve conflicts at the root, regenerate affected artifacts, and rerun affected plus regression checks.
7. Append exact commands, environment, worktree/commit, exit codes, artifacts, reviewer, decision, failure, and next action to `WORKLOG.md`.
8. Continue while a safe, relevant, authorized next action exists. Wait for delegated threads when work is in flight; do not create overlapping writers.

Durable state rules:

- `GOAL.md` holds the outcome, accepted model, baseline, authority, phases, routing, delegation, gates, and completion proof.
- `WORKLOG.md` is append-only. Preserve failures, superseded decisions, exact evidence, and next actions; never rewrite history to make a pass look cleaner.
- `RESULT.md` is the final evidence packet and must be completed before the goal can be declared complete.
- Integration locks, generated catalogs, fixtures, manifests, evidence indexes, and result artifacts are content-addressed where their canonical docs require it. Any bound-input change invalidates dependent evidence and triggers the declared rerun.
- Worktree cleanliness is verified before and after each root integration. Incidental artifacts are removed only when they are known to be generated by this task and safe to remove; unrelated user work is preserved.

## Anti-cheating, approval, and safety gates

No worker or coordinator may:

- weaken, skip, delete, narrow, or rewrite a verifier to obtain a pass;
- replace real Plane authorization, sandbox, gateway, MCP, or end-to-end behavior with mocks for final proof;
- claim implementation from docs, scaffolds, generated fixtures, imports, model prose, screenshots alone, or a happy-path trace;
- hide failures, skips, xpasses, retries, provider/model fallbacks, setup failures, or extra live attempts;
- silently shrink full Plane action/integration coverage, omit an MCP tool, accept a generic mapping, or deprecate a compatibility path without the explicit authority required by the current manifest/ADR;
- copy credentials into Plane, generated code, prompts, fixtures, logs, evidence, or result artifacts; or repurpose a credential outside its approved host-held scope;
- retry `outcome_unknown` blindly, infer success from a lost response, or perform dependent mutation before reconciliation;
- let model-supplied actor, workspace, tenant, run, budget, catalog, audit, or correlation fields become authoritative;
- use an exploratory board/PDF, historical task, or donor implementation as normative authority;
- lower numeric targets or change product boundaries without a recorded decision and the required approval.

Approval and safety gates:

- The current canonical approval record and G0 determine when runtime, application, or verification implementation may begin. `APPROVAL-MANIFEST.md` is the controlling implementation-start authority where the current docs assign it that role; `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` are evidence inputs, not competing gates. Do not infer approval from a prose status line, a branch name, or a worker claim.
- Runtime Plane operations are autonomous within live Plane authorization. HR/admin proposal approval, evaluator review, human outcome acceptance, release approval, rollout promotion, deployment, destructive data changes, credential rotation/revocation, incompatible public contracts, paid services, and security exceptions remain explicit product/delivery gates and are not runtime confirmation prompts.
- Staged rollout may proceed after P10 verification despite no users, but every stage requires the declared authority, observation, canary, safety stop, readback, and rollback evidence.
- Automatically stop and trigger rollback review on authorization bypass, credential disclosure, isolation/network escape, duplicate committed mutation, missing required audit, unsafe replay/reconciliation, unbound event, model/provider fallback, or evidence-integrity failure.
- Destructive data changes, purchases, shared-environment writes, credential repurposing, public incompatible changes, deployment, push/merge, and external system mutations require explicit approval before the action.

## Blocker standard

Difficulty, uncertainty, a long-running worker, a failing test, missing convenience, or a useful unanswered investigation is not by itself a blocker. The coordinator must record the failure and take the smallest safe next action: inspect the source, narrow the task without changing scope, add a fixture/negative control, route a fix thread, wait, or escalate the exact decision.

A true blocker requires the same external condition to prevent meaningful progress for the required repeated goal turns, no authorized alternative, and a recorded packet containing the exact condition, evidence, affected phase, preserved partial work, and smallest user or external action that would unblock it. Never label a task blocked merely to stop waiting.

## Evidence contract

Every qualifying claim binds all of the following:

- exact repository, branch/worktree, commit SHA, and clean-status result;
- integration-lock version/digest and all relevant Plane, Hermes, MCP, SDK, catalog, adapter, runtime, fixture, prompt, model metadata, configuration, isolate, container, and execution-limit digests;
- command, arguments, environment prerequisites, UTC start/end, exit code, and raw-log/artifact hashes;
- authoritative before/after Plane state, gateway envelopes, audit intent/outcome, runtime/event traces, object IDs, cleanup, and negative-control results;
- producer identity and independent acquisition/binding evidence where required;
- worker commit, Sol Medium review verdict, root integration commit, and any approved exception with reason, risk, compensating control, expiry, approver, timestamp, and immutable evidence reference.

Evidence from another repository state, run, trial, nonce, actor, workspace, channel, or producer role does not qualify even when its content hash matches. Model output is never the oracle for Plane state, authorization, isolation, mutation count, audit completeness, or evaluator/human review transitions.

## Completion proof

The goal is complete only when all of these are true:

1. P0–P11 exit gates pass and their evidence is incorporated into `RESULT.md` and the append-only `WORKLOG.md`.
2. Plane, Hermes, the official MCP fork, and the Plane Python SDK resolve to the final integration lock from clean checkouts; all involved repository statuses are clean.
3. The version-controlled primary verifier, callable from clean checkouts (the current design proposes `./scripts/agent-tooling/verify-release --integration-lock <approved-lock> --evidence <immutable-evidence-index>`), passes non-zero on any required contract, lifecycle, gateway, authorization, isolation, mutation, runtime, compatibility, operations, load, recovery, provenance, or rollout failure.
4. The mandatory live Plane+Hermes acceptance passes on the real Plane gateway with host-held Agent credentials, `openai-codex`, exact `gpt-5.6-luna`, native tools, TypeScript composition, allowed/denied readback, exact planning artifacts, idempotent replay, audit correlation, credential/network isolation, and cleanup. No fallback run counts.
5. Full Plane action/integration coverage is evidenced through the generated catalog, typed gateway paths, adaptive discovery, and complete 177-tool MCP/SDK mapping and compatibility evidence. No operation is omitted merely because it is not eager.
6. Backend conversations, product events, assignments, runs, artifacts, outcomes, evaluator review, human final decision, private memory/skills, schedules, delegation, chief-of-staff, HR governance, and reused settings/API/CLI operations satisfy their accepted contracts. Chat/composer/thread UI remains excluded.
7. Deterministic tests pass at 100% with zero skips/xpasses, the full deterministic suite passes twice from clean state, and the exact final artifact passes three consecutive final verification runs. Live evaluation retains at least 50 qualifying authenticated Hermes/Luna attempts, at least 90% complete success, and zero security-critical violations.
8. Security, load/soak, latency, interruption, `outcome_unknown` reconciliation, artifact expiry/cleanup, credential rotation/revocation, kill-switch, recovery, migration, and rollback evidence meets the approved numeric gates.
9. Staged rollout has recorded development, allowlisted, expanded, and GA evidence, explicit authority, safety stops, post-deploy enabled/permitted/denied/audit readbacks, and last-known-good rollback proof.
10. `RESULT.md` contains final SHAs/statuses, verifier command/output, focused checks, catalog/MCP evidence, security findings/disposition, load/reliability/evaluation metrics, migration/rollback, rollout/deployment/readback, redacted audit evidence, residual risks/acceptance, manifest version, independent reviewer, and immutable log references.
11. All spawned implementation/review threads are archived after evidence incorporation and no follow-up remains; no incidental artifacts remain; `git status --short` is empty in every repository in scope.

Only after this proof exists may the root coordinator report completion. A local commit, green documentation check, generated plan, or successful scaffold import is a progress checkpoint, not completion.

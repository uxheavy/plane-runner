# Worklog

This file records durable progress for the Plane Agent Tooling goal. Append entries chronologically. Preserve failed attempts and exact evidence.

## Current state

| Field                      | Value                                                                |
| -------------------------- | -------------------------------------------------------------------- |
| Phase                      | Program definition                                                   |
| Active gate                | Explicit approval of `APPROVAL-MANIFEST.md` (single implementation gate) |
| Plane branch               | `codex/agent-tooling-architecture`                                   |
| Hermes branch              | Not created from baseline `5e88745f125c0d332c1d16ea0363860d447657f5` |
| Last verified Plane commit | `c5f4537686` (current integrated base at reconciliation)             |
| Next action                | Obtain explicit `APPROVAL-MANIFEST.md` approval, then enter G0; release and verification manifests remain evidence inputs |

## 2026-07-29 — Goal grounding

### Evidence

- Plane architecture baseline exists under `docs/agent-tooling/`.
- ADR-0001 is accepted.
- Plane worktree was clean before goal artifacts were added.
- No prior `GOAL.md`, `WORKLOG.md`, or `RESULT.md` existed in the inspected Plane tree.
- Implementation status remains not started.

### Decisions carried forward

- Internal Plane agents use native Hermes tools plus TypeScript Code Mode.
- External agents retain the Python MCP compatibility interface.
- Every path converges on the Plane Operation Gateway.
- Dedicated agents use one revocable Plane credential held host-side.
- Plane authorization and approval run on every operation.
- Existing Hermes concurrency and approval behavior is reused.
- Pending approval does not survive runtime restart.

### Next action

Resolve the eager native tools and supported operation boundary required by the broader project-planning pilot.

## 2026-07-29 — Live acceptance scope

### Decision

- The user selected a broader project-planning workflow rather than simple CRUD or the narrower triage proposal.
- Goal completion requires a real Hermes process against the authenticated Plane development server.
- The final live proof cannot use a mocked Plane Operation Gateway.

### Required proof

- Analyze a seeded allowed project's release readiness.
- Create one parent plan and three coordinated child work items after approval.
- Add one source-linked planning comment.
- Prove retry idempotency.
- Verify created state and correlated audit evidence.
- Prove structured denial against an inaccessible control project.
- Probe generated-TypeScript credential and network isolation.

## 2026-07-29 — Model and evaluation requirements

### Observed evidence

- Local ChatGPT subscription authentication exists at `~/.codex/auth.json`.
- Hermes source supports subscription-backed provider `openai-codex`.
- The local Codex model registry advertises canonical model ID `gpt-5.6-luna`.
- No credential contents were read or copied into program artifacts.

### Requirements

- All counted live acceptance and evaluation runs use `openai-codex` and `gpt-5.6-luna`.
- Silent provider or model fallback fails verification.
- Evaluation includes at least 50 version-controlled scenarios.
- Evaluation includes at least 50 authenticated live Hermes runs.
- The complete deterministic suite passes twice from clean state.
- Computer Use provides user-visible Plane and Hermes readback evidence.

## 2026-07-29 — Independent goal red-team

### Corrections adopted

- Added immutable release and verification manifests with explicit change control.
- Added verifier negative controls and independent clean-checkout execution.
- Strengthened live proof with frozen prompts, separate approver and verifier principals, pre-write readback, unique tags, canary secrets, controlled egress probes, and cleanup.
- Increased evaluation to 50 retained live Luna runs across ten project variants and adversarial scenarios.
- Required at least 90% workflow success and zero security, duplicate-mutation, or audit violations.
- Added cross-repository provenance, operator lifecycle, audit-failure, confused-deputy, full MCP inventory, GA, and rollout-promotion gates.

## 2026-07-29 — Source and interface inventory

### Evidence

- Pinned the official Python MCP compatibility surface at commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`.
- Captured 177 unique MCP tools in a machine-readable, checksummed inventory.
- Traced the public Plane operations and current authorization behavior required by the project-planning workflow.
- Traced Hermes eager registration, deferred dispatch, middleware, approval, and current Python Code Mode seams.
- Compared four independent gateway interfaces: one deep operation seam, a named semantic facade, a durable state machine, and a catalog/batch/plan facade.

### Proposed decision

- Use request-bound `execute` as the core gateway interface.
- Keep catalog `search` and `describe` as a separate read-only interface.
- Keep approval, idempotency, reconciliation, and audit lifecycle as an internal state machine.
- Expose five eager domain tools plus `plane_docs`, `plane_search`, and `plane_execute` in Hermes.
- Do not expose a general graph-planning DSL in v1.

### Next action

Obtain user approval of the proposed interface boundary before freezing the corresponding manifest rows.

## 2026-07-29 — Compatibility and verifier design

### Proposed external MCP disposition

- Route 171 ordinary pinned MCP tools through gateway-backed compatibility adapters.
- Retain `get_pql_reference` as versioned local read-only behavior.
- Route five attachment tools through a hardened attachment adapter with explicit SSRF, transfer, redaction, and cleanup policy.
- Deprecate or omit none of the 177 pinned v0.2.11 tools.

### Verifier strengthening

- Added verifier ownership and independence requirements.
- Mapped every goal area to required verification checks.
- Defined the immutable 50-trial evaluation ledger.
- Defined expected-failure semantics for all four negative controls.
- Defined the clean-checkout verifier execution contract and proposed final command.

### Next action

Independently review the proposed compatibility and verification documents, then resolve the remaining numeric and runtime manifest rows.

## 2026-07-29 — Independent pre-freeze review

### Verdict

Reject manifest freeze at Plane commit `805f12ddbf`.

### Confirmed evidence

- The 177-tool inventory count and digest are correct.
- The 171 + 1 + 5 compatibility partition is syntactically complete.
- The proposed hybrid gateway is a reasonable conceptual seam.

### Freeze blockers to close

- Replace category-only MCP disposition with a 177-row behavioral and gateway mapping.
- Capture runtime `tools/list` schemas and behavioral fixtures rather than treating AST signatures as the compatibility oracle.
- Freeze 50 distinct scenario specifications and correct scenario/trial arithmetic.
- Expand verifier coverage from goal areas to every normative requirement and release row.
- Define the gateway wire transport, authenticated binding, version negotiation, approval transition, and retry protocol.
- Define pilot schemas, errors, authorization, approval, idempotency, result, and semantic-composition contracts.
- Define approval classes, approver authorization, group preflight, freshness, dependency substitution, partial failure, and external MCP behavior.
- Add negative controls for approval, isolate, callback identity, duplicate mutation, result limits, MCP omission, provenance, and rollback.
- Define evidence storage, signing, trust, retention, and replacement rules.
- Resolve immutable-model limitations, evaluator authentication, exact client versions, rollout cohorts, and durable authorities.
- Resolve the full 177-tool release commitment versus narrow vertical-slice sequencing.

### Progress after reviewed commit

- Proposed explicit Deno supervisor/Worker isolate architecture at commit `1bdb3b4a14`.
- Proposed exact execution, result, retention, performance, recovery, and observation thresholds for later approval.

### Next action

Obtain the immediate gateway-interface decision, then close the remaining technical pre-freeze blockers before requesting whole-manifest approval.

## 2026-07-29 — Core gateway interface accepted

### Decision

- The user accepted the deep-hybrid core gateway boundary.
- The gateway exposes one request-bound operation-execution seam.
- Read-only catalog discovery remains a separate interface.
- Approval, idempotency, reconciliation, result control, and audit lifecycle remain internal.
- Friendly native Hermes tools remain thin adapters rather than a second enforcement implementation.

### North Star

Use the least custom code that satisfies the approved production and security gates. Prefer reuse and generation over additional interfaces or protocols.

### Still open

- Exact eager tools and supported operation boundary.
- Explicit preflight groups and omission or inclusion of a graph DSL.
- Wire transport and external approval behavior.
- All remaining independent-review blockers before manifest freeze.

## 2026-07-29 — MCP reuse and release-plan write accepted

### Official MCP boundary

- Reuse Plane's official Python MCP server as the external adapter host.
- Preserve its deployed transports and 177-tool compatibility surface.
- Migrate existing handlers incrementally to the gateway rather than recreating the server.
- Keep internal Hermes on native tools and TypeScript Code Mode without an MCP hop.

### Release-plan write boundary

- Represent the parent, three children, and source comment as one curated `plane.release_plans.create@1` semantic operation.
- Validate, authorize, approve, claim idempotency, execute, reconcile, and audit the complete business action in the gateway.
- Do not add a general workflow-graph DSL in v1.

### Rationale

These choices reuse existing code and avoid both a duplicate MCP implementation and a generic workflow engine.

### Next action

Freeze the exact semantic operation contract and the gateway wire adapter.

## 2026-07-29 — Official MCP gateway seam and forks

### Decision

- Add one optional gateway transport at the official Plane Python SDK `BaseResource` seam.
- Keep existing official MCP handlers and their tool-level contracts in place.
- Select gateway mode in the MCP client factory.
- Preserve explicit local PQL and specialized attachment exceptions.

### External repositories

- Forked `makeplane/plane-mcp-server` to `uxheavy/plane-mcp-server`.
- Created `uxheavy/plane-mcp-server` branch `codex/agent-tooling-v1` at `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`.
- Forked `makeplane/plane-python-sdk` to `uxheavy/plane-python-sdk`.
- Created `uxheavy/plane-python-sdk` branch `codex/agent-tooling-v1` at `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426`.
- Added both forks as pinned submodules under `external/` at Plane commit `f4d2dd3119`.

### Evidence

- The pinned official MCP server centralizes `PlaneClient` creation in `get_plane_client_context()`.
- Plane Python SDK v0.2.20 routes every ordinary resource request through `BaseResource`.
- `BaseResource` owns the shared HTTP session, URL, authentication, retry, and response-normalization seam.

### Consequence

The release integration lock and clean-checkout verifier cover four repositories: Plane, Hermes, the official MCP server, and the Plane Python SDK.

### Next action

Specify the versioned gateway wire contract used by native Hermes, Code Mode callbacks, and the SDK transport.

## 2026-07-29 — Gateway wire transport accepted

### Decision

- Use one versioned JSON HTTP adapter inside Plane's existing `/api/v1` service.
- Reuse current Plane API-key and OAuth authentication.
- Keep identity, authorization, approval, idempotency, result control, and audit inside the deep gateway module.
- Do not add an internal MCP hop, gRPC service, broker, or separate gateway deployment.

### Proposed wire contract

- Bounded authenticated catalog search and description endpoints.
- One workspace-bound operation-execution endpoint.
- Operation major version and catalog digest on every call.
- Host-derived mutation `Idempotency-Key`.
- Structured `succeeded`, `approval_required`, `rejected`, `failed`, and `outcome_unknown` states.
- Optional shared Python SDK transport over the same endpoint.

### Still open

The wire reserves `approval_required`, but the approver authority, decision transport, expiry, and exact resume protocol require a separate decision before manifest freeze.

### Next action

Specify the pilot semantic operation schemas and approval protocol.

## 2026-07-29 — Pilot operation contracts proposed

### Contract boundary

- Defined nine callable pilot operations plus host-bound workspace context.
- Replaced raw serializer passthrough with narrow canonical project, cycle, work-item, comment, and page projections.
- Reserved credentials, actor identity, workspace identity, idempotency, approval, and audit fields for trusted host context.
- Required non-leaking reference resolution and independent authorization of related objects.
- Added cycle removal to the observed public-operation mapping for work-item placement updates.

### Source-driven differences

- Project-name resolution is excluded because project names are not unique.
- Current-cycle results remain plural because Plane can return zero or multiple current cycles.
- Agent comment writes use the same member-or-admin role as work-item writes, closing the weaker public comment-permission mismatch.
- Gateway idempotency replaces public external-ID check-then-create behavior as the concurrency guarantee.
- The release-plan operation requires one transaction and commit-safe activity delivery to guarantee exact counts and replay.

### Verification

- A fresh independent source review confirmed the serializer constraints, permission mappings, cycle-placement behavior, comment sanitization gap, and release-plan atomicity requirements.
- The repository formatter initially rejected both changed documents; they were formatted before commit verification.

### Still open

The contracts remain proposed until approval authority, effect labels, generated schema digest, executable fixtures, and manifest approval are resolved.

### Next action

Resolve the approval decision authority and resume protocol, one product decision at a time.

## 2026-07-29 — Hermes approval broker accepted

### Decision

- Hermes remains the live approval UX.
- A separate trusted broker credential submits the human decision to Plane.
- The agent execution credential cannot approve its own operation.
- Generated TypeScript receives neither credential.
- Plane binds the decision to the exact attempt and input digest, rechecks authority, and consumes approval once.

### Reuse boundary

Hermes's existing queue, prompt routing, blocking wait, timeout, and same-turn continuation are reused. Plane operations add a typed approval entry and exclude Hermes's session and permanent dangerous-command allowances.

### Still open

- Exact human approver eligibility.
- Default approval-effect policy and administrator overrides.
- Broker credential issuance, storage, rotation, revocation, and connector binding.

### Next action

Choose the exact Plane human eligibility rule for approving one pending operation.

## 2026-07-29 — Autonomous default clarified

### Correction

- Plane agents do not ask for permission by default.
- The dedicated agent identity and its configured Plane scope decide whether an operation is allowed.
- Authorized operations execute immediately.
- Unauthorized operations return a non-leaking denial.
- Administrators may optionally configure selected semantic effects to require a human prompt.

### Consequence

The Hermes broker protocol remains an optional policy path rather than the normal mutation path. The mandatory broad planning run proves autonomous execution; separate live controls prove configured approve-once, denial, and timeout behavior.

### Next action

Define the smallest administrator policy-matching rule and approver eligibility for the optional prompt path.

## 2026-07-29 — Runtime operation approvals removed

### Final correction

- Plane agent operations never pause for a human confirmation.
- Plane's live authorization is the final runtime allow-or-deny decision.
- Authorized operations execute autonomously.
- Unauthorized operations return a non-leaking denial.
- V1 has no operation-approval policy, prompt state, broker credential, decision endpoint, wait limit, or resume protocol.

### Superseded work

The previously recorded mandatory and optional Hermes approval-broker designs are retained only as historical worklog entries. They are removed from the current architecture, contracts, release manifest, verification manifest, and implementation scope.

### Consequence

Release-manifest approval, verifier qualification, rollout promotion, and deployment approval remain human-controlled delivery gates. They are distinct from agent runtime behavior.

### Next action

Freeze the remaining operation, result, runtime, compatibility, evaluation, and rollout decisions without designing runtime approvals.

## 2026-07-30 — Evaluation and MCP disposition inventories proposed

### Evaluation contracts

- Added 71 distinct candidate behavioral scenarios.
- Allocated exactly 30 broad-planning Luna trials across ten fixtures and 20 additional authenticated Hermes/Luna safety trials.
- Added shared product-evidence contracts for actor, setup, steps, artifacts, comparison, and approval.
- Added Plane-specific prevention cases for comment sanitization, cursor search, relation privacy, referenced objects, parent/date/cycle invariants, member privacy, atomic failure stages, per-mutation idempotency, and curated projections.
- Added paired sandbox liveness and authorized-callback controls so a dead or unexecuted probe cannot pass.
- Explicitly marked all rows non-qualifying until exact fixtures, predicates, schemas, prompts, configuration, commands, and digests are frozen.

### External MCP compatibility

- Expanded the pinned 177-tool inventory into 177 unique disposition rows.
- Verified exact source-name equality and the 171 shared-SDK, one local-PQL, and five hardened-attachment split.
- Clarified that disposition and mapping strategy do not replace the pending generated MCP-handler-to-SDK-call and SDK method/path-to-versioned-operation maps.

### Contract corrections from Plane source review

- Required semantic comment sanitization independently of the weaker public comment-create serializer.
- Required stable cursor search and hydrated curated projections through a Plane-owned query module.
- Required independent visibility checks for related work items.
- Prohibited silent filtering of invalid assignee and label references.
- Prohibited self-parent and descendant hierarchy cycles.
- Required date validation after merging a patch with stored dates.
- Defined current-cycle timestamps, inclusivity, stable ordering, and pagination.

### Verification

- Initial formatting, patch-integrity, count, and exact source-name checks passed before independent review.
- Structural checks proved 71 unique scenario IDs, ten `Live ×3` rows, twenty `Live ×1` rows, 177 unique disposition names, and exact name-set equality with the pinned JSON inventory.
- Independent Plane-source review found 11 of its 14 original semantic gaps resolved and identified four remaining specification ambiguities.
- Independent goal red-team review found no remaining P0 and confirmed the live allocation, sandbox controls, negative controls, qualification language, and MCP strategy wording.
- Closed the four Plane-semantic ambiguities by freezing a Plane-owned current-cycle page seam, member/admin-only assignee choices, idempotent repeated cycle removal with canonical `changed_fields`, and optional comment source links.
- Made the requirement-level matrix an explicit pre-approval gate and clarified the distinction between 71 candidate scenarios and 50 live executions.
- Fresh post-review verification is required immediately before commit; the earlier passing checks are not reused as completion evidence.

### Still open

- Exact eager native tool approval.
- Requirement-level completion-criterion coverage matrix.
- Frozen scenario fixtures and executable predicates.
- Generated MCP handler/SDK route-to-operation maps and digests.
- TypeScript isolate, numeric limits, audit storage policy, load gates, and rollout windows.

### Next action

Close independent-review findings, commit this verified inventory increment, then add the requirement-level verification matrix before requesting manifest approval.

## 2026-07-30 — Requirement-level verification coverage proposed

### Coverage map

- Added `REQUIREMENT-COVERAGE.md` with one row for each of the 78 `GOAL.md` completion criteria.
- Added six primary-verifier obligations and all 18 mandatory `RESULT.md` completion-proof fields.
- Added all 91 release-manifest table rows: 17 identity, seven workflow, ten pilot-operation, 14 runtime-pin, 18 limit, 21 numeric-gate, and four rollout rows.
- Added separate mappings for material release prose covering authorities, eager surface, MCP convergence, preflight, qualification, denominator, promotion, rollback triggers, and exceptions.
- Required the compatibility validator to expand all 177 pinned MCP tools into individual virtual requirement IDs; a count-only assertion cannot pass.
- Defined 24 content-addressed evidence record classes shared by the matrix.

### Verifier clarifications

- Made property/fuzz suites explicit for schemas, pagination, idempotency keys, result limits, and untrusted results.
- Made MCP schema-version transitions explicit.
- Made Computer Use screenshots of both Plane and Hermes state explicit.
- Made provider/model-fingerprint drift invalidate prior evidence and require the complete live suite again.
- Made named authorities, threshold-change approval, promotion/retirement documentation, direct-database bypass checks, all execution-limit boundaries, operator alerts/runbooks, rollout windows, and rollback triggers explicit.
- Replaced check-range shorthand in the requirement matrix with exact VM and evidence IDs for machine validation.
- Added section-relative source ordinals and 17 exact raw source-block digests; all digests recompute from the current goal and release manifest.
- Added a non-recursive VM-023 outer qualifier so the primary verifier must reject a failing, missing, ignored, or falsely passing signed result in every required VM-001 through VM-023 slot.
- Expanded VM-018 with an unapproved numeric-threshold-lowering control.
- Added an independently scored highest-impact oracle for the mandatory release-plan proposal.

### Exact external MCP mapping

- Added `MCP-MAPPING-CONTRACT.md` with a canonical per-tool proof record covering source, runtime schema/transitions, exact behavior classification, handler branches, stable edge IDs, structured SDK/gateway transformations, call dependencies/cardinality, traces, and typed conformance evidence.
- Required independent source-derived control inventories and exact set joins; wildcards, catch-alls, category labels, unresolved values, and bare `sdk_http_intent` cannot satisfy routing proof.
- Added disposition-specific proof for 171 shared-SDK tools, local PQL with zero calls, and each hardened attachment branch.
- Added VM-022 with 17 mapping-sensitivity mutations covering omitted tools/branches/calls, swapped routes, wrong versions, generic mappings, mutation misclassification, invalid edge/dependency graphs, incomplete transformations, mis-keyed evidence, schema-transition drift, attachment bypass, PQL calls, and gateway bypass.

### Verification state

- Structural counts currently match 78 completion criteria, six primary-verifier obligations, 18 completion-proof fields, and 109 release table/prose rows before the 177 per-tool expansion.
- Independent goal and MCP mapping re-reviews found no remaining P0, P1, or P2 after the final corrections.
- This remains a proposed specification. It is not approval, executable verifier evidence, implementation, or production readiness.

### Next action

Rerun fresh structural, source-digest, formatting, staged-diff, and credential-pattern checks, then commit this logical coverage increment. Exact executable scenario fixtures and generated MCP route bundles remain later pre-approval artifacts.

## 2026-07-30 — Planning evaluation fixtures proposed

### Candidate artifacts

- Added ten exact, seed-independent fixture variants binding FX-PLAN-001 through FX-PLAN-010 to EV-001 through EV-010.
- Added a strict Draft 2020-12 fixture schema and predicate-set schema.
- Added the exact autonomous Hermes acceptance prompt for `openai-codex` and `gpt-5.6-luna`.
- Added 54 machine-readable common, plan-created, and scenario-specific pass/fail predicates.
- Added an implementation-independent semantic oracle for references, current-cycle cardinality, deterministic generation, blocker direction, scoring, pagination, pointer resolution, and exact scenario bindings.
- Added a fixture contract that records six SHA-256 artifact digests, fresh identity and time expansion, predicate selection, evidence binding, and the qualification boundary.

### Validation evidence

- Strict AJV compilation and validation passed for both JSON data/schema pairs.
- The semantic oracle passed 10 fixtures and 54 predicates.
- The scoring oracle reproduced every expected top-three source selection, including the 120-item complete-cursor-chain fixture.
- Initial strict validation found and structurally repaired two schema-condition scoping defects; validation was not weakened.
- Recomputed the requirement-coverage hashes for the changed 14-row runtime-pin block and 17-line material-prose block.
- Independent Plane-source review found that EV-009 declared prior-child fields outside `plane.release_plans.create@1`, child-to-source mapping lacked an observable encoding, and generated-artifact eligibility relied on fixture-only metadata.
- Repaired the candidate without expanding the v1 operation: prior children now use Plane create defaults, generated artifacts use the canonical agent-visible `[run:<tag>]` name marker, and every child encodes its source as `[source:<PROJECT-IDENTIFIER>-<SEQUENCE>]`.
- The semantic verifier now derives eligibility and source mapping from those observable names, rejects hidden-metadata disagreement, and checks EV-009's prior child inputs against v1-supported defaults.
- Follow-up review found and closed a remaining harness edge case by constraining every `${RUN_TAG}` to the same canonical marker grammar in the contract, schema, and verifier.
- Final red-team review replaced EV-010's tautological pagination flag with an exact 25-item, five-page cursor oracle requiring four consumed continuations and a terminal null cursor, and normalized both schema IDs to the `plane.so` namespace.

### Qualification state

This is a digest-bound candidate, not user approval, verifier qualification, implementation authorization, or release evidence. Any change to a bound artifact requires new digests and invalidates evidence tied to the prior candidate.

### Next action

Obtain independent source-alignment and false-pass reviews, close findings, rerun all checks, and commit the verified fixture-freeze increment. The exact eager native tool set remains the next unanswered architecture decision.

## 2026-07-30 — Safety evaluation evidence design proposed

### Source-grounded trial design

- Separated EV-011 through EV-030 into a sibling `safety-v1` bundle rather than adding conditional complexity to `planning-v1`.
- Distinguished static fixture validation from live-trial qualification and prohibited producer-supplied Boolean verdicts as qualification oracles.
- Required immutable evidence indexing and producer separation between verifier, fault harness, canary services, supervisor, Hermes, and the independent final verifier.
- Froze RFC 8785 canonical result bytes, exact inline/spill boundaries, bounded authenticated artifact reads, and cumulative-result spill behavior.
- Distinguished gateway audit, pre-actor edge-authentication evidence, and pre-gateway host-security evidence.
- Selected exact result, idempotency, unknown-outcome, dependency, sandbox, callback, concurrency, and restart branches for EV-011 through EV-030.
- Required verifier-owned mutation controls for effect, audit, correlation, fault-boundary, evidence-producer, byte/digest, and skipped-probe false passes.

### Qualification state

This design resolves candidate seams only. It is not the executable `safety-v1` bundle, manifest approval, implementation authorization, or trial evidence.

### Next action

Generate the strict safety fixtures, per-scenario prompts and TypeScript probes, trial-result schema, independent live verifier, operator mutation suite, and transitive digest contract. Record the already granted exact eager native tool approval in the next logical documentation increment.

## 2026-07-30 — Exact eager Hermes surface approved

### User decision

- `plane_search_work_items` is eager in v1.
- `plane_get_work_item` is eager in v1.
- `plane_create_work_item` is eager in v1.
- `plane_update_work_item` is eager in v1.
- `plane_add_comment` is eager in v1.
- `plane_docs` is eager in v1.
- `plane_search` is eager in v1.
- `plane_execute` is eager in v1.

The user approved the exact set at `2026-07-29T20:15:13Z`. This approves tool visibility, not the still-candidate operation schemas or the release and verification manifests.

### Next action

Freeze the remaining safety fixtures and exact supported operation boundary, then present the complete release and verification manifests for their required approvals before implementation.

## 2026-07-30 — Deno boundary corrected from current primary sources

### Source correction

- Confirmed that current Deno supports the proposed `--no-npm` and `--no-remote` flags.
- Confirmed that statically analyzable imports can load without ordinary read permission.
- Confirmed that `localStorage`, Cache API, and Deno KV can consume disk without read/write permission.
- Confirmed that Deno KV remains gated by `--unstable-kv` in the selected current runtime line.
- Replaced permission-only assumptions with a production parser/transpiler boundary, engine-level string-code-generation denial, model-created Worker denial, immutable storage denial stubs, and per-execution disk isolation.
- Selected an outer trusted launcher plus an explicitly separate locked-down model Worker as the executable seam. The launcher embeds the verified `data:` bootstrap so neither process needs read permission; the bootstrap exposes only a narrow immutable Plane RPC facade and removes native Node, raw messaging, storage, and Worker surfaces before importing one bounded verified model module.
- Expanded EV-026 from 18 to 29 exact hostile subcases and from 36 to 58 authorized-callback controls, adding fresh-realm, recoverable function-constructor/import, `process.getBuiltinModule`, and inherited-launcher-read escapes.

### Qualification state

This remains a proposed runtime boundary. The exact Deno artifact, complete launch vector, engine mechanism, bootstrap bytes, and positive-control flag differential must be frozen in the qualification lock and pass the executable safety bundle before release approval or implementation.

## 2026-07-30 — Plane effect cardinality traced

### Source correction

- Confirmed that current Plane has no transactional domain-outbox model; successful endpoints publish multiple Celery tasks directly after persistence rather than registering `transaction.on_commit()` callbacks.
- Confirmed that `Issue.save()` creates one `IssueSequence` row synchronously.
- Confirmed that `IssueComment.save()` creates one `Description` backing row synchronously.
- Confirmed that one minimal comment activity is defensible only after the selected activity task completes; notification and webhook effects remain seed- and configuration-dependent.
- Replaced proposed outbox-row assertions with exact synchronous object deltas, captured broker-publication multisets, and eventual activity readback.
- Required the selected gateway/application-service path to move all initial activity/webhook publication behind `transaction.on_commit()` so a composed transaction rollback cannot leak tasks.
- Selected the simpler candidate audit policy: terminal success audit and invocation result commit in the same transaction as the mutation, so either write failing rolls back the mutation.

### Qualification state

The source facts are confirmed. The exact gateway/application-service composition and its complete broker-publication multiset remain candidate release-manifest inputs and require manifest approval before implementation; the current direct `.delay()` paths do not yet satisfy the proposed transaction contract.

## 2026-08-04 — Accepted contract reconciliation

### Reconciliation

- ADR-0008, ADR-0009, and ADR-0010 are accepted and now control their respective private-memory/gardener, dynamic-delegation/schedule, and versioned-runtime-contract implementation lanes.
- Evaluator review is mandatory before a human accepts or returns any Agent outcome; human acceptance remains the final product decision.
- Explicit approval of `APPROVAL-MANIFEST.md` plus G0 is the sole implementation-start gate. `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` are evidence inputs to that approval and are not competing pre-implementation gates.
- The current integrated Plane state at reconciliation is branch `codex/agent-tooling-architecture`, commit `c5f4537686152dd510c6aaefc0fd82a3eb358d2c`; runtime, application, and verification implementation remain not started.

## 2026-08-04 — Durable non-UI ultragoal created

### Evidence

- Rewrote `docs/agent-tooling/GOAL.md` into the durable ultragoal for the complete non-UI Plane Agent program. The goal now records the accepted one-Agent/one-role product model, backend conversation and event scope, no-chat-UI boundary, reused-settings rule, Plane/Hermes/Buzz ownership, adaptive disclosure, full action/integration completion, phase gates P0–P11, delegated-thread contract, reuse/subtraction rules, anti-cheating rules, safety stops, evidence binding, blocker standard, durable state rules, and completion proof.
- Current Plane evidence: `/Users/nqh/Desktop/CODES/plane`, branch `codex/agent-tooling-architecture`, commit `f2be7a82792611ac843e6d6b210f83723b2c4066` (`f2be7a8279`).
- Current Hermes evidence: `/Users/nqh/Desktop/CODES/hermes-agent`, branch `main`, commit `112f51a5543d490768931514d48a780ad964a868` (`112f51a55`).
- Plane remains at the thin `apps/api/plane/agent` root/lifecycle/adapters scaffold; Hermes `plane_runtime` is installed and discoverable at `/Users/nqh/Desktop/CODES/hermes-agent/plane_runtime/__init__.py`; implementation beyond these scaffolds has not started.
- `/private/tmp/plane-runner.pdf`, the Freeform `Plane-runner` board, and historical task `019fa696-357f-79d0-8dbb-bfe4fa722241` remain exploratory context and are not normative authority.

### Model and delegation policy

- Implementation/work threads use GPT-5.6 Luna xhigh.
- Review threads use GPT-5.6 Sol Medium, following the latest user override.
- The root thread is coordinator/delegator, not feature implementer; work is delegated through threads, never subagents. The root owns integration, conflict resolution, lock/digest updates, gate decisions, final proof, cleanup, and task archiving.

### Active phase and next action

- Active phase: **P0 — durable contracts and approval baseline**.
- Next action: the root coordinator refreshes the authoritative approval record, ownership boundaries, integration-lock inputs, and P0 verifier evidence, then delegates only the first disjoint implementation lanes whose dependencies and start gate are satisfied.

# Plane Agent Tooling: V1 Approval Manifest

## Status

**Ready for approval — implementation remains blocked until explicit user approval.**

This is the controlling pre-implementation manifest. `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` remain legacy evidence inputs; neither is a competing implementation-start gate. The G0 preflight is a coordination verifier and cannot override an ADR, this manifest, or the user approval gate. This manifest is not approved.

`APPROVAL-MANIFEST.md` is the sole G0 human approval authority. G0 freezes semantic names, boundaries, and logical runtime/event/publication invariants only; G1 freezes generated operation/event schemas and catalog artifacts. Physical queue/RPC transport remains a later ADR-0010 implementation choice. No fixture, release, verification, coverage, or generated-artifact document can add a G0 approval or freeze prerequisite.

## Outcome and authority

Ship one production-capable path in which a Plane agent can drive an assigned outcome through Plane semantic operations and self-hosted TypeScript composition, with the same Plane authorization and audit boundary used by external MCP clients.

- Plane is the product owner, system of record, sole authorization authority, and owner of Agent identity, profiles, assignments, runs, invocations, conversations, publication, artifacts, agent-private memory, skills, schedules, delegation, evaluator review, outcomes, gateway, catalog, audit, and settings administration.
- Hermes is the hidden execution kernel and separate runtime-service owner. Its product identity, chat UI, session store, profile directories, registry globals, and operational vocabulary do not cross the Plane product boundary. `plane_runtime.execute` is the narrow adapter seam.
- Buzz is a reference/code donor only. It is not a runtime dependency, production owner, product authority, or durable-state authority.
- The pinned `uxheavy` Plane MCP and Python SDK forks are compatibility adapters. Existing MCP handlers migrate incrementally through the shared gateway and are not recreated as 177 Plane modules.
- Shared generated contracts and fixtures are the cross-repository compatibility source. The integration lock binds their digests to Plane, Hermes, MCP, and SDK revisions.
- All administration reuses existing Plane settings surfaces, services, state, permissions, and UI components. No chat, composer, inbox, thread, sidecar, transcript, or conversation-navigation UI and no second settings framework are in scope.

## Product invariants

- One underlying Plane Agent model has exactly one declarative role per configured agent. Built-in roles are `worker`, `delegator`, `gardener`, `chief_of_staff`, `hr`, and `evaluator`; administrators may define additional single roles.
- Every human receives exactly one chief-of-staff Agent restricted to that human's live Plane permissions. HR proposes Agent creation, change, and retirement; a workspace administrator approves each proposal.
- An assignment is a durable commission, a run is an execution attempt, an invocation is one kernel dispatch, and an outcome submission is the reviewable result. Evaluators review every outcome before a human accepts or returns it; human acceptance is final.
- Approved schedules create ordinary assignments and runs. The dedicated delegator dynamically plans each case, assigns unclaimed work to humans or Agents, and records rationale. Workers and ordinary specialists do not freely delegate. Saved/versioned workflow definitions are out of scope.
- Gardeners may apply approved improvements to private memory and skills across sessions, but knowledge is never copied between Agents. Every improvement is immutable and rollbackable.
- Authorized runtime operations run autonomously within the dedicated Agent's live Plane authorization. V1 has no runtime human-confirmation prompt, approval broker, capability-token system, or pending operation-approval state. Release, rollout, deployment, HR/admin approval, evaluator review, and human outcome acceptance remain separate human-controlled gates.
- Every attempted operation produces append-only intent/outcome audit evidence. Model-visible results are bounded; oversized authoritative results use temporary artifacts and durable audit retains only the approved redacted summary and digest.
- Full Plane integration/action coverage is required before the non-UI program is complete. Adaptive disclosure controls initial context, not global catalog visibility or authorization.

## First supported semantic operation boundary

The first supported semantic boundary is the nine existing major-version operation IDs already grounded in `RELEASE-MANIFEST.md` and `PILOT-CONTRACTS.md`. Their schemas, curated projections, errors, authorization mappings, idempotency, and reconciliation rules are generated from the frozen catalog in P1; no replacement IDs or generic REST projection are introduced.

At G0, this paragraph freezes semantic operation IDs and boundaries only. The machine-readable names are in [`model-facing-surface.json`](./model-facing-surface.json); generated input/output/error schemas and event/publication schemas are explicitly a G1 generation and qualification input.

| Operation ID                   | Semantic capability                                                                 | Initial disclosure                   |
| ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------ |
| `plane.projects.resolve@1`     | Resolve an authorized project by exact ID or identifier                             | Progressive                          |
| `plane.cycles.list_current@1`  | List current cycles with bounded cursor pagination                                  | Progressive                          |
| `plane.work_items.search@1`    | Search work items by text, sequence, or project identifier                          | Eager direct adapter                 |
| `plane.work_items.get@1`       | Read one work item and bounded visible relations                                    | Eager direct adapter                 |
| `plane.project_members.list@1` | List eligible active project members                                                | Progressive                          |
| `plane.work_items.create@1`    | Create one parent or child work item with optional cycle placement                  | Eager direct adapter                 |
| `plane.work_items.update@1`    | Patch one work item and optional cycle placement                                    | Eager direct adapter                 |
| `plane.comments.create@1`      | Create one sanitized source-linked comment                                          | Eager direct adapter                 |
| `plane.release_plans.create@1` | Atomically create one parent, exactly three children, and one source-linked comment | Progressive; required by composition |

Workspace binding is trusted host context, not a caller-supplied operation. The universal discovery primitive is a separate catalog adapter and is always available to an authenticated client; discovery never grants execution permission.

## Frozen model-facing surface

These names are the only model-facing names for the first boundary. They are intentionally unqualified natural Plane vocabulary at the runtime profile boundary; internal contract IDs retain the `plane.*` namespace. The catalog and composition adapters are distinct from domain mutations, so discovery and composition cannot collide with a domain capability.

| Model-facing name    | Surface contract                        | Dispatch or purpose                                                         | Compatibility status                                                                      |
| -------------------- | --------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `search_workspace`   | `plane.workspace.search@1`              | Universal typed-reference discovery across authorized Plane object types    | New approved universal primitive; replaces no legacy contract                             |
| `search_catalog`     | `plane.catalog.search@1`                | Bounded read-only catalog query of the complete supported operation catalog | New approved discovery name; replaces the generic discovery alias                         |
| `describe_operation` | `plane.catalog.describe@1`              | Return one exact major-version operation contract and curated overlay       | New approved discovery name; replaces generic `describe`                                  |
| `compose_typescript` | `plane.typescript.compose@1`            | Run bounded model-written TypeScript through credential-free host callbacks | New approved composition name; supersedes retired generic and prefixed Code Mode surfaces |
| `search_work_items`  | adapter for `plane.work_items.search@1` | Common work-item lookup                                                     | New approved natural Plane name; supersedes the historical prefixed proposal              |
| `get_work_item`      | adapter for `plane.work_items.get@1`    | Read a work item and visible relations                                      | New approved natural Plane name; supersedes the historical prefixed proposal              |
| `create_work_item`   | adapter for `plane.work_items.create@1` | Create one parent or child work item                                        | New approved natural Plane name; supersedes the historical prefixed proposal              |
| `update_work_item`   | adapter for `plane.work_items.update@1` | Update work-item fields or cycle placement                                  | New approved natural Plane name; supersedes the historical prefixed proposal              |
| `create_comment`     | adapter for `plane.comments.create@1`   | Create a source-linked comment                                              | New approved natural Plane name; supersedes the historical prefixed proposal              |

The minimal eager direct pilot set is exactly `search_workspace`, `search_work_items`, `get_work_item`, `create_work_item`, `update_work_item`, and `create_comment`. `search_catalog`, `describe_operation`, and `compose_typescript` are universal/profile tools; the remaining semantic operations are progressively discoverable. The coordinated release-plan operation is invoked through the composition surface in the live planning prompt. This is the smallest useful ergonomic surface; the retired-name negative control rejects generic aliases plus the historical `plane_*` variants.

## Curated catalog overlay

Every generated catalog entry has exactly these behavioral fields in addition to its stable operation ID and major version:

- `purpose`, `model_description`, `examples`, and `aliases`;
- `input_schema`, `output_schema`, and `error_schema`;
- `classification` (`read` or `mutation`), `safety_metadata`, and `authorization_mapping`;
- `idempotency_policy` and `reconciliation_policy`;
- `result_policy` and `artifact_policy`;
- `audit_redaction_policy`;
- `public_api_composition` or `retained_local_behavior`;
- `native_adapter`, `mcp_adapter`, `typescript_adapter`, and `compatibility`;
- `disclosure`, `direct_tool`, `promotion_criteria`, `retirement_criteria`, and `lifecycle`.

OpenAPI supplies transport facts where accurate. The curated overlay owns agent descriptions, semantic composition, authorization mapping, idempotency, result/artifact policy, audit redaction, and disclosure behavior. Private UI/session routes are not automatically catalog operations.

## Logical runtime, dispatch, publication, and event contracts

The controlling logical contract is `plane.agent-runtime/v1`, as accepted by ADR-0010. Plane persists the immutable `RunSnapshot` and per-dispatch `InvocationEnvelope`; the runtime service exposes the logical adapter `plane_runtime.execute(run, invocation, host, emit, cancellation) -> RuntimeExit`. Dispatch is durable, host-bound, schema-validated, idempotent at ingress, ordered by `(runId, invocationId, sequence)`, duplicate-safe, and rejected for forged identity, stale digest, out-of-order sequence, over-limit payloads, or illegal lifecycle transitions. Runtime observations are untrusted until Plane ingress validates them and verifies publication receipts.

The physical durable queue/RPC transport between Plane and the separate runtime service remains implementation-defined, exactly as ADR-0010 permits. A later transport choice cannot change the logical contract, event taxonomy, dispatch semantics, ownership, or evidence requirements. The accepted gateway HTTP adapter remains a thin versioned adapter under Plane's existing API service; it is not a second domain authority.

The versioned runtime event union is:

```ts
type RuntimeEventV1 = {
  protocol: "plane.agent-runtime/v1";
  runId: string;
  invocationId: string;
  sequence: number;
  eventId: string;
  body:
    | ProgressObserved
    | ConversationPublicationObserved
    | InputRequestObserved
    | ArtifactObserved
    | UsageObserved
    | OutcomeSubmissionObserved
    | FailureObserved
    | BlockerObserved;
};

type RuntimeExitV1 = {
  kind: "completed" | "waiting_for_input" | "failed" | "blocked" | "cancelled";
  finalSequence: number;
  failure?: RuntimeFailure;
};
```

Every terminal invocation produces exactly one visible Plane terminal product event: outcome, failure, blocker, or cancellation. `waiting_for_input` is visible and non-terminal. Raw model final text is run-inspection evidence only.

Explicit publication uses `plane.publication.create@1` through the trusted `RuntimeHost` and the Operation Gateway:

```ts
type PublicationRequestV1 = {
  protocol: "plane.agent-publication/v1";
  publicationId: string;
  runId: string;
  invocationId: string;
  sourceEventId: string;
  kind: "conversation" | "input_request" | "artifact" | "outcome";
  ref: string;
};

type PublicationReceiptV1 = {
  protocol: "plane.agent-publication/v1";
  operation: "plane.publication.create@1";
  publicationId: string;
  attemptId: string;
  auditRef: string;
  productEventRef: string;
  state: "accepted" | "replayed";
};
```

The receipt is required before Plane projects conversation, input-request, artifact, or outcome state. Publication is idempotent by actor, workspace, operation major version, and `publicationId`; the trusted host supplies authoritative identity and correlation fields.

## Frozen v1 execution, result, artifact, and audit policy

These values promote the existing detailed v1 table from `RELEASE-MANIFEST.md`; deployment may be stricter but may not be looser without a manifest revision and approval.

| Limit                                        |                                           V1 maximum or rule |
| -------------------------------------------- | -----------------------------------------------------------: |
| Model-written TypeScript source              |                                                 64 KiB UTF-8 |
| Total TypeScript composition wall time       |                                                  120 seconds |
| TypeScript child CPU time                    |                                                   30 seconds |
| TypeScript child memory                      |                                                      256 MiB |
| Inner Plane calls per execution              |                                                           64 |
| Concurrent inner Plane calls                 |                                                            8 |
| Operations in one explicit preflight group   |                                                           16 |
| Inline serialized result per inner operation |                                                       32 KiB |
| Cumulative inline inner results              |                                                      128 KiB |
| Final model-visible composition result       |                                                       64 KiB |
| Combined model-visible stdout and stderr     |                                                       32 KiB |
| Oversized-result preview                     |                                                        8 KiB |
| Temporary authoritative artifact             |                                                       10 MiB |
| Bounded artifact read response               |               32 KiB canonical; at most 23,000 decoded bytes |
| Temporary artifact retention                 |                                        1 hour after creation |
| Expired-artifact cleanup lag                 |                                                   15 minutes |
| Invocation and audit metadata retention      |                                             365 days minimum |
| Bulky full results in durable audit          | Never by default; retain digest and bounded redacted summary |

The host counts attempts before asynchronous dispatch. Rejected, denied, failed, and successful callback attempts consume the inner-call budget. Explicit group preflight validates schema, references, live authorization, budget, and concurrency only; it never emits approval state.

For the coordinated release-plan write, the gateway claims one durable invocation/idempotency record before side effects and commits the four work items, four `IssueSequence` rows, one comment, one `Description` backing row, four cycle bridges when applicable, terminal-success audit fact, and invocation result transition through one named PostgreSQL connection and transaction. Success-audit or result-transition failure, any pre-commit failure, or a proven-not-committed server rejection rolls back all application effects, then appends exactly one correlated `failed` outcome and moves the invocation to `retryable`. Lost commit acknowledgement is `outcome_unknown`, never proven rollback, and requires reconciliation without blind retry. All initial activity/webhook publications register with `transaction.on_commit()`; direct `.delay()` inside the transaction is forbidden. A failed transaction publishes zero callbacks/tasks; broker publications and eventual activity readback are verified separately.

## Delivery and gates

Each slice is demonstrably usable before the next expands scope. Native-only pilot execution is an intermediate prerequisite for the deterministic domain spine; it is not the final G2. G2 requires the real forked-Hermes path with both the approved native direct surface and `compose_typescript`. External MCP mapping may be prepared after G0, handler migration starts after G1, does not block G2, and is required for G3/full compatibility.

- **Pilot gate:** deterministic read and mutation slices, shared contract fixtures, native-only prerequisite, and the mandatory live acceptance run pass. Pilot does not authorize deployment.
- **Production gate:** all release and verification evidence, pinned artifacts, operator readiness, rollback, load, compatibility, and security gates pass; deployment authority explicitly approves.
- **Deployment gate:** each development, allowlisted, expanded, and GA promotion has its own deployed artifact, configuration, observation window, safety-stop, readback, rollback evidence, and explicit approver. No approval here authorizes pushing, merging, deploying, purchasing services, or mutating production.

Exact Deno/Worker technology, the long-tail catalog and promotion set, MCP migration order, production load/latency targets, and rollout observation windows remain open in their declared later lanes. They cannot change this first semantic boundary or logical runtime contract without a new manifest revision.

## Required evidence before production

- Unit and contract tests for every frozen catalog operation and structured error.
- Authorization matrix for allowed and denied Plane roles and object scopes.
- Native, TypeScript callback, and external MCP integration paths crossing the same gateway.
- Idempotency, timeout, interruption, concurrency, bounded-result, artifact-expiry, publication-receipt, and audit-failure tests.
- Security probes for credential disclosure, forged callbacks, cross-run replay, network, filesystem, subprocess, and package escapes, with zero successful escapes.
- Real supported-client compatibility tests against the pinned official MCP server.
- The existing release/verification numeric and rollout gates, as later-lane evidence inputs, after their applicable contracts are qualified.

## Implementation approval gate

Implementation may begin only after the user explicitly approves this statement:

> **I approve `APPROVAL-MANIFEST.md` as the controlling Plane Agent Tooling V1 scope and authorize implementation to begin. I understand that pilot and production remain separately gated.**

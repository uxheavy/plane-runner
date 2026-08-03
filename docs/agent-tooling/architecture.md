# Target Architecture

## System view

```mermaid
flowchart LR
    H["Plane-native agent runtime"] --> N["Plane-native tools"]
    H --> C["TypeScript composition"]
    K["Forked Hermes execution kernel"] --> H
    C --> R["Credential-free host RPC"]
    N --> G["Plane Operation Gateway"]
    R --> G
    E["External Python MCP"] --> G
    G --> A["Plane authentication and authorization"]
    G --> S["Plane application services"]
    G --> U["Append-only audit"]
```

## Supported operation contract

The shared contract is a catalog of stable semantic operations and Plane integrations/actions. It is the only supported agent-facing path into Plane application behavior.

The catalog base is generated from Plane's supported public OpenAPI surface. A curated overlay supplies agent-oriented descriptions, examples, aliases, safety metadata, result policies, idempotency metadata, and direct-tool promotion metadata. Agent-native operations may be added when no appropriate public API operation exists. Private UI/session routes are not automatically agent-facing.

Every operation defines:

- Stable operation ID and version.
- Typed input and output schemas.
- Structured error codes.
- Pagination and filtering behavior where applicable.
- Authorization context requirements.
- Idempotency support and retry behavior.
- Per-result limit and large-result behavior.
- Audit redaction rules.

Catalog visibility is global and complete for the supported Plane integration/action inventory. Adaptive disclosure controls which schemas are eager for a role and assignment; it does not remove operations from global discovery. Discovering an operation does not imply permission to execute it.

## Plane Operation Gateway

The gateway initially lives inside the Plane API service. It is a boundary around existing Plane application services, not a second business-logic implementation.

Cross-process callers use one versioned JSON HTTP adapter under Plane's existing `/api/v1` service. The adapter reuses current API-key and OAuth authentication. Hermes native tools, the credential-free Code Mode host callback, and the official Python SDK transport converge on the same request-bound gateway module below that wire seam.

For every operation it:

1. Authenticates the caller: a dedicated Plane Agent identity for internal Agent paths, or the authenticated human/integration principal for external MCP paths.
2. Validates the operation and input schema.
3. Evaluates current workspace membership, project role, object permissions, and other Plane authorization.
4. Applies idempotency and concurrency controls.
5. Invokes Plane application services.
6. Shapes and limits the returned result.
7. Appends correlated audit evidence.

Native tools, Code Mode callbacks, and external MCP handlers all cross this boundary. No path receives direct database access.

## Identity and credentials

Each Plane-native agent has a dedicated Plane identity and one revocable Plane credential. The trusted runtime host holds the credential and sends it on internal gateway calls. External MCP callers retain their OAuth or personal-access-token principal and do not use an internal Agent credential. Plane derives the acting identity from the authenticated credential; a model-supplied identity is never authoritative.

The initial architecture does not mint run-bound capability tokens or per-operation credentials. Plane's existing authorization remains the sole entitlement system. `run_id`, `tool_call_id`, and invocation ID are correlation and idempotency metadata, not authorization capabilities.

Generated TypeScript never receives the Plane credential.

## Plane Agent domain ownership

Plane keeps four layers explicit:

1. The agent actor identity owns the durable Plane principal, credential, memberships, roles, and object permissions. These facts are the sole entitlement source and are not versioned as behavioral profile content.
2. A behavioral profile version owns persona, exactly one role, instructions, model/runtime defaults, skill and context references, agent-private memory scopes, and default tool-presentation choices. A run pins the resolved version. Built-in roles are `worker`, `delegator`, `gardener`, `chief_of_staff`, `hr`, and `evaluator`; workspace administrators may define additional single roles.
3. Human ownership may provision one automatic chief-of-staff agent per human. That agent's effective permissions are the human's current live Plane permissions and are never broader.
4. Tool availability comes from installed and enabled Plane features and integrations. Tool disclosure chooses which available schemas are eager or progressive. Neither layer grants or denies Plane operations.

The minimum durable relationships have independent lifecycles:

```text
Agent actor -> Profile version
Assignment contract -> target + objective + acceptance + assignee + source/rationale
Run attempt -> assignment + resolved profile/context/tool/runtime snapshot
Runtime invocation -> one kernel dispatch within a run
Outcome submission -> run + artifacts + summary/evidence + review
```

An assignment is the commission to produce an outcome, not the outcome itself. A Plane run may span multiple Hermes sessions, invocations, processes, or restarts. Plane owns the durable conversation and history throughout.

## Plane-native runtime profile

The fork does not expose the `hermes-cli` personality or default 54-tool core as the Plane agent's product surface. A fresh agent begins with Plane identity, role, assignment, current object and conversation context, relevant knowledge, available operations, tool-presentation defaults, and runtime policy.

The model-facing catalog is designed from natural Plane workflows. Every run starts with a small universal Plane work core, then adds eager tools relevant to the agent profile and current assignment. Long-tail Plane operations, external connectors, browser, files, terminal, and specialist integrations may remain available while their schemas are progressively disclosed. The exact universal core is the next open catalog decision.

The universal core has one `search_workspace` discovery primitive. It returns typed references across Plane object types. Specialized searches remain discoverable for workflows that require domain-specific filters or projections; they do not compete in every agent's initial context.

The hidden execution kernel supplies the mechanisms for the model loop, context management, tool dispatch, transcript capture, concurrency, and bounded results. Plane owns the durable product concepts and authoritative state for identity, profiles, assignments, runs, conversations, agent-private memory, skills, schedules, dynamic delegation, artifacts, evaluator review, and outcomes. Reused kernel subsystems sit behind Plane adapters when they support those concepts; kernel-specific work systems and operational tools remain hidden.

Definitions and control state for memory, skills, schedules, and dynamic delegation remain in Plane. There is no saved/versioned workflow-definition system in this scope. The execution kernel may execute these mechanisms behind adapters. Plane-governed storage remains authoritative; `MEMORY.md`, subject-bound `USER.md`, skill packages, and other files are lossless run projections rather than the source of truth. Gardener improvements remain agent-private, immutable, and rollbackable; no knowledge is copied between agents.

Native adapters remain thin:

- Validate the local tool contract.
- Attach trusted execution correlation.
- Call the Plane Operation Gateway.
- Return structured gateway results.

They do not reproduce Plane authorization or business logic.

## Accepted Plane runtime contract

ADR-0010 accepts one versioned logical runtime contract across a durable cross-process seam to a separate co-located agent-runtime service. The queue or RPC transport remains an implementation choice. Plane persists an immutable run snapshot and creates a separate invocation envelope for each kernel dispatch. Human answers and other new context remain Plane-owned events referenced by the envelope, while cumulative run budgets cannot reset across invocations. Inside the runtime service, one `plane_runtime.execute` adapter invokes the kernel through a trusted host, validates observations defensively, and transmits them across the cross-process seam. Plane ingress revalidates and maps them into product state. Plane API modules never import the adapter or the hidden kernel's internal agent class; sessions, profile directories, registry globals, provider clients, and transport details do not cross the logical contract.

A runtime invocation maps to one visible Plane product event: outcome submission, failure, blocker, or cancellation. A waiting-for-input question is a visible non-terminal pause. Kernel final text is not automatically a conversation message. A conversation message requires an explicit agent publication action through an authorized, idempotent, audited Plane semantic operation. Runtime events are untrusted observations until Plane ingress revalidates host binding, identity, schema, sequence, limits, receipts, and legal state transitions. If invocation infrastructure dies first, Plane derives exactly one failure, blocker, or cancellation from authoritative lease state. Intentional messages and compact activity receipts appear in conversation; detailed model/tool transcript remains in the run-inspection surface.

Recoverable invocation failures may continue the same Plane run when safe. `outcome_unknown` is reconciled or escalated and is never blindly replayed. A fresh run follows terminal failure/cancellation or human-requested revision.

Execution leases and containers belong to runtime invocations, not runs. A long-waiting run may release them and later recreate invocation infrastructure from Plane-owned snapshots, events, permitted checkpoints, and remaining budget.

## TypeScript composition surface

The Plane-native profile retains progressive capability discovery and one self-hosted TypeScript composition path. Its final tool names are not yet frozen. Bare `docs`, `search`, and `execute` are rejected because they collide with company knowledge, web, files, connectors, and Hermes's existing code-execution concepts.

TypeScript executes inside the disposable container assigned to one runtime invocation. A restricted child isolate has no Plane credentials, ambient environment secrets, arbitrary network, package installation, subprocess creation, or unrelated filesystem access. Its only Plane capability is a credential-free RPC callback to trusted host code.

Every inner callback traverses Hermes's normal tool middleware and the Plane Operation Gateway. Inner calls therefore retain authorization, audit, result limits, and tool-call correlation.

## Autonomous execution and concurrency

Agents execute autonomously within the live permissions of their dedicated Plane identity. An authorized operation proceeds immediately. An unauthorized operation returns a non-leaking denial. The dedicated delegator may create normal assignments for unclaimed work and records its rationale; ordinary worker and specialist agents do not freely delegate. V1 has no runtime human-confirmation state, approval credential, pending approval, or same-turn approval resume protocol.

An explicitly declared operation group may be preflighted as a group before concurrent dispatch. Preflight performs schema, reference, authorization, budget, and concurrency validation only. It never emits a prompt, pending state, decision token, or resume requirement. Group execution uses per-operation outcomes rather than pretending to be transactional.

## Mutation safety

Supported mutations accept a stable invocation or idempotency key where Plane can provide safe replay semantics.

- A known failed operation may be retried according to its contract.
- A known successful operation returns the recorded result.
- An indeterminate non-idempotent operation returns `outcome_unknown`.
- `outcome_unknown` is never retried blindly.

## Results and artifacts

Model-visible results are always bounded. Normal results return structured data directly. Oversized results return a preview and a temporary artifact reference that existing read tools can inspect in bounded ranges.

After a temporary artifact expires, durable audit retains the redacted intent, affected object IDs, outcome, result hash, and bounded summary rather than the full bulky payload.

Exact thresholds and retention periods remain configuration decisions.

## Audit and replay evidence

Each attempted operation records:

- Authenticated acting principal, with dedicated Plane Agent identity where the caller is internal.
- Runtime run, turn, tool call, and invocation identifiers when the caller is an internal Agent; external MCP request identifiers otherwise.
- Operation ID and contract version.
- Validated arguments or a redacted digest.
- Authorization decision.
- Affected object identifiers.
- Outcome, structured error code, and latency.
- Result hash and bounded summary.

Audit is append-only. Audit evidence supports investigation and reconciliation; it does not imply that arbitrary side effects can be replayed.

## Versioning

Audit and execution metadata pin exact catalog, source schema, TypeScript runtime, and adapter digests. Additive schema evolution is preferred. Breaking behavior requires an explicit compatibility and migration decision.

The external MCP compatibility surface is versioned independently from native tool ergonomics, while both resolve to the shared operation contract. Full Plane integration/action coverage is a non-UI completion requirement even though adaptive disclosure keeps every schema out of the initial prompt.

## Reuse from the Hermes kernel

Reuse:

- Native tool registry and Tool Search.
- Tool-call identifiers and middleware hooks.
- Concurrent execution and ordered result projection.
- Session transcript persistence.
- Oversized-result spill and bounded previews.
- Gateway run events.

Extend only where Plane requires:

- TypeScript rather than Hermes's current Python Code Mode runtime.
- Plane operation catalog adapters.
- Plane identity credential injection in trusted host callbacks.
- Plane authorization, idempotency, and audit integration.
- Stronger child-isolate restrictions for Plane Code Mode.

## Administration and release

All required administration reuses Plane's existing settings surfaces, services, state, permissions, and UI components. No second settings framework is introduced. API and CLI administration remain complete and sufficient for non-UI operation.

After verification, release may proceed through staged rollout even though the current product has no users. Automated safety stops remain mandatory at every stage; authorization bypasses, credential exposure, sandbox escapes, duplicate mutations, missing audit events, or unsafe outcome reconciliation stop promotion and trigger rollback review.

# Plane Agent Tooling Program

This folder is the durable source of truth for taking Plane's agent-facing tooling from architecture through production.

## Status

| Field                  | Value                                                                    |
| ---------------------- | ------------------------------------------------------------------------ |
| Program status         | Accepted architecture and contracts; implementation not started          |
| Reviewed baseline      | `dac96b0ff9a3adb6bfcc3fea235ab4a697ae5acd` (historical evidence only)    |
| Agent runtime status   | Not implemented                                                          |
| Related delivered base | Semantic context picker core merged separately into `preview`            |
| Current gate           | Obtain explicit approval of `APPROVAL-MANIFEST.md` before implementation |
| Last updated           | 2026-08-03                                                               |

## Outcome

Plane agents can safely perform useful Plane work through native semantic operations and TypeScript composition. External agents continue to use Plane's supported MCP interface. Every path shares Plane authorization, result controls, and append-only audit evidence.

## Documents

| Document                                                                | Purpose                                                              |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [Product requirements](./product-requirements.md)                       | Users, outcomes, boundaries, and success measures                    |
| [Architecture](./architecture.md)                                       | Components, trust boundaries, contracts, and runtime behavior        |
| [Delivery plan](./delivery-plan.md)                                     | Workstreams, dependencies, gates, rollout, and ownership             |
| [Non-UI implementation overview](./NON-UI-IMPLEMENTATION-OVERVIEW.md)   | Generated parallel-lane execution map through production rollout     |
| [Decision register](./decision-register.md)                             | Accepted, superseded, and open decisions                             |
| [Release manifest](./RELEASE-MANIFEST.md)                               | Release-scope, version, rollout, and numeric-gate evidence input     |
| [Verification manifest](./VERIFICATION-MANIFEST.md)                     | Check, oracle, negative-control, and evidence input                  |
| [Requirement coverage](./REQUIREMENT-COVERAGE.md)                       | Criterion and release-row checks, oracles, and evidence              |
| [Evaluation scenarios](./EVALUATION-SCENARIOS.md)                       | Seventy-one behavioral contracts and live-trial allocation           |
| [Planning fixture contract](./EVALUATION-FIXTURE-CONTRACT.md)           | Digest-bound EV-001 through EV-010 inputs and predicates             |
| [Safety evaluation design](./SAFETY-EVALUATION-DESIGN.md)               | Exact EV-011 through EV-030 trial, evidence, fault, and oracle seams |
| [Source inventory](./SOURCE-INVENTORY.md)                               | Observed Plane API, MCP, and Hermes facts                            |
| [Interface design](./INTERFACE-DESIGN.md)                               | Four alternatives and the proposed v1 gateway seam                   |
| [MCP compatibility](./MCP-COMPATIBILITY.md)                             | Complete external-tool disposition and conformance plan              |
| [MCP exact mapping](./MCP-MAPPING-CONTRACT.md)                          | Per-tool branch, SDK edge, route join, and sensitivity contract      |
| [MCP dispositions](./inventories/plane-mcp-v0.2.11-dispositions.md)     | Disposition strategy for all 177 pinned external tools               |
| [Runtime design](./RUNTIME-DESIGN.md)                                   | TypeScript isolate options and proposed Deno boundary                |
| [Gateway wire](./GATEWAY-WIRE.md)                                       | Accepted JSON HTTP adapter and proposed v1 envelope                  |
| [Pilot contracts](./PILOT-CONTRACTS.md)                                 | Proposed normalized schemas for the nine pilot operations            |
| [Durable goal](./GOAL.md)                                               | Finish line, constraints, verifiers, and approval gates              |
| [Worklog](./WORKLOG.md)                                                 | Attempts, evidence, current state, and next action                   |
| [Result](./RESULT.md)                                                   | Completion evidence and remaining risks                              |
| [ADR synthesis](./ADR-SYNTHESIS.md)                                     | Non-normative grounding, arena comparison, and design provenance     |
| [Model-facing surface](./model-facing-surface.json)                     | Exact machine-readable G0 name set and G0/G1 contract policy         |
| [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md)       | Durable rationale for the overall architecture                       |
| [ADR-0002](../decisions/0002-autonomous-agent-operations.md)            | Supersedes runtime operation approval with autonomous execution      |
| [ADR-0003](../decisions/0003-plane-agent-native-product-boundary.md)    | Plane Agent is the native product abstraction                        |
| [ADR-0004](../decisions/0004-fork-hermes-as-hidden-execution-kernel.md) | Hermes fork is the hidden execution kernel                           |
| [ADR-0005](../decisions/0005-plane-owned-agent-profiles.md)             | One role-bearing Agent model and profile governance                  |
| [ADR-0006](../decisions/0006-assignment-and-run-lifecycle.md)           | Assignment, run, invocation, outcome, and publication lifecycle      |
| [ADR-0007](../decisions/0007-adaptive-plane-tool-exposure.md)           | Adaptive tool availability and disclosure                            |
| [ADR-0008](../decisions/0008-scoped-memory-and-context.md)              | Accepted private memory, skills, gardener, and rollback rules        |
| [ADR-0009](../decisions/0009-workflows-and-agent-delegation.md)         | Accepted dynamic planning and delegation without saved workflows     |
| [ADR-0010](../decisions/0010-plane-runtime-contract.md)                 | Accepted versioned Plane runtime contract                            |

## Source-of-truth rules

- This folder owns the current product and technical plan.
- ADRs preserve decisions that are expensive to reverse.
- The decision register tracks both accepted decisions and unresolved questions.
- `CONTEXT.md` preserves the broader interview history but does not override accepted decisions here.
- The local Freeform board `Plane-runner` (`8208a432-a415-434c-9f06-5731a6185db4`) is the developer's non-normative workplace mind. Ideas become durable only when promoted into this repository.
- Any local exploratory board or PDF is non-normative developer context and is not an approval or freeze authority.
- `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` provide evidence inputs to the controlling `APPROVAL-MANIFEST.md`; neither is a competing implementation-start gate.
- `RESULT.md` is the canonical in-progress completion-proof placeholder. It is included in the normative seal now, but its pending contents cannot claim G5 completion.
- No runtime, application, or verification implementation may begin until the explicit `APPROVAL-MANIFEST.md` gate—the sole implementation-start approval—is approved and G0 is satisfied. Contract/documentation reconciliation may proceed before that gate.
- G0 freezes semantic names, boundaries, and logical runtime/event/publication invariants only. Generated operation/event schemas are a G1 input; physical queue/RPC transport remains a later ADR-0010 choice. `RELEASE-MANIFEST.md`, `VERIFICATION-MANIFEST.md`, `EVALUATION-FIXTURE-CONTRACT.md`, and `REQUIREMENT-COVERAGE.md` cannot add an approval or freeze prerequisite.
- Observable interfaces must have contract tests before production rollout.

## G0 preflight

The verifier uses the repository's declared `ajv@8` dependency through `ajv/dist/2020.js`. From a fresh checkout, run `pnpm install --frozen-lockfile` before any verifier command; no prior worker `node_modules` is assumed. Renderer output uses deterministic built-in serialization and does not invoke optional local formatters.

Run the approval-ready preflight with:

```sh
node docs/agent-tooling/verifiers/verify-g0-preflight.mjs --mode preflight
```

This mode must pass while human approval is pending. Normal G0 verification is:

```sh
node docs/agent-tooling/verifiers/verify-g0-preflight.mjs --mode g0
```

It must remain non-zero until the exact approval statement in `APPROVAL-MANIFEST.md` is recorded.

The package is sealed with two logical commits: a content/remediation commit followed by an evidence-seal commit that changes only `SOURCE-INVENTORY.md`, `WORKLOG.md`, `g0-readiness.json`, and `integration-lock.g0.json`. Run `node docs/agent-tooling/verifiers/seal-g0-evidence.mjs` after the clean content commit and before the evidence-seal commit. The verifier requires the seal commit's first parent to be the recorded content commit and rejects later semantic or unsealed commits.

Retired-name validation is fail-closed across the governed package. Every Markdown preamble and heading/section has an explicit authority classification, and every governed structured source has an explicit pointer policy with authoritative fields or a documented recursive non-model-facing subtree; missing or stale declarations fail preflight. Text exclusions are token-local: a marked historical occurrence, an ordinary repository path, or a designated internal identifier cannot exempt a separate authoritative occurrence on the same line. The shared authority-marker grammar covers authoritative/model-facing declarations and semantic/schema/input/output/error notes. The negative-control command includes valid-reseal adversarial controls for every retired token family, the prior bypasses, structured-source markers, policy coverage, cleanup retry/backoff, and positive historical, internal-identifier, path, and ordinary-prose contexts.

The pending record has no approver identity or timestamp. A temporary approved-state test may add `approvedBy`, `approvedAt`, and `evidenceBinding` to a copied readiness record; the approved transition may change only that copied readiness file. The real record remains pending until the human uses the exact statement in `APPROVAL-MANIFEST.md`.

Run the machine-readable evidence checks directly with:

```sh
node docs/agent-tooling/verifiers/validate-ajv-2020.mjs
node docs/agent-tooling/verifiers/validate-ownership-map.mjs
node docs/agent-tooling/verifiers/validate-requirement-coverage.mjs
node docs/agent-tooling/verifiers/run-g0-negative-controls.mjs
node docs/agent-tooling/verifiers/test-g0-approved-fixture.mjs
```

## Current next decisions

1. Approve the exact semantic names and boundaries in `APPROVAL-MANIFEST.md`.
2. At G1, generate and qualify the operation/event schemas, catalog, and cross-repository fixtures.
3. Complete release and verification evidence inputs at their later gates and bind their qualified references into the applicable evidence index.
4. Pass G0, then implement full Plane integration/action coverage with adaptive disclosure and reused settings administration.

# Plane Agent Tooling: V1 Approval Manifest

## Status

**Proposed — implementation is blocked until the user approves the gate at the end of this document.**

This is the controlling pre-implementation manifest. On approval, it supersedes the implementation-start gates in `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md`. Those documents remain design and test references; unfinished detail in them does not block coding. Deployment remains separately gated.

## Outcome

Ship one production-capable path in which a Plane agent can drive an assigned outcome through Plane semantic operations and self-hosted TypeScript composition, with the same Plane authorization and audit boundary used by external MCP clients.

## V1 architecture

- Plane remains the system of record and sole authorization authority.
- A Plane Operation Gateway exposes curated, versioned semantic operations through Plane application services; agents never receive database access.
- The fork exposes a dedicated Plane-native runtime profile rather than inheriting the `hermes-cli` personality or default tool catalog.
- Plane owns one durable Agent product/runtime model with exactly one role per configured agent, plus lifecycle and control state for profiles, assignments, runs, conversations, agent-private memory, skills, schedules, delegation, artifacts, evaluator review, and outcomes. The execution kernel supplies model-loop, context, learning, skill-use, schedule/delegation execution, tool-dispatch, transcript/checkpoint, concurrency, and recovery mechanisms behind Plane adapters; it is not presented to users or models as a separate product.
- Built-in roles are worker, delegator, gardener, chief of staff, HR, and evaluator. Every human automatically receives one chief-of-staff agent restricted to that human's live Plane permissions. Administrators may define custom single roles on the same model.
- The dedicated delegator dynamically plans each case, automatically assigns unclaimed work to humans or agents, and records why. Worker and ordinary specialist agents do not freely delegate. Approved schedules create normal assignments and runs.
- Saved/versioned workflow definitions and a workflow-definition system are outside the target design. There is no workflow-definition lane; the delegator plans each case dynamically.
- Gardeners may maintain multiple agents and apply private memory/skill improvements automatically across sessions. Knowledge is never copied between agents; every improvement has immutable history and rollback.
- HR may propose agent creation, change, or retirement, but a workspace administrator approves the proposal. Evaluators review every agent outcome before a human accepts or returns it; human acceptance is final.
- The model-facing surface is derived from natural Plane work and vocabulary.
- Every agent initially receives a small universal Plane work core plus eager tools selected from its profile and current assignment.
- Other available operations remain progressively discoverable without placing every schema in the model's initial context.
- The universal core uses one `search_workspace` tool to find typed references across Plane object types; specialized domain searches are discovered only when advanced filters or projections are needed.
- Exact core tools, discovery tools, and composition-tool names remain open and must be resolved before this manifest can be approved.
- Internal contract IDs, audit events, and adapter metadata retain the `plane.*` namespace even when native Plane-domain tool names do not.
- Model-written TypeScript runs in a restricted child isolate inside the disposable container for one runtime invocation. Containers may be released and recreated while the durable Plane run continues.
- Plane credentials remain in host callbacks. Generated TypeScript receives neither credentials nor ambient authority.
- Plane derives the internal Agent identity from its credential and applies live authorization to every operation; external MCP calls retain their authenticated human or integration caller.
- Authorized operations execute autonomously. V1 adds no second capability-token system and no runtime human-approval prompts.
- Every attempted operation produces append-only audit records, including denial and failure outcomes.
- The existing official Plane Python MCP server remains the external-agent interface and is adapted incrementally to the gateway; it is not replaced.
- The Plane MCP server and Plane Python SDK are maintained as pinned `uxheavy` forks and locked with the Plane and Hermes revisions used for a release.
- Full Plane integration/action coverage is required before the non-UI program is complete. Adaptive disclosure keeps the full catalog discoverable without placing every schema in the initial context.
- All required administration reuses existing Plane settings surfaces, services, state, permissions, and UI components; no settings framework is introduced.
- After verification, rollout may proceed in stages even though there are no current users. Automated safety stops remain mandatory at every stage.

## Initial operation catalog

The searchable catalog includes these semantic operations:

1. Resolve project context.
2. List current cycles.
3. Search work items.
4. Read a work item and its relations.
5. List project members.
6. Create a work item, including parent/child placement.
7. Update a work item and planning placement.
8. Create a source-linked comment.
9. Create one coordinated release plan containing one parent, three children, and one source-linked comment.

The catalog may grow additively. New eager tools require evidence that they are common enough to justify permanent model context.

## Required behavior

- Typed, versioned inputs, outputs, pagination, bounded results, and structured errors.
- Stable invocation keys for mutations; retries must not duplicate committed effects.
- Unknown non-idempotent outcomes are reported as `outcome_unknown` and are never retried blindly.
- Safe independent reads may run concurrently. Mutations preserve declared ordering.
- Callback identity, tenant, run, operation budget, and audit correlation are host-bound and cannot be supplied authoritatively by generated code.
- Generated code has no arbitrary network, subprocess, package-installation, unrelated filesystem, or cross-run callback access.
- Oversized results are summarized or spilled to bounded, expiring artifacts.
- Compatibility dispositions exist for every tool in the pinned official MCP version before that version is declared production-compatible.

## Delivery slices

1. **Read slice:** gateway, catalog, approved Plane-native read tools, progressive capability discovery, TypeScript composition, authorization denials, and audit readback.
2. **Mutation slice:** create/update/comment, idempotency, ordered execution, failure handling, and release-plan composition.
3. **External compatibility:** route the pinned official MCP server through the gateway without breaking its supported clients.
4. **Production hardening:** limits, observability, kill switches, credential lifecycle, load, rollback, and operator documentation.

Each slice must be demonstrably usable before the next slice expands scope. No runtime, application, or verification implementation starts until this manifest is explicitly approved and G0 is satisfied.

## Verification required before production

- Unit and contract tests for every catalog operation and structured error.
- Authorization matrix covering allowed and denied Plane roles and object scopes.
- Integration tests proving all three entry paths—native tools, Code Mode callbacks, and external MCP—cross the gateway.
- Idempotency, timeout, interruption, concurrency, large-result, and audit-failure tests.
- Security probes for credential disclosure, forged callbacks, cross-run replay, network, filesystem, subprocess, and package escapes, with zero successful escapes.
- Real supported-client compatibility tests against the pinned official MCP server.
- At least 50 retained authenticated execution-kernel evaluation runs across happy paths, denials, partial failures, retries, hostile generated code, and materially different project shapes; at least 90% complete scenario success and zero authorization bypasses, credential disclosures, duplicate committed mutations, or missing required audit outcomes.
- One mandatory clean live acceptance run using the locally authenticated ChatGPT subscription, provider `openai-codex`, and exact model `gpt-5.6-luna`, with no fallback.
- The live run must read an authorized project, receive a non-leaking denial from a control project, use native tools and TypeScript Code Mode, create exactly one parent release-plan item, three children, and one source-linked comment, then prove idempotent replay and correlated Plane audit records.
- A documented clean-checkout verification command must fail non-zero on any required check.

## Not required before coding starts

- A completed verifier implementation.
- Pre-generated evidence for code that does not exist.
- Exhaustive mutation-testing of the verification harness.
- Production deployment, rollout approval, or changes to shared environments.
- General workflow DSLs, direct REST catalog projection, direct database access, or a second permission model.

## Separate later gates

- **Pilot gate:** the read and mutation slices pass deterministic tests and the mandatory live acceptance run.
- **Production gate:** all verification above passes against pinned release artifacts; operational readiness, rollback evidence, and deployment authority are explicitly approved.
- No approval of this document authorizes pushing, merging, deploying, purchasing services, or mutating production.

## Implementation approval gate

Implementation may begin only after the user explicitly approves this statement:

> **I approve `APPROVAL-MANIFEST.md` as the controlling Plane Agent Tooling V1 scope and authorize implementation to begin. I understand that pilot and production remain separately gated.**

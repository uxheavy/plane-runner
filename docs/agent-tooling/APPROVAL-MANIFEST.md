# Plane Agent Tooling: V1 Approval Manifest

## Status

**Proposed — implementation is blocked until the user approves the gate at the end of this document.**

This is the controlling pre-implementation manifest. On approval, it supersedes the implementation-start gates in `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md`. Those documents remain design and test references; unfinished detail in them does not block coding. Deployment remains separately gated.

## Outcome

Ship one production-capable path in which a Plane-native agent can drive an assigned outcome through Plane-native tools and self-hosted TypeScript composition, with Hermes operating as its hidden execution kernel and with the same Plane authorization and audit boundary used by external MCP clients.

## V1 architecture

- Plane remains the system of record and sole authorization authority.
- A Plane Operation Gateway exposes curated, versioned semantic operations through Plane application services; agents never receive database access.
- The fork exposes a dedicated Plane-native runtime profile rather than inheriting the `hermes-cli` personality or default tool catalog.
- Hermes supplies execution, lifecycle, delegation, memory, skills, scheduling, and tool-dispatch machinery beneath the Plane-native profile; it is not presented to users or models as a separate product.
- The model-facing surface is derived from natural Plane workflows and vocabulary. Exact eager tools, discovery tools, and composition-tool names remain open and must be resolved before this manifest can be approved.
- Enabled long-tail capabilities remain discoverable without placing every schema in the model's initial context.
- Internal contract IDs, audit events, and adapter metadata retain the `plane.*` namespace even when native Plane-domain tool names do not.
- Model-written TypeScript runs in a restricted child isolate inside the disposable Hermes run container.
- Plane credentials remain in host callbacks. Generated TypeScript receives neither credentials nor ambient authority.
- Plane derives the agent identity from its credential and applies live authorization to every operation.
- Authorized operations execute autonomously. V1 adds no second capability-token system and no runtime human-approval prompts.
- Every attempted operation produces append-only audit records, including denial and failure outcomes.
- The existing official Plane Python MCP server remains the external-agent interface and is adapted incrementally to the gateway; it is not replaced.
- The Plane MCP server and Plane Python SDK are maintained as pinned `uxheavy` forks and locked with the Plane and Hermes revisions used for a release.

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

Each slice must be demonstrably usable before the next slice expands scope.

## Verification required before production

- Unit and contract tests for every catalog operation and structured error.
- Authorization matrix covering allowed and denied Plane roles and object scopes.
- Integration tests proving all three entry paths—native tools, Code Mode callbacks, and external MCP—cross the gateway.
- Idempotency, timeout, interruption, concurrency, large-result, and audit-failure tests.
- Security probes for credential disclosure, forged callbacks, cross-run replay, network, filesystem, subprocess, and package escapes, with zero successful escapes.
- Real supported-client compatibility tests against the pinned official MCP server.
- At least 50 retained authenticated Hermes evaluation runs across happy paths, denials, partial failures, retries, hostile generated code, and materially different project shapes; at least 90% complete workflow success and zero authorization bypasses, credential disclosures, duplicate committed mutations, or missing required audit outcomes.
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

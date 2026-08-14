# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 and the offline G4 production-candidate checks are complete. The
current named working branch starts from wrapper
`3f2a478209fb94049376f781d33ddd4b63a038de`, whose source parent is
`1d1012f71c48615bb28b7988ce74c82421aa1d53` and whose runtime is bound to
Hermes `d2e655101f263329359e7d0de9d0b856202a3e4b`.

Live functional acceptance is not complete. The latest authorized attempt
failed before creating a Plane run or provider request because its credential
source was not bind-visible to Colima. The source correction now stages the
credential into an owner-only Docker-visible path, but it has not completed one
real provider-backed invocation.

Execution now follows the backend-first user-testing loop in [GOAL.md](./GOAL.md):
a fast GPT-5.6 Luna provider smoke, three persistent persona journeys covering
every non-UI Plane Agent feature and failure boundary, targeted root-fix/retest
waves, one final full G4 verifier, and one consolidated Sol Medium review. The
campaign ledgers are under `user-testing-output/plane-agents/`.

The rollback fixture deliberately separates the current candidate from the
previous last-known-good artifacts. `current.planeCommit` is the approved
source parent `1d1012f71c48615bb28b7988ce74c82421aa1d53`; the final candidate
wrapper is its sole child. Current API
services use the rebuilt API artifact source/revision
`1d1012f71c48615bb28b7988ce74c82421aa1d53`,
while `agent-runtime` uses the Hermes `d2e655101f263329359e7d0de9d0b856202a3e4b`
artifact above. The independent `previous` section retains the accepted G3
service artifact digest
`sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e`.
The validator rejects cross-mixing between these current and previous
provenance bindings.

Controlled rollout is a separate successor goal. Historical G5 work contains
offline schemas and rollout-control tooling but no executed or promoted stage,
and none of it is part of the current candidate. Pilot, production, deployment,
destructive, credential, purchase, external-write, and other separately
governed actions remain gated independently.

The Plane-owned provider-egress relay is parent-side and invocation-bound:
the trusted runtime may use its configured external network, while the child
stays AF_UNIX-only and receives no real provider credential. The exact Hermes
constructor seam is wired through the existing bootstrap/service chain and the
candidate image is pinned in the runtime manifest. The local functional
campaign carries one typed descriptor for the only permitted program route:
`openai-codex/gpt-5.6-luna` at
`https://chatgpt.com/backend-api/codex/responses`, with fallback disabled. The
live runner validates that descriptor before reading the credential source,
starting Docker networking, or invoking the API.

### Safe runtime failure observability

`RuntimeExit.failure` keeps the existing `code`, bounded `message`, and
`retryable` fields and may add one allowlisted `cause` when the code is
`runtime_error`: `host_operation_failure`, `cancellation_monitor_failure`,
`invalid_usage_accounting`, or `static_configuration_failure`. Plane maps that
finite value into its existing bounded failure classification; it never copies
the runtime message into the product-facing result. The live failure result
also carries a fixed, capped operation summary for `work_item.read`,
`catalog.search`, `agent.outcome.evaluate`, `agent.outcome.submit`, and
`agent.outcome.publish`, exposing only each operation's status, allowlisted
error code, and count. The count is an audit-outcome count, so an idempotent
publish replay may legitimately make `agent.outcome.publish` greater than one.
Exactly one semantic publication is proved separately by one applied
publication binding and its durable outcome terminal; raw audit rows, inputs,
outputs, and messages remain outside the result.

## What is authoritative

- [GOAL.md](./GOAL.md) is the active objective, success proof, phase/dependency map, and worker/reviewer protocol.
- [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) through [ADR-0010](../decisions/0010-plane-runtime-contract.md) are the durable product and architecture source of truth.
- [Repository AGENTS.md](../../AGENTS.md) and nested `AGENTS.md` files govern implementation boundaries and repository checks.

The ADRs preserve durable decisions. This directory deliberately does not contain a second requirements package, approval manifest, generated plan mirror, G0 seal/readiness harness, historical worklog, or generated evidence set. Git history retains that context; implementation contracts and verification artifacts exist only where they protect an executable contract.

## ADR index

| ADR                                                                 | Decision                                                                            |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [0001](../decisions/0001-plane-agent-tooling-architecture.md)       | Shared Plane Operation Gateway, native Hermes tools, and external MCP compatibility |
| [0002](../decisions/0002-autonomous-agent-operations.md)            | Autonomous operations within live Plane authorization                               |
| [0003](../decisions/0003-plane-agent-native-product-boundary.md)    | Plane Agent as a native Plane product                                               |
| [0004](../decisions/0004-fork-hermes-as-hidden-execution-kernel.md) | Hidden Hermes execution kernel                                                      |
| [0005](../decisions/0005-plane-owned-agent-profiles.md)             | One role-bearing Plane Agent model                                                  |
| [0006](../decisions/0006-assignment-and-run-lifecycle.md)           | Independent assignment and run lifecycle                                            |
| [0007](../decisions/0007-adaptive-plane-tool-exposure.md)           | Adaptive Plane-native tool exposure                                                 |
| [0008](../decisions/0008-scoped-memory-and-context.md)              | Private, governable Agent memory and skills                                         |
| [0009](../decisions/0009-workflows-and-agent-delegation.md)         | Dynamic planning and delegation without saved workflows                             |
| [0010](../decisions/0010-plane-runtime-contract.md)                 | Versioned Plane runtime contract                                                    |

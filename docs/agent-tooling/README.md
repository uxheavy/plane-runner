# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 and the provider-free exact-image G4 checks are complete for the
current shared integration source `9ad2d5c41a6019effa47fc10d96d338d7ffb1378`. The
API artifact is `plane-agent-api:g4-v21-9ad2d5c` at
`sha256:82fb034a78b35622a53167fb6ec2d47ce9e46e53fd0855ae06ef565254e933b1`;
the runtime artifact is
`plane-agent-runtime:hermes-6c460f10-g4-v21-9ad2d5c` at
`sha256:e7fe74d4bc3fdcb61a572336a32aae964fc95fe487eac4284a39423ae8062c60`.
Both are bound to Hermes `6c460f10fe215718dce36dd73cda94155a9a34f8`, MCP
`c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The exact-image functional
red-team and final bootstrap are green provider-free, including verbatim
search-result-to-read handoff with target-digest correlation, versioned
assigned-work-item binding with authorized success and out-of-scope denial;
The v21 source is ready for one final durable metadata wrapper.
W05/W06 are live-clean from their immutable v15 receipt and provider-disabled
zero-delta replay. Manager setup diagnostics and Compose env isolation are covered
by bounded provider-free regressions. W03/W04 and W07/W08 remain dirty after
their v19 `PREPARED_CALL_INVALID` stops; Manager remains dirty after its v19
opaque `api-invocation` stop. Fresh serialized reruns remain separately
authorized.

S00 Wave 0AT passed at Plane
`dcb9ce46e97292777dd3f6f6beff5d520e69bdb6` with one fresh GPT-5.6 Luna
primary and one eligible provider-disabled replay. Provider-free PF1 evidence
is complete for the Worker and Manager route suites and for the tested
Operator contracts. The initial provider-backed persona tasks proved that the
accepted runner exposes only its fixed S00 commission; a typed scenario input
is being added to that existing runner before W/M/O routes resume. Their results
are not inferred. O02 has a separate real external-client closure. The
consolidated Sol review and separately authorized v16 W03/W04 and W07/W08 live
runs remain pending.

Execution now follows the backend-first user-testing loop in [GOAL.md](./GOAL.md):
a fast GPT-5.6 Luna provider smoke, three persistent persona journeys covering
every non-UI Plane Agent feature and failure boundary, targeted root-fix/retest
waves, one final full G4 verifier, and one consolidated Sol Medium review. The
campaign ledgers are under `user-testing-output/plane-agents/`.

The rollback fixture remains an offline binding for the active candidate. Its
`current.planeCommit` is the approved source parent
`9ad2d5c41a6019effa47fc10d96d338d7ffb1378`; its final candidate wrapper is
that parent's sole child. The independent `previous` section retains the accepted G3
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

The live contract owns one canonical six-field `providerRelay` projection.
Authority and config generation use the shared projection, and config-only
preflight requires exact equality before credential staging or provider access.
The runner forwards the validated authority projection to the API invocation,
which reuses those bytes in success and runtime failure receipts. A relay-free
failure receipt is valid only when its bounded facts prove that no run,
invocation, runtime exit, provider attempt, ingress event, or terminal existed.
The standalone validator never treats a missing relay as a wildcard.

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

Every live success or failure receipt includes the same ordered `s00Gate`
predicate projection. It records the first failed predicate, safe lifecycle
states, product references, publication kind and operation, terminal binding
references, and bounded counts. The receipt also carries the validated
`authorityId`, authority-derived canary IDs, and a semantic SHA-256 digest over
the complete bounded receipt body. The standalone validator recomputes that
digest before accepting the handoff. Product publication truth comes from the
durable Plane outcome record; the matching audit receipt only corroborates
freshness. The projection never includes prompts, transcripts, payloads,
tokens, credentials, or runtime messages.

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

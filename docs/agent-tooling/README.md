# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 are complete. Sol Medium review rejected the exact wrapper `d42161bb29bf28f04246b96051cee3a88dcccd36` on P1 because the pinned Hermes adapter did not translate Plane's typed `openai-codex` wire. The adapter blocker is closed in the canonical Hermes owner at `d2e655101f263329359e7d0de9d0b856202a3e4b`, descended directly from Hermes `114eabf9d807b659e36d767e4de46ca056297ccb`; the current Plane lifecycle source commit is `79995597f9b45e137ca2cdbd48756150bdf65478`, a direct child of wrapper `0330003e71ffda6076cee807cd8c5f6eb2e11911`. The current runtime artifact is `plane-agent-runtime:hermes-d2e65510-g4-cleanup-fix` at `sha256:28dd20b99e322ad30445715b70607bfaa453635e9df472e37b595f4b84b4e895`, labeled with Plane revision `79995597f9b45e137ca2cdbd48756150bdf65478`; the API artifact is `plane-agent-api:g4-79995597` at `sha256:a64ff214b8159d1adc1ea939d676c74f808bbc2b71ec0ac81816d3d04245111a`. The exact-image UDS probe and focused adapter tests remain bound to the GPT-5.6 Codex route, XAI preservation, and fail-closed mismatches. The lifecycle regression keeps caller-supplied current and G3 Hermes roots out of cleanup and permits deletion only for verifier-created runtime logs. This is an implementation/provenance correction, not live acceptance. The latest authorized live canary remains permanently `outcome_unknown`; its blocked-canary receipt SHA-256 is `20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a`. A fresh explicitly authorized run is required; that attempt must not be replayed. A separate pre-live root failure retained receipt SHA-256 `4e2a96a9fcaa5dccf5a8a1994b008016bf45aa7b8cc5c163f32aabb4cb4f958c`; it made no provider request, live invocation, credential mutation, or G5 action and is not `outcome_unknown`. Remaining risk is a fresh live G4 after the same Sol review; staged G5 remains incomplete. No chat UI is in scope.

The rollback fixture deliberately separates the current candidate from the
previous last-known-good artifacts. `current.planeCommit` is the exact P2
metadata wrapper `de2a7b98dd26b65f6816f615fcfaa0060331dc31`; current API
services use the rebuilt API artifact source/revision
`79995597f9b45e137ca2cdbd48756150bdf65478`,
while `agent-runtime` uses the Hermes `d2e655101f263329359e7d0de9d0b856202a3e4b`
artifact above. The independent `previous` section retains the accepted G3
service artifact digest
`sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e`.
The validator rejects cross-mixing between these current and previous
provenance bindings.

The implementation authorization is local-only. Live G4 and staged G5 remain
subject to their explicit authority, canary, safety-stop, rollback, and rollout
gates; pilot, production, deployment, destructive, credential, purchase,
external-write, and other separately governed actions remain gated independently.

The Plane-owned provider-egress relay is parent-side and invocation-bound:
the trusted runtime may use its configured external network, while the child
stays AF_UNIX-only and receives no real provider credential. The exact Hermes
constructor seam is now wired through the existing bootstrap/service chain;
the candidate image is pinned in the runtime manifest. A replacement live
provider proof requires fresh explicit external-action authority. That authority
and its matching live config carry one typed descriptor for the only permitted
program route: `openai-codex/gpt-5.6-luna` at
`https://chatgpt.com/backend-api/codex/responses`, with fallback disabled. The
live runner validates that descriptor before reading the credential source,
starting Docker networking, or invoking the API; this work does not complete
live G4 or G5.

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

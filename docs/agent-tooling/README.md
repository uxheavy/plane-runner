# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 are complete. Sol Medium review rejected the exact wrapper `d42161bb29bf28f04246b96051cee3a88dcccd36` on P1 because the pinned Hermes adapter did not translate Plane's typed `openai-codex` wire. The adapter blocker is closed in the canonical Hermes owner at `d2e655101f263329359e7d0de9d0b856202a3e4b`, descended directly from Hermes `114eabf9d807b659e36d767e4de46ca056297ccb`; source commit `ec777c8bbce54a7f131f13d4ddbca0eb9b074fa8` is a direct child of the wrapper `b34c5f9f23797a5f1769ab887536faef640dcd30`, and the final candidate is exactly one metadata wrapper child of that source. The rebuilt runtime artifact is `plane-agent-runtime:hermes-d2e65510-g4-ec777c8b` at `sha256:c8f1ea4c4b12fef35c3b5368d042d75831db91f2719baea719340d0fa537fcdf`, labeled with Plane revision `ec777c8bbce54a7f131f13d4ddbca0eb9b074fa8`; the API artifact is `plane-agent-api:g4-ec777c8b` at `sha256:56978705e73a7f9648a43d0767ca855bfb90a95edb33dba3e2db9abecb3c85d8`. The exact-image UDS probe and focused adapter tests remain bound to the GPT-5.6 Codex route, XAI preservation, and fail-closed mismatches. The lifecycle regression keeps caller-supplied current and G3 Hermes roots out of cleanup and permits deletion only for verifier-created runtime logs. This is an implementation/provenance correction, not live acceptance. The retained explicitly authorized live G4 failure receipt SHA-256 is `7b6bf435b3e1383dd68840ce6b34dce98c0aab51bfbd35408d96cd476d37e801`; it failed at API invocation before any provider attempt, with `providerAttempts=[]`, `provider_requests=0`, `live_requests=0`, `credential_mutations=0`, and `G5_actions=0`, and is not `outcome_unknown`. Its sanitized failure log SHA-256 is `0b91152a213e1540534cda9c74a726896dd7ad971cc89cf248567985437dc50e`. An older live canary receipt `20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a` remains historical `outcome_unknown` evidence and must not be replayed. No live retry is performed here; staged G5 remains incomplete. No chat UI is in scope.

The rollback fixture deliberately separates the current candidate from the
previous last-known-good artifacts. `current.planeCommit` is the approved
source parent `ec777c8bbce54a7f131f13d4ddbca0eb9b074fa8`; the final candidate
wrapper is its sole child. Current API
services use the rebuilt API artifact source/revision
`ec777c8bbce54a7f131f13d4ddbca0eb9b074fa8`,
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

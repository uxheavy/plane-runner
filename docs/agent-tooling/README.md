# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 are complete. Sol Medium review rejected the exact wrapper `d42161bb29bf28f04246b96051cee3a88dcccd36` on P1 because the pinned Hermes adapter did not translate Plane's typed `openai-codex` wire. The adapter blocker is closed in the canonical Hermes owner at `d2e655101f263329359e7d0de9d0b856202a3e4b`, descended directly from Hermes `114eabf9d807b659e36d767e4de46ca056297ccb`; source commit `1d1012f71c48615bb28b7988ce74c82421aa1d53` is a direct child of the wrapper `61eb87390ff8881eefc7a63f27406b358dee82e5`, and the final candidate is exactly one metadata wrapper child of that source. The rebuilt runtime artifact is `plane-agent-runtime:hermes-d2e65510-g4-1d1012f7` at `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`, labeled with Plane revision `1d1012f71c48615bb28b7988ce74c82421aa1d53`; the API artifact is `plane-agent-api:g4-1d1012f7` at `sha256:0a350d4619c9edd55769ed8efdaa2dc740de551689ec41abd682e73565b6c3f2`. The credential-bind correction stages a bounded owner-only provider source into the repository-owned run directory before Docker networking, preflights the staged file without reading its contents, and binds only that staged file during invocation. The exact-image UDS probe and focused adapter tests remain bound to the GPT-5.6 Codex route, XAI preservation, and fail-closed mismatches. The lifecycle regression keeps caller-supplied current and G3 Hermes roots out of cleanup and permits deletion only for verifier-created runtime logs. This is an implementation/provenance correction, not live acceptance. The retained explicitly authorized live G4 failure receipt SHA-256 is `2013336c367397263ea1d5fdf41e46dfda5ed449c8f0be39913f5c6d5c727861`; it failed at `api-invocation` with Docker exit 125 because the caller-owned provider source under `/private/tmp` was not bind-visible to Colima. No Plane run, invocation, or evidence object was created; `provider_requests=0`, `live_requests=0`, `credential_mutations=0`, and `G5_actions=0`, with cleanup removing zero resources. This is pre-container failure evidence, not `outcome_unknown`; no live retry is performed here, staged G5 remains incomplete, and no chat UI is in scope.

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

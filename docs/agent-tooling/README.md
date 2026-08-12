# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 are complete. The previously accepted canonical offline G4 wrapper remains the baseline; the current unaccepted remediation is based on source correction `c1e6fbf999cb0d1bc7bf29ccd09472c43e2d3ce0` and its one exact metadata-wrapper child still requires fresh offline proof before it can replace that baseline. The rebuilt API artifact is `plane-agent-api:g4-c1e6fbf9` at `sha256:84df816b0f15acf87858e677271ea64b9b3cc3d6212f2dc7fe3c09177aa2417b`, and the rebuilt runtime artifact is `plane-agent-runtime:hermes-114eabf9-g4-c1e6fbf9` at `sha256:225964fb13c92605675f2a676bb09048ce7effaeae11c4bfba7bb6cfe8d761b9`; both are source-bound to `c1e6fbf999cb0d1bc7bf29ccd09472c43e2d3ce0`. The remediation uses the external `PLANE_G4_EXPECTED_CANDIDATE` authority, one shared G3/G4 verifier lock with an inherited descriptor, Docker-visible Hermes preflight, and a retained sanitized receipt. The latest authorized live canary attempt remains permanently `outcome_unknown`; its blocked-canary receipt SHA-256 is `20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a`. A fresh explicitly authorized run is required; that attempt must not be replayed. This offline repair made no provider request or retry. Live G4 and staged G5 remain incomplete. No chat UI is in scope.

The rollback fixture deliberately separates the current candidate from the
previous last-known-good artifacts. `current.planeCommit` is the source
correction `c1e6fbf999cb0d1bc7bf29ccd09472c43e2d3ce0`; current API services use
the rebuilt API artifact revision/digest above, and `agent-runtime` uses the
rebuilt runtime artifact revision/digest above. The independent `previous`
section retains the accepted G3 service artifact digest
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

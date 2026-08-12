# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 through G3 are complete. The previously accepted canonical offline G4 wrapper remains the baseline; the current remediation source correction is `0d3100f477bf64ca4f6287efb97c42afa59918f1` and its exact single-child wrapper still requires fresh offline proof before it can replace that baseline. The runtime image remains bound to image-source commit `c47ddfe6174ecd6d66257d8fedbd5d425c7f3172`; the API image is bound to tag `plane-agent-api:g4-0d3100f4`, image ID `sha256:84038637524ae8233050d7c26a0be2c4b9326800f5b3c59e2851378047d88077`, and source revision `0d3100f477bf64ca4f6287efb97c42afa59918f1`. The remediation uses the external `PLANE_G4_EXPECTED_CANDIDATE` authority, one shared G3/G4 verifier lock with an inherited descriptor, Docker-visible Hermes preflight, and a retained sanitized receipt. The latest authorized live attempt remains `outcome_unknown` and will not be blindly replayed; this offline repair made no provider request or retry. Live G4 and staged G5 remain incomplete. No chat UI is in scope.

The implementation authorization is local-only. Live G4 and staged G5 remain
subject to their explicit authority, canary, safety-stop, rollback, and rollout
gates; pilot, production, deployment, destructive, credential, purchase,
external-write, and other separately governed actions remain gated independently.

The Plane-owned provider-egress relay is parent-side and invocation-bound:
the trusted runtime may use its configured external network, while the child
stays AF_UNIX-only and receives no real provider credential. The exact Hermes
constructor seam is now wired through the existing bootstrap/service chain;
the candidate image is pinned in the runtime manifest. A replacement live
provider proof requires fresh explicit external-action authority, and this work
does not complete live G4 or G5.

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

# Plane Agent documentation

This directory contains the compact execution control surface for the non-UI Plane Agent program.

## Current status

G0 is complete as a lightweight condition: ADRs 0001–0010 are present and coherent, [GOAL.md](./GOAL.md) states the scope/non-goals and full lane map, and local implementation is authorized by the user on 2026-08-04. Implementation has not started in this repository.

The authorization is local-only. Pilot, production, deployment, destructive, credential, purchase, external-write, and other separately governed actions remain gated independently.

## What is authoritative

- [GOAL.md](./GOAL.md) is the active objective, success proof, phase/dependency map, and worker/reviewer protocol.
- [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) through [ADR-0010](../decisions/0010-plane-runtime-contract.md) are the durable product and architecture source of truth.
- [Repository AGENTS.md](../../AGENTS.md) and nested `AGENTS.md` files govern implementation boundaries and repository checks.

The ADRs preserve durable decisions. This directory deliberately does not contain a second requirements package, approval manifest, generated plan mirror, G0 seal/readiness harness, historical worklog, or generated evidence set. Git history retains that context; implementation contracts and verification artifacts should be added later only when they protect a real contract.

## ADR index

| ADR | Decision |
| --- | --- |
| [0001](../decisions/0001-plane-agent-tooling-architecture.md) | Shared Plane Operation Gateway, native Hermes tools, and external MCP compatibility |
| [0002](../decisions/0002-autonomous-agent-operations.md) | Autonomous operations within live Plane authorization |
| [0003](../decisions/0003-plane-agent-native-product-boundary.md) | Plane Agent as a native Plane product |
| [0004](../decisions/0004-fork-hermes-as-hidden-execution-kernel.md) | Hidden Hermes execution kernel |
| [0005](../decisions/0005-plane-owned-agent-profiles.md) | One role-bearing Plane Agent model |
| [0006](../decisions/0006-assignment-and-run-lifecycle.md) | Independent assignment and run lifecycle |
| [0007](../decisions/0007-adaptive-plane-tool-exposure.md) | Adaptive Plane-native tool exposure |
| [0008](../decisions/0008-scoped-memory-and-context.md) | Private, governable Agent memory and skills |
| [0009](../decisions/0009-workflows-and-agent-delegation.md) | Dynamic planning and delegation without saved workflows |
| [0010](../decisions/0010-plane-runtime-contract.md) | Versioned Plane runtime contract |

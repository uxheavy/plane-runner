# ADR-0001: Shared Plane operation gateway with native Hermes tools and external MCP compatibility

## Status

Accepted; runtime operation-approval portions superseded by ADR-0002; invocation-isolation wording superseded by ADR-0006

## Date

2026-07-29

## Context

Plane needs a safe and usable agent-facing operation surface. Plane already has a Python MCP server for external clients. Plane Agents backed by the hidden Hermes kernel need common semantic tools plus a way to discover and compose the broader supported Plane API without loading a very large tool catalog into model context.

All agent activity must preserve Plane identity, live authorization, approval policy, mutation safety, bounded results, and append-only auditing. Generated code must not receive credentials or database access.

## Decision

Use one shared Plane Operation Gateway as the supported agent-facing application boundary.

Plane Agents backed by the hidden Hermes kernel use native semantic tools and self-hosted TypeScript Code Mode. Code Mode exposes documentation, searchable operation discovery, and execution through credential-free host callbacks. The generated TypeScript runs in a restricted child isolate within invocation-scoped runtime isolation.

External clients continue to use Plane's Python MCP server. Its handlers migrate incrementally to the same Plane Operation Gateway.

The operation catalog is generated from the supported public OpenAPI surface and enriched by a curated agent-oriented overlay. Plane's live authorization remains authoritative for every operation.

Each Plane Agent uses one revocable Plane credential held only by trusted Hermes host code. The initial design does not add run-bound capability tokens or per-operation credentials.

Hermes's existing native tool registry, Tool Search, concurrency, approval lifecycle, session persistence, and oversized-result behavior are reused where their boundaries fit.

## Alternatives considered

### Use MCP internally for Plane Agents

- Benefit: one protocol for internal and external consumers.
- Cost: adds protocol transport, server lifecycle, and schema translation inside a system that already controls both ends.
- Rejected: native Hermes adapters provide the same model-facing contracts with less internal machinery.

### Expose the complete catalog as eager tools

- Benefit: no discovery step.
- Cost: large tool schemas consume context and reduce selection reliability.
- Rejected: progressive discovery preserves full coverage without an oversized eager surface.

### Project the public OpenAPI schema without curation

- Benefit: minimal catalog maintenance.
- Cost: API descriptions and shapes are not consistently optimized for agent selection, composition, safety, or result control.
- Rejected: generated coverage plus a curated overlay balances completeness and usability.

### Mint run-bound or per-operation capability tokens

- Benefit: shorter credential exposure windows.
- Cost: adds issuance, refresh, verification, failure, and revocation machinery while Plane already authorizes every operation live.
- Rejected for the initial architecture: a revocable credential per dedicated agent identity is sufficient while it remains host-side.

### Pause and replay Code Mode after approval

- Benefit: approval state outlives invocation-scoped runtime isolation.
- Cost: duplicates Hermes's approval lifecycle and makes side-effect replay substantially harder.
- Rejected: reuse Hermes's same-turn blocking approval and fail the run if the runtime dies.

## Consequences

- Native, Code Mode, and external MCP consumers share one supported operation contract.
- Plane authorization and business logic remain centralized.
- The gateway becomes a security- and reliability-critical boundary requiring contract, authorization, audit, and failure testing.
- The Python MCP server remains a supported compatibility layer during migration.
- TypeScript Code Mode requires a new Hermes runtime adapter and restricted child isolate.
- Credential theft from trusted Hermes host state remains possible until revocation; secure storage, rotation, network isolation, and incident controls are required.
- Pending approvals do not survive Hermes or runtime restart in the initial release.
- Further expensive-to-reverse decisions should receive separate ADRs rather than editing this history.

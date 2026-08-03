# ADR-0005: Plane owns declarative agent profiles

## Status

Accepted

## Date

2026-08-03

## Context

Plane Agent needs different teammates such as project managers, customer-intake agents, chiefs of staff, delegators, gardeners, and evaluators. Implementing each role as a separate runtime class would duplicate lifecycle and execution behavior and make roles expensive to add or revise.

Hermes profile files are implementation-oriented and cannot be the durable Plane product model. Plane also needs to keep actor authorization, behavioral configuration, and tool presentation separate; combining them would create an implicit second permission model.

## Decision

Represent each Plane Agent with a durable Plane actor identity and separately versioned Plane-owned behavioral profiles.

The actor identity owns the authorization facts:

- Plane user/agent identity and credential;
- workspace and project memberships;
- roles and object permissions.

These facts are not versioned profile content. They remain the sole entitlement source under ADR-0002.

A behavioral profile version defines:

- display name, persona, role, instructions, and expected outcomes;
- model and runtime defaults where configurable;
- skill and context references;
- default tool-presentation preferences, including eager and progressively disclosed schemas;
- memory scopes;

Plane compiles the profile together with the current assignment into the kernel's runtime configuration. Agent roles are profile data plus skills and presentation defaults, not distinct harness implementations.

Agent profile changes are versioned. A run records the exact resolved profile version used for execution.

Installed or enabled integrations determine which operations are available to present. The profile influences presentation and behavioral defaults only. It does not grant, deny, or pre-authorize operations; every operation still crosses live Plane authorization.

## Alternatives considered

### Create a runtime implementation for each role

- Benefit: each role can be deeply customized.
- Cost: duplicates infrastructure and makes roles architectural commitments.
- Rejected: the roles share one execution model.

### Use Hermes profiles as the source of truth

- Benefit: minimal adapter work.
- Cost: leaks Hermes configuration into Plane and weakens Plane ownership.
- Rejected: the native product needs a stable Plane-domain contract.

### Encode roles only in free-form prompts

- Benefit: very flexible.
- Cost: behavior, skill references, presentation, provenance, versioning, and administration become implicit.
- Rejected: operational policy requires structured fields.

## Consequences

- New agent roles usually require profile, skill, and presentation changes rather than runtime code.
- Plane needs profile schema, validation, versioning, and administrative UI.
- Runtime configuration is generated; users do not edit Hermes files directly.
- Actor identity and permissions change independently from profile versions.
- Tool availability and disclosure remain ergonomics, never a second authorization layer.

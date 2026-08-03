# ADR-0005: Plane owns one role-bearing Agent model

## Status

Accepted

## Date

2026-08-03

## Context

Plane Agent needs different teammates such as workers, chiefs of staff, delegators, gardeners, HR agents, and evaluators. Implementing each role as a separate runtime class would duplicate lifecycle and execution behavior and make roles expensive to add or revise. The product therefore needs one underlying Plane Agent model with explicit role governance.

Hermes profile files are implementation-oriented and cannot be the durable Plane product model. Plane also needs to keep actor authorization, behavioral configuration, and tool presentation separate; combining them would create an implicit second permission model.

## Decision

Represent every configured Plane Agent with one durable Plane actor identity and separately versioned Plane-owned behavioral profiles. Each agent has exactly one role at a time. A role is profile data and policy within the shared Agent model, not a second product abstraction or runtime implementation.

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

The built-in roles are:

| Role | Product responsibility |
| ---- | ---------------------- |
| `worker` | Complete assigned outcomes. Workers and ordinary specialist roles do not freely delegate. |
| `delegator` | Dynamically plan each case, assign unclaimed work to humans or agents, and record the reason for each assignment. |
| `gardener` | Curate agent-private memories and skills across sessions and may maintain multiple agents, with each read and change remaining scoped to its target agent. |
| `chief_of_staff` (chief of staff) | Automatically provision one agent for every human and operate only within that human's current live Plane permissions. |
| `hr` | Propose creation, change, or retirement of agents; a workspace administrator must approve the proposal. |
| `evaluator` | Review every agent outcome before a human may accept or return it. Human review remains final. |

Administrators may define custom roles, but each custom role is still a single role on the same Agent model. A custom role cannot create a new authorization system or bypass the delegator, gardener, HR, evaluator, or human-review controls.

Agent profile changes are versioned. A run records the exact resolved profile version and single role used for execution. HR proposals do not change an agent until a workspace administrator approves them. The automatically provisioned chief-of-staff relationship is maintained by Plane as the human's permissions change.

Installed or enabled integrations determine which operations are available to present. The profile influences presentation and behavioral defaults only. It does not grant, deny, or pre-authorize operations; every operation still crosses live Plane authorization.

## Alternatives considered

### Create a runtime implementation for each role

- Benefit: each role can be deeply customized.
- Cost: duplicates infrastructure and makes roles architectural commitments.
- Rejected: every role must use the same Agent lifecycle and runtime model.

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
- A role change is an explicit, versioned product change rather than an implicit prompt edit.
- A dedicated delegator is the product owner of dynamic routing; ordinary specialist agents do not gain free delegation merely by receiving a skill.
- Tool availability and disclosure remain ergonomics, never a second authorization layer.

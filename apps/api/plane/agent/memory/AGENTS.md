# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/memory/`.

## Local Responsibility

This package owns Plane-side memory governance and deterministic memory
projection helpers. PostgreSQL records are authoritative; runtime files are
disposable projections.

## Architecture Rules

- Agent-private memory and subject-user preferences are separate visibility
  modes. A subject user is never inferred or merged into Agent memory.
- Candidate revisions are immutable. Promotion and rollback append a new
  revision; they never rewrite an earlier revision.
- Context assembly defaults to denying subject-user preferences unless the
  caller supplies an authorization port.

## Local Verification

Run the focused Plane Agent memory, skill, and schedule tests through the
repository-supported API test container. Do not add routes, UI, Hermes
imports, or a second authorization model here.

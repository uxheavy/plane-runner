# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/skills/`.

## Local Responsibility

This package owns Plane-side skill revision governance and lossless Hermes-
compatible package projections.

## Architecture Rules

- Skill package files are stored as structured Plane data and projected only
  for execution; runtime files never become authority.
- Agent, subject-user, template, workspace, and organization visibility remain
  explicit. Sharing beyond one Agent requires an approved human proposal.
- Revision promotion and rollback append immutable revisions.

## Local Verification

Run the focused Plane Agent memory, skill, and schedule tests through the
repository-supported API test container. Do not add routes, UI, Hermes
imports, or a second authorization model here.

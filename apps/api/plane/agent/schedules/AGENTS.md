# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/schedules/`.

## Local Responsibility

This package owns Plane schedule definitions and fire control state.

## Architecture Rules

- A fire creates a normal `AssignmentContract` through the existing lifecycle
  service; it never creates a workflow definition or alternate assignment
  lifecycle.
- Schedule fire keys are deterministic and retries converge on one fire and
  one assignment.
- Stored timezone and retry policy are Plane control state; the kernel may
  execute a dispatched assignment but does not own schedule state.

## Local Verification

Run the focused Plane Agent memory, skill, and schedule tests through the
repository-supported API test container. Do not add routes, UI, Hermes
imports, or a second scheduler aggregate.

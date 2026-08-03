# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/` and its descendants.

## Local Responsibility

This package is the Plane-owned product domain for one Agent system. Its
packages mark independent durable concepts: actor, profile, assignment,
revision, run, invocation, outcome, review, conversation, product events,
artifacts, memory, skills, schedules, delegation, evaluation, lifecycle, and
application services.

It is a regular importable Python package, not a Django app yet. Do not add
`apps.py`, models, migrations, routes, settings registration, test harnesses,
or chat UI as part of this scaffold.

## Architecture Rules

- `actor` owns the durable Plane principal and authorization facts; `profile`
  owns versioned behavioral/configuration data. Built-in roles are profile data,
  skills, and presentation defaults over one underlying agent system—not
  role-specific engines.
- Assignment/revision, run/invocation, and outcome/review remain separate
  records with independent lifecycles. Conversation and product events are
  Plane-owned records; runtime output is not authoritative by itself.
- `lifecycle` is the one deep cross-record state-transition seam. Application
  services and adapters converge on it; record packages must not grow sibling
  transition interfaces or mutate other concepts directly.
- `adapters/operation_gateway`, `catalog`, `idempotency`, and `audit` remain
  Plane-owned. They share the same application rules and must not become a
  second authorization or business-logic implementation.
- Expand operation coverage behind adapters and the catalog. Do not create one
  shallow prompt/runtime module per external operation, including the pinned
  177-tool compatibility surface.
- There is no saved workflow-definition package in this scaffold. Delegation
  is a separate durable concept, not an implicit workflow engine.

## Working Method

Keep this package domain-first and importable. When implementation is
authorized, put legal cross-record transitions behind `lifecycle`, keep
application services request-oriented, and keep transport/runtime integrations
in adapters. Reuse existing Plane authorization and application services
instead of copying their behavior here.

## Current Gotchas

| Gotcha | Why It Matters | Correct Action |
| --- | --- | --- |
| This scaffold is not a Django app. | Registering it or adding migrations would create runtime and schema commitments before the lifecycle contract exists. | Keep it out of `INSTALLED_APPS`; add only the package markers and scoped guidance until implementation is explicitly in scope. |
| A profile role is not an execution engine. | Role-specific runners would duplicate lifecycle and authorization behavior. | Express built-in roles as Plane-owned data/configuration over the common agent system. |
| The external operation count is not the domain shape. | Mirroring 177 operations as prompt/runtime modules makes discovery shallow and fragments enforcement. | Grow the catalog and adapters behind the shared Plane lifecycle/application rules. |

## Local Verification

From `apps/api/`, verify package discovery and imports without Django setup:

```sh
python -c "import importlib.util; assert importlib.util.find_spec('plane.agent')"
python -c "import plane.agent"
```

Inspect the final tree and confirm no files were added under
`apps/api/plane/settings/`, `apps/api/plane/db/migrations/`, routes, or UI.

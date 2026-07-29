# Semantic Context Hydration API Dogfood Report

Status: clean API surface after two waves.

## Outcome

Three persistent personas exercised the routed Django endpoint through isolated
API clients and the PostgreSQL test stack. Wave 1 found one high-severity error:
ordinary malformed top-level payloads returned HTTP 500. The serializer boundary
was fixed, simplified, and retested after the required cooling interval.

Wave 2 passed all 41 persona cases:

- Maya: 3/3 normal entity, field, freshness, ordering, and batch journeys.
- Ravi: 7/7 guest, private, revoked, cross-scope, and deleted-data journeys.
- Quinn: 31/31 authentication, HTTP, malformed input, batching, correlation,
  error-safety, and freshness journeys.

QUI-001 is closed. No blocker, high-severity friction, privacy leak, or external
prerequisite remains in the discoverable API surface.

## Boundary

This is API-only evidence. The local port-8000 service belongs to another stack
and does not contain this branch's route, so deterministic authenticated testing
used this checkout's real Django route and database through DRF clients. Plane's
shared login-cookie implementation was not re-proven here. UI activation,
selection presentation, and the actual composer remain the M7 UI-branch handoff.

Raw secrets and database identifiers were not retained in this dossier.

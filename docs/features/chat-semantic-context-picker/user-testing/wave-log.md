# API Dogfood Wave Log

## Wave 1 — initialized

- Date: 2026-07-29
- Mode: API-only, per user instruction.
- Target: the routed Django endpoint with three isolated authenticated or
  unauthenticated API clients.
- Personas: Maya (primary), Ravi (restricted), Quinn (skeptic).
- Initial sandboxed HTTP check could not reach port 8000. A later approved probe
  found a pre-existing local API container, but it returned route-level 404
  because it does not contain this branch's hydration route.
- Runtime decision: use the repository's Dockerized Django/PostgreSQL contract
  environment. It reaches routing, authentication, permissions, serializers,
  persistence, and response rendering without requiring the missing composer UI.
- Stop condition: every discoverable route/edge case has no blocker or high
  friction, or an external prerequisite is identified.

## Wave 1 — synthesis

| Persona | Routed cases | Result              | Verdict                                                                |
| ------- | -----------: | ------------------- | ---------------------------------------------------------------------- |
| Maya    |            3 | 3 passed            | Normal entity, field, freshness, ordering, and batch surface is clean. |
| Ravi    |            7 | 7 passed            | Authorization and privacy surface is clean.                            |
| Quinn   |           31 | 25 passed, 6 failed | One high-severity validation root cause, QUI-001.                      |

- Baseline feature contract: 11 passed in 4.18 seconds.
- Verified issue: malformed top-level JSON values reach a serializer error-shape
  failure and become a generic HTTP 500 instead of a client-actionable HTTP 400.
- Privacy observation: the generic failure did not expose a traceback, SQL, or
  submitted marker.
- Stop decision: continue. A high-severity ordinary-input failure remains.
- Fix routing: persistent debug/fix agent owns the serializer root fix and
  focused regression verification. The persona agents remain available for the
  next wave.

## Fix wave — QUI-001

- Root cause: top-level `_strict_keys()` raised list-shaped DRF validation
  detail before the serializer's normal error normalization, which caused
  `Serializer.errors` to raise `ValueError` and the endpoint to return 500.
- Fix: map only top-level strict-key failures to DRF's configured non-field
  error key and avoid reflecting submitted unknown key names.
- Simplification: reviewed under the simplify skill; the narrow normalization
  is already the smallest clear behavior-preserving shape.
- Focused verification: Quinn 31 passed; existing hydration contracts 11
  passed.
- Required inter-wave delay: 10 minutes completed before Wave 2.

## Wave 2 — clean surface

| Persona | Routed cases | Result             | Verdict                                         |
| ------- | -----------: | ------------------ | ----------------------------------------------- |
| Maya    |            3 | 3 passed in 2.00s  | Would use; no normal-flow regression.           |
| Ravi    |            7 | 7 passed in 2.55s  | Would use; no permission or privacy regression. |
| Quinn   |           31 | 31 passed in 6.49s | Would integrate; QUI-001 closed.                |

- New issues: none.
- Open blocker or high-severity friction: none.
- Stop decision: clean discoverable API surface. Proceed to the final combined
  verifier and close the dogfood run if it passes.

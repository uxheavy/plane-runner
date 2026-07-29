# Quinn API Dogfood — Wave 1

## Verdict

I would not integrate this endpoint tomorrow. The valid contract, authentication,
batching, ordering, and freshness behavior are coherent, but several ordinary
top-level payload mistakes return HTTP 500 instead of a stable client error.

## Routed API evidence

- Route: `POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/`
- Client: isolated DRF `APIClient`; no direct hydration-service calls
- Runtime: Dockerized Django/PostgreSQL contract environment
- Test file:
  `apps/api/plane/tests/contract/api/test_semantic_context_hydration_quinn_dogfood.py`
- Command:
  `docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/contract/api/test_semantic_context_hydration_quinn_dogfood.py -q`
- Result: 31 cases collected; 25 passed and 6 failed from one shared root cause

## Finding

### QUI-001 — top-level validation mistakes become HTTP 500

- Severity: high
- Reproduction: send any of these authenticated JSON bodies:
  - `null`
  - `{}`
  - `{"schemaVersion": 1}`
  - `{"items": []}`
  - an otherwise shaped body with an unknown top-level key
- Expected: HTTP 400 with a stable JSON validation error
- Actual: HTTP 500 with the sanitized generic JSON error
  `{"error": "Something went wrong please try again later"}`
- Root-cause evidence: the serializer's top-level strict-key validation raises a
  list-style DRF `ValidationError`; `Serializer.errors` then tries to build a
  `ReturnDict` and raises `ValueError`.
- Impact: a typo or incomplete composer payload looks like a server outage,
  creates error logs, and prevents an integrator from distinguishing their bad
  request from a retryable server failure.
- Privacy: the response did not echo the submitted marker or expose a traceback.

The six failing cases are retained as regression evidence for the fix/retest
wave.

## Clean cases

- Anonymous requests return 401; authenticated GET returns 405.
- Malformed JSON returns 400; `text/plain` returns 415.
- Null/wrong-shaped nested items, bad UUIDs, unsupported kinds/entity types, and
  unsupported fields return safe 400 responses.
- Duplicate references are accepted; 50 items succeed and 51 returns 400.
- Response count, reference correlation, input order, and shared authorization
  timestamp are deterministic for a batch.
- Mixed success/not-found-style results remain item-scoped and ordered.
- Missing/equal observed versions are fresh; older/newer versions are stale;
  malformed observed versions return 400.
- Error responses do not echo unknown submitted key/value markers.

## Retest scope

After QUI-001 is fixed, rerun all 31 Quinn cases and confirm every top-level
shape failure returns 400 without a traceback, payload echo, or generic 500.

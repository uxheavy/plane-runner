# Quinn API Dogfood — Wave 2

## Verdict

I would integrate this routed API tomorrow. QUI-001 is closed: all previously
failing top-level payload mistakes now produce safe HTTP 400 responses, and the
rest of the contract remains green.

## Exact routed evidence

- Route: `POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/`
- Client: the same isolated DRF `APIClient` test lane; no direct service calls
- Runtime: Dockerized Django/PostgreSQL contract environment
- Test file:
  `apps/api/plane/tests/contract/api/test_semantic_context_hydration_quinn_dogfood.py`
- Command:
  `docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/contract/api/test_semantic_context_hydration_quinn_dogfood.py -q`
- Result: `31 passed in 6.49s`

## QUI-001 retest

The following formerly failing authenticated JSON bodies now return HTTP 400:

- `null`
- `{}`
- `{"schemaVersion": 1}`
- `{"items": []}`
- an otherwise shaped body containing an unknown top-level key

The unknown marker key/value is not echoed. Every error assertion also confirms
a non-empty JSON response with no traceback, SQL text, or local user path.

## Regression coverage retained

- Anonymous POST remains 401; authenticated GET remains 405.
- Malformed JSON remains 400; `text/plain` remains 415.
- Nested shape errors, invalid UUIDs, unsupported kinds/types/fields, and bad
  observed versions remain safe 400 responses.
- A 50-item duplicate batch remains ordered and correlated; 51 items remains
  rejected with 400.
- Mixed result batches remain item-scoped and ordered.
- Missing/equal observed versions remain fresh, while older/newer versions are
  marked stale.

No blocker, high-severity friction, privacy regression, or new issue was found
in Quinn's Wave 2 surface.

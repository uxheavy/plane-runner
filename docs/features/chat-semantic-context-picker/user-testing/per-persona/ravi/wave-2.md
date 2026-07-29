# Ravi API Dogfood — Wave 2

## Retest purpose

Ravi retested his complete restricted-collaborator lane after QUI-001 changed
top-level serializer error normalization and unknown-key messages. The existing
routed test was reused unchanged against the Dockerized Django/PostgreSQL stack.
No product code or test was modified for this wave.

## Result

**Clean: 7 of 7 routed API cases passed. No authorization or privacy regression
was found.**

Command:

```text
docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/contract/api/test_semantic_context_hydration_ravi_dogfood.py -q
```

Sanitized result:

```text
collected 7 items
.......
7 passed in 2.55s
```

Durable executable evidence:
`apps/api/plane/tests/contract/api/test_semantic_context_hydration_ravi_dogfood.py`

## Privacy and authorization confirmation

| Retested boundary                      | Result                                                         |
| -------------------------------------- | -------------------------------------------------------------- |
| Anonymous session                      | Exact `401`; no result envelope                                |
| Inactive workspace membership          | Exact `403`; no result envelope                                |
| Missing or inactive project membership | Per-item `FORBIDDEN`; no `canonical` member                    |
| Guest page feature disabled            | Non-owned page `FORBIDDEN`; no `canonical` member              |
| Guest page feature enabled             | Approved public page metadata resolves                         |
| Private page and editor block          | Owner allowed; outsider `FORBIDDEN` with no `canonical` member |
| Workspace mismatch                     | Whole request `400`; no partial object result                  |
| Cross-project or deleted work item     | Per-item `NOT_FOUND`; no `canonical` member                    |
| Deleted project-page link              | Per-item `NOT_FOUND`; no `canonical` member                    |
| Revoked project membership             | Per-item `FORBIDDEN`; no `canonical` member                    |

All denied per-item results remained value-free: the test explicitly asserts
that `canonical` is absent. Fixture identities remain randomized under
`@plane.test`; this report contains no credentials, identifiers, or user data.

## Persona verdict

**Would Ravi use this tomorrow? Yes.** QUI-001's response-normalization change
did not alter any restricted-user boundary. In-scope context remains useful,
and access revocation, private ownership, project scope, and deletion are still
enforced on the next routed request.

- Verified issues: none.
- External blockers: none.
- Further Ravi retest needed for QUI-001: no.

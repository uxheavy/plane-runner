# Ravi API Dogfood — Wave 1

## Persona and boundary

Ravi is a restricted guest or limited collaborator. He expects semantic context
to work inside his assigned scope and to fail safely without returning canonical
values outside it.

This wave exercised the real Django route with an isolated DRF `APIClient` and
PostgreSQL test database. It did not call the hydration service directly. The
user requested API-only testing, so browser screenshots and recordings do not
apply; the executable contract test is the durable evidence.

## Result

**Clean: 7 of 7 routed API cases passed. No verified product bug was found.**

Command:

```text
docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/contract/api/test_semantic_context_hydration_ravi_dogfood.py -q
```

Sanitized result:

```text
collected 7 items
.......
7 passed in 2.56s
```

Evidence:
`apps/api/plane/tests/contract/api/test_semantic_context_hydration_ravi_dogfood.py`

## Cases and observed behavior

| Case                                               | Routed API result                         | Privacy result                    |
| -------------------------------------------------- | ----------------------------------------- | --------------------------------- |
| Anonymous request                                  | `401`; no result envelope                 | No canonical value                |
| Inactive workspace member                          | `403`; route rejected                     | No canonical value                |
| Active workspace member without project membership | `200` with per-item `FORBIDDEN`           | No canonical value                |
| Inactive project membership                        | `200` with per-item `FORBIDDEN`           | No canonical value                |
| Guest with page feature disabled                   | Non-owned public page returns `FORBIDDEN` | No canonical value                |
| Guest with page feature enabled                    | Non-owned public page resolves            | Only approved page metadata       |
| Private page owner                                 | Resolves for the owner                    | Only approved page metadata       |
| Private page outsider                              | `FORBIDDEN`                               | No canonical value                |
| Private editor block owner                         | `authorization_only`                      | No editor content is returned     |
| Private editor block outsider                      | `FORBIDDEN`                               | No editor content is returned     |
| Workspace slug mismatch in a mixed batch           | Whole request returns `400`               | No partial result or object value |
| Cross-project object identity                      | Per-item `NOT_FOUND`                      | No canonical value                |
| Soft-deleted work item                             | Per-item `NOT_FOUND`                      | No canonical value                |
| Soft-deleted project-page link                     | Per-item `NOT_FOUND`                      | No canonical value                |
| Revoked project membership after page unlink       | Per-item `FORBIDDEN`                      | No canonical value                |

Fixture identities used randomized `@plane.test` addresses. The evidence records
only response status, stable error codes, and the absence of canonical data; it
contains no credentials or real user content.

## Persona verdict

**Would Ravi use this tomorrow? Yes.** In-scope public-page hydration follows the
guest feature switch, ownership is respected for private pages, revoked access
takes effect on the next request, and inaccessible references do not leak fresh
Plane values.

## Routes blocked and issues

- Routes blocked by external prerequisites: none.
- Verified blocker, high, medium, or low issues: none.
- Retest focus if authorization code changes: private editor blocks, guest feature
  switching, and soft-deleted project-page links.

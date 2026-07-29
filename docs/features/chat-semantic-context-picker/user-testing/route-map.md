# API Route Map

## Target boundary

| Item           | Value                                                                           |
| -------------- | ------------------------------------------------------------------------------- |
| Route          | `POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/`                    |
| Runtime        | Real Django/DRF route through isolated API clients and PostgreSQL test database |
| Authentication | Plane browser session authentication                                            |
| Public API key | Out of scope: the endpoint is a Plane app API, not `plane/api`                  |
| UI/browser     | Excluded by the user's API-only instruction                                     |

A pre-existing local API container is running on port 8000, but an anonymous
HTTP probe returned a Django route-level 404 because that container does not
contain this branch's hydration route. It is not a valid target for this feature
and was not rebuilt because it belongs to a separate local stack. The isolated
test-compose stack exposes a pytest runner rather than a public port, so API
dogfood uses DRF clients against this checkout's routed endpoint. Direct service
calls do not count as route coverage.

## Discoverable surface

| Surface           | Cases                                                                  | Status       |
| ----------------- | ---------------------------------------------------------------------- | ------------ |
| Authentication    | anonymous, active member, inactive/revoked member                      | Wave 2 clean |
| HTTP envelope     | POST, wrong method, JSON parsing, validation errors                    | Wave 2 clean |
| Batch contract    | empty, one, duplicate, mixed, ordered, 50, over 50                     | Wave 2 clean |
| Entity references | work item, project, cycle, module, page, view                          | Wave 2 clean |
| Field references  | 11 allowlisted work-item fields                                        | Wave 2 clean |
| Freshness         | observed version absent, equal, older, newer, malformed                | Wave 2 clean |
| Authorization     | roles, private page, guest access, missing project, workspace mismatch | Wave 2 clean |
| Lifecycle         | deleted entity, deleted link, inactive membership                      | Wave 2 clean |
| Invalid identity  | missing IDs, invalid UUIDs, unsupported kinds/types/fields             | Wave 2 clean |
| Response safety   | canonical allowlists, authorization-only, per-item errors, correlation | Wave 2 clean |

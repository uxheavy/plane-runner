# ADR 0004: Batch Typed References Through Permission-Scoped Hydration

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

The browser can observe fresher local state than Django, but its identifiers and
values are not proof of authorization. Plane's read access is primarily enforced
through active workspace/project membership, project-scoped queries, private
page ownership, and guest feature rules. The missing composer needs a small seam
that can be called at submission and again before later agent actions.

## Decision

- Add one authenticated workspace endpoint that hydrates up to 50 version 1
  references in request order.
- Validate the public shape at the API boundary and again inside the hydration
  service.
- Scope every query to the reference workspace, project, active membership, and
  the entity's existing visibility rule.
- Return curated canonical values for entities and work-item fields.
- Return authorization-only success for editor blocks and ranges after checking
  their parent page or work item.
- Mark a canonical result stale when its current `updated_at` differs from the
  optional client-observed entity version.
- Never query soft-deleted rows or return whole serializers, filter queries,
  member email, editor documents, or arbitrary model fields.

## Failure semantics

| Code          | Meaning                                                              |
| ------------- | -------------------------------------------------------------------- |
| `FORBIDDEN`   | The acting user lacks active project or object visibility.           |
| `NOT_FOUND`   | No active entity exists inside the asserted workspace/project scope. |
| `UNSUPPORTED` | The reference is valid but has no approved server resolver.          |

Malformed versions, kinds, UUIDs, fields, workspace mismatches, and oversized
batches reject the entire request with HTTP 400. Valid item failures remain in an
HTTP 200 batch so one stale or deleted target does not discard other context.

## Rejected alternatives

| Alternative                                  | Reason                                                                                                     |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Trust client values after authentication     | Authentication does not authorize an object or prove freshness.                                            |
| Call existing detail endpoints once per item | Adds round trips and cannot express one ordered partial result.                                            |
| Serialize existing full API serializers      | Exposes fields beyond the context privacy allowlist.                                                       |
| Resolve editor blocks from saved HTML        | Cached HTML can lag Yjs and lacks reliable live range identity.                                            |
| Hide all denial as `NOT_FOUND`               | The product requires visible permission failures; cross-project object mismatch still remains `NOT_FOUND`. |

## Consequences

| Positive                                                   | Cost                                                      |
| ---------------------------------------------------------- | --------------------------------------------------------- |
| Composer integration needs one bounded call                | The service owns explicit project and privacy queries.    |
| Canonical and client observations remain distinguishable   | Consumers must render or handle `stale`.                  |
| Editor privacy is rechecked without false canonical claims | Current editor text remains a labeled client observation. |
| Per-item failures support region bundles                   | Callers must preserve ordered result correlation.         |

## Framework note

The repository pins Django 4.2.30 and Django REST framework 3.15.2. M5 follows
those APIs and Plane conventions. Django's official documentation now marks 4.2
unsupported, so a framework upgrade remains a separate repository risk rather
than hidden scope in this feature.

The implementation follows DRF's requirement that custom views explicitly scope
or check each retrieved object: <https://www.django-rest-framework.org/api-guide/permissions/#object-level-permissions>.

# M5 Evidence: Permission-Safe Server Hydration

## Delivered endpoint

```text
POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/
```

```json
{
  "schemaVersion": 1,
  "items": [
    {
      "reference": {
        "kind": "entity",
        "workspaceSlug": "acme",
        "projectId": "project-uuid",
        "entityType": "work_item",
        "entityId": "work-item-uuid"
      },
      "observedEntityVersion": "2026-07-29T08:00:00Z"
    }
  ]
}
```

The authenticated endpoint accepts 1-50 version 1 items and preserves their
order. Malformed batches return HTTP 400. A valid batch returns HTTP 200 with an
independent success or failure for every item.

## Resolution modes

| Mode                 | References                    | Result                                                                    |
| -------------------- | ----------------------------- | ------------------------------------------------------------------------- |
| `canonical`          | Entities and work-item fields | Curated current value, resolution time, entity version, and `stale` flag  |
| `authorization_only` | Editor blocks and ranges      | Fresh parent-document authorization without invented saved editor content |

Canonical observations use `source: server_canonical`. They remain separate
from browser observations so the composer can preserve both sides of a conflict.

## Permission and privacy proof

| Scenario         | Verified behavior                                                               |
| ---------------- | ------------------------------------------------------------------------------- |
| Roles            | Active admin, member, and guest project members can resolve project entities.   |
| Project scope    | Workspace membership without project membership returns `FORBIDDEN`.            |
| Guest features   | Public pages follow the project's guest feature setting.                        |
| Private pages    | Only the page owner can resolve the page or authorize its editor references.    |
| Cross-project    | An object ID asserted under another project returns `NOT_FOUND`.                |
| Deletion         | Soft-deleted objects and relationship rows are never hydrated.                  |
| Allowlist        | Six entities and 11 work-item fields return only approved context fields.       |
| Defense in depth | The service revalidates references even when called without the API serializer. |

## Verification

| Gate            | Result                                                                      |
| --------------- | --------------------------------------------------------------------------- |
| TDD RED         | Eight endpoint tests failed while the route and implementation were absent. |
| Hydration suite | 11 Django/PostgreSQL cases passed.                                          |
| Page regression | Five existing cross-project page scope cases passed.                        |
| Python gates    | Ruff format and lint passed on all affected Python files.                   |
| Documentation   | Markdown lint and strict validation passed.                                 |

See [ADR 0004](./decisions/0004-server-hydration-boundary.md) for the batch,
failure, and editor trade-offs.

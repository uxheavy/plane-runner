# M5 Evidence Contract: Permission-Safe Server Hydration

## Selected evidence

| Scenario        | Acceptance proof                                                   | Prevention proof                                           |
| --------------- | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| Active roles    | Admin, member, and guest project members resolve approved entities | Workspace membership alone does not authorize project data |
| Canonical value | Current database value and version are returned                    | Client-observed values are never treated as authority      |
| Staleness       | A differing observed version sets `stale: true`                    | Conflict does not overwrite either observation             |
| Private page    | Owner resolves the page or its editor reference                    | Another active project member receives `FORBIDDEN`         |
| Editor          | Parent document access returns `authorization_only`                | Server does not invent canonical Tiptap block content      |
| Scope           | Entity must belong to the referenced workspace and project         | Cross-project identifiers return `NOT_FOUND`               |
| Deletion        | Soft-deleted rows return `NOT_FOUND`                               | `all_objects` is never used for hydration                  |
| Boundary        | Version, shape, UUIDs, workspace, and 50-item limit validate       | Invalid batches never reach hydration queries              |

## Contract boundary

Successful entity and field results contain an allowlisted `server_canonical`
observation. Live editor references contain authorization evidence only because
the database cannot reconstruct the user's current Yjs/Tiptap selection. Results
preserve request order and failures are isolated per valid item.

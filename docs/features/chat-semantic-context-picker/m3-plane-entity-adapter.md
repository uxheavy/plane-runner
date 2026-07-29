# M3 Evidence: Plane Entity Adapter

## Delivered coverage

| Plane target | Current store path                   | Captured context                                                 |
| ------------ | ------------------------------------ | ---------------------------------------------------------------- |
| Work item    | `issue.issues.getIssueById`          | Curated identity, scheduling, relationship IDs, and `updated_at` |
| Project      | `projectRoot.project.getProjectById` | Name, identifier, description, archive state, and timestamp      |
| Cycle        | `cycle.getCycleById`                 | Name, description, status, dates, archive state, and timestamp   |
| Module       | `module.getModuleById`               | Name, description, status, dates, archive state, and timestamp   |
| Page         | `projectPages.getPageById`           | Name, project IDs, access, lock/archive state, and timestamp     |
| View         | `projectView.getViewById`            | Name, description, project, access, lock state, and timestamp    |

## Work-item field allowlist

| Field                             | Output                        |
| --------------------------------- | ----------------------------- |
| `name`, `description`, `priority` | Current scalar value          |
| `state`                           | ID, name, and group           |
| `assignees`                       | ID and display name; no email |
| `labels`                          | ID and name                   |
| `start_date`, `target_date`       | Current date or `null`        |
| `estimate`                        | Point ID, key, and value      |
| `cycle`                           | ID and name                   |
| `module`                          | Ordered module IDs and names  |

Missing related labels remain visible as an ID with a `null` display value.
Missing primary records and project mismatches return `VALUE_UNAVAILABLE`.
Editor blocks return `UNSUPPORTED` until M4.

## CoreRootStore binding

```ts
const contextSource = createPlaneEntityContextSource({
  access: createPlaneCoreRootStoreAccess(rootStore),
});
```

The binding follows the current `CoreRootStore` paths without importing MobX or
the web application into `@plane/chat-context`. Getter functions read on every
capture, so registration and preview contain identity only while capture observes
the latest client state.

## Privacy boundary

| Excluded data                            | Reason                                                 |
| ---------------------------------------- | ------------------------------------------------------ |
| Whole MobX records                       | Prevent accidental field expansion and non-JSON values |
| Member email and profile data            | Not required for semantic context                      |
| Saved-view queries                       | May expose unrelated filters and users                 |
| Page document and work-item editor state | M4 must read the live Tiptap/Yjs source                |
| Arbitrary record properties              | Only explicit projectors can enter the bundle          |

## Verification

| Gate          | Result                                                                                  |
| ------------- | --------------------------------------------------------------------------------------- |
| TDD RED       | Resolver export and CoreRootStore binding export were each absent before implementation |
| Browser suite | Three files and 15 tests passed in stable Google Chrome                                 |
| M3 tests      | Five tests cover fields, entities, freshness, privacy, failures, and store binding      |
| Type and lint | Strict TypeScript and OxLint passed with zero warnings                                  |

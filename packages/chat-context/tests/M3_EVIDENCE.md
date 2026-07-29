# M3 Evidence Contract: Plane Entity Context Source

## Non-visual exception

M3 is a non-UI store Adapter. Evidence is typed Plane-shaped records, current
capture values, allowlisted JSON output, and structured missing-state failures.

## Selected evidence

| Scenario                    | Acceptance proof                                                            | Prevention proof                                                                     |
| --------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Fresh work-item field       | A second capture observes a store mutation                                  | Preview labels and registration do not read store values                             |
| Field allowlist             | Every accepted work-item field returns useful JSON                          | Extra record properties never enter output                                           |
| Related values              | State, members, labels, estimate, cycle, and modules resolve to names       | Missing related labels become explicit `null`, not hidden record data                |
| Entity coverage             | Work item, project, cycle, module, page, and view capture curated snapshots | Descriptions, queries, members, and editor documents are excluded unless allowlisted |
| Missing or mismatched state | Missing records and cross-project records return `VALUE_UNAVAILABLE`        | Client identity cannot select a different project's cached object                    |
| Editor handoff              | Editor blocks return `UNSUPPORTED`                                          | M3 does not infer collaborative content from cached HTML                             |

## Plane source mapping

| Context data | Current Plane owner                                                    |
| ------------ | ---------------------------------------------------------------------- |
| Work items   | `CoreRootStore.issue.issues.getIssueById`                              |
| Projects     | `CoreRootStore.projectRoot.project.getProjectById`                     |
| Cycles       | `CoreRootStore.cycle.getCycleById`                                     |
| Modules      | `CoreRootStore.module.getModuleById`                                   |
| Pages        | `CoreRootStore.projectPages.getPageById`                               |
| Views        | `CoreRootStore.projectView.getViewById`                                |
| States       | `CoreRootStore.state.getStateById`                                     |
| Labels       | `CoreRootStore.label.getLabelById`                                     |
| Members      | `CoreRootStore.memberRoot.getUserDetails`                              |
| Estimates    | `CoreRootStore.projectEstimate.getEstimateById(...).estimatePointById` |

# M1 Evidence Contract: Browser Selection Foundation

## Non-visual exception

M1 changes no user-visible UI, email, notification, link, payment, authentication,
or admin workflow. Expected evidence is browser behavior, typed output, production
bundle inspection, and lifecycle state. No screenshot baseline is required.

## Selected evidence

| Scenario                         | Actor            | Protected outcome                                                             | Prevention outcome                                                    | Comparison                                         |
| -------------------------------- | ---------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------- |
| Nested point selection           | Picker core      | The topmost useful nested target is returned                                  | Ignored Plane and React Grab subtrees cannot intercept selection      | Real Chrome identity assertions                    |
| Portal and open-shadow selection | Picker core      | Targets outside the app root and inside open shadow roots remain discoverable | Invalid coordinates return no candidates                              | Real Chrome identity assertions                    |
| Navigation and unmount           | Picker core      | A replacement target is discoverable after route change                       | Detached targets and stale global state cannot survive                | Real Chrome identity and document-state assertions |
| Production dependency            | Package consumer | Only the primitives subpath is imported                                       | CLI entry points and source-copy UI are absent from the built package | Build output and dependency inspection             |

## Runtime setup

| Field            | Value                                                       |
| ---------------- | ----------------------------------------------------------- |
| Browser          | Installed stable Google Chrome through Vitest Browser Mode  |
| Environment      | Isolated browser iframe; no Plane server or customer data   |
| Upstream package | Exact `react-grab` version from the workspace catalog       |
| Fixture cleanup  | Every test removes its mounted DOM and restores route state |

## Residual risk after M1

- Cross-origin iframe internals are intentionally unsupported by the product scope.
- Semantic ranking and registration lifecycle belong to M2 contract tests.
- Firefox and WebKit coverage is deferred because Plane's first verification target
  is Chromium and the primitive uses standard DOM APIs.

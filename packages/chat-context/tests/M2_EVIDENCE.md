# M2 Evidence Contract: Core Picker and Registry

## Non-visual exception

M2 exports a non-UI TypeScript contract. Evidence is typed requests, versioned
results, browser-backed registry behavior, cancellation state, and JSON-safe
fixtures. No screenshot baseline or user-facing copy changes.

## Selected evidence

| Scenario                  | Acceptance proof                                                              | Prevention proof                                                         | Layer                                         |
| ------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------- |
| Point preview and capture | Nested field previews and captures its current value with its entity ancestor | Preview performs no value read and capture does not fall back silently   | Public Interface in browser runtime           |
| Partial region capture    | Intersecting child fields are ordered and successful values are returned      | Duplicate parent entity is suppressed and failed child becomes a warning | Public Interface in browser runtime           |
| Registration lifecycle    | Unregister removes a target and a new registration can be selected            | Stale disposer cannot remove a replacement registration                  | Registry contract                             |
| Disposal during capture   | Pending capture resolves once as `ABORTED`                                    | Late source completion cannot emit context after disposal                | Public Interface with controlled async source |
| Production acquisition    | React Grab captures through the same public picker contract                   | Core does not depend on fake-only acquisition behavior                   | Public Interface with production Adapter      |
| Bounded failures          | Empty and oversized selections return versioned failures                      | Context sources are not invoked for invalid selections                   | Public Interface                              |
| Operation supersession    | A newer preview completes while the prior capture aborts                      | Late capture cannot overwrite the newer operation                        | Public Interface with controlled async source |

## Runtime setup

| Field                  | Value                                                              |
| ---------------------- | ------------------------------------------------------------------ |
| Runner                 | Vitest Browser Mode in installed stable Google Chrome              |
| Production acquisition | M1 React Grab adapter suite                                        |
| Contract acquisition   | Deterministic fake implementing the same Interface                 |
| Source                 | In-memory fake returning typed JSON values and controlled failures |
| Data                   | Local synthetic Plane references only                              |

## Residual risk after M2

- MobX values and entity labels are M3 adapter responsibilities.
- Tiptap/Yjs identity and live values are M4 responsibilities.
- Permission failures and canonical server values are M5 responsibilities.
- Visual fallback capture and storage are M8 responsibilities.

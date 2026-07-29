# ADR 0002: Use a Minimal Domain-Typed Picker Interface

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

The picker must connect entity-aware Plane rendering, a browser selection engine,
live client state, later server hydration, and a composer that is not in this
checkout. Publishing every internal stage would make dependency changes and UI
lifecycle changes affect all consumers.

## Decision

Expose one deep TypeScript Module with three operations:

```ts
interface SemanticContextPicker {
  register(element: Element, target: SemanticTarget): () => void;
  select(request: SelectionRequest): Promise<SelectionResult>;
  dispose(): void;
}
```

- `register()` associates a mounted element with immutable, typed Plane identity.
- `select({ operation: "preview" })` locates candidates without reading values.
- `select({ operation: "capture" })` resolves current allowlisted values and emits
  a versioned, JSON-safe context bundle.
- `dispose()` cancels active work and releases browser resources idempotently.
- React hooks, session state, React Grab, MobX, Tiptap/Yjs, and server transport are
  Adapters or Implementations behind this Interface.
- Expected failures are discriminated results. Programmer errors may throw.

## Invariants

- Registrations contain references only; DOM attributes never contain values.
- The nearest registered semantic target wins unless the user selects an ancestor.
- A failed field capture never silently becomes a whole-entity capture.
- Values are read at capture time and identify their source and observation time.
- Detached targets cannot remain selectable.
- Client references never grant authorization; the server reauthorizes them.
- Region results are deterministic, bounded, deduplicated, and may contain warnings.

## Consequences

| Positive                                                     | Cost                                                           |
| ------------------------------------------------------------ | -------------------------------------------------------------- |
| Three operations are the stable test and integration surface | Internal orchestration remains substantial                     |
| Plane identity is explicit and auditable                     | New entity kinds require deliberate union and resolver changes |
| React Grab and UI lifecycle can change locally               | React call sites still need semantic registration              |
| Preview avoids MobX/editor reads                             | Capture is asynchronous                                        |
| Future composer consumes only a versioned bundle             | Final transport validation waits for composer access           |

## Implementation evidence

M2 implements the Interface in `@plane/chat-context`. Browser contract tests prove
nested preview, fresh point capture, partial region capture, replacement-safe
registration, and disposal during pending work. See
[M2 evidence](../m2-core-contracts.md).

## Rejected alternatives

| Alternative              | Reason                                                             |
| ------------------------ | ------------------------------------------------------------------ |
| React hooks as the core  | Couples the engine and tests to presentation.                      |
| Public plugin registries | Creates extension contracts before multiple implementations exist. |
| Public state machine     | Exposes overlay lifecycle to entity and composer consumers.        |
| DOM inference only       | Cannot recover reliable Plane object and field identity.           |

## Reconsider when

- A second acquisition engine or editor requires runtime extension rather than a
  private Adapter.
- More than one simultaneous picker session becomes a product requirement.
- Region and visual capture cannot fit the same request/result semantics.

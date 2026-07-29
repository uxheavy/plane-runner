# Interface Design: Chat Semantic Context Picker

## Requirements constrain the seam

| Requirement | Interface consequence |
| --- | --- |
| Plane identity must survive DOM changes | Call sites register typed Plane references, not selectors or copied values. |
| Hover must remain cheap | Preview locates candidates; capture alone reads MobX or Tiptap/Yjs values. |
| React Grab may change | No React Grab type crosses the Plane-owned interface. |
| The composer is absent | It receives a JSON-safe versioned bundle through a later adapter. |
| Visibility is not authorization | Server hydration accepts references and reauthorizes every item. |
| Region capture may be partial | Successful items and structured warnings can coexist. |

## Four alternatives were evaluated

### Alternative A: Domain-first React anchors

Entity-aware hooks such as `useWorkItemSemanticAnchors()` make common call sites
short and difficult to misuse. The design is Plane-specific and keeps values out
of component props. Its React hooks are useful adapters, but they are too close
to presentation to be the core interface or the only test surface.

### Alternative B: Extensible picker kernel

Catalogs for acquisition, providers, resolvers, policies, and snapshots support
many future surfaces. The flexibility creates several public authoring contracts,
extension ordering rules, and partial-failure behaviors before a second real
implementation exists. Those contracts would be shallow and expensive to change.

### Alternative C: Session state machine

`begin()`, immutable snapshots, commands, and a terminal outcome make navigation,
cancellation, supersession, and late asynchronous results explicit. This is a
strong model for the future overlay adapter. It exposes UI lifecycle vocabulary
that entity call sites and composer consumers do not need.

### Alternative D: Minimal deep module

`register()`, `select()`, and `dispose()` hide hit-testing, ranking, value reads,
privacy policy, cancellation, and serialization. A discriminated request supports
preview and capture without separate APIs. This is the smallest stable test seam.

## Decision combines A and D

Alternative D is the core Module. Alternative A supplies typed Plane references
and later convenience hooks. Alternative C may be an internal UI Adapter; it is
not part of the M2 public contract. Alternative B is rejected until at least two
real implementations justify a configurable Seam.

```ts
interface SemanticContextPicker {
  register(element: Element, target: SemanticTarget): () => void;
  select(request: SelectionRequest): Promise<SelectionResult>;
  dispose(): void;
}

type SelectionRequest = {
  operation: "preview" | "capture";
  area:
    | { kind: "point"; clientX: number; clientY: number }
    | { kind: "region"; left: number; top: number; right: number; bottom: number };
  ancestorOffset?: number;
  signal?: AbortSignal;
};
```

The production Implementation uses React Grab through a selection Adapter. A
native fake adapter is the second real Implementation for contract tests. The
Seam is therefore justified without publishing a plugin system.

## Correct usage stays narrow

```tsx
const anchor = useWorkItemSemanticAnchors({
  workspaceSlug,
  projectId,
  workItemId,
});

return <Priority ref={anchor.field("priority")} />;
```

Call sites supply identity only. They never supply a MobX record, current value,
serializer, resolver callback, permission claim, or React Grab object.

## Evolution follows one current version

- Export one current `SemanticContextBundle` alias backed by version 1.
- Add optional fields only when old consumers can ignore them safely.
- Introduce a new discriminated version for incompatible wire changes.
- Keep experimental adapter contracts private until two implementations need them.
- Add visual fallback only after its privacy and storage contract is designed in M8.

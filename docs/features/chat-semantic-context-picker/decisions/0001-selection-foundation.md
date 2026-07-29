# ADR 0001: Use React Grab Primitives Behind a Plane Adapter

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

The semantic context picker needs proven browser inspection behavior without creating a separate application or implementing the entire interaction engine from scratch. Plane still requires domain-specific resolution because external inspectors identify DOM elements or source files, not Plane objects and fields.

## Decision

Use [React Grab](https://github.com/aidenybai/react-grab) as the primary open-source foundation for browser selection.

- Pin `react-grab@0.1.50` exactly.
- Adopt only `getElementsAtPoint` and `isElementGrabbable` from
  `react-grab/primitives` for stateless acquisition and ignored-subtree behavior.
- Do not adopt page freezing, source context, clipboard, editor opening, the full
  renderer, or React Grab's lifecycle listeners.
- Access it only through a Plane-owned selection adapter.
- Keep Plane target registration, context resolution, permission handling, freshness, and serialization independent of React Grab.
- Use React Dev Inspector and stagewise as secondary implementation and product references.
- Keep visual snapshot support outside the foundational dependency decision.

## Consequences

| Positive                                                   | Cost                                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------- |
| Reuses a maintained MIT-licensed inspector engine          | Requires a dependency validation spike                     |
| Matches Plane's TypeScript and React environment           | Needs an adapter because React Grab targets source context |
| Avoids a fully custom hit-testing lifecycle                | Package changes must be absorbed behind the adapter        |
| Leaves Plane semantics and permissions under Plane control | Semantic registration remains Plane-specific work          |
| Real Chrome and bundle verifiers guard the dependency seam | The package installs an unused CLI transitively            |

## Reconsider when

- Production builds cannot use the required primitives without source instrumentation.
- Bundle or runtime cost is disproportionate to the primitive surface used.
- Portal, iframe, or cleanup behavior cannot satisfy acceptance criteria.
- A smaller stable primitive package already present in Plane covers the same behavior.

## M1 evidence

See [M1 selection-foundation evidence](../m1-selection-foundation.md). The adapter
is intentionally stateless; Plane owns Escape, confirmation, navigation, unmount,
and disposal behavior in M2.

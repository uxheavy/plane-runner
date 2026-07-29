# ADR 0005: Integrate the Composer Through Hydration and Consumer Ports

- Status: Accepted
- Date: 2026-07-29
- Decision owners: User and Codex

## Context

The Plane AI composer is not present in this checkout and its UI belongs to a
separate branch. The core still needs to prove that captured bundles can cross a
stable boundary without exposing internal registry, editor, MobX, or UI types.

## Decision

Expose one `SemanticContextComposerAdapter` backed by two caller-supplied ports:

- a hydration port that sends a versioned workspace request and returns unknown
  server data; and
- a consumer port that accepts one verified composer attachment.

The Adapter owns batching, the 50-item limit, single-workspace enforcement,
runtime response parsing, exact ordered-reference correlation, cancellation,
staleness preservation, and structured failures. It removes denied items and
their client observations before calling the consumer. Partial region failures
remain explicit warnings. If no authorized item remains, the consumer is not
called.

## Rejected alternatives

| Alternative                                   | Reason                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------- |
| Import a future composer implementation       | The source is absent and would reverse the dependency direction.          |
| Export only raw JSON types                    | Every consumer would repeat security-sensitive correlation and filtering. |
| Trust a typed hydration callback              | Network JSON is unknown at runtime regardless of TypeScript declarations. |
| Correlate results by array position only      | Reordered responses could attach canonical values to the wrong reference. |
| Pass denied client observations with warnings | This leaks data after the server has rejected current access.             |

## Consequences

| Positive                                    | Cost                                                                |
| ------------------------------------------- | ------------------------------------------------------------------- |
| UI branch implements two narrow callbacks   | It must translate its API client and composer state into the ports. |
| Core behavior is testable without UI code   | Actual chip presentation remains outside this branch.               |
| Runtime guards protect the network boundary | The package carries a small validation implementation.              |
| Canonical and observed values coexist       | The composer must decide how to present stale differences.          |

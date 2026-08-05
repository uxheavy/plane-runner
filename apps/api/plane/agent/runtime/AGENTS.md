# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/runtime/`.

## Local Responsibility

This package owns the Plane-side logical dispatch and untrusted runtime-frame
ingress seam. It owns validation, binding, replay, ordering, and durable
evidence persistence; it does not own a runtime kernel, queue, scheduler, or
product outcome transition.

## Architecture Rules

- The `RuntimeTransport` interface crosses the separate runtime-service seam
  with canonical JSON strings only. Do not import Hermes, AIAgent, or a broker.
- Dispatch sends the immutable stored `RunSnapshot` and `InvocationEnvelope`.
  Ingress receives serialized untrusted `RuntimeEvent`/`RuntimeExit` frames and
  validates them with the packaged `plane.agent-runtime/v1` artifacts.
- Runtime evidence is append-only and invocation-bound. It never becomes an
  alternate Plane lifecycle, publication, conversation, or outcome authority.
- `RuntimeExit(kind=completed)` is evidence only. Explicit lifecycle gateway
  operations and `propose_outcome` remain the product mutation boundary.

## Local Verification

Run the focused runtime contract and G1 tests through the repository API test
environment. Confirm changed/bad frames leave both evidence rows and Plane
product state unchanged, while exact replay returns the original row.

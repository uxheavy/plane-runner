# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/code_mode/` and its descendants.

## Local Responsibility

This folder owns the Plane credential-free host RPC exposed to generated
TypeScript running in an existing restricted child isolate.

## Architecture Rules

- Generated code receives typed callback contracts only; never pass a Plane
  credential, database handle, Django request headers, or model object into the
  child isolate.
- Every callback routes through the accepted Operation Gateway and returns a
  bounded receipt correlated to the bound actor, workspace, run, invocation,
  idempotency key, gateway receipt, and audit receipt.
- The callback layer does not authorize operations or maintain an allowlist;
  live Plane authorization is evaluated by the gateway for each operation.
- Keep cumulative budget, cancellation, output/spill bounds, and the restricted
  network/filesystem/process policy at this seam. Do not import Hermes or add a
  direct network, subprocess, or filesystem client here.

## Local Verification

Run Code Mode host contract tests with the gateway contract tests. Include
replay, binding, cancellation, budget, receipt-size, and forbidden-capability
coverage in the focused evidence.

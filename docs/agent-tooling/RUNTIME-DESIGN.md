# TypeScript Runtime and Isolate Design

## Status

Proposed for release-manifest approval. This is an architecture decision, not implementation authorization.

## Options considered

### Node.js permission model

Node can restrict filesystem, network, child-process, worker, native-addon, WASI, FFI, and inspector access. Its own documentation explicitly describes the mechanism as a seat belt for trusted code rather than a security boundary for malicious code. It also documents bypass-relevant inherited descriptors and cross-process signaling behavior.

Disposition: reject as the only generated-code isolate. It may remain a trusted build or host runtime.

### Deno permission sandbox in the run container

Deno executes TypeScript directly and denies sensitive I/O unless granted. Its permission model covers filesystem, network, environment, subprocess, system information, FFI, and imports. Explicit deny flags take precedence and `--no-prompt` prevents generated code from requesting permission interactively.

Disposition: recommended, with a trusted supervisor and the existing disposable run container as defense in depth.

### Embedded QuickJS or WebAssembly runtime

An embedded runtime can expose only explicit host functions and can provide strong memory and instruction limits. It adds a native dependency, a second JavaScript compatibility target, custom TypeScript compilation, and more runtime maintenance.

Disposition: reserve as fallback if the Deno security qualification fails.

### Nested container or microVM per execution

This gives the strongest kernel boundary but adds image lifecycle, startup, scheduling, networking, and cleanup complexity inside an already disposable run container.

Disposition: not v1. Reconsider only if the approved threat model requires a kernel boundary between Hermes and generated code.

## Recommended v1 boundary

Run a pinned Deno process inside the same disposable Hermes run container:

1. Hermes starts a trusted, versioned supervisor entry point under a dedicated unprivileged child identity.
2. The child receives a minimal fixed environment with no Plane, model-provider, subscription, MCP, storage, or host credentials.
3. Deno starts with `--no-prompt`, `--no-config`, `--no-npm`, `--no-remote`, and explicit deny policy for read, write, network, environment, subprocess, system, FFI, and import access.
4. The supervisor loads only the submitted TypeScript source and a versioned generated Plane declaration/client from trusted in-memory input or its pinned entry point.
5. Generated code runs in a separate Deno Worker with no permissions.
6. A dedicated inherited descriptor carries framed supervisor-to-host RPC. Generated code receives no descriptor, endpoint, token, or authoritative context fields.
7. The supervisor converts allowed Worker messages into `plane.call(operation, input)` requests. The host supplies workspace, agent, run, turn, outer tool call, budgets, catalog digest, approval binding, and audit correlation.
8. Arbitrary stdout and stderr are treated only as bounded logs, never as authenticated RPC.
9. The host enforces wall time, CPU, memory, process count, inner-call count, concurrency, and cumulative result limits and terminates the child on violation.
10. The outer disposable run container supplies the kernel, mount, process, and cleanup boundary. Generated code receives no direct database or Plane network route.

## Module and seam placement

- `plane_execute` is the Hermes adapter that accepts model-written TypeScript.
- The TypeScript runner module owns compilation/loading, isolate lifecycle, limits, and log/result framing.
- The credential-free callback is the only seam from the runner to Plane operations.
- The Plane Operation Gateway remains the sole module that owns authorization, approval policy, mutation safety, result shaping, and audit evidence.
- Deno's permission system is a sandbox adapter, not a substitute for gateway policy.

## Package and import policy

- V1 exposes standard ECMAScript/TypeScript and the generated `plane` client only.
- Static and dynamic remote imports are denied.
- `npm:`, `jsr:`, URL, local-path, and data-driven package loading are denied to model-written code.
- No install command or package cache is model-accessible.
- Any future library must be bundled into the reviewed runtime artifact and added through a manifest revision.

## Approval interception

The outer `plane_execute` call does not pre-authorize its inner operations. Each `plane.call` crosses the host callback and gateway independently. Authorized calls execute autonomously under the default policy. If an administrator configures an effect to prompt, an approval-required transition pauses only that logical inner call. The existing Hermes approval lifecycle resumes the exact call in the same turn. Sibling calls that were already authorized and admitted may continue.

## Required security qualification

- Read, write, directory, `/proc`, and unrelated descriptor probes.
- DNS, HTTP, TCP, UDP, loopback, link-local, metadata, and Unix-socket probes.
- Environment, command execution, worker escalation, FFI, WASI, native addon, inspector, and signal probes.
- Static, dynamic, `npm:`, `jsr:`, URL, and local import probes.
- RPC-frame injection through stdout/stderr.
- Direct inherited-descriptor discovery and use.
- Cross-run, sibling-process, stale-handle, identity, workspace, catalog, budget, and correlation forgery.
- CPU loop, memory growth, output flood, call flood, concurrency flood, timeout, cancellation, and parent/container death.
- Runtime and supervisor vulnerability review against the exact pinned artifact.

Failure of a security invariant blocks release. It does not silently widen a Deno permission or move a credential into the child.

## Source evidence

- Deno permissions reference: <https://docs.deno.com/runtime/reference/permissions/>
- Deno security model: <https://docs.deno.com/runtime/fundamentals/security/>
- Deno run reference: <https://docs.deno.com/runtime/reference/cli/run/>
- Node.js permission model and documented constraints: <https://nodejs.org/api/permissions.html>

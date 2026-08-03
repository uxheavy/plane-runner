# TypeScript Runtime and Isolate Design

## Status

Proposed architecture input. This document is not an approval or freeze authority and does not authorize implementation. G0 freezes the logical runtime/event/publication boundary; generated schemas are a G1 input, while physical queue/RPC remains implementation-defined under ADR-0010.

## Options considered

### Node.js permission model

Node can restrict filesystem, network, child-process, worker, native-addon, WASI, FFI, and inspector access. Its own documentation explicitly describes the mechanism as a seat belt for trusted code rather than a security boundary for malicious code. It also documents bypass-relevant inherited descriptors and cross-process signaling behavior.

Disposition: reject as the only generated-code isolate. It may remain a trusted build or host runtime.

### Deno permission sandbox in the runtime-invocation container

Deno executes TypeScript directly and denies sensitive I/O unless granted. Its permission model covers filesystem, network, environment, subprocess, system information, FFI, and imports. Explicit deny flags take precedence and `--no-prompt` prevents generated code from requesting permission interactively.

Disposition: recommended, with a trusted supervisor and a disposable runtime-invocation container as defense in depth.

### Embedded QuickJS or WebAssembly runtime

An embedded runtime can expose only explicit host functions and can provide strong memory and instruction limits. It adds a native dependency, a second JavaScript compatibility target, custom TypeScript compilation, and more runtime maintenance.

Disposition: reserve as fallback if the Deno security qualification fails.

### Nested container or microVM per execution

This gives the strongest kernel boundary but adds image lifecycle, startup, scheduling, networking, and cleanup complexity inside an already disposable runtime-invocation container.

Disposition: not v1. Reconsider only if the approved threat model requires a kernel boundary between Hermes and generated code.

## Recommended v1 boundary

Run a pinned Deno process inside the disposable container for one Hermes-backed runtime invocation:

1. Hermes starts a trusted, versioned supervisor entry point under a dedicated unprivileged child identity.
2. The child receives a minimal fixed environment with no Plane, model-provider, subscription, MCP, storage, or host credentials.
3. Deno starts with `--no-prompt`, `--no-config`, `--no-npm`, `--no-remote`, no unstable feature flags, and explicit deny policy for read, write, network, environment, subprocess, system, FFI, and import access. The trusted launcher itself is the pinned entry module and needs no granted read path. The qualification lock freezes the complete argument and environment vector; production specifically omits `--unstable-kv` and `--unstable-worker-options`.
4. The trusted supervisor parses and transpiles submitted TypeScript before starting Deno, rejects every static or dynamic import in model source, and sends the compiled source plus digest through a bounded one-shot stdin frame. This is required because Deno loads a statically analyzable module graph without ordinary read permission.
5. A fixed trusted launcher consumes and closes the source frame, verifies its digest, and starts an explicitly separate Worker from a verified `data:` bootstrap embedded in the pinned launcher. Because the parent has no permissions, the Worker inherits none without unstable Worker options. The launcher transfers the bounded model source bytes once, then discards them. Inside the model Worker, the bootstrap captures its private RPC closure; installs an immutable narrowly typed `plane` facade backed only by that closure; replaces `process` with a frozen denial facade whose only capability is deterministic `runtime_surface_denied`; and removes or freezes `require`, `createRequire`, loader hooks, Node worker/thread and VM access, raw messaging, model-created Workers, and persistent storage surfaces. Only after lockdown does it construct a bounded `data:` module from the verified model bytes and dynamically import it. Deno's engine-level string-code-generation denial is active from process startup, so trusted module compilation remains available while indirect `eval`, all function-constructor families, and constructed imports do not. No bootstrap handle, raw port, source buffer, privileged constructor, or raw RPC method is placed in the model module's globals.
6. A dedicated inherited descriptor carries framed supervisor-to-host RPC. Generated code receives no descriptor, endpoint, token, or authoritative context fields.
7. The supervisor converts allowed Worker messages into `plane.call(operation, input)` requests. The host supplies workspace, agent, run, turn, outer tool call, budgets, catalog digest, and audit correlation.
8. Arbitrary stdout and stderr are treated only as bounded logs, never as authenticated RPC.
9. The host enforces wall time, CPU, memory, process count, inner-call count, concurrency, cumulative result, and ephemeral-disk limits and terminates the child on violation. The child storage namespace is unique per execution and destroyed with the disposable runtime-invocation container.
10. The outer disposable runtime-invocation container supplies the kernel, mount, process, and cleanup boundary. Generated code receives no direct database or Plane network route. Container lifetime is not Plane run lifetime; a later invocation may use a replacement container while the durable run continues from Plane-owned state.

## Module and seam placement

- The `compose_typescript` Plane-native composition tool is the adapter that accepts model-written TypeScript; its semantic surface contract is `plane.typescript.compose@1`.
- The TypeScript runner module owns compilation/loading, isolate lifecycle, limits, and log/result framing.
- The credential-free callback is the only seam from the runner to Plane operations.
- The Plane Operation Gateway remains the sole module that owns authorization, mutation safety, result shaping, and audit evidence.
- Deno's permission system is a sandbox adapter, not a substitute for gateway policy.

## Package and import policy

- V1 exposes standard ECMAScript/TypeScript and the generated `plane` client only.
- Static and dynamic remote imports are denied.
- `npm:`, `jsr:`, URL, local-path, and data-driven package loading are denied to model-written code.
- No install command or package cache is model-accessible.
- Any future library must be bundled into the reviewed runtime artifact and added through a manifest revision.

## Host callback authorization

The outer composition call does not pre-authorize its inner operations. Each host callback crosses the gateway independently. Authorized calls execute autonomously; unauthorized calls fail without affecting independently admitted siblings.

## Required security qualification

- Read, write, directory, `/proc`, and unrelated descriptor probes.
- DNS, HTTP, TCP, UDP, loopback, link-local, metadata, and Unix-socket probes.
- Environment, command execution, worker escalation, FFI, WASI, native addon, inspector, and signal probes.
- Static, dynamic, `npm:`, `jsr:`, URL, and local import probes.
- Persistent `localStorage`, Cache API, and Deno KV write/readback probes, including absence from a later clean isolate and zero backing-store delta.
- `data:` and `blob:` nested-Worker probes and indirect string-code-generation/import probes.
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
- Deno module loading reference: <https://docs.deno.com/runtime/fundamentals/modules/>
- Deno unstable feature flags: <https://docs.deno.com/runtime/reference/cli/unstable_flags/>
- Node.js permission model and documented constraints: <https://nodejs.org/api/permissions.html>

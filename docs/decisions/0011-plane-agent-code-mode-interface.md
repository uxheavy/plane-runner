# ADR-0011: Expose Plane Agent Code Mode through discovery and execution

## Status

Accepted; supersedes the model-facing Code Mode tool-presentation and publication portions of ADR-0007 and ADR-0010

## Date

2026-08-26

## Context

Plane Agents need broad access to Plane without loading the complete operation catalog into every model turn. Code Mode should let a model discover a small relevant API, compose several reads and writes in one sandboxed program, keep large intermediate results outside model context, and publish exactly one durable lifecycle result.

The existing design exposes transport and orchestration details to the model: `modelToolset`, `plane_execute_typescript`, `plane_publish`, generic operation identifiers, catalog search and describe steps, prepared-call references, model-authored idempotency and correlation values, gateway envelopes, and a separate submit-then-publish sequence. Live model runs have repeatedly spent their effort reproducing this protocol instead of completing Plane work.

The following existing decisions remain authoritative:

- ADR-0001: one shared Plane Operation Gateway, host-held credentials, and restricted generated-code execution.
- ADR-0002: live Plane authorization decides every operation; Code Mode adds no second permission system.
- ADR-0006: Plane owns assignment, run, outcome, conversation, and terminal product state.
- ADR-0010: the runtime is a separate service behind Plane's versioned runtime contract, with Plane-authoritative events, budgets, recovery, and reconciliation.

This ADR changes only the model-facing Code Mode contract and the host facade supporting it.

## Decision

Expose exactly two Code Mode tools to the model:

1. `Plane:discover` reveals a bounded, task-relevant TypeScript declaration slice.
2. `Plane:execute` runs one bounded TypeScript function body against the current assignment.

`Plane:` is the MCP server namespace. The local tool identifiers are `discover` and `execute`; they do not repeat a `plane_` prefix.

Generated code receives two frozen ambient values:

- `task`, containing the assignment objective, acceptance criteria, and typed target.
- `plane`, containing only the discovered resource methods and the terminal `finish` method.

The `plane` namespace remains inside generated code because it identifies the host-owned Plane capability boundary and avoids magical or colliding global resource names.

### Discovery contract

`Plane:discover` has one purpose: recover a capability missing from the current task declarations. It does not execute an operation or imply authorization.

Description:

> Find Plane Agent SDK methods and TypeScript types for one intended workflow. Use when the current task declarations do not contain a method needed to complete the assignment. Describe the whole workflow, not an API name. Returns one bounded replacement declaration slice. Discovery does not authorize execution.

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["query"],
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "maxLength": 500,
      "description": "The complete intended workflow, for example: list urgent unassigned work items, assign one member, then finish."
    }
  }
}
```

Result:

```ts
type DiscoverResponse = { status: "ok"; declarations: string } | { status: "error"; error: ToolError };
```

The declaration slice:

- contains at most eight matched methods plus only their transitive types and constraints;
- is at most 16 KiB of canonical UTF-8 text;
- is rejected with `narrow_query` guidance rather than silently truncated;
- replaces the previous discovery slot instead of accumulating in model context; and
- is exactly the declaration slice used to type-check the next execution.

Plane prepares the initial task kit before the first model turn from the stable base contract, immutable assignment, smallest likely method closure, transitive types, and one relevant example. Task kits and discovered slices are deterministic, trust-ranked, internally digest-bound, and size-capped. User or external content remains typed data and cannot declare capabilities or alter policy.

### Execution contract

`Plane:execute` has one purpose: compose Plane resource operations in the restricted runtime.

Description:

> Run one bounded TypeScript function body against the current Plane assignment. `plane` and `task` are injected and frozen. Use ordinary typed resource methods; do not import, export, construct a client, or return large data. Return compact JSON for further reasoning, or call `await plane.finish(...)` exactly once to complete, wait for input, or block. Plane owns identity, authorization, pagination, idempotency, receipts, and recovery.

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["code"],
  "properties": {
    "code": {
      "type": "string",
      "minLength": 1,
      "maxLength": 8192,
      "description": "TypeScript statements executed as an async function body with ambient plane and task objects. Imports and exports are forbidden."
    }
  }
}
```

Model-visible result:

```ts
type ExecuteResponse =
  | { status: "returned"; value: JsonValue }
  | { status: "completed" }
  | { status: "waiting_for_input" }
  | { status: "blocked" }
  | { status: "error"; error: ToolError };

type ToolError = Readonly<{
  code: string;
  message: string;
  resolution: string;
  retryable: boolean;
  recovery: "fix_code" | "discover_capability" | "narrow_query" | "retry_same_call" | "wait" | "reconcile" | "none";
  field?: string;
  expected?: string;
  example?: JsonValue;
}>;
```

An ordinary completion must return canonical JSON. The returned value is capped at 8 KiB and exists only for further model reasoning; it does not complete or publish the assignment. Falling through without a JSON return or `plane.finish(...)` is an actionable error.

Full receipts, traces, call references, usage records, and reconciliation state remain in Plane's audit and run-inspection surfaces. They never enter the generated-code API or model-visible tool result.

### Generated-code interface

The initial Code Mode language is TypeScript. Plane wraps the submitted statements in an async function, so generated code contains no module, import, export, client-construction, credential, base-URL, or callback boilerplate.

The stable base declarations include:

```ts
type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | readonly JsonValue[] | { readonly [key: string]: JsonValue };

type PlaneRef<Kind extends string> = string & {
  readonly __planeKind: Kind;
};

declare const task: Readonly<{
  target: PlaneRef<string>;
  objective: string;
  acceptanceCriteria: readonly string[];
}>;

declare const plane: Readonly<{
  finish(input: FinishInput): Promise<never>;
  // Only task-relevant resource namespaces are declared here.
}>;

type FinishInput =
  | {
      kind: "completed";
      summary: string;
      content?: string;
      artifacts?: readonly PlaneRef<"artifact">[];
      evidence?: readonly PlaneRef<string>[];
    }
  | {
      kind: "waiting_for_input";
      question: string;
      context?: JsonValue;
    }
  | {
      kind: "blocked";
      reason: string;
      evidence?: readonly PlaneRef<string>[];
    };
```

Discovered resource APIs follow Plane's official SDK vocabulary, such as `plane.workItems.retrieve(...)` and `plane.workItems.update(...)`, but form a host-bound Agent SDK rather than a credential-taking public client. Methods accept typed references or named inputs and return typed domain values, never gateway receipts. Paginated reads expose lazy `AsyncIterable` values so filtering, joining, and aggregation remain inside the sandbox. Each fetched page is independently authorized, budgeted, cancellable, bounded, and audited by the host.

TypeScript is a first-release scope decision, not a permanent platform constraint. It reuses Plane's Node SDK vocabulary, generated types, and existing restricted Node child without adding another runtime or security surface. Python should be added only if representative evaluations show a material task-success advantage that justifies a second language contract and sandbox.

### Host and sandbox boundary

Keep the existing restricted Node child and Operation Gateway. Replace the generic model-authored callback protocol with a deeply frozen typed SDK facade.

For every generated SDK call, the trusted host:

1. validates the persisted actor, workspace, run, and invocation binding;
2. validates input against the canonical Operation Gateway descriptor;
3. evaluates live Plane authorization;
4. derives idempotency, correlation, and call identity;
5. reserves and enforces budgets;
6. dispatches through the Operation Gateway;
7. stores complete receipts and audit evidence;
8. projects only the typed domain result into the child; and
9. reconciles reserved and actual usage.

The canonical Operation Gateway descriptor registry is authoritative for method existence, schema, scope, result bounds, and mutation recovery. MCP action declarations and public SDK types are donor and conformance inputs, not independent authorities.

Generated code receives no credentials, environment, network, filesystem, process, worker, dynamic import, native addon, dynamic string-code generation, or direct database access. Existing source, protocol, call, page, byte, duration, CPU, memory, process, output, cancellation, and unconditional child-termination limits remain enforced.

Mutation outcomes remain explicit below the model boundary:

- `not_dispatched`: no effect began; the same call may be retried safely.
- `rejected`: Plane proved no effect; the request must be corrected or stopped.
- `applied`: return or replay the persisted typed domain result.
- `outcome_unknown`: stop execution and require Plane reconciliation; never issue a replacement mutation.

Immediate source correction is allowed only when Plane proves that no mutation or terminal call began. Agent-facing errors must state what failed, how to recover, and whether the same call is safe to retry.

### Terminal and publication semantics

`plane.finish(...)` is the only generated-code lifecycle exit. It is explicit, authorized, and non-returning.

- `completed` performs one semantic Plane application operation that creates the durable outcome submission and its visible Plane event together while preserving them as distinct internal records.
- `waiting_for_input` creates one visible question, pauses the run, and ends the current invocation.
- `blocked` creates one visible blocker and records the blocked terminal state.

The first applied finish wins. The host immediately stops the child; later output, callbacks, exceptions, or runtime exits cannot relabel the authoritative Plane event. Plane automatically correlates applied operation receipts with the terminal result.

If generated code or the model turn ends without an applied finish, Plane records one visible `MISSING_TERMINAL_PUBLICATION` failure. Raw model final text remains technical transcript evidence and never becomes a product message implicitly. This preserves ADR-0006's explicit-publication rule without requiring the model to leave Code Mode and call a second publication tool.

### Removed model-facing protocol

The Code Mode path no longer exposes:

- `modelToolset`, `standard`, or `code_mode_only` routing vocabulary;
- `plane_operation`, `plane_execute_typescript`, or `plane_publish`;
- `catalog.search` followed by `catalog.describe` choreography;
- generic operation identifiers or MCP action strings;
- `preparedCallRef` or prepared-call normalization and continuation states;
- model-authored workspace, actor, run, outcome, idempotency, correlation, or gateway metadata;
- generic host callbacks and gateway envelopes;
- raw receipts, trace references, call references, or spill handles; or
- separate outcome submission followed by publication.

These details may continue to exist below the trusted host boundary where required for compatibility, audit, or migration, but they are not part of the new model contract.

## Alternatives considered

### Keep the existing Code Mode protocol and improve prompting

- Benefit: smallest implementation change.
- Cost: preserves the transport choreography and ambiguous terminal route that live models have failed to reproduce reliably.
- Rejected: the failure is in the interface boundary, not missing prose.

### Expose all Plane operations as eager tools

- Benefit: removes discovery.
- Cost: consumes substantial context and creates overlapping tool-selection choices.
- Rejected: a small task kit plus explicit discovery preserves coverage with less model burden.

### Expose one generic operation tool inside generated code

- Benefit: very small host facade.
- Cost: makes the model author operation identifiers and transport-shaped inputs, loses useful type checking, and leaks gateway semantics.
- Rejected: ordinary resource methods are a simpler model interface.

### Use only `Plane:execute` and perform discovery inside generated code

- Benefit: one model-visible tool.
- Cost: the model must generate code before it knows the callable interface, or fall back to dynamic untyped invocation.
- Rejected: discovery and execution are distinct, non-overlapping model decisions.

### Inject resource namespaces as globals

- Benefit: removes the `plane.` qualifier from generated code.
- Cost: creates magical globals, collision risk, and no visible boundary between local code and host capabilities.
- Rejected: the short `plane` namespace carries useful contract meaning.

### Use Python as the only initial language

- Benefit: concise scripting and strong data-processing ergonomics.
- Cost: adds a second runtime and schema/type projection path while the existing sandbox and official resource vocabulary are Node-oriented.
- Rejected for the first release: TypeScript provides the smaller implementation and security surface. Python remains an evidence-driven extension.

### Preserve separate submit and publish operations

- Benefit: keeps outcome creation and conversation projection independently callable.
- Cost: permits a submitted outcome with no visible publication and forces the model to coordinate a second terminal tool after successful execution.
- Rejected: one explicit terminal method can create both distinct records through one authorized application operation.

## Consequences

- The model chooses between only discovery and execution, with non-overlapping activation conditions.
- The generated program reads like ordinary Plane SDK code rather than a transport adapter.
- Large intermediate Plane data stays inside the restricted child; only bounded JSON or terminal status reaches model context.
- Plane retains live authorization, host-held identity and credentials, gateway auditing, idempotency, budgets, cancellation, and reconciliation.
- Existing Code Mode routing, prepared-call, generic callback, and publish compatibility code becomes migration debt and should be deleted after callers move to this contract.
- The task-kit generator, declaration projection, typed SDK facade, actionable error mapping, and terminal application operation become compatibility-critical interfaces requiring contract tests.
- This ADR defines the target contract; implementation and live acceptance require a separately authorized change and evidence plan.

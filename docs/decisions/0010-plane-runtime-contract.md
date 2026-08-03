# ADR-0010: Use one versioned Plane runtime contract

## Status

Accepted

## Date

2026-08-03

## Context

ADR-0003 through ADR-0007 establish a Plane-native product backed by a hidden Hermes kernel. The seam is still expensive to reverse. Hermes's current `AIAgent` constructor and surrounding modules expose provider, profile-directory, chat-platform, session, callback, filesystem, and process-global details. Allowing Plane callers to depend on that surface would turn donor implementation into product contract.

Plane also needs a run to survive kernel process loss or span several sessions without making Hermes session persistence authoritative. Agent execution is a separate service co-located with Plane, not an in-process Plane API or library dependency.

## Decision

Introduce one Plane-owned, versioned logical runtime contract implemented by the separate agent-runtime service and a deterministic test adapter.

Plane product callers use intent-level agent commands. Plane persists control state and dispatches runtime invocations across a durable cross-process seam. The exact queue or RPC transport remains an implementation choice and must not change the domain contract. Internal Plane Agent calls carry a bound dedicated Agent identity; external MCP calls carry the authenticated human or integration caller and do not masquerade as an internal Agent.

Inside the runtime service, only the narrow runtime adapter crosses into Hermes:

```python
exit = await plane_runtime.execute(
    run=run_snapshot,
    invocation=invocation_envelope,
    host=bound_plane_host,
    emit=validated_event_sink,
    cancellation=run_cancellation,
)
```

`plane_runtime.execute` is the logical adapter interface inside the runtime service, not a Python import used by Plane API modules. No Plane product module and no other runtime-service module imports `AIAgent`, Hermes profile loaders, gateways, session databases, registry globals, cron, delegation, workflow-definition state, or chat-platform types.

### Runtime hierarchy

- `AssignmentContract` is the durable commission to produce an outcome.
- `RunAttempt` is one Plane-owned execution attempt with a frozen snapshot.
- `RuntimeInvocation` is one kernel dispatch within a run.
- `OutcomeSubmission` is the visible result submitted for human review.

A run may wait for hours and span several runtime invocations, Hermes sessions, leases, containers, processes, or restarts. A safe continuation after human input or recoverable process failure may create a new invocation within the same run. An `outcome_unknown` operation is reconciled or escalated and is never blindly replayed. A deliberate fresh execution after terminal run failure or cancellation, or after human-requested revision, creates a new run.

### Run snapshot and invocation envelope

Plane persists one immutable `RunSnapshot` when the run is created:

```ts
type RunSnapshot = Readonly<{
  protocol: "plane.agent-runtime/v1";
  runId: string;
  assignment: {
    version: string;
    targetRef: string;
    objective: string;
    acceptanceCriteria: readonly string[];
  };
  actorRef: string;
  profileVersion: string;
  behavioralPrompt: string;
  context: readonly VersionedContextRef[];
  toolPresentation: {
    eagerOperations: readonly OperationDescriptor[];
    catalogDigest: string;
  };
  model: RuntimeModelRoute;
  totalBudgetPolicy: RuntimeBudgetPolicy;
  contractDigests: ContractDigests;
}>;
```

Each kernel dispatch receives a separate immutable `InvocationEnvelope`:

```ts
type InvocationEnvelope = Readonly<{
  protocol: "plane.agent-runtime/v1";
  invocationId: string;
  runId: string;
  runSnapshotDigest: string;
  trigger:
    | { kind: "initial" }
    | { kind: "human_input"; eventRef: string }
    | { kind: "recoverable_restart"; eventRef: string }
    | { kind: "continuation"; eventRef: string };
  newContextEventRefs: readonly string[];
  checkpointRef?: string;
  remainingBudget: RuntimeBudget;
  lease: RuntimeLease;
  causationRef: string;
  cancellationRef: string;
}>;
```

A human answer is a durable Plane event referenced by the invocation envelope. It does not mutate the run snapshot or live only in a Hermes session. A checkpoint reference is accepted only when the host has proven the continuation safe.

Run budgets accumulate across invocations. The trusted host derives `remainingBudget` from durable usage and the run's total budget policy; a new invocation cannot reset it.

Neither contract contains a Plane credential, database handle, permission decision, mutable profile, gateway endpoint, transport headers, Hermes configuration path, or provider client. Tool presentation is not authorization. The trusted host binds actor, workspace, credential, run, catalog, idempotency, budgets, and audit correlation when calling the Plane Operation Gateway.

### Events and exit

The kernel emits ordered, bounded, duplicate-safe observations:

```ts
type RuntimeEvent = Readonly<{
  protocol: "plane.agent-runtime/v1";
  runId: string;
  invocationId: string;
  sequence: number;
  eventId: string;
  body:
    | ProgressObserved
    | ConversationPublicationObserved
    | InputRequestObserved
    | ArtifactObserved
    | UsageObserved
    | OutcomeSubmissionObserved
    | FailureObserved
    | BlockerObserved;
}>;

type RuntimeExit = Readonly<{
  kind: "completed" | "waiting_for_input" | "failed" | "blocked" | "cancelled";
  finalSequence: number;
  failure?: RuntimeFailure;
}>;
```

The runtime adapter validates events before transmission as defense in depth. Plane validates every cross-process envelope again at ingress and is authoritative for every product-state transition. Until Plane verifies trusted-host binding, actor authority, run and invocation identity, schema, sequence, idempotency, limits, and a legal lifecycle transition, every event is an untrusted observation.

Product-visible mutations do not occur merely because an event arrived. An explicit agent publication action calls a semantic Plane operation through the trusted `RuntimeHost`; the operation crosses the authorized, idempotent, audited Plane Operation Gateway and returns a Plane receipt. `ConversationPublicationObserved`, `InputRequestObserved`, `ArtifactObserved`, and `OutcomeSubmissionObserved` carry or correlate the resulting message, artifact, submission, operation-attempt, and audit references. Plane ingress verifies those receipts before projecting state. Raw model final text remains transcript/run-inspection evidence and is not automatically a conversation message.

If some lifecycle proposals use a dedicated host event-ingress endpoint rather than the general operation endpoint, that endpoint is trusted-host bound and reuses equivalent Plane authentication, authorization, idempotency, application-service, transition, and audit rules. It is not a parallel path around the Operation Gateway invariants.

Every terminal invocation must map to one visible Plane terminal product event: outcome submission, failure, blocker, or cancellation. A `waiting_for_input` exit is a visible non-terminal question that pauses the run and may start a later invocation. This is a Plane lifecycle invariant, not a promise the kernel can always fulfill. If the lease expires or the container dies before a terminal observation arrives, Plane or its trusted supervisor reconciles the authoritative cause and records exactly one visible failure, blocker, or cancellation through the same application-service and audit rules. `RuntimeExit.completed` is kernel evidence, not authority to submit or accept an outcome.

### Isolation and compatibility

V1 runs one active invocation per isolated process or container until Hermes process-global profile and registry state is removed or proven safe for multiplexing.

The execution lease and container belong to the runtime invocation, not the durable run. They may be released while waiting and recreated from Plane-owned snapshots, events, permitted checkpoints, and remaining budget. No container lifetime is part of the Plane run contract.

G0 accepts the logical type names, semantics, event variants, trust/publication/dispatch constraints, and the compatibility rules for `RunSnapshot`, `InvocationEnvelope`, `RuntimeEvent`, and `RuntimeExit`. At G1, the exact JSON Schema bytes and their digests are generated and frozen before the implementation lanes that consume those generated schemas begin. Contract fixtures cover snapshot immutability, accumulated budgets, human-input references, safe checkpoints, forged binding, duplicate and out-of-order events, receipt verification, illegal transitions, bounded payloads and artifacts, lease/container death, waiting for input, explicit publication, completion, and incompatible versions.

## Alternatives considered

### Expose `AIAgent` directly to Plane

- Benefit: minimal adapter code.
- Cost: leaks Hermes product, provider, session, and global-state assumptions into Plane.
- Rejected: it makes the donor implementation the public interface.

### Import the runtime adapter into the Plane API process

- Benefit: avoids a cross-process dispatch mechanism.
- Cost: couples Plane request handling, credentials, failure containment, and scaling to Hermes process state.
- Rejected: execution remains a separate co-located service behind durable dispatch.

### Make Hermes sessions the Plane run record

- Benefit: reuses existing transcript persistence.
- Cost: creates two authorities and cannot represent a run spanning sessions or restarts.
- Rejected: Plane owns durable run, conversation, and history state.

### Use a multi-method start, stream, persist, and finalize protocol

- Benefit: exposes every lifecycle phase explicitly.
- Cost: callers must coordinate ordering, retries, and partial failure across a shallow interface.
- Rejected: one deep execution interface hides the kernel lifecycle.

### Import Buzz ACP as the runtime protocol

- Benefit: reuses a conversation-oriented harness.
- Cost: introduces a third production owner and vocabulary without an existing Plane integration.
- Rejected: Buzz remains a UX and ACP reference donor.

## Consequences

- Plane and Hermes share one small compatibility artifact rather than internal module types.
- Plane and the runtime service communicate across a durable cross-process seam whose transport can change without changing agent-domain state.
- Plane owns profile compilation, role governance, run state, publication, conversation, artifacts, evaluator review, and recovery policy.
- Hermes owns the hidden inner execution mechanisms behind its adapter.
- A deterministic adapter can test Plane lifecycle without a model or Hermes process.
- G0 accepts the snapshot/envelope logical semantics, event taxonomy, publication mapping, cumulative budgets, payload limits, restart rules, and trust/publication/dispatch constraints. G1 generates and freezes the exact JSON Schema bytes before the implementation lanes that consume those generated schemas begin.

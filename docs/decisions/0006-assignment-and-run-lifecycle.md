# ADR-0006: Plane owns assignment and run lifecycle

## Status

Accepted

## Date

2026-08-03

## Context

The native interaction begins when a person, an approved schedule, or the dedicated delegator creates a normal Plane assignment and ends when the submitted result is accepted or returned for revision. A model session alone cannot represent this lifecycle: runs may pause for input, fail, block, retry, produce artifacts, or submit a result that still requires evaluator and human review.

Plane must remain authoritative even when the execution kernel restarts or changes.

## Decision

Preserve five independently meaningful Plane records and lifecycles:

- An **agent actor** is the durable Plane principal and assignee.
- A **profile version** is the immutable behavioral configuration resolved for execution.
- An **assignment contract** is the durable commission to produce an outcome: target, objective, acceptance criteria and context, assignee, and review state.
- A **run attempt** is one execution attempt against an assignment, with a frozen profile, context, tool-presentation, model, and runtime snapshot.
- An **outcome submission** is the result produced by a run: summary, artifacts, and supporting evidence that a human accepts or returns for revision.

These records may initially share one deep Plane module, but they are not one aggregate with one lifecycle.

The minimum assignment flow is assigned, active, submitted, evaluator reviewed, then accepted or revision requested by a human. A run separately records queued, running, waiting for input, succeeded, failed, blocked, or cancelled execution state. Approved schedules and the dedicated delegator create ordinary assignments and runs; neither introduces a separate workflow-definition state. Exact persistence names may follow existing Plane conventions, but the assignment, run, outcome, evaluator review, and human decision concepts remain distinct.

A Plane run may wait for extended periods and span multiple runtime invocations, Hermes sessions, leases, containers, processes, or restarts. A runtime invocation is one kernel dispatch within the durable run. The run keeps an immutable resolved snapshot; each invocation references that snapshot plus new Plane-owned input/context events, safe continuation state, and remaining cumulative budget. Execution leases and containers belong to invocations and may be recreated. Answering a question or recovering from an invocation/process failure may create a new invocation in the same run when continuation is safe. An `outcome_unknown` operation is reconciled or escalated and is never blindly replayed, whether in the same or a new run. A deliberate fresh execution after terminal run failure or cancellation, or after human-requested revision, creates a new run.

Plane records progress, questions, artifacts, submissions, evaluator review, human decision, conversation, and run history. Hermes executes runtime invocations and reports events, transcripts, and checkpoints; it does not own authoritative assignment, run, outcome, conversation, or history state.

Kernel output is not published implicitly. A model final text or Hermes transcript entry becomes visible only through an explicit authorized Plane product mutation. Every terminal runtime invocation maps to exactly one visible terminal event: an outcome submission, failure, blocker, or cancellation. A waiting-for-input question is a visible non-terminal pause and may lead to a later invocation in the same run. If invocation infrastructure dies before publishing, Plane derives a failure, blocker, or cancellation from authoritative lease state and records the cause. A run cannot be considered product-complete merely because the kernel stopped successfully.

Normal conversation contains intentional messages, progress, questions, and submissions. Technical model/tool transcript and detailed operation receipts remain in the secondary run-inspection surface. Compact activity receipts may summarize relevant changes without dumping every tool call or field mutation into chat.

## Alternatives considered

### Treat a Hermes session as the run or assignment

- Benefit: fewer records.
- Cost: conflates product state, execution attempt, transcript, and retry behavior.
- Rejected: an assignment can span multiple attempts and reviews, while a run can span multiple kernel sessions.

### Use only work-item status

- Benefit: reuses an existing Plane field.
- Cost: agent execution and human delivery state would be overloaded into project workflow states.
- Rejected: work-item workflow and agent-run execution answer different questions.

### Let Hermes own run state

- Benefit: keeps execution data near the executor.
- Cost: Plane cannot reliably render, authorize, audit, or recover the native experience.
- Rejected: Plane is the system of record for its teammate.

## Consequences

- One assignment may have several runs, but only one authoritative current review state.
- One run may have several runtime invocations without making Hermes session identity durable product state.
- Outcome submissions retain their producing run, artifacts, evidence, and review decision.
- Every outcome enters evaluator review before a human can accept or return it; evaluator feedback is advisory to the human's final decision.
- The run contract requires a visible terminal Plane event, preventing an internally completed kernel turn from publishing nothing useful to humans.
- Product conversation and technical run inspection remain distinct projections of correlated evidence.
- Retries and revisions preserve prior run evidence instead of rewriting history.
- Plane needs a versioned event contract between its run service and the Hermes kernel.
- Human outcome acceptance is distinct from per-operation authorization in ADR-0002.

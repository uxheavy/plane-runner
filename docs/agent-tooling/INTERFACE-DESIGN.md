# Plane Operation Gateway Interface Design

## Status

The core deep-hybrid boundary was accepted by the user on 2026-07-29. Exact eager tools, operation scope, preflight groups, limits, and compatibility rows remain subject to release-manifest approval. This decision does not authorize implementation.

## Design constraints

- Plane authorization remains the permission oracle for every operation.
- Credentials, workspace identity, agent identity, and run identity are trusted host context.
- Generated TypeScript receives none of those credentials.
- Plane-native tools hosted by the Hermes kernel, TypeScript composition, and external MCP compatibility converge on one gateway module.
- The v1 interface should keep common calls obvious without projecting 177 MCP tools into every model prompt.
- Idempotency, bounded results, and audit evidence apply uniformly below all adapters.

## Design A: one deep operation seam

The gateway exposes one primary interface:

```ts
interface PlaneOperationGateway {
  execute(operation: OperationRef, input: unknown): Promise<OperationResult>;
}
```

The caller receives a request-bound gateway instance. It cannot supply credentials, workspace identity, agent identity, or audit identity. `OperationRef` resolves against a versioned catalog. Expected denial, conflict, bounded-result, and indeterminate-outcome states are typed values rather than transport exceptions.

This is the smallest and deepest design. Authorization, idempotency, result control, and audit behavior stay local to one module. Native Hermes, Code Mode, and MCP are adapters at the seam. Its weakness is discoverability: callers need a separate way to find operations and learn schemas.

## Design B: common-case semantic facade

The gateway directly exposes named methods corresponding to the proposed eager surface:

```ts
interface PlaneWorkspaceTools {
  searchWorkItems(input: SearchWorkItemsInput): Promise<SearchWorkItemsResult>;
  getWorkItem(input: GetWorkItemInput): Promise<GetWorkItemResult>;
  createWorkItem(input: CreateWorkItemInput): Promise<CreateWorkItemResult>;
  updateWorkItem(input: UpdateWorkItemInput): Promise<UpdateWorkItemResult>;
  addComment(input: AddCommentInput): Promise<AddCommentResult>;
}
```

Natural Plane references and semantic inputs make the common path easy for models. A method can hide a multi-call public-API composition, such as creating a work item and assigning its cycle. The tradeoff is a wider gateway interface and a stronger long-term compatibility obligation. It also does not naturally cover the full catalog without adding a second generic interface.

## Design C: durable command state machine

The gateway exposes begin and reconcile commands with durable attempt and evidence identifiers:

```ts
interface PlaneCommandMachine {
  advance(command: GatewayCommand): Promise<GatewayTransition>;
}
```

This makes mutation reconciliation, audit receipts, and restart behavior explicit. It is strongest for correctness and operations. It is also too much protocol for normal callers: every native tool and generated program would need to understand gateway lifecycle states that should remain implementation details.

## Design D: catalog, batch, and plan facade

The gateway exposes catalog search and description, single calls, batches, and an explicit dependency graph:

```ts
interface PlaneProgramGateway {
  search(query: string): Promise<CatalogMatch[]>;
  describe(operation: OperationRef): Promise<OperationDescriptor>;
  call(operation: OperationRef, input: unknown): Promise<OperationResult>;
  batch(group: OperationGroup): Promise<GroupResult>;
  preflight(plan: OperationPlan): Promise<PreflightResult>;
  execute(plan: ValidatedOperationPlan): Promise<PlanResult>;
}
```

This supports progressive discovery, explicit concurrency, and group preflight. It is the most flexible design and the closest to a workflow engine. It creates the largest v1 surface, duplicates responsibilities already present in Hermes, and makes plan freshness and partial failure much harder to specify.

## Comparison

Design A has the best interface depth and the fewest seams, but needs a discovery companion. Design B gives Hermes the best common-case ergonomics, but should be an adapter rather than the core module interface. Design C provides the right internal execution semantics, but leaks too much lifecycle protocol if exposed. Design D is powerful, but brings workflow-engine complexity before evidence shows that v1 needs it.

## Accepted v1 core boundary

Use a hybrid in which each layer has one job:

1. The core Plane Operation Gateway module has a deep request-bound `execute` interface.
2. A separate read-only catalog module exposes `search` and `describe` because discovery is a distinct interface with different caching and testing needs.
3. The gateway internally implements a durable command state machine for authorization, idempotency, reconciliation, bounded results, and append-only audit evidence.
4. The fork exposes a Plane-native runtime profile whose model-facing tools are designed from Plane workflows rather than inherited from `hermes-cli`.
5. Common Plane-domain tools remain thin common-case adapters. Their exact names and eager boundary are pending the Plane-native catalog decision.
6. Progressive discovery and TypeScript composition remain required, but the generic `docs`, `search`, and `execute` names and the earlier `plane_docs`, `plane_search`, and `plane_execute` surface are retired.
7. Generated TypeScript receives a credential-free operation callback plus catalog types. It does not receive the internal lifecycle protocol.
8. V1 does not expose a general graph-planning DSL. The mandatory coordinated release-plan write is one curated semantic catalog operation.
9. Semantic multi-step compositions live in the operation catalog and gateway implementation, not independently inside native, Code Mode, or MCP adapters.
10. The 177-tool Python MCP surface is a compatibility adapter. Each MCP contract maps to gateway operations, retained local behavior, or an explicitly approved deprecation disposition.

This keeps the caller interface simple while preserving one enforcement locality. It also lets native tools be ergonomic without turning their small eager set into a security boundary.

## Proposed catalog descriptor

Each catalog entry should contain one idea per field:

- stable operation ID and major version;
- purpose and model-facing description;
- input and output schemas;
- read or mutation classification;
- idempotency and reconciliation policy;
- authorization mapping to current Plane behavior;
- result and artifact limits;
- audit redaction policy;
- public API composition or retained local behavior;
- native-tool and external-MCP adapter mappings;
- compatibility status and lifecycle metadata.

OpenAPI supplies transport facts where it is accurate. The curated semantic overlay owns behavioral facts that OpenAPI cannot express, including authorization mapping, idempotency, bounded-result policy, and semantic compositions.

## North Star

Choose the least custom code that satisfies the approved production and security gates. Reuse Plane and Hermes behavior at their natural seams, generate schemas and adapters from one catalog, and add a new protocol only when a verified requirement cannot be met by the simpler boundary.

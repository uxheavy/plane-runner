# Plane Operation Gateway Wire Contract

## Status

The use of Plane's existing JSON HTTP API service as the v1 gateway adapter was accepted by the user on 2026-07-29. The exact wire schemas below are P1 generation inputs under the controlling logical contract; they do not choose the separate runtime service's physical durable queue/RPC transport and do not authorize implementation.

## Boundary

The deep `PlaneOperationGateway.execute()` module remains the core interface inside Plane. One thin Django REST adapter exposes that interface to trusted hosts in other processes.

V1 does not add an internal MCP hop, gRPC service, message broker, or separate gateway deployment.

## Endpoints

### Catalog discovery

```text
GET /api/v1/agent-operations/catalog/
GET /api/v1/agent-operations/catalog/{operation_id}/
```

The list endpoint supports bounded text search, tags, read-or-mutation classification, cursor, and limit. The detail endpoint returns one exact major-version contract. Responses carry a catalog digest and HTTP `ETag`.

Catalog visibility is identical across authenticated Plane identities. Visibility does not imply execution permission.

### Operation execution

```text
POST /api/v1/workspaces/{workspace_slug}/agent-operations/execute/
```

The endpoint accepts media type `application/vnd.plane.agent-operation+json;version=1`.

Proposed request:

```json
{
  "operation": "plane.work_items.get@1",
  "catalog_digest": "sha256:...",
  "input": {},
  "client_context": {
    "client": "hermes",
    "run_id": "...",
    "turn_id": "...",
    "outer_call_id": "...",
    "inner_call_id": "..."
  }
}
```

`Idempotency-Key` is required for mutations and rejected on reads. The trusted adapter creates it; model-written TypeScript cannot provide it.

`client_context` is correlation metadata, not identity or permission. Plane binds it to the authenticated actor, workspace, server-generated attempt ID, and audit record. Generated code cannot set or override the object.

### Temporary artifact reads

```text
GET /api/v1/workspaces/{workspace_slug}/agent-artifacts/{artifact_ref}/?cursor={cursor}&limit={limit}
```

The reference and cursor are opaque authenticated ASCII values. `artifact_ref` and `infrastructure_attempt_ref` are each at most 256 bytes, and each cursor is at most 512 bytes. `limit` counts decoded authoritative bytes, defaults to 23,000, and is restricted to 1 through 23,000. A success returns artifact reference, byte offset, Base64 bytes, decoded byte length, chunk SHA-256, infrastructure attempt reference, and an opaque next cursor or terminal `null`. Decoded chunks are at most 23,000 bytes, and the complete canonical response, including Base64 expansion and envelope fields, is at most 32 KiB; the server shortens a chunk below the requested limit if necessary to preserve that bound. The cursor is bound to artifact, actor, workspace, run, expiry, and prior offset.

The exact read result is:

```ts
type ArtifactReadResult = {
  artifact_ref: string;
  offset: number;
  byte_length: number;
  bytes_base64: string;
  chunk_sha256: string;
  next_cursor: string | null;
  infrastructure_attempt_ref: string;
};

type ArtifactReadFailure =
  | {
      error: { code: "artifact_not_found"; message: "The requested artifact was not found."; retry: "never" };
      infrastructure_attempt_ref: string;
    }
  | {
      error: { code: "invalid_artifact_cursor"; message: "The artifact cursor is invalid."; retry: "never" };
      infrastructure_attempt_ref: string;
    }
  | {
      error: { code: "artifact_expired"; message: "The artifact has expired."; retry: "never" };
      infrastructure_attempt_ref: string;
    };
```

Binding failure returns `403 artifact_not_found`; stale or mismatched cursor returns `409 invalid_artifact_cursor`; expiry returns `410 artifact_expired`. The response schema rejects unknown fields. All three failures expose no artifact bytes, digest, size, actor, workspace, run, cursor payload, or expiry timestamp. Reads consume callback call and output budgets and produce exactly one infrastructure intent/outcome pair joined by `infrastructure_attempt_ref`. Generated TypeScript can reach this endpoint only through the credential-free host method `plane.readArtifact`; it receives no URL, workspace slug, credential, or cursor signing material.

## Authentication and binding

- The wire reuses Plane's current `X-Api-Key` and OAuth bearer authentication.
- Plane derives the acting identity from the authenticated credential.
- The workspace path is authorized against that identity on every execution.
- Hermes holds one revocable Plane agent credential in trusted host state.
- The official MCP server continues using its existing authenticated session credential.
- Generated TypeScript receives no credential, endpoint, HTTP headers, workspace slug, or authoritative correlation fields.
- Direct database access is not part of the adapter.

## Result envelope

Every authenticated actor-bound gateway result contains the exact operation, catalog digest, server attempt ID, audit reference, and one state. The edge-authentication exception below is not a `GatewayWireResult`.

```ts
type GatewayWireResult = {
  [O in CatalogOperationId]: GatewayWireResultFor<O>;
}[CatalogOperationId];

type GatewayWireResultFor<O extends CatalogOperationId> =
  | {
      state: "succeeded";
      operation: O;
      catalog_digest: string;
      attempt_id: string;
      audit_ref: string;
      replayed: boolean;
      output: { kind: "inline"; value: CatalogOperationOutputs[O] } | ({ kind: "artifact" } & ArtifactDescriptor);
    }
  | ({
      operation: O;
      catalog_digest: string;
      attempt_id: string;
      audit_ref: string;
      replayed: boolean;
    } & CatalogOperationFailureVariants[O]);

type ArtifactDescriptor = {
  preview: {
    encoding: "utf-8-prefix";
    byte_length: number;
    value: string;
  };
  preview_limit_bytes: 8192 | 2048;
  artifact_ref: string;
  authoritative_byte_length: number;
  authoritative_sha256: string;
  expires_at: string;
};

type DependencyUnavailableError = {
  code: "dependency_unavailable";
  message: "A required Plane dependency is unavailable.";
  retry: "same_invocation";
  details: { retry_after_ms: number };
};
```

`CatalogOperationOutputs` maps each exact operation ID to its strict successful inline projection. `CatalogOperationFailureVariants` maps each operation ID to a union of complete `{state,error}` variants, so both the permitted error codes and their fixed state remain correlated with the operation; it has no open-string or independently selectable state fallback. Unknown fields, states, and codes are rejected. `DependencyUnavailableError` shows the exact safety-v1 dependency detail shape. Other operation-specific errors may expose only bounded shapes frozen by their approved versioned contracts, such as authorized ambiguity candidates or validation field paths and safe corrective hints; there is no generic `details` object.

`replayed` is present on every authenticated gateway result. It is `true` only when returning a previously recorded terminal compatible success or deterministic rejection; it is always `false` for a newly executed result, `failed`, or `outcome_unknown`.

## HTTP behavior

- `200` returns a success, replay, deterministic rejection, or reconciled result.
- `400` means malformed wire input.
- `401` means invalid or revoked authentication.
- `403` means a non-leaking authorization denial.
- `409` means idempotency conflict, stale contract, or another deterministic conflict.
- `413` means an input or result policy limit was exceeded.
- `429` carries bounded retry guidance.
- `5xx` is reserved for dependency or internal failure; mutation retry behavior still comes from the structured envelope and invocation record.

Callers never infer mutation retry safety from HTTP status alone.

Authentication rejection happens before an actor-bound gateway result exists. HTTP 401 returns only `{error:{code:"authentication_failed",message:"Authentication failed.",retry:"never"},edge_attempt_ref}`. It does not contain gateway state, Plane attempt ID, operation audit reference, actor, output, details, or object data. The trusted host may normalize that body to its own rejected-result shape while preserving `source:"edge_authentication"`.

## Idempotency

Mutation identity is scoped by authenticated actor, workspace, operation major version, and `Idempotency-Key`.

- Same key and same normalized input digest returns the recorded result with `replayed: true` when the logical invocation has a terminal compatible result.
- A known pre-commit failure may leave the invocation `retryable` without a terminal result. After its contract's backoff or health gate, one caller may atomically claim the next server attempt under the same logical invocation; concurrent retry claimers cannot both execute.
- Same key and different input returns `idempotency_conflict` without execution.
- A mutation that may have committed but cannot be reconciled returns `outcome_unknown` and `retry: "reconcile"`.
- `outcome_unknown` returns HTTP 200 and allows explicit reconciliation only through the original trusted host/operator context bound to the authenticated actor and invocation.
- Reads do not accept mutation idempotency keys and may use ordinary transport retry policy.

For Hermes, the host derives keys from the trusted tool-call identity or stable Code Mode label. For MCP, middleware binds the outer MCP request ID and inner SDK-call ordinal into host context; tool arguments cannot forge them.

## Catalog and version negotiation

- Operation IDs include their contract major version, such as `plane.work_items.get@1`.
- Additive compatible schema and documentation changes preserve the major version.
- Incompatible input, output, error, authorization, or idempotency changes require a new major operation ID.
- Every request pins the exact catalog digest used by its adapter.
- A stale incompatible digest fails before authorization or execution.
- Native, Code Mode, SDK, and MCP adapter digests are pinned together in the integration lock.

## Official Python SDK adapter

Plane Python SDK adds one optional `GatewayTransport` at `BaseResource`.

- Default SDK behavior remains direct public REST.
- Gateway mode converts the SDK's method, path-template match, path values, query, and body into an operation call.
- The method/path-to-operation table is generated and digest-pinned rather than handwritten in MCP handlers.
- The transport converts gateway success into the existing SDK response shape.
- The transport converts structured failure into existing `HttpError` behavior plus machine-readable gateway details.
- The official MCP client factory selects gateway mode; ordinary MCP tool handlers remain unchanged.

## Local Hermes callback

The Deno supervisor does not call this HTTP endpoint. Generated TypeScript sends a credential-free local `plane.call(operation, input)` message to trusted Hermes host code. The host binds context, supplies the Plane credential and catalog digest, derives mutation idempotency, calls the HTTP adapter, and maps the response back to the isolate.

## Required contract tests

- Authentication and revocation for API key and OAuth.
- Workspace, actor, and cross-tenant binding.
- Catalog search, describe, digest, ETag, and incompatible-version failure.
- Input validation and non-leaking denial.
- Every result-envelope state and HTTP mapping.
- Same-key replay, changed-input conflict, lost response, and `outcome_unknown` reconciliation.
- Result spill, bounded artifact read, expiry, and cleanup.
- Forged client context, workspace, catalog, attempt, and idempotency fields.
- Native, Code Mode, SDK, and MCP adapters against shared semantic fixtures.
- SDK direct-REST default behavior remains backward compatible.

# Plane Operation Gateway Wire Contract

## Status

The use of Plane's existing JSON HTTP API service as the v1 cross-process transport was accepted by the user on 2026-07-29. Exact schemas below are proposed for release-manifest approval. This document does not authorize implementation.

## Boundary

The deep `PlaneOperationGateway.execute()` module remains the core interface inside Plane. One thin Django REST adapter exposes that interface to trusted hosts in other processes.

V1 does not add an internal MCP hop, gRPC service, message broker, or separate gateway deployment.

## Endpoints

### Catalog discovery

```text
GET /api/v1/agent-operations/catalog/
GET /api/v1/agent-operations/catalog/{operation_id}/
```

The list endpoint supports bounded text search, tags, effect, cursor, and limit. The detail endpoint returns one exact major-version contract. Responses carry a catalog digest and HTTP `ETag`.

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

## Authentication and binding

- The wire reuses Plane's current `X-Api-Key` and OAuth bearer authentication.
- Plane derives the acting identity from the authenticated credential.
- The workspace path is authorized against that identity on every execution.
- Hermes holds one revocable Plane agent credential in trusted host state.
- The official MCP server continues using its existing authenticated session credential.
- Generated TypeScript receives no credential, endpoint, HTTP headers, workspace slug, or authoritative correlation fields.
- Direct database access is not part of the adapter.

## Result envelope

Every response contains the exact operation, catalog digest, server attempt ID, audit reference, and one state.

```ts
type GatewayWireResult =
  | {
      state: "succeeded";
      operation: string;
      catalog_digest: string;
      attempt_id: string;
      audit_ref: string;
      replayed: boolean;
      output:
        | { kind: "inline"; value: unknown }
        | { kind: "artifact"; preview: unknown; artifact_ref: string; expires_at: string };
    }
  | {
      state: "approval_required";
      operation: string;
      catalog_digest: string;
      attempt_id: string;
      audit_ref: string;
      approval: {
        approval_id: string;
        effect: string;
        summary: string;
        input_digest: string;
        expires_at: string;
      };
    }
  | {
      state: "rejected" | "failed" | "outcome_unknown";
      operation: string;
      catalog_digest: string;
      attempt_id: string;
      audit_ref: string;
      error: {
        code: string;
        message: string;
        retry: "never" | "same_invocation" | "new_invocation" | "reconcile";
        details?: unknown;
      };
    };
```

The approval ID is opaque correlation, not a capability. `APPROVAL-PROTOCOL.md` defines the accepted Hermes-broker decision path and the exact same-turn retry; approver eligibility and credential mechanics remain pre-freeze decisions.

## HTTP behavior

- `200` returns a success, replay, deterministic rejection, or reconciled result.
- `202` means an approval decision is required and no side effect has run.
- `400` means malformed wire input.
- `401` means invalid or revoked authentication.
- `403` means a non-leaking authorization denial.
- `409` means idempotency conflict, stale contract, or another deterministic conflict.
- `413` means an input or result policy limit was exceeded.
- `429` carries bounded retry guidance.
- `5xx` is reserved for dependency or internal failure; mutation retry behavior still comes from the structured envelope and invocation record.

Callers never infer mutation retry safety from HTTP status alone.

## Idempotency

Mutation identity is scoped by authenticated actor, workspace, operation major version, and `Idempotency-Key`.

- Same key and same normalized input digest returns the recorded result with `replayed: true`.
- Same key and different input returns `idempotency_conflict` without execution.
- A mutation that may have committed but cannot be reconciled returns `outcome_unknown` and `retry: "reconcile"`.
- Reads do not accept mutation idempotency keys and may use ordinary transport retry policy.

For Hermes, the host derives keys from the trusted tool-call identity or stable Code Mode label. For MCP, middleware binds the outer MCP request ID and inner SDK-call ordinal into host context; tool arguments cannot forge them.

## Catalog and version negotiation

- Operation IDs include their contract major version, such as `plane.work_items.get@1`.
- Additive compatible schema and documentation changes preserve the major version.
- Incompatible input, output, error, authorization-effect, or idempotency changes require a new major operation ID.
- Every request pins the exact catalog digest used by its adapter.
- A stale incompatible digest fails before authorization, approval, or execution.
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
- Forged client context, workspace, catalog, attempt, approval, and idempotency fields.
- Native, Code Mode, SDK, and MCP adapters against shared semantic fixtures.
- SDK direct-REST default behavior remains backward compatible.

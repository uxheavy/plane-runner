# External MCP Exact Mapping Contract

## Status

Proposed verifier contract for VM-012. This document freezes the evidence shape needed to prove how every pinned Plane MCP v0.2.11 tool reaches the Plane Operation Gateway. The 177-row disposition inventory is an input, not routing proof.

## Required content-addressed bundle

The bundle contains a manifest, one proof record per pinned tool, independently generated source inventories, exact route maps, conformance evidence, and trace joins. Every JSON document uses a canonical serializer and records its SHA-256 digest in the bundle manifest.

```ts
type Behavior =
  | "read"
  | "mutation"
  | "local_only"
  | "attachment_metadata"
  | "presigned_url"
  | "external_source_fetch"
  | "content_read";

type Capability = "pageable" | "bounded_result" | "structured_error";

type PredicateExpr =
  | { op: "always" }
  | { op: "present" | "truthy"; path: string }
  | {
      op: "equals" | "not_equals" | "less_than" | "less_or_equal" | "greater_than" | "greater_or_equal";
      path: string;
      value_json: string;
    }
  | { op: "in" | "not_in"; path: string; values_json: string[] }
  | { op: "iteration"; collection_path: string; item_predicate: PredicateExpr }
  | { op: "exception"; exception_type: string }
  | { op: "status"; source_edge_id: string; status: number }
  | { op: "type_is"; path: string; type_name: string }
  | {
      op: "derived";
      derivation_id: string;
      contract_digest: string;
      dependency_edge_ids: string[];
      input_paths: string[];
      fixture_ids: string[];
      evidence_ids: string[];
    }
  | { op: "and" | "or"; args: PredicateExpr[] }
  | { op: "not"; arg: PredicateExpr };

type MappingSource =
  | { kind: "argument" | "host_binding"; path: string }
  | { kind: "sdk_response"; source_edge_id: string; path: string }
  | { kind: "constant"; value_json: string }
  | {
      kind: "local_derivation";
      derivation_id: string;
      contract_digest: string;
      dependency_edge_ids: string[];
      input_paths: string[];
      fixture_ids: string[];
      evidence_ids: string[];
    };

type MappingRule = {
  source: MappingSource;
  destination_path: string;
  transform:
    | "identity"
    | "rename"
    | "omit_if_null"
    | "canonical_identifier"
    | "opaque_cursor_encode"
    | "opaque_cursor_decode"
    | "curated_projection"
    | "structured_error";
  default_json?: string;
  transform_contract_digest?: string;
};

type StatusMapping = {
  source_status: number | "sdk_exception";
  source_error_code: string | null;
  destination_outcome:
    | "ok"
    | "invalid_input"
    | "not_found"
    | "ambiguous_reference"
    | "denied"
    | "conflict"
    | "rate_limited"
    | "failed"
    | "outcome_unknown";
};

type CallCardinality = {
  minimum: number;
  maximum: number | null;
  per_item_source: MappingSource | null;
};

type McpToolProof = {
  tool_name: string;
  mcp: {
    commit: string;
    source_file: string;
    source_line: number;
    tools_list_schema_digest: string;
  };
  disposition: "MCP-D-001" | "MCP-D-002" | "MCP-D-003";
  adapter_class: "shared_sdk_transport" | "local_pql" | "hardened_attachment";
  behaviors: Behavior[];
  capabilities: Capability[];
  branches: HandlerBranchProof[];
  conformance_evidence_ids: string[];
};

type HandlerBranchProof = {
  branch_id: string;
  source_span: string;
  predicate: PredicateExpr;
  predicate_source_digest: string;
  reachability: { status: "reachable" } | { status: "unreachable"; reviewed_reason: string; reviewer_id: string };
  edges: Array<SdkEdgeProof | LocalEdgeProof | AttachmentEdgeProof>;
};

type SdkEdgeProof = {
  edge_id: string;
  edge_type: "sdk";
  call_site_span: string;
  sdk_commit: string;
  sdk_resource_method: string;
  sdk_source_span: string;
  http_method: string;
  normalized_path_template: string;
  request_model: string | null;
  response_model: string | null;
  gateway_operation_id: string;
  gateway_contract_version: number;
  request_mapping: MappingRule[];
  success_mapping: MappingRule[];
  error_mapping: StatusMapping[];
  pagination_mapping: MappingRule[];
  result_mapping: MappingRule[];
  call_order: number;
  dependency_edge_ids: string[];
  cardinality: CallCardinality;
  trace_ids: string[];
};

type LocalEdgeProof = {
  edge_id: string;
  edge_type: "local";
  behavior: "pql_reference";
  content_digest: string;
  zero_sdk_gateway_network_proof_id: string;
};

type AttachmentEdgeProof = {
  edge_id: string;
  edge_type: "attachment";
  behavior: "presigned_url" | "external_source_fetch" | "content_read";
  transfer_policy_version: string;
  authorization_trace_ids: string[];
  transfer_trace_ids: string[];
  security_evidence_ids: string[];
};

type AssertionKind =
  | "runtime_schema"
  | "success"
  | "qualified_unsupported"
  | "legacy_shadow"
  | "authorization_denial"
  | "structured_error"
  | "pagination"
  | "result_bound"
  | "retry"
  | "duplicate_delivery"
  | "lost_response"
  | "ambiguous_outcome"
  | "reconciliation"
  | "audit"
  | "authorization_before_transfer"
  | "redirect_ssrf_dns"
  | "transfer_limits"
  | "secret_redaction"
  | "byte_retention_cleanup"
  | "pql_brief_content"
  | "pql_full_content"
  | "local_derivation"
  | "zero_sdk_gateway_network";

type ConformanceEvidence = {
  evidence_id: string;
  tool_name: string;
  branch_id: string | null;
  edge_id: string | null;
  behavior: Behavior;
  capability: Capability | null;
  assertion_kind: AssertionKind;
  fixture_id: string;
  expected_oracle_id: string;
  artifact_digest: string;
  trace_ids: string[];
};

type SchemaTransitionProof = {
  transition_id: string;
  tool_name: string;
  from_contract_version: string;
  to_contract_version: string;
  from_schema_digest: string;
  to_schema_digest: string;
  direction: "backward" | "forward";
  expected: "compatible" | "incompatible";
  fixture_ids: string[];
  result_artifact_digest: string;
};
```

Every `edge_id` is unique within its tool. Every dependency names an edge in the same tool, the dependency graph is acyclic, and every trace/evidence reference resolves to the exact tool, branch, and edge. Exact mapping fields cannot contain a wildcard, catch-all, category-only value, unresolved template variable, or bare `sdk_http_intent`. That label may describe disposition strategy only; it cannot satisfy an SDK edge.

Mapping and predicate arrays must be nonempty where the source inventory reports corresponding fields or conditions. `transform_contract_digest` is mandatory for any transform whose complete semantics are not fixed by this document. Free-form prose cannot satisfy a predicate, mapping, status, or cardinality field.

## Independently generated control inventories

The mapping generator and verifier consume separate source-derived inventories:

- runtime `tools/list` tool names and schemas;
- handler functions, stable branch IDs, branch predicates, and source spans;
- handler SDK call sites, including calls inside loops and conditional branches;
- SDK resource methods, HTTP verbs, normalized path templates, and model types;
- frozen gateway catalog operation IDs and versions;
- source-derived behavior classification, including every mutation and attachment behavior.
- source-derived capability classification for pagination, bounded results, and structured errors;
- an independently generated or explicitly approved canonical semantic-mapping inventory containing the exact predicate, request, success, error, pagination, result, host-binding, constant, and local-derivation records expected for every branch/edge;
- pinned baseline and independently captured runtime tool-schema artifacts;
- approved schema-transition pairs and their compatibility direction.

An unreachable branch requires a nonempty source-grounded rationale and reviewer identity. The mapping author cannot solely approve unreachable status.

## Required exact joins

VM-012 fails unless all joins are exact:

1. Pinned inventory tool-name set = runtime `tools/list` set = disposition set = per-tool proof set.
2. Source-derived handler branch set = recorded branch set, with no orphan or duplicate branch ID.
3. Source-derived edge set = recorded edge set, with stable unique `edge_id` values, exact call order/cardinality, valid same-tool dependencies, and an acyclic dependency graph.
4. Every referenced SDK method/path exists at the pinned SDK commit and every used method/path has a mapping.
5. Every mapped gateway operation ID/version exists in the frozen catalog.
6. Every executed trace joins tool → branch → SDK or exception edge → gateway operation → audit attempt.
7. Source-derived behavior and capability sets = proof behavior and capability sets exactly, with no duplicate or unknown combination; any reachable mutation edge requires `mutation`, and pagination/result/error source behavior requires its corresponding capability.
8. Canonicalized proof predicates and every request/success/error/pagination/result mapping equal the independently generated or explicitly approved semantic-mapping inventory exactly, including SDK source edges, host bindings, constants, transforms/defaults, local derivations, statuses, and cardinality.
9. Every SDK-response source names a valid dependency edge. Every local derivation or derived predicate has a content-addressed contract, exact input/dependency set, nonempty fixture/evidence references, and a matching `local_derivation` assertion. Cardinality iteration uses the same typed `MappingSource` dataflow.
10. Every tool/branch/edge/behavior/capability has the exact required `AssertionKind` set, nonempty fixture/oracle/artifact IDs, and nonempty trace IDs whenever execution is part of the oracle.
11. Every `tools_list_schema_digest` equals both the independently captured runtime schema artifact and the expected pinned baseline or approved transition endpoint.
12. Every approved schema transition has one complete `SchemaTransitionProof`; fixture IDs are nonempty and the recorded result equals the declared compatibility expectation.
13. No orphan route-map row, wildcard mapping, generic terminal label, unresolved dependency, unreferenced evidence record, or unresolved artifact/trace reference exists.

## Disposition-specific proof

### MCP-D-001 shared SDK transport

Every reachable Plane behavior has one or more exact SDK edges. Schema, success, structured error, pagination/result normalization, and normalized legacy shadow comparison pass. Every mutation additionally proves denial, retry, duplicate delivery, lost response, ambiguous outcome, reconciliation, and audit behavior.

### MCP-D-002 local PQL

`get_pql_reference` proves the pinned `brief` and `full` content digests and static plus runtime absence of SDK, gateway, filesystem-derived content, and network calls.

### MCP-D-003 hardened attachments

Every Plane subcall has an exact SDK edge. Every non-SDK transfer branch has its own attachment edge and separately proves authorization-before-transfer, redirect and DNS-rebinding defense, loopback/link-local/metadata/private-network denial, scheme/content-type/size/time limits, presigned-secret redaction, byte-retention policy, and cleanup. Category-wide evidence cannot replace per-tool/per-branch evidence.

## Per-tool conformance

Every proof record links typed `ConformanceEvidence` records keyed to the exact tool, branch, edge, behavior, fixture, oracle, artifact, and traces. The required assertion sets are exact rather than minimum counts:

- every tool: `runtime_schema`, exactly one of `success` or `qualified_unsupported`, `legacy_shadow`, and `authorization_denial`;
- pageable or bounded tools: capability-keyed `pagination` and/or `result_bound` as identified by the source-derived capability inventory;
- tools with structured errors: capability-keyed `structured_error`;
- every executed SDK edge: trace/audit joins to its `success`, applicable `structured_error`, and `audit` assertions;
- every local derivation or derived predicate: `local_derivation` keyed to the exact tool/branch/edge and its contract/fixture;
- every mutation: `retry`, `duplicate_delivery`, `lost_response`, `ambiguous_outcome`, `reconciliation`, and `audit`;
- local PQL: `zero_sdk_gateway_network`, `pql_brief_content`, and `pql_full_content`;
- every attachment transfer edge: `authorization_before_transfer`, `redirect_ssrf_dns`, `transfer_limits`, `secret_redaction`, and `byte_retention_cleanup`.

An empty evidence list, unrelated existing evidence ID, category-wide attachment record, or record keyed to a different tool/branch/edge cannot satisfy a requirement. The verifier derives the expected assertion-kind multiset independently and requires exact equality.

Schema-transition proof separately joins each runtime schema digest to its content-addressed artifact and pins `from`/`to` versions, both schema digests, compatibility direction, expected verdict, nonempty fixtures, and result digest. An incompatible transition passes only when the client rejects it for the frozen versioning reason; silent narrowing or information loss fails.

## VM-022 mapping sensitivity controls

The verifier first passes an unmodified positive fixture, then must fail for the intended reason when each isolated mutation is introduced:

1. Omit one tool proof.
2. Duplicate one disposition.
3. Omit one conditional handler branch.
4. Omit one SDK call from a multi-call handler.
5. Swap one HTTP method or normalized path.
6. Use a nonexistent or wrong-version gateway operation.
7. Replace an exact SDK edge with bare `sdk_http_intent`.
8. Misclassify one mutation as read-only.
9. Remove one required mutation denial/retry fixture.
10. Route one attachment fetch outside hardened transfer policy.
11. Add an SDK, gateway, or network call to the local PQL tool.
12. Route one traced Plane call outside the gateway.
13. Duplicate an edge ID, break a dependency reference, or introduce a dependency cycle.
14. Replace one structured predicate, field mapping, SDK source edge, host binding, constant, status, transform, or cardinality with either generic/incomplete data or a well-formed but semantically wrong value that differs from the independent semantic inventory.
15. Remove a source-derived behavior/capability, omit `mutation` from a reachable mutation edge, or remove pagination/bounded/error applicability.
16. Empty, mis-key, or substitute one required behavior- or capability-scoped conformance/attachment evidence record.
17. Mismatch one runtime schema artifact digest or omit/change one required schema-transition record.

A mutation that fails because setup is broken or for a reason other than its exact intended validator invariant—tool/branch/edge set, route, version, edge graph, semantic mapping, behavior/capability, evidence, schema transition, disposition policy, or gateway trace—does not qualify the control.

# External MCP Compatibility Plan

## Status

Proposed for release-manifest approval. The compatibility baseline is the official Python MCP server at commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`.

## Compatibility unit

Compatibility is evaluated per MCP tool contract, not per REST endpoint. An MCP tool may map to one gateway operation, several gateway operations, or deliberately retained local behavior.

The pinned source inventory contains 177 unique tool names. Tool name, input semantics, successful output semantics, structured failure behavior, and documented transport/authentication behavior form the baseline. Exact byte-for-byte output compatibility is not required when the legacy output is nondeterministic, but a normalized comparison must preserve all documented information.

## Complete disposition

The following mutually exclusive rules cover every pinned tool. The inventory checker must fail if a tool matches zero or more than one rule.

| Rule      | Match                                                         | Count | Disposition                               | Rationale                                                                                                                                    |
| --------- | ------------------------------------------------------------- | ----: | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| MCP-D-001 | `category != "pql"` and `category != "work_item_attachments"` |   171 | Gateway-backed compatibility adapter      | Preserve the Python MCP contract while routing authorization, approval, mutation safety, result limits, and audit through shared operations. |
| MCP-D-002 | `name == "get_pql_reference"`                                 |     1 | Retain local read-only behavior           | The tool returns static query-language reference material and does not call Plane. Its content is versioned and tested.                      |
| MCP-D-003 | `category == "work_item_attachments"`                         |     5 | Hardened attachment compatibility adapter | Preserve attachment behavior while separating Plane authorization from controlled source/presigned URL transfer and SSRF policy.             |

No pinned v0.2.11 tool is deprecated or omitted in v1.

## Gateway-backed adapter contract

- The adapter derives workspace and identity from its authenticated MCP session.
- It translates the legacy MCP input into one or more versioned semantic gateway calls.
- Multi-step composition stays in the gateway catalog when it represents one semantic Plane action.
- It translates structured gateway outcomes into compatible MCP success or error results.
- It does not duplicate Plane authorization or create an MCP-specific entitlement list.
- Mutating tools receive stable invocation keys and the gateway's reconciliation behavior.
- The adapter applies no weaker result bound than the native and Code Mode paths.
- Every inner gateway attempt remains independently auditable under the outer MCP call correlation.

## Attachment adapter contract

- Plane authorization is completed before resolving or transferring attachment content.
- Generated code never receives presigned credentials or storage credentials.
- Redirects, DNS rebinding, loopback, link-local, metadata, private-network, and unsupported-scheme destinations are rejected.
- Source download and object upload use an explicit size, duration, redirect, and content-type policy.
- Logs and audit summaries redact query signatures, authorization data, and sensitive headers.
- Attachment bytes are not retained in durable audit records.
- Temporary content is deleted according to the approved artifact-retention policy.

## Transport and authentication compatibility

The v1 compatibility suite covers:

- stdio with `PLANE_API_KEY` and `PLANE_WORKSPACE_SLUG`;
- hosted Streamable HTTP OAuth at `/http/mcp`;
- hosted Streamable HTTP PAT at `/http/api-key/mcp` with its workspace header;
- legacy SSE at `/sse` for the duration of the approved compatibility window.

The suite must include initialization, capability negotiation, tool listing, representative reads and writes, structured denial, approval interruption where supported by the client, pagination, oversized results, mutation retry, and transport reconnect.

## Conformance tiers

1. Every one of the 177 tools receives schema and adapter-contract tests.
2. Every tool receives at least one successful integration path or an environment-qualified unsupported-feature result matching the legacy contract.
3. Every mutating tool receives denial and retry tests.
4. Every category receives shadow comparison against the pinned Python handler on equivalent seeded state.
5. Pilot operations and every exceptional local or attachment tool receive live real-client tests.

## Change policy

- Additive optional fields and new tools are allowed in a compatible minor release.
- Removing or renaming a tool, making an optional input required, narrowing accepted input, or removing output information requires an approved deprecation plan and major compatibility version.
- Security hardening may reject behavior that the legacy server allowed only through an explicit approved security exception record with migration guidance.
- Native Hermes tool names and schemas version independently from this external MCP contract.

## Required evidence

- Pinned inventory digest and generated coverage report.
- Per-tool disposition and gateway-operation mapping.
- Schema-diff report.
- Shadow-comparison report with reviewed normalizers.
- Real-client versions, configurations, and transcripts.
- Transport/authentication matrix.
- Failure, retry, approval, pagination, and result-bound evidence.
- Rollback proof that restores the pinned legacy handler without contract or data loss.

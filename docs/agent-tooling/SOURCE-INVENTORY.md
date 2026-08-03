# Source Inventory

This document records observed source facts used to freeze the v1 release. It distinguishes current implementation from the target architecture.

## Pinned sources

| Source                    | Revision                                                         | Evidence                     |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------- |
| Plane                     | `d4679197ba` on `codex/agent-tooling-architecture`               | Local authoritative worktree |
| Hermes                    | `5e88745f125c0d332c1d16ea0363860d447657f5` on `main`             | Local authoritative worktree |
| Official Python MCP       | `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`     | `makeplane/plane-mcp-server` |
| Python MCP SDK dependency | `plane-sdk==0.2.20`                                              | MCP `pyproject.toml`         |
| Plane Python SDK          | tag `v0.2.20`, commit `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426` | `makeplane/plane-python-sdk` |

## Plane public interface

- The public Plane interface is mounted under `/api/v1/`.
- Public API-key authentication uses `X-Api-Key`.
- OpenAPI generation uses DRF Spectacular when `ENABLE_DRF_SPECTACULAR=1`.
- The OpenAPI hook emits only `/api/v1/` paths and excludes `PUT`.
- No generated OpenAPI document is checked into the inspected Plane revision.
- `/api/v1/` does not expose API-key-authenticated workspace discovery.
- Workspace slug must therefore be trusted host context for the v1 internal-agent workflow.
- The internal workspace-discovery route uses session authentication and is not part of the v1 agent contract.

## Planning-workflow operations

| Capability             | Public method and path                                                                     | Declared operation ID      | Important current behavior                                                |
| ---------------------- | ------------------------------------------------------------------------------------------ | -------------------------- | ------------------------------------------------------------------------- |
| List projects          | `GET /api/v1/workspaces/{slug}/projects/`                                                  | `list_projects`            | Membership/public-network filtered and paginated                          |
| Retrieve project       | `GET /api/v1/workspaces/{slug}/projects/{project_id}/`                                     | `retrieve_project`         | Project UUID comes from list/lite lookup                                  |
| List current cycles    | `GET /api/v1/workspaces/{slug}/projects/{project_id}/cycles/?cycle_view=current`           | `list_cycles`              | Returns a bare array with zero or more overlapping current cycles         |
| Search work items      | `GET /api/v1/workspaces/{slug}/work-items/search/`                                         | `search_work_items`        | Text/identifier search, not semantic embedding search                     |
| List work items        | `GET /api/v1/workspaces/{slug}/projects/{project_id}/work-items/`                          | `list_work_items`          | Paginated; supports fields, expand, ordering, and external lookup         |
| Retrieve work item     | `GET /api/v1/workspaces/{slug}/projects/{project_id}/work-items/{work_item_id}/`           | `retrieve_work_item`       | Supports expanded assignees through serializer behavior                   |
| Retrieve by identifier | `GET /api/v1/workspaces/{slug}/work-items/{PROJECT}-{SEQUENCE}/`                           | `get_workspace_work_item`  | Resolves project membership from the identifier                           |
| List project members   | `GET /api/v1/workspaces/{slug}/projects/{project_id}/project-members-lite/`                | `get_project_members_lite` | Exposes member activity status and role                                   |
| List relations         | `GET /api/v1/workspaces/{slug}/projects/{project_id}/work-items/{work_item_id}/relations/` | `list_work_item_relations` | Returns grouped related IDs, not expanded work items                      |
| Create parent or child | `POST /api/v1/workspaces/{slug}/projects/{project_id}/work-items/`                         | `create_work_item`         | A child supplies `parent`; parent must be in the same project             |
| Update work item       | `PATCH /api/v1/workspaces/{slug}/projects/{project_id}/work-items/{work_item_id}/`         | `update_work_item`         | Partial state/priority/parent/assignee updates; cycle/module are separate |
| Assign cycle           | `POST /api/v1/workspaces/{slug}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/`     | `add_cycle_work_items`     | State converges but repeated calls emit activity                          |
| Create comment         | `POST /api/v1/workspaces/{slug}/projects/{project_id}/work-items/{work_item_id}/comments/` | `create_work_item_comment` | Source links must be encoded in supported comment content/fields          |

## Plane permission behavior

- Safe project reads require active workspace membership and then apply project-membership or public-project filtering.
- Work-item, cycle, and relation reads require active project membership.
- Work-item, cycle, and relation mutations require active project membership with member or administrator role.
- Comment creation currently requires active project membership but does not use the stricter member/admin mutation role check.
- Search independently filters results to active project memberships.
- These current behaviors are the authorization oracle; the agent layer must not broaden them.

## Plane idempotency gaps

- `create_work_item` has no standard idempotency-key support.
- Optional external identifiers return `409` on an observed duplicate rather than replaying the first success.
- The external-identifier precheck has no database uniqueness constraint and is not race-safe.
- `create_work_item_comment` has the same non-race-safe duplicate-precheck behavior.
- `update_work_item` repeats timestamps, activity, and webhook side effects even when field state converges.
- Cycle assignment and relation creation converge principal database state but repeat activity side effects.
- The Plane Operation Gateway must add invocation-level idempotency and outcome reconciliation for the v1 write workflow.

## Existing Python MCP compatibility surface

- The official Python MCP uses Python, FastMCP `3.2.0`, and `plane-sdk==0.2.20`.
- Source registration contains 177 unique tools across 25 top-level categories.
- The README's older “100+ tools across 20 categories” statement is not the compatibility oracle.
- The pinned machine-readable inventory is `inventories/plane-mcp-v0.2.11.json`.
- The pinned inventory SHA-256 is `2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1`.
- The inventory contains tool name, category, source file, line, signature, and return annotation.
- Most MCP tools call the public Plane SDK.
- Some MCP tools compose several public operations.
- `get_pql_reference` is local-only behavior.
- Attachment tools may call public source or presigned object-storage URLs in addition to Plane.
- Compatibility must therefore map each MCP tool contract to one or more gateway operations or explicitly retained local behavior.

### Shared SDK transport seam

- Every ordinary MCP handler obtains `PlaneClient` through `get_plane_client_context()`.
- `PlaneClient` constructs resource objects over a shared `Configuration` type.
- Every SDK resource inherits `BaseResource`.
- `BaseResource` owns the common `requests.Session`, URL construction, authentication headers, retries, and HTTP response normalization.
- SDK v0.2.20 does not currently accept a custom transport.
- Adding one optional transport at `BaseResource` is the smallest common seam for preserving existing MCP handlers while routing their SDK calls through the gateway.

### Authentication and transports

- Stdio requires `PLANE_API_KEY` and `PLANE_WORKSPACE_SLUG`.
- Hosted OAuth uses `/http/mcp` with read and write scopes.
- Hosted PAT uses `/http/api-key/mcp` with bearer PAT and `X-Workspace-slug`.
- Legacy SSE OAuth uses `/sse`.
- The inspected stdio startup does not implement the README's claimed `PLANE_ACCESS_TOKEN` environment alternative.

## Hermes integration facts

- Native tools self-register through the Hermes registry.
- Truly eager tools must be registered and included in `_HERMES_CORE_TOOLS`.
- Non-core native, plugin, and MCP tools can be deferred behind Hermes Tool Search.
- Deferred calls are unwrapped before middleware, approval hooks, guardrails, and dispatch.
- Plane v1 does not invoke Hermes approval hooks to confirm Plane operations; the observation above describes existing Hermes behavior only.
- Hermes's current `execute_code` runtime is Python-only.
- The Python runtime already demonstrates credential scrubbing and authenticated local host RPC.
- Plane TypeScript Code Mode needs a separate restricted runner rather than adding Plane access to generic Python Code Mode.
- `openai-codex` resolves to the subscription-backed Codex Responses mode.
- `gpt-5.6-luna` is in Hermes's current curated Codex model catalog.

## Superseded eager Hermes surface proposal

The following earlier proposal is retained as source history but superseded by ATD-106 through ATD-114 and ADR-0007. It is not the current native tool contract:

- `plane_search_work_items`
- `plane_get_work_item`
- `plane_create_work_item`
- `plane_update_work_item`
- `plane_add_comment`
- `plane_docs`
- `plane_search`
- `plane_execute`

Workspace, project, and run identity remain host-bound context. Final eager and progressive tool names and schemas remain open catalog decisions.

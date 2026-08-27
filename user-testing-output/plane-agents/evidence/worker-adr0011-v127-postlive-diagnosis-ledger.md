# ADR-0011 Worker O02 post-live receipt and diagnosis

## Bounded receipt

- Status: `LIVE_STOP`.
- Scope: exactly one corrected fresh Worker flow after a zero-effect checkout-bind preflight stop. No retry, fallback, replay, second primary, or subagent.
- Candidate/wrapper: `a7850636a3c76e280afdbba603c2e4413f5fa76d`.
- Source: `cc37dc3d9666d419be9ad2391b86e02354e4d7e3`.
- API image: `plane-agent-api:g4-v127-cc37dc3d`, `sha256:f6e404586277ec9e42b4f8e83f50fc8228b8bf794ed6c6a8a6faca305d61e85b`.
- Runtime image: `plane-agent-runtime:hermes-d4789f13-v129-cc37dc3d`, `sha256:1dc74bd3d76bb98b76ed4085e03039e2c96c233e8a19d3c47d9fc028e71dfe4c`.
- Hermes/MCP/SDK pins: `d4789f135fda04434cca788d07c634dc7c3bbfca` / `d65df7c94bcd41a3c7795c40c1227e2199889d71` / `4403116b3601a29d7a2c507c8bef1db768574142`.
- Commission: `code-mode-semantic-rename`.
- Descriptor SHA-256: `c103cc59d5c621876ab141ddfdf190020b4f4744b190dc6f3d18366926edb90a`.
- Manifest SHA-256: `886c4e3e667aa2ace913f4bb015a4187269d02f8ffa1530b440fae73ed7657c3`.
- Model policy: `openai-codex/gpt-5.6-luna`, reasoning `xhigh`, fallback `false`.
- Run: `9485d885-4327-4114-b644-fc365fc903b7`, state `succeeded`.
- Invocation: `invocation:26b43abf-f7e1-4555-8c6d-05e99ecc455a`, state `succeeded`.
- Runtime exit: `completed`, final sequence `5`, failure `null`.
- Provider attempts: exactly `2`; both upstream-initiated and `2xx`.
- Terminal lifecycle: hook installed; terminal action observed at `post_tool_batch`; reason `terminal_action_observed`; `api_call_count=2`; `provider_responses=2`; `iteration_budget_used=2`; `iteration_budget_remaining=14`; outcome publication `null`.
- Plane host operation receipts: `false`. Absent rows: `search_workspace`, `work_item.read`, `work_item.rename`, `catalog.search`, `catalog.describe`, `agent.outcome.evaluate`, `agent.outcome.submit`, `agent.outcome.publish`.
- S00 gate: `failed`; first failed predicate `one_applied_outcome_publication`; visible outcome terminal passed; applied publication count `0`; publication refs unavailable.
- Provider stderr SHA-256: `27e9eabd1d99e57417027d96eebf03ac54964a5b0ca6bc15c93047ce423f92b4`.
- Raw result SHA-256: `3238dbbff861283b18dce58fdc82865f11998fd1995820003900e5a82647254d`.
- Raw result: `unavailable`; it was removed after bounded receipt validation and cleanup. No raw model payload, credentials, or unbounded result is retained here.
- Owner-only auth source was passed opaquely; its contents were not read, printed, or retained.
- Cleanup predicate: scratch removed; lease absent; labeled containers `0`; live networks `0`; worktree clean.

## Provider-free diagnosis

### ROOT_CAUSE

The flow had a non-enforcing model/terminal seam. Pinned Hermes presents Code Mode guidance and the registered model tools `Plane:discover` and `Plane:execute`, but the Codex transport defaults a tool-bearing request to `tool_choice=auto`. Its post-search forced-choice helper still detects only the legacy `plane_execute_typescript` name (`hermes-agent/agent/chat_completion_helpers.py:60-96,1256-1265`). Therefore the source does not guarantee the required `Plane:execute` route, and the bounded receipt does not retain the actual wire choice.

Once a terminal-shaped `Plane:execute` result exists, Hermes observes the host terminal hook after the tool batch and its finalizer treats `terminal_action(...)` as completed (`hermes-agent/agent/conversation_loop.py:6183-6207`; `hermes-agent/agent/turn_finalizer.py:238-249`). Plane Code Mode accepts `plane.finish({kind:"completed", ...})` and maps it through `finish_code_mode` to `propose_outcome` (`apps/api/plane/agent/code_mode/host.py:581-678`; `apps/api/plane/agent/lifecycle/services.py:3026-3052`). That terminal path does not prove the commission's read/rename operations or the separate applied `agent.outcome.publish` receipt. The retained facts—zero operation rows, zero applied publication, but observed terminal action—match this shortcut path.

Exact response classes are unavailable, not inferred: the retained bounded result omitted `runtimeDiagnostics.requests[*].toolChoice`, `visibleToolset`, and `responses[*].responseClass/toolCall` even though the wrapper schema can validate those fields (`tools/agent-g4-live-invoke.py:1137-1220`). Consequently this ledger does not claim whether the two responses were `text_response`, `Plane:discover`, `Plane:execute`, or another tool-call shape.

### Smallest owner seam

Hermes' Code Mode request/terminal contract: make the exact `Plane:execute` tool name the forced post-search choice, and make completion fail closed unless the Code Mode execution proves the required operation receipts plus the applied outcome publication. The next run must retain the bounded request/response classes so the model-choice branch is directly auditable. No implementation was made in this record.

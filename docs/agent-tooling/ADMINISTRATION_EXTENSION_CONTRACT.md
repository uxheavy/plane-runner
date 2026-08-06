# G3 administration extension contract

The Plane administration lane owns authorization, bounded readback, redaction, and the API/CLI envelope. The L7 domain worker owns delegation lineage, HR proposals, chief-of-staff provisioning, and evaluator review state. L7 must expose an adapter; it must not add those records to Plane's Agent models.

The adapter is registered as an `AgentAdminExtensionPort` and may optionally implement `AgentAdminExtensionServicePort`:

- `read(workspace_id, resource_id) -> Mapping[str, Any] | None` returns one already-authorized projection.
- `execute(AgentAdminExtensionCommand) -> Mapping[str, Any]` handles only `delegation.lineage.read`, `hr.proposal.read`, `chief_of_staff.provision`, or `evaluator.review`.
- A separate `AgentAdminExtensionSerializerPort.serialize(value)` returns the typed, redacted projection used by both API and CLI.

Every command carries `workspace_id`, optional `actor_id`, `run_id`, and `invocation_id`, an idempotency key, and a bounded JSON payload. The adapter must re-check live workspace/object authorization, bind actor/run/invocation relationships, reject cross-workspace references without existence details, and return no credentials, socket paths, control metadata, raw payloads, or unbounded content. Mutations must be idempotent and write through the existing shared gateway/audit boundary when they are gateway operations.

The adapter is expected to return stable fields for its resource plus the existing administration envelope fields (`resource`, `workspace_id`, `actor_id`, `run_id`, `invocation_id`, `state`, `created_at`, and a redacted evidence reference). Plane must not infer domain state from counts or duplicate L7 lifecycle records.

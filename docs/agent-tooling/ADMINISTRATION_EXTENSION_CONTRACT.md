# G3 administration extension contract

Plane owns the administration boundary: live workspace authorization, bounded
pagination, redaction, and the API/CLI envelope. The L7 lifecycle owns
delegation lineage, HR proposals and decisions, chief-of-staff provisioning,
evaluator review, acceptance/revision, and cancellation state. The merged L7
models and lifecycle services are the only source of that state; administration
does not infer it from counts or duplicate it.

## Concrete adapters

The Plane implementation is `plane.agent.administration_extensions` and is
registered under `plane.agent.governance`:

- `PlaneAgentAdministrationExtension.read(workspace_id, resource_id)` returns
  the typed `GovernanceReadback` projection.
- `PlaneAgentAdministrationExtension.execute(AgentAdminExtensionCommand)`
  handles the bounded command actions below and delegates transitions to the
  existing L7 lifecycle services.
- `build_governance_readback(workspace, limit, resource_id=None)` is the one
  projection builder used by the API and management command.

The same projection is available through:

- `GET /api/v1/workspaces/{slug}/agent-admin/governance/`
- `GET /api/v1/workspaces/{slug}/agent-admin/governance/?resource_id=assignment:{uuid}&limit=...`
- `POST /api/v1/workspaces/{slug}/agent-admin/governance/commands/`
- `manage.py agent_governance_readback --workspace-slug ... [--resource-id ... --limit ...]`
- `manage.py agent_governance --workspace-slug ... --action ... --idempotency-key ... --payload ...`

All API endpoints reuse `WorkspaceOwnerPermission`; the commands use the same
workspace-scoped adapter checks and never accept a credential, socket, or
control value. A missing or cross-workspace object returns the same bounded
unavailable error and does not reveal whether it exists elsewhere.

## Stable command actions

| Action | Plane binding | L7 operation/service authority |
| --- | --- | --- |
| `delegation.lineage.read` | assignment lineage projection | `AssignmentContract` lineage fields |
| `hr.proposal.read` | HR proposal projection | `AgentHRProposal` |
| `hr.proposal.decide` | proposal + live human reviewer | `decide_hr_proposal` |
| `chief_of_staff.provision` | human + HR proposer | `propose_chief_of_staff` (human approval remains required) |
| `evaluator.review` | outcome + run + independent evaluator | `review_outcome` |
| `outcome.accept` | reviewed outcome + live human reviewer | `accept_outcome` |
| `outcome.request_revision` | reviewed outcome + live human reviewer | `request_revision` |
| `assignment.cancel` | workspace assignment + live human reviewer | `cancel_assignment` |

Gateway-originated Agent mutations remain the existing
`OperationGateway` operations (`agent.assignment.delegate`,
`agent.assignment.cancel`, `agent.hr.propose`, `agent.hr.decide`,
`agent.outcome.evaluate`, `agent.outcome.accept`, and
`agent.outcome.request_revision`). The administration adapter does not create
a second permission model or bypass that gateway for those calls.

## Projection and safety contract

`GovernanceReadback` contains bounded lists of `assignments`, `hr_proposals`,
and `evaluator_reviews`, each limited to 1–100 records and scoped to one
workspace. It exposes typed IDs, lifecycle states, delegation parent/root and
actor bindings, HR decision facts, evaluator criteria/verdict/recommendation,
and redacted provenance. It excludes profile credentials, raw requested
profiles, runtime control/lease/socket metadata, raw operation request/result
payloads, and unbounded evidence.

The API and CLI use the same serializer-free projection function, enforce the
8 KiB UTF-8 response ceiling, and reject credential-shaped command payloads.
The `credential_configured` boolean remains the only credential fact exposed
by the existing actor projection; credential values are never substituted with
strings.

Every mutation is idempotent at the L7 service boundary or is convergent on
its terminal state. Every object lookup rechecks workspace scope. Optional
`actor_id`, `run_id`, and `invocation_id` command fields must bind to the target
record before a transition is attempted.

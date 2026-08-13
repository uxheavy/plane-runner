# Plane Agent dogfood personas

These are persistent test personas, not separate agent products or runtime
modes. Each uses the same native Plane Agent model with a Plane-owned role and
profile. All live journeys use GPT-5.6 Luna.

## Maya — working Agent

Maya is a senior product engineer who wants an assigned issue completed without
micromanaging the agent. She expects the agent to discover the right Plane
objects, use the tools it needs, leave an inspectable artifact, and publish a
concise outcome. She stops trusting the product if the result exists only in a
transcript, if replay duplicates a mutation, or if memory crosses user or Agent
boundaries.

Primary routes: W01–W08. Session: `plane-agents-wave-1-working-agent`.

## Elena — manager and delegator

Elena leads a mixed human/Agent team. She is comfortable with Plane but not
with agent-runtime terminology. She wants to commission work, let an Agent plan
and delegate bounded sub-work, review evidence, request revision, and govern
new roles without creating an alternate permission system. She stops using the
feature if delegated work loses lineage, schedules bypass normal assignments,
or an Agent can approve its own employment or final result.

Primary routes: M01–M08. Session: `plane-agents-wave-1-manager-delegator`.

## Omar — skeptical operator and integrator

Omar owns platform security and integrations. He assumes retries, crashes,
stale credentials, cross-workspace references, and hostile client inputs will
happen. He wants one authorization source, bounded receipts, exact audit
readback, safe reconciliation, and a rollback path. He rejects the product if
MCP or Code Mode bypasses the gateway, if credentials enter generated code, or
if `outcome_unknown` is blindly replayed.

Primary routes: O01–O10. Session: `plane-agents-wave-1-operator-integrator`.

# Operator O01/O03-O09 provider-free readiness — 2026-08-18

Status: `READY_WITH_COMMIT`

This is a provider-free preparation receipt for the Operator lane. It is not
live-route closure and does not authorize an image build, Compose journey, or
provider call.

## Binding

- Source before the lane change: `d4316b79272254b61d038a65cba6a9860a6afeeb`.
- Lane commit: `6bf7d25cd6344ff61363d29a54b1872c045fa8ca`.
- Operator descriptor: `tools/agent-g4-operator-v6.json`.
- Descriptor SHA-256: `5594c150048dc824c3ce84a1cccd163f30d9753a25d53303316bf6b45a52f6c6`.
- Descriptor route set is exactly `O01,O03,O04,O05,O06,O07,O08,O09`.
  `O02` remains excluded as already clean; `O10` is outside this lane.
- Descriptor model policy remains provider `openai-codex`, model
  `gpt-5.6-luna`, reasoning `xhigh`, fallback disabled. No credential or
  provider secret was read, copied into evidence, or used.

## Compact route matrix

| Route | Descriptor commission / provider-free evidence | Later live proof still required |
| --- | --- | --- |
| O01 | `presentation-and-sdk-identity`; scenario parser and Operator scope regression | Catalog disclosure versus live denial with zero side effect |
| O03 | `presentation-and-sdk-identity`; scenario parser and contract suite | Authenticated SDK caller binding and substitution/expiry denial |
| O04 | `lease-and-replay-boundaries`; descriptor contract coverage | Host-only lease rotation/revocation/expiry across dispatch and callback |
| O05 | `lease-and-replay-boundaries`; descriptor contract coverage | Stable idempotency across dispatch, callback, mutation, submit, publish |
| O06 | `failure-and-budget-reconciliation`; descriptor contract coverage | Cancellation/timeout/process-death reconciliation and no blind unknown replay |
| O07 | `failure-and-budget-reconciliation`; descriptor contract coverage | Cumulative model/tool/Code Mode/run budgets across invocations |
| O08 | `ingress-health-and-rollback`; descriptor contract coverage | Malformed/oversized/duplicate/out-of-order/cross-bound ingress rejection |
| O09 | `ingress-health-and-rollback`; descriptor contract coverage | Bounded concurrent gateway load plus health/audit/quota/version/readback |

The scenario regression proves the exact route binding and model policy; the
contract suites prove the provider-free launch/result/runtime contract. They do
not substitute for the later exact-candidate live proof in the final column.

## Provider-free checks

All commands below ran against the lane commit or its fresh synthetic clone.

| Check | Result |
| --- | --- |
| `tools/tests/test_agent_g4_live_scenario.py -k 'operator'` | 4 passed, 53 deselected |
| `tools/tests/test_agent_g4_live_support.py tools/tests/test_agent_g4_live_result.py tools/tests/test_agent_g4_live_launch.py` | 23 passed |
| `tools/tests/test_agent_g4_contract.py` | 110 passed |
| Fresh clone: full `tools/tests/test_agent_g4_live_scenario.py` | 57 passed |
| Fresh clone: support/result/launch suite | 23 passed |
| Fresh clone: `tools/tests/test_agent_g4_contract.py` | 110 passed |
| `git diff --check` | passed |

The native API/runtime pytest collection was attempted for the Operator
readback, runtime-unit, and production-contract groups. Collection stopped in
the checkout because `celery` is not installed (`ModuleNotFoundError: No
module named 'celery'`); no result was represented as a pass.

## Fresh workspace and safety boundaries

- Fresh synthetic workspace:
  `/private/tmp/plane-agent-operator-o01-o09-provider-free-ready.qwaomK`.
- Fresh workspace HEAD:
  `6bf7d25cd6344ff61363d29a54b1872c045fa8ca`.
- Existing source `.env*` files copied to identical relative paths:
  `13`; every copied file was byte-compared successfully. Values were never
  printed, read for interpretation, sourced, or synthesized.
- Descriptor permissions in the fresh workspace: `0600`.
- `setup.sh` was not run. No Docker/Compose command, image build/pull,
  capacity lease, live journey, or provider request was started.
- Provider attempts/effects: `0`. O02 was not rerun. No `outcome_unknown`
  was replayed.

## Remaining proof

After root integrates provider-free lane commits and publishes one shared exact
candidate, root must release one serialized capacity-gated Operator journey
against the real Plane service/API/database/CLI/runtime contracts. That single
journey must exercise O01 and O03-O09: presentation versus live authorization
and scope isolation, trusted-host credential handling, idempotency/replay,
cancellation/timeout/process-death reconciliation without blind unknown
replay, cumulative quotas and budgets, malformed/oversized/duplicate/
out-of-order/cross-bound ingress rejection, bounded concurrent gateway load,
and audit/health/version/readback. Live closure remains unclaimed until that
exact candidate-bound proof and cleanup receipt exist.

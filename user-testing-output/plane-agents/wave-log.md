# Plane Agent dogfood wave log

## Baseline — 2026-08-13

- Candidate branch: `codex/agent-functional-dogfood`
- Candidate baseline: `3f2a478209fb94049376f781d33ddd4b63a038de`
- Source baseline: `1d1012f71c48615bb28b7988ce74c82421aa1d53`
- Product scope: complete non-UI Plane Agent system; no chat UI
- Provider/model: ChatGPT subscription route, `openai-codex/gpt-5.6-luna`, no fallback
- Accepted evidence: G0–G3 and offline G4 baseline
- Functional gap: no successful live provider-backed invocation; the existing
  live test covers only read, denied evaluator canary, submit, and publish
- Rollout: explicitly outside this goal; no G5 stage has executed
- Goal-tool note: the pre-existing Codex goal is paused and points to a GOAL.md
  path absent from the old `preview` checkout. Execution follows the corrected
  GOAL.md on this named candidate branch until integration.

## Wave 0A — fast provider smoke

- Status: dirty — UT-001
- Scope: S00 only
- Rule: do not run the full G3/G4 verifier before this smoke
- Result: fresh live contract validated, but the runner stopped in `0.77s`
  before credential staging because a clean checkout had no `tmp/` parent
- Provider/Plane actions: zero
- Cleanup: clean
- Next: Luna root-fixes UT-001 in the established runner, then the same Maya
  task reruns S00 only; a clean smoke unlocks the three parallel journeys

## Wave 0B — runner-fix retest

- Status: dirty — UT-002
- Candidate: `b414ad6672dd79815ae17ab19b436f2a1b45a173`
- UT-001: closed; clean checkout advanced through credential staging
- Plane lifecycle reached: one run, one invocation, and one visible
  `run_blocker`
- Failure: `runtime_transport_pre_dispatch_failure` / `unclassified_exception`
- Provider attempts and requested Plane operations: zero
- Cleanup: clean
- Next: Luna diagnoses and fixes the established runtime transport owner, then
  the same Maya task reruns S00 only

## Wave 0C — credential fix with temporary API artifact

- Status: dirty — UT-003
- Candidate: `5872cf9664ae0266e661454601d56ade5fab9579`
- UT-002: closed; failure is now correctly classified as configuration
- Temporary fixed-source API artifact built successfully; runtime unchanged
- Plane lifecycle reached: one run, one invocation, one visible `run_blocker`
- Failure: amended source was copied to `/workspace/apps/api`, but the command
  resolver likely imported stale prepared-base code from `/code`
- Provider attempts and requested product operations: zero
- Cleanup: clean; temporary API artifact removed
- Next: Luna fixes the established API artifact executable-source boundary,
  then Maya reruns S00 only

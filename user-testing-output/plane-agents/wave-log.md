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

## Wave 0 — fast provider smoke

- Status: ready
- Scope: S00 only
- Rule: do not run the full G3/G4 verifier before this smoke
- Stop decision: first real boundary failure routes to focused diagnosis; a
  clean smoke unlocks the three parallel persona journeys

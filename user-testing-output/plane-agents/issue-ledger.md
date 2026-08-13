# Plane Agent dogfood issue ledger

Severity: `blocker`, `friction`, `annoyance`, `positive`.

| Issue | Severity | Persona/routes | Evidence | Root cause | Fix owner/commit | Retest | Status |
| ----- | -------- | -------------- | -------- | ---------- | ---------------- | ------ | ------ |

An issue is closed only after the same persona retests the real journey and the
affected route-map cells are clean. Test-only failures without user-visible or
contract impact remain verifier diagnostics rather than dogfood issues.

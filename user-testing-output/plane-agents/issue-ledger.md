# Plane Agent dogfood issue ledger

Severity: `blocker`, `friction`, `annoyance`, `positive`.

| Issue  | Severity | Persona/routes | Evidence                         | Root cause                                                                                           | Fix owner/commit           | Retest | Status |
| ------ | -------- | -------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------- | ------ | ------ |
| UT-001 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Clean checkout has no `tmp/`; live runner creates its child without first creating the owned parent. | pending Luna root-fix task | S00    | open   |

An issue is closed only after the same persona retests the real journey and the
affected route-map cells are clean. Test-only failures without user-visible or
contract impact remain verifier diagnostics rather than dogfood issues.

# Plane Agent dogfood issue ledger

Severity: `blocker`, `friction`, `annoyance`, `positive`.

| Issue  | Severity | Persona/routes | Evidence                         | Root cause                                                                                                                      | Fix owner/commit                           | Retest                       | Status |
| ------ | -------- | -------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ---------------------------- | ------ |
| UT-001 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Clean checkout has no `tmp/`; live runner creates its child without first creating the owned parent.                            | `b414ad6672dd79815ae17ab19b436f2a1b45a173` | Wave 0B passed this boundary | closed |
| UT-002 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Resolver accepted only legacy XAI material and reduced credential failure to an unclassified transport exception.               | `5872cf9664ae0266e661454601d56ade5fab9579` | Wave 0C classified boundary  | closed |
| UT-003 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | G4 API artifact copies fixed source to `/workspace/apps/api`, but the resolver imports stale prepared-base source from `/code`. | pending Luna API artifact root-fix task    | S00                          | open   |

An issue is closed only after the same persona retests the real journey and the
affected route-map cells are clean. Test-only failures without user-visible or
contract impact remain verifier diagnostics rather than dogfood issues.

# Plane Agent dogfood issue ledger

Severity: `blocker`, `friction`, `annoyance`, `positive`.

| Issue  | Severity | Persona/routes | Evidence                         | Root cause                                                                                                                       | Fix owner/commit                           | Retest                        | Status |
| ------ | -------- | -------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------- | ------ |
| UT-001 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Clean checkout has no `tmp/`; live runner creates its child without first creating the owned parent.                             | `b414ad6672dd79815ae17ab19b436f2a1b45a173` | Wave 0B passed this boundary  | closed |
| UT-002 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Resolver accepted only legacy XAI material and reduced credential failure to an unclassified transport exception.                | `5872cf9664ae0266e661454601d56ade5fab9579` | Wave 0C classified boundary   | closed |
| UT-003 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | G4 API artifact copied fixed source to `/workspace/apps/api`, but the resolver imported stale prepared-base source from `/code`. | `1793f338342b93f8a1655f5131aab461d2b68b65` | Wave 0D module paths passed   | closed |
| UT-004 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Candidate API artifact did not install `plane-agent-runtime-credential-resolver` at its configured `/usr/local/bin` path.        | `642f3eebb4755a7b203f235cd9261b26d18a57ab` | Wave 0E artifact proof passed | closed |
| UT-005 | blocker  | Maya / S00     | `waves/wave-0-provider-smoke.md` | Real broker/lease/resolver invocation configuration rejects before provider dispatch despite a proven candidate resolver image.  | Luna live credential-handoff root-fix task | S00 Wave 0F                   | open   |

An issue is closed only after the same persona retests the real journey and the
affected route-map cells are clean. Test-only failures without user-visible or
contract impact remain verifier diagnostics rather than dogfood issues.

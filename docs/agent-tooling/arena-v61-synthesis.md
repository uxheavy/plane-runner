# V61 Arena synthesis

## Frame

The V61 artifact is one provider-free Plane source candidate derived from V60
source `021b8f37ad895fe78ed3eefe04aee2653a57e243`. The rubric is: preserve the
existing Plane/Hermes boundaries; make the Worker mutation commission execute
through Code Mode without weakening denied controls; make Manager replay proof
durable and zero-delta; require Operator queued-to-active lease binding plus
rotate/revoke/expiry at dispatch and callback; retain bounded evidence only;
and keep the result free of candidate notes, secrets, provider calls, and live
journeys.

## Picks

- Worker base `db44bbac465a3ab51e57cec475abb5b93f6e8a61` (judge 23/25):
  selected for the aggregate W01-W08 mutation commission and exact composition
  regression. The temporary candidate note was excluded.
- Manager base `88d3616e108e1e3b361451619113cf52df32972b` (judge 25/25):
  selected for durable succeeded-identity plus zero-delta replay proof. The
  temporary candidate note was excluded. `c81781e973` shell promotion and
  `6f5618211` shared latch were rejected.
- Operator base `cb14d8f4801a854c891bde8aa4c2d9e0e6ed948c`: selected for the
  queued-to-active bind and rotate/revoke/expiry checks at dispatch and callback.
  Judge: 22/25; selected over A 21/25 for the preserved issue-without-invocation bind and nine-predicate lifecycle proof.

## Grafts and rejections

The Operator graft was taken from `034bd16c7b3574b74689d471f000c2b962937151`:
`route_evidence` plumbing and the central O04 expectation gate, the owner-only
`agent_g4_operator_route` module pattern while retaining the B nine predicates
and the issue-without-invocation-then-bind path, and the missing-route
projection assertion. A fake already-bound queued lease, the inline 140-line
helper/manual gate duplication, and raw secret/digest/path retention were
rejected.

No temporary Arena candidate notes were grafted. ADR-0001 through ADR-0010,
Plane authority, hidden Hermes, the single gateway, publication boundaries,
and the exact seven-file environment-copy rule remain unchanged.

## Verification

Focused Worker, Manager, and Operator tests, compilation, manifest/schema/hash
checks, diff checks, and candidate binding are required before the one V61
source commit and sole wrapper refreeze. Provider, live, Compose journeys, and
broad historical G3/G4/G5 ceremony are excluded.

# Decision Register

Each row contains one decision. Importance is intentionally left as `_/10` for product ranking.

## Accepted

| ID      | Decision                                                                              | Importance |
| ------- | ------------------------------------------------------------------------------------- | ---------- |
| ATD-001 | External agents access Plane through MCP.                                             | \_/10      |
| ATD-002 | Plane's existing Python MCP server remains supported.                                 | \_/10      |
| ATD-003 | Plane-native Hermes agents use native Hermes tools.                                   | \_/10      |
| ATD-004 | Plane-native Hermes agents receive direct semantic Plane tools.                       | \_/10      |
| ATD-005 | Plane-native Hermes agents receive TypeScript Code Mode.                              | \_/10      |
| ATD-006 | Code Mode exposes `docs`.                                                             | \_/10      |
| ATD-007 | Code Mode exposes `search`.                                                           | \_/10      |
| ATD-008 | Code Mode exposes `execute`.                                                          | \_/10      |
| ATD-009 | Common Plane operations are eager native tools.                                       | \_/10      |
| ATD-010 | Remaining supported Plane operations are progressively discoverable.                  | \_/10      |
| ATD-011 | Direct tools are an ergonomic surface rather than a security tier.                    | \_/10      |
| ATD-012 | Catalog visibility is identical for every Plane identity.                             | \_/10      |
| ATD-013 | Catalog visibility does not imply execution permission.                               | \_/10      |
| ATD-014 | Plane's live authorization model decides every operation.                             | \_/10      |
| ATD-015 | The tooling layer does not duplicate Plane authorization with an operation allowlist. | \_/10      |
| ATD-016 | Plane-native agents have dedicated Plane identities.                                  | \_/10      |
| ATD-017 | Each Plane-native agent has one revocable Plane credential.                           | \_/10      |
| ATD-018 | Hermes stores Plane agent credentials in trusted host state.                          | \_/10      |
| ATD-019 | Generated TypeScript never receives Plane credentials.                                | \_/10      |
| ATD-020 | The initial architecture does not mint run-bound capability tokens.                   | \_/10      |
| ATD-021 | The initial architecture does not mint per-operation credentials.                     | \_/10      |
| ATD-022 | Native direct tools cross the Plane Operation Gateway.                                | \_/10      |
| ATD-023 | Native Code Mode operations cross the Plane Operation Gateway.                        | \_/10      |
| ATD-024 | External MCP operations converge on the Plane Operation Gateway.                      | \_/10      |
| ATD-025 | Agents never access Plane's database directly.                                        | \_/10      |
| ATD-026 | The Plane Operation Gateway initially lives inside the Plane API service.             | \_/10      |
| ATD-027 | The supported catalog starts from Plane's public OpenAPI surface.                     | \_/10      |
| ATD-028 | A curated overlay enriches generated operation schemas.                               | \_/10      |
| ATD-029 | Explicit agent-native operations may supplement the public API.                       | \_/10      |
| ATD-030 | Private UI and session routes are not automatically agent-facing.                     | \_/10      |
| ATD-031 | Approval policy is evaluated separately from authorization.                           | \_/10      |
| ATD-032 | Approval is evaluated for each inner Code Mode operation.                             | \_/10      |
| ATD-033 | Approval never grants absent Plane permission.                                        | \_/10      |
| ATD-034 | Hermes's existing live approval lifecycle is reused.                                  | \_/10      |
| ATD-035 | Approval resumes the exact tool call in the same logical turn.                        | \_/10      |
| ATD-036 | A pending approval does not survive Hermes or container restart.                      | \_/10      |
| ATD-037 | Restart while awaiting approval fails the run.                                        | \_/10      |
| ATD-038 | Concurrent admitted sibling operations may continue while one waits for approval.     | \_/10      |
| ATD-039 | Explicitly declared groups may be preflighted before concurrent dispatch.             | \_/10      |
| ATD-040 | Concurrent groups return per-operation outcomes.                                      | \_/10      |
| ATD-041 | Concurrent groups are not represented as database transactions.                       | \_/10      |
| ATD-042 | Supported mutations use idempotency when available.                                   | \_/10      |
| ATD-043 | An indeterminate non-idempotent mutation returns `outcome_unknown`.                   | \_/10      |
| ATD-044 | `outcome_unknown` is never retried blindly.                                           | \_/10      |
| ATD-045 | Model-visible results are always bounded.                                             | \_/10      |
| ATD-046 | Oversized authoritative results may be stored as temporary artifacts.                 | \_/10      |
| ATD-047 | Temporary artifacts are readable through bounded read tools.                          | \_/10      |
| ATD-048 | Durable audit does not retain bulky full results by default.                          | \_/10      |
| ATD-049 | Durable audit retains a result hash and bounded summary.                              | \_/10      |
| ATD-050 | Every attempted operation produces append-only audit evidence.                        | \_/10      |
| ATD-051 | Model-written TypeScript runs inside the disposable Hermes run container.             | \_/10      |
| ATD-052 | Model-written TypeScript runs in a restricted child isolate.                          | \_/10      |
| ATD-053 | The child isolate has no ambient network access.                                      | \_/10      |
| ATD-054 | The child isolate has no package-installation access.                                 | \_/10      |
| ATD-055 | The child isolate has no subprocess access.                                           | \_/10      |
| ATD-056 | The child isolate has no unrelated filesystem access.                                 | \_/10      |
| ATD-057 | The child isolate reaches Plane only through credential-free host RPC.                | \_/10      |
| ATD-058 | Audit metadata pins exact catalog and adapter versions.                               | \_/10      |
| ATD-059 | Audit metadata pins the TypeScript runtime version.                                   | \_/10      |
| ATD-060 | External MCP compatibility is versioned independently from native tool ergonomics.    | \_/10      |

## Superseded

| ID      | Superseded decision                                                                  | Replacement                                                     | Importance |
| ------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------- | ---------- |
| ATS-001 | Pause Code Mode by releasing the container and replaying prior calls after approval. | ATD-034 and ATD-035 reuse Hermes's live same-turn approval.     | \_/10      |
| ATS-002 | Mint a short-lived assertion for every Hermes run.                                   | ATD-017 uses one revocable credential per Plane agent identity. | \_/10      |

## Open

| ID      | Open decision                                         | Importance |
| ------- | ----------------------------------------------------- | ---------- |
| ATO-001 | Approve the first pilot scope.                        | \_/10      |
| ATO-002 | Select the initial eager native tools.                | \_/10      |
| ATO-003 | Define the first supported operation boundary.        | \_/10      |
| ATO-004 | Define the curated overlay fields.                    | \_/10      |
| ATO-005 | Define direct-tool promotion criteria.                | \_/10      |
| ATO-006 | Define eager-tool retirement criteria.                | \_/10      |
| ATO-007 | Define per-operation result thresholds.               | \_/10      |
| ATO-008 | Define cumulative execution result thresholds.        | \_/10      |
| ATO-009 | Define temporary artifact retention.                  | \_/10      |
| ATO-010 | Define credential issuance and storage mechanics.     | \_/10      |
| ATO-011 | Define credential rotation and revocation operations. | \_/10      |
| ATO-012 | Define catalog compatibility rules.                   | \_/10      |
| ATO-013 | Define native tool compatibility rules.               | \_/10      |
| ATO-014 | Define external MCP migration order.                  | \_/10      |
| ATO-015 | Define numeric production success targets.            | \_/10      |
| ATO-016 | Define audit retention and redaction periods.         | \_/10      |
| ATO-017 | Define which operation groups benefit from preflight. | \_/10      |
| ATO-018 | Define the exact TypeScript isolate technology.       | \_/10      |

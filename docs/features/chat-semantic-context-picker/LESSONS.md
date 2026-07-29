# Lesson Ledger: Chat Semantic Context Picker

## Structural completion gate

Implementation fingerprint: `sha256:899cea747d4e2bd7b32ee24955b1945abec95299dbde93e8eb6bc1ec43923b9f`

`pnpm verify:chat-context` recomputes this fingerprint from the feature contracts,
implementation, API wiring, tests, and release scripts. A mismatch blocks release
until the relevant feature documentation and this ledger are reviewed together.

## Human corrections and product constraints

| Lesson                                                                                              | Disposition   | Durable mechanism                                                                                                                   |
| --------------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Keep the dossier at `docs/features/chat-semantic-context-picker`.                                   | Encoded       | The documentation contract requires the ledger, goal, result, worklog, plan, and all six ADRs at that exact root.                   |
| Use the dedicated `chat-semantic-context-picker-core` branch and let Codex oversee the non-UI work. | Judgment-only | Branch and ownership are workflow choices recorded in `README.md` and `RESULT.md`; product code must remain branch-independent.     |
| Prior Cursor and Codex inspector use already validated the product idea.                            | Judgment-only | Product validation remains a single-user product decision; `README.md` records it without inventing a second research gate.         |
| Keep the non-UI core separate from the user-owned UI branch.                                        | Encoded       | `@plane/chat-context` has no UI dependency; the dummy composer contract and M7 handoff keep presentation external.                  |
| The missing Plane AI composer must not block the core.                                              | Encoded       | `SemanticContextComposerAdapter` uses hydration and consumer ports; fixtures and the dummy consumer test the absent integration.    |
| Reuse Plane's TypeScript, React, and Django stack and proven open-source selection code.            | Encoded       | Exact `react-grab` catalog pin, Plane-owned Adapter, Chrome tests, and the bundle gate enforce the boundary.                        |
| Use one production visual renderer rather than two screenshot stacks.                               | Encoded       | Exact `html2canvas-pro` pin, one exported renderer subpath, separate bundle gate, and real-pixel Chrome test.                       |
| Codex browser annotation separates semantic metadata from pixels.                                   | Encoded       | Plane uses typed semantic references independently from `semantic: false` visual attachments; ADR 0006 records the source boundary. |
| Update the feature dossier whenever implementation or verification changes.                         | Encoded       | `verify-feature-docs.mjs` fingerprints the implementation and is called by the primary release verifier.                            |
| A staged rollout is unnecessary for the sole current user.                                          | Judgment-only | GOAL and delivery plan exclude rollout infrastructure; revisit if the release audience changes.                                     |

## Failed checks and unexpected outcomes

| Lesson                                                                                                   | Disposition   | Durable mechanism                                                                                                                                  |
| -------------------------------------------------------------------------------------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Point capture initially widened a field selection to its parent entity.                                  | Encoded       | Browser contract tests require the fresh top field only and reject silent parent fallback.                                                         |
| Test fixtures initially reused usernames and failed to authenticate an owner client.                     | Encoded       | Django contract fixtures create distinct users and exercise authenticated owner, member, guest, revoked, and denied cases.                         |
| Broad failure types and mutating sort logic failed package checks.                                       | Encoded       | Strict TypeScript, zero-warning package lint, format, and build gates run in `verify-release.sh`.                                                  |
| A simulated renderer test did not prove that the selected screenshot stack produced pixels.              | Encoded       | `html2canvas-pro-visual-renderer.browser.test.ts` decodes and checks an exact modern-CSS PNG crop.                                                 |
| Five public failure variants lacked direct proof during the first completion audit.                      | Encoded       | Composer and visual contract suites exercise every exported failure code and lifecycle branch.                                                     |
| Permission checks at the HTTP serializer alone could be bypassed by direct service use.                  | Encoded       | The hydration service revalidates references; a direct-service Django regression test enforces it.                                                 |
| The first documentation verifier serialized file reads and failed the repository pre-commit lint policy. | Encoded       | File discovery, hashing, and existence checks use `Promise.all`; the zero-warning pre-commit lint gate enforces the pattern.                       |
| Verification created a local `.pnpm-store/` and dirtied the worktree.                                    | Encoded       | Root `.gitignore` excludes the generated store.                                                                                                    |
| Registry signature and Markdown tool downloads failed without network access.                            | Judgment-only | This is an execution-environment permission condition; exact commands are retried with approved network access rather than weakening verification. |
| The commit hook reformatted Markdown after the first documentation check.                                | Encoded       | The pre-commit formatter normalizes staged Markdown; the completion workflow reruns Markdown validation against committed content.                 |

## Architectural decisions

| Decision                                                                      | Disposition | Durable mechanism                                                                                        |
| ----------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------- |
| Isolate React Grab primitives behind a Plane Adapter.                         | Encoded     | ADR 0001, adapter Chrome tests, and forbidden bundle markers.                                            |
| Expose only `register`, `select`, and `dispose` from the deep core Interface. | Encoded     | ADR 0002, discriminated TypeScript contracts, and public-contract tests.                                 |
| Use Plane block IDs and block-relative editor offsets.                        | Encoded     | ADR 0003 and live Tiptap/Yjs block, range, replacement, and privacy tests.                               |
| Treat browser values as observations, never authorization.                    | Encoded     | ADR 0004, bounded Django hydration, allowlists, and permission regressions.                              |
| Integrate the absent composer through narrow ports.                           | Encoded     | ADR 0005, runtime response parsing, ordered correlation, denied-value removal, and dummy consumer tests. |
| Keep visual fallback in memory behind a privacy and review gate.              | Encoded     | ADR 0006, denied-surface checks, one-time confirmation lifecycle, size limits, and no storage port.      |

## Deferred boundary

| Item                                                                            | Disposition | Follow-up                                                                                                                             |
| ------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Actual activation, crosshair, hover, chip, preview, removal, and send workflow. | Deferred    | M7 belongs to the user-owned UI branch because this checkout does not contain the target composer. Add the UI-to-composer test there. |
| Semantic coverage for generic Plane surfaces without stable domain identity.    | Deferred    | Add registrations only when M7 identifies concrete entity-aware call sites; do not infer identity from display text or DOM paths.     |

# Semantic Chat Context Guide

## Scope

This file governs `packages/chat-context`. The repository `AGENTS.md` still
applies unless a rule here is more specific.

## Local Responsibility

This package owns the reusable, non-UI semantic selection core. The corresponding
authorization boundary lives in `apps/api/plane/app/context_hydration.py`. Product
and contract rationale live in `docs/features/chat-semantic-context-picker/`.

## Canonical Owners

| Concern                                                | Canonical Path                                                             |
| ------------------------------------------------------ | -------------------------------------------------------------------------- |
| Public TypeScript contracts and runtime guards         | `src/contracts.ts`, `src/composer-integration.ts`                          |
| Selection lifecycle and semantic registration          | `src/semantic-context-picker.ts`                                           |
| Plane store and live-editor observations               | `src/plane-entity-context-source.ts`, `src/plane-editor-context-source.ts` |
| Visual privacy and optional renderer                   | `src/visual-context.ts`, `src/html2canvas-pro.ts`                          |
| Server validation, authorization, and canonical values | `apps/api/plane/app/context_hydration.py`                                  |
| Full release gate                                      | `verify-release.sh`, `.github/workflows/chat-semantic-context.yml`         |

## Architecture Rules

- Keep activation controls, overlays, preview chips, and send UI outside this
  package. Integrate an absent composer through the existing ports.
- Semantic references carry stable Plane identifiers and project scope, never DOM
  text, arbitrary object paths, cached records, or permission claims.
- Treat browser values as observations. Remove denied observations after the
  authenticated Django hydration boundary and before composer handoff.
- Keep screenshot rendering in the optional `./html2canvas-pro` entry point.
  Sensitive-surface denial must happen before rendering, and visual context must
  remain in memory pending explicit review.
- When a reference shape or allowlist changes, update the TypeScript type, runtime
  guard, Django validator/projector, fixtures, and both browser and API tests as one
  contract change.

## Working Method

| Change                                     | Required Method                                                                                                            |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Add an entity or field                     | Add the client projector and server allowlist/projector together; cover allowed, denied, missing, and cross-project cases. |
| Change editor metadata                     | Confirm the real Tiptap attribute meaning in `packages/editor`; expose only an explicit privacy-safe projection.           |
| Change cancellation or navigation behavior | Recheck the signal after every awaited port and add a browser regression test.                                             |
| Change visual capture                      | Prove sensitive-node denial occurs before renderer invocation and rerun the bundle guard.                                  |

## Current Gotchas

| Gotcha                                                                | Correct Action                                                                                  |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| The composer UI is not in this checkout.                              | Preserve the consumer port; do not invent presentation code here.                               |
| Docker API tests require `apps/api/.env`.                             | Run `./setup.sh` once locally. CI creates the API env from `.env.example`. Never commit `.env`. |
| Browser tests use Playwright with Chrome.                             | Install or expose Chrome before treating an environment failure as a product failure.           |
| The release script tears down the isolated Docker test stack on exit. | Do not run it against a shared development stack.                                               |

## Local Verification

- TypeScript only: `pnpm --filter @plane/chat-context check:types`
- Browser behavior: `pnpm --filter @plane/chat-context test`
- Production bundles: `pnpm --filter @plane/chat-context build && pnpm --filter @plane/chat-context verify:bundle`
- Complete cross-stack gate from the repository root: `pnpm verify:chat-context`

The complete command is enforced for relevant pull requests by
`.github/workflows/chat-semantic-context.yml`.

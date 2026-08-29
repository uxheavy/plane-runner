# Repository Map

## Scope

This file governs the repository unless a closer `AGENTS.md` applies to the files
being changed.

## Commands

- `pnpm dev` - Start all dev servers (web:3000, admin:3001)
- `pnpm build` - Build all packages and apps
- `pnpm check` - Run all checks (format, lint, types)
- `pnpm check:lint` - OxLint across all packages
- `pnpm check:types` - TypeScript type checking
- `pnpm fix` - Auto-fix format and lint issues
- `pnpm turbo run <command> --filter=<package>` - Target specific package/app
- `pnpm --filter=@plane/ui storybook` - Start Storybook on port 6006

## Sources of Truth

| Concern | Authoritative location |
| --- | --- |
| JavaScript/TypeScript format and lint | `.oxfmtrc.json`, `.oxlintrc.json`, `docs/linting.md` |
| Package commands and dependency versions | root and package-level `package.json` files, `pnpm-workspace.yaml` |
| Task graph | `turbo.json` |
| Path ownership | `CODEOWNERS` |
| Pull-request enforcement | `.github/workflows/` |
| API test setup and conventions | `apps/api/tests/RUNNING_TESTS.md`, `apps/api/tests/TESTING_GUIDE.md` |

## Scoped Maps

| Path | Read first |
| --- | --- |
| `packages/chat-context/` | `packages/chat-context/AGENTS.md` |
| `packages/tailwind-config/` | `packages/tailwind-config/AGENTS.md` |

## Change Evidence

- Run the narrowest relevant package checks before the repository-wide checks.
- Report exact commands and results; name checks that were skipped or unavailable.
- CI is authoritative. The pre-commit hook is a fast local aid, not merge proof.
- Get human approval before deployments, destructive operations, or other external writes.

## Backend Tests (Docker)

The Django/pytest suite for `apps/api` runs in an isolated stack defined by `docker-compose-test.yml` at the repo root.

Prereq (once): `./setup.sh` — generates `apps/api/.env` from `.env.example`.

- Full suite: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Subset: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit`
- Teardown: `docker compose -f docker-compose-test.yml down -v`

See `apps/api/tests/RUNNING_TESTS.md` for the full walkthrough and troubleshooting; see `apps/api/tests/TESTING_GUIDE.md` for test conventions and fixtures.

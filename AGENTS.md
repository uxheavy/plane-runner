# Agent Development Guide

## Scope

This file governs the repository unless a nested `AGENTS.md` is closer to the changed file.

## Project Identity

Plane is a pnpm/Turborepo monorepo. The Django API and workers live in `apps/api`; browser applications live in `apps/web`, `apps/admin`, and `apps/space`; collaborative transport lives in `apps/live`.

## Canonical Owners

| Concern                        | Canonical Location                              |
| ------------------------------ | ----------------------------------------------- |
| Local environment bootstrap    | `setup.sh` and each app's `.env.example`        |
| Local container topology       | `docker-compose-local.yml`                      |
| Public API and file routing    | `apps/proxy/Caddyfile.ce`                       |
| Community self-host deployment | `deployments/cli/community/`                    |
| Backend tests                  | `docker-compose-test.yml` and `apps/api/tests/` |

## Architecture Rules

- Local browser-facing API and file traffic share the proxy origin. API and worker containers reach MinIO through its Docker service name. These are different network boundaries; do not make one endpoint value serve both.
- Treat `.env.example` files as reproducible local defaults and `.env` files as untracked machine state. Never commit credentials or generated secrets.
- Encode recurring corrections in code, tests, validation, or automation first. Add an `AGENTS.md` gotcha only when the decision still requires human judgment.

## Working Method

| Situation                                           | Required Method                                                                                                             |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Initial local setup                                 | Run `./setup.sh`, then `docker compose -f docker-compose-local.yml up -d`, then `pnpm dev`.                                 |
| Changing local env, storage, or proxy configuration | Update the canonical files together, run `pnpm check:local-dev`, then run `pnpm check:local-dev:runtime` with the stack up. |
| Debugging an upload                                 | Prove each hop separately: browser asset request → signed upload URL → proxy route → MinIO object → worker metadata task.   |
| Finishing after a correction or failed check        | Review the whole task, encode every recurring/systemic lesson, and explicitly disposition one-off or judgment-only lessons. |
| Finishing an authorized repository change           | Remove incidental artifacts, commit the validated logical change, and verify `git status --short` is empty.                 |

## Current Gotchas

| Gotcha                                      | Why It Matters                                                                                                            | Correct Action                                                                                                     |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `setup.sh` preserves existing `.env` files. | Re-running setup must not destroy local credentials or overrides, but updated examples will not replace old local values. | Compare the affected `.env` with its `.env.example` and update only the intended keys.                             |
| Local app env files are named `.env`.       | Creating parallel `.env.local` files can silently override the setup-generated values in Vite.                            | Use the files created by `setup.sh`; inspect and remove stale overrides when behavior disagrees with the examples. |

## Commands

- `pnpm dev` — start all frontend and package development processes.
- `pnpm build` — build all packages and apps.
- `pnpm check` — run repository format, lint, and type checks.
- `pnpm check:local-dev` — validate the local env/proxy/storage contract and Docker Compose syntax.
- `pnpm check:local-dev:runtime` — verify the running proxy, signed upload, MinIO object, worker access, and cleanup.
- `pnpm check:lint` — run OxLint across all packages.
- `pnpm check:types` — run TypeScript type checking.
- `pnpm fix` — apply available format and lint fixes.
- `pnpm turbo run <command> --filter=<package>` — run a targeted task.
- `pnpm --filter=@plane/ui storybook` — start Storybook on port 6006.

## Code Style

- Use `workspace:*` for internal dependencies and `catalog:` for external dependencies.
- Keep TypeScript strict and fully typed.
- Format with oxfmt and lint with the shared `.oxlintrc.json` configuration.
- Use MobX stores in `packages/shared-state` for shared client state.
- Build shared components in `@plane/ui` and verify them in Storybook when appropriate.

## Backend Tests

The Django/pytest suite runs in the isolated stack defined by `docker-compose-test.yml`.

- Prerequisite: `./setup.sh`
- Full suite: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Unit subset: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit`
- Teardown: `docker compose -f docker-compose-test.yml down -v`

See `apps/api/tests/RUNNING_TESTS.md` for execution details and `apps/api/tests/TESTING_GUIDE.md` for conventions.

## Current Enforcement State

- `pnpm check:local-dev` enforces the local network-boundary defaults and validates `docker-compose-local.yml`.
- `pnpm check`, OxLint, oxfmt, and TypeScript enforce application code quality.
- `pnpm check:local-dev:runtime` enforces the end-to-end upload path when storage or proxy behavior changes.

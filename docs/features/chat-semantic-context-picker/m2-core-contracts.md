# M2 Evidence: Core Contracts and Registry

## Delivered boundary

| Surface        | Delivered behavior                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------- |
| References     | Versioned entity, allowlisted work-item field, and editor-block identities                                          |
| Lifecycle      | `register`, `select`, and idempotent `dispose`                                                                      |
| Preview        | Ordered semantic candidates without value reads                                                                     |
| Point capture  | Fresh value from the top candidate only                                                                             |
| Region capture | Bounded, spatially ordered, deduplicated items with partial warnings                                                |
| Failures       | Versioned `NO_TARGET`, `TARGET_GONE`, `UNSUPPORTED`, `VALUE_UNAVAILABLE`, `ABORTED`, and `TOO_MANY_TARGETS` results |
| Isolation      | React Grab remains behind the Plane acquisition Adapter                                                             |

Registrations copy their typed identity, stale disposers cannot remove replacement
registrations, detached elements are discarded, and a newer operation or disposal
aborts active capture. Preview never invokes a context source.

## Test evidence

| Gate                      | Result                                                                                              |
| ------------------------- | --------------------------------------------------------------------------------------------------- |
| TDD RED                   | New suite failed because `createSemanticContextPicker` was absent; existing M1 tests remained green |
| First implementation pass | Six of seven tests passed; point capture incorrectly included its parent entity                     |
| Contract correction       | Point capture now selects only the top candidate; preview retains the ancestor stack                |
| Browser suite             | Two files and ten tests passed in stable Google Chrome                                              |
| Type safety               | Strict TypeScript passed                                                                            |
| Lint and format           | OxLint passed with zero warnings; oxfmt check passed                                                |
| Production build          | ESM and declaration build passed                                                                    |
| Bundle guard              | Consumer bundle passed at 14,913 gzip bytes against the 30,000-byte ceiling                         |

## Commands

```bash
cd packages/chat-context
./node_modules/.bin/vitest run
./node_modules/.bin/tsc -p tsconfig.json --noEmit
../../node_modules/.pnpm/oxlint@1.51.0/node_modules/oxlint/bin/oxlint --max-warnings=0 .
../../node_modules/.pnpm/oxfmt@0.35.0/node_modules/oxfmt/bin/oxfmt --check .
./node_modules/.bin/tsdown
node scripts/verify-production-bundle.mjs
```

## Deferred ownership

| Capability                                   | Milestone |
| -------------------------------------------- | --------- |
| Plane store labels and values                | M3        |
| Tiptap/Yjs live content                      | M4        |
| Server authorization and canonical hydration | M5        |
| Composer-independent fixtures and consumer   | M6        |
| Visual fallback                              | M8        |

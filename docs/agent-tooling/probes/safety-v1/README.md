# Safety v1 generated TypeScript probe ABI

This directory contains generated-code probes for EV-021 through EV-028 and the EV-026 parser-only import sources. They are qualification fixtures, not a Plane or Hermes implementation.

## Scenario orchestrator ABI

Every executable scenario module default-exports one closed function:

```ts
run(fixture: ScenarioFixture, plane: NarrowPlaneCallback): Promise<ScenarioResult>
```

The callback exposes only the exact operation methods required by that scenario. It carries no credential, endpoint, authority, binding, frame, or raw channel. Each fixture is closed and contains only public operation input plus non-secret canaries.

For EV-023 through EV-026, the module itself owns the complete frozen ordered runtime profile in one invocation and therefore one model isolate. A caller cannot select, skip, duplicate, or reorder a hostile subcase. Every subcase executes fixed computation and successful `plane.work_items.get@1` controls before the hostile operation, requires the exact structured policy code, then executes a second fixed computation and successful callback. A resolved hostile operation, wrong denial, failed callback, missing record, or incomplete profile throws. Returned records contain the exact ordinal, probe identity, observed denial, and four control outcomes; they never contain hostile values or Plane bodies. Signed supervisor events, deadlines, listener/backing-store evidence, and final predicate recomputation remain external oracles.

Diagnostic error normalization is frozen to three cases: an explicit top-level `.code`; an explicit nested `.error.code`; or, for the exact digest-pinned Deno runtime, `Deno.errors.NotCapable`, which maps only to the profile entry’s already-frozen expected permission label. Engine `EvalError` maps only to `runtime_codegen_denied`. No message matching, constructor-name matching, generic `Error`, `TypeError`, or producer Boolean is accepted. These generated labels are diagnostic: qualification independently binds the exact attempted API, pinned error class/engine trace, supervisor evidence, and absence of the forbidden effect.

EV-026's 12 parser-only sources are not referenced by `ev026.ts`, are never sent to the trusted data-URL bootstrap, and can never enter a model Worker. The trusted parent owns their exact ordered submission and brackets each one with successful parent computation and authorized-callback controls. Qualification consumes signed parser and callback evidence rather than a harness-supplied Boolean, so an omitted source, missing denial, failed bracket, Worker start, or resolver event cannot pass vacuously.

## Result-shaping programs

- `ev021.ts` issues exactly two work-item reads and exactly two sequential bounded artifact reads. It validates contiguous reconstruction, length, SHA-256, and terminal cursor without returning authoritative bodies.
- `ev022.ts` issues exactly five sequential work-item reads and no artifact reads. It returns the frozen six-field five-record summary; the exact-128-KiB control is a separate harness run and never enters this program.
- `ev027.ts` issues exactly eight fresh callback controls. It returns exactly eight `{ordinal, work_item_id}` records, preserving public identity correspondence while exposing no callback frame or authority.
- `ev028.ts` starts exactly eight reads synchronously in ordinal order before awaiting `Promise.all`. It returns only `{ordinal, work_item_id, attempt_id, audit_ref}` in submitted order. Admission/release scheduling remains harness-owned.

For EV-027, the evaluation seam captures and mutates frames between each pair outside generated code:

- pair 1: `forged_authority_fields`;
- pair 2: `sibling_binding`;
- pair 3: `cross_run_binding`;
- pair 4: `accepted_frame_replay`.

Generated code cannot request, construct, retain, inspect, replay, or alter any frame. The verifier joins each attack to one host-security record and zero gateway attempts while independently proving all eight model callbacks succeeded.

## EV-026 runtime and parser probes

EV-026 contains 17 runtime-selected probes and 12 dedicated parser-source programs: exactly 29 hostile subcases. The runtime-selected set covers four filesystem/process operations, three direct persistence surfaces, two nested Worker constructors, five runtime-code-generation paths, and three Node builtin-module recovery surfaces. Its model program owns 34 callback controls around those 17 probes. The harness owns 24 callback controls around the six static-import and six variable-dynamic-import parser submissions, for 58 controls total.

The second runtime subcase, and second filesystem read, renders `${PINNED_LAUNCHER_PATH}` from the strictly validated `pinned_launcher_path` fixture field and executes exactly `Deno.readTextFile("${PINNED_LAUNCHER_PATH}")`. It must return `filesystem_denied`, proving that the model Worker inherited no launcher-scoped read grant. Missing-file, wrong-path, or successful-read results do not qualify.

Each `ev026.static-*.ts` program has exactly one hostile static import and an unconditional module-body error. Each `ev026.dynamic-*.ts` program binds exactly one hostile specifier to a local variable, passes that variable to exactly one dynamic import expression, and has an unconditional module-body error. Every source enters the production trusted parser/transpiler exactly like any other submitted generated program. A conforming parser rejects it with `module_specifier_denied` before model Worker construction, Deno resolution, fetch, or module-body execution. The supervisor brackets each parser submission with before/after compute and authorized-callback controls in the unchanged parent/harness isolate, then proves supervisor health and a fresh clean Worker canary. A parser source is never dynamically imported by the trusted bootstrap.

Before hashing and submitting each of `ev026.static-remote.template.ts` and `ev026.dynamic-remote.template.ts`, the harness replaces exactly one occurrence each of `__HARNESS_DOMAIN__` and `__RUN_TAG__` with schema-validated DNS-label text. The rendered specifier is therefore exactly `https://module.${HARNESS_DOMAIN}/ev026-${RUN_TAG}.ts`. Each parser-submission attestation binds the rendered source digest, not the template digest.

The two Worker probes use `data:` and `blob:` entry URLs. Each payload would attempt `localStorage`, Cache API, and `Deno.openKv` using the fixture nonce if construction succeeded; the production boundary must instead return `worker_creation_denied` before construction. For the blob probe, the harness takes the backing-store baseline after the Blob and its object URL exist. Worker construction and the unreachable payload must add no backing-store delta. Cleanup evidence separately proves revocation and absence of that exact harness-owned Blob artifact.

The five code-generation probes construct the exact data-module dynamic import through indirect `eval`, recovered `Function`, recovered `AsyncFunction`, recovered `GeneratorFunction`, and recovered `AsyncGeneratorFunction` constructors. Each constructed callable is advanced far enough to reach its import if construction is not denied. All five must return `runtime_codegen_denied` at construction/evaluation rather than a module-resolution result.

The three builtin-module recovery probes call exactly `process.getBuiltinModule("module")`, `process.getBuiltinModule("worker_threads")`, and `process.getBuiltinModule("vm")`. Generated code sees only an immutable frozen denial facade whose exact `getBuiltinModule` contract throws `runtime_surface_denied`; `process` is not absent. A verifier-owned global inventory must prove that only this facade is present and that no native process object, require/createRequire surface, module hook, worker constructor, or VM context constructor is reachable. Qualification requires zero hook, worker, and context creation. A missing-global `ReferenceError`, unsupported API, successful recovery, mutable facade, native-process exposure, or later downstream denial does not qualify.

The trusted bootstrap is embedded in the pinned outer launcher and starts as a verified `data:` Worker before dynamically importing the separately verified model source from a trusted `data:` URL. Neither parent nor child receives read permission, and neither launch uses `--unstable-worker-options`. The launcher path probe independently guards against accidental scoped-read inheritance.

Direct and Worker-payload persistence values are identical and deterministic: localStorage key/value `plane:ev026:${nonce}`/`${nonce}`; cache name `plane-ev026-${nonce}`; request URL `https://ev026.invalid/${nonce}`; response body `${nonce}` with exact header `{"content-type":"text/plain"}`; and `Deno.openKv("/tmp/plane-ev026-${nonce}.sqlite3")` with key `["plane","ev026",nonce]` and value `${nonce}`. Denial must occur on the first storage access/open call. Production omits `--unstable-kv` and installs the deterministic `Deno.openKv` denial stub; the isolated positive control uses the same pinned binary with only `--unstable-kv` added.

The programs intentionally contain no credentials or authoritative context. Host-observed policy errors, listener counts, backing-store deltas, process markers, callback traces, and signed supervisor evidence remain the qualification oracles.

# Wave 0 — S00 provider smoke

Status: dirty at the first live-runner boundary. No replay was attempted.

## Candidate and binding

- Candidate checkout: clean disposable clone at wrapper `3f2a478209fb94049376f781d33ddd4b63a038de`.
- Source parent: `1d1012f71c48615bb28b7988ce74c82421aa1d53`.
- API image: `plane-agent-api:g4-1d1012f7`, digest `sha256:0a350d4619c9edd55769ed8efdaa2dc740de551689ec41abd682e73565b6c3f2`, contract `plane.operation/v1`.
- Runtime image: `plane-agent-runtime:hermes-d2e65510-g4-1d1012f7`, digest `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`.
- Hermes: `d2e655101f263329359e7d0de9d0b856202a3e4b`.
- Provider/model: `openai-codex/gpt-5.6-luna`; fallback disabled; provider route is the configured ChatGPT subscription descriptor.
- Fresh authority: `s00-live-20260813T083104Z`; authority SHA-256 `8ef154ef6d692537f77085d87e92eb1c6e64d3ee44fe61d1c5c0953bc12e9d51`; config SHA-256 `f6b27809b0687cbf798862fdbad3b38eb9052f0288e53acb56c48641be6c0eb6`.
- Contract preflight exited 0; command SHA-256 `32756a110745e4b69a3c8627021527a073ac7c434b5cd6659483245674954060`.
- Elapsed live-runner time: approximately `0.77s` (runner exit 2).

Executed command, with the credential-source value intentionally redacted:

```sh
PLANE_G4_EXPECTED_CANDIDATE=3f2a478209fb94049376f781d33ddd4b63a038de \
PLANE_G4_LIVE_AUTHORITY=/private/tmp/plane-s00-authority.json \
PLANE_G4_LIVE_CONFIG=/private/tmp/plane-s00-config.json \
PLANE_G4_LIVE_COMMAND='bash tools/agent-g4-live.sh' \
PLANE_G4_PROVIDER_SECRET_SOURCE=<existing-owner-only-chatgpt-subscription-source> \
bash tools/agent-g4-live.sh
```

## First failing boundary

```text
mkdir: .../plane-s00.v81iv5/tmp: No such file or directory
event=agent.g4.live-runner status=failed expected=invocation-run-directory actual=unavailable suggestion=use-the-repository-owned-tmp-root
event=agent.g4.live-runner.failure phase=credential-staging error_class=unavailable exit_code=2
```

Root cause: a clean clone has no repository-owned `tmp/` directory because Git
does not represent empty directories, while `tools/agent-g4-live.sh` assumes
`${ROOT_DIR}/tmp` exists before creating its per-run directory.

## Provider and Plane evidence

- Provider reached: no. Credential bytes were not read or printed.
- Provider attempts, actors, profiles, assignments, runs, invocations, gateway receipts, outcomes, publications, terminal events, and audit rows: all `0`.
- Replay: not attempted; no historical `outcome_unknown` invocation was replayed.
- Cleanup: no labeled runtime container, network, or volume remained; disposable clones and temporary authority/config files were removed.

No broad verifier, rollout, deployment, or unrelated suite ran.

## Wave 0B — S00 provider smoke retest

Status: dirty at the first product invocation boundary. No replay was
attempted.

- Candidate: `b414ad6672dd79815ae17ab19b436f2a1b45a173`; API/runtime artifacts remain pinned to source `1d1012f71c48615bb28b7988ce74c82421aa1d53` and Hermes `d2e655101f263329359e7d0de9d0b856202a3e4b`; no image refreeze.
- Provider/model: `openai-codex/gpt-5.6-luna`, ChatGPT subscription route, fallback disabled.
- Fresh authority/config: `s00-live-20260813T090120Z-wave0b-r3`; authority SHA-256 `c8e6e6292924742b9585cebe5f844a0fa409be23dbd6b6d98410660ce228fe6f`; config SHA-256 `d48cc556770a5523e9ead28ed9c0b39259ea3dbdc8403c33dfc443572ddaecc6`.
- Contract preflight passed; elapsed live-runner time was approximately `65.5s`.

```text
event=agent.g4.live-runner.failure phase=api-invocation error_class=unspecified exit_code=1
status=failed reasonCode=runtime_transport_pre_dispatch_failure reasonPhase=runtime_transport reasonDetail=unclassified_exception
runRef=c02d4209-106b-4667-b314-086fe2cb3c51 runState=blocked
invocationRef=7ef841e0-efed-45a1-9e2b-68ec1311aeff invocationState=blocked
providerAttempts=[] terminal={present:true,kind:run_blocker}
```

The API created one run and invocation, then the runtime transport failed
before dispatch or provider-attempt intent. GPT-5.6 Luna was not reached. No
permitted read, denied evaluator operation, outcome, publication, requested
operation audit, or replay occurred. Plane correctly recorded one visible
`run_blocker`. Cleanup left no task-owned container, network, volume, checkout,
authority/config file, or Plane test stack. No broad verifier, build, load,
rollout, deployment, or source edit ran.

## Wave 0C — amended API source

Status: dirty at the first runtime-configuration boundary. No replay was
attempted.

- Candidate: `5872cf9664ae0266e661454601d56ade5fab9579`.
- Temporary API artifact: `plane-agent-api:g4-5872cf96-wave0c`, digest `sha256:e17d8a54e97915fcab66a5734a5ac5bd4fe34607c1b1b7e04ef013912a4a2dd1`; source/contract/artifact labels passed.
- Runtime/Hermes artifact remained unchanged.
- Fresh GPT-5.6 Luna authority/config and temporary candidate binding passed validation.
- One live invocation ran for approximately `49s`.

```text
status=failed reasonCode=runtime_configuration_pre_dispatch_failure reasonPhase=runtime_configuration reasonDetail=dispatch_rejected
runRef=12f7fcbb-5c9a-4583-8386-aad1e2fa411f runState=blocked
invocationRef=12705a90-6b88-4eaa-87ba-2d7de3983994 invocationState=blocked
providerAttempts=[] terminal={present:true,kind:run_blocker}
```

Sanitized inspection confirmed that the staged source is owner-only and has
the exact supported Codex auth key/type shape. The temporary image nevertheless
rejected credential resolution. `apps/api/Dockerfile.g4` copies amended source
to `/workspace/apps/api`, while the installed command resolver imports the
prepared base's `/code`; the built artifact is therefore likely executing the
stale parser. No provider, tool, gateway, outcome, publication, or replay action
occurred. One visible lifecycle blocker was recorded. Temporary image, checkout,
authority/config, and Docker resources were removed; prepared base/runtime
images were preserved. No broad verifier, load, G5, rollout, or deployment ran.

## Wave 0D — pre-live artifact proof

Status: dirty before live execution. No authority/config or S00 invocation ran.

- Candidate: `1793f338342b93f8a1655f5131aab461d2b68b65`.
- Temporary API artifact digest: `sha256:40b21ee2077bc916cd277b9acdf626c631deef4cf7db32fb1d01bea8516e1c32`; labels passed.
- Runtime/Hermes remained unchanged.
- Network-isolated module proof passed: `plane`, runtime credentials, and runtime config all resolved under `/workspace/apps/api`.

```text
/workspace/apps/api/plane/__init__.py
/workspace/apps/api/plane/agent/runtime/credentials.py
/workspace/apps/api/plane/agent/runtime/config.py
FileNotFoundError: [Errno 2] No such file or directory: '/usr/local/bin/plane-agent-runtime-credential-resolver'
```

The expected installed resolver is absent because `apps/api/Dockerfile.g4`
copies the candidate source but does not install its resolver script at the
path used by production configuration. The synthetic owner-only Codex document
was never resolved, and no credential value was displayed. No provider or Plane
product action occurred. The proof container, temporary image, synthetic file,
checkout, and Colima resources were cleaned; prepared base/runtime images were
preserved. No broad verifier, load, G5, rollout, or deployment ran.

## Wave 0E — packaged resolver retest

Status: dirty at the live credential-handoff boundary. No replay was attempted.

- Product source: `0ae680f418afe1da78fc697cf83e53a9d8d280df`.
- Temporary API image: `plane-agent-api:g4-0ae680f4-wave0e`, digest `sha256:872d2e12c8077f42ef3fd55b38670817e037fd297c89fb9322c70ccec9f13862`; source and contract labels passed.
- Runtime/Hermes image remained unchanged.
- Fresh authority/config: `s00-live-20260813T102933Z-wave0e`; GPT-5.6 Luna through the ChatGPT subscription route; fallback disabled.
- Build took approximately `1.7s`; the live runner exited after approximately `81s`.

The required network-disabled proof passed before any live action:

```text
/workspace/apps/api/plane/__init__.py
/workspace/apps/api/plane/agent/runtime/credentials.py
/workspace/apps/api/plane/agent/runtime/config.py
resolver_regular=1 mode=0755 owner=0:0 byte_identical=1
resolver_keys=api_key_only
```

The synthetic exact Codex auth document was owner-only. No credential value was
printed or retained in evidence.

The one fresh live invocation then stopped at:

```text
status=failed reasonCode=runtime_configuration_pre_dispatch_failure reasonPhase=runtime_configuration reasonDetail=dispatch_rejected
runRef=a8728511-7846-447f-a682-a4dfb0aa5848 runState=blocked
invocationRef=4cfecbc9-36c0-4be2-8a02-e4ee2d128669 invocationState=blocked
providerAttempts=[] terminal={present:true,kind=run_blocker}
```

The candidate source and packaged resolver are now proven. The remaining defect
is within the real broker, lease, resolver, or invocation-configuration handoff.
The provider was not reached, the permitted/denied tool canaries did not run,
and no outcome or explicit publication occurred. Plane recorded one visible
`run_blocker`. No prior invocation was replayed; the helper still has no replay
step. Cleanup removed the disposable image, checkout, authority/config,
synthetic auth, containers, networks, and volumes while preserving the prepared
base and pinned runtime image. No broad G3/G4, G5, rollout, or deployment ran.

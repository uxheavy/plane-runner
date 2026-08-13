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

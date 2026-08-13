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

## Wave 0F — accepted credential, rejected runtime lease

Status: dirty at the supervisor-to-runtime credential-lease boundary. No replay
was attempted.

- Product source: `5a1e5bfa93eb971fa4138aa8b9b94a7d61a63a90`.
- Temporary API image digest: `sha256:d44d7eee9430c48820305af5934f9330f5bebc4fac60c489ebf28127f9e17cf2`.
- Runtime/Hermes remained pinned and unchanged.
- Fresh authority: `s00-live-20260813T112930Z-wave0f`; GPT-5.6 Luna through the ChatGPT subscription route; fallback disabled.

Network-disabled proof confirmed candidate module provenance, resolver
permissions and byte identity, current Codex document acceptance with exactly
the `api_key` result key, and classified rejection of an unexpected shape. The
real document also satisfied every sanitized key, type, size, and control-byte
predicate; no value was printed.

The one fresh live invocation then stopped at:

```text
status=failed reasonCode=runtime_configuration_pre_dispatch_failure reasonPhase=runtime_configuration reasonDetail=dispatch_rejected
runRef=51351a1f-b409-47ea-8f31-cb293666a8eb runState=blocked
invocationRef=d3ed113b-d01c-4bfa-8253-7f1987f8a224 invocationState=blocked
providerAttempts=[] terminal={present:true,kind=run_blocker}
```

One actor, profile, assignment, run, and invocation were created. The candidate
resolver/parser and source shape are proven; the next defect is downstream in
the live supervisor, broker, relay, lease binding, or pinned runtime
configuration. Provider attempts, gateway operations, outcome submissions, and
publications were zero. Plane recorded one lifecycle `run_blocker`. Replay was
not attempted because the run did not succeed. Cleanup removed every disposable
artifact and Docker resource while preserving the prepared base and pinned
runtime image. No broad G3/G4, G5, rollout, or deployment ran.

## Wave 0G — unshared credential-revocation state

Status: dirty before live authority/configuration. No invocation or replay ran.

- Source: `e5b5e626fc69380ed6c02468565f56837de8fcaa`.
- Temporary API image digest: `sha256:6f0fdd6837ae5e4fe744330d304045708add53153d03e4b60273641a41311641`.
- Runtime/Hermes remained pinned and unchanged.
- Candidate provenance, resolver behavior, and canonical `run:<uuid>` provider-audit binding all passed with networking disabled.

The required runner topology check failed before live setup:

```text
credential_state_env_bindings=2
api_runtime_state_path_shared=false
shared_state_mount_declared=false
runtime_revocation_state_contract=unshared
```

The live runner gives Plane and the runtime different credential-revocation
state paths and declares no shared mount, so runtime-side lease validation
cannot observe Plane-owned revocation state. Authority/configuration, Plane
records, runtime startup, and provider egress were not attempted. Cleanup was
complete; no broad G3/G4, G5, rollout, or deployment ran.

## Wave 0H — shared-state retest and approved live invocation

Status: dirty at an unclassified runtime configuration boundary. No replay ran.

- Source: `fc662d3f3521b44b719c08a57edcbdf402b0dfd5`.
- Temporary API image digest: `sha256:7d08028a3ccb1a65224b5b6c8449e0483bd39febe9e4b688273c01b6e36fe71a`.
- Runtime/Hermes remained pinned and unchanged.
- Candidate provenance, resolver behavior, canonical run binding, one shared API-RW/runtime-RO credential-state volume, revocation visibility, runtime secret isolation, and exact volume cleanup all passed without networking.

After the user explicitly approved the exact synthetic payload, the coordinator
executed one fresh GPT-5.6 Luna S00 call with no fallback. It exited after about
70 seconds with:

```text
status=failed reasonCode=runtime_configuration_pre_dispatch_failure reasonPhase=unavailable reasonDetail=unavailable
runRef=2b4a60e1-d542-4d68-9e9f-d1c08d56591c runState=blocked
invocationRef=77339474-80bd-4b8b-afd2-af486c952297 invocationState=blocked
providerAttempts=[] terminal={present:true,kind=run_blocker}
```

The provider was not reached. Permitted/denied tool canaries, outcome,
publication, and successful terminal product state did not run. Plane recorded
one lifecycle `run_blocker`. No old invocation was replayed. The runner and Maya
removed the temporary image, checkout, descriptors, containers, networks,
volumes, and run files; prepared base and pinned runtime images remain. No broad
G3/G4, G5, rollout, or deployment ran.

## Wave 0I — S00 exact-candidate manifest binding

Status: blocked at the first live authority/configuration boundary. Exactly one
fresh approved S00 command ran; it exited before credential staging, Plane
resource creation, runtime startup, or provider dispatch. No retry or replay ran.

- Candidate: `735f79bb32fe9934a98e01b2772232109d546ec7`.
- Temporary API artifact: `plane-agent-api:g4-735f79-wave0i`, digest
  `sha256:47f806e823ad871f472da9d53d814c6c4edbf5611935a2d395880eece36c8d25`.
- Pinned runtime/Hermes remained unchanged at
  `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`.
- Network-disabled provenance, minimal-environment resolver, approved child
  environment, bounded diagnostics, shared revocation topology, and config-only
  authority validation passed.
- The live command exited `1` in about `0.36s` with
  `authority_apiArtifact_mismatch`.
- Provider attempts: zero. No actor, profile, assignment, run, invocation,
  gateway receipt, outcome, publication, or terminal product state was created.
- Root cause: `tools/agent-g4-live.sh` reads the checkout's durable frozen
  `tools/agent-g4-manifest.json`, while the disposable authority/config were
  validated against the exact-candidate artifact manifest. The runner exposes
  no supported way to select that manifest, creating two sources of truth.
- Cleanup removed the temporary API image and all Wave 0I handoff artifacts;
  labeled containers, networks, and volumes were zero. Prepared base and pinned
  runtime images remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, or source edit ran.

## Wave 0J — S00 API invocation at 96bb2649f6

Status: blocked after the explicit disposable-manifest boundary passed. Exactly
one fresh approved S00 command reached API invocation and failed. No retry,
replay, or second provider call ran.

- Candidate: `96bb2649f6356f1614a8ba2315089091b12ee938`, direct parent
  `e26bf86cdfcda02e6a0659fc1792c8fdec665eb9`.
- Temporary API artifact: `plane-agent-api:g4-96bb2649-wave0j`, digest
  `sha256:76e31ae82eafcaa96cb16e8cf20576fc3e739fd622197011cd022ce073a50b73`.
- Pinned runtime/Hermes remained unchanged at
  `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`.
- The checkout-owned manifest, fresh authority/config, GPT-5.6 Luna subscription
  descriptor, no-fallback binding, and config-only proof passed before live
  side effects.
- Fresh run `6ae053c0-2583-4032-8d08-6d2216b283ea` failed.
- Fresh invocation `invocation:58ec752a-8aba-4a41-9368-cedd47394be4`
  failed at `api-invocation` with exit `1`; bounded reason/detail/subreason were
  unavailable.
- Provider attempts: zero. Permitted read, denied evaluation, gateway receipts,
  outcome submission, publication, and successful terminal state were not
  reached. No replay ran.
- The temporary image, checkout, manifest, authority/config, and generator were
  removed. Task-labeled containers, networks, and volumes were empty; prepared
  base and pinned runtime remained.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0T — live subscription retest at ecfacc0ea4

Status: dirty at the first concrete provider-audit rejection. Exactly one
fresh approved lifecycle ran; no retry or replay ran.

### Candidate and binding

- Authoritative checkout was clean at
  `ecfacc0ea4712fca3cb24b37d96ca893113b5bad`; the disposable clone was
  detached and clean at that exact SHA.
- API image digest:
  `sha256:e7a168f6260ee3773c2a4668f2170f537d004b8b1feef15e2f775b90049d73aa`.
- Sealed-donor runtime image digest:
  `sha256:5d16c7f5d13879c94c0a744966c81ebcc1a98c62ee6b868986f9d50e16732b34`;
  runtime source digest
  `bb0342bccb492ceb0f9e99605eb7b7d461f5239da39bc0df99fb65229ba0026a`.
- Hermes donor was `d2e655101f263329359e7d0de9d0b856202a3e4b`, digest
  `sha256:6f1c2dc5857d445e13b34f9cc9723ee5c7636c2cfe2ef213c7fc4d972855c1bd`.
- Fresh authority/config validation passed for ChatGPT subscription,
  `openai-codex/gpt-5.6-luna`, with fallback disabled. Owner-only auth-file
  metadata passed the `0600` preflight; contents and raw path were not recorded.

### First failing boundary and provider evidence

The single live runner exited `1` at `api-invocation` with this finite receipt:

```text
failure=runtime_configuration_pre_dispatch_failure
reasonPhase=runtime_configuration
reasonDetail=dispatch_rejected
reasonSubreason=provider_attempt_evidence_rejected
runRef=dce717b3-d27e-48de-ad85-a9baa50a174e runState=blocked
invocationRef=invocation:81185303-1f62-46db-b48b-f79d51d346a7 invocationState=blocked
terminal={present:true,kind=run_blocker}
```

Provider reached: yes. Plane readback contained eight provider-attempt rows,
sequences `1` through `8`, each `phase=completed`, `upstreamInitiated=true`,
`statusClass=2xx`, and no error code. This fails the required exactly-one-attempt
assertion. The bounded receipt does not prove whether an additional unpersisted
request existed, so no larger count is claimed.

No permitted read, denied evaluator receipt, explicit OutcomeSubmission,
publication, successful terminal product event, or replay was evidenced before
the stop. One visible `run_blocker` was recorded. The first owner is the trusted
Plane host provider-attempt callback seam: `agent_supervisor` invokes
`record_provider_attempt_notice`, and the runtime relay converts a required
callback exception into `provider_attempt_evidence_rejected`.

### Cleanup and scope

- No replay or second live journey ran.
- The live runner removed task-owned runtime containers, networks, volumes,
  credential staging, run files, disposable images, and checkout.
- Prepared base and pinned Hermes donor artifacts remain unchanged.
- No broad G3/G4/G5 verifier, load test, rollout, refreeze, deployment, UI, or
  reviewer ran.

## Wave 0S — provider-free remote-rejection proof at 656ced1019

Status: clean for the Plane remote-runtime rejection boundary; S00 remains dirty
at the real pinned Hermes bootstrap before provider-attempt intent.

- Candidate: `656ced10198e3330926a31481ec646e9d39c0f32`.
- The exact live helper used the real `agent_supervisor` command and
  `RemoteRuntimeTransport` against an authenticated local runtime endpoint.
- Canonical HTTP 409 evidence preserved `runtime_process_failed`,
  `runtime_process`, and `process_exit` through the transport, lifecycle,
  durable control/terminal state, and final bounded live receipt.
- The configuration-rejection and successful fake-provider controls remained
  covered, including exactly one terminal product event, zero attempts for the
  rejection, one attempt for success, and redacted error material.
- Central migration-backed Docker execution passed all three focused tests in
  `6.98s`; the test stack and volumes were then removed.
- No product behavior changed. The proof removes Plane propagation from the
  active failure fence. The next test must execute the real pinned Hermes
  bootstrap provider-free and expose its first pre-relay failure before any new
  subscription request.

No broad G3/G4 verifier, unrelated suite, image refreeze, provider call, G5,
rollout, pilot, or deployment ran.

## Wave 0R — supervisor terminalization retest at afe98be81d

Status: dirty at the first API-invocation boundary. Exactly one fresh approved
lifecycle ran; no retry or replay ran.

- Candidate: `afe98be81d6feee9856c89f1a001c02be4ecf1c0`.
- API image digest:
  `sha256:d9ccea8ddf2b8c327cb72d3cea6bffb289f9827bf6b697e3754f1b854ccbdff7`.
- Runtime image digest:
  `sha256:755670b7074debdbf95c6dae225d95865186793f33f673e14ec14c27d14b7f2a`.
- Both artifacts were built once from the exact candidate using the sealed
  Hermes donor and one disposable manifest.
- Fresh ChatGPT subscription / `openai-codex/gpt-5.6-luna` config validation
  passed with fallback disabled.
- Fresh run `0ff0a87b-a0a5-4a4e-910f-883d87a31e5a` failed.
- Fresh invocation `invocation:df4bb8e5-3537-4932-aaf0-70d1424313b7`
  failed at `api-invocation`; provider attempts remained zero and the receipt
  still reported an unspecified reason.
- No permitted read, denied evaluator operation, gateway receipt, outcome,
  publication, or replay ran. Plane returned one visible `run_failure` marker.
- Cleanup removed all task-owned resources and left zero labeled containers,
  networks, or volumes; the prepared base and sealed donor remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0Q — bounded result handoff retest at c1d7e28b8c

Status: dirty at the first API-invocation boundary. Exactly one fresh approved
lifecycle ran; no retry or replay ran.

- Candidate: `c1d7e28b8c7d21605388751140a5cacc38cbb5a7`.
- API image digest:
  `sha256:358872fe149fe53fe862cc536dbdc3888f4794a6266d5b43e60bed11e2176794`.
- Runtime image digest:
  `sha256:cd049fdcb605048e887ea04e730a4620b94696ccfbf3815264c03cb865699656`.
- Both artifacts were built once from the exact candidate and bound by one
  disposable manifest using the sealed Hermes donor.
- Fresh authority/config validation passed with ChatGPT subscription,
  `openai-codex/gpt-5.6-luna`, and fallback disabled.
- Fresh run `372c6bb8-143d-4876-a9ba-2f019369b5b7` failed.
- Fresh invocation `invocation:dc439242-1556-4749-8505-7c9e72700cde`
  failed at `api-invocation` with an unspecified failure.
- Provider attempts: zero. No permitted read, denied evaluator operation,
  gateway receipt, outcome, publication, or replay ran. Plane returned one
  visible `run_failure` marker.
- Post-run code trace identified the bypass: when supervisor setup raises before
  `run_runtime_invocation()` returns, `call_command()` never yields a bounded
  result and the live helper falls back to a generic failure.
- Cleanup removed all task-owned resources and left zero labeled containers,
  networks, or volumes; the prepared base and sealed donor remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0P — provider-audit propagation retest at d3fd5a87f2

Status: dirty at the first API-invocation boundary. Exactly one fresh approved
lifecycle ran; no retry or replay ran.

- Candidate: `d3fd5a87f2af7a82231fe771d5ce1f0f0c1f3b24`.
- API image digest:
  `sha256:d2293db50cf57d84b65102468a1f8108c76ebb6c3097ce2f360fac63421915f3`.
- Runtime image digest:
  `sha256:1d17e782bc7e85dec4bebc3e48d547d661c5cf52fc7389faedca8313c1983682`.
- Both artifacts were built once from the exact candidate and bound by one
  disposable manifest. The runtime used the sealed Hermes donor attested as
  `d2e655101f263329359e7d0de9d0b856202a3e4b`.
- Fresh authority/config validation passed with ChatGPT subscription,
  `openai-codex/gpt-5.6-luna`, and fallback disabled.
- Fresh run `c0bf548b-5a80-47f7-b02c-0cd2def8ef43` failed.
- Fresh invocation `invocation:ba0a1736-fe8c-4f3e-af1b-0b69befe19ec`
  failed at `api-invocation` with an unclassified `RuntimeError`.
- Provider attempts: zero. The runtime's new
  `provider_attempt_evidence_rejected` marker did not reach the bounded receipt.
- No permitted read, denied evaluator operation, gateway receipt, outcome,
  publication, or replay ran. Plane returned one visible `run_failure` marker.
- Cleanup left zero task-labeled containers, networks, or volumes and removed
  all disposable images, checkout, manifest, authority/config, and credential
  staging. The prepared base and sealed donor remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0N — S00 live budget retest at 8702d282bc

Status: blocked at `api-invocation`; exactly one fresh approved lifecycle ran,
with no retry or replay.

- Candidate: `8702d282bc89c9f474fde51fe15d2382bb92f959`.
- Temporary API image digest:
  `sha256:c8b5a7920ed1a8c67fbd9bda9c02923d9395a70a8f3748b797b19107f3e98855`.
- Fresh disposable manifest and authority/config validation passed with
  GPT-5.6 Luna, ChatGPT subscription routing, and fallback disabled.
- Fresh run `a7828d3e-5cc2-4660-b644-f4d53215e77c` failed.
- Fresh invocation `invocation:b008822a-5531-4f88-9135-9166bd14ffe3`
  failed at the bounded `api-invocation` RuntimeError boundary.
- Provider attempts: zero. No permitted read, denied evaluation, gateway
  receipt, outcome, publication, successful terminal event, or replay ran.
- The current-source literal management-command path passes with a fake runtime,
  but the live manifest continued to bind the older runtime image. Runtime-image
  source parity must be established before another provider call.
- Temporary image, checkout, manifest, authority/config, and Colima were
  removed. Task-labeled containers, networks, and volumes were empty; prepared
  base and pinned runtime images remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0O — matched current-source runtime retest at 4ec33bb637

Status: dirty at the first API-invocation boundary. Exactly one fresh approved
lifecycle ran; no retry or replay ran.

- Candidate: `4ec33bb637d4ce7e60c29e0afc50ffb503e43574`.
- API image digest:
  `sha256:12e056eae752fd3e305c76a806139fe9b8ea33c587f63554af645007c589b6be`.
- Runtime image digest:
  `sha256:c16270428c485d6ed8185a1bb3830f1d64fe04278b9837ed031642b3679adc77`.
- Both artifacts were built once from the exact candidate. The runtime used the
  sealed Hermes donor attested as `d2e655101f263329359e7d0de9d0b856202a3e4b`
  with tree digest
  `9485115c76b71c47b08d14ec4a1df7cb615301f8e151959c00a80382bdb61bbc`.
- Fresh authority/config and config-only validation passed with ChatGPT
  subscription routing, `openai-codex/gpt-5.6-luna`, and fallback disabled.
- Fresh run `6fb4bcc4-503a-4aa7-b7ec-e44dfe86954f` failed.
- Fresh invocation `invocation:65b99651-a21c-4752-aaa7-b4368f342e8a`
  failed at `api-invocation` with an unclassified `RuntimeError`.
- Provider attempts: zero. The permitted read, denied evaluator operation,
  gateway receipts, outcome submission, publication, and replay did not run.
- Plane recorded one visible `run_failure` terminal event.
- The current bounded receipt cannot distinguish an API-side rejection from a
  runtime process failure; no narrower root-cause claim is made.
- Disposable images, checkout, manifest, authority/config, containers,
  networks, volumes, relay sockets, and credential staging were removed. The
  prepared base and pinned sealed donor remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0L — execution-dependent lifecycle proof at 0afb4cc9bb

Status: stopped before live S00 at the first focused lifecycle regression
failure. No authority/config, credential read, provider request, Plane live
lifecycle, retry, replay, or publication ran.

- Candidate: `0afb4cc9bbf9be96be979c79d7802c2610898128`.
- Temporary API image digest:
  `sha256:4ed5eddf1024e876d38b4ee14b0eba29e8b4f55d82bab97c20ea071a08895aff`.
- Two execution-dependent tests ran in the candidate image on an internal-only
  Compose network with repository test dependencies.
- Passed: canonical resolved profile policy reached the fake cross-process relay,
  produced exactly one `intent → started → completed` attempt, and cleaned up.
- Failed: a direct update of persisted `RunAttempt.snapshot` did not raise the
  expected `DatabaseError`. The database therefore did not enforce the immutable
  run snapshot required by ADR-0006/ADR-0010.
- The live S00 was not started after this first failure.
- Compose services/network, temporary API image, checkout, manifest/test files,
  and Colima were removed. Prepared base and pinned runtime images remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or provider call ran.

## Wave 0M — S00 live entry-point retest at cb75a64741

Status: blocked at `api-invocation`; exactly one fresh approved lifecycle ran,
with no retry or replay.

- Candidate: `cb75a6474129d87b3edb077a0760f6aef03c9d68`.
- Temporary API image digest:
  `sha256:b1949914f33d0600790fe0715c64727c9abae4b4e6d1b11881befb700252711a`.
- Fresh disposable manifest and authority/config validation passed with
  GPT-5.6 Luna, ChatGPT subscription routing, and fallback disabled.
- Fresh run `5c7936da-5b38-408d-98b5-7a3e22a6ed62` failed.
- Fresh invocation `invocation:014b8a05-869b-400d-86dd-2eca6404f5ec`
  failed at the bounded `api-invocation` RuntimeError boundary.
- Provider attempts: zero. No permitted read, denied evaluation, gateway
  receipt, outcome, publication, successful terminal event, or replay ran.
- Because canonical lifecycle policy and migration-backed database invariants
  already pass, the remaining failure belongs to the exact live entry point or
  its diagnostic propagation and requires a persisted snapshot/envelope trace.
- Temporary image, checkout, manifest, authority/config, and Colima were
  removed. Task-labeled containers, networks, and volumes were empty; prepared
  base and pinned runtime images remain.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

## Wave 0K — S00 policy-consumer retest at 0f855f864b

Status: blocked at `api-invocation`; exactly one fresh approved lifecycle ran,
with no retry or replay.

- Candidate: `0f855f864b2448e0d943996c2f9dc977328244f4`.
- Temporary API image digest:
  `sha256:4ef7acb423f7bc84ce2ead1c160f41d35b697aad4bec62ce80d6b9dbceb231a3`.
- Direct changed-function proof under `--network none` passed: incomplete Hermes
  policy produces the bounded `runtime_configuration_pre_dispatch_failure`
  contract without a raw exception. The focused pytest wrapper did not reach its
  body because its autouse fixture could not resolve the absent test database.
- Fresh run `7c90f4d3-ac59-4361-8f2f-36d2533a1f59` failed.
- Fresh invocation `invocation:ad89fbc3-3d09-461d-ba65-d08c8f1075b8`
  failed at `api-invocation`; the outer live result still reported an unspecified
  runtime error.
- Provider attempts: zero. No permitted read, denied evaluation, gateway
  receipt, outcome, publication, successful terminal event, or replay ran.
- Interpretation: safe consumer classification is fixed, but the real lifecycle
  producer still omits required resolved Hermes policy fields and must be fixed
  at its owning snapshot/dispatch seam.
- Temporary image and all Wave 0K artifacts were removed; task-labeled
  containers, networks, and volumes were empty. Prepared base and pinned runtime
  remained, and Colima was returned to stopped state.

No broad G3/G4 verifier, unrelated suite, load test, G5, rollout, pilot,
deployment, source edit, or extra provider call ran.

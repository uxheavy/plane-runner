# Plane Agent tooling

This directory documents the durable Plane Agent product and its provider-free verification surface.

## Verification

Run the canonical checks from the repository root:

```sh
tools/verify-agent-g3.sh
PLANE_G4_RECEIPT_PATH=/private/tmp/plane-agent-g4-provider-free.json \
  tools/verify-agent-g4.sh --offline
python3 tools/verify-agent-g4-operations.py \
  --verifier-receipt /private/tmp/plane-agent-g4-provider-free.json
python3 tools/agent-g4-rollback-drill.py
```

The G4 verifier checks the pinned API and runtime images, G3 behavior, runtime contracts and cross-process transport, runtime service behavior, the container red-team, gateway workload, rollback, operator readback, production configuration, and cleanup. It makes no provider request.

The durable source and artifact pins are in `tools/agent-g4-manifest.json`. Its
candidate is exactly the source revision embedded in both tested images. The
operations owner map is `tools/agent-g4-operations-v1.json`; it accepts only a
passed sanitized provider-free receipt with zero provider attempts.

Restricted live execution is external to this repository and requires a named approved operational owner. This repository contains no provider credential staging, launcher, provider scenario, live evidence, support, or recovery machinery.

## Authority

- Repository and nested `AGENTS.md` files govern implementation.
- ADR-0001 through ADR-0010 govern the durable product architecture.
- [Runtime operations](./operations/agent-runtime-operations.md) contains the provider-free operational checks.

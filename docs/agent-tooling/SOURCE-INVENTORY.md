# Source Inventory

This inventory records stable repository identities and exact source SHAs used by the approval package. It contains no local absolute paths and does not require sibling checkouts for clean-worktree verification. The reviewed baseline and sealed package evidence are separate facts.

## Reviewed baseline

| Repository | Stable path           | Reviewed SHA                               | Ref                                | Authority and role                                                     |
| ---------- | --------------------- | ------------------------------------------ | ---------------------------------- | ---------------------------------------------------------------------- |
| Plane      | repository root (`.`) | `dac96b0ff9a3adb6bfcc3fea235ab4a697ae5acd` | `codex/agent-tooling-architecture` | historical reviewed baseline; not required to equal the sealed package |

The reviewed baseline is an ancestor check only. The exact Plane package content SHA is `5e066fb672feac2348ff7209d49af5b2768fbaa5` and is also machine-bound as `integration-lock.g0.json#/seal/contentCommit`; the seal commit is the current first-parent evidence boundary. No branch name is used as package identity.

## Current pinned source revisions

| Repository            | Stable repository path            | Exact SHA                                  | Ref/tag                              | Role                                                               |
| --------------------- | --------------------------------- | ------------------------------------------ | ------------------------------------ | ------------------------------------------------------------------ |
| Plane package         | `.`                               | `5e066fb672feac2348ff7209d49af5b2768fbaa5` | sealed content commit                | control plane, domain, gateway, catalog, and integration root      |
| Hermes                | `repository:uxheavy/hermes-agent` | `112f51a5543d490768931514d48a780ad964a868` | `main`                               | separate runtime service and hidden execution-kernel adapter donor |
| Buzz                  | `repository:uxheavy/buzz`         | `3b8567a05d4c40e667d061666feb7aa7bc38212d` | `main`                               | reference donor only; never a runtime dependency or authority      |
| Plane MCP fork        | `external/plane-mcp-server`       | `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1` | `codex/agent-tooling-v1` / `0.2.11`  | official MCP compatibility adapter host                            |
| Plane Python SDK fork | `external/plane-python-sdk`       | `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426` | `codex/agent-tooling-v1` / `v0.2.20` | shared Python SDK transport seam                                   |

## Plane gitlink evidence

The sealed content commit must point these submodules at the exact pinned SHAs:

| Gitlink                     | Required SHA                               |
| --------------------------- | ------------------------------------------ |
| `external/plane-mcp-server` | `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1` |
| `external/plane-python-sdk` | `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426` |

## Evidence boundary

`integration-lock.g0.json` binds every source SHA, remote, ref, gitlink, normative documentation input, accepted ADR, generator, fixture, and verifier input. The lock's `reviewedBaseline` is not a digest of the package. The lock's `seal.contentCommit` is the first parent of the evidence-seal commit; the verifier rejects a semantic change or an extra unsealed commit after that boundary.

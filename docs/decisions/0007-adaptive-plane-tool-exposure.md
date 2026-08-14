# ADR-0007: Expose Plane-native tools adaptively

## Status

Accepted

## Date

2026-08-03

## Context

Plane's external MCP currently contains 177 tools across a broad catalog, while the execution kernel also has a broad native tool surface. Exposing every supported Plane action eagerly would consume context, preserve non-native terminology, and reduce reliable tool selection. A fixed tiny catalog would prevent agents from completing varied Plane assignments. The target must therefore combine complete operation coverage with adaptive disclosure.

ADR-0001 establishes the shared Plane Operation Gateway and progressive operation catalog. This ADR decides how the Plane-native runtime presents available operations to the model.

## Decision

Keep three separate layers:

1. **Actor authorization:** Plane identity, credential, memberships, roles, and object permissions. This is the sole entitlement source.
2. **Tool availability:** operations supplied by installed and enabled Plane features or integrations.
3. **Tool disclosure:** which available schemas are eager versus progressively disclosed for the resolved profile and assignment.

All supported Plane integrations and actions are represented in the shared operation catalog and gateway before the non-UI program is finished. Compose each run's model-facing disclosure from three presentation layers:

1. A small universal Plane work core available to every Plane Agent.
2. Eager tools selected from available operations using the resolved profile and current assignment.
3. Other available operation schemas exposed through progressive discovery.

Catalog discoverability is global: an authenticated agent client can search the complete supported operation/action catalog. Role and assignment context decide which schemas are eager, not whether a supported operation exists. Discovering an operation does not imply that the current actor may execute it; live Plane authorization remains final for every call.

The universal core includes one `search_workspace` operation that returns typed references across Plane objects. Ordinary reads may use one typed-reference reader when it can preserve clear schemas and authorization behavior. Mutations remain explicit semantic operations rather than one universal mutation tool.

The exact universal-core membership, final names, promotion rules, and schemas remain separate catalog decisions and must be verified against real Plane work. Presentation never grants, denies, or pre-authorizes an operation; live Plane authorization remains final.

The v1 run snapshot represents each eager entry as an `EagerOperationPresentation`:

```ts
type EagerOperationPresentation = {
  operationRef: string;
  schemaDigest: string;
  inputSchema: object;
  disclosure: "eager";
};
```

`inputSchema` is the bounded canonical JSON Schema object from the gateway descriptor. `schemaDigest` continues to identify the complete canonical descriptor, including its result schema. The immutable run snapshot content digest authenticates the embedded input-schema bytes. The contract allows at most 64 entries, bounds each input schema to 16 KiB of canonical UTF-8 JSON, bounds the aggregate eager presentation to 512 KiB, and rejects oversize data without truncation. It does not include a result schema, aliases, broad coercion, or per-operation permissions.

This is a pre-release v1 contract correction found by functional dogfood. It does not require a deployed compatibility migration because the contract has not been released as a compatibility promise.

## Alternatives considered

### Expose every Plane and Hermes tool eagerly

- Benefit: immediate visibility of all operations.
- Cost: excessive context and ambiguous selection.
- Rejected: catalog size is not a useful default interface.

### Give every profile a fixed closed tool list

- Benefit: predictable prompts.
- Cost: assignments cannot discover permitted long-tail operations without profile changes.
- Rejected: progressive discovery preserves flexibility.

### Provide one generic read/write operation

- Benefit: very small schema surface.
- Cost: weak mutation semantics, authorization explanations, validation, and audit readability.
- Rejected for writes: mutations remain typed Plane actions.

## Consequences

- Global catalog visibility and adaptive eager disclosure are separate: visibility is complete, while prompt exposure is intentionally selective.
- Plane authorization still evaluates every operation under ADR-0002.
- Installed integrations determine availability; profiles and assignment context influence disclosure without changing entitlement or reducing catalog coverage.
- The 177-tool MCP remains an external compatibility surface rather than the native prompt catalog.

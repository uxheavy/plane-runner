# `@plane/agent-runtime-contract`

The public contract boundary accepts serialized JSON text or UTF-8 `Uint8Array` bytes. Contract parsers, canonical digest helpers, schema validation, and runtime verification reject live JavaScript objects before inspecting them; callers must serialize once at the process boundary.

Parsed values are package-owned, frozen values used internally by the semantic verifier. The package does not export configurable traversal limits, live-object normalizers, object mutators, or raw schema subpaths. Serialized input is capped before parsing, and traversal, collection, event, receipt, and verification-error work is bounded.

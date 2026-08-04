#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const verifierPath = fileURLToPath(import.meta.url);
const root = resolve(dirname(verifierPath), "..");
const repositoryRoot = resolve(root, "../..");
const modeIndex = process.argv.indexOf("--mode");
const mode = modeIndex === -1 ? "g0" : process.argv[modeIndex + 1];
const negativeControlMode = process.argv.includes("--negative-control");
const negativeMarker = resolve(repositoryRoot, ".g0-negative-control");
if (!new Set(["preflight", "g0"]).has(mode)) {
  console.error("usage: verify-g0-preflight.mjs --mode preflight|g0");
  process.exit(2);
}

const failures = [];
const results = [];
const expectedApprovalStatement =
  "I approve `APPROVAL-MANIFEST.md` as the controlling Plane Agent Tooling V1 scope and authorize implementation to begin. I understand that pilot and production remain separately gated.";
const paths = {
  manifest: "docs/agent-tooling/APPROVAL-MANIFEST.md",
  sourceInventory: "docs/agent-tooling/SOURCE-INVENTORY.md",
  ownershipMap: "docs/agent-tooling/ownership-map.json",
  ownershipSchema: "docs/agent-tooling/ownership-map.schema.json",
  lockSchema: "docs/agent-tooling/integration-lock.schema.json",
  lock: "docs/agent-tooling/integration-lock.g0.json",
  readinessSchema: "docs/agent-tooling/g0-readiness.schema.json",
  readiness: "docs/agent-tooling/g0-readiness.json",
  modelSurfaceSchema: "docs/agent-tooling/model-facing-surface.schema.json",
  modelSurface: "docs/agent-tooling/model-facing-surface.json",
  plan: "docs/agent-tooling/NON-UI-IMPLEMENTATION-PLAN.json",
  overview: "docs/agent-tooling/NON-UI-IMPLEMENTATION-OVERVIEW.md",
  productRequirements: "docs/agent-tooling/product-requirements.md",
  result: "docs/agent-tooling/RESULT.md",
  fixture: "docs/agent-tooling/fixtures/planning-v1.json",
  fixtureSchema: "docs/agent-tooling/fixtures/planning-v1.schema.json",
  predicates: "docs/agent-tooling/fixtures/planning-v1.predicates.json",
  predicateSchema: "docs/agent-tooling/fixtures/planning-v1.predicates.schema.json",
  prompt: "docs/agent-tooling/prompts/release-planning-v1.md",
  planningValidator: "docs/agent-tooling/verifiers/validate-planning-fixtures.mjs",
};
const canonicalMarkdown = [
  "README.md",
  "GOAL.md",
  "APPROVAL-MANIFEST.md",
  "SOURCE-INVENTORY.md",
  "decision-register.md",
  "delivery-plan.md",
  "architecture.md",
  "INTERFACE-DESIGN.md",
  "RUNTIME-DESIGN.md",
  "GATEWAY-WIRE.md",
  "PILOT-CONTRACTS.md",
  "RELEASE-MANIFEST.md",
  "VERIFICATION-MANIFEST.md",
  "REQUIREMENT-COVERAGE.md",
  "RESULT.md",
  "product-requirements.md",
  "EVALUATION-FIXTURE-CONTRACT.md",
  "EVALUATION-SCENARIOS.md",
  "MCP-COMPATIBILITY.md",
  "MCP-MAPPING-CONTRACT.md",
  "SAFETY-EVALUATION-DESIGN.md",
  "ADR-SYNTHESIS.md",
  "NON-UI-IMPLEMENTATION-OVERVIEW.md",
  "inventories/plane-mcp-v0.2.11-dispositions.md",
  "prompts/release-planning-v1.md",
  ...Array.from(
    { length: 10 },
    (_, index) =>
      `../decisions/${String(index + 1).padStart(4, "0")}-${
        [
          "plane-agent-tooling-architecture",
          "autonomous-agent-operations",
          "plane-agent-native-product-boundary",
          "fork-hermes-as-hidden-execution-kernel",
          "plane-owned-agent-profiles",
          "assignment-and-run-lifecycle",
          "adaptive-plane-tool-exposure",
          "scoped-memory-and-context",
          "workflows-and-agent-delegation",
          "plane-runtime-contract",
        ][index]
      }.md`
  ),
];

// The retired-name policy is deliberately narrower than a file allowlist. Its
// governed paths are an explicit inventory, its Markdown authority uses exact
// section headings, and its structured authority uses exact JSON-pointer
// patterns. A path, section, or pointer that is not declared cannot silently
// become model-facing; authority-shaped mutations fail closed instead.
const markdownPolicyPaths = [
  "docs/agent-tooling/ADR-SYNTHESIS.md",
  "docs/agent-tooling/APPROVAL-MANIFEST.md",
  "docs/agent-tooling/EVALUATION-FIXTURE-CONTRACT.md",
  "docs/agent-tooling/EVALUATION-SCENARIOS.md",
  "docs/agent-tooling/GATEWAY-WIRE.md",
  "docs/agent-tooling/GOAL.md",
  "docs/agent-tooling/INTERFACE-DESIGN.md",
  "docs/agent-tooling/MCP-COMPATIBILITY.md",
  "docs/agent-tooling/MCP-MAPPING-CONTRACT.md",
  "docs/agent-tooling/NON-UI-IMPLEMENTATION-OVERVIEW.md",
  "docs/agent-tooling/PILOT-CONTRACTS.md",
  "docs/agent-tooling/README.md",
  "docs/agent-tooling/RELEASE-MANIFEST.md",
  "docs/agent-tooling/REQUIREMENT-COVERAGE.md",
  "docs/agent-tooling/RESULT.md",
  "docs/agent-tooling/RUNTIME-DESIGN.md",
  "docs/agent-tooling/SAFETY-EVALUATION-DESIGN.md",
  "docs/agent-tooling/VERIFICATION-MANIFEST.md",
  "docs/agent-tooling/architecture.md",
  "docs/agent-tooling/decision-register.md",
  "docs/agent-tooling/delivery-plan.md",
  "docs/agent-tooling/inventories/plane-mcp-v0.2.11-dispositions.md",
  "docs/agent-tooling/product-requirements.md",
  "docs/agent-tooling/prompts/release-planning-v1.md",
  "docs/agent-tooling/SOURCE-INVENTORY.md",
  "docs/agent-tooling/WORKLOG.md",
  "docs/decisions/0001-plane-agent-tooling-architecture.md",
  "docs/decisions/0002-autonomous-agent-operations.md",
  "docs/decisions/0003-plane-agent-native-product-boundary.md",
  "docs/decisions/0004-fork-hermes-as-hidden-execution-kernel.md",
  "docs/decisions/0005-plane-owned-agent-profiles.md",
  "docs/decisions/0006-assignment-and-run-lifecycle.md",
  "docs/decisions/0007-adaptive-plane-tool-exposure.md",
  "docs/decisions/0008-scoped-memory-and-context.md",
  "docs/decisions/0009-workflows-and-agent-delegation.md",
  "docs/decisions/0010-plane-runtime-contract.md",
];

const markdownSectionPolicy = {
  "docs/agent-tooling/ADR-SYNTHESIS.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent ADR Synthesis", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Design workspace and source hierarchy", "non-model-facing"],
      [2, "Cross-repository grounding", "non-model-facing"],
      [2, "Grounded ownership", "non-model-facing"],
      [2, "Architect arena", "non-model-facing"],
      [2, "Synthesis decision", "non-model-facing"],
      [2, "Verification record", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/APPROVAL-MANIFEST.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent Tooling: V1 Approval Manifest", "non-model-facing"],
      [2, "Status", "authoritative/model-facing"],
      [2, "Outcome and authority", "authoritative/model-facing"],
      [2, "Product invariants", "authoritative/model-facing"],
      [2, "First supported semantic operation boundary", "authoritative/model-facing"],
      [2, "Frozen model-facing surface", "authoritative/model-facing"],
      [2, "Curated catalog overlay", "authoritative/model-facing"],
      [2, "Logical runtime, dispatch, publication, and event contracts", "authoritative/model-facing"],
      [2, "Frozen v1 execution, result, artifact, and audit policy", "authoritative/model-facing"],
      [2, "Delivery and gates", "authoritative/model-facing"],
      [2, "Required evidence before production", "authoritative/model-facing"],
      [2, "Implementation approval gate", "authoritative/model-facing"],
    ],
  },
  "docs/agent-tooling/EVALUATION-FIXTURE-CONTRACT.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Planning Evaluation Fixture Contract", "non-model-facing"],
      [2, "Bound artifacts", "non-model-facing"],
      [2, "Identity and time expansion", "non-model-facing"],
      [2, "Predicate selection", "non-model-facing"],
      [2, "Evidence binding", "non-model-facing"],
      [2, "Deterministic scoring oracle", "non-model-facing"],
      [2, "Qualification boundary", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/EVALUATION-SCENARIOS.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent Tooling v1 Evaluation Scenarios", "non-model-facing"],
      [2, "Status and counting rules", "non-model-facing"],
      [2, "Product evidence contracts", "non-model-facing"],
      [3, "Live broad-planning contract", "non-model-facing"],
      [3, "Additional live safety contract", "non-model-facing"],
      [3, "Deterministic release contract", "non-model-facing"],
      [2, "Scenario inventory", "non-model-facing"],
      [2, "Coverage requirements", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/GATEWAY-WIRE.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Operation Gateway Wire Contract", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Boundary", "non-model-facing"],
      [2, "Endpoints", "non-model-facing"],
      [3, "Catalog discovery", "non-model-facing"],
      [3, "Operation execution", "non-model-facing"],
      [3, "Temporary artifact reads", "non-model-facing"],
      [2, "Authentication and binding", "non-model-facing"],
      [2, "Result envelope", "non-model-facing"],
      [2, "HTTP behavior", "non-model-facing"],
      [2, "Idempotency", "non-model-facing"],
      [2, "Catalog and version negotiation", "non-model-facing"],
      [2, "Official Python SDK adapter", "non-model-facing"],
      [2, "Local Hermes callback", "non-model-facing"],
      [2, "Required contract tests", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/GOAL.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Durable Ultragoal: Complete the non-UI Plane Agent system", "non-model-facing"],
      [2, "Active objective", "non-model-facing"],
      [2, "Observable outcome and audience", "non-model-facing"],
      [2, "Accepted product model", "non-model-facing"],
      [2, "Normative invariants", "non-model-facing"],
      [2, "Current baseline and evidence", "non-model-facing"],
      [2, "Normative resource catalog and authority", "authoritative/model-facing"],
      [3, "Repository authorities", "authoritative/model-facing"],
      [3, "Canonical Plane Agent documents", "authoritative/model-facing"],
      [3, "Source, catalog, fixture, and evidence authorities", "authoritative/model-facing"],
      [2, "Integration gates (G0–G5)", "non-model-facing"],
      [3, "G0 — Implementation contract frozen", "non-model-facing"],
      [3, "G1 — Deterministic domain spine", "non-model-facing"],
      [3, "G2 — Real single-agent vertical slice", "non-model-facing"],
      [3, "G3 — Non-UI feature breadth complete", "non-model-facing"],
      [3, "G4 — Production candidate verified", "non-model-facing"],
      [3, "G5 — Controlled rollout complete", "non-model-facing"],
      [2, "Durable phase plan", "non-model-facing"],
      [3, "P0 — Durable contracts and approval baseline", "non-model-facing"],
      [3, "P1 — Generated contracts, catalog, fixtures, and integration lock", "non-model-facing"],
      [3, "P2 — Plane domain, lifecycle, and roles", "non-model-facing"],
      [3, "P3 — Operation Gateway, security, idempotency, audit, and catalog foundation", "non-model-facing"],
      [3, "P4 — Separate runtime service, Hermes adapter, and snapshot/invocation protocol", "non-model-facing"],
      [3, "P5 — Restricted TypeScript composition and adaptive tool discovery", "non-model-facing"],
      [3, "P6 — Private memory, skills, gardeners, and schedules", "non-model-facing"],
      [3, "P7 — Dynamic delegation, chief-of-staff, HR, and evaluation", "non-model-facing"],
      [3, "P8 — Full Plane action and MCP/SDK compatibility convergence", "non-model-facing"],
      [3, "P9 — Reused settings, operations, observability, credentials, and runbooks", "non-model-facing"],
      [3, "P10 — Deterministic/live evaluation, security, load, recovery, and rollback", "non-model-facing"],
      [3, "P11 — Staged rollout, post-deploy proof, and GA completion", "non-model-facing"],
      [2, "Skill-routing catalog", "non-model-facing"],
      [2, "Delegation operating contract", "non-model-facing"],
      [2, "Reuse and subtraction rules", "non-model-facing"],
      [2, "Goal loop and durable state", "non-model-facing"],
      [2, "Anti-cheating, approval, and safety gates", "non-model-facing"],
      [2, "Blocker standard", "non-model-facing"],
      [2, "Evidence contract", "non-model-facing"],
      [2, "Completion proof", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/INTERFACE-DESIGN.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Operation Gateway Interface Design", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Design constraints", "non-model-facing"],
      [2, "Design A: one deep operation seam", "non-model-facing"],
      [2, "Design B: common-case semantic facade", "non-model-facing"],
      [2, "Design C: durable command state machine", "non-model-facing"],
      [2, "Design D: catalog, batch, and plan facade", "non-model-facing"],
      [2, "Comparison", "non-model-facing"],
      [2, "Accepted v1 core boundary", "non-model-facing"],
      [2, "Proposed catalog descriptor", "non-model-facing"],
      [2, "North Star", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/MCP-COMPATIBILITY.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "External MCP Compatibility Plan", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Compatibility unit", "non-model-facing"],
      [2, "Reuse boundary", "non-model-facing"],
      [2, "Accepted migration seam", "non-model-facing"],
      [2, "Complete disposition", "non-model-facing"],
      [2, "Gateway-backed adapter contract", "non-model-facing"],
      [2, "Attachment adapter contract", "non-model-facing"],
      [2, "Transport and authentication compatibility", "non-model-facing"],
      [2, "Conformance tiers", "non-model-facing"],
      [2, "Change policy", "non-model-facing"],
      [2, "Required evidence", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/MCP-MAPPING-CONTRACT.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "External MCP Exact Mapping Contract", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Required content-addressed bundle", "non-model-facing"],
      [2, "Independently generated control inventories", "non-model-facing"],
      [2, "Required exact joins", "non-model-facing"],
      [2, "Disposition-specific proof", "non-model-facing"],
      [3, "MCP-D-001 shared SDK transport", "non-model-facing"],
      [3, "MCP-D-002 local PQL", "non-model-facing"],
      [3, "MCP-D-003 hardened attachments", "non-model-facing"],
      [2, "Per-tool conformance", "non-model-facing"],
      [2, "VM-022 mapping sensitivity controls", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/NON-UI-IMPLEMENTATION-OVERVIEW.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent non-UI implementation overview", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Outcome", "authoritative/model-facing"],
      [2, "Scope boundary", "authoritative/model-facing"],
      [2, "Working principles", "non-model-facing"],
      [2, "How a traditional company would run it", "non-model-facing"],
      [2, "Execution map", "non-model-facing"],
      [2, "Lane summary", "non-model-facing"],
      [2, "Integration gates", "non-model-facing"],
      [3, "G0: Implementation contract frozen", "non-model-facing"],
      [3, "G1: Deterministic domain spine", "non-model-facing"],
      [3, "G2: Real single-agent vertical slice", "non-model-facing"],
      [3, "G3: Non-UI feature breadth complete", "non-model-facing"],
      [3, "G4: Production candidate verified", "non-model-facing"],
      [3, "G5: Controlled rollout complete", "non-model-facing"],
      [2, "Parallel delivery lanes", "non-model-facing"],
      [3, "L0: Product, architecture, and contract control", "non-model-facing"],
      [3, "L1: Verification and release engineering", "non-model-facing"],
      [3, "L2: Plane agent domain and lifecycle", "non-model-facing"],
      [3, "L3: Operation catalog, gateway, authorization, and audit", "non-model-facing"],
      [3, "L4: Runtime service and Hermes kernel adapter", "non-model-facing"],
      [3, "L5: Native tools, progressive discovery, and TypeScript isolation", "non-model-facing"],
      [3, "L6: Private memory, skills, gardeners, and schedules", "non-model-facing"],
      [3, "L7: Dynamic planning and delegation", "non-model-facing"],
      [3, "L8: External MCP and SDK convergence", "non-model-facing"],
      [3, "L9: Platform, security, reliability, and operations", "non-model-facing"],
      [3, "L10: Minimal administration and settings", "non-model-facing"],
      [3, "L11: Evaluation, production proof, and rollout", "non-model-facing"],
      [2, "Reuse-first decision rule", "non-model-facing"],
      [2, "Definition of finished", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/PILOT-CONTRACTS.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent Tooling Pilot Contracts", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Contract rules", "non-model-facing"],
      [2, "Shared value shapes", "non-model-facing"],
      [2, "Canonical result projections", "non-model-facing"],
      [2, "Read operations", "non-model-facing"],
      [3, "`plane.projects.resolve@1`", "non-model-facing"],
      [3, "`plane.cycles.list_current@1`", "non-model-facing"],
      [3, "`plane.work_items.search@1`", "non-model-facing"],
      [3, "`plane.work_items.get@1`", "non-model-facing"],
      [3, "`plane.project_members.list@1`", "non-model-facing"],
      [2, "Mutation operations", "non-model-facing"],
      [3, "`plane.work_items.create@1`", "non-model-facing"],
      [3, "`plane.work_items.update@1`", "non-model-facing"],
      [3, "`plane.comments.create@1`", "non-model-facing"],
      [3, "`plane.release_plans.create@1`", "non-model-facing"],
      [2, "Error codes", "non-model-facing"],
      [2, "Source alignment and intentional differences", "non-model-facing"],
      [2, "G1 generation inputs (not a G0 prerequisite)", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/README.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent Tooling Program", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Outcome", "non-model-facing"],
      [2, "Documents", "non-model-facing"],
      [2, "Source-of-truth rules", "non-model-facing"],
      [2, "G0 preflight", "non-model-facing"],
      [2, "Current next decisions", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/RELEASE-MANIFEST.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Release Manifest: Plane Agent Tooling v1", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Release identity", "non-model-facing"],
      [2, "Required workflows", "non-model-facing"],
      [2, "Pilot operation inventory", "non-model-facing"],
      [2, "Runtime pins", "non-model-facing"],
      [2, "V1 execution and retention limits", "non-model-facing"],
      [2, "Numeric release gates", "non-model-facing"],
      [2, "Rollout requirements", "non-model-facing"],
      [2, "Exceptions", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/REQUIREMENT-COVERAGE.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane Agent Tooling Requirement Coverage", "non-model-facing"],
      [2, "Authority", "non-model-facing"],
      [2, "Sources", "non-model-facing"],
      [2, "Outcome", "non-model-facing"],
      [2, "Normative product invariants", "non-model-facing"],
      [2, "Integration gates", "non-model-facing"],
      [2, "P0–P11 phase and writable-surface join", "non-model-facing"],
      [2, "Completion proof", "non-model-facing"],
      [2, "Gate ownership rule", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/RESULT.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Result", "non-model-facing"],
      [2, "Implemented outcome", "non-model-facing"],
      [2, "Repository state", "non-model-facing"],
      [2, "Primary verifier", "non-model-facing"],
      [2, "Mandatory live Hermes acceptance", "non-model-facing"],
      [2, "Focused verification", "non-model-facing"],
      [2, "Security and compatibility evidence", "non-model-facing"],
      [2, "Evaluation and performance evidence", "non-model-facing"],
      [2, "Provider and model evidence", "non-model-facing"],
      [2, "Computer Use evidence", "non-model-facing"],
      [2, "Rollout and production readback", "non-model-facing"],
      [2, "Release and verifier manifests", "non-model-facing"],
      [2, "Build and deployment provenance", "non-model-facing"],
      [2, "Residual risks", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/RUNTIME-DESIGN.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "TypeScript Runtime and Isolate Design", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Options considered", "non-model-facing"],
      [3, "Node.js permission model", "non-model-facing"],
      [3, "Deno permission sandbox in the runtime-invocation container", "non-model-facing"],
      [3, "Embedded QuickJS or WebAssembly runtime", "non-model-facing"],
      [3, "Nested container or microVM per execution", "non-model-facing"],
      [2, "Recommended v1 boundary", "non-model-facing"],
      [2, "Module and seam placement", "non-model-facing"],
      [2, "Package and import policy", "non-model-facing"],
      [2, "Host callback authorization", "non-model-facing"],
      [2, "Required security qualification", "non-model-facing"],
      [2, "Source evidence", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/SAFETY-EVALUATION-DESIGN.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Safety Evaluation and Trial Evidence Design", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Separate bundle", "non-model-facing"],
      [2, "Trial result contract", "non-model-facing"],
      [2, "Predicate model", "non-model-facing"],
      [2, "Canonical result bytes and artifacts", "non-model-facing"],
      [2, "Audit record classes", "non-model-facing"],
      [2, "Frozen errors and HTTP mapping", "non-model-facing"],
      [2, "Invocation retry state machine", "non-model-facing"],
      [2, "Exact live scenario profiles", "non-model-facing"],
      [3, "EV-011 — inaccessible control project", "non-model-facing"],
      [3, "EV-012 — foreign existing UUID", "non-model-facing"],
      [3, "EV-013 — revocation before dispatch", "non-model-facing"],
      [3, "EV-014 — permission removal after preflight", "non-model-facing"],
      [3, "EV-015 — autonomous broad write", "non-model-facing"],
      [3, "EV-016 — exact replay", "non-model-facing"],
      [3, "EV-017 — changed-input conflict", "non-model-facing"],
      [3, "EV-018 — lost response after commit", "non-model-facing"],
      [3, "EV-019 — atomic child failure", "non-model-facing"],
      [3, "EV-020 — ambiguous dispatched mutation", "non-model-facing"],
      [3, "EV-021 — oversized result", "non-model-facing"],
      [3, "EV-022 — cumulative results", "non-model-facing"],
      [3, "EV-023 — credential and process probes", "non-model-facing"],
      [3, "EV-024 — DNS, public HTTP, and Plane network", "non-model-facing"],
      [3, "EV-025 — loopback, link-local, and metadata", "non-model-facing"],
      [3, "EV-026 — filesystem, subprocess, package, and module loading", "non-model-facing"],
      [3, "EV-027 — callback binding", "non-model-facing"],
      [3, "EV-028 — eight out-of-order reads", "non-model-facing"],
      [3, "EV-029 — container death after commit", "non-model-facing"],
      [3, "EV-030 — admitted dependency interruption", "non-model-facing"],
      [2, "Sandbox anti-vacuity protocol", "non-model-facing"],
      [2, "Remaining qualification boundary", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/VERIFICATION-MANIFEST.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Verification Manifest: Plane Agent Tooling v1", "non-model-facing"],
      [2, "Status and change control", "non-model-facing"],
      [2, "Evidence contract", "non-model-facing"],
      [2, "Verifier ownership and independence", "non-model-facing"],
      [2, "Check inventory", "non-model-facing"],
      [2, "Completion-criterion coverage", "non-model-facing"],
      [2, "Mandatory live-project oracles", "non-model-facing"],
      [2, "Extensive live-evaluation ledger", "non-model-facing"],
      [2, "Negative-control qualification", "non-model-facing"],
      [2, "Clean-checkout execution contract", "non-model-facing"],
      [2, "Primary entry point", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/architecture.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Target Architecture", "non-model-facing"],
      [2, "System view", "non-model-facing"],
      [2, "Supported operation contract", "non-model-facing"],
      [2, "Plane Operation Gateway", "non-model-facing"],
      [2, "Identity and credentials", "non-model-facing"],
      [2, "Plane Agent domain ownership", "non-model-facing"],
      [2, "Plane-native runtime profile", "authoritative/model-facing"],
      [2, "Accepted Plane runtime contract", "non-model-facing"],
      [2, "TypeScript composition surface", "non-model-facing"],
      [2, "Autonomous execution and concurrency", "non-model-facing"],
      [2, "Mutation safety", "non-model-facing"],
      [2, "Results and artifacts", "non-model-facing"],
      [2, "Audit and replay evidence", "non-model-facing"],
      [2, "Versioning", "non-model-facing"],
      [2, "Reuse from the Hermes kernel", "non-model-facing"],
      [2, "Administration and release", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/decision-register.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Decision Register", "non-model-facing"],
      [2, "Accepted", "non-model-facing"],
      [2, "Superseded", "non-model-facing"],
      [2, "Frozen in controlling manifest pending approval", "non-model-facing"],
      [2, "Open", "non-model-facing"],
      [2, "Proposed", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/delivery-plan.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Delivery Plan", "non-model-facing"],
      [2, "Delivery strategy", "non-model-facing"],
      [2, "Workstreams and gates", "non-model-facing"],
      [3, "0. Program definition", "non-model-facing"],
      [3, "1. Operation contract", "non-model-facing"],
      [3, "2. Plane Operation Gateway", "non-model-facing"],
      [3, "3. Plane Agent execution pilot", "non-model-facing"],
      [3, "4. TypeScript Code Mode", "non-model-facing"],
      [3, "5. Mutation reliability", "non-model-facing"],
      [3, "6. Roles, private knowledge, schedules, and dynamic delegation", "non-model-facing"],
      [3, "7. Evaluation and production hardening", "non-model-facing"],
      [3, "8. Controlled rollout", "non-model-facing"],
      [3, "9. External MCP convergence", "non-model-facing"],
      [2, "First vertical slice", "non-model-facing"],
      [2, "Production readiness checklist", "non-model-facing"],
      [2, "Ownership model", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/inventories/plane-mcp-v0.2.11-dispositions.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Plane MCP v0.2.11 Per-Tool Dispositions", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Invariants", "non-model-facing"],
      [2, "Dispositions", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/product-requirements.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Product Requirements", "non-model-facing"],
      [2, "Problem", "non-model-facing"],
      [2, "Users", "non-model-facing"],
      [3, "Plane-native agents", "non-model-facing"],
      [3, "External agents", "non-model-facing"],
      [3, "Plane administrators and operators", "non-model-facing"],
      [3, "Auditors", "non-model-facing"],
      [2, "Required outcomes", "authoritative/model-facing"],
      [2, "Agent model and roles", "non-model-facing"],
      [2, "Non-goals", "non-model-facing"],
      [2, "Product principles", "non-model-facing"],
      [2, "Pilot options", "non-model-facing"],
      [2, "Success measures", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/prompts/release-planning-v1.md": {
    preamble: "non-model-facing",
    headings: [[1, "Plane Release-Readiness Planning Acceptance Prompt v1", "authoritative/model-facing"]],
  },
  "docs/agent-tooling/SOURCE-INVENTORY.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Source Inventory", "non-model-facing"],
      [2, "Reviewed baseline", "non-model-facing"],
      [2, "Current pinned source revisions", "non-model-facing"],
      [2, "Plane gitlink evidence", "non-model-facing"],
      [2, "Evidence boundary", "non-model-facing"],
    ],
  },
  "docs/agent-tooling/WORKLOG.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "Worklog", "non-model-facing"],
      [2, "Current state", "non-model-facing"],
      [2, "2026-07-29 — Goal grounding", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [3, "Decisions carried forward", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Live acceptance scope", "non-model-facing"],
      [3, "Decision", "non-model-facing"],
      [3, "Required proof", "non-model-facing"],
      [2, "2026-07-29 — Model and evaluation requirements", "non-model-facing"],
      [3, "Observed evidence", "non-model-facing"],
      [3, "Requirements", "non-model-facing"],
      [2, "2026-07-29 — Independent goal red-team", "non-model-facing"],
      [3, "Corrections adopted", "non-model-facing"],
      [2, "2026-07-29 — Source and interface inventory", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [3, "Proposed decision", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Compatibility and verifier design", "non-model-facing"],
      [3, "Proposed external MCP disposition", "non-model-facing"],
      [3, "Verifier strengthening", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Independent pre-freeze review", "non-model-facing"],
      [3, "Verdict", "non-model-facing"],
      [3, "Confirmed evidence", "non-model-facing"],
      [3, "Freeze blockers to close", "non-model-facing"],
      [3, "Progress after reviewed commit", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Core gateway interface accepted", "non-model-facing"],
      [3, "Decision", "non-model-facing"],
      [3, "North Star", "non-model-facing"],
      [3, "Still open", "non-model-facing"],
      [2, "2026-07-29 — MCP reuse and release-plan write accepted", "non-model-facing"],
      [3, "Official MCP boundary", "non-model-facing"],
      [3, "Release-plan write boundary", "non-model-facing"],
      [3, "Rationale", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Official MCP gateway seam and forks", "non-model-facing"],
      [3, "Decision", "non-model-facing"],
      [3, "External repositories", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [3, "Consequence", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Gateway wire transport accepted", "non-model-facing"],
      [3, "Decision", "non-model-facing"],
      [3, "Proposed wire contract", "non-model-facing"],
      [3, "Still open", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Pilot operation contracts proposed", "non-model-facing"],
      [3, "Contract boundary", "non-model-facing"],
      [3, "Source-driven differences", "non-model-facing"],
      [3, "Verification", "non-model-facing"],
      [3, "Still open", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Hermes approval broker accepted", "non-model-facing"],
      [3, "Decision", "non-model-facing"],
      [3, "Reuse boundary", "non-model-facing"],
      [3, "Still open", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Autonomous default clarified", "non-model-facing"],
      [3, "Correction", "non-model-facing"],
      [3, "Consequence", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-29 — Runtime operation approvals removed", "non-model-facing"],
      [3, "Final correction", "non-model-facing"],
      [3, "Superseded work", "non-model-facing"],
      [3, "Consequence", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Evaluation and MCP disposition inventories proposed", "non-model-facing"],
      [3, "Evaluation contracts", "non-model-facing"],
      [3, "External MCP compatibility", "non-model-facing"],
      [3, "Contract corrections from Plane source review", "non-model-facing"],
      [3, "Verification", "non-model-facing"],
      [3, "Still open", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Requirement-level verification coverage proposed", "non-model-facing"],
      [3, "Coverage map", "non-model-facing"],
      [3, "Verifier clarifications", "non-model-facing"],
      [3, "Exact external MCP mapping", "non-model-facing"],
      [3, "Verification state", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Planning evaluation fixtures proposed", "non-model-facing"],
      [3, "Candidate artifacts", "non-model-facing"],
      [3, "Validation evidence", "non-model-facing"],
      [3, "Qualification state", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Safety evaluation evidence design proposed", "non-model-facing"],
      [3, "Source-grounded trial design", "non-model-facing"],
      [3, "Qualification state", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Exact eager Hermes surface approved", "non-model-facing"],
      [3, "User decision", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [2, "2026-07-30 — Deno boundary corrected from current primary sources", "non-model-facing"],
      [3, "Source correction", "non-model-facing"],
      [3, "Qualification state", "non-model-facing"],
      [2, "2026-07-30 — Plane effect cardinality traced", "non-model-facing"],
      [3, "Source correction", "non-model-facing"],
      [3, "Qualification state", "non-model-facing"],
      [2, "2026-08-04 — Accepted contract reconciliation", "non-model-facing"],
      [3, "Reconciliation", "non-model-facing"],
      [2, "2026-08-04 — Durable non-UI ultragoal created", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [3, "Model and delegation policy", "non-model-facing"],
      [3, "Active phase and next action", "non-model-facing"],
      [2, "2026-08-04 — Independent review correction of durable Ultragoal", "non-model-facing"],
      [3, "Corrections", "non-model-facing"],
      [3, "Validation record", "non-model-facing"],
      [2, "2026-08-04 — Sol Medium documentation correction", "non-model-facing"],
      [3, "Correction and evidence", "non-model-facing"],
      [2, "2026-08-04 — P0/G0 pre-approval reconciliation package", "non-model-facing"],
      [3, "Scope and evidence", "non-model-facing"],
      [3, "Contract and control changes", "non-model-facing"],
      [3, "G0 structure added", "non-model-facing"],
      [3, "Validation", "non-model-facing"],
      [3, "Changed-file scope", "non-model-facing"],
      [3, "Next action", "non-model-facing"],
      [3, "Final pre-commit correction", "non-model-facing"],
      [3, "Post-hook digest refresh", "non-model-facing"],
      [2, "2026-08-04 — Fresh Sol Medium remediation evidence seal", "non-model-facing"],
      [3, "Seal generation", "non-model-facing"],
      [3, "Final validation matrix (executed before this entry was appended)", "non-model-facing"],
      [2, "2026-08-04 — Second Sol Medium remediation correction", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [2, "2026-08-04 — Retired-name authority remediation", "non-model-facing"],
      [3, "Evidence", "non-model-facing"],
      [3, "Control-harness correction", "non-model-facing"],
      [2, "2026-08-04 — Fresh Luna remediation: exact retired-token occurrence binding", "non-model-facing"],
      [3, "Scope and checkpoint", "non-model-facing"],
      [3, "Validation evidence", "non-model-facing"],
      [2, "2026-08-04 — Fresh Luna remediation: clause-level historical marker consumption", "non-model-facing"],
      [3, "Scope and design", "non-model-facing"],
      [3, "Content checkpoint", "non-model-facing"],
      [3, "Post-seal validation", "non-model-facing"],
      [
        2,
        "2026-08-04 — Fresh Luna remediation: manifest table, sealed-inventory policy, and cleanup reliability",
        "non-model-facing",
      ],
      [3, "Scope and design", "non-model-facing"],
      [3, "Content checkpoint", "non-model-facing"],
      [
        2,
        "2026-08-04 — Fresh Luna remediation: global retired-family matching and approval-manifest authority",
        "non-model-facing",
      ],
      [3, "Scope and design", "non-model-facing"],
      [3, "Content checkpoint", "non-model-facing"],
      [3, "Post-seal validation", "non-model-facing"],
      [2, "2026-08-04 — Fresh Luna remediation: final sealed validation", "non-model-facing"],
      [2, "2026-08-04 — Fail-closed governed-source authority remediation", "non-model-facing"],
      [3, "Scope and design", "non-model-facing"],
      [3, "Exact control arithmetic", "non-model-facing"],
      [3, "Post-seal validation", "non-model-facing"],
    ],
  },
  "docs/decisions/0001-plane-agent-tooling-architecture.md": {
    preamble: "non-model-facing",
    headings: [
      [
        1,
        "ADR-0001: Shared Plane operation gateway with native Hermes tools and external MCP compatibility",
        "non-model-facing",
      ],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Use MCP internally for Plane-native agents", "non-model-facing"],
      [3, "Expose the complete catalog as eager tools", "non-model-facing"],
      [3, "Project the public OpenAPI schema without curation", "non-model-facing"],
      [3, "Mint run-bound or per-operation capability tokens", "non-model-facing"],
      [3, "Pause and replay Code Mode after approval", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0002-autonomous-agent-operations.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0002: Plane agent operations execute autonomously within Plane authorization", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0003-plane-agent-native-product-boundary.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0003: Plane Agent is a native Plane product", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Embed the Hermes product inside Plane", "non-model-facing"],
      [3, "Keep Plane and Hermes as loosely integrated products", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0004-fork-hermes-as-hidden-execution-kernel.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0004: Fork Hermes as the hidden Plane Agent execution kernel", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Build a new agent runtime", "non-model-facing"],
      [3, "Consume Hermes unchanged as an external service", "non-model-facing"],
      [3, "Copy selected Hermes modules into Plane", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0005-plane-owned-agent-profiles.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0005: Plane owns one role-bearing Agent model", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Create a runtime implementation for each role", "non-model-facing"],
      [3, "Use Hermes profiles as the source of truth", "non-model-facing"],
      [3, "Encode roles only in free-form prompts", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0006-assignment-and-run-lifecycle.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0006: Plane owns assignment and run lifecycle", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Treat a Hermes session as the run or assignment", "non-model-facing"],
      [3, "Use only work-item status", "non-model-facing"],
      [3, "Let Hermes own run state", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0007-adaptive-plane-tool-exposure.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0007: Expose Plane-native tools adaptively", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Expose every Plane and Hermes tool eagerly", "non-model-facing"],
      [3, "Give every profile a fixed closed tool list", "non-model-facing"],
      [3, "Provide one generic read/write operation", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0008-scoped-memory-and-context.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0008: Keep Agent memory and skills private and governable", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "One shared company memory document", "non-model-facing"],
      [3, "Let every agent maintain private unstructured memory", "non-model-facing"],
      [3, "Let gardeners copy knowledge between agents", "non-model-facing"],
      [3, "Disable durable memory permanently", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0009-workflows-and-agent-delegation.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0009: Use dynamic planning and delegation, not saved workflows", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Add a saved workflow-definition product", "non-model-facing"],
      [3, "Let every agent delegate freely", "non-model-facing"],
      [3, "Encode all delegation only in skills", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
  "docs/decisions/0010-plane-runtime-contract.md": {
    preamble: "non-model-facing",
    headings: [
      [1, "ADR-0010: Use one versioned Plane runtime contract", "non-model-facing"],
      [2, "Status", "non-model-facing"],
      [2, "Date", "non-model-facing"],
      [2, "Context", "non-model-facing"],
      [2, "Decision", "non-model-facing"],
      [3, "Runtime hierarchy", "non-model-facing"],
      [3, "Run snapshot and invocation envelope", "non-model-facing"],
      [3, "Events and exit", "non-model-facing"],
      [3, "Isolation and compatibility", "non-model-facing"],
      [2, "Alternatives considered", "non-model-facing"],
      [3, "Expose `AIAgent` directly to Plane", "non-model-facing"],
      [3, "Import the runtime adapter into the Plane API process", "non-model-facing"],
      [3, "Make Hermes sessions the Plane run record", "non-model-facing"],
      [3, "Use a multi-method start, stream, persist, and finalize protocol", "non-model-facing"],
      [3, "Import Buzz ACP as the runtime protocol", "non-model-facing"],
      [2, "Consequences", "non-model-facing"],
    ],
  },
};

const structuredPolicyPaths = [
  "docs/agent-tooling/NON-UI-IMPLEMENTATION-PLAN.json",
  "docs/agent-tooling/fixtures/planning-v1.json",
  "docs/agent-tooling/fixtures/planning-v1.predicates.json",
  "docs/agent-tooling/fixtures/planning-v1.predicates.schema.json",
  "docs/agent-tooling/fixtures/planning-v1.schema.json",
  "docs/agent-tooling/g0-readiness.json",
  "docs/agent-tooling/g0-readiness.schema.json",
  "docs/agent-tooling/integration-lock.g0.json",
  "docs/agent-tooling/integration-lock.schema.json",
  "docs/agent-tooling/inventories/plane-mcp-v0.2.11.json",
  "docs/agent-tooling/model-facing-surface.json",
  "docs/agent-tooling/model-facing-surface.schema.json",
  "docs/agent-tooling/ownership-map.json",
  "docs/agent-tooling/ownership-map.schema.json",
];

const verifierPolicyPaths = [
  "docs/agent-tooling/verifiers/render-non-ui-implementation-plan.mjs",
  "docs/agent-tooling/verifiers/render-requirement-coverage.mjs",
  "docs/agent-tooling/verifiers/run-g0-negative-controls.mjs",
  "docs/agent-tooling/verifiers/seal-g0-evidence.mjs",
  "docs/agent-tooling/verifiers/test-g0-approved-fixture.mjs",
  "docs/agent-tooling/verifiers/validate-ajv-2020.mjs",
  "docs/agent-tooling/verifiers/validate-ownership-map.mjs",
  "docs/agent-tooling/verifiers/validate-planning-fixtures.mjs",
  "docs/agent-tooling/verifiers/validate-requirement-coverage.mjs",
  "docs/agent-tooling/verifiers/verify-g0-preflight.mjs",
];

// Structured declarations are intentionally scoped to semantic fields and
// bounded evidence subtrees. There is no document-root fallback: a new string
// pointer outside these declarations is unclassified until it is deliberately
// classified.
const structuredAuthority = {
  "docs/agent-tooling/NON-UI-IMPLEMENTATION-PLAN.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["title"],
      ["status"],
      ["scope", "included"],
      ["scope", "excluded"],
      ["scope", "uiRule"],
      ["principles"],
      ["phaseLaneRelationships"],
      ["gates"],
      ["lanes"],
    ],
  },
  "docs/agent-tooling/fixtures/planning-v1.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["schema"],
      ["fixture_set_id"],
      ["seed_clock"],
      ["symbolic_identity_rule"],
      ["impact_scoring"],
      ["shared"],
      ["fixtures"],
      ["common_expected"],
    ],
  },
  "docs/agent-tooling/fixtures/planning-v1.predicates.json": {
    authoritative: [["common", "*", "expected", "required", "*"]],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["schema"],
      ["predicate_set_id"],
      ["fixture_set"],
      ["common"],
      ["plan_created"],
      ["scenario_overrides"],
    ],
  },
  "docs/agent-tooling/fixtures/planning-v1.predicates.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [["$schema"], ["$id"], ["title"], ["type"], ["required"], ["properties"], ["$defs"]],
  },
  "docs/agent-tooling/fixtures/planning-v1.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [["$schema"], ["$id"], ["title"], ["type"], ["required"], ["properties"], ["$defs"]],
  },
  "docs/agent-tooling/g0-readiness.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["recordId"],
      ["status"],
      ["approval"],
      ["owners"],
      ["integrationLock"],
      ["evidenceDigests"],
      ["clauses"],
      ["preflightCommand"],
      ["normalVerificationCommand"],
    ],
  },
  "docs/agent-tooling/g0-readiness.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["$id"],
      ["title"],
      ["type"],
      ["required"],
      ["properties"],
      ["$defs"],
      ["allOf"],
    ],
  },
  "docs/agent-tooling/integration-lock.g0.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["lockId"],
      ["status"],
      ["reviewedBaseline"],
      ["repositories"],
      ["digests"],
      ["seal"],
      ["pendingInputs"],
      ["owners"],
    ],
  },
  "docs/agent-tooling/integration-lock.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [["$schema"], ["$id"], ["title"], ["type"], ["required"], ["properties"]],
  },
  "docs/agent-tooling/inventories/plane-mcp-v0.2.11.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [["repository"], ["commit"], ["version"], ["tools"]],
  },
  "docs/agent-tooling/model-facing-surface.json": {
    authoritative: [
      ["names", "*", "name"],
      ["names", "*", "description"],
    ],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["surfaceId"],
      ["status"],
      ["g0ContractPolicy"],
      ["names", "*", "kind"],
      ["names", "*", "operationId"],
      ["names", "*", "disclosure"],
      ["retiredNames"],
    ],
  },
  "docs/agent-tooling/model-facing-surface.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [["properties", "names", "items", "properties", "description"]],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["$id"],
      ["title"],
      ["type"],
      ["required"],
      ["properties", "$schema"],
      ["properties", "surfaceId"],
      ["properties", "status"],
      ["properties", "g0ContractPolicy"],
      ["properties", "names", "type"],
      ["properties", "names", "items", "required"],
      ["properties", "names", "items", "type"],
      ["properties", "names", "items", "properties", "name"],
      ["properties", "names", "items", "properties", "kind"],
      ["properties", "names", "items", "properties", "operationId"],
      ["properties", "names", "items", "properties", "disclosure"],
      ["properties", "names", "items", "properties", "eager"],
      ["properties", "retiredNames"],
    ],
  },
  "docs/agent-tooling/ownership-map.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["mapId"],
      ["status"],
      ["repositoryRoot"],
      ["overlapRule"],
      ["owners", "*", "ownerId"],
      ["owners", "*", "role"],
      ["owners", "*", "repository"],
      ["owners", "*", "planLaneIds"],
      ["owners", "*", "writePaths"],
      ["owners", "*", "readPaths"],
      ["owners", "*", "restriction"],
      ["surfaces", "*", "surfaceId"],
      ["surfaces", "*", "description"],
      ["surfaces", "*", "repository"],
      ["surfaces", "*", "paths"],
      ["surfaces", "*", "ownerId"],
      ["surfaces", "*", "planLaneIds"],
      ["requiredSurfaceIds"],
    ],
  },
  "docs/agent-tooling/ownership-map.schema.json": {
    authoritative: [],
    authoritativeSubtrees: [],
    nonModelFacingSubtrees: [
      ["$schema"],
      ["$id"],
      ["title"],
      ["type"],
      ["required"],
      ["properties", "$schema"],
      ["properties", "mapId"],
      ["properties", "status"],
      ["properties", "repositoryRoot"],
      ["properties", "overlapRule"],
      ["properties", "owners"],
      ["properties", "surfaces"],
      ["properties", "requiredSurfaceIds"],
    ],
  },
};

const retiredNameSourcePolicy = {
  markdownPaths: markdownPolicyPaths,
  structuredPaths: structuredPolicyPaths,
  verifierPaths: verifierPolicyPaths,
  markdownSectionPolicy,
  structuredAuthority,
};

function absolute(relativePath) {
  return relativePath.startsWith("docs/") ? resolve(repositoryRoot, relativePath) : resolve(root, relativePath);
}

function read(relativePath) {
  return readFileSync(absolute(relativePath), "utf8");
}

function readBytes(relativePath) {
  return readFileSync(absolute(relativePath));
}

function readJson(relativePath) {
  return JSON.parse(read(relativePath));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function check(name, fn, { approvalOnly = false } = {}) {
  try {
    fn();
    results.push({ name, status: "pass" });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    results.push({ name, status: approvalOnly ? "pending" : "fail", message });
    if (!approvalOnly) failures.push({ name, message });
  }
}

function git(cwd, args, { allowFailure = false } = {}) {
  const result = spawnSync("git", ["-C", cwd, ...args], { encoding: "utf8" });
  if (!allowFailure && result.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`);
  }
  return { status: result.status ?? 1, stdout: result.stdout.trim(), stderr: result.stderr.trim() };
}

function runCommand(program, args) {
  const result = spawnSync(program, args, { cwd: repositoryRoot, encoding: "utf8" });
  return { status: result.status ?? 1, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function gitShow(commit, path) {
  const result = spawnSync("git", ["-C", repositoryRoot, "show", `${commit}:${path}`], { encoding: "buffer" });
  assert(result.status === 0, `git show cannot read ${commit}:${path}`);
  return result.stdout;
}

function fileDigest(relativePath) {
  return sha256(readBytes(relativePath));
}

function validateWithAjv(schemaPath, valuePath, label) {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const validate = ajv.compile(readJson(schemaPath));
  const valid = validate(readJson(valuePath));
  assert(valid, `${label} failed AJV 2020 validation: ${JSON.stringify(validate.errors)}`);
}

function checkMarkdownLinks() {
  const headingCache = new Map();
  function anchorsFor(path) {
    if (headingCache.has(path)) return headingCache.get(path);
    const source = read(path);
    const anchors = new Set();
    const counts = new Map();
    for (const line of source.split("\n")) {
      const heading = line.match(/^#{1,6}\s+(.+?)\s*#*$/);
      if (!heading) continue;
      const text = heading[1].replaceAll(/[`*_~]/g, "").replaceAll(/<[^>]+>/g, "");
      const base = text
        .toLowerCase()
        .trim()
        .replaceAll(/[^\p{Letter}\p{Number} -]/gu, "")
        .replaceAll(/\s+/g, "-");
      const count = counts.get(base) ?? 0;
      counts.set(base, count + 1);
      anchors.add(count === 0 ? base : `${base}-${count}`);
    }
    for (const match of source.matchAll(/<(?:a|span)[^>]+(?:id|name)=["']([^"']+)["'][^>]*>/gi)) anchors.add(match[1]);
    headingCache.set(path, anchors);
    return anchors;
  }
  for (const path of canonicalMarkdown) {
    const file = absolute(`docs/agent-tooling/${path}`);
    assert(existsSync(file), `canonical Markdown file is missing: ${path}`);
    const source = read(`docs/agent-tooling/${path}`);
    for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const raw = match[1].trim().split(/\s+/)[0].replace(/^<|>$/g, "");
      if (!raw || /^(?:https?:|mailto:|#?\/\/)/i.test(raw)) continue;
      const [targetPart, anchor] = raw.split("#", 2);
      const target = targetPart ? decodeURIComponent(targetPart) : `docs/agent-tooling/${path}`;
      const targetPath = isAbsolute(target) ? target : resolve(dirname(file), target);
      assert(existsSync(targetPath), `${path} links to missing ${raw}`);
      if (anchor) {
        const targetRelative = relative(root, targetPath);
        assert(anchorsFor(targetRelative).has(decodeURIComponent(anchor)), `${path} links to missing anchor ${raw}`);
      }
    }
  }
  for (const path of canonicalMarkdown) {
    for (const match of read(`docs/agent-tooling/${path}`).matchAll(/\/(?:Users|private\/tmp)\/[A-Za-z0-9_./-]+/g)) {
      const candidate = match[0].replace(/[.,;:]+$/, "");
      throw new Error(`${path} contains a non-portable absolute path ${candidate}`);
    }
  }
}

function markdownSectionPolicyFor(path, source) {
  const policy = retiredNameSourcePolicy.markdownSectionPolicy[path];
  assert(policy, `${path} has no Markdown section policy`);
  assert(
    new Set(["authoritative/model-facing", "non-model-facing"]).has(policy.preamble),
    `${path} has an invalid Markdown preamble classification`
  );
  const headings = [...source.matchAll(/^(#{1,6})\s+(.+?)\s*#*$/gm)].map((match) => [match[1].length, match[2]]);
  const declaredHeadings = policy.headings.map(([level, heading, classification]) => {
    assert(
      Number.isInteger(level) &&
        typeof heading === "string" &&
        new Set(["authoritative/model-facing", "non-model-facing"]).has(classification),
      `${path} has an invalid Markdown section declaration`
    );
    return [level, heading];
  });
  assert(
    JSON.stringify(headings) === JSON.stringify(declaredHeadings),
    `${path} has an unclassified or stale Markdown section policy`
  );
  return {
    preamble: policy.preamble,
    headings: [...source.matchAll(/^(#{1,6})\s+(.+?)\s*#*$/gm)].map((match, index) => ({
      start: match.index,
      heading: match[2],
      classification: policy.headings[index][2],
    })),
  };
}

function parseFrozenModelFacingTable(manifest) {
  const heading = "## Frozen model-facing surface";
  const headingStart = manifest.indexOf(heading);
  assert(headingStart >= 0, "manifest is missing the Frozen model-facing surface section");
  const sectionEnd = manifest.indexOf("\n## ", headingStart + heading.length);
  const section = manifest.slice(headingStart, sectionEnd === -1 ? manifest.length : sectionEnd);
  const lines = section.split("\n");
  const headerIndexes = lines
    .map((line, index) => ({ line, index }))
    .filter(({ line }) => /^\|.*\|$/.test(line))
    .filter(({ line }) => line.split("|")[1]?.trim() === "Model-facing name")
    .map(({ index }) => index);
  assert(headerIndexes.length === 1, "manifest frozen model-facing table must have exactly one name header");
  const headerIndex = headerIndexes[0];
  assert(
    /^\|(?:\s*:?-{3,}:?\s*\|){4}$/.test(lines[headerIndex + 1] ?? ""),
    "manifest frozen model-facing table has an invalid separator"
  );
  const rows = [];
  for (let index = headerIndex + 2; index < lines.length && /^\|.*\|$/.test(lines[index]); index += 1) {
    const cells = lines[index]
      .trim()
      .slice(1, -1)
      .split("|")
      .map((cell) => cell.trim());
    assert(cells.length === 4, "manifest frozen model-facing table row must have four columns");
    rows.push(cells[0].replace(/^`|`$/g, ""));
  }
  assert(rows.length > 0, "manifest frozen model-facing table has no data rows");
  return rows;
}

function checkPolicyCoverage(lock) {
  const governed = [
    ...retiredNameSourcePolicy.markdownPaths,
    ...retiredNameSourcePolicy.structuredPaths,
    ...retiredNameSourcePolicy.verifierPaths,
  ];
  assert(new Set(governed).size === governed.length, "retired-name source policy contains duplicate paths");
  const sealed = [...new Set([...lock.seal.contentPaths, ...lock.seal.sealEvidencePaths])].toSorted();
  assert(
    JSON.stringify(governed.toSorted()) === JSON.stringify(sealed),
    "retired-name source policy must exactly cover sealed content and governed seal evidence paths"
  );
  assert(
    JSON.stringify(Object.keys(retiredNameSourcePolicy.markdownSectionPolicy).toSorted()) ===
      JSON.stringify(retiredNameSourcePolicy.markdownPaths.toSorted()),
    "retired-name Markdown section policy paths are missing or stale"
  );
  const expectedMarkdown = [
    ...canonicalMarkdown.map((path) =>
      path.startsWith("../") ? `docs/${path.slice(3)}` : `docs/agent-tooling/${path}`
    ),
    "docs/agent-tooling/SOURCE-INVENTORY.md",
    "docs/agent-tooling/WORKLOG.md",
  ]
    .filter((path, index, all) => all.indexOf(path) === index)
    .toSorted();
  assert(
    JSON.stringify(retiredNameSourcePolicy.markdownPaths.toSorted()) === JSON.stringify(expectedMarkdown),
    "retired-name Markdown policy does not exactly cover canonical Markdown and governed evidence"
  );
  for (const path of retiredNameSourcePolicy.markdownPaths) markdownSectionPolicyFor(path, read(path));
  assert(
    JSON.stringify(Object.keys(retiredNameSourcePolicy.structuredAuthority).toSorted()) ===
      JSON.stringify(retiredNameSourcePolicy.structuredPaths.toSorted()),
    "retired-name structured authority policy paths are missing or stale"
  );
}

function checkAdrRegister() {
  for (const name of [
    "0001-plane-agent-tooling-architecture.md",
    "0002-autonomous-agent-operations.md",
    "0003-plane-agent-native-product-boundary.md",
    "0004-fork-hermes-as-hidden-execution-kernel.md",
    "0005-plane-owned-agent-profiles.md",
    "0006-assignment-and-run-lifecycle.md",
    "0007-adaptive-plane-tool-exposure.md",
    "0008-scoped-memory-and-context.md",
    "0009-workflows-and-agent-delegation.md",
    "0010-plane-runtime-contract.md",
  ])
    assert(/^Accepted(?:$|;)/m.test(read(`../decisions/${name}`)), `${name} is not Accepted`);
  const register = read("decision-register.md");
  assert(/\| ATD-143 \|/.test(register), "decision register does not contain ATD-143");
  assert(
    /ADR-0008, ADR-0009, and ADR-0010 are accepted/.test(register),
    "register does not bind ATD-143 to the three ADRs"
  );
  assert(
    /\| ATO-020 \|/.test(register) && /\| ATO-018 \|/.test(register) && /\| ATO-014 \|/.test(register),
    "later-lane decisions are not retained as open"
  );
}

function checkAuthorityAndContractPolicy() {
  const manifest = read(paths.manifest);
  assert(manifest.includes("sole G0 human approval authority"), "manifest does not declare the sole G0 authority");
  assert(
    manifest.includes("G1 freezes generated operation/event schemas"),
    "manifest does not demote schema freezing to G1"
  );
  assert(
    manifest.includes("Physical queue/RPC transport remains a later"),
    "manifest does not preserve the later physical transport choice"
  );
  for (const path of [
    "PILOT-CONTRACTS.md",
    "RELEASE-MANIFEST.md",
    "VERIFICATION-MANIFEST.md",
    "EVALUATION-FIXTURE-CONTRACT.md",
    "REQUIREMENT-COVERAGE.md",
  ]) {
    const source = read(`docs/agent-tooling/${path}`);
    assert(
      /cannot approve|not an approval|single G0 human approval|evidence input/i.test(source),
      `${path} lacks an explicit demotion to evidence/input status`
    );
  }
  const plan = readJson(paths.plan);
  const gate = plan.gates.find((candidate) => candidate.id === "G0");
  assert(
    gate?.exit.some((line) => /generated operation\/event schemas are a G1 input/i.test(line)),
    "G0 still freezes generated schemas"
  );
  assert(
    gate?.exit.some((line) => /physical.*queue\/RPC.*implementation-defined under ADR-0010/i.test(line)),
    "G0 does not preserve the later physical transport choice"
  );
  assert(
    !read(paths.overview).includes("Freeze the pilot operation catalog, model-facing presentation, runtime transport"),
    "generated overview still freezes physical runtime transport at G0"
  );
}

function checkAcceptedAdrSchemaAuthority() {
  for (const path of canonicalMarkdown.filter((candidate) => candidate.startsWith("../decisions/"))) {
    const source = read(`docs/agent-tooling/${path}`)
      .replaceAll(/<!--.*?-->/gs, " ")
      .replaceAll(/\s+/g, " ");
    const mentionsSchemas =
      /\b(?:generated|exact|JSON|snapshot|envelope|runtime event)[^.!?]{0,160}\bschemas?\b|\bschemas?\b[^.!?]{0,160}\b(?:generated|exact|JSON|snapshot|envelope|runtime event)\b/i.test(
        source
      );
    const mentionsImplementationPrerequisite =
      /\b(?:before|prior to|precede|preceding)\b[^.!?]{0,160}\b(?:implementation|implementing|AIAgent adaptation|runtime lane|application lane|verification lane)\b/i.test(
        source
      );
    if (mentionsSchemas && mentionsImplementationPrerequisite) {
      assert(
        /\bG1\b[^.!?]{0,180}\b(?:generate|freeze|schema|consumer|lane)|\b(?:consumer|lane)[^.!?]{0,180}\bG1\b/i.test(
          source
        ),
        `${path} retains a generated-schema prerequisite before implementation without the G1 consumer-lane boundary`
      );
    }
  }
  const runtimeAdr = read("../decisions/0010-plane-runtime-contract.md");
  assert(
    /G0[\s\S]{0,500}logical type names[\s\S]{0,500}G1[\s\S]{0,500}exact JSON Schema bytes/i.test(runtimeAdr),
    "ADR-0010 does not state the G0 logical-contract and G1 generated-schema authority boundary"
  );
  assert(
    /implementation lanes that consume those generated schemas/i.test(runtimeAdr),
    "ADR-0010 does not bind generated schema freezing to the lanes that consume it"
  );
}

function checkManifestAndDigests(lock, readiness) {
  const manifest = read(paths.manifest);
  const statusLine = manifest.split("\n").find((line) => line.startsWith("**")) ?? "";
  assert(statusLine.includes("Ready for approval"), "manifest is not in Ready for approval status");
  assert(!statusLine.includes("Approved"), "manifest status must not claim Approved");
  assert(!manifest.includes("STATUS_APPROVED"), "manifest contains a fake approval marker");
  assert(readiness.approval.statement === expectedApprovalStatement, "G0 approval statement changed");
  assert(
    readiness.approval.manifestDigest === lock.digests.files[paths.manifest],
    "readiness manifest digest differs from lock"
  );
  assert(
    readiness.evidenceDigests.files &&
      JSON.stringify(readiness.evidenceDigests.files) === JSON.stringify(lock.digests.files),
    "readiness and lock evidence maps are not byte-for-byte equal"
  );
}

function checkSourceAndRepositoryPins(lock) {
  const inventory = read(paths.sourceInventory);
  assert(!/\/Users\/|\/private\/tmp\//.test(inventory), "source inventory contains an absolute or ephemeral path");
  const contentCommit = lock.seal.contentCommit;
  const plane = lock.repositories.find((repository) => repository.id === "plane");
  assert(plane?.sha === contentCommit, "Plane repository SHA must equal sealed contentCommit");
  for (const repository of lock.repositories)
    assert(inventory.includes(repository.sha), `source inventory does not contain ${repository.id} SHA`);
  const ancestry = git(repositoryRoot, ["merge-base", "--is-ancestor", lock.reviewedBaseline.planeSha, contentCommit], {
    allowFailure: true,
  });
  assert(ancestry.status === 0, "reviewed Plane baseline is not an ancestor of sealed contentCommit");
  assert(
    git(root, ["remote", "get-url", "upstream"]).stdout === plane.remote,
    "Plane upstream remote differs from integration lock"
  );
  const status = git(repositoryRoot, ["status", "--porcelain", "--untracked-files=all"]).stdout;
  const permittedDirty =
    negativeControlMode && repositoryRoot.startsWith(resolve(tmpdir())) && existsSync(negativeMarker);
  if (!permittedDirty) assert(status === "", "authoritative Plane checkout must be clean");
  for (const [path, repositoryId] of Object.entries({
    "external/plane-mcp-server": "plane-mcp",
    "external/plane-python-sdk": "plane-sdk",
  })) {
    const pinned = git(repositoryRoot, ["ls-tree", contentCommit, path]).stdout.split(/\s+/)[2];
    const expected = lock.repositories.find((repository) => repository.id === repositoryId)?.sha;
    assert(pinned === expected, `${path} gitlink differs from integration lock`);
  }
}

function changedPaths(commit) {
  return git(repositoryRoot, ["diff-tree", "--no-commit-id", "--name-status", "-r", commit])
    .stdout.split("\n")
    .filter(Boolean)
    .map((line) => line.split("\t"));
}

function checkSeal(lock, readiness) {
  const head = git(repositoryRoot, ["rev-parse", "HEAD"]).stdout;
  const contentCommit = lock.seal.contentCommit;
  assert(contentCommit !== "0".repeat(40), "seal contentCommit is unpopulated");
  assert(
    git(repositoryRoot, ["rev-parse", `${contentCommit}^{tree}`]).stdout === lock.seal.contentTree,
    "sealed content tree is stale"
  );
  const headParent = git(repositoryRoot, ["rev-parse", "HEAD^"]).stdout;
  const sealCommit =
    readiness.status === "pending-human-approval" ? head : readiness.approval.evidenceBinding.sealedHead;
  assert(sealCommit && /^[0-9a-f]{40}$/.test(sealCommit), "seal commit is not recorded as a full commit SHA");
  const sealParent = git(repositoryRoot, ["rev-parse", `${sealCommit}^`]).stdout;
  assert(sealParent === contentCommit, "seal commit first parent must equal recorded contentCommit");
  const allowedSealPaths = [...lock.seal.allowedSealPaths].toSorted();
  assert(
    JSON.stringify([...lock.seal.sealEvidencePaths].toSorted()) === JSON.stringify(allowedSealPaths),
    "seal evidence paths must equal the allowed seal paths"
  );
  const sealChanges = changedPaths(sealCommit).toSorted((left, right) =>
    left.join("\0").localeCompare(right.join("\0"))
  );
  const expectedSealChanges = allowedSealPaths
    .map((path) => ["M", path])
    .toSorted((left, right) => left.join("\0").localeCompare(right.join("\0")));
  assert(
    JSON.stringify(sealChanges) === JSON.stringify(expectedSealChanges),
    `seal commit changed paths are not exactly the four allowed seal paths: ${JSON.stringify(sealChanges)}`
  );
  const allowed = new Set(lock.seal.allowedSealPaths);
  for (const path of lock.seal.contentPaths) {
    assert(!allowed.has(path), `content path is also an allowed seal path: ${path}`);
    assert(lock.digests.files[path] === fileDigest(path), `seal-bound digest mismatch for ${path}`);
    assert(
      sha256(gitShow(contentCommit, path)) === lock.digests.files[path],
      `content commit bytes differ for ${path}`
    );
  }
  assert(lock.seal.contentPaths.includes(paths.result), "RESULT.md must be in the normative seal content set");
  const evidencePaths = [...lock.seal.contentPaths, "docs/agent-tooling/SOURCE-INVENTORY.md"].toSorted();
  assert(
    JSON.stringify(Object.keys(lock.digests.files).toSorted()) === JSON.stringify(evidencePaths),
    "lock does not bind exactly the declared normative files"
  );
  assert(
    lock.digests.files[paths.sourceInventory] === fileDigest(paths.sourceInventory),
    "source inventory digest is stale"
  );
  const baseline = gitShow(lock.seal.worklogBaseline.commit, "docs/agent-tooling/WORKLOG.md");
  const worklog = readBytes("docs/agent-tooling/WORKLOG.md");
  assert(worklog.length > baseline.length, "WORKLOG has no appended remediation evidence");
  assert(
    lock.seal.worklogBaseline.byteLength === baseline.length && lock.seal.worklogBaseline.sha256 === sha256(baseline),
    "WORKLOG baseline seal is stale"
  );
  assert(
    sha256(worklog.subarray(0, baseline.length)) === lock.seal.worklogBaseline.sha256,
    "WORKLOG pre-existing prefix was modified"
  );
  if (readiness.status !== "pending-human-approval") {
    const sealedHead = readiness.approval.evidenceBinding.sealedHead;
    assert(
      sealCommit === sealedHead && headParent === sealedHead,
      "approved state must be an explicit readiness-only transition from the sealed head"
    );
    assert(
      git(repositoryRoot, ["rev-parse", `${sealedHead}^`]).stdout === contentCommit,
      "approved state is not based on the sealed content commit"
    );
    const parentLock = JSON.parse(gitShow(sealedHead, paths.lock));
    assert(parentLock.seal.contentCommit === contentCommit, "approved state parent does not carry the same seal");
    const approvalChanges = changedPaths(head);
    assert(
      JSON.stringify(approvalChanges) === JSON.stringify([["M", paths.readiness]]),
      "approved transition changed more than g0-readiness.json"
    );
  }
}

function checkOwnershipAndSchemas(lock, readiness) {
  for (const [schema, instance, label] of [
    [paths.lockSchema, paths.lock, "integration lock"],
    [paths.readinessSchema, paths.readiness, "G0 readiness"],
    [paths.ownershipSchema, paths.ownershipMap, "ownership map"],
    [paths.modelSurfaceSchema, paths.modelSurface, "model-facing surface"],
    [paths.fixtureSchema, paths.fixture, "planning fixtures"],
    [paths.predicateSchema, paths.predicates, "planning predicates"],
  ])
    validateWithAjv(schema, instance, label);
  assert(lock.status === "candidate-for-approval", "integration lock cannot be approved independently");
  assert(
    lock.pendingInputs.every((input) => input.state === "pending" && /^G[1-5]$/.test(input.dependentGate)),
    "future inputs must remain explicit pending slots with a declared gate"
  );
  assert(readiness.clauses.length === 9, "G0 readiness must contain nine clauses");
  assert(
    readiness.clauses.every((clause) => clause.reviewerRole === "sol-reviewer"),
    "every G0 clause must name Sol as reviewer"
  );
  const ownershipResult = runCommand("node", ["docs/agent-tooling/verifiers/validate-ownership-map.mjs"]);
  assert(
    ownershipResult.status === 0,
    `ownership validator failed: ${(ownershipResult.stdout + ownershipResult.stderr).trim()}`
  );
}

function checkModelFacingSurface() {
  const surface = readJson(paths.modelSurface);
  const expected = [
    "search_workspace",
    "search_catalog",
    "describe_operation",
    "compose_typescript",
    "search_work_items",
    "get_work_item",
    "create_work_item",
    "update_work_item",
    "create_comment",
  ];
  assert(
    JSON.stringify(surface.names.map((entry) => entry.name)) === JSON.stringify(expected),
    "model-facing name set is not exact or ordered"
  );
  assert(
    JSON.stringify(surface.names.filter((entry) => entry.kind === "eager-direct").map((entry) => entry.name)) ===
      JSON.stringify(expected.slice(4)),
    "eager direct set is not exact"
  );
  assert(
    surface.names.find((entry) => entry.name === "search_workspace").description.includes("not work-item lookup"),
    "search_workspace is not separated from search_work_items"
  );
  assert(
    surface.names
      .find((entry) => entry.name === "search_work_items")
      .description.includes("does not cover all workspace object types"),
    "search_work_items is not separated from search_workspace"
  );
  assert(
    surface.g0ContractPolicy.generatedSchemaGate === "G1" &&
      surface.g0ContractPolicy.physicalTransportGate.includes("later"),
    "model surface has an invalid G0/G1 policy"
  );
  assert(
    JSON.stringify(parseFrozenModelFacingTable(read(paths.manifest))) === JSON.stringify(expected),
    "frozen manifest model-facing table differs from the exact ordered model-facing surface"
  );
}

function escapeRegExp(value) {
  return value.replaceAll(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function tokenOccurrences(text, name) {
  const token = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(name)}(?![A-Za-z0-9_])`, "g");
  return [...text.matchAll(token)].map((match) => ({ start: match.index, end: match.index + match[0].length }));
}

function rangesForPattern(text, pattern, valueGroup = 0) {
  return [...text.matchAll(pattern)].map((match) => {
    const value =
      valueGroup === 0 ? match[0] : (match.slice(valueGroup).find((candidate) => candidate !== undefined) ?? match[0]);
    const valueOffset = valueGroup === 0 ? 0 : match[0].indexOf(value);
    return { start: match.index + valueOffset, end: match.index + valueOffset + value.length };
  });
}

function isWithinRange(occurrence, ranges) {
  return ranges.some((range) => occurrence.start >= range.start && occurrence.end <= range.end);
}

function classifyHistoricalOccurrences(line, occurrences) {
  const markerPattern =
    /\b(?:retired|historical|negative[- ]control|legacy|supersed(?:ed|es)?|rejected|forbidden|replaced)\b/gi;
  const separators = /[;|.!?\n]/g;
  const separatorPositions = [...line.matchAll(separators)].map((match) => match.index);
  const historical = new Set();

  // Pair each marker and occurrence once at the clause level. A marker between
  // two occurrences has two directional candidates, so it is ambiguous and
  // cannot exempt either occurrence from authoritative-name validation.
  const clauses = [];
  let clauseStart = 0;
  for (const separatorPosition of [...separatorPositions, line.length]) {
    clauses.push({ start: clauseStart, end: separatorPosition });
    clauseStart = separatorPosition + 1;
  }

  const consumedMarkers = new Set();
  const consumedOccurrences = new Set();

  for (const clause of clauses) {
    const clauseOccurrences = occurrences
      .map((occurrence, index) => ({ occurrence, index }))
      .filter(({ occurrence }) => occurrence.start >= clause.start && occurrence.end <= clause.end);
    const clauseMarkers = [...line.matchAll(markerPattern)]
      .map((match) => ({ start: match.index, end: match.index + match[0].length }))
      .filter((marker) => marker.start >= clause.start && marker.end <= clause.end);

    const markerCandidates = clauseMarkers.map((marker) => {
      const candidates = new Set();
      const firstFollowing = clauseOccurrences.find(({ occurrence }) => occurrence.start >= marker.end);
      const lastPreceding = clauseOccurrences.findLast(({ occurrence }) => occurrence.end <= marker.start);
      if (firstFollowing) candidates.add(firstFollowing.index);
      if (lastPreceding) candidates.add(lastPreceding.index);
      return { marker, candidates };
    });

    // A marker is usable only when its occurrence candidate is unique in both
    // directions. This rejects between-occurrence ambiguity and competing
    // markers, and the consumed sets make the one-to-one rule global across
    // all retired-name families and all clauses in the line.
    for (const { marker, candidates } of markerCandidates) {
      if (candidates.size !== 1 || consumedMarkers.has(marker.start)) continue;
      const [occurrenceIndex] = candidates;
      const contenders = markerCandidates.filter((candidate) => candidate.candidates.has(occurrenceIndex));
      if (contenders.length !== 1 || contenders[0].candidates.size !== 1) continue;
      if (consumedOccurrences.has(occurrenceIndex)) continue;

      consumedMarkers.add(marker.start);
      consumedOccurrences.add(occurrenceIndex);
      historical.add(occurrenceIndex);
    }
  }

  return occurrences.map((_, index) => historical.has(index));
}

function designatedInternalIdentifierRanges(line) {
  const ranges = rangesForPattern(
    line,
    /\b(?:operationId|runtime[-_ ]adapter(?:[-_ ](?:identifier|id))?|adapter[-_ ](?:identifier|id))\b\s*[:=]\s*(?:"([^"]+)"|'([^']+)'|`([^`]+)`|([A-Za-z0-9_.@-]+))/gi,
    1
  );
  ranges.push(...rangesForPattern(line, /[`"]plane\.[a-z0-9_.-]+@[0-9]+[`"]?/gi));
  ranges.push(...rangesForPattern(line, /\bplane_runtime\.[A-Za-z0-9_.-]+/g));
  return ranges;
}

function ordinaryPathRanges(line) {
  return rangesForPattern(line, /\bdocs\/[-A-Za-z0-9_./]+/g);
}

function hasAuthorityMarker(line) {
  return /\bauthoritative\s+(?:model[- ]facing|name|description|purpose|schema|operation|alias|input|output|error)\b|\bmodel[- ]facing\s+(?:name|description|purpose|schema|operation|alias|input|output|error)\b|\b(?:semantic purpose|input note|output note|error note|schema note)\b/i.test(
    line
  );
}

function retiredNameOccurrences(line, retiredNames) {
  return retiredNames
    .flatMap((name, familyIndex) =>
      tokenOccurrences(line, name).map((occurrence, occurrenceIndex) => ({
        start: occurrence.start,
        end: occurrence.end,
        name,
        familyIndex,
        occurrenceIndex,
      }))
    )
    .toSorted(
      (left, right) =>
        left.start - right.start ||
        left.end - right.end ||
        left.familyIndex - right.familyIndex ||
        left.occurrenceIndex - right.occurrenceIndex
    );
}

function retiredNameViolations(line, retiredNames, { authoritative = false, structured = false } = {}) {
  const occurrences = retiredNameOccurrences(line, retiredNames);
  if (occurrences.length === 0 || (!structured && !authoritative && !hasAuthorityMarker(line))) return new Set();
  const internalRanges = designatedInternalIdentifierRanges(line);
  const pathRanges = ordinaryPathRanges(line);
  const historical = classifyHistoricalOccurrences(line, occurrences);
  return new Set(
    occurrences
      .filter(
        (occurrence, index) =>
          !historical[index] && !isWithinRange(occurrence, internalRanges) && !isWithinRange(occurrence, pathRanges)
      )
      .map((occurrence) => occurrence.name)
  );
}

function pointerMatches(segments, pattern) {
  return segments.length === pattern.length && pattern.every((part, index) => part === "*" || part === segments[index]);
}

function pointerStartsWith(segments, pattern) {
  return segments.length >= pattern.length && pattern.every((part, index) => part === "*" || part === segments[index]);
}

function structuredFieldClassification(path, segments) {
  const policy = retiredNameSourcePolicy.structuredAuthority[path];
  assert(policy, `${path} has no structured authority policy`);
  if (
    policy.authoritative.some((pattern) => pointerMatches(segments, pattern)) ||
    policy.authoritativeSubtrees.some((pattern) => pointerStartsWith(segments, pattern))
  )
    return "authoritative";
  if (policy.nonModelFacingSubtrees.some((pattern) => pointerStartsWith(segments, pattern))) return "non-model-facing";
  return "unclassified";
}

function jsonPointer(segments) {
  return `/${segments.map((segment) => String(segment).replaceAll("~", "~0").replaceAll("/", "~1")).join("/")}`;
}

function reachableStringPointers(value, segments = [], pointers = []) {
  if (typeof value === "string") {
    pointers.push(segments);
    return pointers;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => reachableStringPointers(item, [...segments, String(index)], pointers));
    return pointers;
  }
  if (value && typeof value === "object")
    for (const [key, child] of Object.entries(value)) reachableStringPointers(child, [...segments, key], pointers);
  return pointers;
}

function validateStructuredAuthorityPolicy() {
  for (const path of structuredPolicyPaths) {
    const policy = structuredAuthority[path];
    assert(policy, `${path} has no structured authority policy`);
    const pointers = reachableStringPointers(readJson(path));
    assert(pointers.length > 0, `${path} has no reachable string pointers to classify`);
    for (const pattern of policy.authoritative)
      assert(
        pointers.some((segments) => pointerMatches(segments, pattern)),
        `${path} has a stale structured authority declaration ${jsonPointer(pattern)}`
      );
    for (const pattern of [...policy.authoritativeSubtrees, ...policy.nonModelFacingSubtrees])
      assert(
        pointers.some((segments) => pointerStartsWith(segments, pattern)),
        `${path} has a stale structured authority declaration ${jsonPointer(pattern)}`
      );
    for (const segments of pointers)
      assert(
        structuredFieldClassification(path, segments) !== "unclassified",
        `${path} has an unclassified structured authority pointer ${jsonPointer(segments)}`
      );
  }
}

function checkStructuredRetiredNames(path, value, retired, segments = []) {
  if (typeof value === "string") {
    const classification = structuredFieldClassification(path, segments);
    if (classification === "authoritative")
      for (const name of retiredNameViolations(value, retired, { structured: true }))
        throw new Error(`${path} authoritatively uses retired name ${name} in ${jsonPointer(segments)}`);
    if (classification === "non-model-facing")
      for (const name of retiredNameViolations(value, retired))
        throw new Error(
          `${path} has a non-model-facing authority marker for retired name ${name} in ${jsonPointer(segments)}`
        );
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => checkStructuredRetiredNames(path, item, retired, [...segments, String(index)]));
    return;
  }
  if (value && typeof value === "object")
    for (const [key, child] of Object.entries(value))
      checkStructuredRetiredNames(path, child, retired, [...segments, key]);
}

function checkRetiredNameControls() {
  const surface = readJson(paths.modelSurface);
  const retired = [...surface.retiredNames.bare, ...surface.retiredNames.historicalPrefixed];
  const controls = retired.flatMap((name) => [
    { name, label: `bare ${name}`, line: `Authoritative model-facing name: ${name}`, rejects: true },
    { name, label: `dotted ${name}`, line: `Authoritative model-facing name: plane.${name}`, rejects: true },
    {
      name,
      label: `historical ${name}`,
      line: `Historical negative-control prose: retired alias ${name}`,
      rejects: false,
    },
    { name, label: `internal ${name}`, line: `operationId: "plane.${name}@1"`, rejects: false },
    {
      name,
      label: `mixed internal and authoritative ${name}`,
      line: `operationId: "plane.${name}@1"; Authoritative model-facing name: ${name}`,
      rejects: true,
    },
    {
      name,
      label: `mixed historical and authoritative ${name}`,
      line: `Rejected historical alias ${name}; Authoritative model-facing name: ${name}`,
      rejects: true,
    },
    {
      name,
      label: `ordinary path and prose ${name}`,
      line: `Implementation note: see docs/agent-tooling/README.md; ordinary prose may ${name}.`,
      rejects: false,
    },
  ]);
  for (const control of controls)
    assert(retiredNameViolations(control.line, retired).has(control.name) === control.rejects, control.label);

  for (const name of retired) {
    const line = `Rejected ${name} authoritative model-facing name ${name}`;
    const occurrences = retiredNameOccurrences(line, retired).filter((occurrence) => occurrence.name === name);
    assert(occurrences.length === 2, `compact same-clause control must contain two ${name} occurrences`);
    const allOccurrences = retiredNameOccurrences(line, retired);
    const historical = classifyHistoricalOccurrences(line, allOccurrences);
    const nameHistorical = allOccurrences
      .map((occurrence, index) => ({ occurrence, historical: historical[index] }))
      .filter(({ occurrence }) => occurrence.name === name)
      .map(({ historical: isHistorical }) => isHistorical);
    assert(nameHistorical[0], `compact same-clause control did not allow the explicitly rejected ${name} occurrence`);
    assert(!nameHistorical[1], `compact same-clause control incorrectly allowed the authoritative ${name} occurrence`);
    assert(
      retiredNameViolations(line, retired).has(name),
      `compact same-clause control did not reject the later authoritative ${name} occurrence`
    );

    const ambiguousLine = `${name} rejected ${name} authoritative model-facing name`;
    const ambiguousOccurrences = retiredNameOccurrences(ambiguousLine, retired).filter(
      (occurrence) => occurrence.name === name
    );
    assert(ambiguousOccurrences.length === 2, `ambiguous same-clause control must contain two ${name} occurrences`);
    assert(
      classifyHistoricalOccurrences(ambiguousLine, retiredNameOccurrences(ambiguousLine, retired)).every(
        (matched) => !matched
      ),
      `ambiguous same-clause control consumed a marker for ${name}`
    );
  }
}

function checkStructuredModelFacingFields() {
  const surface = readJson(paths.modelSurface);
  const expected = surface.names.map((entry) => entry.name);
  assert(new Set(expected).size === expected.length, "model-facing names must be unique");
  assert(
    expected.every((name) => !surface.retiredNames.bare.includes(name)),
    "model-facing names contain a retired bare alias"
  );
  assert(
    expected.every((name) => !surface.retiredNames.historicalPrefixed.includes(name)),
    "model-facing names contain a retired historical alias"
  );
  const predicates = readJson(paths.predicates);
  const required = predicates.common.find((predicate) => predicate.id === "PLAN-COMMON-007")?.expected?.required;
  assert(
    JSON.stringify(required) === JSON.stringify(expected),
    "structured required tool field differs from exact model-facing set"
  );
}

function checkRetiredNames() {
  const surface = readJson(paths.modelSurface);
  const retired = [...surface.retiredNames.bare, ...surface.retiredNames.historicalPrefixed];
  checkPolicyCoverage(lock);
  validateStructuredAuthorityPolicy();

  for (const path of retiredNameSourcePolicy.structuredPaths)
    checkStructuredRetiredNames(path, readJson(path), retired);

  for (const path of retiredNameSourcePolicy.markdownPaths) {
    const source = read(path);
    const sectionPolicy = markdownSectionPolicyFor(path, source);
    let offset = 0;
    let sectionIndex = -1;
    for (const line of source.split("\n")) {
      while (
        sectionIndex + 1 < sectionPolicy.headings.length &&
        sectionPolicy.headings[sectionIndex + 1].start <= offset
      )
        sectionIndex += 1;
      const section = sectionIndex === -1 ? "preamble" : sectionPolicy.headings[sectionIndex].heading;
      const classification =
        sectionIndex === -1 ? sectionPolicy.preamble : sectionPolicy.headings[sectionIndex].classification;
      const violations = retiredNameViolations(line, retired, {
        authoritative: classification === "authoritative/model-facing",
      });
      for (const name of violations)
        if (classification === "authoritative/model-facing")
          throw new Error(`${path} authoritatively uses retired name ${name}`);
        else throw new Error(`${path} has a non-model-facing authority marker for retired name ${name} in ${section}`);
      offset += line.length + 1;
    }
  }
  const required =
    readJson(paths.predicates).common.find((predicate) => predicate.id === "PLAN-COMMON-007")?.expected?.required ?? [];
  assert(
    JSON.stringify(required) === JSON.stringify(surface.names.map((entry) => entry.name)),
    "planning predicate surface differs from machine-readable exact surface"
  );
  assert(
    read(paths.prompt).includes("search_workspace") && read(paths.prompt).includes("compose_typescript"),
    "planning prompt does not use approved names"
  );
  checkStructuredModelFacingFields();
}

function checkGeneratedArtifacts(lock) {
  for (const [command, label] of [
    [["docs/agent-tooling/verifiers/render-non-ui-implementation-plan.mjs", "--check"], "generated overview"],
    [["docs/agent-tooling/verifiers/render-requirement-coverage.mjs", "--check"], "generated requirement coverage"],
    [["docs/agent-tooling/verifiers/validate-requirement-coverage.mjs"], "requirement coverage"],
    [["docs/agent-tooling/verifiers/validate-planning-fixtures.mjs"], "planning fixtures"],
  ]) {
    const result = runCommand("node", command);
    assert(result.status === 0, `${label} check failed: ${(result.stdout + result.stderr).trim()}`);
  }
  const fixturePaths = [
    paths.fixture,
    paths.fixtureSchema,
    paths.predicates,
    paths.predicateSchema,
    paths.prompt,
    paths.planningValidator,
  ];
  const fixtureBundle = sha256(
    fixturePaths
      .map((path) => `${path}\0${fileDigest(path)}\n`)
      .toSorted()
      .join("")
  );
  assert(lock.digests.files[paths.fixture] === fileDigest(paths.fixture), "fixture digest is not sealed");
  assert(fixtureBundle.length === 64, "fixture bundle digest could not be computed");
}

function checkG0Record() {
  const readiness = readJson(paths.readiness);
  if (mode === "preflight")
    assert(
      readiness.status === "pending-human-approval" && readiness.approval.status === "pending",
      "preflight accepts only a fully ready pending package"
    );
  assert(
    readiness.status === "pending-human-approval" || readiness.status === "approved",
    "G0 readiness status is invalid"
  );
  const expectedClauseStatuses = new Map(
    readiness.status === "pending-human-approval"
      ? [
          ["G0-ADR-STATUS", "ready"],
          ["G0-MANIFEST-STATUS", "ready-pending-approval"],
          ["G0-SEMANTIC-BOUNDARY", "ready"],
          ["G0-RUNTIME-CONTRACT", "ready"],
          ["G0-LIMITS-AUDIT", "ready"],
          ["G0-OWNERSHIP-LOCK", "ready"],
          ["G0-LEGACY-RECONCILIATION", "ready"],
          ["G0-GENERATED-ARTIFACTS", "ready"],
          ["G0-HUMAN-APPROVAL", "pending"],
        ]
      : [
          ["G0-ADR-STATUS", "ready"],
          ["G0-MANIFEST-STATUS", "ready"],
          ["G0-SEMANTIC-BOUNDARY", "ready"],
          ["G0-RUNTIME-CONTRACT", "ready"],
          ["G0-LIMITS-AUDIT", "ready"],
          ["G0-OWNERSHIP-LOCK", "ready"],
          ["G0-LEGACY-RECONCILIATION", "ready"],
          ["G0-GENERATED-ARTIFACTS", "ready"],
          ["G0-HUMAN-APPROVAL", "ready"],
        ]
  );
  assert(
    JSON.stringify(readiness.clauses.map((clause) => clause.id)) === JSON.stringify([...expectedClauseStatuses.keys()]),
    "G0 readiness clause IDs are not the exact ordered set"
  );
  for (const clause of readiness.clauses)
    assert(
      clause.status === expectedClauseStatuses.get(clause.id),
      `${clause.id} has status ${clause.status}; expected ${expectedClauseStatuses.get(clause.id)} for ${readiness.status}`
    );
}

const lock = readJson(paths.lock);
const readiness = readJson(paths.readiness);
check("local Markdown links, anchors, and portable paths", checkMarkdownLinks);
check("accepted ADR 0001 through 0010 and register consistency", checkAdrRegister);
check("single approval authority and G0/G1/G4 policy", checkAuthorityAndContractPolicy);
check("accepted ADR generated-schema authority", checkAcceptedAdrSchemaAuthority);
check("manifest and byte-for-byte evidence bindings", () => checkManifestAndDigests(lock, readiness));
check("source, repository pins, and reviewed-baseline separation", () => checkSourceAndRepositoryPins(lock));
check("AJV 2020 schemas, ownership join, and pending slots", () => checkOwnershipAndSchemas(lock, readiness));
check("exact model-facing surface", checkModelFacingSurface);
check("retired-name negative control", checkRetiredNames);
check("retired-name table controls", checkRetiredNameControls);
check("content/evidence seal and append-only WORKLOG prefix", () => checkSeal(lock, readiness));
check("generated overview, coverage, and planning fixtures", () => checkGeneratedArtifacts(lock));
check("G0 record completeness", checkG0Record);
check(
  "human approval",
  () => {
    if (mode === "preflight") return;
    assert(
      readiness.status === "approved" && readiness.approval.status === "approved",
      "approval pending: record the exact manifest statement before implementation"
    );
    assert(
      readiness.approval.approvedBy.identity && readiness.approval.approvedBy.reference,
      "approved state lacks approver identity/reference"
    );
    assert(
      readiness.approval.approvedAt && readiness.approval.evidenceBinding.contentCommit,
      "approved state lacks timestamp/evidence binding"
    );
    assert(
      readiness.approval.evidenceBinding.contentCommit === lock.seal.contentCommit,
      "approved state content binding differs from lock"
    );
    assert(
      readiness.approval.evidenceBinding.lockDigest === fileDigest(paths.lock),
      "approved state lock binding differs from sealed lock"
    );
  },
  { approvalOnly: mode === "g0" }
);

for (const result of results)
  console.log(
    `${result.status === "pass" ? "PASS" : result.status === "pending" ? "PENDING" : "FAIL"} ${result.name}${result.message ? ` — ${result.message}` : ""}`
  );

if (mode === "preflight") {
  if (failures.length > 0) {
    console.error(`G0 preflight failed with ${failures.length} non-approval failure(s).`);
    process.exit(1);
  }
  console.log("G0 preflight passed; human approval remains pending by design.");
  process.exit(0);
}

if (failures.length > 0) {
  console.error(`G0 verification failed with ${failures.length} non-approval failure(s).`);
  process.exit(1);
}
if (readiness.status !== "approved") {
  console.error(
    "G0 verification failed specifically because human approval is pending; no implementation authorization is implied."
  );
  process.exit(1);
}
console.log(
  "G0 verification passed for a valid approved state; this verifier does not itself grant implementation authorization."
);

# Chat Semantic Context Picker

Non-UI foundation for attaching visible Plane content to an agent message without
copying labels or guessing object identity.

## Scope

The package provides:

- typed references for work items, fields, projects, cycles, modules, pages, views,
  and live editor blocks or ranges;
- point and region selection through a Plane-owned React Grab adapter;
- fresh client-store or live-editor observations;
- Django hydration that rechecks workspace, project, guest, and private-object
  access before returning curated canonical values;
- a composer adapter that removes denied observations before handoff; and
- an in-memory visual fallback with sensitive-surface denial and explicit review.

The composer activation control, crosshair, hover treatment, preview, chips, and
send workflow are intentionally left to the separate UI integration.

## Integration

Import semantic APIs from `@plane/chat-context`. Import the optional screenshot
renderer from `@plane/chat-context/html2canvas-pro` so semantic-only consumers do
not bundle it.

The host must:

1. register mounted Plane elements with stable semantic references;
2. provide access to current Plane stores and mounted Tiptap editors;
3. implement the authenticated hydration transport and composer consumer ports;
4. show the exact semantic or visual context before sending; and
5. mark custom credential or private surfaces with
   `data-plane-context-sensitive`.

## Documentation

- [Product specification](./product-spec.md)
- [Technical design and contracts](./technical-design.md)
- [Architecture decision](./decisions/0001-semantic-context-picker.md)

## Verification

Run `pnpm verify:chat-context` from the repository root. The command checks types,
lint, formatting, browser behavior, production bundles, API permissions, and page
scope. Pull requests to `preview` run the same command through
`.github/workflows/chat-semantic-context.yml` whenever the feature or its contracts
change.

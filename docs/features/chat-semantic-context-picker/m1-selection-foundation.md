# M1 Evidence: Selection Foundation

## Decision outcome

| Item                  | Result                                                                                   |
| --------------------- | ---------------------------------------------------------------------------------------- |
| Dependency            | `react-grab@0.1.50`, exact workspace catalog pin                                         |
| License               | MIT                                                                                      |
| Public subpath        | `react-grab/primitives`                                                                  |
| Plane imports         | `getElementsAtPoint`, `isElementGrabbable`                                               |
| Excluded runtime APIs | Source context, clipboard, editor opening, Three.js, freeze/unfreeze, full renderer, CLI |
| Plane wrapper build   | 1.45 kB ESM before consumer bundling                                                     |
| Consumer bundle       | 13,217 gzip bytes; 30,000-byte enforced ceiling                                          |
| Browser verifier      | Three tests passed in installed stable Google Chrome                                     |

## Sources

| Source                                                                                                 | Evidence used                                                                        |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| [React Grab package documentation](https://www.npmjs.com/package/react-grab/v/0.1.50?activeTab=readme) | Official primitive subpath, hit-testing API, filter, container, and ignore attribute |
| [React Grab package metadata](https://www.npmjs.com/package/react-grab/v/0.1.50)                       | Exact release, MIT license, exports, dependencies, integrity, and provenance         |
| [Vitest Browser Mode](https://vitest.dev/guide/browser/)                                               | Real-browser provider and Chromium instance configuration                            |
| [Playwright browser documentation](https://playwright.dev/docs/browsers)                               | Installed Chrome channel and browser execution model                                 |

## Verified behaviors

| Behavior               | Acceptance proof                                               | Prevention proof                                                            |
| ---------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Nested target          | Topmost nested field is the first candidate                    | Plane and React Grab ignored overlays are absent from candidates            |
| Portal and shadow DOM  | Body-level portal and open-shadow target are discovered        | Invalid coordinates return an empty result                                  |
| Navigation and unmount | Replacement target is discovered after route change            | Detached target never reappears and pointer state stays unchanged           |
| Production bundle      | Consumer bundle includes the primitives needed for hit-testing | CLI, renderer, source-copy, editor-opening, and Three.js markers are absent |

## Boundary correction

React Grab is used as a stateless acquisition Implementation, not as Plane's picker
lifecycle. Plane does not call `freeze()` and does not install React Grab listeners.
Escape, confirmation, cancellation, navigation ownership, and `dispose()` therefore
belong to the private M2 session Implementation and its contract tests.

This boundary is smaller than ADR 0001 initially allowed. It avoids global React
update interception and makes unmount cleanup a Plane concern. The published
package still installs `@react-grab/cli` transitively, but production bundling proves
that the CLI is absent from the runtime output. The bundle verifier guards upgrades.

## Commands

```bash
pnpm --filter @plane/chat-context test
pnpm --filter @plane/chat-context check:types
pnpm --filter @plane/chat-context check:lint
pnpm --filter @plane/chat-context check:format
pnpm --filter @plane/chat-context build
pnpm --filter @plane/chat-context verify:bundle
```

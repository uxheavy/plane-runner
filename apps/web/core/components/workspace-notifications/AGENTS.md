# Inbox Focus Mode

## Scope

This file governs `apps/web/core/components/workspace-notifications/`.

## Local Responsibility

This folder owns Plane's workspace-wide Inbox UI. Treat Inbox as a focus mode that brings attention-requiring contexts to the user; it is not a project browser or a replacement workspace.

The model is additive:

- Preserve existing work-item notification and embedded-work-item behavior.
- Add new typed attention contexts without converting them into work items.
- An embedded context is a usable focused working surface, not merely a summary card.

## Canonical Owners

| Concern                             | Canonical location                                             |
| ----------------------------------- | -------------------------------------------------------------- |
| Inbox route and list/detail layout  | `apps/web/app/(all)/[workspaceSlug]/(projects)/notifications/` |
| Inbox UI and notification cards     | `apps/web/core/components/workspace-notifications/`            |
| Workspace notification state        | `apps/web/core/store/notifications/`                           |
| Notification client API             | `apps/web/core/services/workspace-notification.service.ts`     |
| Existing embedded work-item surface | `apps/web/core/components/issues/peek-overview/`               |
| Work-item comments and activity     | `apps/web/core/components/issues/issue-detail/issue-activity/` |
| Notification API behavior           | `apps/api/plane/app/views/notification/base.py`                |

## Architecture Rules

- Keep Inbox workspace-scoped and cross-project. Selecting an attention item must not require navigating the project hierarchy.
- Preserve the dedicated focus-mode shell: workspace top navigation remains available while the Projects sidebar stays out of the Inbox layout.
- Selecting an item opens its typed working surface in the Inbox detail region. Do not automatically navigate the main route to the underlying artifact, channel, or thread.
- Retain an explicit action for opening the canonical Plane artifact route or opening a conversation alongside structured work.
- Preserve the existing work-item embed path through `IssuePeekOverview` with `embedIssue`. Do not replace it with a reduced notification-specific work-item renderer.
- Keep existing work-item comments and activity behavior unchanged. Do not copy or migrate them into channel or thread messages.
- Conversation attention items must embed the relevant channel or thread as a usable surface: users can read context, reply, react, attach context, and manage the focused thread. Channel administration and broad channel navigation remain outside Inbox.
- Inbox conversation selection is independent from the conversation sidecar used alongside normal Plane work. Inspecting a conversation in Inbox must not silently replace a separately pinned conversation.
- Preserve type identity. Work items, channels, threads, comments, and agent receipts may share attention semantics, but they remain distinct domain objects and must use distinct detail renderers.
- Extend existing read/unread, archive, snooze, filtering, and responsive conventions where they make sense. Do not silently invent identical lifecycle semantics for a new attention type; surface product ambiguity before encoding it.
- On narrow screens, selection replaces the Inbox list with the embedded context. Closing or going Back restores the prior Inbox tab, filters, scroll position, selection where appropriate, and conversation draft.

## Working Method

| Situation                             | Required method                                                                                                                                                                                          |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Changing work-item attention behavior | Trace notification selection through `sidebar/notification-card/item.tsx` → `root.tsx` → `IssuePeekOverview`; preserve the existing work-item capability unless the product decision explicitly changes. |
| Adding a new attention type           | Add a typed dispatch from notification/context identity to its dedicated detail renderer. Do not add issue-shaped conditionals to the work-item renderer.                                                |
| Adding conversation detail            | Reuse the canonical channel/thread model and composer behavior. Keep Inbox-specific code responsible only for focus-mode selection, containment, and recovery.                                           |
| Changing responsive behavior          | Verify desktop list/detail and narrow-screen list → detail → Back as one stateful flow.                                                                                                                  |
| Changing notification lifecycle       | Check the UI store, client service, and API behavior together; distinguish current source behavior from proposed behavior.                                                                               |

## Current Gotchas

| Gotcha                                                                                         | Why it matters                                                                                                  | Correct action                                                                                                                |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| The current notification list API filters `entity_name="issue"`.                               | The generic notification model does not mean Inbox already supports arbitrary Plane artifacts or conversations. | Treat non-work-item attention as an additive product and domain extension.                                                    |
| Current “All” behavior excludes mention notifications.                                         | The label can be mistaken for a literal union of all notification types.                                        | Verify tab semantics before extending or renaming them.                                                                       |
| Selected notification, tab, and filters are primarily in MobX memory rather than the URL.      | Current selection is not a durable deep-link or browser-history contract.                                       | Preserve current behavior unless navigation recovery is explicitly redesigned; do not claim URL recovery that does not exist. |
| `embedIssue` changes containment, dismissal, and layout controls—not the work-item body.       | Rebuilding a small preview would accidentally remove editing, properties, widgets, and comments.                | Reuse the embedded work-item surface and keep the explicit full-route action.                                                 |
| Conversation focus mode and the normal conversation sidecar serve different navigation states. | Coupling them can replace or lose a pinned conversation while the user is triaging.                             | Keep their active-context state independent and switch only through an explicit action.                                       |

## Local Verification

For Inbox UI changes, run the scripts defined in `apps/web/package.json`:

```bash
pnpm --filter=web check:types
pnpm --filter=web check:lint
```

Also verify manually:

- Desktop Inbox list → work-item detail without project-route navigation.
- Desktop Inbox list → conversation detail without changing a pinned sidecar conversation.
- Work-item inline editing, properties, widgets, and comments remain available according to permissions.
- Narrow-screen list → embedded context → Back restores the prior Inbox state and draft.
- The explicit full-artifact or open-alongside-work action reaches the intended canonical context.

No focused automated Inbox test was found when this guidance was added. The commands above are defined by `apps/web/package.json` but were not executed for this documentation-only change.

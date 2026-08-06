#!/usr/bin/env python3
"""Static proof that future Agent settings extend Plane's existing settings shell."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"settings reuse proof failed: {message}")


def main() -> None:
    required = (
        "apps/web/app/routes/core.ts",
        "apps/web/app/(all)/[workspaceSlug]/(settings)/layout.tsx",
        "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/layout.tsx",
        "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/page.tsx",
        "apps/web/core/components/workspace/settings",
        "apps/web/core/services/workspace.service.ts",
        "apps/web/core/store/workspace/index.ts",
        "packages/ui/src",
    )
    for relative in required:
        if not (ROOT / relative).exists():
            fail(f"missing existing Plane settings owner: {relative}")

    routes = (ROOT / "apps/web/app/routes/core.ts").read_text(encoding="utf-8")
    if '"./(all)/[workspaceSlug]/(settings)/layout.tsx"' not in routes:
        fail("workspace settings route is not owned by the existing settings layout")
    if "@/components/workspace/settings" not in (
        ROOT / "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/page.tsx"
    ).read_text(encoding="utf-8"):
        fail("workspace settings page does not reuse existing settings components")

    for path in (ROOT / "apps/web").rglob("*"):
        normalized = str(path.relative_to(ROOT)).casefold()
        if not path.is_file():
            continue
        if any(marker in normalized for marker in ("agent-settings", "agent_settings", "agentsettings")):
            fail(f"custom Agent settings framework detected: {path.relative_to(ROOT)}")
        if "settings" in normalized and ("chat" in normalized or "chat" in path.name.casefold()):
            fail(f"chat surface introduced into settings: {path.relative_to(ROOT)}")

    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=AMCR"],
            cwd=ROOT,
            text=True,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"could not inspect the task diff: {exc}")
    for relative in changed:
        normalized = relative.casefold()
        if normalized.startswith("apps/web/") and (
            "agent" in normalized or "chat" in normalized
        ):
            fail(f"Agent lane changed a custom UI/chat surface: {relative}")

    print("settings reuse proof passed: existing route/layout/components/services/stores/@plane/ui are the extension owners")


if __name__ == "__main__":
    main()

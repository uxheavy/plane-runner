#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Prove that the candidate keeps Agent work inside Plane's existing settings shell."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOTS = (
    "apps/web/",
    "apps/admin/",
    "apps/space/",
    "packages/ui/src/",
)
SETTINGS_OWNER_ROOTS = (
    "apps/web/app/(all)/[workspaceSlug]/(settings)/",
    "apps/web/core/components/workspace/settings/",
    "apps/web/core/services/workspace.service.ts",
    "apps/web/core/store/workspace/",
)
FORBIDDEN_UI_MARKERS = (
    "agent-chat",
    "agent_chat",
    "agentchat",
    "agent-composer",
    "agent_composer",
    "agent-thread",
    "agent_thread",
    "agent-inbox",
    "agent_inbox",
    "agent-sidecar",
    "agent_sidecar",
    "agent-transcript",
    "agent_transcript",
    "agent settings",
    "agent-settings",
    "agent_settings",
)


class SettingsReuseError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SettingsReuseError(f"git {' '.join(args)} failed: {exc}") from exc


def _exists_at(root: Path, commit: str, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}:{relative}"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _read_at(root: Path, commit: str, relative: str) -> str:
    return _git(root, "show", f"{commit}:{relative}")


def _ui_path(relative: str) -> bool:
    return relative.startswith(UI_ROOTS)


def _settings_owner_path(relative: str) -> bool:
    return relative.startswith(SETTINGS_OWNER_ROOTS)


def _changed_ui_paths(root: Path, base: str, candidate: str) -> list[tuple[str, str]]:
    rows = _git(root, "diff", "--name-status", "--find-renames", base, candidate, "--", *UI_ROOTS)
    changes: list[tuple[str, str]] = []
    for row in rows.splitlines():
        fields = row.split("\t")
        if len(fields) < 2:
            continue
        status = fields[0]
        relative = fields[-1]
        changes.append((status, relative))
    return changes


def check_committed_range(root: Path, base: str, candidate: str) -> None:
    if subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", base, candidate],
        check=False,
    ).returncode != 0:
        raise SettingsReuseError(f"base {base} is not an ancestor of candidate {candidate}")

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
        if not _exists_at(root, candidate, relative):
            raise SettingsReuseError(f"missing existing Plane settings owner at candidate: {relative}")

    routes = _read_at(root, candidate, "apps/web/app/routes/core.ts")
    if '"./(all)/[workspaceSlug]/(settings)/layout.tsx"' not in routes:
        raise SettingsReuseError("workspace settings route is not owned by the existing settings layout")
    page = _read_at(
        root,
        candidate,
        "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/page.tsx",
    )
    if "@/components/workspace/settings" not in page:
        raise SettingsReuseError("workspace settings page does not reuse existing settings components")

    candidate_ui_paths = _git(root, "ls-tree", "-r", "--name-only", candidate, "--", *UI_ROOTS).splitlines()
    for relative in candidate_ui_paths:
        normalized = relative.casefold()
        if any(marker in normalized for marker in ("agent-settings", "agent_settings", "agentsettings")):
            raise SettingsReuseError(f"custom Agent settings framework detected: {relative}")

    changes = _changed_ui_paths(root, base, candidate)
    for status, relative in changes:
        if status.startswith("A") or status.startswith("D") or not _settings_owner_path(relative):
            raise SettingsReuseError(
                f"UI change is outside the existing settings owners: status={status} path={relative}"
            )
        if not _exists_at(root, base, relative) or not _exists_at(root, candidate, relative):
            raise SettingsReuseError(f"settings reuse change must modify an existing file: {relative}")
        diff = _git(root, "diff", "--unified=0", "--no-color", base, candidate, "--", relative)
        added_lines = [line[1:].casefold() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
        for line in added_lines:
            if any(marker in line for marker in FORBIDDEN_UI_MARKERS):
                raise SettingsReuseError(f"Agent/chat UI marker added to settings owner {relative}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: check-agent-settings-reuse.py BASE_COMMIT CANDIDATE_COMMIT", file=sys.stderr)
        return 2
    base, candidate = args
    try:
        check_committed_range(ROOT, base, candidate)
    except SettingsReuseError as exc:
        print(f"settings reuse proof failed: {exc}", file=sys.stderr)
        return 1
    print(f"settings reuse proof passed: committed_range={base}..{candidate} existing_settings_owners=reused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

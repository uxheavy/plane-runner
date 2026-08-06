from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "check-agent-settings-reuse.py"
SPEC = importlib.util.spec_from_file_location("check_agent_settings_reuse", MODULE_PATH)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _fixture(tmp_path: Path, *, unrelated_ui: bool = False) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Settings proof test")
    files = {
        "apps/web/app/routes/core.ts": '"./(all)/[workspaceSlug]/(settings)/layout.tsx"',
        "apps/web/app/(all)/[workspaceSlug]/(settings)/layout.tsx": "export default function Layout() {}",
        "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/layout.tsx": "export default function Layout() {}",
        "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/page.tsx": "import Settings from \"@/components/workspace/settings\";",
        "apps/web/core/components/workspace/settings/index.tsx": "export default function Settings() {}",
        "apps/web/core/services/workspace.service.ts": "export const workspaceService = {};",
        "apps/web/core/store/workspace/index.ts": "export const workspaceStore = {};",
        "packages/ui/src/index.ts": "export {};",
    }
    if unrelated_ui:
        files["apps/web/core/components/other/Panel.tsx"] = "export default function Panel() {}"
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)
    return root, _git(root, "rev-parse", "HEAD")


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", message], check=True)
    return _git(root, "rev-parse", "HEAD")


def test_clean_candidate_range_is_checked(tmp_path):
    root, base = _fixture(tmp_path)
    candidate = _git(root, "rev-parse", "HEAD")
    checker.check_committed_range(root, base, candidate)


def test_existing_settings_owner_modification_is_accepted(tmp_path):
    root, base = _fixture(tmp_path)
    page = root / "apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/page.tsx"
    page.write_text(page.read_text(encoding="utf-8") + "\nexport const extension = true;\n", encoding="utf-8")
    candidate = _commit(root, "reuse settings owner")
    checker.check_committed_range(root, base, candidate)


def test_existing_unrelated_ui_modification_is_rejected(tmp_path):
    root, base = _fixture(tmp_path, unrelated_ui=True)
    panel = root / "apps/web/core/components/other/Panel.tsx"
    panel.write_text(panel.read_text(encoding="utf-8") + "\nexport const changed = true;\n", encoding="utf-8")
    candidate = _commit(root, "change unrelated UI")
    with pytest.raises(checker.SettingsReuseError, match="outside the existing settings owners"):
        checker.check_committed_range(root, base, candidate)


def test_differently_named_new_ui_surface_is_rejected(tmp_path):
    root, base = _fixture(tmp_path)
    panel = root / "apps/web/core/components/workspace/inspector/Panel.tsx"
    panel.parent.mkdir(parents=True)
    panel.write_text("export default function Panel() {}\n", encoding="utf-8")
    candidate = _commit(root, "add a new UI surface")
    with pytest.raises(checker.SettingsReuseError, match="outside the existing settings owners"):
        checker.check_committed_range(root, base, candidate)

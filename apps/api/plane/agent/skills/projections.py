"""Lossless deterministic skill-package projections."""

from __future__ import annotations

from collections.abc import Mapping

from plane.agent.lifecycle.runtime_contract import canonical_json, content_digest
from plane.db.models import AgentSkillRevision


def normalize_skill_files(package_files: Mapping[str, str]) -> dict[str, str]:
    """Validate and sort a Hermes-compatible package without rewriting files."""

    if not isinstance(package_files, Mapping) or "SKILL.md" not in package_files:
        raise ValueError("skill package must contain SKILL.md")
    normalized: dict[str, str] = {}
    for raw_name, content in package_files.items():
        if not isinstance(raw_name, str) or not raw_name or raw_name.startswith("/") or ".." in raw_name.split("/"):
            raise ValueError("skill package paths must be relative and traversal-free")
        if not isinstance(content, str):
            raise ValueError("skill package files must contain text")
        normalized[raw_name] = content
    return {name: normalized[name] for name in sorted(normalized)}


def skill_package_digest(package_files: Mapping[str, str]) -> str:
    return content_digest(normalize_skill_files(package_files))


def project_skill_package(revision: AgentSkillRevision) -> dict[str, str]:
    """Return the exact sorted file map a runtime adapter may materialize."""

    files = normalize_skill_files(revision.package_files)
    if skill_package_digest(files) != revision.package_digest:
        raise ValueError("skill package digest mismatch")
    return files


def parse_skill_package(package_files: Mapping[str, str]) -> dict[str, str]:
    """Round-trip parser for a projected package; content is intentionally untouched."""

    files = normalize_skill_files(package_files)
    if skill_package_digest(files) != content_digest(files):
        raise ValueError("skill package is not canonical")
    canonical_json(files)
    return files

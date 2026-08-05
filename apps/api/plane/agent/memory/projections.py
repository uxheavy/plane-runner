"""Deterministic, lossless Markdown projections for Plane Agent memory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from plane.agent.lifecycle.runtime_contract import canonical_json, content_digest
from plane.db.models import AgentMemoryEntry, AgentMemoryRevision, AgentMemoryVisibility


_ENTRY_MARKER = re.compile(r"^<!-- plane-memory-entry:v1 (?P<meta>\{.*\}) -->\n?$", re.MULTILINE)


@dataclass(frozen=True)
class ProjectedMemory:
    """One memory item reconstructed from a runtime projection."""

    entry_ref: str
    key: str
    revision: int
    visibility: str
    subject_user_ref: str | None
    content: str
    content_digest: str


def _memory_metadata(entry: AgentMemoryEntry, revision: AgentMemoryRevision) -> dict[str, object]:
    content = revision.content
    return {
        "entryRef": f"memory-entry:{entry.id}",
        "key": entry.key,
        "revision": revision.revision,
        "visibility": entry.visibility,
        "subjectUserRef": f"user:{entry.subject_user_id}" if entry.subject_user_id else None,
        "contentChars": len(content),
        "separatorAdded": not content.endswith("\n"),
        "contentDigest": revision.content_digest,
    }


def _project(entries: Iterable[tuple[AgentMemoryEntry, AgentMemoryRevision]], filename: str) -> str:
    projection = f"# {filename}\n\n<!-- plane-agent-memory:v1 -->\n\n"
    for entry, revision in sorted(entries, key=lambda pair: pair[0].key):
        content = revision.content
        metadata = canonical_json(_memory_metadata(entry, revision))
        projection += f"## {entry.key}\n<!-- plane-memory-entry:v1 {metadata} -->\n{content}"
        if not content.endswith("\n"):
            projection += "\n"
        projection += "<!-- plane-memory-entry-end -->\n\n"
    return projection


def project_memory_markdown(entries: Iterable[tuple[AgentMemoryEntry, AgentMemoryRevision]]) -> str:
    """Project only Agent-private entries into a deterministic ``MEMORY.md``."""

    entries = list(entries)
    if any(entry.visibility != AgentMemoryVisibility.AGENT_PRIVATE for entry, _ in entries):
        raise ValueError("MEMORY.md may contain only Agent-private entries")
    return _project(entries, "MEMORY.md")


def project_user_markdown(entries: Iterable[tuple[AgentMemoryEntry, AgentMemoryRevision]]) -> str:
    """Project one authorized subject user's preferences into ``USER.md``."""

    entries = list(entries)
    if any(
        entry.visibility != AgentMemoryVisibility.SUBJECT_USER or entry.subject_user_id is None for entry, _ in entries
    ):
        raise ValueError("USER.md may contain only subject-user entries")
    subject_ids = {entry.subject_user_id for entry, _ in entries}
    if len(subject_ids) > 1:
        raise ValueError("USER.md may contain one subject user")
    return _project(entries, "USER.md")


def parse_memory_markdown(markdown: str) -> tuple[ProjectedMemory, ...]:
    """Parse the exact Plane projection format without normalizing content."""

    if not isinstance(markdown, str) or "<!-- plane-agent-memory:v1 -->" not in markdown:
        raise ValueError("unsupported Plane memory projection")
    parsed: list[ProjectedMemory] = []
    cursor = 0
    while True:
        marker_start = markdown.find("<!-- plane-memory-entry:v1 ", cursor)
        if marker_start < 0:
            break
        match = _ENTRY_MARKER.match(markdown, marker_start)
        if match is None:
            raise ValueError("invalid Plane memory entry marker")
        metadata = json.loads(match.group("meta"))
        body_start = match.end()
        if markdown[body_start : body_start + 1] == "\n":
            body_start += 1
        content_chars = metadata.get("contentChars")
        separator_added = metadata.get("separatorAdded")
        if not isinstance(content_chars, int) or content_chars < 0 or not isinstance(separator_added, bool):
            raise ValueError("invalid Plane memory entry metadata")
        content = markdown[body_start : body_start + content_chars]
        end_start = body_start + content_chars
        if separator_added:
            if markdown[end_start : end_start + 1] != "\n":
                raise ValueError("missing Plane memory entry separator")
            end_start += 1
        terminator = "<!-- plane-memory-entry-end -->"
        if markdown[end_start : end_start + len(terminator)] != terminator:
            raise ValueError("missing Plane memory entry terminator")
        if content_digest({"content": content}) != metadata.get("contentDigest"):
            raise ValueError("Plane memory content digest mismatch")
        parsed.append(
            ProjectedMemory(
                entry_ref=metadata["entryRef"],
                key=metadata["key"],
                revision=metadata["revision"],
                visibility=metadata["visibility"],
                subject_user_ref=metadata.get("subjectUserRef"),
                content=content,
                content_digest=metadata["contentDigest"],
            )
        )
        cursor = end_start + len(terminator)
    return tuple(parsed)

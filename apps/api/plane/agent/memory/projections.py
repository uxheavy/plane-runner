"""Deterministic, lossless Markdown projections for Plane Agent memory."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, Literal

from plane.agent.lifecycle.runtime_contract import canonical_json, content_digest
from plane.db.models import AgentMemoryEntry, AgentMemoryRevision, AgentMemoryVisibility


_PROJECTION_HEADER = re.compile(r"# (?P<filename>MEMORY|USER)\.md\n\n<!-- plane-agent-memory:v1 -->\n\n")
_ENTRY_HEADER = re.compile(r"## (?P<key>[^\r\n]+)\n<!-- plane-memory-entry:v1 (?P<meta>[^\r\n]+) -->\n")
_MEMORY_ENTRY_METADATA = frozenset(
    {
        "contentBytes",
        "contentChars",
        "contentDigest",
        "entryRef",
        "key",
        "revision",
        "separatorAdded",
        "subjectUserRef",
        "visibility",
    }
)
_MAX_CONTENT_BYTES = 65_536


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
        "contentBytes": len(content.encode("utf-8")),
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
    """Parse the canonical Plane projection format without normalizing content.

    Parsing is deliberately fail-closed: the header, every entry, every byte of
    content, and the final separator must be consumed in the exact order emitted
    by the projector.  Entry content is sliced by its declared Unicode character
    length, so marker-looking text inside content remains opaque and lossless.
    """

    if not isinstance(markdown, str):
        raise ValueError("unsupported Plane memory projection")
    header = _PROJECTION_HEADER.match(markdown, 0)
    if header is None:
        raise ValueError("unsupported Plane memory projection")
    filename = header.group("filename")
    parsed: list[ProjectedMemory] = []
    entry_refs: set[str] = set()
    keys: set[str] = set()
    subject_refs: set[str] = set()
    previous_key: str | None = None
    cursor = header.end()
    terminator = "<!-- plane-memory-entry-end -->"

    while cursor < len(markdown):
        match = _ENTRY_HEADER.match(markdown, cursor)
        if match is None:
            raise ValueError("unexpected or unmarked Plane memory projection content")
        key_from_header = match.group("key")
        metadata_raw = match.group("meta")
        try:
            metadata = json.loads(
                metadata_raw,
                object_pairs_hook=_reject_duplicate_metadata_keys,
                parse_constant=_reject_non_finite_json,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Plane memory entry metadata JSON") from exc
        if not isinstance(metadata, dict) or frozenset(metadata) != _MEMORY_ENTRY_METADATA:
            raise ValueError("Plane memory entry metadata fields are not canonical")
        try:
            if canonical_json(metadata) != metadata_raw:
                raise ValueError("Plane memory entry metadata is not canonical JSON")
        except Exception as exc:
            raise ValueError("Plane memory entry metadata is not canonical JSON") from exc
        _validate_entry_metadata(metadata, key_from_header=key_from_header, filename=filename)
        body_start = match.end()
        content_chars = metadata.get("contentChars")
        content_bytes = metadata.get("contentBytes")
        separator_added = metadata.get("separatorAdded")
        if (
            not isinstance(content_chars, int)
            or isinstance(content_chars, bool)
            or content_chars < 0
            or not isinstance(content_bytes, int)
            or isinstance(content_bytes, bool)
            or content_bytes < 0
            or content_bytes > _MAX_CONTENT_BYTES
            or not isinstance(separator_added, bool)
        ):
            raise ValueError("invalid Plane memory entry metadata")
        content = markdown[body_start : body_start + content_chars]
        if len(content) != content_chars or len(content.encode("utf-8")) != content_bytes:
            raise ValueError("Plane memory entry content length mismatch")
        end_start = body_start + content_chars
        if separator_added != (not content.endswith("\n")):
            raise ValueError("Plane memory entry separator metadata mismatch")
        if separator_added:
            if markdown[end_start : end_start + 1] != "\n":
                raise ValueError("missing Plane memory entry separator")
            end_start += 1
        if markdown[end_start : end_start + len(terminator)] != terminator:
            raise ValueError("missing Plane memory entry terminator")
        if content_digest({"content": content}) != metadata.get("contentDigest"):
            raise ValueError("Plane memory content digest mismatch")
        after_terminator = end_start + len(terminator)
        if markdown[after_terminator : after_terminator + 2] != "\n\n":
            raise ValueError("missing Plane memory entry separator")
        if key_from_header in keys or metadata["entryRef"] in entry_refs:
            raise ValueError("duplicate Plane memory entry")
        if previous_key is not None and key_from_header <= previous_key:
            raise ValueError("Plane memory entries must be ordered by key")
        subject_ref = metadata["subjectUserRef"]
        if subject_ref is not None:
            subject_refs.add(subject_ref)
        if filename == "USER" and len(subject_refs) > 1:
            raise ValueError("USER.md may contain one subject user")
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
        keys.add(key_from_header)
        entry_refs.add(metadata["entryRef"])
        previous_key = key_from_header
        cursor = after_terminator + 2
    return tuple(parsed)


def reproject_memory_markdown(entries: Iterable[ProjectedMemory], filename: Literal["MEMORY.md", "USER.md"]) -> str:
    """Serialize parsed runtime entries back to the exact canonical bytes."""

    if filename not in {"MEMORY.md", "USER.md"}:
        raise ValueError("unsupported Plane memory projection filename")
    parsed = tuple(entries)
    keys: set[str] = set()
    subject_refs: set[str] = set()
    result = f"# {filename}\n\n<!-- plane-agent-memory:v1 -->\n\n"
    previous_key: str | None = None
    for entry in parsed:
        if entry.key in keys or (previous_key is not None and entry.key <= previous_key):
            raise ValueError("Project parsed memory entries must be unique and ordered")
        if filename == "MEMORY.md" and entry.visibility != "agent_private":
            raise ValueError("MEMORY.md may contain only Agent-private entries")
        if filename == "USER.md" and entry.visibility != "subject_user":
            raise ValueError("USER.md may contain only subject-user entries")
        if entry.subject_user_ref is not None:
            subject_refs.add(entry.subject_user_ref)
        if filename == "USER.md" and len(subject_refs) > 1:
            raise ValueError("USER.md may contain one subject user")
        content = entry.content
        metadata = canonical_json(
            {
                "contentBytes": len(content.encode("utf-8")),
                "contentChars": len(content),
                "contentDigest": entry.content_digest,
                "entryRef": entry.entry_ref,
                "key": entry.key,
                "revision": entry.revision,
                "separatorAdded": not content.endswith("\n"),
                "subjectUserRef": entry.subject_user_ref,
                "visibility": entry.visibility,
            }
        )
        result += f"## {entry.key}\n<!-- plane-memory-entry:v1 {metadata} -->\n{content}"
        if not content.endswith("\n"):
            result += "\n"
        result += "<!-- plane-memory-entry-end -->\n\n"
        keys.add(entry.key)
        previous_key = entry.key
    return result


def _reject_duplicate_metadata_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key, value in pairs:
        if key in metadata:
            raise ValueError(f"duplicate metadata key: {key}")
        metadata[key] = value
    return metadata


def _reject_non_finite_json(value: str) -> object:
    raise ValueError(f"non-finite JSON value is not allowed: {value}")


def _validate_entry_metadata(metadata: dict[str, object], *, key_from_header: str, filename: str) -> None:
    key = metadata["key"]
    if (
        not isinstance(key, str)
        or not key.strip()
        or "\r" in key
        or "\n" in key
        or len(key.encode("utf-8")) > 255
        or key != key_from_header
    ):
        raise ValueError("invalid Plane memory entry key")
    entry_ref = metadata["entryRef"]
    if not isinstance(entry_ref, str) or len(entry_ref) > 64 or not entry_ref.startswith("memory-entry:"):
        raise ValueError("invalid Plane memory entry reference")
    try:
        if str(uuid.UUID(entry_ref.removeprefix("memory-entry:"))) != entry_ref.removeprefix("memory-entry:"):
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid Plane memory entry reference") from exc
    revision = metadata["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("invalid Plane memory revision")
    visibility = metadata["visibility"]
    subject_ref = metadata["subjectUserRef"]
    if not isinstance(visibility, str) or visibility not in {"agent_private", "subject_user"}:
        raise ValueError("invalid Plane memory visibility")
    if visibility == "agent_private" and subject_ref is not None:
        raise ValueError("Agent-private projection entry cannot bind a subject user")
    if visibility == "subject_user":
        if not isinstance(subject_ref, str) or not subject_ref.startswith("user:"):
            raise ValueError("subject-user projection entry requires a user reference")
        try:
            if str(uuid.UUID(subject_ref.removeprefix("user:"))) != subject_ref.removeprefix("user:"):
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise ValueError("invalid subject-user projection reference") from exc
    if filename == "MEMORY" and visibility != "agent_private":
        raise ValueError("MEMORY.md may contain only Agent-private entries")
    if filename == "USER" and visibility != "subject_user":
        raise ValueError("USER.md may contain only subject-user entries")
    digest = metadata["contentDigest"]
    if not isinstance(digest, str) or not re.fullmatch(r"content:[0-9a-f]{64}", digest):
        raise ValueError("invalid Plane memory content digest")

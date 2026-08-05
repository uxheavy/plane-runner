# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared bounded JSON validation for Plane-owned Agent boundaries."""

from __future__ import annotations

import math
import json
import re
from copy import deepcopy
from typing import Any

MAX_BOUNDED_TEXT_BYTES = 4_096
MAX_BOUNDED_BYTE_COUNT = 1_048_576


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


MAX_AGENT_JSON_DEPTH = 8
MAX_AGENT_COLLECTION_ITEMS = 64
MAX_AGENT_READBACK_BYTES = MAX_BOUNDED_BYTE_COUNT

_CREDENTIAL_KEY = re.compile(r"[^a-z0-9]+", re.IGNORECASE)
_EMBEDDED_CREDENTIAL_URL = re.compile(
    r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@|[?&#](?:api[\W_]*key|access[\W_]*token|refresh[\W_]*token|token|secret|password)\s*=\s*[^&#\s]+",
    re.IGNORECASE,
)
_INLINE_CREDENTIAL = re.compile(
    r"(?<![a-z0-9])(?:x[\s_-]*api[\s_-]*key|api[\s_-]*key|authorization|auth|bearer|basic|access[\s_-]*token|refresh[\s_-]*token|token|password|cookie|secret)(?![a-z0-9])(?:\s*[:=,/\\_-]\s*|\s+)[^\s]+",
    re.IGNORECASE,
)
_KNOWN_CREDENTIAL_PREFIX = re.compile(
    r"(?<![a-z0-9])(?:sk-(?:ant-)?[a-z0-9_-]{8,}|gh[pousr]_[a-z0-9_]{8,}|github_pat_[a-z0-9_]{8,}|xox[baprs]-[a-z0-9-]{8,}|akia[0-9a-z]{16}|AIza[0-9a-z_-]{16,}|eyJ[a-z0-9_-]{20,})(?![a-z0-9])",
    re.IGNORECASE,
)


class AgentValueError(ValueError):
    """Raised when an Agent JSON value cannot cross a trusted boundary."""


def contains_credential_value(value: str) -> bool:
    return bool(
        _EMBEDDED_CREDENTIAL_URL.search(value)
        or _INLINE_CREDENTIAL.search(value)
        or _KNOWN_CREDENTIAL_PREFIX.search(value)
    )


def is_credential_key(key: str) -> bool:
    normalized = _CREDENTIAL_KEY.sub("", key).lower()
    if normalized in {
        "apikey",
        "accesskey",
        "authorization",
        "authorizationheader",
        "auth",
        "authentication",
        "authheader",
        "bearer",
        "basic",
        "cookie",
        "credential",
        "credentialref",
        "password",
        "secret",
        "secretkey",
        "token",
        "tokenvalue",
        "header",
        "headers",
    }:
        return True
    if any(
        fragment in normalized
        for fragment in (
            "apikey",
            "accesskey",
            "authorization",
            "credential",
            "password",
            "secret",
            "cookie",
            "bearer",
            "basic",
        )
    ):
        return True
    if normalized.endswith(("token", "key")) and any(
        prefix in normalized for prefix in ("api", "auth", "access", "refresh", "client", "x")
    ):
        return True
    return False


def _validate_json_tree(
    value: Any,
    *,
    field_name: str,
    max_items: int,
    max_depth: int,
    max_string_bytes: int,
    reject_credentials: bool,
    allowed_keys: set[str] | None,
    path: str,
    depth: int,
) -> None:
    if depth > max_depth:
        raise AgentValueError(f"{field_name} exceeds the maximum JSON nesting depth")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_string_bytes:
            raise AgentValueError(f"{path} exceeds {max_string_bytes} UTF-8 bytes")
        if reject_credentials and contains_credential_value(value):
            raise AgentValueError(f"{path} contains credential-shaped data")
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AgentValueError(f"{path} must contain finite JSON numbers")
        return
    if isinstance(value, list):
        if len(value) > max_items:
            raise AgentValueError(f"{path} contains more than {max_items} items")
        for index, item in enumerate(value):
            _validate_json_tree(
                item,
                field_name=field_name,
                max_items=max_items,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                reject_credentials=reject_credentials,
                allowed_keys=None,
                path=f"{path}[{index}]",
                depth=depth + 1,
            )
        return
    if isinstance(value, dict):
        if len(value) > max_items:
            raise AgentValueError(f"{path} contains more than {max_items} properties")
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentValueError(f"{path} contains a non-string JSON key")
            if allowed_keys is not None and key not in allowed_keys:
                raise AgentValueError(f"{path}.{key} is not an accepted behavioral field")
            if len(key.encode("utf-8")) > max_string_bytes:
                raise AgentValueError(f"{path}.{key} exceeds the key byte limit")
            if reject_credentials and is_credential_key(key):
                raise AgentValueError(f"{path}.{key} is credential-shaped")
            _validate_json_tree(
                item,
                field_name=field_name,
                max_items=max_items,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                reject_credentials=reject_credentials,
                allowed_keys=None,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return
    raise AgentValueError(f"{path} is not a supported JSON value")


def validate_bounded_json(
    value: Any,
    field_name: str,
    *,
    max_bytes: int = MAX_BOUNDED_BYTE_COUNT,
    max_items: int = MAX_AGENT_COLLECTION_ITEMS,
    max_depth: int = MAX_AGENT_JSON_DEPTH,
    max_string_bytes: int = MAX_BOUNDED_TEXT_BYTES,
    reject_credentials: bool = False,
    allowed_keys: set[str] | None = None,
) -> Any:
    """Validate JSON shape, limits, and optional credential separation."""

    _validate_json_tree(
        value,
        field_name=field_name,
        max_items=max_items,
        max_depth=max_depth,
        max_string_bytes=max_string_bytes,
        reject_credentials=reject_credentials,
        allowed_keys=allowed_keys,
        path=field_name,
        depth=0,
    )
    try:
        encoded = canonical_json(value).encode("utf-8")
    except Exception as exc:
        raise AgentValueError(f"{field_name} must contain canonical JSON") from exc
    if len(encoded) > max_bytes:
        raise AgentValueError(f"{field_name} exceeds {max_bytes} canonical JSON bytes")
    return deepcopy(value)


def validate_bounded_list(
    value: Any,
    field_name: str,
    *,
    min_items: int = 0,
    max_items: int = MAX_AGENT_COLLECTION_ITEMS,
    max_bytes: int = MAX_BOUNDED_BYTE_COUNT,
    max_string_bytes: int = MAX_BOUNDED_TEXT_BYTES,
    reject_credentials: bool = False,
) -> list[Any]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise AgentValueError(f"{field_name} must be a list")
    if len(value) < min_items:
        raise AgentValueError(f"{field_name} must contain at least {min_items} items")
    return validate_bounded_json(
        value,
        field_name,
        max_bytes=max_bytes,
        max_items=max_items,
        max_string_bytes=max_string_bytes,
        reject_credentials=reject_credentials,
    )


def validate_bounded_string_list(
    value: Any,
    field_name: str,
    *,
    min_items: int = 0,
    max_items: int = MAX_AGENT_COLLECTION_ITEMS,
    max_bytes: int = MAX_BOUNDED_BYTE_COUNT,
    max_string_bytes: int = MAX_BOUNDED_TEXT_BYTES,
) -> list[str]:
    result = validate_bounded_list(
        value,
        field_name,
        min_items=min_items,
        max_items=max_items,
        max_bytes=max_bytes,
        max_string_bytes=max_string_bytes,
    )
    for index, item in enumerate(result):
        if not isinstance(item, str) or not item.strip():
            raise AgentValueError(f"{field_name}[{index}] must be a non-empty string")
    return result


PROFILE_MODEL_KEYS = {
    "provider",
    "model",
    "temperature",
    "top_p",
    "max_tokens",
    "max_output_tokens",
    "reasoning_effort",
    "frequency_penalty",
    "presence_penalty",
    "stop",
    "seed",
}
PROFILE_RUNTIME_KEYS = {
    "provider",
    "model",
    "adapter",
    "totalBudget",
    "total_budget",
    "maxEventPayloadBytes",
    "max_event_payload_bytes",
    "maxArtifactBytes",
    "max_artifact_bytes",
    "maxReceiptBytes",
    "max_receipt_bytes",
}
PROFILE_TOOL_KEYS = {
    "eager",
    "eager_operations",
    "eagerOperations",
    "catalogDigest",
    "catalog_digest",
}


def validate_profile_dictionary(value: Any, field_name: str, *, allowed_keys: set[str]) -> dict[str, Any]:
    """Validate a typed behavioral defaults dictionary, never credentials."""

    result = validate_bounded_json(
        value or {},
        field_name,
        max_items=MAX_AGENT_COLLECTION_ITEMS,
        reject_credentials=True,
        allowed_keys=allowed_keys,
    )
    if not isinstance(result, dict):
        raise AgentValueError(f"{field_name} must be an object")
    return result

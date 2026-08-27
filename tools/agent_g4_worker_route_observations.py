# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure runtime observations used by the typed Worker route checks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def has_code_mode_callback(observations: Iterable[Any], operation_id: str) -> bool:
    """Recognize the bounded outer Plane:execute observation for the typed route."""

    if operation_id != "work_item.rename":
        return False
    marker = "Plane host model code plane.code-mode.execute@1 -> ok"
    for raw_payload in observations:
        if not isinstance(raw_payload, dict):
            continue
        body = raw_payload.get("body")
        payload = body.get("payload") if isinstance(body, dict) else None
        text = payload.get("text") if isinstance(payload, dict) else None
        if text == marker:
            return True
    return False

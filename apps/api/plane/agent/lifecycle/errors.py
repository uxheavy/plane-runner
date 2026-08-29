# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

from django.core.exceptions import ValidationError


class AgentDomainError(ValidationError):
    """Base error for invalid Plane Agent domain commands and contracts."""

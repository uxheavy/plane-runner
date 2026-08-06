# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.core.exceptions import ValidationError


class AgentDomainError(ValidationError):
    """Base error for invalid Plane Agent domain commands and contracts."""

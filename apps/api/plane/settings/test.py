# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Test Settings"""

import os

from .common import *  # noqa

DEBUG = True
PLANE_AUDIT_ENFORCE_ROLE_SEPARATION = os.environ.get("PLANE_AUDIT_ENFORCE_ROLE_SEPARATION", "0") == "1"
PLANE_AUDIT_MIGRATION_ROLE = (
    os.environ.get("PLANE_AUDIT_MIGRATION_ROLE") or DATABASES["default"].get("USER") or "plane"  # noqa: F405
)

# Send it in a dummy outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

INSTALLED_APPS.append(  # noqa
    "plane.tests"
)

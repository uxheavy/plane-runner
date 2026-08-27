# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane-native semantic tool adapters and catalog presentation.

Modules are intentionally imported by their explicit path.  The gateway also
imports a semantic adapter, so eager package imports would create a circular
dependency at the security seam.
"""

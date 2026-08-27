# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane's shared, authorization-bound operation gateway."""

from .catalog import OPERATION_CATALOG, OperationDescriptor

__all__ = ["OPERATION_CATALOG", "OperationDescriptor"]

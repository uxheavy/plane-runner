"""Plane Agent discovery facade over the canonical gateway catalog."""

from plane.operation_gateway.catalog import (
    CATALOG_DIGEST,
    CODE_MODE_CALLBACK_NAMES,
    OPERATION_CATALOG,
    OperationDescriptor,
    catalog_search,
    code_mode_callback_names,
    describe_operation,
    get_operation,
    operation_catalog_snapshot,
)

__all__ = [
    "CATALOG_DIGEST",
    "CODE_MODE_CALLBACK_NAMES",
    "OPERATION_CATALOG",
    "OperationDescriptor",
    "catalog_search",
    "code_mode_callback_names",
    "describe_operation",
    "get_operation",
    "operation_catalog_snapshot",
]

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.operation_gateway.views import OperationGatewayAPIEndpoint

urlpatterns = [
    path(
        "operations/",
        OperationGatewayAPIEndpoint.as_view(http_method_names=["post"]),
        name="operation-gateway",
    ),
]

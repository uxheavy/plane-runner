# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

"""API adapters for the existing operation catalog and gateway registry."""

from rest_framework.response import Response

from plane.agent.catalog_admin import catalog_page, gateway_status
from plane.api.views.agent_admin import AgentAdminAPIView


class AgentGatewayStatusAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        return Response(gateway_status())


class AgentGatewayCatalogAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug):
        raw_limit = request.query_params.get("limit", "10")
        try:
            limit = int(raw_limit)
            payload = catalog_page(
                query=request.query_params.get("query", ""),
                limit=limit,
                cursor=request.query_params.get("cursor"),
            )
        except (TypeError, ValueError) as exc:
            return Response({"error": {"code": "CATALOG_INVALID", "message": str(exc)}}, status=400)
        return Response(payload)

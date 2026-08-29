# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

from rest_framework.response import Response

from plane.agent.context_readback import AgentContextReadbackTooLarge, build_actor_context_readback
from plane.api.views.agent_admin import AgentAdminAPIView
from plane.db.models import AgentActor
from django.shortcuts import get_object_or_404


class AgentContextReadbackAPIEndpoint(AgentAdminAPIView):
    def get(self, request, slug, actor_id):
        actor = get_object_or_404(AgentActor, workspace__slug=slug, pk=actor_id)
        limit = self.get_per_page(request, default_per_page=1, max_per_page=10)
        try:
            return Response(build_actor_context_readback(actor, limit=limit))
        except AgentContextReadbackTooLarge as exc:
            return Response({"error": {"code": "READBACK_TOO_LARGE", "message": str(exc)}}, status=400)

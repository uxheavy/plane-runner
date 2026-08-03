# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import status
from rest_framework.response import Response

from plane.app.context_hydration import SemanticContextHydrationSerializer, hydrate_semantic_context
from plane.app.permissions import WorkspaceUserPermission

from .base import BaseAPIView


class SemanticContextHydrationEndpoint(BaseAPIView):
    permission_classes = [WorkspaceUserPermission]

    def post(self, request, slug):
        serializer = SemanticContextHydrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            hydrate_semantic_context(request.user, slug, serializer.validated_data["items"]),
            status=status.HTTP_200_OK,
        )

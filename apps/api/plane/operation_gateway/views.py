"""Internal JSON HTTP adapter for the shared Operation Gateway."""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.api.views.base import BaseAPIView

from .contracts import OperationGatewayRequestSerializer
from .gateway import OperationGateway


class OperationGatewayAPIEndpoint(BaseAPIView):
    """POST one versioned gateway envelope using the live API-key caller."""

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [AllowAny]

    def post(self, request: Any) -> Response:
        gateway = OperationGateway()
        if not request.user.is_authenticated:
            envelope, http_status = gateway.unauthenticated_response(request.data)
            return Response(envelope, status=http_status)

        serializer = OperationGatewayRequestSerializer(data=request.data)
        if not serializer.is_valid():
            envelope, http_status = gateway.record_invalid_request(request, request.data)
            return Response(envelope, status=http_status)

        envelope, http_status = gateway.execute(request, serializer.validated_data)
        return Response(envelope, status=http_status)

    def handle_exception(self, exc: Exception) -> Response:
        gateway = OperationGateway()
        raw_data = self._raw_data()
        user = getattr(self.request, "user", None)
        is_authenticated = bool(user is not None and user.is_authenticated)

        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            envelope, http_status = gateway.unauthenticated_response(raw_data)
            return Response(envelope, status=http_status)
        if isinstance(exc, Throttled):
            if is_authenticated:
                envelope, http_status = gateway.record_invalid_request(
                    self.request,
                    raw_data,
                    code="THROTTLED",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            else:
                envelope, http_status = gateway.unauthenticated_response(
                    raw_data,
                    code="THROTTLED",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return Response(envelope, status=http_status)
        if isinstance(exc, PermissionDenied):
            if is_authenticated:
                envelope, http_status = gateway.record_invalid_request(
                    self.request,
                    raw_data,
                    code="NOT_AUTHORIZED",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            else:
                envelope, http_status = gateway.unauthenticated_response(raw_data)
            return Response(envelope, status=http_status)

        if is_authenticated:
            envelope, http_status = gateway.record_invalid_request(
                self.request,
                raw_data,
                code="INTERNAL_ERROR",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        else:
            envelope, http_status = gateway.unauthenticated_response(raw_data)
        return Response(envelope, status=http_status)

    def _raw_data(self) -> Any:
        try:
            return self.request.data
        except Exception:
            return {}

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.utils import timezone
from django.db.models import Q

# Third party imports
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

# Module imports
from plane.db.models import APIToken


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authentication with an API Key
    """

    www_authenticate_realm = "api"
    media_type = "application/json"
    auth_header_name = "X-Api-Key"

    def get_api_token(self, request):
        return request.headers.get(self.auth_header_name)

    def validate_api_token(self, token):
        try:
            api_token = APIToken.objects.get(
                Q(Q(expired_at__gt=timezone.now()) | Q(expired_at__isnull=True)),
                token=token,
                is_active=True,
                user__is_active=True,
            )
        except APIToken.DoesNotExist:
            raise AuthenticationFailed("Given API token is not valid")

        # save api token last used
        api_token.last_used = timezone.now()
        api_token.save(update_fields=["last_used"])
        return (api_token.user, api_token.token)

    def authenticate(self, request):
        token = self.get_api_token(request=request)
        if not token:
            return None

        # Validate the API token
        user, token = self.validate_api_token(token)
        return user, token


class APIKeyOrBearerAuthentication(APIKeyAuthentication):
    """Authenticate the gateway with either the legacy API-key or bearer wire.

    The credential is still resolved through the existing ``APIToken`` model,
    so bearer transport does not introduce a second identity or permission
    system.  The external MCP OAuth adapter can preserve its bearer header
    while Plane remains the sole caller-binding authority.
    """

    def get_api_token(self, request):
        api_key = request.headers.get("X-Api-Key")
        if api_key:
            return api_key
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
        return None

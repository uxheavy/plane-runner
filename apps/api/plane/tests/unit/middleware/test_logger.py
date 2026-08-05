# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Unit tests for APITokenLogMiddleware.

Covers the credential-hygiene guarantees of the external API request logger:
- the raw API key is never persisted (a non-reversible hash is stored instead)
- sensitive request headers are redacted before being logged
"""

import hashlib
import hmac
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from plane.middleware.logger import APITokenLogMiddleware


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def middleware():
    return APITokenLogMiddleware(Mock(return_value=HttpResponse(b"{}")))


@pytest.mark.unit
class TestAPITokenLogMiddleware:
    API_KEY = "plane_api_supersecretvalue"
    AUTHORIZATION = "Bearer secret-bearer-token"
    COOKIE = "sessionid=secret-session-value"

    def _captured_log_data(self, middleware, request_factory):
        request = request_factory.get(
            "/api/v1/workspaces/",
            HTTP_X_API_KEY=self.API_KEY,
            HTTP_AUTHORIZATION=self.AUTHORIZATION,
            HTTP_COOKIE=self.COOKIE,
        )
        request.user = AnonymousUser()
        response = HttpResponse(b"{}")
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(request, response, request_body=b"")
            assert process_logs.delay.called
            return process_logs.delay.call_args.kwargs["log_data"]

    def test_token_identifier_is_hashed_not_plaintext(self, middleware, request_factory):
        log_data = self._captured_log_data(middleware, request_factory)

        expected_hash = hmac.new(settings.SECRET_KEY.encode(), self.API_KEY.encode(), hashlib.sha256).hexdigest()
        assert log_data["token_identifier"] == expected_hash
        assert self.API_KEY not in log_data["token_identifier"]

    def test_sensitive_headers_are_redacted(self, middleware, request_factory):
        log_data = self._captured_log_data(middleware, request_factory)

        # None of the sensitive header values may appear in the logged headers.
        assert self.API_KEY not in log_data["headers"]
        assert self.AUTHORIZATION not in log_data["headers"]
        assert self.COOKIE not in log_data["headers"]
        assert "[REDACTED]" in log_data["headers"]

    def test_no_log_without_api_key(self, middleware, request_factory):
        request = request_factory.get("/api/v1/workspaces/")
        request.user = AnonymousUser()
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(request, HttpResponse(b"{}"), request_body=b"")
            assert not process_logs.delay.called

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/workspaces/acme/agent-admin/actors/",
            "/api/v1/workspaces/acme/agent-admin/runs/run/input-events/",
            "/api/v1/workspaces/acme/agent-admin/runs/run/outcome/",
            "/api/v1/workspaces/acme/agent-runtime/runs/run/",
        ],
    )
    def test_agent_routes_queue_metadata_only(self, middleware, request_factory, path):
        request_secret = "credential_ref=canary-request-secret"
        response_secret = "raw-runtime-payload-canary"
        request = request_factory.post(
            path,
            data=request_secret.encode(),
            content_type="application/json",
            HTTP_X_API_KEY=self.API_KEY,
            HTTP_X_REQUEST_ID="request-canary-id",
        )
        request.user = AnonymousUser()
        response = HttpResponse(response_secret.encode(), status=201)
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(request, response, request_body=request_secret.encode(), duration_ms=7)
            log_data = process_logs.delay.call_args.kwargs["log_data"]

        serialized = repr(log_data)
        assert request_secret not in serialized
        assert response_secret not in serialized
        assert self.API_KEY not in serialized
        assert "headers" not in log_data
        assert log_data["request_body"]["bytes"] == len(request_secret.encode())
        assert log_data["response_body"]["bytes"] == len(response_secret.encode())
        assert log_data["request_id"] == "request-canary-id"

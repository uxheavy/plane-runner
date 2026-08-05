# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.api.views.agent_admin import (
    AgentActorAdminDetailAPIEndpoint,
    AgentActorAdminListCreateAPIEndpoint,
    AgentAssignmentAdminDetailAPIEndpoint,
    AgentAssignmentAdminListCreateAPIEndpoint,
    AgentAssignmentCancelAPIEndpoint,
    AgentAssignmentDispatchAPIEndpoint,
    AgentGatewayReadbackDetailAPIEndpoint,
    AgentGatewayReadbackListAPIEndpoint,
    AgentOutcomeAcceptAPIEndpoint,
    AgentOutcomeAdminCreateAPIEndpoint,
    AgentOutcomeAdminDetailAPIEndpoint,
    AgentOutcomeRevisionAPIEndpoint,
    AgentOutcomeReviewAPIEndpoint,
    AgentProfileVersionAdminListCreateAPIEndpoint,
    AgentProfileVersionAdminDetailAPIEndpoint,
    AgentRunAdminDetailAPIEndpoint,
    AgentRunCancelAPIEndpoint,
    AgentRunInputEventAdminListCreateAPIEndpoint,
    AgentRunInvocationAdminListCreateAPIEndpoint,
)


urlpatterns = [
    path(
        "workspaces/<str:slug>/agent-admin/actors/",
        AgentActorAdminListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="agent-admin-actors",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/actors/<uuid:pk>/",
        AgentActorAdminDetailAPIEndpoint.as_view(http_method_names=["get", "patch"]),
        name="agent-admin-actor",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/actors/<uuid:actor_id>/profiles/",
        AgentProfileVersionAdminListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="agent-admin-profiles",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/actors/<uuid:actor_id>/profiles/<uuid:pk>/",
        AgentProfileVersionAdminDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-profile",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/actors/<uuid:actor_id>/assignments/",
        AgentAssignmentAdminListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="agent-admin-assignments",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/assignments/<uuid:pk>/",
        AgentAssignmentAdminDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-assignment",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/assignments/<uuid:assignment_id>/cancel/",
        AgentAssignmentCancelAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-assignment-cancel",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/assignments/<uuid:assignment_id>/dispatch/",
        AgentAssignmentDispatchAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-assignment-dispatch",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/runs/<uuid:pk>/",
        AgentRunAdminDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-run",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/runs/<uuid:run_id>/input-events/",
        AgentRunInputEventAdminListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="agent-admin-run-input-events",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/runs/<uuid:run_id>/invocations/",
        AgentRunInvocationAdminListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="agent-admin-run-invocations",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/runs/<uuid:run_id>/cancel/",
        AgentRunCancelAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-run-cancel",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/runs/<uuid:run_id>/outcome/",
        AgentOutcomeAdminCreateAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-outcome-create",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/outcomes/<uuid:pk>/",
        AgentOutcomeAdminDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-outcome",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/outcomes/<uuid:pk>/review/",
        AgentOutcomeReviewAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-outcome-review",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/outcomes/<uuid:pk>/accept/",
        AgentOutcomeAcceptAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-outcome-accept",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/outcomes/<uuid:pk>/revise/",
        AgentOutcomeRevisionAPIEndpoint.as_view(http_method_names=["post"]),
        name="agent-admin-outcome-revise",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/gateway/readback/",
        AgentGatewayReadbackListAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-gateway-readback",
    ),
    path(
        "workspaces/<str:slug>/agent-admin/gateway/readback/<uuid:pk>/",
        AgentGatewayReadbackDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="agent-admin-gateway-receipt",
    ),
]

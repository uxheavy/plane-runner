# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Skeptical-integrator dogfood coverage for the routed hydration API."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember


def _url(slug):
    return f"/api/workspaces/{slug}/chat-context/hydrate/"


def _project_reference(workspace, project, **overrides):
    reference = {
        "kind": "entity",
        "workspaceSlug": workspace.slug,
        "projectId": str(project.id),
        "entityType": "project",
        "entityId": str(project.id),
    }
    reference.update(overrides)
    return reference


def _payload(items, schema_version=1):
    return {"schemaVersion": schema_version, "items": items}


def _item(reference, **overrides):
    item = {"reference": reference}
    item.update(overrides)
    return item


def _assert_safe_json_error(response, expected_status=status.HTTP_400_BAD_REQUEST):
    assert response.status_code == expected_status
    assert response.headers["Content-Type"].startswith("application/json")
    body = response.json()
    rendered = str(body).lower()
    assert body
    assert "traceback" not in rendered
    assert "sql" not in rendered
    assert "/users/" not in rendered


@pytest.fixture
def quinn_project(db, workspace, create_user):
    project = Project.objects.create(
        name="Quinn API Contract",
        identifier="QAPI",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=create_user,
        role=20,
        is_active=True,
    )
    return project


@pytest.mark.contract
@pytest.mark.django_db
class TestSemanticContextHydrationQuinnDogfood:
    def test_authentication_and_method_boundaries(self, session_client, workspace, quinn_project):
        reference = _project_reference(workspace, quinn_project)

        anonymous = APIClient().post(_url(workspace.slug), _payload([_item(reference)]), format="json")
        _assert_safe_json_error(anonymous, status.HTTP_401_UNAUTHORIZED)

        wrong_method = session_client.get(_url(workspace.slug))
        _assert_safe_json_error(wrong_method, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_json_parsing_and_content_type_boundaries(self, session_client, workspace):
        malformed_json = session_client.generic(
            "POST",
            _url(workspace.slug),
            data=b'{"schemaVersion": 1,',
            content_type="application/json",
        )
        _assert_safe_json_error(malformed_json)

        unsupported_media_type = session_client.generic(
            "POST",
            _url(workspace.slug),
            data=b'{"schemaVersion": 1, "items": []}',
            content_type="text/plain",
        )
        _assert_safe_json_error(unsupported_media_type, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            {},
            {"schemaVersion": 1},
            {"items": []},
            {"schemaVersion": None, "items": []},
            {"schemaVersion": 1, "items": None},
            {"schemaVersion": 1, "items": {}},
            {"schemaVersion": 1, "items": []},
            {"schemaVersion": 0, "items": [{}]},
            {"schemaVersion": 2, "items": [{}]},
            {"schemaVersion": 1, "items": [None]},
            {"schemaVersion": 1, "items": [{}]},
            {"schemaVersion": 1, "items": [{"reference": None}]},
            {"schemaVersion": 1, "items": [], "unexpected": True},
        ],
    )
    def test_empty_missing_null_and_wrong_shape_payloads_are_safe_400s(self, session_client, workspace, payload):
        response = session_client.post(_url(workspace.slug), payload, format="json")
        _assert_safe_json_error(response)

    @pytest.mark.parametrize(
        "reference",
        [
            {"kind": "future_kind"},
            {
                "kind": "entity",
                "workspaceSlug": "test-workspace",
                "projectId": "not-a-uuid",
                "entityType": "project",
                "entityId": "not-a-uuid",
            },
            {
                "kind": "entity",
                "workspaceSlug": "test-workspace",
                "projectId": str(uuid4()),
                "entityType": "future_entity",
                "entityId": str(uuid4()),
            },
            {
                "kind": "field",
                "entity": {
                    "kind": "entity",
                    "workspaceSlug": "test-workspace",
                    "projectId": str(uuid4()),
                    "entityType": "project",
                    "entityId": str(uuid4()),
                },
                "fieldKey": "secret_field",
            },
        ],
    )
    def test_invalid_identity_kind_type_and_field_are_safe_400s(self, session_client, workspace, reference):
        response = session_client.post(_url(workspace.slug), _payload([_item(reference)]), format="json")
        _assert_safe_json_error(response)

    def test_duplicate_items_and_fifty_item_batch_preserve_order_and_correlation(
        self, session_client, workspace, quinn_project
    ):
        reference = _project_reference(workspace, quinn_project)
        items = [_item(reference) for _ in range(50)]

        response = session_client.post(_url(workspace.slug), _payload(items), format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["schemaVersion"] == 1
        assert len(response.data["results"]) == 50
        assert [result["reference"] for result in response.data["results"]] == [reference] * 50
        assert all(result["ok"] for result in response.data["results"])
        assert len({result["authorizedAt"] for result in response.data["results"]}) == 1

        oversized = session_client.post(_url(workspace.slug), _payload(items + [_item(reference)]), format="json")
        _assert_safe_json_error(oversized)

    def test_mixed_success_and_not_found_results_remain_item_scoped_and_ordered(
        self, session_client, workspace, quinn_project
    ):
        found = _project_reference(workspace, quinn_project)
        missing_id = uuid4()
        missing = _project_reference(
            workspace,
            quinn_project,
            projectId=str(missing_id),
            entityId=str(missing_id),
        )

        response = session_client.post(
            _url(workspace.slug),
            _payload([_item(found), _item(missing), _item(found)]),
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert [result["ok"] for result in response.data["results"]] == [True, False, True]
        assert response.data["results"][1]["code"] == "FORBIDDEN"
        assert [result["reference"] for result in response.data["results"]] == [found, missing, found]

    def test_observed_versions_have_predictable_freshness_semantics(self, session_client, workspace, quinn_project):
        reference = _project_reference(workspace, quinn_project)
        equal = quinn_project.updated_at.isoformat()
        older = (quinn_project.updated_at - timedelta(days=1)).isoformat()
        newer = (quinn_project.updated_at + timedelta(days=1)).isoformat()
        items = [
            _item(reference),
            _item(reference, observedEntityVersion=equal),
            _item(reference, observedEntityVersion=older),
            _item(reference, observedEntityVersion=newer),
        ]

        response = session_client.post(_url(workspace.slug), _payload(items), format="json")

        assert response.status_code == status.HTTP_200_OK
        assert [result["stale"] for result in response.data["results"]] == [False, False, True, True]
        assert all(result["canonical"]["entityVersion"] == equal for result in response.data["results"])

    @pytest.mark.parametrize("observed", ["", "yesterday", 123, True, [], {}])
    def test_malformed_observed_versions_are_safe_400s(self, session_client, workspace, quinn_project, observed):
        reference = _project_reference(workspace, quinn_project)
        response = session_client.post(
            _url(workspace.slug),
            _payload([_item(reference, observedEntityVersion=observed)]),
            format="json",
        )
        _assert_safe_json_error(response)

    def test_error_responses_do_not_echo_unknown_payload_values(self, session_client, workspace):
        marker = "DO-NOT-ECHO-QUI-7d2f"
        response = session_client.post(
            _url(workspace.slug),
            {"schemaVersion": 1, "items": [], marker: marker},
            format="json",
        )

        _assert_safe_json_error(response)
        assert marker not in str(response.json())

    def test_current_timestamp_with_timezone_is_accepted(self, session_client, workspace, quinn_project):
        reference = _project_reference(workspace, quinn_project)
        response = session_client.post(
            _url(workspace.slug),
            _payload([_item(reference, observedEntityVersion=timezone.now().isoformat())]),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

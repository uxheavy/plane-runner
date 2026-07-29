# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Routed API dogfood for restricted semantic-context collaborators."""

from uuid import uuid4

import pytest
from rest_framework import status

from plane.db.models import Issue, Page, Project, ProjectMember, ProjectPage, User, WorkspaceMember


def _url(slug):
    return f"/api/workspaces/{slug}/chat-context/hydrate/"


def _entity(workspace_slug, project_id, entity_type, entity_id):
    return {
        "kind": "entity",
        "workspaceSlug": workspace_slug,
        "projectId": str(project_id),
        "entityType": entity_type,
        "entityId": str(entity_id),
    }


def _post(client, workspace_slug, references):
    return client.post(
        _url(workspace_slug),
        {
            "schemaVersion": 1,
            "items": [{"reference": reference} for reference in references],
        },
        format="json",
    )


def _user(prefix):
    identity = uuid4()
    return User.objects.create(
        username=f"{prefix}-{identity}",
        email=f"{prefix}-{identity}@plane.test",
    )


def _add_memberships(workspace, project, user, *, role=5):
    workspace_member = WorkspaceMember.objects.create(
        workspace=workspace,
        member=user,
        role=role,
        is_active=True,
    )
    project_member = ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=user,
        role=role,
        is_active=True,
    )
    return workspace_member, project_member


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Ravi's scoped project",
        identifier="RAVI",
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


@pytest.fixture
def work_item(db, workspace, project):
    return Issue.objects.create(
        name="Restricted context",
        project=project,
        workspace=workspace,
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestRaviSemanticContextHydrationDogfood:
    def test_anonymous_and_inactive_workspace_members_cannot_enter_route(
        self, api_client, workspace, project, work_item
    ):
        reference = _entity(workspace.slug, project.id, "work_item", work_item.id)

        anonymous_response = _post(api_client, workspace.slug, [reference])
        assert anonymous_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "results" not in anonymous_response.data

        inactive_user = _user("inactive-workspace")
        workspace_member, _ = _add_memberships(workspace, project, inactive_user)
        workspace_member.is_active = False
        workspace_member.save(update_fields=["is_active"])
        api_client.force_authenticate(user=inactive_user)

        inactive_response = _post(api_client, workspace.slug, [reference])
        assert inactive_response.status_code == status.HTTP_403_FORBIDDEN
        assert "results" not in inactive_response.data

    def test_missing_and_inactive_project_memberships_fail_per_item_without_leaking_values(
        self, api_client, workspace, project, work_item
    ):
        reference = _entity(workspace.slug, project.id, "work_item", work_item.id)
        user = _user("limited-project")
        WorkspaceMember.objects.create(
            workspace=workspace,
            member=user,
            role=15,
            is_active=True,
        )
        api_client.force_authenticate(user=user)

        missing_response = _post(api_client, workspace.slug, [reference])
        assert missing_response.status_code == status.HTTP_200_OK
        assert missing_response.data["results"][0]["code"] == "FORBIDDEN"
        assert "canonical" not in missing_response.data["results"][0]

        project_member = ProjectMember.objects.create(
            workspace=workspace,
            project=project,
            member=user,
            role=5,
            is_active=False,
        )
        inactive_response = _post(api_client, workspace.slug, [reference])
        assert inactive_response.status_code == status.HTTP_200_OK
        assert inactive_response.data["results"][0]["code"] == "FORBIDDEN"
        assert "canonical" not in inactive_response.data["results"][0]
        assert project_member.is_active is False

    def test_guest_page_access_tracks_feature_switch_and_private_ownership(
        self, api_client, workspace, project, create_user
    ):
        guest = _user("guest")
        _add_memberships(workspace, project, guest, role=5)
        api_client.force_authenticate(user=guest)

        public_page = Page.objects.create(
            workspace=workspace,
            name="Guest feature page",
            owned_by=create_user,
            access=Page.PUBLIC_ACCESS,
        )
        owned_private_page = Page.objects.create(
            workspace=workspace,
            name="Ravi's private page",
            owned_by=guest,
            access=Page.PRIVATE_ACCESS,
        )
        other_private_page = Page.objects.create(
            workspace=workspace,
            name="Someone else's private page",
            owned_by=create_user,
            access=Page.PRIVATE_ACCESS,
        )
        for page in [public_page, owned_private_page, other_private_page]:
            ProjectPage.objects.create(project=project, page=page, workspace=workspace)

        references = [
            _entity(workspace.slug, project.id, "page", page.id)
            for page in [public_page, owned_private_page, other_private_page]
        ]
        feature_off_response = _post(api_client, workspace.slug, references)
        assert [result.get("code") for result in feature_off_response.data["results"]] == [
            "FORBIDDEN",
            None,
            "FORBIDDEN",
        ]
        assert feature_off_response.data["results"][1]["ok"] is True
        assert all(
            "canonical" not in result
            for result in [
                feature_off_response.data["results"][0],
                feature_off_response.data["results"][2],
            ]
        )

        project.guest_view_all_features = True
        project.save(update_fields=["guest_view_all_features"])
        feature_on_response = _post(api_client, workspace.slug, references)
        assert feature_on_response.data["results"][0]["ok"] is True
        assert feature_on_response.data["results"][1]["ok"] is True
        assert feature_on_response.data["results"][2]["code"] == "FORBIDDEN"

    def test_private_editor_blocks_authorize_the_owner_without_leaking_content(self, api_client, workspace, project):
        owner = _user("private-page-owner")
        outsider = _user("private-page-outsider")
        _add_memberships(workspace, project, owner, role=15)
        _add_memberships(workspace, project, outsider, role=15)
        page = Page.objects.create(
            workspace=workspace,
            name="Private editor document",
            owned_by=owner,
            access=Page.PRIVATE_ACCESS,
        )
        ProjectPage.objects.create(project=project, page=page, workspace=workspace)
        reference = {
            "kind": "editor_block",
            "document": _entity(workspace.slug, project.id, "page", page.id),
            "blockId": "block-with-private-content",
        }

        api_client.force_authenticate(user=owner)
        owner_response = _post(api_client, workspace.slug, [reference])
        owner_result = owner_response.data["results"][0]
        assert owner_result["ok"] is True
        assert owner_result["resolution"] == "authorization_only"
        assert "canonical" not in owner_result

        api_client.force_authenticate(user=outsider)
        outsider_response = _post(api_client, workspace.slug, [reference])
        outsider_result = outsider_response.data["results"][0]
        assert outsider_result["ok"] is False
        assert outsider_result["code"] == "FORBIDDEN"
        assert "canonical" not in outsider_result

    def test_workspace_mismatch_is_rejected_before_any_item_resolution(self, api_client, workspace, project, work_item):
        user = _user("mismatch")
        _add_memberships(workspace, project, user, role=5)
        api_client.force_authenticate(user=user)
        valid = _entity(workspace.slug, project.id, "work_item", work_item.id)
        mismatch = {**valid, "workspaceSlug": "another-workspace"}

        response = _post(api_client, workspace.slug, [valid, mismatch])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "results" not in response.data
        assert str(work_item.id) not in str(response.data)

    def test_cross_project_identity_and_deleted_entity_are_not_found(
        self, api_client, workspace, project, work_item, create_user
    ):
        user = _user("scoped")
        _add_memberships(workspace, project, user, role=5)
        other_project = Project.objects.create(
            name="Other scope",
            identifier="OTHER-RAVI",
            workspace=workspace,
            created_by=create_user,
            guest_view_all_features=True,
        )
        ProjectMember.objects.create(
            workspace=workspace,
            project=other_project,
            member=user,
            role=5,
            is_active=True,
        )
        api_client.force_authenticate(user=user)
        cross_project = _entity(workspace.slug, other_project.id, "work_item", work_item.id)
        deleted = _entity(workspace.slug, project.id, "work_item", work_item.id)
        work_item.delete()

        response = _post(api_client, workspace.slug, [cross_project, deleted])

        assert response.status_code == status.HTTP_200_OK
        assert [result["code"] for result in response.data["results"]] == ["NOT_FOUND", "NOT_FOUND"]
        assert all("canonical" not in result for result in response.data["results"])

    def test_deleted_page_link_and_revoked_project_link_stop_resolution(
        self, api_client, workspace, project, create_user
    ):
        user = _user("revoked-link")
        _, project_member = _add_memberships(workspace, project, user, role=15)
        page = Page.objects.create(
            workspace=workspace,
            name="Unlinked page",
            owned_by=create_user,
            access=Page.PUBLIC_ACCESS,
        )
        project_page = ProjectPage.objects.create(project=project, page=page, workspace=workspace)
        reference = _entity(workspace.slug, project.id, "page", page.id)
        api_client.force_authenticate(user=user)

        project_page.delete()
        unlinked_response = _post(api_client, workspace.slug, [reference])
        assert unlinked_response.status_code == status.HTTP_200_OK
        assert unlinked_response.data["results"][0]["code"] == "NOT_FOUND"
        assert "canonical" not in unlinked_response.data["results"][0]

        project_member.is_active = False
        project_member.save(update_fields=["is_active"])
        revoked_response = _post(api_client, workspace.slug, [reference])
        assert revoked_response.status_code == status.HTTP_200_OK
        assert revoked_response.data["results"][0]["code"] == "FORBIDDEN"
        assert "canonical" not in revoked_response.data["results"][0]

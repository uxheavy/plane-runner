# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for permission-safe semantic context hydration."""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError

from plane.app.context_hydration import hydrate_semantic_context
from plane.db.models import (
    Cycle,
    CycleIssue,
    Estimate,
    EstimatePoint,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueView,
    Label,
    Module,
    ModuleIssue,
    Page,
    Project,
    ProjectMember,
    ProjectPage,
    State,
    User,
    WorkspaceMember,
)


def _url(slug):
    return f"/api/workspaces/{slug}/chat-context/hydrate/"


def _entity(workspace, project, entity_type, entity_id):
    return {
        "kind": "entity",
        "workspaceSlug": workspace.slug,
        "projectId": str(project.id),
        "entityType": entity_type,
        "entityId": str(entity_id),
    }


def _hydrate(client, workspace, items):
    return client.post(
        _url(workspace.slug),
        {"schemaVersion": 1, "items": items},
        format="json",
    )


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Context Project",
        identifier="CTX",
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
def work_item(db, workspace, project, create_user):
    state = State.objects.create(
        name="Started",
        color="#123456",
        group="started",
        project=project,
        workspace=workspace,
    )
    return Issue.objects.create(
        name="Fresh canonical work item",
        description_html="<p>Approved description</p>",
        state=state,
        priority="high",
        project=project,
        workspace=workspace,
    )


def _add_user(workspace, project, role=15):
    identity = uuid4()
    user = User.objects.create(username=f"context-{identity}", email=f"context-{identity}@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role, is_active=True)
    ProjectMember.objects.create(workspace=workspace, project=project, member=user, role=role, is_active=True)
    return user


@pytest.mark.contract
@pytest.mark.django_db
class TestSemanticContextHydration:
    def test_hydrates_every_supported_entity_and_work_item_field(
        self, session_client, workspace, project, work_item, create_user
    ):
        cycle = Cycle.objects.create(
            name="Cycle One",
            description="Cycle description",
            owned_by=create_user,
            project=project,
            workspace=workspace,
        )
        module = Module.objects.create(
            name="Module One",
            description="Module description",
            project=project,
            workspace=workspace,
        )
        page = Page.objects.create(
            workspace=workspace,
            name="Public page",
            owned_by=create_user,
            access=Page.PUBLIC_ACCESS,
        )
        view = IssueView.objects.create(
            workspace=workspace,
            project=project,
            name="Public view",
            description="View description",
            query={},
            owned_by=create_user,
            access=1,
        )
        label = Label.objects.create(name="Bug", project=project, workspace=workspace)
        estimate = Estimate.objects.create(name="Points", project=project, workspace=workspace)
        point = EstimatePoint.objects.create(
            estimate=estimate,
            key=2,
            value="Medium",
            project=project,
            workspace=workspace,
        )
        ProjectPage.objects.create(project=project, page=page, workspace=workspace)
        CycleIssue.objects.create(cycle=cycle, issue=work_item, project=project, workspace=workspace)
        ModuleIssue.objects.create(module=module, issue=work_item, project=project, workspace=workspace)
        IssueAssignee.objects.create(
            issue=work_item,
            assignee=create_user,
            project=project,
            workspace=workspace,
        )
        IssueLabel.objects.create(issue=work_item, label=label, project=project, workspace=workspace)
        Issue.objects.filter(id=work_item.id).update(estimate_point=point)
        work_item.refresh_from_db()

        entity_references = [
            _entity(workspace, project, "work_item", work_item.id),
            _entity(workspace, project, "project", project.id),
            _entity(workspace, project, "cycle", cycle.id),
            _entity(workspace, project, "module", module.id),
            _entity(workspace, project, "page", page.id),
            _entity(workspace, project, "view", view.id),
        ]
        work_item_fields = [
            "name",
            "description",
            "state",
            "priority",
            "assignees",
            "labels",
            "start_date",
            "target_date",
            "estimate",
            "cycle",
            "module",
        ]
        items = [{"reference": reference} for reference in entity_references]
        items.extend(
            {
                "reference": {
                    "kind": "field",
                    "entity": entity_references[0],
                    "fieldKey": field,
                }
            }
            for field in work_item_fields
        )

        response = _hydrate(session_client, workspace, items)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 17
        assert all(result["ok"] for result in response.data["results"])
        entity_values = [result["canonical"]["value"] for result in response.data["results"][:6]]
        assert [value["name"] for value in entity_values] == [
            "Fresh canonical work item",
            "Context Project",
            "Cycle One",
            "Module One",
            "Public page",
            "Public view",
        ]
        assert "description" not in entity_values[0]
        assert "query" not in entity_values[-1]
        field_values = {
            field: result["canonical"]["value"] for field, result in zip(work_item_fields, response.data["results"][6:])
        }
        assert field_values["state"]["name"] == "Started"
        assert field_values["assignees"] == [{"id": str(create_user.id), "displayName": create_user.display_name}]
        assert field_values["labels"] == [{"id": str(label.id), "name": "Bug"}]
        assert field_values["estimate"] == {"id": str(point.id), "key": 2, "value": "Medium"}
        assert field_values["cycle"] == {"id": str(cycle.id), "name": "Cycle One"}
        assert field_values["module"] == [{"id": str(module.id), "name": "Module One"}]

    def test_hydrates_canonical_entity_and_field_and_marks_stale(self, session_client, workspace, project, work_item):
        reference = _entity(workspace, project, "work_item", work_item.id)
        response = _hydrate(
            session_client,
            workspace,
            [
                {"reference": reference, "observedEntityVersion": "2000-01-01T00:00:00Z"},
                {
                    "reference": {
                        "kind": "field",
                        "entity": reference,
                        "fieldKey": "description",
                    }
                },
            ],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["schemaVersion"] == 1
        entity_result, field_result = response.data["results"]
        assert entity_result["ok"] is True
        assert entity_result["resolution"] == "canonical"
        assert entity_result["canonical"]["source"] == "server_canonical"
        assert entity_result["canonical"]["value"]["name"] == "Fresh canonical work item"
        assert entity_result["stale"] is True
        assert field_result["canonical"]["value"] == "<p>Approved description</p>"

    @pytest.mark.parametrize("role", [20, 15])
    def test_admins_and_members_can_hydrate_project_entities(self, api_client, workspace, project, work_item, role):
        user = _add_user(workspace, project, role)
        api_client.force_authenticate(user=user)

        response = _hydrate(
            api_client,
            workspace,
            [{"reference": _entity(workspace, project, "work_item", work_item.id)}],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["ok"] is True

    def test_restricted_guest_can_only_hydrate_work_items_they_created(
        self, api_client, workspace, project, work_item
    ):
        guest = _add_user(workspace, project, role=5)
        guest_work_item = Issue(
            name="Guest-created work item",
            state=work_item.state,
            priority="none",
            project=project,
            workspace=workspace,
        )
        guest_work_item.save(created_by_id=guest.id)
        api_client.force_authenticate(user=guest)
        restricted_reference = _entity(workspace, project, "work_item", work_item.id)

        response = _hydrate(
            api_client,
            workspace,
            [
                {"reference": restricted_reference},
                {"reference": {"kind": "field", "entity": restricted_reference, "fieldKey": "name"}},
                {
                    "reference": {
                        "kind": "editor_block",
                        "document": restricted_reference,
                        "blockId": "restricted-block",
                    }
                },
                {"reference": _entity(workspace, project, "work_item", guest_work_item.id)},
            ],
        )

        assert response.status_code == status.HTTP_200_OK
        *denied, allowed = response.data["results"]
        assert all(result["ok"] is False and result["code"] == "FORBIDDEN" for result in denied)
        assert allowed["ok"] is True
        assert allowed["canonical"]["value"]["name"] == "Guest-created work item"

    def test_workspace_member_without_project_access_is_denied(self, api_client, workspace, project, work_item):
        identity = uuid4()
        user = User.objects.create(
            username=f"workspace-only-{identity}",
            email=f"workspace-only-{identity}@plane.so",
        )
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15, is_active=True)
        api_client.force_authenticate(user=user)

        response = _hydrate(
            api_client,
            workspace,
            [{"reference": _entity(workspace, project, "work_item", work_item.id)}],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["ok"] is False
        assert response.data["results"][0]["code"] == "FORBIDDEN"

    def test_private_page_requires_owner_and_editor_capture_is_authorization_only(
        self, session_client, workspace, project, create_user
    ):
        page = Page.objects.create(
            workspace=workspace,
            name="Private plan",
            owned_by=create_user,
            access=Page.PRIVATE_ACCESS,
        )
        ProjectPage.objects.create(project=project, page=page, workspace=workspace)
        reference = _entity(workspace, project, "page", page.id)
        editor_reference = {"kind": "editor_block", "document": reference, "blockId": "block-1"}

        owner_response = _hydrate(session_client, workspace, [{"reference": editor_reference}])
        assert owner_response.data["results"][0]["ok"] is True
        assert owner_response.data["results"][0]["resolution"] == "authorization_only"
        assert "canonical" not in owner_response.data["results"][0]

        other = _add_user(workspace, project)
        session_client.force_authenticate(user=other)
        denied_response = _hydrate(session_client, workspace, [{"reference": editor_reference}])
        assert denied_response.data["results"][0]["ok"] is False
        assert denied_response.data["results"][0]["code"] == "FORBIDDEN"

    def test_guest_page_visibility_follows_project_feature_access(self, api_client, workspace, project, create_user):
        page = Page.objects.create(
            workspace=workspace,
            name="Guest-visible page",
            owned_by=create_user,
            access=Page.PUBLIC_ACCESS,
        )
        ProjectPage.objects.create(project=project, page=page, workspace=workspace)
        guest = _add_user(workspace, project, role=5)
        api_client.force_authenticate(user=guest)
        item = {"reference": _entity(workspace, project, "page", page.id)}

        denied_response = _hydrate(api_client, workspace, [item])
        assert denied_response.data["results"][0]["code"] == "FORBIDDEN"

        Project.objects.filter(id=project.id).update(guest_view_all_features=True)
        allowed_response = _hydrate(api_client, workspace, [item])
        assert allowed_response.data["results"][0]["ok"] is True

    def test_deleted_and_cross_project_objects_do_not_resolve(
        self, session_client, workspace, project, work_item, create_user
    ):
        other_project = Project.objects.create(
            name="Other Project",
            identifier="OTHER",
            workspace=workspace,
            created_by=create_user,
        )
        ProjectMember.objects.create(
            workspace=workspace,
            project=other_project,
            member=create_user,
            role=20,
            is_active=True,
        )
        cross_project = _entity(workspace, other_project, "work_item", work_item.id)
        deleted_reference = _entity(workspace, project, "work_item", work_item.id)
        work_item.delete()

        response = _hydrate(
            session_client,
            workspace,
            [{"reference": deleted_reference}, {"reference": cross_project}],
        )

        assert response.status_code == status.HTTP_200_OK
        assert [result["code"] for result in response.data["results"]] == ["NOT_FOUND", "NOT_FOUND"]

    def test_rejects_workspace_mismatch_and_unbounded_batches(self, session_client, workspace, project):
        mismatched = _entity(workspace, project, "project", project.id)
        mismatched["workspaceSlug"] = "another-workspace"

        mismatch_response = _hydrate(session_client, workspace, [{"reference": mismatched}])
        assert mismatch_response.status_code == status.HTTP_400_BAD_REQUEST

        oversized_response = _hydrate(
            session_client,
            workspace,
            [{"reference": _entity(workspace, project, "project", project.id)}] * 51,
        )
        assert oversized_response.status_code == status.HTTP_400_BAD_REQUEST

    def test_service_revalidates_references_when_called_without_the_api_serializer(self, create_user, workspace):
        with pytest.raises(ValidationError):
            hydrate_semantic_context(
                create_user,
                workspace.slug,
                [{"reference": {"kind": "entity", "workspaceSlug": workspace.slug}}],
            )

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project-lead dogfood coverage for the routed semantic context API."""

from datetime import date

import pytest
from rest_framework import status

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
)


WORK_ITEM_FIELDS = [
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


def _url(workspace):
    return f"/api/workspaces/{workspace.slug}/chat-context/hydrate/"


def _entity(workspace, project, entity_type, entity_id):
    return {
        "kind": "entity",
        "workspaceSlug": workspace.slug,
        "projectId": str(project.id),
        "entityType": entity_type,
        "entityId": str(entity_id),
    }


def _post(client, workspace, items):
    return client.post(
        _url(workspace),
        {"schemaVersion": 1, "items": items},
        format="json",
    )


@pytest.fixture
def maya_scenario(db, api_client, workspace, create_user):
    """Create a realistic active-project graph behind an isolated app client."""
    project = Project.objects.create(
        name="Launch Project",
        identifier="LAUNCH",
        description="Ship the agent-native workflow",
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
    state = State.objects.create(
        name="In Progress",
        color="#123456",
        group="started",
        project=project,
        workspace=workspace,
    )
    work_item = Issue.objects.create(
        name="Prepare launch",
        description_html="<p>Coordinate the release.</p>",
        state=state,
        priority="high",
        start_date=date(2026, 7, 29),
        target_date=date(2026, 8, 5),
        project=project,
        workspace=workspace,
    )
    cycle = Cycle.objects.create(
        name="Launch week",
        description="Final launch cycle",
        owned_by=create_user,
        project=project,
        workspace=workspace,
    )
    module = Module.objects.create(
        name="Agent context",
        description="Semantic context delivery",
        project=project,
        workspace=workspace,
    )
    page = Page.objects.create(
        workspace=workspace,
        name="Launch brief",
        owned_by=create_user,
        access=Page.PUBLIC_ACCESS,
    )
    view = IssueView.objects.create(
        workspace=workspace,
        project=project,
        name="Launch blockers",
        description="High-priority work",
        query={},
        owned_by=create_user,
        access=1,
    )
    label = Label.objects.create(name="Launch", project=project, workspace=workspace)
    estimate = Estimate.objects.create(name="Effort", project=project, workspace=workspace)
    estimate_point = EstimatePoint.objects.create(
        estimate=estimate,
        key=3,
        value="Large",
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
    Issue.objects.filter(id=work_item.id).update(estimate_point=estimate_point)
    work_item.refresh_from_db()
    api_client.force_authenticate(user=create_user)
    return {
        "client": api_client,
        "workspace": workspace,
        "project": project,
        "work_item": work_item,
        "cycle": cycle,
        "module": module,
        "page": page,
        "view": view,
        "label": label,
        "estimate_point": estimate_point,
        "user": create_user,
    }


@pytest.mark.contract
@pytest.mark.django_db
class TestMayaSemanticContextDogfood:
    def test_realistic_mixed_request_returns_all_entities_and_fields(self, maya_scenario):
        scenario = maya_scenario
        workspace = scenario["workspace"]
        project = scenario["project"]
        work_item_reference = _entity(workspace, project, "work_item", scenario["work_item"].id)
        entities = [
            work_item_reference,
            _entity(workspace, project, "project", project.id),
            _entity(workspace, project, "cycle", scenario["cycle"].id),
            _entity(workspace, project, "module", scenario["module"].id),
            _entity(workspace, project, "page", scenario["page"].id),
            _entity(workspace, project, "view", scenario["view"].id),
        ]
        items = [{"reference": reference} for reference in entities]
        items.extend(
            {
                "reference": {
                    "kind": "field",
                    "entity": work_item_reference,
                    "fieldKey": field,
                }
            }
            for field in WORK_ITEM_FIELDS
        )

        response = _post(scenario["client"], workspace, items)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["schemaVersion"] == 1
        assert len(response.data["results"]) == 17
        assert all(result["ok"] for result in response.data["results"])
        assert [result["reference"] for result in response.data["results"]] == [item["reference"] for item in items]
        assert [result["canonical"]["value"]["name"] for result in response.data["results"][:6]] == [
            "Prepare launch",
            "Launch Project",
            "Launch week",
            "Agent context",
            "Launch brief",
            "Launch blockers",
        ]
        fields = {
            key: result["canonical"]["value"] for key, result in zip(WORK_ITEM_FIELDS, response.data["results"][6:])
        }
        assert fields == {
            "name": "Prepare launch",
            "description": "<p>Coordinate the release.</p>",
            "state": {
                "id": str(scenario["work_item"].state_id),
                "name": "In Progress",
                "group": "started",
            },
            "priority": "high",
            "assignees": [
                {
                    "id": str(scenario["user"].id),
                    "displayName": scenario["user"].display_name,
                }
            ],
            "labels": [{"id": str(scenario["label"].id), "name": "Launch"}],
            "start_date": "2026-07-29",
            "target_date": "2026-08-05",
            "estimate": {
                "id": str(scenario["estimate_point"].id),
                "key": 3,
                "value": "Large",
            },
            "cycle": {"id": str(scenario["cycle"].id), "name": "Launch week"},
            "module": [{"id": str(scenario["module"].id), "name": "Agent context"}],
        }

    def test_duplicates_keep_input_order_and_each_result_is_fresh(self, maya_scenario):
        scenario = maya_scenario
        workspace = scenario["workspace"]
        project = scenario["project"]
        work_item = scenario["work_item"]
        entity = _entity(workspace, project, "work_item", work_item.id)
        name = {"kind": "field", "entity": entity, "fieldKey": "name"}
        priority = {"kind": "field", "entity": entity, "fieldKey": "priority"}
        previous_version = work_item.updated_at.isoformat()

        work_item.name = "Launch is ready"
        work_item.priority = "urgent"
        work_item.save()
        items = [
            {"reference": name, "observedEntityVersion": previous_version},
            {"reference": priority},
            {"reference": name, "observedEntityVersion": previous_version},
            {"reference": entity, "observedEntityVersion": previous_version},
        ]

        response = _post(scenario["client"], workspace, items)

        assert response.status_code == status.HTTP_200_OK
        assert [result["reference"] for result in response.data["results"]] == [item["reference"] for item in items]
        assert [result["canonical"]["value"] for result in response.data["results"][:3]] == [
            "Launch is ready",
            "urgent",
            "Launch is ready",
        ]
        assert [result["stale"] for result in response.data["results"]] == [True, False, True, True]
        assert len({result["authorizedAt"] for result in response.data["results"]}) == 1

        current_version = response.data["results"][0]["canonical"]["entityVersion"]
        version_response = _post(
            scenario["client"],
            workspace,
            [
                {"reference": name, "observedEntityVersion": current_version},
                {"reference": name, "observedEntityVersion": "2999-01-01T00:00:00Z"},
            ],
        )
        assert version_response.status_code == status.HTTP_200_OK
        assert [result["stale"] for result in version_response.data["results"]] == [False, True]

    def test_maximum_batch_of_50_preserves_every_duplicate_result(self, maya_scenario):
        scenario = maya_scenario
        reference = _entity(
            scenario["workspace"],
            scenario["project"],
            "project",
            scenario["project"].id,
        )
        items = [{"reference": reference} for _ in range(50)]

        response = _post(scenario["client"], scenario["workspace"], items)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 50
        assert all(result["ok"] for result in response.data["results"])
        assert all(result["reference"] == reference for result in response.data["results"])
        assert all(result["canonical"]["value"]["name"] == "Launch Project" for result in response.data["results"])

# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Semantic, bounded search over Plane objects visible to one caller."""

from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q

from plane.app.permissions import ROLE
from plane.db.models import Cycle, Issue, Module, Page, Project, ProjectMember, Workspace
from plane.db.models.page import ProjectPage


MAX_SEARCH_ITEMS = 20


def _reference(namespace: str, value: Any) -> str:
    return f"{namespace}:{value}"


def _project_membership(user: Any):
    return Q(project__project_projectmember__member=user, project__project_projectmember__is_active=True)


def _work_item_visibility(user: Any):
    """Match Plane's issue endpoint policy, including guest-created-only access."""

    membership = ProjectMember.objects.filter(
        project_id=OuterRef("project_id"),
        member=user,
        is_active=True,
    )
    return (
        Exists(membership.filter(role__gt=ROLE.GUEST.value))
        | Exists(
            membership.filter(
                role=ROLE.GUEST.value,
                project__guest_view_all_features=True,
            )
        )
        | (
            Exists(
                membership.filter(
                    role=ROLE.GUEST.value,
                    project__guest_view_all_features=False,
                )
            )
            & Q(created_by=user)
        )
    )


class WorkspaceSearchService:
    """Search Plane's typed work graph without exposing ORM or API shapes."""

    def search(
        self,
        *,
        workspace: Workspace,
        user: Any,
        query: str,
        limit: int = MAX_SEARCH_ITEMS,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        offset = self._offset(cursor)
        requested_limit = max(1, min(limit, 50))
        # The gateway's result bound is part of the descriptor. Keep the core
        # deliberately small so a large caller limit cannot create a spill.
        page_limit = min(requested_limit, MAX_SEARCH_ITEMS)
        needle = query.strip()
        results: list[dict[str, Any]] = []
        results.extend(self._workspace_results(workspace, needle))
        results.extend(self._project_results(workspace, user, needle))
        results.extend(self._work_item_results(workspace, user, needle))
        results.extend(self._module_results(workspace, user, needle))
        results.extend(self._cycle_results(workspace, user, needle))
        results.extend(self._page_results(workspace, user, needle))
        results.sort(key=lambda item: (item["objectType"], item["title"].casefold(), item["ref"]))
        page = results[offset : offset + page_limit]
        next_cursor = f"cursor:{offset + page_limit}" if offset + page_limit < len(results) else None
        return {"results": page, "nextCursor": next_cursor}

    @staticmethod
    def _offset(cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not isinstance(cursor, str) or not cursor.startswith("cursor:"):
            raise ValueError("search cursor is invalid")
        try:
            offset = int(cursor.removeprefix("cursor:"))
        except ValueError as exc:
            raise ValueError("search cursor is invalid") from exc
        if offset < 0:
            raise ValueError("search cursor is invalid")
        return offset

    @staticmethod
    def _workspace_results(workspace: Workspace, query: str) -> list[dict[str, Any]]:
        if (
            query
            and query.casefold() not in workspace.name.casefold()
            and query.casefold() not in workspace.slug.casefold()
        ):
            return []
        return [
            {
                "objectType": "workspace",
                "ref": _reference("workspace", workspace.id),
                "title": workspace.name,
                "workspaceRef": _reference("workspace", workspace.id),
            }
        ]

    @staticmethod
    def _project_results(workspace: Workspace, user: Any, query: str) -> list[dict[str, Any]]:
        projects = Project.objects.filter(
            workspace=workspace,
            project_projectmember__member=user,
            project_projectmember__is_active=True,
            archived_at__isnull=True,
        ).distinct()
        if query:
            projects = projects.filter(Q(name__icontains=query) | Q(identifier__icontains=query))
        return [
            {
                "objectType": "project",
                "ref": _reference("project", project.id),
                "title": project.name,
                "workspaceRef": _reference("workspace", workspace.id),
            }
            for project in projects.only("id", "name", "identifier").order_by("name", "id")[:MAX_SEARCH_ITEMS]
        ]

    @staticmethod
    def _work_item_results(workspace: Workspace, user: Any, query: str) -> list[dict[str, Any]]:
        issues = Issue.issue_objects.filter(
            _work_item_visibility(user),
            workspace=workspace,
            project__archived_at__isnull=True,
        ).distinct()
        if query:
            issues = issues.filter(
                Q(name__icontains=query) | Q(sequence_id__icontains=query) | Q(project__identifier__icontains=query)
            )
        results = []
        for issue in (
            issues.select_related("project")
            .only("id", "name", "sequence_id", "project_id")
            .order_by("name", "id")[:MAX_SEARCH_ITEMS]
        ):
            read_input = {
                "project_id": str(issue.project_id),
                "issue_id": str(issue.id),
            }
            results.append(
                {
                    "objectType": "work_item",
                    "ref": _reference("work-item", issue.id),
                    "title": issue.name,
                    "workspaceRef": _reference("workspace", workspace.id),
                    "projectRef": _reference("project", issue.project_id),
                    "key": issue.sequence_id,
                    # Preserve the typed search result while providing the exact
                    # canonical input shape for the existing authorized gateway
                    # read. The gateway still re-checks live project membership.
                    "workItemReadInput": read_input,
                    # The model-facing Plane tool is one typed operation envelope.
                    # Return that envelope ready to call so callers never rebuild
                    # an authorization-sensitive target from display references.
                    "workItemReadCall": {
                        "action": "read",
                        "operationRef": "operation:work_item.read",
                        "input": read_input,
                    },
                }
            )
        return results

    @staticmethod
    def _module_results(workspace: Workspace, user: Any, query: str) -> list[dict[str, Any]]:
        modules = Module.objects.filter(
            _project_membership(user),
            workspace=workspace,
            project__archived_at__isnull=True,
            archived_at__isnull=True,
        ).distinct()
        if query:
            modules = modules.filter(Q(name__icontains=query) | Q(project__identifier__icontains=query))
        return [
            {
                "objectType": "module",
                "ref": _reference("module", module.id),
                "title": module.name,
                "workspaceRef": _reference("workspace", workspace.id),
                "projectRef": _reference("project", module.project_id),
            }
            for module in modules.only("id", "name", "project_id").order_by("name", "id")[:MAX_SEARCH_ITEMS]
        ]

    @staticmethod
    def _cycle_results(workspace: Workspace, user: Any, query: str) -> list[dict[str, Any]]:
        cycles = Cycle.objects.filter(
            _project_membership(user),
            workspace=workspace,
            project__archived_at__isnull=True,
            archived_at__isnull=True,
        ).distinct()
        if query:
            cycles = cycles.filter(Q(name__icontains=query) | Q(project__identifier__icontains=query))
        return [
            {
                "objectType": "cycle",
                "ref": _reference("cycle", cycle.id),
                "title": cycle.name,
                "workspaceRef": _reference("workspace", workspace.id),
                "projectRef": _reference("project", cycle.project_id),
            }
            for cycle in cycles.only("id", "name", "project_id").order_by("name", "id")[:MAX_SEARCH_ITEMS]
        ]

    @staticmethod
    def _page_results(workspace: Workspace, user: Any, query: str) -> list[dict[str, Any]]:
        member_project = ProjectMember.objects.filter(
            project_id=OuterRef("project_id"),
            member=user,
            is_active=True,
        )
        linked_project = (
            ProjectPage.objects.filter(
                page_id=OuterRef("pk"),
                deleted_at__isnull=True,
                project__workspace=workspace,
                project__archived_at__isnull=True,
            )
            .annotate(has_member_project=Exists(member_project))
            .filter(has_member_project=True)
        )
        full_feature_member = member_project.filter(
            Q(role__gt=ROLE.GUEST.value) | Q(role=ROLE.GUEST.value, project__guest_view_all_features=True)
        )
        full_feature_project = linked_project.filter(has_member_project=Exists(full_feature_member))
        pages = (
            Page.objects.filter(
                workspace=workspace,
                parent__isnull=True,
                archived_at__isnull=True,
            )
            .annotate(has_member_project=Exists(linked_project), has_full_feature_project=Exists(full_feature_project))
            .filter(has_member_project=True)
            .filter(Q(owned_by=user) | Q(access=Page.PUBLIC_ACCESS, has_full_feature_project=True))
        )
        if query:
            pages = pages.filter(Q(name__icontains=query) | Q(description_stripped__icontains=query))
        return [
            {
                "objectType": "page",
                "ref": _reference("page", page.id),
                "title": page.name,
                "workspaceRef": _reference("workspace", workspace.id),
            }
            for page in pages.distinct().only("id", "name").order_by("name", "id")[:MAX_SEARCH_ITEMS]
        ]

"""Effective MCP manifest: source inventory plus explicit gateway mappings.

The checked-in action rows remain the pinned external inventory.  This module
adds the Plane-specific disposition layer so every supported action has one
explicit operation ID and every unsupported action has a stable, concrete
reason.  No category or name wildcard is used for routing.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any


GATEWAY_OVERRIDES: dict[str, dict[str, Any]] = {
    "get_me": {"operation_id": "user.me", "result_key": "user"},
    "list_work_items": {"operation_id": "work_item.list", "result_key": "work_items"},
    "create_work_item": {"operation_id": "work_item.create", "result_key": "work_item"},
    "retrieve_work_item": {
        "operation_id": "work_item.retrieve",
        "result_key": "work_item",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "update_work_item": {
        "operation_id": "work_item.update",
        "result_key": "work_item",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "delete_work_item": {
        "operation_id": "work_item.delete",
        "result_key": "deleted",
        "result_mode": "none",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "search_work_items": {"operation_id": "work_item.search", "result_key": "issues"},
    "list_work_item_activities": {
        "operation_id": "work_item_activity.list",
        "result_key": "activities",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "retrieve_work_item_activity": {
        "operation_id": "work_item_activity.retrieve",
        "result_key": "activity",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_work_item_relations": {
        "operation_id": "work_item_relation.list",
        "result_key": "relations",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "create_work_item_relation": {
        "operation_id": "work_item_relation.create",
        "result_key": "relations",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "delete_cycle": {"operation_id": "cycle.delete", "result_key": "deleted", "result_mode": "none"},
    "list_cycle_work_items": {"operation_id": "cycle.work_item.list", "result_key": "work_items"},
    "transfer_cycle_work_items": {
        "operation_id": "cycle.transfer",
        "result_key": "message",
        "result_mode": "none",
    },
    "delete_module": {"operation_id": "module.delete", "result_key": "deleted", "result_mode": "none"},
    "list_module_work_items": {"operation_id": "module.work_item.list", "result_key": "work_items"},
    "delete_intake_work_item": {
        "operation_id": "intake.delete",
        "result_key": "deleted",
        "result_mode": "none",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "delete_label": {"operation_id": "label.delete", "result_key": "deleted", "result_mode": "none"},
    "delete_project": {"operation_id": "project.delete", "result_key": "deleted", "result_mode": "none"},
    "delete_state": {"operation_id": "state.delete", "result_key": "deleted", "result_mode": "none"},
    "delete_work_item_comment": {
        "operation_id": "comment.delete",
        "result_key": "deleted",
        "result_mode": "none",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "delete_work_item_link": {
        "operation_id": "link.delete",
        "result_key": "deleted",
        "result_mode": "none",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_work_item_attachments": {"operation_id": "work_item_attachment.list", "result_key": "attachments"},
    "get_work_item_attachment_download_url": {
        "operation_id": "work_item_attachment.download_url",
        "result_key": "attachment",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "upload_work_item_attachment_from_url": {
        "operation_id": "work_item_attachment.upload_from_url",
        "result_key": "attachment",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "delete_work_item_attachment": {
        "operation_id": "work_item_attachment.delete",
        "result_key": "deleted",
        "result_mode": "none",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "read_work_item_attachment": {
        "operation_id": "work_item_attachment.read",
        "result_key": "attachment_read",
        "result_mode": "content",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_cycles": {"operation_id": "cycle.list", "result_key": "cycles"},
    "create_cycle": {"operation_id": "cycle.create", "result_key": "cycle"},
    "retrieve_cycle": {"operation_id": "cycle.retrieve", "result_key": "cycle"},
    "update_cycle": {"operation_id": "cycle.update", "result_key": "cycle"},
    "list_modules": {"operation_id": "module.list", "result_key": "modules"},
    "create_module": {"operation_id": "module.create", "result_key": "module"},
    "retrieve_module": {"operation_id": "module.retrieve", "result_key": "module"},
    "update_module": {"operation_id": "module.update", "result_key": "module"},
    "list_projects": {"operation_id": "project.list", "result_key": "projects"},
    "create_project": {"operation_id": "project.create", "result_key": "project"},
    "retrieve_project": {"operation_id": "project.retrieve", "result_key": "project"},
    "update_project": {"operation_id": "project.update", "result_key": "project"},
    "list_states": {"operation_id": "state.list", "result_key": "states"},
    "create_state": {"operation_id": "state.create", "result_key": "state"},
    "retrieve_state": {"operation_id": "state.retrieve", "result_key": "state"},
    "update_state": {"operation_id": "state.update", "result_key": "state"},
    "list_labels": {"operation_id": "label.list", "result_key": "labels"},
    "create_label": {"operation_id": "label.create", "result_key": "label"},
    "retrieve_label": {"operation_id": "label.retrieve", "result_key": "label"},
    "update_label": {"operation_id": "label.update", "result_key": "label"},
    "list_work_item_links": {
        "operation_id": "link.list",
        "result_key": "links",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "create_work_item_link": {
        "operation_id": "link.create",
        "result_key": "link",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "retrieve_work_item_link": {
        "operation_id": "link.retrieve",
        "result_key": "link",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "update_work_item_link": {
        "operation_id": "link.update",
        "result_key": "link",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_work_item_comments": {
        "operation_id": "comment.list",
        "result_key": "comments",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "create_work_item_comment": {
        "operation_id": "comment.create",
        "result_key": "comment",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "retrieve_work_item_comment": {
        "operation_id": "comment.retrieve",
        "result_key": "comment",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "update_work_item_comment": {
        "operation_id": "comment.update",
        "result_key": "comment",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_intake_work_items": {"operation_id": "intake.list", "result_key": "intake_work_items"},
    "create_intake_work_item": {"operation_id": "intake.create", "result_key": "intake_work_item"},
    "retrieve_intake_work_item": {
        "operation_id": "intake.retrieve",
        "result_key": "intake_work_item",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "update_intake_work_item": {
        "operation_id": "intake.update",
        "result_key": "intake_work_item",
        "input_aliases": {"work_item_id": "issue_id"},
    },
    "list_pages": {"operation_id": "page.list", "result_key": "pages"},
    "retrieve_page": {"operation_id": "page.retrieve", "result_key": "page"},
    "create_page": {"operation_id": "page.create", "result_key": "page"},
    "get_project_members": {"operation_id": "project_member.list", "result_key": "members"},
    "get_workspace_members": {"operation_id": "workspace_member.list", "result_key": "members"},
    # Native Plane breadth operations.  Each public action keeps a distinct
    # operation ID even where the adapter shares one typed implementation.
    "manage_cycle_work_items": {
        "operation_id": "cycle.work_item.manage",
        "result_key": "cycle_work_items",
        "result_mode": "none",
    },
    "manage_cycle_archive": {"operation_id": "cycle.archive", "result_key": "archived"},
    "complete_cycle": {"operation_id": "cycle.complete", "result_key": "cycle"},
    "manage_module_work_items": {
        "operation_id": "module.work_item.manage",
        "result_key": "module_work_items",
        "result_mode": "none",
    },
    "manage_module_archive": {
        "operation_id": "module.archive",
        "result_key": "module",
        "result_mode": "none",
    },
    "manage_project_archive": {
        "operation_id": "project.archive",
        "result_key": "project",
        "result_mode": "none",
    },
    "update_project_features": {"operation_id": "project.features.update", "result_key": "project"},
    "get_project_estimate": {"operation_id": "project.estimate.retrieve", "result_key": "estimate"},
    "list_project_estimate_points": {"operation_id": "project.estimate.points.list", "result_key": "points"},
    "create_project_estimate": {"operation_id": "project.estimate.create", "result_key": "estimate"},
    "update_project_estimate": {"operation_id": "project.estimate.update", "result_key": "estimate"},
    "delete_project_estimate": {
        "operation_id": "project.estimate.delete",
        "result_key": "deleted",
        "result_mode": "none",
    },
    "link_estimate_to_project": {"operation_id": "project.estimate.link", "result_key": "project"},
    "create_project_estimate_points": {
        "operation_id": "project.estimate.points.create",
        "result_key": "points",
    },
    "update_project_estimate_point": {
        "operation_id": "project.estimate.point.update",
        "result_key": "point",
    },
    "delete_project_estimate_point": {
        "operation_id": "project.estimate.point.delete",
        "result_key": "deleted",
        "result_mode": "none",
    },
    "retrieve_work_item_by_identifier": {
        "operation_id": "work_item.identifier.retrieve",
        "result_key": "work_item",
    },
    "manage_work_item_assignee": {"operation_id": "work_item.assignee.manage", "result_key": "work_item"},
    "manage_work_item_label": {"operation_id": "work_item.label.manage", "result_key": "work_item"},
    "list_archived_work_items": {"operation_id": "work_item.archive.list", "result_key": "work_items"},
    "manage_work_item_archive": {
        "operation_id": "work_item.archive",
        "result_key": "work_item",
        "result_mode": "none",
    },
    "remove_work_item_relation": {
        "operation_id": "work_item_relation.remove",
        "result_key": "removed",
        "result_mode": "none",
    },
}


UNSUPPORTED_REASONS: dict[str, tuple[str, str]] = {
    "customers.base": (
        "CUSTOMER_DOMAIN_ADAPTER_UNAVAILABLE",
        "Plane has no safe reusable customer application service in this commit.",
    ),
    "customers.properties": (
        "CUSTOMER_PROPERTY_ADAPTER_UNAVAILABLE",
        "Customer property semantics require the unavailable customer domain adapter.",
    ),
    "customers.property_values": (
        "CUSTOMER_PROPERTY_VALUE_ADAPTER_UNAVAILABLE",
        "Customer property-value mutations require the unavailable customer domain adapter.",
    ),
    "customers.requests": (
        "CUSTOMER_REQUEST_ADAPTER_UNAVAILABLE",
        "Customer request semantics require the unavailable customer domain adapter.",
    ),
    "customers.work_items": (
        "CUSTOMER_WORK_ITEM_ADAPTER_UNAVAILABLE",
        "Customer-scoped work-item semantics are not safely reusable from this commit.",
    ),
    "initiatives": (
        "INITIATIVE_DOMAIN_ADAPTER_UNAVAILABLE",
        "Plane has no safe reusable initiative application service in this commit.",
    ),
    "milestones": (
        "MILESTONE_DOMAIN_ADAPTER_UNAVAILABLE",
        "Plane has no safe reusable milestone application service in this commit.",
    ),
    "releases.base": (
        "RELEASE_DOMAIN_ADAPTER_UNAVAILABLE",
        "Plane has no safe reusable release application service in this commit.",
    ),
    "releases.changelog": (
        "RELEASE_CHANGELOG_ADAPTER_UNAVAILABLE",
        "Release changelog semantics require a release application adapter.",
    ),
    "releases.labels": (
        "RELEASE_LABEL_ADAPTER_UNAVAILABLE",
        "Release label semantics require a release application adapter.",
    ),
    "releases.tags": (
        "RELEASE_TAG_ADAPTER_UNAVAILABLE",
        "Release tag semantics require a release application adapter.",
    ),
    "releases.work_items": (
        "RELEASE_WORK_ITEM_ADAPTER_UNAVAILABLE",
        "Release-scoped work-item semantics require a release application adapter.",
    ),
    "pql": (
        "PQL_QUERY_ADAPTER_UNAVAILABLE",
        "PQL execution requires a bounded query application service not present in this seam.",
    ),
    "work_item_activities": (
        "ACTIVITY_PROJECTION_NOT_MUTATION_SAFE",
        "Activity history is a derived projection and is not exposed as a gateway mutation family.",
    ),
    "work_item_properties": (
        "WORK_ITEM_PROPERTY_ADAPTER_UNAVAILABLE",
        "Work-item property semantics require relationship-aware application services.",
    ),
    "work_item_relation_definitions": (
        "RELATION_DEFINITION_ADAPTER_UNAVAILABLE",
        "Relation-definition semantics require relationship-aware application services.",
    ),
    "work_item_relations": (
        "RELATION_ADAPTER_UNAVAILABLE",
        "Work-item relation semantics require relationship-aware application services.",
    ),
    "work_item_types": (
        "WORK_ITEM_TYPE_ADAPTER_UNAVAILABLE",
        "Work-item type semantics require project configuration application services.",
    ),
    "work_logs": (
        "WORK_LOG_ADAPTER_UNAVAILABLE",
        "Work-log semantics require a dedicated time-tracking application service.",
    ),
    "roles": (
        "ROLE_DEFINITION_NOT_CALLER_MUTABLE",
        "Role definitions are administrative configuration and have no caller-safe gateway service.",
    ),
    "workspaces": (
        "WORKSPACE_CONTROL_ADAPTER_UNAVAILABLE",
        "Workspace settings and feature mutations require a workspace-control application service.",
    ),
}


UNSUPPORTED_EVIDENCE: dict[str, tuple[str, str]] = {
    "customers": (
        "No Customer model is present under apps/api/plane/db/models and no customer route is present "
        "under apps/api/plane/api/urls.",
        "The Plane edition has no customer domain persistence or application service to authorize and reconcile.",
    ),
    "initiatives": (
        "No Initiative model is present under apps/api/plane/db/models and no initiative route is present "
        "under apps/api/plane/api/urls.",
        "The Plane edition has no initiative domain persistence or application service.",
    ),
    "milestones": (
        "No Milestone model is present under apps/api/plane/db/models and no milestone route is present "
        "under apps/api/plane/api/urls.",
        "The Plane edition has no milestone domain persistence or application service.",
    ),
    "releases": (
        "No Release model is present under apps/api/plane/db/models and no release route is present "
        "under apps/api/plane/api/urls.",
        "The Plane edition has no release domain persistence or application service.",
    ),
    "work_item_properties": (
        "No typed work-item property model or route is present under apps/api/plane/db/models or "
        "apps/api/plane/api/urls; Issue.properties is only an untyped JSON field.",
        "An untyped JSON field cannot provide the requested property schema, relationship validation, "
        "option lifecycle, and caller-bound reconciliation.",
    ),
    "work_item_relation_definitions": (
        "No work-item relation-definition model or route is present under apps/api/plane/db/models or "
        "apps/api/plane/api/urls.",
        "IssueRelation stores only the fixed relation choices and cannot represent caller-defined relation "
        "definitions.",
    ),
    "work_item_types": (
        "No public work-item type application route is present under apps/api/plane/api/urls; the internal "
        "IssueType model is not exposed by a caller-bound gateway service.",
        "The internal type relation lacks the required project import and lifecycle application service.",
    ),
    "work_logs": (
        "No work-log model or work-log route is present under apps/api/plane/db/models or apps/api/plane/api/urls.",
        "The exporter label issue_worklogs is not a time-tracking persistence or mutation service.",
    ),
    "roles": (
        "No caller-scoped role definition route is present under apps/api/plane/api/urls; Plane permissions "
        "expose fixed role constants instead.",
        "Role definitions are administrative configuration and cannot be safely projected as caller-mutable "
        "semantic actions.",
    ),
    "workspaces": (
        "Workspace.explored_features is stored state, but no workspace feature application route is present "
        "under apps/api/plane/api/urls.",
        "Stored feature JSON without a workspace-control service cannot provide live authorization and safe "
        "reconciliation.",
    ),
}


UNSUPPORTED_ACTION_EVIDENCE: dict[str, tuple[str, str]] = {
    "get_project_worklog_summary": (
        "No project work-log model, query service, or route is present under apps/api/plane/db/models or "
        "apps/api/plane/api/urls.",
        "A summary cannot be derived from exporter metadata without inventing time-tracking semantics.",
    ),
    "attach_page_to_work_item": (
        "Page has a ProjectPage through-model but no WorkItemPage relation model or route is present under "
        "apps/api/plane/db/models or apps/api/plane/api/urls.",
        "Project page membership cannot be used to claim work-item page attachment semantics.",
    ),
    "list_work_item_pages": (
        "Page has a ProjectPage through-model but no WorkItemPage relation model or route is present under "
        "apps/api/plane/db/models or apps/api/plane/api/urls.",
        "There is no exact work-item/page relation to authorize, list, or audit.",
    ),
    "detach_page_from_work_item": (
        "Page has a ProjectPage through-model but no WorkItemPage relation model or route is present under "
        "apps/api/plane/db/models or apps/api/plane/api/urls.",
        "There is no exact work-item/page relation to detach or reconcile.",
    ),
    "count_work_items": (
        "The Plane operation catalog explicitly rejects PQL input and no PQL execution service is present in "
        "apps/api/plane.",
        "Counting with arbitrary PQL would bypass the bounded typed query contract.",
    ),
}


def _unsupported_reason(action: dict[str, Any]) -> tuple[str, str, str, str]:
    category_code, category_reason = UNSUPPORTED_REASONS.get(
        action["category"],
        (
            f"{action['category'].upper().replace('.', '_')}_ADAPTER_UNAVAILABLE",
            f"No safe reusable {action['category']} application adapter is registered in this commit.",
        ),
    )
    action_slug = re.sub(r"[^A-Z0-9]+", "_", action["name"].upper()).strip("_")
    action_code = f"{category_code}_{action_slug}_DEFERRED"
    if len(action_code) > 64:
        action_code = f"{category_code[:48]}_{hashlib.sha256(action['name'].encode()).hexdigest()[:12]}"
    evidence = UNSUPPORTED_ACTION_EVIDENCE.get(action["name"])
    if evidence is None:
        evidence = UNSUPPORTED_EVIDENCE.get(
            action["category"].split(".", 1)[0],
            (
                "No exact domain model, route, or application service for this action is present in the Plane edition.",
                "Adding a guessed adapter would bypass the edition's typed authorization and reconciliation "
                "boundaries.",
            ),
        )
    reason = f"Public action {action['name']} is durably unsupported: {category_reason} {evidence[0]}"
    return action_code.replace("_DEFERRED", "_UNSUPPORTED"), reason, evidence[1], evidence[0]


def effective_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply exact supported mappings and concrete fail-closed dispositions."""

    manifest = deepcopy(raw)
    overrides = raw.get("gateway_overrides") or GATEWAY_OVERRIDES
    if overrides != GATEWAY_OVERRIDES:
        raise ValueError("The manifest JSON gateway overlay does not match the typed mapping source")
    manifest["gateway_overrides"] = deepcopy(overrides)
    seen = set()
    for action in manifest.get("actions", []):
        name = action["name"]
        if name in overrides:
            override = overrides[name]
            action.update(
                {
                    "gateway_status": "supported",
                    "gateway_operation_id": override["operation_id"],
                    "mapping_kind": "semantic_gateway_operation_exact_v1",
                    "rationale_code": "SEMANTIC_GATEWAY_OPERATION_EXACT",
                    "rationale": f"Explicitly mapped to the typed Plane operation {override['operation_id']}.",
                    "blocker": None,
                }
            )
            seen.add(name)
            continue
        if action["gateway_status"] == "supported":
            raise ValueError(f"Manifest action {name!r} is supported without an exact override")
        if action["gateway_status"] == "deferred":
            code, reason, invariant, api_absence = _unsupported_reason(action)
            action["disposition"] = "MCP-D-004"
            action["adapter"] = "unsupported"
            action["gateway_status"] = "unsupported"
            action["mapping_kind"] = "durable_unsupported_exact_v1"
            action["rationale_code"] = code
            action["rationale"] = reason
            action["blocker"] = {
                **(action.get("blocker") or {}),
                "code": code,
                "action": name,
                "reason": reason,
                "invariant": invariant,
                "api_absence": api_absence,
                "required_semantic_shape": {
                    "category": action["category"],
                    "behavior": action["behavior"],
                    "mutation": action["mutation"],
                    "signature": action["signature"],
                    "return_annotation": action["return_annotation"],
                    "sdk_entrypoints": action.get("sdk_entrypoints", []),
                },
                "blocked_capabilities": (
                    [
                        "live_gateway_authorization",
                        "gateway_idempotency_reconciliation",
                        "append_only_audit",
                    ]
                    if action["mutation"]
                    else [
                        "live_gateway_authorization",
                        "bounded_read_result",
                        "append_only_audit_attribution",
                    ]
                ),
                "public_contract_risk": "unsupported_until_the_cited_edition_invariant_changes",
            }
    missing = set(overrides) - seen
    if missing:
        raise ValueError(f"Gateway overrides name actions absent from manifest: {sorted(missing)}")
    return manifest

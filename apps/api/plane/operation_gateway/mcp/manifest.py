"""Effective MCP manifest: source inventory plus explicit gateway mappings.

The checked-in action rows remain the pinned external inventory.  This module
adds the Plane-specific disposition layer so every supported action has one
explicit operation ID and every unsupported action has a stable, concrete
reason.  No category or name wildcard is used for routing.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


GATEWAY_OVERRIDES: dict[str, dict[str, Any]] = {
    "get_me": {"operation_id": "user.me", "result_key": "user"},
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
    "retrieve_intake_work_item": {"operation_id": "intake.retrieve", "result_key": "intake_work_item"},
    "update_intake_work_item": {"operation_id": "intake.update", "result_key": "intake_work_item"},
    "list_pages": {"operation_id": "page.list", "result_key": "pages"},
    "retrieve_page": {"operation_id": "page.retrieve", "result_key": "page"},
    "create_page": {"operation_id": "page.create", "result_key": "page"},
    "get_project_members": {"operation_id": "project_member.list", "result_key": "members"},
    "get_workspace_members": {"operation_id": "workspace_member.list", "result_key": "members"},
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


def _unsupported_reason(action: dict[str, Any]) -> tuple[str, str]:
    return UNSUPPORTED_REASONS.get(
        action["category"],
        (
            f"{action['category'].upper().replace('.', '_')}_ADAPTER_UNAVAILABLE",
            f"No safe reusable {action['category']} application adapter is registered in this commit.",
        ),
    )


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
            code, reason = _unsupported_reason(action)
            action["rationale_code"] = code
            action["rationale"] = reason
            action["blocker"] = {
                **(action.get("blocker") or {}),
                "code": code,
                "action": name,
                "reason": reason,
                "required_semantic_shape": {
                    "category": action["category"],
                    "behavior": action["behavior"],
                    "mutation": action["mutation"],
                    "signature": action["signature"],
                    "return_annotation": action["return_annotation"],
                    "sdk_entrypoints": action.get("sdk_entrypoints", []),
                },
                "blocked_capabilities": [
                    "live_gateway_authorization",
                    "gateway_idempotency_reconciliation",
                    "append_only_audit",
                ],
                "public_contract_risk": "none_until_an_exact_semantic_operation_and_contract_adapter_is_approved",
            }
    missing = set(overrides) - seen
    if missing:
        raise ValueError(f"Gateway overrides name actions absent from manifest: {sorted(missing)}")
    return manifest

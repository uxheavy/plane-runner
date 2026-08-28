# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from pathlib import Path

import pytest

from plane.operation_gateway.mcp import (
    MCP_ACTIONS,
    MCP_COMPATIBILITY_MANIFEST,
    MCPCompatibilityError,
    gateway_operation_for,
    require_gateway_operation,
)
from plane.operation_gateway.catalog import IMPLEMENTED_OPERATION_IDS, OPERATION_CATALOG
from plane.operation_gateway.contracts import GatewayOperationInputSerializer


@pytest.mark.contract
def test_mcp_manifest_classifies_each_public_action_once():
    assert MCP_COMPATIBILITY_MANIFEST["source"] == {
        "repository": "https://github.com/makeplane/plane-mcp-server",
        "commit": "96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1",
        "version": "0.2.11",
        "inventory_digest": "2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1",
    }
    assert len({action.name for action in MCP_ACTIONS}) == len(MCP_ACTIONS)
    supported_names = {action.name for action in MCP_ACTIONS if action.gateway_status == "supported"}
    assert supported_names == set(MCP_COMPATIBILITY_MANIFEST["gateway_overrides"])
    for action in MCP_ACTIONS:
        assert (action.gateway_status, action.disposition) in {
            ("supported", "MCP-D-001"),
            ("supported", "MCP-D-003"),
            ("local_only", "MCP-D-002"),
            ("unsupported", "MCP-D-004"),
        }


@pytest.mark.contract
def test_gateway_lookup_is_explicit_and_fail_closed():
    assert gateway_operation_for("get_me") == "user.me"
    assert gateway_operation_for("list_work_item_attachments") == "work_item_attachment.list"
    assert gateway_operation_for("retrieve_work_item") == "work_item.retrieve"
    assert require_gateway_operation("retrieve_work_item") == "work_item.retrieve"

    with pytest.raises(MCPCompatibilityError) as unknown:
        gateway_operation_for("not_a_public_plane_tool")
    assert unknown.value.code == "MCP_ACTION_NOT_INVENTORY"

    with pytest.raises(MCPCompatibilityError) as unsupported:
        require_gateway_operation("list_work_item_properties")
    assert unsupported.value.code == "MCP_ACTION_UNSUPPORTED"

    with pytest.raises(MCPCompatibilityError) as local:
        require_gateway_operation("get_pql_reference")
    assert local.value.code == "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE"


@pytest.mark.contract
def test_every_supported_action_reaches_an_explicit_executable_operation():
    supported = [action for action in MCP_ACTIONS if action.gateway_status == "supported"]
    assert supported
    assert all(action.gateway_operation_id in IMPLEMENTED_OPERATION_IDS for action in supported)
    assert all(action.mapping_kind == "semantic_gateway_operation_exact_v1" for action in supported)
    assert all(action.name in MCP_COMPATIBILITY_MANIFEST["gateway_overrides"] for action in supported)
    assert len({(action.name, action.gateway_operation_id) for action in supported}) == len(supported)


@pytest.mark.contract
def test_proven_live_action_families_have_one_explicit_operation_mapping():
    expected = {
        "list_work_items": "work_item.list",
        "create_work_item": "work_item.create",
        "retrieve_work_item": "work_item.retrieve",
        "update_work_item": "work_item.update",
        "delete_work_item": "work_item.delete",
        "search_work_items": "work_item.search",
        "list_work_item_activities": "work_item_activity.list",
        "retrieve_work_item_activity": "work_item_activity.retrieve",
        "list_work_item_relations": "work_item_relation.list",
        "create_work_item_relation": "work_item_relation.create",
        "delete_cycle": "cycle.delete",
        "list_cycle_work_items": "cycle.work_item.list",
        "transfer_cycle_work_items": "cycle.transfer",
        "delete_module": "module.delete",
        "list_module_work_items": "module.work_item.list",
        "delete_intake_work_item": "intake.delete",
        "delete_label": "label.delete",
        "delete_project": "project.delete",
        "delete_state": "state.delete",
        "delete_work_item_comment": "comment.delete",
        "delete_work_item_link": "link.delete",
    }
    assert {name: gateway_operation_for(name) for name in expected} == expected


@pytest.mark.contract
def test_catalog_input_fields_are_declared_by_the_typed_boundary_serializer():
    declared = set(GatewayOperationInputSerializer().fields)
    assert {
        operation_id: sorted(set(descriptor.input_fields) - declared)
        for operation_id, descriptor in OPERATION_CATALOG.items()
        if set(descriptor.input_fields) - declared
    } == {}


@pytest.mark.contract
def test_gateway_adapters_do_not_dispatch_drf_views_or_loopback_requests():
    operation_gateway_root = Path(__file__).parents[3] / "operation_gateway"
    for relative_path in ("operations.py", "gateway.py", "mcp/attachments.py"):
        source = (operation_gateway_root / relative_path).read_text(encoding="utf-8")
        assert "plane.api.views" not in source
        assert ".as_view(" not in source

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
from plane.operation_gateway.contracts import MAX_RESULT_BYTES, GatewayOperationInputSerializer
from plane.operation_gateway.mcp.adapter_registry import ADAPTER_REGISTRY
from plane.operation_gateway.operations import SPECIAL_GATEWAY_OPERATION_IDS, get_operation_handler


@pytest.mark.contract
def test_mcp_manifest_exhaustively_classifies_the_pinned_public_surface():
    assert MCP_COMPATIBILITY_MANIFEST["source"] == {
        "repository": "https://github.com/makeplane/plane-mcp-server",
        "commit": "96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1",
        "version": "0.2.11",
        "inventory_digest": "2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1",
    }
    assert MCP_COMPATIBILITY_MANIFEST["tool_count"] == 177
    assert len(MCP_ACTIONS) == 177
    assert len({action.name for action in MCP_ACTIONS}) == 177
    supported_names = {action.name for action in MCP_ACTIONS if action.gateway_status == "supported"}
    assert supported_names == set(MCP_COMPATIBILITY_MANIFEST["gateway_overrides"])
    assert sum(action.gateway_status == "supported" for action in MCP_ACTIONS) == 86
    assert sum(action.gateway_status == "unsupported" for action in MCP_ACTIONS) == 90
    assert sum(action.disposition == "MCP-D-002" for action in MCP_ACTIONS) == 1

    for action in MCP_ACTIONS:
        assert action.source_file.startswith("plane_mcp/tools/")
        assert action.source_line > 0
        assert isinstance(action.signature, str)
        assert action.return_annotation
        assert action.preserves
        assert action.rationale_code
        assert action.rationale
        if action.disposition != "MCP-D-002":
            assert action.sdk_entrypoints
        assert "*" not in action.mapping_kind
        assert "sdk_http_intent" not in action.mapping_kind


@pytest.mark.contract
def test_unsupported_actions_cannot_claim_a_gateway_operation():
    for action in MCP_ACTIONS:
        if action.disposition == "MCP-D-002":
            assert action.gateway_status == "local_only"
            assert action.adapter == "local_pql"
            assert action.gateway_operation_id is None
            assert action.behavior == "local_only"
            continue

        if action.gateway_status == "supported":
            assert action.gateway_operation_id
            assert action.blocker is None
            continue

        assert action.gateway_status == "unsupported"
        assert action.disposition == "MCP-D-004"
        assert action.adapter == "unsupported"
        assert action.gateway_operation_id is None
        assert action.blocker["action"] == action.name
        assert action.blocker["code"] != "SEMANTIC_OPERATION_NOT_REGISTERED"
        assert action.blocker["invariant"]
        assert action.blocker["api_absence"]
        assert action.mutation is (action.behavior == "mutation") or action.disposition == "MCP-D-003"
        assert "caller_identity" in action.preserves
        assert "oauth_and_api_key_auth" in action.preserves
        assert "bounded_results" in action.preserves
        assert "audit_attribution" in action.preserves
        if "cursor" in action.signature or "per_page" in action.signature:
            assert "pageable" in action.capabilities
        else:
            assert "pageable" not in action.capabilities


@pytest.mark.contract
def test_gateway_lookup_is_explicit_and_fail_closed():
    assert gateway_operation_for("get_me") == "user.me"
    assert gateway_operation_for("list_work_item_attachments") == "work_item_attachment.list"
    assert gateway_operation_for("retrieve_work_item") == "work_item.retrieve"
    assert require_gateway_operation("retrieve_work_item") == "work_item.retrieve"

    with pytest.raises(MCPCompatibilityError) as unknown:
        gateway_operation_for("not_a_public_plane_tool")
    assert unknown.value.code == "MCP_ACTION_NOT_INVENTORY"


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


@pytest.mark.contract
def test_generated_action_matrix_is_executable():
    rows = ADAPTER_REGISTRY["actions"]
    assert ADAPTER_REGISTRY["source"]["commit"] == "96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1"
    assert ADAPTER_REGISTRY["manifest_digest"] == "1c9964ff9165b528601fb5cb5e98cb68ae70a88865cfefbbf40a7c25a310be06"
    assert ADAPTER_REGISTRY["tool_count"] == len(rows) == 177
    assert len({row["tool_name"] for row in rows}) == 177
    required = {
        "tool_name",
        "registration",
        "disposition",
        "gateway_operation_id",
        "handler",
        "catalog_schema_digest",
        "authorization_service",
        "idempotency_policy",
        "result_limit_bytes",
        "identity_mode",
        "audit_policy",
        "representative_test",
    }
    for row in rows:
        assert required <= row.keys()
        assert 1 <= row["result_limit_bytes"] <= MAX_RESULT_BYTES
        assert row["representative_test"].endswith("test_generated_action_matrix_is_executable")
        if row["registration"] == "gateway":
            assert row["disposition"] in {"MCP-D-001", "MCP-D-003"}
            descriptor = OPERATION_CATALOG[row["gateway_operation_id"]]
            assert row["handler"] == descriptor.handler
            assert row["catalog_schema_digest"] == descriptor.schema_digest
            assert row["authorization_service"] == f"live_{descriptor.authorization_scope}_permission"
            assert row["result_limit_bytes"] == descriptor.max_result_bytes
            assert (
                get_operation_handler(row["gateway_operation_id"]) is not None
                or row["gateway_operation_id"] in SPECIAL_GATEWAY_OPERATION_IDS
            )
            if row["return_annotation"] == "None":
                assert row["result_mode"] == "none"
            else:
                assert row["result_mode"] != "none"
        elif row["registration"] == "unsupported":
            assert row["disposition"] == "MCP-D-004"
            assert row["gateway_operation_id"] is None
            assert row["handler"] is None
            assert row["blocker"]["invariant"]
            assert row["blocker"]["api_absence"]
        else:
            assert row["registration"] == "local"
            assert row["disposition"] == "MCP-D-002"
            assert row["gateway_operation_id"] is None

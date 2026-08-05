from collections import Counter
from pathlib import Path

import pytest

from plane.operation_gateway.mcp import (
    MCP_ACTIONS,
    MCP_COMPATIBILITY_MANIFEST,
    MCPCompatibilityError,
    gateway_operation_for,
    get_mcp_action,
    require_gateway_operation,
)
from plane.operation_gateway.catalog import IMPLEMENTED_OPERATION_IDS, OPERATION_CATALOG
from plane.operation_gateway.contracts import GatewayOperationInputSerializer


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
    assert len(MCP_COMPATIBILITY_MANIFEST["gateway_overrides"]) == 43
    assert Counter(action.disposition for action in MCP_ACTIONS) == Counter(
        {"MCP-D-001": 171, "MCP-D-002": 1, "MCP-D-003": 5}
    )
    assert sum(action.gateway_status == "supported" for action in MCP_ACTIONS) == 43
    assert sum(action.gateway_status == "deferred" for action in MCP_ACTIONS) == 133

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
def test_deferred_actions_cannot_claim_a_gateway_operation():
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

        assert action.gateway_status == "deferred"
        assert action.gateway_operation_id is None
        assert action.blocker["action"] == action.name
        assert action.blocker["code"] != "SEMANTIC_OPERATION_NOT_REGISTERED"
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
    assert get_mcp_action("retrieve_work_item") is not None
    assert gateway_operation_for("retrieve_work_item") is None

    with pytest.raises(MCPCompatibilityError) as deferred:
        require_gateway_operation("retrieve_work_item")
    assert deferred.value.code == "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE"
    assert deferred.value.tool_name == "retrieve_work_item"

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

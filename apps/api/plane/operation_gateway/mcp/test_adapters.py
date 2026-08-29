# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure contract proofs for MCP gateway registrations."""

from __future__ import annotations

import unittest

from .adapter_registry import get_registration
from .attachment_adapter import AttachmentGatewayAdapter, AttachmentImage
from .attachment_policy import (
    AttachmentFailure,
    MAX_IMAGE_READ_BYTES,
    MAX_TEXT_READ_BYTES,
    assert_public_url,
    read_limit,
)
from .compatibility import MCP_ACTIONS, MCP_COMPATIBILITY_MANIFEST
from .sdk_adapter import MCPAdapterError, MCPGatewayExecutionError, SharedSDKGatewayAdapter


class FakeGateway:
    def __init__(self, *, result_by_operation=None, error=None, replayed=False):
        self.calls = []
        self.result_by_operation = result_by_operation or {}
        self.error = error
        self.replayed = replayed

    def execute(self, *, operation_id, input, idempotency_key, correlation_id):
        self.calls.append((operation_id, dict(input), idempotency_key, correlation_id))
        envelope = {
            "schema_version": "plane.operation/v1",
            "operation_id": operation_id,
            "caller": {"type": "user", "id": "caller-1"},
            "audit_receipt": "audit-1",
            "idempotency": {"key": idempotency_key, "replayed": self.replayed},
        }
        if self.error:
            envelope.update({"ok": False, "error": self.error})
        else:
            envelope.update({"ok": True, "result": self.result_by_operation[operation_id]})
        return envelope


class FakeContentReader:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = []

    def read(self, *, url: str, max_bytes: int) -> bytes:
        self.calls.append((url, max_bytes))
        self.asserted_max_bytes = max_bytes
        return self.content


class RuntimeAdapterTests(unittest.TestCase):
    def test_supported_actions_have_exact_runtime_registrations(self):
        actions = {action.name: action for action in MCP_ACTIONS}
        for tool_name, override in MCP_COMPATIBILITY_MANIFEST["gateway_overrides"].items():
            registration = get_registration(tool_name)
            self.assertIsNotNone(registration)
            self.assertEqual(registration.gateway_operation_id, actions[tool_name].gateway_operation_id)
            self.assertEqual(registration.gateway_operation_id, override["operation_id"])

        self.assertIsNone(get_registration("list_work_item_properties"))
        self.assertIsNone(get_registration("get_pql_reference"))
        self.assertIsNone(get_registration("not_a_public_plane_tool"))

    def test_supported_read_and_mutation_use_exact_gateway_operations(self):
        gateway = FakeGateway(
            result_by_operation={
                "user.me": {"user": {"id": "u1"}},
                "work_item_attachment.delete": {"deleted": True},
            }
        )
        adapter = SharedSDKGatewayAdapter(gateway)
        self.assertEqual(
            adapter.invoke("get_me", {}, idempotency_key="k1", correlation_id="c1"),
            {"id": "u1"},
        )
        self.assertIsNone(
            adapter.invoke(
                "delete_work_item_attachment",
                {"project_id": "p1", "work_item_id": "i1", "attachment_id": "a1"},
                idempotency_key="k2",
                correlation_id="c2",
            )
        )
        self.assertEqual(gateway.calls[0][0], "user.me")
        self.assertEqual(gateway.calls[1][0], "work_item_attachment.delete")
        self.assertEqual(gateway.calls[1][1]["issue_id"], "i1")
        self.assertNotIn("caller", gateway.calls[1][1])

    def test_denied_and_replayed_receipts_preserve_gateway_semantics(self):
        denied = FakeGateway(
            error={"code": "NOT_AUTHORIZED", "message": "denied", "retryable": False},
            result_by_operation={},
        )
        with self.assertRaises(MCPGatewayExecutionError) as raised:
            SharedSDKGatewayAdapter(denied).invoke("get_me", {}, idempotency_key="k", correlation_id="c")
        self.assertEqual(raised.exception.code, "NOT_AUTHORIZED")
        replayed = FakeGateway(result_by_operation={"user.me": {"user": {"id": "u1"}}}, replayed=True)
        self.assertEqual(
            SharedSDKGatewayAdapter(replayed).invoke("get_me", {}, idempotency_key="k", correlation_id="c"),
            {"id": "u1"},
        )

    def test_unsupported_and_unknown_actions_fail_closed_with_specific_codes(self):
        gateway = FakeGateway(result_by_operation={"work_item.retrieve": {"work_item": {"id": "i1", "name": "one"}}})
        self.assertEqual(
            SharedSDKGatewayAdapter(gateway).invoke(
                "retrieve_work_item",
                {"project_id": "p1", "work_item_id": "i1"},
                idempotency_key="k",
                correlation_id="c",
            ),
            {"id": "i1", "name": "one"},
        )
        with self.assertRaises(MCPAdapterError) as unsupported:
            SharedSDKGatewayAdapter(FakeGateway()).invoke(
                "list_work_item_properties", {}, idempotency_key="k", correlation_id="c"
            )
        self.assertEqual(unsupported.exception.code, "MCP_ACTION_UNSUPPORTED")
        self.assertIn("WORK_ITEM_PROPERTY", unsupported.exception.message)
        with self.assertRaises(MCPAdapterError) as local:
            SharedSDKGatewayAdapter(FakeGateway()).invoke(
                "get_pql_reference", {}, idempotency_key="k", correlation_id="c"
            )
        self.assertEqual(local.exception.code, "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE")
        with self.assertRaises(MCPAdapterError) as unknown:
            SharedSDKGatewayAdapter(FakeGateway()).invoke(
                "not_a_public_plane_tool", {}, idempotency_key="k", correlation_id="c"
            )
        self.assertEqual(unknown.exception.code, "MCP_ACTION_NOT_INVENTORY")

    def test_attachment_read_preserves_bounded_content_shape(self):
        gateway = FakeGateway(
            result_by_operation={
                "work_item_attachment.read": {
                    "attachment_read": {
                        "download_url": "https://signed.example/a",
                        "content_type": "image/png",
                        "max_bytes": 5 * 1024 * 1024,
                    }
                }
            }
        )
        reader = FakeContentReader(b"png")
        value = AttachmentGatewayAdapter(gateway, reader).invoke(
            "read_work_item_attachment",
            {"project_id": "p1", "work_item_id": "i1", "attachment_id": "a1"},
            idempotency_key="k",
            correlation_id="c",
        )
        self.assertEqual(value, AttachmentImage(content_type="image/png", data=b"png"))
        self.assertEqual(reader.calls, [("https://signed.example/a", 5 * 1024 * 1024)])

    def test_read_pagination_and_result_bounds_are_fail_closed(self):
        registration = get_registration("list_cycles")
        self.assertIsNotNone(registration)
        validator = SharedSDKGatewayAdapter._validate_public_result
        validator(registration, {"results": [1, 2], "next_cursor": "next"}, {"per_page": 2})
        with self.assertRaises(MCPAdapterError) as page_size:
            validator(registration, {"results": []}, {"per_page": 0})
        self.assertEqual(page_size.exception.code, "MCP_PAGE_BOUNDS_INVALID")
        validator(registration, "x" * (registration.result_limit_bytes - 2), {})
        with self.assertRaises(MCPAdapterError) as result_size:
            validator(registration, "x" * (registration.result_limit_bytes - 1), {})
        self.assertEqual(result_size.exception.code, "MCP_GATEWAY_RESULT_TOO_LARGE")

    def test_attachment_source_and_content_bounds_are_enforced(self):
        with self.assertRaises(AttachmentFailure):
            assert_public_url("http://127.0.0.1/internal")
        self.assertEqual(read_limit("image/png"), MAX_IMAGE_READ_BYTES)
        self.assertEqual(read_limit("text/plain"), MAX_TEXT_READ_BYTES)
        with self.assertRaises(AttachmentFailure):
            read_limit("application/zip")


if __name__ == "__main__":
    unittest.main()

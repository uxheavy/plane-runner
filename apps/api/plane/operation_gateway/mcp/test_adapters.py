"""Pure contract proofs for generated MCP gateway registrations."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from .adapter_registry import ADAPTER_REGISTRATIONS
from .attachment_adapter import AttachmentGatewayAdapter, AttachmentImage
from .attachment_policy import (
    AttachmentFailure,
    MAX_IMAGE_READ_BYTES,
    MAX_TEXT_READ_BYTES,
    assert_public_url,
    read_limit,
)
from .registry_generator import build_adapter_registry
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


class GeneratedAdapterTests(unittest.TestCase):
    def test_registry_is_exhaustive_and_matches_the_manifest(self):
        manifest_path = Path(__file__).with_name("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        generated = build_adapter_registry(manifest)
        checked_in = json.loads(Path(__file__).with_name("adapter_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(generated, checked_in)
        self.assertEqual(len(ADAPTER_REGISTRATIONS), 177)
        self.assertEqual(
            {row.registration for row in ADAPTER_REGISTRATIONS},
            {"gateway", "blocked", "local"},
        )
        self.assertEqual(sum(row.registration == "gateway" for row in ADAPTER_REGISTRATIONS), 43)
        self.assertEqual(sum(row.registration == "blocked" for row in ADAPTER_REGISTRATIONS), 133)
        for row in ADAPTER_REGISTRATIONS:
            self.assertEqual(
                row.public_signature, next(a["signature"] for a in manifest["actions"] if a["name"] == row.tool_name)
            )
            if row.registration == "blocked":
                self.assertEqual(row.blocker["action"], row.tool_name)
                self.assertIsNone(row.gateway_operation_id)

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

    def test_deferred_and_unknown_actions_fail_closed_with_specific_codes(self):
        with self.assertRaises(MCPAdapterError) as deferred:
            SharedSDKGatewayAdapter(FakeGateway()).invoke(
                "retrieve_work_item", {}, idempotency_key="k", correlation_id="c"
            )
        self.assertEqual(deferred.exception.code, "MCP_ACTION_GATEWAY_MAPPING_UNAVAILABLE")
        self.assertIn("WORK_ITEM", deferred.exception.message)
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
        registration = next(row for row in ADAPTER_REGISTRATIONS if row.tool_name == "list_customers")
        validator = SharedSDKGatewayAdapter._validate_public_result
        validator(registration, {"results": [1, 2], "next_cursor": "next"}, {"per_page": 2})
        with self.assertRaises(MCPAdapterError) as page_size:
            validator(registration, {"results": []}, {"per_page": 0})
        self.assertEqual(page_size.exception.code, "MCP_PAGE_BOUNDS_INVALID")
        with self.assertRaises(MCPAdapterError) as result_size:
            validator(registration, "x" * (16 * 1024 + 1), {})
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

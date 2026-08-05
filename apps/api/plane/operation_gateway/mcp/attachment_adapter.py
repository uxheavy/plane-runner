"""Typed public-contract adapter for the five donor attachment tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .sdk_adapter import GatewayInvoker, SharedSDKGatewayAdapter


class AttachmentContentReader(Protocol):
    def read(self, *, url: str, max_bytes: int) -> bytes: ...


@dataclass(frozen=True)
class AttachmentImage:
    content_type: str
    data: bytes


class AttachmentGatewayAdapter:
    """Reuse the shared gateway transport and add only content-shape handling."""

    def __init__(self, invoker: GatewayInvoker, content_reader: AttachmentContentReader):
        self._gateway = SharedSDKGatewayAdapter(invoker)
        self._content_reader = content_reader

    def invoke(self, tool_name: str, arguments: dict[str, object], *, idempotency_key: str, correlation_id: str):
        value = self._gateway.invoke(
            tool_name,
            arguments,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        if tool_name != "read_work_item_attachment":
            return value
        if not isinstance(value, dict):
            raise ValueError("The gateway read authorization result is invalid")
        content = self._content_reader.read(url=str(value["download_url"]), max_bytes=int(value["max_bytes"]))
        content_type = str(value["content_type"])
        if content_type.startswith("image/"):
            return AttachmentImage(content_type=content_type, data=content)
        return content.decode("utf-8")

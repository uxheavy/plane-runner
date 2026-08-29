# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Dependency-free attachment transfer and content-boundary policy."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_READ_BYTES = 5 * 1024 * 1024
MAX_TEXT_READ_BYTES = 1 * 1024 * 1024

READABLE_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
READABLE_TEXT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/xml",
        "text/yaml",
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
    }
)

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


class AttachmentFailure(Exception):
    """A bounded semantic attachment failure safe for gateway translation."""

    def __init__(self, code: str, http_status: int = 400, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise AttachmentFailure("EXTERNAL_SOURCE_REJECTED", 400)
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)}
    except (OSError, socket.gaierror):
        raise AttachmentFailure("EXTERNAL_SOURCE_REJECTED", 400) from None
    for value in addresses:
        address = ipaddress.ip_address(value)
        if any(address in network for network in _PRIVATE_NETWORKS) or address.is_private or address.is_loopback:
            raise AttachmentFailure("EXTERNAL_SOURCE_REJECTED", 400)


def read_limit(content_type: str) -> int:
    if content_type in READABLE_IMAGE_TYPES:
        return MAX_IMAGE_READ_BYTES
    if content_type in READABLE_TEXT_TYPES:
        return MAX_TEXT_READ_BYTES
    raise AttachmentFailure("ATTACHMENT_CONTENT_UNSUPPORTED", 400)

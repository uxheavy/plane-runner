# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib

import pytest

from plane.bgtasks.webhook_task import (
    WEBHOOK_RESPONSE_BODY_LIMIT,
    WebhookResponseReadError,
    read_bounded_webhook_response,
)


class StreamResponse:
    def __init__(self, chunks, headers=None, error=None, expected_chunk_size=None):
        self.chunks = chunks
        self.headers = headers or {}
        self.error = error
        self.expected_chunk_size = expected_chunk_size
        self.closed = False

    def iter_content(self, chunk_size):
        if self.expected_chunk_size is not None:
            assert chunk_size == self.expected_chunk_size
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error

    def close(self):
        self.closed = True

    @property
    def content(self):
        raise AssertionError("full response content must not be read")

    @property
    def text(self):
        raise AssertionError("full response text must not be read")


@pytest.mark.unit
def test_exact_limit_is_bounded_and_not_truncated_when_stream_ends():
    response = StreamResponse([b"a" * WEBHOOK_RESPONSE_BODY_LIMIT])

    evidence = read_bounded_webhook_response(response)
    response.close()

    assert evidence.prefix.encode() == b"a" * WEBHOOK_RESPONSE_BODY_LIMIT
    assert evidence.observed_size == WEBHOOK_RESPONSE_BODY_LIMIT
    assert evidence.size_known is True
    assert evidence.truncated is False
    assert evidence.prefix_sha256 == hashlib.sha256(b"a" * WEBHOOK_RESPONSE_BODY_LIMIT).hexdigest()
    assert len(evidence.prefix.encode()) <= WEBHOOK_RESPONSE_BODY_LIMIT
    assert response.closed is True


@pytest.mark.unit
def test_one_extra_byte_is_observed_but_not_retained():
    response = StreamResponse([b"a" * WEBHOOK_RESPONSE_BODY_LIMIT, b"b"])

    evidence = read_bounded_webhook_response(response)

    assert evidence.prefix == "a" * WEBHOOK_RESPONSE_BODY_LIMIT
    assert evidence.observed_size == WEBHOOK_RESPONSE_BODY_LIMIT + 1
    assert evidence.size_known is False
    assert evidence.truncated is True
    assert len(evidence.prefix.encode()) == WEBHOOK_RESPONSE_BODY_LIMIT


@pytest.mark.unit
def test_content_length_large_stream_stops_at_configured_limit():
    response = StreamResponse(
        [b"z" * (1024 * 1024)],
        headers={"Content-Length": str(1024 * 1024)},
    )

    evidence = read_bounded_webhook_response(response)

    assert evidence.prefix == "z" * WEBHOOK_RESPONSE_BODY_LIMIT
    assert evidence.observed_size == WEBHOOK_RESPONSE_BODY_LIMIT + 1
    assert evidence.size_known is False
    assert evidence.truncated is True
    assert len(evidence.prefix.encode()) == WEBHOOK_RESPONSE_BODY_LIMIT


@pytest.mark.unit
def test_multibyte_boundary_does_not_exceed_byte_limit():
    response = StreamResponse(["ab€".encode("utf-8")])

    evidence = read_bounded_webhook_response(response, limit=4)

    assert evidence.prefix == "ab"
    assert len(evidence.prefix.encode("utf-8")) <= 4
    assert evidence.truncated is True


@pytest.mark.unit
def test_sensitive_response_values_are_redacted_before_storage():
    response = StreamResponse([b'{"token":"do-not-store","message":"ok"}'])

    evidence = read_bounded_webhook_response(response)

    assert "do-not-store" not in evidence.prefix
    assert "[REDACTED]" in evidence.prefix


@pytest.mark.unit
def test_stream_exception_keeps_bounded_evidence_and_marks_truncation():
    response = StreamResponse([b"prefix"], error=RuntimeError("response body exploded"))

    with pytest.raises(WebhookResponseReadError) as caught:
        read_bounded_webhook_response(response)

    evidence = caught.value.evidence
    assert evidence.prefix == "prefix"
    assert evidence.observed_size == len(b"prefix")
    assert evidence.size_known is False
    assert evidence.truncated is True
    assert evidence.prefix_sha256 == hashlib.sha256(b"prefix").hexdigest()


@pytest.mark.unit
def test_declared_short_length_does_not_hide_observed_extra_bytes():
    response = StreamResponse([b"a" * (WEBHOOK_RESPONSE_BODY_LIMIT + 1)], headers={"Content-Length": "1"})

    evidence = read_bounded_webhook_response(response)

    assert evidence.observed_size == WEBHOOK_RESPONSE_BODY_LIMIT + 1
    assert evidence.size_known is False
    assert evidence.truncated is True


@pytest.mark.unit
def test_declared_long_length_does_not_claim_a_short_stream_is_truncated():
    response = StreamResponse([b"short"], headers={"Content-Length": "999999"})

    evidence = read_bounded_webhook_response(response)

    assert evidence.observed_size == len(b"short")
    assert evidence.size_known is True
    assert evidence.truncated is False


@pytest.mark.unit
def test_chunked_multibyte_and_plain_sensitive_values_are_bounded_and_redacted():
    json_response = StreamResponse([b'{"password":"multi word secret","safe":"ok"}'])
    form_response = StreamResponse([b"token=multi word secret&safe=ok"])
    plain_response = StreamResponse([b"Authorization: Bearer multi word secret"])

    json_evidence = read_bounded_webhook_response(json_response)
    form_evidence = read_bounded_webhook_response(form_response)
    plain_evidence = read_bounded_webhook_response(plain_response)

    for evidence in (json_evidence, form_evidence, plain_evidence):
        assert "multi word secret" not in evidence.prefix
        assert "[REDACTED]" in evidence.prefix
        assert len(evidence.prefix.encode()) <= WEBHOOK_RESPONSE_BODY_LIMIT

"""Unit tests for src/security/watermark/extractor.py.

Tests WatermarkExtractor using a mocked WatermarkService to isolate
the extractor logic from the database layer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.security.watermark.extractor import _HTML_WATERMARK_PATTERN, WatermarkExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET_KEY = b"test-secret-key-for-unit-tests"
_PAYLOAD_DELIMITER = "|"


def _make_valid_encoded(
    user_id: uuid.UUID | None = None,
    export_id: uuid.UUID | None = None,
    timestamp: datetime | None = None,
    secret: bytes = _SECRET_KEY,
) -> str:
    """Build a correctly HMAC-signed base64 watermark payload."""
    uid = user_id or uuid.uuid4()
    eid = export_id or uuid.uuid4()
    ts = timestamp or datetime.now(UTC)
    payload = _PAYLOAD_DELIMITER.join([str(uid), str(eid), ts.isoformat()])
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    signed = f"{payload}{_PAYLOAD_DELIMITER}{sig}"
    return base64.b64encode(signed.encode("utf-8")).decode("ascii")


def _make_extractor(
    decode_return: dict[str, Any] | None,
    lookup_return: Any = None,
) -> WatermarkExtractor:
    """Build a WatermarkExtractor with a mocked WatermarkService."""
    mock_session = MagicMock()
    extractor = WatermarkExtractor.__new__(WatermarkExtractor)
    extractor._session = mock_session

    mock_service = MagicMock()
    mock_service.decode_invisible_watermark.return_value = decode_return
    mock_service.lookup_by_export_id = AsyncMock(return_value=lookup_return)
    extractor._service = mock_service

    return extractor


# ---------------------------------------------------------------------------
# extract_from_encoded — valid watermark roundtrip
# ---------------------------------------------------------------------------


class TestExtractFromEncodedValid:
    """Valid watermark should return decoded payload + export log."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_valid_watermark(self) -> None:
        export_id = uuid.uuid4()
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": str(export_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        log_entry = {"id": str(export_id), "document_type": "pdf"}
        extractor = _make_extractor(decoded_payload, log_entry)

        result = await extractor.extract_from_encoded("any-encoded-string")

        assert result is not None
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_watermark_payload_present_in_result(self) -> None:
        export_id = uuid.uuid4()
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": str(export_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decoded_payload, {"id": str(export_id)})

        result = await extractor.extract_from_encoded("any-encoded-string")

        assert result is not None
        assert result["watermark"] == decoded_payload

    @pytest.mark.asyncio
    async def test_export_log_present_in_result(self) -> None:
        export_id = uuid.uuid4()
        log_entry = {"id": str(export_id), "document_type": "html"}
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": str(export_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decoded_payload, log_entry)

        result = await extractor.extract_from_encoded("any-encoded-string")

        assert result is not None
        assert result["export_log"] == log_entry

    @pytest.mark.asyncio
    async def test_lookup_called_with_correct_uuid(self) -> None:
        export_id = uuid.uuid4()
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": str(export_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decoded_payload)

        await extractor.extract_from_encoded("any-encoded-string")

        extractor._service.lookup_by_export_id.assert_awaited_once_with(export_id)


# ---------------------------------------------------------------------------
# extract_from_encoded — tampered / invalid inputs
# ---------------------------------------------------------------------------


class TestExtractFromEncodedTampered:
    """Tampered or invalid payloads should return None."""

    @pytest.mark.asyncio
    async def test_returns_none_when_service_decode_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        result = await extractor.extract_from_encoded("garbage")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_export_id_missing_from_payload(self) -> None:
        # decode succeeds but the payload has no export_id field
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decode_return=decoded_payload)

        result = await extractor.extract_from_encoded("valid-looking-encoded")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_export_id_is_empty_string(self) -> None:
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": "",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decode_return=decoded_payload)

        result = await extractor.extract_from_encoded("encoded-with-empty-export-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_export_id_is_invalid_uuid(self) -> None:
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": "not-a-valid-uuid",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decode_return=decoded_payload)

        result = await extractor.extract_from_encoded("encoded-with-bad-uuid")

        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_not_called_on_invalid_export_id(self) -> None:
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": "totally-not-a-uuid",
            "timestamp": "irrelevant",
        }
        extractor = _make_extractor(decode_return=decoded_payload)

        await extractor.extract_from_encoded("encoded")

        extractor._service.lookup_by_export_id.assert_not_awaited()


# ---------------------------------------------------------------------------
# extract_from_encoded — truncated / malformed inputs
# ---------------------------------------------------------------------------


class TestExtractFromEncodedMalformed:
    """Malformed encoded strings should be gracefully rejected."""

    @pytest.mark.asyncio
    async def test_empty_string_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        result = await extractor.extract_from_encoded("")
        assert result is None

    @pytest.mark.asyncio
    async def test_random_bytes_encoded_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        result = await extractor.extract_from_encoded("YWJjZGVm")  # base64 of 'abcdef'
        assert result is None

    @pytest.mark.asyncio
    async def test_non_base64_string_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        result = await extractor.extract_from_encoded("!!!not-base64!!!")
        assert result is None


# ---------------------------------------------------------------------------
# extract_from_html
# ---------------------------------------------------------------------------


class TestExtractFromHtml:
    """HTML extraction should parse the meta tag and delegate to extract_from_encoded."""

    @pytest.mark.asyncio
    async def test_no_meta_tag_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        html = "<html><head><title>Test</title></head><body></body></html>"
        result = await extractor.extract_from_html(html)
        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_from_valid_meta_tag(self) -> None:
        export_id = uuid.uuid4()
        decoded_payload = {
            "user_id": str(uuid.uuid4()),
            "export_id": str(export_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        extractor = _make_extractor(decoded_payload, {"id": str(export_id)})

        encoded = "ZW5jb2RlZC13YXRlcm1hcms="  # arbitrary placeholder
        html = f'<html><head><meta name="kmflow-watermark" content="{encoded}"></head></html>'

        await extractor.extract_from_html(html)

        # extract_from_encoded was called — service.decode_invisible_watermark should be invoked
        extractor._service.decode_invisible_watermark.assert_called_once_with(encoded)

    @pytest.mark.asyncio
    async def test_empty_html_returns_none(self) -> None:
        extractor = _make_extractor(decode_return=None)
        result = await extractor.extract_from_html("")
        assert result is None

    @pytest.mark.asyncio
    async def test_meta_tag_with_tampered_content_returns_none(self) -> None:
        # decode returns None (tampered HMAC)
        extractor = _make_extractor(decode_return=None)
        html = '<html><head><meta name="kmflow-watermark" content="tampered-content"></head></html>'
        result = await extractor.extract_from_html(html)
        assert result is None


# ---------------------------------------------------------------------------
# HTML watermark pattern (unit test for the compiled regex)
# ---------------------------------------------------------------------------


class TestHtmlWatermarkPattern:
    """Validate the compiled regex matches expected HTML patterns."""

    def test_pattern_matches_standard_meta_tag(self) -> None:
        html = '<meta name="kmflow-watermark" content="abc123==">'
        m = _HTML_WATERMARK_PATTERN.search(html)
        assert m is not None
        assert m.group(1) == "abc123=="

    def test_pattern_does_not_match_different_name(self) -> None:
        html = '<meta name="other-watermark" content="abc123==">'
        m = _HTML_WATERMARK_PATTERN.search(html)
        assert m is None

    def test_pattern_captures_base64_with_slashes(self) -> None:
        encoded = "aGVsbG8vd29ybGQ+Zm9v"
        html = f'<meta name="kmflow-watermark" content="{encoded}">'
        m = _HTML_WATERMARK_PATTERN.search(html)
        assert m is not None
        assert m.group(1) == encoded

"""BDD tests for Export Watermarking service (Story #387).

Scenarios:
  1. PDF report export carries both visible and invisible watermarks
  2. Invisible watermark can identify the recipient from a recovered document
  3. HTML narrative export carries embedded watermark metadata
  4. Export log query returns all exports with full metadata
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.export_log import ExportLog
from src.security.watermark.extractor import WatermarkExtractor
from src.security.watermark.service import WatermarkService

USER_ID = uuid.uuid4()
EXPORT_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()


def _make_service(session: AsyncMock | None = None) -> WatermarkService:
    return WatermarkService(session or AsyncMock())


class TestVisibleWatermark:
    """Scenario 1 (partial): Visible watermark generation."""

    def test_visible_watermark_contains_engagement_name(self) -> None:
        service = _make_service()
        dt = datetime(2026, 2, 27, tzinfo=UTC)
        result = service.generate_visible_watermark("ACME Corp Engagement", dt)
        assert "ACME Corp Engagement" in result
        assert "2026-02-27" in result

    def test_visible_watermark_uses_current_date_if_none(self) -> None:
        service = _make_service()
        result = service.generate_visible_watermark("Test Engagement")
        assert "Test Engagement" in result
        assert "Exported" in result


class TestInvisibleWatermark:
    """Scenario 1 & 2: Invisible watermark encoding/decoding round-trip."""

    def test_encode_decode_round_trip(self) -> None:
        service = _make_service()
        ts = datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
        encoded = service.encode_invisible_watermark(USER_ID, EXPORT_ID, ts)

        decoded = service.decode_invisible_watermark(encoded)
        assert decoded is not None
        assert decoded["user_id"] == str(USER_ID)
        assert decoded["export_id"] == str(EXPORT_ID)
        assert "2026-02-27" in decoded["timestamp"]

    def test_tampered_watermark_returns_none(self) -> None:
        service = _make_service()
        encoded = service.encode_invisible_watermark(USER_ID, EXPORT_ID)

        # Tamper with the encoded string
        tampered = encoded[:-5] + "XXXXX"
        decoded = service.decode_invisible_watermark(tampered)
        assert decoded is None

    def test_invalid_base64_returns_none(self) -> None:
        service = _make_service()
        decoded = service.decode_invisible_watermark("not-valid-base64!!!")
        assert decoded is None

    def test_wrong_field_count_returns_none(self) -> None:
        import base64

        service = _make_service()
        bad_payload = base64.b64encode(b"field1|field2").decode("ascii")
        decoded = service.decode_invisible_watermark(bad_payload)
        assert decoded is None


class TestHTMLWatermark:
    """Scenario 3: HTML narrative export carries embedded watermark metadata."""

    def test_html_meta_tag_generated(self) -> None:
        service = _make_service()
        meta = service.generate_html_watermark_meta(EXPORT_ID, ENGAGEMENT_ID, USER_ID)

        assert 'name="kmflow-watermark"' in meta
        assert f'data-export-id="{EXPORT_ID}"' in meta
        assert f'data-engagement-id="{ENGAGEMENT_ID}"' in meta
        assert 'content="' in meta

    def test_html_watermark_decodable(self) -> None:
        service = _make_service()
        meta = service.generate_html_watermark_meta(EXPORT_ID, ENGAGEMENT_ID, USER_ID)

        # Extract content attribute value
        import re

        match = re.search(r'content="([^"]+)"', meta)
        assert match is not None
        encoded = match.group(1)

        decoded = service.decode_invisible_watermark(encoded)
        assert decoded is not None
        assert decoded["user_id"] == str(USER_ID)
        assert decoded["export_id"] == str(EXPORT_ID)


class TestExportLogCreation:
    """Scenario 1 (partial): Export log entry creation."""

    @pytest.mark.asyncio
    async def test_create_export_log(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = WatermarkService(mock_session)
        await service.create_export_log(
            export_id=EXPORT_ID,
            recipient_id=USER_ID,
            document_type="PDF",
            engagement_id=ENGAGEMENT_ID,
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, ExportLog)
        assert added.id == EXPORT_ID
        assert added.recipient_id == USER_ID
        assert added.document_type == "PDF"
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()


class TestExportLogQuery:
    """Scenario 4: Export log query returns paginated results."""

    @pytest.mark.asyncio
    async def test_get_export_logs_paginated(self) -> None:
        mock_session = AsyncMock()

        log_entry = MagicMock(spec=ExportLog)
        log_entry.id = EXPORT_ID
        log_entry.recipient_id = USER_ID
        log_entry.document_type = "PDF"
        log_entry.engagement_id = ENGAGEMENT_ID
        log_entry.exported_at = datetime(2026, 2, 27, tzinfo=UTC)

        # count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # list query
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [log_entry]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = WatermarkService(mock_session)
        result = await service.get_export_logs(ENGAGEMENT_ID, limit=20, offset=0)

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["export_id"] == str(EXPORT_ID)
        assert result["items"][0]["recipient_id"] == str(USER_ID)
        assert result["items"][0]["document_type"] == "PDF"
        assert result["limit"] == 20
        assert result["offset"] == 0


class TestExportLogLookup:
    """Scenario 2 (partial): Lookup by export_id for forensic recovery."""

    @pytest.mark.asyncio
    async def test_lookup_found(self) -> None:
        mock_session = AsyncMock()

        log_entry = MagicMock(spec=ExportLog)
        log_entry.id = EXPORT_ID
        log_entry.recipient_id = USER_ID
        log_entry.document_type = "PDF"
        log_entry.engagement_id = ENGAGEMENT_ID
        log_entry.exported_at = datetime(2026, 2, 27, tzinfo=UTC)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = log_entry
        mock_session.execute = AsyncMock(return_value=result_mock)

        service = WatermarkService(mock_session)
        result = await service.lookup_by_export_id(EXPORT_ID)

        assert result is not None
        assert result["export_id"] == str(EXPORT_ID)
        assert result["recipient_id"] == str(USER_ID)

    @pytest.mark.asyncio
    async def test_lookup_not_found(self) -> None:
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        service = WatermarkService(mock_session)
        result = await service.lookup_by_export_id(uuid.uuid4())
        assert result is None


class TestWatermarkExtractor:
    """Scenario 2: Full chain — extract watermark and recover identity."""

    @pytest.mark.asyncio
    async def test_extract_and_lookup(self) -> None:
        mock_session = AsyncMock()

        # Encode a watermark
        service = WatermarkService(mock_session)
        encoded = service.encode_invisible_watermark(USER_ID, EXPORT_ID)

        # Set up lookup to return an export log entry
        log_entry = MagicMock(spec=ExportLog)
        log_entry.id = EXPORT_ID
        log_entry.recipient_id = USER_ID
        log_entry.document_type = "PDF"
        log_entry.engagement_id = ENGAGEMENT_ID
        log_entry.exported_at = datetime(2026, 2, 27, tzinfo=UTC)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = log_entry
        mock_session.execute = AsyncMock(return_value=result_mock)

        extractor = WatermarkExtractor(mock_session)
        result = await extractor.extract_from_encoded(encoded)

        assert result is not None
        assert result["verified"] is True
        assert result["watermark"]["user_id"] == str(USER_ID)
        assert result["export_log"]["recipient_id"] == str(USER_ID)

    @pytest.mark.asyncio
    async def test_extract_from_html(self) -> None:
        mock_session = AsyncMock()
        service = WatermarkService(mock_session)

        meta = service.generate_html_watermark_meta(EXPORT_ID, ENGAGEMENT_ID, USER_ID)
        html = f"<html><head>{meta}</head><body>Report</body></html>"

        # Set up lookup
        log_entry = MagicMock(spec=ExportLog)
        log_entry.id = EXPORT_ID
        log_entry.recipient_id = USER_ID
        log_entry.document_type = "HTML"
        log_entry.engagement_id = ENGAGEMENT_ID
        log_entry.exported_at = datetime(2026, 2, 27, tzinfo=UTC)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = log_entry
        mock_session.execute = AsyncMock(return_value=result_mock)

        extractor = WatermarkExtractor(mock_session)
        result = await extractor.extract_from_html(html)

        assert result is not None
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_extract_from_html_no_watermark(self) -> None:
        mock_session = AsyncMock()
        extractor = WatermarkExtractor(mock_session)
        result = await extractor.extract_from_html("<html><body>No watermark</body></html>")
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_invalid_returns_none(self) -> None:
        mock_session = AsyncMock()
        extractor = WatermarkExtractor(mock_session)
        result = await extractor.extract_from_encoded("garbage-data")
        assert result is None

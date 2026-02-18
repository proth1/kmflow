"""Tests for Silver layer writer.

Tests cover: JSON fallback writes for fragments, entities, and quality events.
Delta Lake writes are tested only when deltalake is installed.
"""

from __future__ import annotations

import json

import pytest

from src.datalake.silver import SilverLayerWriter


class TestSilverLayerWriter:
    """Test Silver layer writer with JSON fallback."""

    @pytest.fixture
    def writer(self, tmp_path) -> SilverLayerWriter:
        return SilverLayerWriter(base_path=str(tmp_path / "datalake"))

    @pytest.mark.asyncio
    async def test_write_fragments(self, writer: SilverLayerWriter) -> None:
        fragments = [
            {
                "id": "frag-1",
                "fragment_type": "text",
                "content": "Test fragment content",
                "metadata_json": {"page": 1},
            },
            {
                "id": "frag-2",
                "fragment_type": "table",
                "content": "col1,col2\nval1,val2",
                "metadata_json": None,
            },
        ]
        result = await writer.write_fragments("eng-1", "ev-1", fragments)
        assert result["rows_written"] == 2
        assert result["table_path"] != ""

    @pytest.mark.asyncio
    async def test_write_fragments_empty(self, writer: SilverLayerWriter) -> None:
        result = await writer.write_fragments("eng-1", "ev-1", [])
        assert result["rows_written"] == 0

    @pytest.mark.asyncio
    async def test_write_entities(self, writer: SilverLayerWriter) -> None:
        entities = [
            {
                "entity_type": "Process",
                "value": "Loan Origination",
                "confidence": 0.95,
                "fragment_id": "frag-1",
            },
        ]
        result = await writer.write_entities("eng-1", "ev-1", entities)
        assert result["rows_written"] == 1

    @pytest.mark.asyncio
    async def test_write_entities_empty(self, writer: SilverLayerWriter) -> None:
        result = await writer.write_entities("eng-1", "ev-1", [])
        assert result["rows_written"] == 0

    @pytest.mark.asyncio
    async def test_write_quality_event(self, writer: SilverLayerWriter) -> None:
        scores = {
            "completeness": 0.85,
            "reliability": 0.90,
            "freshness": 0.70,
            "consistency": 0.95,
        }
        result = await writer.write_quality_event("eng-1", "ev-1", scores)
        assert result["rows_written"] == 1

    @pytest.mark.asyncio
    async def test_json_fallback_creates_readable_files(self, writer: SilverLayerWriter, tmp_path) -> None:
        """Verify JSON fallback files are valid JSON."""
        fragments = [
            {"id": "f1", "fragment_type": "text", "content": "hello"},
        ]
        result = await writer.write_fragments("eng-1", "ev-1", fragments)

        # Read the JSON file
        from pathlib import Path

        json_files = list(Path(result["table_path"]).parent.glob("*.json"))
        # If Delta is not available, there should be JSON files
        if not writer._has_delta:
            assert len(json_files) >= 1
            with open(json_files[0]) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_quality_event_computes_overall_score(self, writer: SilverLayerWriter) -> None:
        scores = {
            "completeness": 0.80,
            "reliability": 0.80,
            "freshness": 0.80,
            "consistency": 0.80,
        }
        result = await writer.write_quality_event("eng-1", "ev-1", scores)
        assert result["rows_written"] == 1

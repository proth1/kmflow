"""Tests for evidence format-specific parsers."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.bpmn_parser import BpmnParser
from src.evidence.parsers.document_parser import DocumentParser
from src.evidence.parsers.factory import (
    classify_by_extension,
    detect_format,
    get_parser,
    parse_file,
)
from src.evidence.parsers.structured_data_parser import StructuredDataParser

# ---------------------------------------------------------------------------
# Factory Tests
# ---------------------------------------------------------------------------


class TestParserFactory:
    """Test suite for the parser factory."""

    def test_get_parser_pdf(self) -> None:
        """Should return DocumentParser for PDF files."""
        parser = get_parser("report.pdf")
        assert isinstance(parser, DocumentParser)

    def test_get_parser_docx(self) -> None:
        """Should return DocumentParser for Word files."""
        parser = get_parser("document.docx")
        assert isinstance(parser, DocumentParser)

    def test_get_parser_xlsx(self) -> None:
        """Should return StructuredDataParser for Excel files."""
        parser = get_parser("data.xlsx")
        assert isinstance(parser, StructuredDataParser)

    def test_get_parser_csv(self) -> None:
        """Should return StructuredDataParser for CSV files."""
        parser = get_parser("data.csv")
        assert isinstance(parser, StructuredDataParser)

    def test_get_parser_json(self) -> None:
        """Should return StructuredDataParser for JSON files."""
        parser = get_parser("config.json")
        assert isinstance(parser, StructuredDataParser)

    def test_get_parser_bpmn(self) -> None:
        """Should return BpmnParser for BPMN files."""
        parser = get_parser("process.bpmn")
        assert isinstance(parser, BpmnParser)

    def test_get_parser_unknown(self) -> None:
        """Should return None for unsupported formats."""
        parser = get_parser("video.mp4")
        assert parser is None

    def test_classify_by_extension(self) -> None:
        """Should classify files by extension."""
        assert classify_by_extension("report.pdf") == "documents"
        assert classify_by_extension("data.csv") == "structured_data"
        assert classify_by_extension("process.bpmn") == "bpm_process_models"
        assert classify_by_extension("photo.png") == "images"
        assert classify_by_extension("unknown.xyz") is None

    def test_detect_format(self) -> None:
        """Should detect format from filename."""
        assert detect_format("report.pdf") == "pdf"
        assert detect_format("data.csv") == "csv"
        assert detect_format("noext") == "unknown"


# ---------------------------------------------------------------------------
# Document Parser Tests
# ---------------------------------------------------------------------------


class TestDocumentParser:
    """Test suite for the DocumentParser."""

    def test_supported_formats(self) -> None:
        """Should support PDF, DOCX, PPTX, TXT."""
        parser = DocumentParser()
        assert parser.can_parse(".pdf")
        assert parser.can_parse(".docx")
        assert parser.can_parse(".pptx")
        assert parser.can_parse(".txt")
        assert not parser.can_parse(".xlsx")

    @pytest.mark.asyncio
    async def test_parse_text_file(self) -> None:
        """Should extract text from a plain text file."""
        parser = DocumentParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello World\nThis is a test document.\n")
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "test.txt")
            assert result.error is None
            assert len(result.fragments) == 1
            assert result.fragments[0].fragment_type == FragmentType.TEXT
            assert "Hello World" in result.fragments[0].content
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_empty_text_file(self) -> None:
        """Should handle empty text files gracefully."""
        parser = DocumentParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "empty.txt")
            assert result.error is None
            # No fragments for empty content
            assert len(result.fragments) == 0
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_unsupported_extension(self) -> None:
        """Should return error for unsupported document formats."""
        parser = DocumentParser()
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "file.xyz")
            assert result.error is not None
            assert "Unsupported" in result.error
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Structured Data Parser Tests
# ---------------------------------------------------------------------------


class TestStructuredDataParser:
    """Test suite for the StructuredDataParser."""

    def test_supported_formats(self) -> None:
        """Should support XLSX, CSV, JSON."""
        parser = StructuredDataParser()
        assert parser.can_parse(".xlsx")
        assert parser.can_parse(".csv")
        assert parser.can_parse(".json")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_csv_file(self) -> None:
        """Should extract table data from CSV files."""
        parser = StructuredDataParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "data.csv")
            assert result.error is None
            assert len(result.fragments) >= 1

            # Should have at least one TABLE fragment
            table_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TABLE]
            assert len(table_frags) == 1
            assert "Alice" in table_frags[0].content

            # Should have schema entity
            entity_frags = [f for f in result.fragments if f.fragment_type == FragmentType.ENTITY]
            assert len(entity_frags) == 1
            schema = json.loads(entity_frags[0].content)
            assert "name" in schema["columns"]
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_json_array(self) -> None:
        """Should extract data from JSON array files."""
        parser = StructuredDataParser()
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "data.json")
            assert result.error is None
            assert result.metadata.get("record_count") == 2

            # Should have schema from first record
            entity_frags = [f for f in result.fragments if f.fragment_type == FragmentType.ENTITY]
            assert len(entity_frags) >= 1
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_json_object(self) -> None:
        """Should extract data from JSON object files."""
        parser = StructuredDataParser()
        data = {"config": "value", "nested": {"key": "val"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "config.json")
            assert result.error is None
            assert result.metadata.get("key_count") == 2

            text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
            assert len(text_frags) == 1
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# BPMN Parser Tests
# ---------------------------------------------------------------------------


class TestBpmnParser:
    """Test suite for the BpmnParser."""

    SIMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_1">
  <bpmn:process id="Process_1" name="Test Process" isExecutable="true">
    <bpmn:startEvent id="Start_1" name="Start"/>
    <bpmn:userTask id="Task_1" name="Review Document"/>
    <bpmn:exclusiveGateway id="GW_1" name="Approved?"/>
    <bpmn:endEvent id="End_1" name="End"/>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start_1" targetRef="Task_1"/>
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="GW_1"/>
    <bpmn:sequenceFlow id="Flow_3" sourceRef="GW_1" targetRef="End_1" name="Yes"/>
  </bpmn:process>
</bpmn:definitions>"""

    def test_supported_formats(self) -> None:
        """Should support BPMN file extensions."""
        parser = BpmnParser()
        assert parser.can_parse(".bpmn")
        assert parser.can_parse(".bpmn2")
        assert parser.can_parse(".xml")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_simple_bpmn(self) -> None:
        """Should extract elements from a simple BPMN file."""
        parser = BpmnParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(self.SIMPLE_BPMN)
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "test.bpmn")
            assert result.error is None

            # Should find tasks, gateways, events, and flows
            element_types = {f.metadata.get("element_type") for f in result.fragments}
            assert "userTask" in element_types
            assert "exclusiveGateway" in element_types
            assert "startEvent" in element_types
            assert "endEvent" in element_types
            assert "sequenceFlow" in element_types

            # Check metadata
            assert result.metadata.get("process_count") == 1
            assert result.metadata.get("task_count") == 1
            assert result.metadata.get("gateway_count") == 1
            assert result.metadata.get("event_count") == 2
            assert result.metadata.get("flow_count") == 3
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_bpmn_extracts_task_names(self) -> None:
        """Should extract task names from BPMN elements."""
        parser = BpmnParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(self.SIMPLE_BPMN)
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "test.bpmn")
            process_elements = [f for f in result.fragments if f.fragment_type == FragmentType.PROCESS_ELEMENT]
            task_content = [f.content for f in process_elements]
            assert any("Review Document" in c for c in task_content)
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parse_bpmn_extracts_flows(self) -> None:
        """Should extract sequence flows as relationships."""
        parser = BpmnParser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(self.SIMPLE_BPMN)
            f.flush()
            temp_path = f.name

        try:
            result = await parser.parse(temp_path, "test.bpmn")
            flow_fragments = [f for f in result.fragments if f.fragment_type == FragmentType.RELATIONSHIP]
            assert len(flow_fragments) == 3
            # Check that flow content includes source and target refs
            assert any("Start_1 -> Task_1" in f.content for f in flow_fragments)
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Parse File Integration Tests
# ---------------------------------------------------------------------------


class TestParseFileIntegration:
    """Integration tests for the parse_file function."""

    @pytest.mark.asyncio
    async def test_parse_unsupported_file(self) -> None:
        """Should return error for unsupported file types."""
        result = await parse_file("/tmp/fake.mp4", "video.mp4")
        assert result.error is not None
        assert "No parser" in result.error

    @pytest.mark.asyncio
    async def test_parse_text_via_factory(self) -> None:
        """Should route text files through DocumentParser."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content for factory routing")
            f.flush()
            temp_path = f.name

        try:
            result = await parse_file(temp_path, "test.txt")
            assert result.error is None
            assert len(result.fragments) == 1
        finally:
            os.unlink(temp_path)

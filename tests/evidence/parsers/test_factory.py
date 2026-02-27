"""Tests for parser factory — Story #296.

Covers BDD Scenario 4 (unsupported format rejected) and factory dispatch logic.
"""

from __future__ import annotations

import pytest

from src.evidence.parsers.bpmn_parser import BpmnParser
from src.evidence.parsers.document_parser import DocumentParser
from src.evidence.parsers.factory import (
    EXTENSION_TO_CATEGORY,
    classify_by_extension,
    detect_format,
    get_parser,
    parse_file,
)
from src.evidence.parsers.structured_data_parser import StructuredDataParser

# ---------------------------------------------------------------------------
# Parser dispatch
# ---------------------------------------------------------------------------


class TestGetParser:
    """Factory correctly routes to the right parser."""

    def test_pdf_routes_to_document_parser(self) -> None:
        parser = get_parser("report.pdf")
        assert isinstance(parser, DocumentParser)

    def test_docx_routes_to_document_parser(self) -> None:
        parser = get_parser("letter.docx")
        assert isinstance(parser, DocumentParser)

    def test_pptx_routes_to_document_parser(self) -> None:
        parser = get_parser("deck.pptx")
        assert isinstance(parser, DocumentParser)

    def test_html_routes_to_document_parser(self) -> None:
        parser = get_parser("page.html")
        assert isinstance(parser, DocumentParser)

    def test_htm_routes_to_document_parser(self) -> None:
        parser = get_parser("page.htm")
        assert isinstance(parser, DocumentParser)

    def test_txt_routes_to_document_parser(self) -> None:
        parser = get_parser("readme.txt")
        assert isinstance(parser, DocumentParser)

    def test_xlsx_routes_to_structured_data(self) -> None:
        parser = get_parser("data.xlsx")
        assert isinstance(parser, StructuredDataParser)

    def test_csv_routes_to_structured_data(self) -> None:
        parser = get_parser("data.csv")
        assert isinstance(parser, StructuredDataParser)

    def test_json_routes_to_structured_data(self) -> None:
        parser = get_parser("data.json")
        assert isinstance(parser, StructuredDataParser)

    def test_bpmn_routes_to_bpmn_parser(self) -> None:
        parser = get_parser("process.bpmn")
        assert isinstance(parser, BpmnParser)

    def test_bpmn2_routes_to_bpmn_parser(self) -> None:
        parser = get_parser("process.bpmn2")
        assert isinstance(parser, BpmnParser)


# ---------------------------------------------------------------------------
# BDD Scenario 4: Unsupported file format rejected
# ---------------------------------------------------------------------------


class TestBDDScenario4UnsupportedFormat:
    """Scenario 4: Unsupported extension returns None from get_parser."""

    def test_unsupported_extension_returns_none(self) -> None:
        parser = get_parser("image.heic")
        assert parser is None

    def test_unknown_extension_returns_none(self) -> None:
        parser = get_parser("data.xyz123")
        assert parser is None

    @pytest.mark.asyncio
    async def test_parse_file_returns_error_for_unsupported(self) -> None:
        """parse_file returns ParseResult with error for unsupported formats."""
        result = await parse_file("/tmp/fake.heic", "image.heic")
        assert result.error is not None
        assert "No parser available" in result.error

    def test_case_insensitive_extension(self) -> None:
        """Extension matching is case-insensitive."""
        parser = get_parser("report.PDF")
        assert isinstance(parser, DocumentParser)


# ---------------------------------------------------------------------------
# Extension classification
# ---------------------------------------------------------------------------


class TestClassifyByExtension:
    def test_pdf_classified_as_documents(self) -> None:
        assert classify_by_extension("report.pdf") == "documents"

    def test_html_classified_as_documents(self) -> None:
        assert classify_by_extension("page.html") == "documents"

    def test_htm_classified_as_documents(self) -> None:
        assert classify_by_extension("page.htm") == "documents"

    def test_xlsx_classified_as_structured_data(self) -> None:
        assert classify_by_extension("data.xlsx") == "structured_data"

    def test_csv_classified_as_structured_data(self) -> None:
        assert classify_by_extension("data.csv") == "structured_data"

    def test_bpmn_classified_as_bpm(self) -> None:
        assert classify_by_extension("process.bpmn") == "bpm_process_models"

    def test_unknown_returns_none(self) -> None:
        assert classify_by_extension("file.heic") is None


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_pdf_format(self) -> None:
        assert detect_format("report.pdf") == "pdf"

    def test_html_format(self) -> None:
        assert detect_format("page.html") == "html"

    def test_no_extension(self) -> None:
        assert detect_format("Makefile") == "unknown"


# ---------------------------------------------------------------------------
# Extension category completeness
# ---------------------------------------------------------------------------


class TestExtensionCategoryRegistry:
    """Verify the extension-to-category mapping covers Phase 1 formats."""

    def test_phase1_document_formats_registered(self) -> None:
        for ext in [".pdf", ".docx", ".doc", ".pptx", ".txt", ".html", ".htm"]:
            assert ext in EXTENSION_TO_CATEGORY, f"{ext} not in EXTENSION_TO_CATEGORY"

    def test_phase1_structured_data_formats_registered(self) -> None:
        for ext in [".xlsx", ".xls", ".csv", ".json"]:
            assert ext in EXTENSION_TO_CATEGORY, f"{ext} not in EXTENSION_TO_CATEGORY"

    def test_phase1_bpm_formats_registered(self) -> None:
        for ext in [".bpmn", ".bpmn2"]:
            assert ext in EXTENSION_TO_CATEGORY, f"{ext} not in EXTENSION_TO_CATEGORY"

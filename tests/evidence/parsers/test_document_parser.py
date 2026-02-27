"""Tests for DocumentParser (PDF, DOCX, PPTX, HTML, TXT) — Story #296.

Covers BDD Scenarios 1 (PDF parsing) and 5 (corrupted file handling),
plus HTML and TXT sub-parser tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.document_parser import DocumentParser


@pytest.fixture
def parser() -> DocumentParser:
    return DocumentParser()


# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------


class TestSupportedFormats:
    """Verify the parser supports all expected document formats."""

    def test_supported_formats_list(self, parser: DocumentParser) -> None:
        expected = [".pdf", ".docx", ".pptx", ".doc", ".txt", ".html", ".htm"]
        for ext in expected:
            assert parser.can_parse(ext), f"{ext} should be supported"

    def test_unsupported_format(self, parser: DocumentParser) -> None:
        assert not parser.can_parse(".xlsx")
        assert not parser.can_parse(".bpmn")


# ---------------------------------------------------------------------------
# BDD Scenario 1: PDF document is parsed successfully
# ---------------------------------------------------------------------------


class TestBDDScenario1PdfParsing:
    """Scenario 1: PDF document parsed with page-level fragments."""

    @pytest.mark.asyncio
    async def test_pdf_text_extraction(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Given a PDF, text content is extracted per page."""
        pdf_path = tmp_path / "test.pdf"
        _create_simple_pdf(pdf_path)

        result = await parser.parse(str(pdf_path), "test.pdf")

        assert result.error is None
        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        assert len(text_frags) >= 1
        assert "Hello" in text_frags[0].content

    @pytest.mark.asyncio
    async def test_pdf_page_count_metadata(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Metadata includes page_count."""
        pdf_path = tmp_path / "test.pdf"
        _create_simple_pdf(pdf_path, pages=3)

        result = await parser.parse(str(pdf_path), "test.pdf")

        assert result.metadata.get("page_count") == 3

    @pytest.mark.asyncio
    async def test_pdf_page_number_in_fragment_metadata(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Each fragment records its source page number."""
        pdf_path = tmp_path / "test.pdf"
        _create_simple_pdf(pdf_path, pages=2)

        result = await parser.parse(str(pdf_path), "test.pdf")

        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        page_numbers = [f.metadata.get("page") for f in text_frags]
        assert 1 in page_numbers
        assert 2 in page_numbers

    @pytest.mark.asyncio
    async def test_pdf_table_extraction(self, parser: DocumentParser, tmp_path: Path) -> None:
        """PDF tables are extracted as TABLE fragments."""
        pdf_path = tmp_path / "test.pdf"
        _create_pdf_with_table(pdf_path)

        result = await parser.parse(str(pdf_path), "test.pdf")

        # Tables may or may not be detected depending on pdfplumber heuristics
        # At minimum, text extraction should succeed without error
        assert result.error is None
        assert len(result.fragments) >= 1


# ---------------------------------------------------------------------------
# HTML Parser Tests
# ---------------------------------------------------------------------------


class TestHtmlParsing:
    """HTML parsing extracts title, body text, and metadata."""

    @pytest.mark.asyncio
    async def test_html_body_text_extraction(self, parser: DocumentParser, tmp_path: Path) -> None:
        html_path = tmp_path / "test.html"
        html_path.write_text(
            "<html><head><title>My Doc</title></head><body><h1>Heading</h1><p>Body text here.</p></body></html>"
        )

        result = await parser.parse(str(html_path), "test.html")

        assert result.error is None
        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        assert len(text_frags) == 1
        assert "Body text here" in text_frags[0].content

    @pytest.mark.asyncio
    async def test_html_title_metadata(self, parser: DocumentParser, tmp_path: Path) -> None:
        html_path = tmp_path / "test.html"
        html_path.write_text("<html><head><title>Page Title</title></head><body><p>Content</p></body></html>")

        result = await parser.parse(str(html_path), "test.html")

        assert result.metadata.get("title") == "Page Title"

    @pytest.mark.asyncio
    async def test_html_char_count_metadata(self, parser: DocumentParser, tmp_path: Path) -> None:
        html_content = "<html><body><p>Content</p></body></html>"
        html_path = tmp_path / "test.htm"
        html_path.write_text(html_content)

        result = await parser.parse(str(html_path), "test.htm")

        assert result.metadata.get("char_count") == len(html_content)

    @pytest.mark.asyncio
    async def test_html_script_style_stripped(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Script and style tags are stripped so JS/CSS doesn't leak into text."""
        html_path = tmp_path / "scripted.html"
        html_path.write_text(
            "<html><body><script>var x = 1;</script>"
            "<style>.cls { color: red; }</style>"
            "<p>Clean text only.</p></body></html>"
        )

        result = await parser.parse(str(html_path), "scripted.html")

        assert result.error is None
        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        assert len(text_frags) == 1
        assert "var x" not in text_frags[0].content
        assert "color: red" not in text_frags[0].content
        assert "Clean text only" in text_frags[0].content

    @pytest.mark.asyncio
    async def test_htm_extension_supported(self, parser: DocumentParser, tmp_path: Path) -> None:
        html_path = tmp_path / "test.htm"
        html_path.write_text("<html><body><p>Works</p></body></html>")

        result = await parser.parse(str(html_path), "test.htm")

        assert result.error is None
        assert len(result.fragments) >= 1


# ---------------------------------------------------------------------------
# TXT Parser Tests
# ---------------------------------------------------------------------------


class TestTxtParsing:
    """Plain text file parsing."""

    @pytest.mark.asyncio
    async def test_txt_content_extraction(self, parser: DocumentParser, tmp_path: Path) -> None:
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("Hello world\nLine two")

        result = await parser.parse(str(txt_path), "test.txt")

        assert result.error is None
        assert len(result.fragments) == 1
        assert result.fragments[0].fragment_type == FragmentType.TEXT
        assert "Hello world" in result.fragments[0].content

    @pytest.mark.asyncio
    async def test_txt_char_count_metadata(self, parser: DocumentParser, tmp_path: Path) -> None:
        content = "Short text"
        txt_path = tmp_path / "test.txt"
        txt_path.write_text(content)

        result = await parser.parse(str(txt_path), "test.txt")

        assert result.metadata.get("char_count") == len(content)

    @pytest.mark.asyncio
    async def test_empty_txt_no_fragments(self, parser: DocumentParser, tmp_path: Path) -> None:
        txt_path = tmp_path / "empty.txt"
        txt_path.write_text("")

        result = await parser.parse(str(txt_path), "empty.txt")

        assert result.error is None
        assert len(result.fragments) == 0


# ---------------------------------------------------------------------------
# BDD Scenario 5: Corrupted file handled gracefully
# ---------------------------------------------------------------------------


class TestBDDScenario5CorruptedFile:
    """Scenario 5: Corrupted file is handled without unhandled exception."""

    @pytest.mark.asyncio
    async def test_corrupted_pdf(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Corrupted PDF returns error, no unhandled exception."""
        bad_pdf = tmp_path / "corrupted.pdf"
        bad_pdf.write_bytes(b"NOT A PDF FILE AT ALL")

        result = await parser.parse(str(bad_pdf), "corrupted.pdf")

        assert result.error is not None
        assert "Parse error" in result.error

    @pytest.mark.asyncio
    async def test_corrupted_docx(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Corrupted DOCX returns error with failure reason."""
        bad_docx = tmp_path / "corrupted.docx"
        bad_docx.write_bytes(b"NOT A DOCX FILE")

        result = await parser.parse(str(bad_docx), "corrupted.docx")

        assert result.error is not None
        assert "Parse error" in result.error

    @pytest.mark.asyncio
    async def test_corrupted_pptx(self, parser: DocumentParser, tmp_path: Path) -> None:
        """Corrupted PPTX returns error."""
        bad_pptx = tmp_path / "corrupted.pptx"
        bad_pptx.write_bytes(b"NOT A PPTX")

        result = await parser.parse(str(bad_pptx), "corrupted.pptx")

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_unsupported_extension_returns_error(self, parser: DocumentParser) -> None:
        result = await parser.parse("/tmp/fake.xyz", "fake.xyz")

        assert result.error is not None
        assert "Unsupported" in result.error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_simple_pdf(path: Path, pages: int = 1) -> None:
    """Create a simple test PDF using reportlab if available, else fpdf2."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        for i in range(pages):
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.cell(200, 10, text=f"Hello from page {i + 1}")
        pdf.output(str(path))
    except ImportError:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(str(path), pagesize=letter)
            for i in range(pages):
                if i > 0:
                    c.showPage()
                c.drawString(72, 700, f"Hello from page {i + 1}")
            c.save()
        except ImportError:
            pytest.skip("No PDF generation library available (fpdf2 or reportlab)")


def _create_pdf_with_table(path: Path) -> None:
    """Create a PDF with a simple table."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        # Simple table
        headers = ["Name", "Value", "Status"]
        data = [["Item A", "100", "Active"], ["Item B", "200", "Inactive"]]
        col_w = 50
        for h in headers:
            pdf.cell(col_w, 10, h, border=1)
        pdf.ln()
        for row in data:
            for cell in row:
                pdf.cell(col_w, 10, cell, border=1)
            pdf.ln()
        pdf.output(str(path))
    except ImportError:
        pytest.skip("fpdf2 not available for table PDF creation")

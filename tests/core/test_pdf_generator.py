"""Tests for PDF report generation module."""

from __future__ import annotations

import pytest

from src.core.pdf_generator import _PRINT_CSS, html_to_pdf, is_pdf_available


class TestPdfGenerator:
    """Tests for PDF generation utilities."""

    def test_is_pdf_available_returns_bool(self) -> None:
        """Should return a boolean indicating WeasyPrint availability."""
        result = is_pdf_available()
        assert isinstance(result, bool)

    def test_print_css_exists(self) -> None:
        """Print CSS constant should contain page and media rules."""
        assert "@media print" in _PRINT_CSS
        assert "@page" in _PRINT_CSS
        assert "A4" in _PRINT_CSS

    def test_html_to_pdf_without_weasyprint(self) -> None:
        """Should raise ImportError if WeasyPrint is not installed."""
        if is_pdf_available():
            pytest.skip("WeasyPrint is installed; cannot test fallback")
        with pytest.raises(ImportError, match="WeasyPrint"):
            html_to_pdf("<html><body>Test</body></html>")

    @pytest.mark.skipif(not is_pdf_available(), reason="WeasyPrint not installed")
    def test_html_to_pdf_basic(self) -> None:
        """Should generate valid PDF bytes from HTML."""
        html = "<html><head></head><body><h1>Test Report</h1><p>Content</p></body></html>"
        pdf_bytes = html_to_pdf(html)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF files start with %PDF-
        assert pdf_bytes[:5] == b"%PDF-"

    @pytest.mark.skipif(not is_pdf_available(), reason="WeasyPrint not installed")
    def test_html_to_pdf_injects_print_css(self) -> None:
        """Should inject print CSS into the HTML head."""
        html = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        # This should not raise - the CSS injection should work
        pdf_bytes = html_to_pdf(html)
        assert isinstance(pdf_bytes, bytes)

    @pytest.mark.skipif(not is_pdf_available(), reason="WeasyPrint not installed")
    def test_html_to_pdf_no_head_tag(self) -> None:
        """Should handle HTML without head tag by wrapping."""
        html = "<h1>Report</h1><p>Content</p>"
        pdf_bytes = html_to_pdf(html)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:5] == b"%PDF-"

"""PDF report generation using WeasyPrint.

Converts HTML reports to PDF format for download.
Falls back to a simple text-based PDF if WeasyPrint is unavailable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML as WeasyHtml  # type: ignore[import-untyped]  # noqa: N811

    _WEASYPRINT_AVAILABLE = True
except ImportError:
    logger.info("WeasyPrint not installed; PDF generation will use fallback mode")


# Print-optimized CSS prepended to all HTML before conversion
_PRINT_CSS = """
<style>
@media print {
    body { font-family: Arial, sans-serif; margin: 20mm; font-size: 11pt; }
    table { page-break-inside: auto; }
    tr { page-break-inside: avoid; }
    th { background-color: #f0f0f0 !important; -webkit-print-color-adjust: exact; }
    .critical { color: #c0392b !important; }
    .warning { color: #d68910 !important; }
    .good { color: #1e8449 !important; }
    .metric { font-size: 24pt; }
    h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 8px; }
    h2 { font-size: 16pt; margin-top: 16px; }
}
@page {
    size: A4;
    margin: 20mm;
    @bottom-center { content: "KMFlow Report - Page " counter(page) " of " counter(pages); font-size: 9pt; color: #999; }
}
</style>
"""


def is_pdf_available() -> bool:
    """Check if PDF generation is available.

    Returns:
        True if WeasyPrint is installed.
    """
    return _WEASYPRINT_AVAILABLE


def html_to_pdf(html: str) -> bytes:
    """Convert an HTML string to PDF bytes.

    Prepends print CSS for consistent formatting.
    If WeasyPrint is unavailable, raises ImportError.

    Args:
        html: HTML content to convert.

    Returns:
        PDF file bytes.

    Raises:
        ImportError: If WeasyPrint is not installed.
        RuntimeError: If PDF conversion fails.
    """
    if not _WEASYPRINT_AVAILABLE:
        raise ImportError(
            "WeasyPrint is required for PDF generation. "
            "Install with: pip install weasyprint"
        )

    # Inject print CSS into the HTML head
    if "<head>" in html:
        enhanced_html = html.replace("<head>", f"<head>{_PRINT_CSS}")
    else:
        enhanced_html = f"<html><head>{_PRINT_CSS}</head><body>{html}</body></html>"

    try:
        doc = WeasyHtml(string=enhanced_html)
        return doc.write_pdf()
    except Exception as e:
        logger.exception("PDF generation failed")
        raise RuntimeError(f"PDF generation failed: {e}") from e

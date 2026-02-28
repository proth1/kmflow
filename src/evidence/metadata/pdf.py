"""PDF metadata extractor.

Extracts title, author, creation date, page count from PDF files
using pdfplumber (already a project dependency).
"""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

from src.evidence.metadata.base import ExtractedMetadata, MetadataExtractor, clean_string

logger = logging.getLogger(__name__)


class PdfMetadataExtractor(MetadataExtractor):
    """Extract metadata from PDF files."""

    supported_extensions = [".pdf"]

    def extract(self, file_path: str, file_size_bytes: int | None = None) -> ExtractedMetadata:
        """Extract metadata from a PDF file.

        Uses pdfplumber to read PDF info dict for title, author,
        creation/modification dates, and page count.
        """
        import pdfplumber

        path = Path(file_path)
        size = file_size_bytes if file_size_bytes is not None else path.stat().st_size

        metadata = ExtractedMetadata(file_size_bytes=size)

        try:
            with pdfplumber.open(file_path) as pdf:
                metadata.page_count = len(pdf.pages)

                info = pdf.metadata or {}
                metadata.title = clean_string(info.get("Title"))
                metadata.author = clean_string(info.get("Author"))
                metadata.creation_date = _parse_pdf_date(info.get("CreationDate"))
                metadata.modification_date = _parse_pdf_date(info.get("ModDate"))
        except Exception:  # Intentionally broad: PDF files can be corrupt or encrypted
            logger.warning("Failed to extract PDF metadata from %s", file_path)

        return metadata


def _parse_pdf_date(value: str | None) -> str | None:
    """Parse PDF date format (D:YYYYMMDDHHmmSS) to ISO 8601.

    PDF dates look like: D:20251001090000+00'00'
    Returns ISO string or None if unparseable.
    """
    if not value:
        return None

    date_str = str(value)
    # Strip the D: prefix
    if date_str.startswith("D:"):
        date_str = date_str[2:]

    # Remove timezone offset characters for simpler parsing
    date_str = date_str.replace("'", "")

    try:
        from datetime import datetime

        # Try full format: YYYYMMDDHHmmSS
        if len(date_str) >= 14:
            dt = datetime(
                year=int(date_str[0:4]),
                month=int(date_str[4:6]),
                day=int(date_str[6:8]),
                hour=int(date_str[8:10]),
                minute=int(date_str[10:12]),
                second=int(date_str[12:14]),
                tzinfo=UTC,
            )
            return dt.isoformat()
        elif len(date_str) >= 8:
            dt = datetime(
                year=int(date_str[0:4]),
                month=int(date_str[4:6]),
                day=int(date_str[6:8]),
                tzinfo=UTC,
            )
            return dt.isoformat()
    except (ValueError, IndexError):
        logger.debug("Could not parse PDF date: %s", value)

    return None

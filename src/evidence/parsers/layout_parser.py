"""Layout-aware document parser using Unstructured.io.

Uses bounding-box-based layout detection to classify document regions
(Title, Paragraph, Table, Figure, Formula) before extraction. This enables:
- Structure-preserving chunking (tables atomic, headings attached to sections)
- Multi-column reading order correction
- Element-type metadata on fragments
- OCR fallback for scanned documents

Falls back to pdfplumber for simple digital PDFs when Unstructured is not
installed or fails.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# Map Unstructured element types to our FragmentType enum
_ELEMENT_TYPE_MAP: dict[str, FragmentType] = {
    "Title": FragmentType.TEXT,
    "NarrativeText": FragmentType.TEXT,
    "UncategorizedText": FragmentType.TEXT,
    "ListItem": FragmentType.TEXT,
    "Address": FragmentType.TEXT,
    "EmailAddress": FragmentType.TEXT,
    "FigureCaption": FragmentType.TEXT,
    "Table": FragmentType.TABLE,
    "Header": FragmentType.TEXT,
    "Footer": FragmentType.TEXT,
    "PageBreak": FragmentType.TEXT,
    "Image": FragmentType.IMAGE,
    "Formula": FragmentType.TEXT,
}


class LayoutAwareDocumentParser(BaseParser):
    """PDF parser using Unstructured.io hi_res layout detection.

    Emits typed ParsedFragment results with bounding box metadata.
    Falls back to the standard DocumentParser if Unstructured is not available.
    """

    supported_formats = [".pdf"]

    def __init__(self, strategy: str = "hi_res") -> None:
        """Initialize with a parsing strategy.

        Args:
            strategy: Unstructured strategy — "hi_res" for layout detection,
                      "fast" for text-only, "auto" to let Unstructured decide.
        """
        self._strategy = strategy

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a PDF using layout-aware extraction."""
        ext = Path(file_name).suffix.lower()
        if ext != ".pdf":
            return ParseResult(error=f"LayoutAwareDocumentParser only handles PDFs, got: {ext}")

        try:
            return await self._parse_with_unstructured(file_path)
        except ImportError:
            logger.info("Unstructured not installed, falling back to pdfplumber")
            return await self._fallback_parse(file_path)
        except Exception as e:  # Intentionally broad: parser library exceptions vary by format
            logger.warning("Unstructured parse failed, falling back: %s", e)
            return await self._fallback_parse(file_path)

    async def _parse_with_unstructured(self, file_path: str) -> ParseResult:
        """Parse using Unstructured.io partition_pdf."""
        import asyncio

        from unstructured.partition.pdf import partition_pdf

        # Run in thread to avoid blocking the event loop
        elements = await asyncio.to_thread(
            partition_pdf,
            filename=file_path,
            strategy=self._strategy,
            include_page_breaks=True,
        )

        fragments: list[ParsedFragment] = []
        metadata: dict[str, str | int | float | bool | list[str] | None] = {
            "parser": "unstructured",
            "strategy": self._strategy,
            "element_count": len(elements),
        }

        for element in elements:
            text = str(element)
            if not text or not text.strip():
                continue

            # Skip page breaks
            element_type = type(element).__name__
            if element_type == "PageBreak":
                continue

            fragment_type = _ELEMENT_TYPE_MAP.get(element_type, FragmentType.TEXT)

            # Build fragment metadata with bounding box info
            frag_meta: dict[str, str | int | float | bool | list[str] | None] = {
                "element_type": element_type,
            }

            # Extract element metadata (page number, coordinates)
            el_meta = element.metadata
            if hasattr(el_meta, "page_number") and el_meta.page_number is not None:
                frag_meta["page"] = el_meta.page_number

            if hasattr(el_meta, "coordinates") and el_meta.coordinates is not None:
                coords = el_meta.coordinates
                if hasattr(coords, "points") and coords.points:
                    # Store bounding box as [x1, y1, x2, y2]
                    points = coords.points
                    if len(points) >= 2:
                        frag_meta["bbox_x1"] = float(points[0][0])
                        frag_meta["bbox_y1"] = float(points[0][1])
                        frag_meta["bbox_x2"] = float(points[-1][0])
                        frag_meta["bbox_y2"] = float(points[-1][1])

            fragments.append(
                ParsedFragment(
                    fragment_type=fragment_type,
                    content=text.strip(),
                    metadata=frag_meta,
                )
            )

        return ParseResult(fragments=fragments, metadata=metadata)

    async def _fallback_parse(self, file_path: str) -> ParseResult:
        """Fall back to pdfplumber-based parsing."""
        from src.evidence.parsers.document_parser import DocumentParser

        parser = DocumentParser()
        return await parser._parse_pdf(file_path)

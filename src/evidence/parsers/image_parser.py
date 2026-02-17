"""Image parser with OCR text extraction.

Extracts text from images (PNG, JPEG, TIFF, BMP) using OCR.
Falls back to metadata-only extraction if OCR is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    """Parser for image files with OCR text extraction."""

    supported_formats = [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse an image file and extract text via OCR.

        Attempts OCR using pytesseract if available, otherwise returns
        metadata-only fragments.

        Args:
            file_path: Path to the image file.
            file_name: Original filename.

        Returns:
            ParseResult with OCR text fragments and image metadata.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        # Extract file metadata
        stat = path.stat()
        result.metadata = {
            "file_name": file_name,
            "file_size": stat.st_size,
            "format": path.suffix.lower().lstrip("."),
        }

        # Attempt OCR extraction
        try:
            text = await self._extract_text_ocr(file_path)
            if text and text.strip():
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=text.strip(),
                        metadata={"source": "ocr", "file_name": file_name},
                    )
                )
        except Exception as e:
            logger.warning("OCR extraction failed for %s: %s", file_name, e)
            result.error = f"OCR extraction failed: {e}"

        # Always add an image fragment referencing the file
        result.fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.IMAGE,
                content=f"Image file: {file_name}",
                metadata={
                    "file_path": file_path,
                    "file_name": file_name,
                    "format": path.suffix.lower().lstrip("."),
                },
            )
        )

        return result

    async def _extract_text_ocr(self, file_path: str) -> str:
        """Extract text from an image using OCR.

        Uses pytesseract if available. This is a synchronous operation
        wrapped for async compatibility.

        Args:
            file_path: Path to the image file.

        Returns:
            Extracted text string.
        """
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text
        except ImportError:
            logger.info("pytesseract/PIL not installed; OCR unavailable")
            return ""

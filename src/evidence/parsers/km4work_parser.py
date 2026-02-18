"""KM4Work evidence parser.

Handles KM4Work (Knowledge Management for Work) artifacts
like process documentation, SOPs, and work instructions.
Delegates actual parsing to DocumentParser but overrides
category metadata to 'km4work'.
"""

from __future__ import annotations

import logging

from src.evidence.parsers.base import BaseParser, ParseResult
from src.evidence.parsers.document_parser import DocumentParser

logger = logging.getLogger(__name__)


class KM4WorkParser(BaseParser):
    """Parser for KM4Work evidence artifacts.

    Supports the same formats as DocumentParser but tags
    output with km4work category metadata.
    """

    supported_formats = [".km4w", ".km4work"]

    def __init__(self) -> None:
        self._doc_parser = DocumentParser()

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a KM4Work file.

        Strips the .km4w/.km4work extension wrapper and delegates
        to the underlying document parser, then tags the result.

        Args:
            file_path: Path to the file.
            file_name: Original filename.

        Returns:
            ParseResult with km4work category metadata.
        """
        # Parse using document parser
        result = await self._doc_parser.parse(file_path, file_name)

        # Tag with km4work category
        result.metadata["evidence_category"] = "km4work"
        result.metadata["parser"] = "km4work"

        for fragment in result.fragments:
            fragment.metadata["evidence_category"] = "km4work"

        return result

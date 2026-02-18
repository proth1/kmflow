"""Job Aids and Edge Cases evidence parser.

Handles job aids, quick reference guides, edge case documentation,
and exception handling procedures.
"""

from __future__ import annotations

import logging

from src.evidence.parsers.base import BaseParser, ParseResult
from src.evidence.parsers.document_parser import DocumentParser

logger = logging.getLogger(__name__)


class JobAidsParser(BaseParser):
    """Parser for Job Aids and Edge Cases evidence.

    Supports the same formats as DocumentParser but tags
    output with job_aids_edge_cases category metadata.
    """

    supported_formats = [".jobaid", ".edgecase"]

    def __init__(self) -> None:
        self._doc_parser = DocumentParser()

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a Job Aids file.

        Args:
            file_path: Path to the file.
            file_name: Original filename.

        Returns:
            ParseResult with job_aids_edge_cases category metadata.
        """
        result = await self._doc_parser.parse(file_path, file_name)

        result.metadata["evidence_category"] = "job_aids_edge_cases"
        result.metadata["parser"] = "job_aids"

        for fragment in result.fragments:
            fragment.metadata["evidence_category"] = "job_aids_edge_cases"

        return result

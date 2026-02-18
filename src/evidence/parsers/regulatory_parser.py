"""Regulatory document parser for clause extraction.

Parses regulatory and policy documents to extract individual clauses,
obligations, and requirements as structured fragments.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# Patterns for common regulatory clause numbering
_CLAUSE_PATTERNS = [
    # "Section 1.2.3" or "Article 5"
    re.compile(r"^(?:Section|Article|Clause|Part|Rule)\s+[\d.]+", re.IGNORECASE),
    # "1.2.3 Title text" or "(a) Text"
    re.compile(r"^\d+(?:\.\d+)+\s+\S"),
    re.compile(r"^\([a-z]\)\s+\S"),
    # "i. Text" or "ii. Text"
    re.compile(r"^(?:i{1,3}|iv|v|vi{0,3})\.\s+\S", re.IGNORECASE),
]

# Keywords indicating obligations
_OBLIGATION_KEYWORDS = frozenset(
    {
        "shall",
        "must",
        "required",
        "obligated",
        "mandatory",
        "prohibited",
        "shall not",
        "must not",
    }
)


class RegulatoryParser(BaseParser):
    """Parser for regulatory and policy documents.

    Extracts individual clauses and identifies obligations.
    Works with plain text regulatory content.
    """

    supported_formats = [".reg", ".policy"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a regulatory document and extract clauses.

        Reads the document, splits into clauses based on numbering patterns,
        and identifies obligations within each clause.

        Args:
            file_path: Path to the document file.
            file_name: Original filename.

        Returns:
            ParseResult with clause fragments and obligation metadata.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except Exception as e:
                result.error = f"Failed to read file: {e}"
                return result

        result.metadata = {
            "file_name": file_name,
            "total_chars": len(text),
        }

        # Split into clauses
        clauses = self._split_into_clauses(text)
        result.metadata["clause_count"] = len(clauses)

        for i, clause in enumerate(clauses):
            if not clause.strip():
                continue

            has_obligation = self._contains_obligation(clause)
            result.fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TEXT,
                    content=clause.strip(),
                    metadata={
                        "clause_index": i,
                        "has_obligation": has_obligation,
                        "source": "regulatory_clause",
                        "file_name": file_name,
                    },
                )
            )

        return result

    def _split_into_clauses(self, text: str) -> list[str]:
        """Split document text into individual clauses.

        Uses regex patterns to identify clause boundaries.
        Falls back to paragraph splitting if no patterns match.

        Args:
            text: Full document text.

        Returns:
            List of clause strings.
        """
        lines = text.split("\n")
        clauses: list[str] = []
        current_clause: list[str] = []

        for line in lines:
            is_clause_start = any(p.match(line.strip()) for p in _CLAUSE_PATTERNS)
            if is_clause_start and current_clause:
                clauses.append("\n".join(current_clause))
                current_clause = []
            current_clause.append(line)

        if current_clause:
            clauses.append("\n".join(current_clause))

        # If no clause boundaries found, split by double newlines
        if len(clauses) <= 1:
            paragraphs = re.split(r"\n\s*\n", text)
            return [p for p in paragraphs if p.strip()]

        return clauses

    def _contains_obligation(self, text: str) -> bool:
        """Check if a clause contains obligation keywords.

        Args:
            text: Clause text to check.

        Returns:
            True if obligation keywords found.
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in _OBLIGATION_KEYWORDS)

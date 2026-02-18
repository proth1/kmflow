"""Abstract base parser interface for evidence parsing.

All format-specific parsers must implement this interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from src.core.models import FragmentType


@dataclass
class ParsedFragment:
    """A fragment extracted during parsing.

    Attributes:
        fragment_type: The type of fragment (text, table, process_element, etc.).
        content: The textual content of the fragment.
        metadata: Additional metadata about the fragment (page number, position, etc.).
    """

    fragment_type: FragmentType
    content: str
    metadata: dict[str, str | int | float | bool | list[str] | None] = field(default_factory=dict)


@dataclass
class ParseResult:
    """Result of parsing an evidence file.

    Attributes:
        fragments: List of extracted fragments.
        metadata: File-level metadata extracted during parsing.
        error: Error message if parsing partially failed (non-fatal).
    """

    fragments: list[ParsedFragment] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool | list[str] | None] = field(default_factory=dict)
    error: str | None = None


class BaseParser(abc.ABC):
    """Abstract base class for evidence file parsers.

    Subclasses must implement:
    - supported_formats: Class variable listing file extensions this parser handles.
    - parse(): Async method to parse a file and return fragments.
    """

    supported_formats: list[str] = []

    @abc.abstractmethod
    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a file and extract fragments.

        Args:
            file_path: Path to the file on disk.
            file_name: Original filename (used for format detection).

        Returns:
            ParseResult with extracted fragments and metadata.
        """
        ...

    def can_parse(self, file_extension: str) -> bool:
        """Check if this parser supports the given file extension.

        Args:
            file_extension: File extension (e.g., ".pdf", ".docx").

        Returns:
            True if this parser can handle the file format.
        """
        return file_extension.lower() in self.supported_formats

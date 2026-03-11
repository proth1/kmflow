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


def detect_xml_namespace(
    root: object,
    keyword: str,
    fallback_ns: str,
    spec_path: str = "",
) -> dict[str, str]:
    """Detect an XML namespace from a root element.

    Shared utility for BPMN, DMN, and other XML-based parsers.

    Args:
        root: lxml root element.
        keyword: Namespace keyword to search for (e.g., "bpmn", "dmn").
        fallback_ns: Default namespace URI if detection fails.
        spec_path: Optional spec path fragment for URI matching (e.g., "omg.org/spec/BPMN").

    Returns:
        Dict mapping the keyword to the detected namespace URI.
    """
    nsmap: dict[str, str] = {}

    tag = getattr(root, "tag", "")
    if isinstance(tag, str) and tag.startswith("{"):
        ns = tag.split("}")[0].strip("{")
        if keyword in ns.lower() or "omg.org" in ns:
            nsmap[keyword] = ns

    root_nsmap = getattr(root, "nsmap", None) or {}
    for _prefix, uri in root_nsmap.items():
        if uri and (keyword in uri.lower() or (spec_path and spec_path in uri)):
            nsmap[keyword] = uri
            break

    if keyword not in nsmap:
        nsmap[keyword] = fallback_ns

    return nsmap

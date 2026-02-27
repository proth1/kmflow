"""Base metadata extractor interface.

All format-specific metadata extractors must implement this interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedMetadata:
    """Structured metadata extracted from an evidence file.

    Attributes:
        title: Document title extracted from file properties.
        author: Document author from file properties.
        creation_date: File creation/authored date as ISO string.
        modification_date: File last-modified date as ISO string.
        page_count: Number of pages (PDF, DOCX, PPTX).
        file_size_bytes: File size in bytes.
        detected_language: ISO 639-1 language code (e.g., "en", "fr").
        sheet_count: Number of sheets (Excel).
        tabular_metadata: Per-sheet metadata for tabular files.
        extra: Additional format-specific metadata.
    """

    title: str | None = None
    author: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None
    page_count: int | None = None
    file_size_bytes: int | None = None
    detected_language: str | None = None
    sheet_count: int | None = None
    tabular_metadata: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Null values are preserved (not omitted) per BDD requirements.
        """
        result: dict[str, Any] = {
            "title": self.title,
            "author": self.author,
            "creation_date": self.creation_date,
            "modification_date": self.modification_date,
            "page_count": self.page_count,
            "file_size_bytes": self.file_size_bytes,
            "detected_language": self.detected_language,
            "sheet_count": self.sheet_count,
            "tabular_metadata": self.tabular_metadata,
        }
        if self.extra:
            result.update(self.extra)
        return result


def clean_string(value: str | None) -> str | None:
    """Return stripped string or None if empty."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned if cleaned else None


class MetadataExtractor(abc.ABC):
    """Abstract base class for metadata extractors.

    Subclasses must implement:
    - supported_extensions: Class variable listing handled extensions.
    - extract(): Method to extract metadata from a file.
    """

    supported_extensions: list[str] = []

    @abc.abstractmethod
    def extract(self, file_path: str, file_size_bytes: int | None = None) -> ExtractedMetadata:
        """Extract metadata from an evidence file.

        Args:
            file_path: Path to the file on disk.
            file_size_bytes: Pre-computed file size (avoids re-stat).

        Returns:
            ExtractedMetadata with all available fields populated.
        """
        ...

    def can_extract(self, file_extension: str) -> bool:
        """Check if this extractor handles the given extension."""
        return file_extension.lower() in self.supported_extensions

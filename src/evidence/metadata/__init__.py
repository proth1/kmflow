"""Evidence metadata extraction module.

Provides automated metadata extraction from evidence files during ingestion.
"""

from __future__ import annotations

from src.evidence.metadata.base import ExtractedMetadata, MetadataExtractor, clean_string
from src.evidence.metadata.excel import ExcelMetadataExtractor
from src.evidence.metadata.language import detect_language
from src.evidence.metadata.pdf import PdfMetadataExtractor

__all__ = [
    "ExtractedMetadata",
    "ExcelMetadataExtractor",
    "MetadataExtractor",
    "PdfMetadataExtractor",
    "clean_string",
    "detect_language",
]

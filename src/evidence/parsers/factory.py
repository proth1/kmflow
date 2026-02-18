"""Parser factory that routes files to the appropriate parser by format.

Provides a single entry point to select the correct parser based on
file extension and MIME type.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.evidence.parsers.aris_parser import ArisParser
from src.evidence.parsers.audio_parser import AudioParser
from src.evidence.parsers.base import BaseParser, ParseResult
from src.evidence.parsers.bpmn_parser import BpmnParser
from src.evidence.parsers.communication_parser import CommunicationParser
from src.evidence.parsers.controls_parser import ControlsParser
from src.evidence.parsers.document_parser import DocumentParser
from src.evidence.parsers.image_parser import ImageParser
from src.evidence.parsers.job_aids_parser import JobAidsParser
from src.evidence.parsers.km4work_parser import KM4WorkParser
from src.evidence.parsers.regulatory_parser import RegulatoryParser
from src.evidence.parsers.saas_parser import SaaSExportsParser
from src.evidence.parsers.structured_data_parser import StructuredDataParser
from src.evidence.parsers.video_parser import VideoParser
from src.evidence.parsers.visio_parser import VisioParser
from src.evidence.parsers.xes_parser import XesParser

logger = logging.getLogger(__name__)

# Registry of all available parsers
_PARSERS: list[BaseParser] = [
    DocumentParser(),
    StructuredDataParser(),
    BpmnParser(),
    ImageParser(),
    AudioParser(),
    VideoParser(),
    RegulatoryParser(),
    CommunicationParser(),
    VisioParser(),
    XesParser(),
    KM4WorkParser(),
    JobAidsParser(),
    SaaSExportsParser(),
    ControlsParser(),
    ArisParser(),
]

# Extension to EvidenceCategory mapping for auto-classification
EXTENSION_TO_CATEGORY: dict[str, str] = {
    # Documents
    ".pdf": "documents",
    ".docx": "documents",
    ".doc": "documents",
    ".pptx": "documents",
    ".txt": "documents",
    # Structured Data
    ".xlsx": "structured_data",
    ".xls": "structured_data",
    ".csv": "structured_data",
    ".json": "structured_data",
    # BPM Process Models
    ".bpmn": "bpm_process_models",
    ".bpmn2": "bpm_process_models",
    # Images
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".gif": "images",
    ".svg": "images",
    ".tiff": "images",
    ".tif": "images",
    ".bmp": "images",
    # Audio
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".flac": "audio",
    # Video
    ".mp4": "video",
    ".avi": "video",
    ".mov": "video",
    ".mkv": "video",
    ".webm": "video",
    # Regulatory/Policy
    ".reg": "regulatory_policy",
    ".policy": "regulatory_policy",
    # Communications
    ".eml": "domain_communications",
    ".mbox": "domain_communications",
    ".chat": "domain_communications",
    ".msg": "domain_communications",
    # Visio / Process diagrams
    ".vsdx": "bpm_process_models",
    # XES event logs
    ".xes": "structured_data",
    # KM4Work
    ".km4w": "km4work",
    ".km4work": "km4work",
    # Job Aids
    ".jobaid": "job_aids_edge_cases",
    ".edgecase": "job_aids_edge_cases",
    # SaaS Exports
    ".salesforce": "saas_exports",
    ".sap_export": "saas_exports",
    ".servicenow_export": "saas_exports",
    # Controls / Evidence
    ".ctrl": "controls_evidence",
    ".audit": "controls_evidence",
    ".monitor": "controls_evidence",
    # ARIS Process Models
    ".aml": "bpm_process_models",
}

# MIME type to file extension mapping
MIME_TO_EXTENSION: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/xml": ".xml",
    "application/xml": ".xml",
}


def get_parser(file_name: str) -> BaseParser | None:
    """Get the appropriate parser for a file based on its extension.

    Args:
        file_name: The filename (with extension).

    Returns:
        A parser instance, or None if no parser supports the format.
    """
    ext = Path(file_name).suffix.lower()
    for parser in _PARSERS:
        if parser.can_parse(ext):
            return parser
    return None


async def parse_file(file_path: str, file_name: str) -> ParseResult:
    """Parse a file using the appropriate parser.

    Args:
        file_path: Path to the file on disk.
        file_name: Original filename.

    Returns:
        ParseResult with extracted fragments and metadata.
    """
    parser = get_parser(file_name)
    if parser is None:
        return ParseResult(error=f"No parser available for: {file_name}")

    return await parser.parse(file_path, file_name)


def classify_by_extension(file_name: str) -> str | None:
    """Classify a file's evidence category based on its extension.

    Args:
        file_name: The filename (with extension).

    Returns:
        The evidence category string, or None if unknown.
    """
    ext = Path(file_name).suffix.lower()
    return EXTENSION_TO_CATEGORY.get(ext)


def detect_format(file_name: str) -> str:
    """Detect the file format from the filename.

    Args:
        file_name: The filename.

    Returns:
        The file format (extension without the dot), e.g. "pdf", "docx".
    """
    ext = Path(file_name).suffix.lower()
    return ext.lstrip(".") if ext else "unknown"

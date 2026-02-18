"""SaaS Exports parser for cloud platform evidence.

Handles exports from Salesforce, SAP, and ServiceNow platforms.
Delegates structured data parsing to StructuredDataParser and enriches
metadata with SaaS-specific information (source system, object types).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult
from src.evidence.parsers.structured_data_parser import StructuredDataParser

logger = logging.getLogger(__name__)

# Map SaaS extensions to their source system identifier
_EXTENSION_TO_SYSTEM: dict[str, str] = {
    ".salesforce": "salesforce",
    ".sap_export": "sap",
    ".servicenow_export": "servicenow",
}

# Known SaaS entity patterns for metadata enrichment
_SALESFORCE_OBJECTS = frozenset(
    {
        "Account",
        "Contact",
        "Opportunity",
        "Lead",
        "Case",
        "Campaign",
        "Task",
        "Event",
        "User",
        "Profile",
    }
)

_SAP_OBJECTS = frozenset(
    {
        "BKPF",
        "BSEG",
        "MARA",
        "MARC",
        "VBAK",
        "VBAP",
        "EKKO",
        "EKPO",
        "KNA1",
        "LFA1",
    }
)

_SERVICENOW_OBJECTS = frozenset(
    {
        "incident",
        "change_request",
        "problem",
        "cmdb_ci",
        "sys_user",
        "task",
        "kb_knowledge",
        "sc_request",
    }
)


class SaaSExportsParser(BaseParser):
    """Parser for SaaS platform exports.

    Delegates actual data parsing to StructuredDataParser for CSV/JSON
    content, then enriches fragments with SaaS-specific metadata.
    """

    supported_formats = [".salesforce", ".sap_export", ".servicenow_export"]

    def __init__(self) -> None:
        self._data_parser = StructuredDataParser()

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a SaaS export file.

        Detects the source system from the extension, delegates to
        StructuredDataParser for content extraction, and enriches
        metadata with SaaS-specific information.

        Args:
            file_path: Path to the file.
            file_name: Original filename.

        Returns:
            ParseResult with SaaS-enriched metadata.
        """
        path = Path(file_path)
        if not path.exists():
            return ParseResult(error=f"File not found: {file_path}")

        ext = Path(file_name).suffix.lower()
        source_system = _EXTENSION_TO_SYSTEM.get(ext, "unknown")

        # Detect underlying format by reading file content
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                raw = path.read_text(encoding="latin-1")
            except Exception as e:
                return ParseResult(error=f"Failed to read file: {e}")

        underlying_format = self._detect_underlying_format(raw)

        # Delegate to StructuredDataParser with a synthetic filename
        synthetic_name = f"export.{underlying_format}"
        try:
            result = await self._data_parser.parse(file_path, synthetic_name)
        except Exception as e:
            logger.exception("Failed to parse SaaS export: %s", file_name)
            return ParseResult(error=f"SaaS parse error: {e}")

        # Enrich metadata
        result.metadata["evidence_category"] = "saas_exports"
        result.metadata["parser"] = "saas_exports"
        result.metadata["source_system"] = source_system
        result.metadata["file_name"] = file_name

        # Detect SaaS-specific entities from content
        detected_objects = self._detect_saas_objects(raw, source_system)
        if detected_objects:
            result.metadata["detected_objects"] = detected_objects
            result.fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.ENTITY,
                    content=json.dumps({"source_system": source_system, "objects": detected_objects}),
                    metadata={
                        "entity_type": "saas_objects",
                        "source_system": source_system,
                    },
                )
            )

        # Tag all fragments with SaaS metadata
        for fragment in result.fragments:
            fragment.metadata["evidence_category"] = "saas_exports"
            fragment.metadata["source_system"] = source_system

        # Try to extract export date from content
        export_date = self._extract_export_date(raw)
        if export_date:
            result.metadata["export_date"] = export_date

        return result

    def _detect_underlying_format(self, raw: str) -> str:
        """Detect whether the content is JSON or CSV.

        Args:
            raw: Raw file content.

        Returns:
            File extension string: "json" or "csv".
        """
        stripped = raw.strip()
        if stripped.startswith(("{", "[")):
            return "json"
        return "csv"

    def _detect_saas_objects(self, raw: str, source_system: str) -> list[str]:
        """Detect known SaaS object types mentioned in the content.

        Args:
            raw: Raw file content.
            source_system: The SaaS platform identifier.

        Returns:
            List of detected object type names.
        """
        object_sets = {
            "salesforce": _SALESFORCE_OBJECTS,
            "sap": _SAP_OBJECTS,
            "servicenow": _SERVICENOW_OBJECTS,
        }
        known_objects = object_sets.get(source_system, frozenset())
        return sorted(obj for obj in known_objects if obj in raw)

    def _extract_export_date(self, raw: str) -> str | None:
        """Try to extract an export date from the content.

        Looks for common export date patterns in JSON exports.

        Args:
            raw: Raw file content.

        Returns:
            Export date string if found, None otherwise.
        """
        import re

        # Common patterns: "export_date": "2024-01-15", "exported_at": "..."
        patterns = [
            r'"(?:export_date|exported_at|ExportDate|exportDate)"\s*:\s*"([^"]+)"',
            r'"(?:timestamp|created_date|CreatedDate)"\s*:\s*"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, raw)
            if match:
                return match.group(1)
        return None

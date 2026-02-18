"""Visio .vsdx file parser.

Extracts shapes, connectors, and text from Visio diagrams.
A .vsdx file is a ZIP archive containing XML files.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from lxml import etree

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# Visio XML namespaces
VISIO_NS = {
    "v": "http://schemas.microsoft.com/office/visio/2012/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class VisioParser(BaseParser):
    """Parser for Microsoft Visio .vsdx files."""

    supported_formats = [".vsdx"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a Visio diagram and extract shapes and connectors.

        Args:
            file_path: Path to the .vsdx file.
            file_name: Original filename.

        Returns:
            ParseResult with process element fragments.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        try:
            if not zipfile.is_zipfile(file_path):
                result.error = f"Not a valid .vsdx (ZIP) file: {file_name}"
                return result

            with zipfile.ZipFile(file_path, "r") as zf:
                page_files = [
                    name for name in zf.namelist() if name.startswith("visio/pages/page") and name.endswith(".xml")
                ]

                result.metadata = {
                    "file_name": file_name,
                    "page_count": len(page_files),
                    "format": "vsdx",
                }

                shapes_found = 0
                connectors_found = 0

                for page_file in sorted(page_files):
                    page_num = self._extract_page_number(page_file)
                    xml_content = zf.read(page_file)
                    tree = etree.fromstring(xml_content)

                    # Extract shapes
                    shapes = tree.findall(".//v:Shape", VISIO_NS)
                    for shape in shapes:
                        shape_type = self._classify_shape(shape)
                        text = self._extract_shape_text(shape)
                        name_attr = shape.get("Name", "")
                        master_id = shape.get("Master", "")

                        if shape_type == "connector":
                            connectors_found += 1
                            if text:
                                result.fragments.append(
                                    ParsedFragment(
                                        fragment_type=FragmentType.RELATIONSHIP,
                                        content=text,
                                        metadata={
                                            "page": page_num,
                                            "shape_name": name_attr,
                                            "shape_type": "connector",
                                        },
                                    )
                                )
                        else:
                            shapes_found += 1
                            fragment_type = (
                                FragmentType.PROCESS_ELEMENT
                                if shape_type in ("activity", "gateway", "event")
                                else FragmentType.TEXT
                            )
                            content = text if text else f"Shape: {name_attr or 'unnamed'}"
                            result.fragments.append(
                                ParsedFragment(
                                    fragment_type=fragment_type,
                                    content=content,
                                    metadata={
                                        "page": page_num,
                                        "shape_name": name_attr,
                                        "shape_type": shape_type,
                                        "master_id": master_id,
                                    },
                                )
                            )

                result.metadata["shape_count"] = shapes_found
                result.metadata["connector_count"] = connectors_found

        except zipfile.BadZipFile:
            result.error = f"Corrupted .vsdx file: {file_name}"
        except etree.XMLSyntaxError as e:
            result.error = f"Invalid XML in .vsdx file: {e}"
        except Exception as e:
            logger.exception("Failed to parse Visio file: %s", file_name)
            result.error = f"Visio parse error: {e}"

        return result

    @staticmethod
    def _extract_page_number(page_file: str) -> int:
        """Extract page number from a page filename like 'visio/pages/page1.xml'."""
        name = Path(page_file).stem  # e.g., "page1"
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 1

    @staticmethod
    def _extract_shape_text(shape: etree._Element) -> str:
        """Extract text content from a Visio shape element."""
        text_parts: list[str] = []
        for text_elem in shape.findall(".//v:Text", VISIO_NS):
            if text_elem.text and text_elem.text.strip():
                text_parts.append(text_elem.text.strip())
            # Also get text from child elements
            for child in text_elem:
                if child.text and child.text.strip():
                    text_parts.append(child.text.strip())
                if child.tail and child.tail.strip():
                    text_parts.append(child.tail.strip())
        return " ".join(text_parts)

    @staticmethod
    def _classify_shape(shape: etree._Element) -> str:
        """Classify a Visio shape as activity, gateway, event, connector, or other."""
        name = (shape.get("Name") or "").lower()
        shape_type = shape.get("Type", "")

        # Connectors have a specific type or naming convention
        if shape_type == "Foreign" or "connector" in name or "dynamic connector" in name:
            return "connector"

        # Check for Begin/End shapes
        cells = shape.findall(".//v:Cell", VISIO_NS)
        for cell in cells:
            cell_name = (cell.get("N") or "").lower()
            if cell_name == "begintrigger" or cell_name == "endtrigger":
                return "connector"

        # Classify by name patterns
        if any(kw in name for kw in ("process", "task", "activity", "action", "step")):
            return "activity"
        if any(kw in name for kw in ("decision", "gateway", "diamond")):
            return "gateway"
        if any(kw in name for kw in ("start", "end", "terminate", "event")):
            return "event"
        if any(kw in name for kw in ("rectangle", "box")):
            return "activity"

        return "other"

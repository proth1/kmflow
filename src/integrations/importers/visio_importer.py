"""Microsoft Visio VSDX process model importer (Story #328).

Parses Visio VSDX files (ZIP archives containing XML) to extract
process shapes, connections, and swim lane role assignments.

Uses ``defusedxml`` for XXE protection. VSDX format is a ZIP
containing XML parts in ``visio/pages/`` and ``visio/masters/``.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring as safe_fromstring

from src.integrations.importers.model_importer import (
    EdgeType,
    ElementType,
    ImportedModel,
    ImportFormatError,
    ModelImporter,
    ProcessEdge,
    ProcessElement,
)

logger = logging.getLogger(__name__)

# Visio namespace for VSDX XML
VISIO_NS = "http://schemas.microsoft.com/office/visio/2012/main"
VISIO_NS_MAP = {"v": VISIO_NS}

# Visio master shape name patterns mapped to BPMN equivalents
_VISIO_SHAPE_MAP: dict[str, ElementType] = {
    "process": ElementType.TASK,
    "task": ElementType.TASK,
    "activity": ElementType.TASK,
    "decision": ElementType.GATEWAY,
    "gateway": ElementType.GATEWAY,
    "start": ElementType.START_EVENT,
    "end": ElementType.END_EVENT,
    "terminator": ElementType.END_EVENT,
    "subprocess": ElementType.SUBPROCESS,
    "event": ElementType.INTERMEDIATE_EVENT,
    "document": ElementType.UNKNOWN,
    "data": ElementType.UNKNOWN,
}


def _classify_shape(master_name: str, shape_text: str) -> ElementType:
    """Classify a Visio shape to BPMN-equivalent type by master name."""
    lower = master_name.lower()
    for pattern, element_type in _VISIO_SHAPE_MAP.items():
        if pattern in lower:
            return element_type
    # Fallback: if shape has text and looks like an activity
    if shape_text and not master_name:
        return ElementType.TASK
    return ElementType.UNKNOWN


class VisioImporter(ModelImporter):
    """Importer for Microsoft Visio VSDX files."""

    def parse(self, file_path: str | Path) -> ImportedModel:
        """Parse a Visio VSDX file.

        Args:
            file_path: Path to the VSDX file.

        Returns:
            ImportedModel with elements and edges.
        """
        path = Path(file_path)
        model = ImportedModel(source_format="visio_vsdx", source_file=str(path))

        if not path.exists():
            model.errors.append(f"File not found: {path}")
            return model

        if path.suffix.lower() != ".vsdx":
            model.errors.append(f"Unsupported file extension: {path.suffix}")
            return model

        try:
            with zipfile.ZipFile(path, "r") as zf:
                self._validate_vsdx(zf)
                masters = self._parse_masters(zf)
                self._parse_pages(zf, model, masters)
        except zipfile.BadZipFile as exc:
            raise ImportFormatError(
                "Corrupted VSDX file (not a valid ZIP archive)",
                format_name="visio_vsdx",
            ) from exc
        except ParseError as exc:
            model.errors.append(f"XML parse error in VSDX: {exc}")
            return model

        logger.info(
            "Visio import complete: %d elements, %d edges from %s",
            model.element_count,
            model.edge_count,
            path.name,
        )

        return model

    def _validate_vsdx(self, zf: zipfile.ZipFile) -> None:
        """Validate the VSDX archive contains required parts."""
        names = zf.namelist()
        # VSDX must contain visio/pages/ directory
        has_pages = any(n.startswith("visio/pages/page") for n in names)
        if not has_pages:
            raise ImportFormatError(
                "VSDX archive missing visio/pages/ content",
                format_name="visio_vsdx",
            )

    def _parse_masters(self, zf: zipfile.ZipFile) -> dict[str, str]:
        """Parse master shapes to get ID-to-name mapping."""
        masters: dict[str, str] = {}

        try:
            masters_xml = zf.read("visio/masters/masters.xml")
        except KeyError:
            return masters

        root = safe_fromstring(masters_xml)

        for master in root.iter(f"{{{VISIO_NS}}}Master"):
            master_id = master.get("ID", "")
            master_name = master.get("Name", "")
            if master_id and master_name:
                masters[master_id] = master_name

        return masters

    def _parse_pages(
        self,
        zf: zipfile.ZipFile,
        model: ImportedModel,
        masters: dict[str, str],
    ) -> None:
        """Parse all pages in the VSDX archive."""
        page_files = sorted(
            n for n in zf.namelist()
            if n.startswith("visio/pages/page") and n.endswith(".xml")
        )

        for page_file in page_files:
            page_xml = zf.read(page_file)
            root = safe_fromstring(page_xml)
            self._parse_page_shapes(root, model, masters)

    def _parse_page_shapes(
        self,
        root: Any,
        model: ImportedModel,
        masters: dict[str, str],
    ) -> None:
        """Extract shapes and connections from a single page."""
        shape_map: dict[str, ProcessElement] = {}
        connections: list[tuple[str, str, str]] = []  # (from_id, to_id, label)

        for shape in root.iter(f"{{{VISIO_NS}}}Shape"):
            shape_id = shape.get("ID", "")
            master_id = shape.get("Master", "")
            master_name = masters.get(master_id, "")

            # Get shape text
            text = ""
            text_elem = shape.find(f".//{{{VISIO_NS}}}Text")
            if text_elem is not None:
                text = (text_elem.text or "").strip()

            # Check if this is a connector (has Begin/End connections)
            begin_x = shape.find(f".//{{{VISIO_NS}}}Cell[@N='BeginX']")
            end_x = shape.find(f".//{{{VISIO_NS}}}Cell[@N='EndX']")

            if begin_x is not None and end_x is not None:
                # This is a connector — process later via Connects
                continue

            # Classify shape
            element_type = _classify_shape(master_name, text)

            if element_type == ElementType.UNKNOWN and not text:
                continue  # Skip non-process shapes without text

            element = ProcessElement(
                id=shape_id,
                name=text or f"Shape_{shape_id}",
                element_type=element_type,
                source_format="visio_vsdx",
                attributes={"master_name": master_name, "master_id": master_id},
            )
            shape_map[shape_id] = element
            model.elements.append(element)

        # Parse connects (relationships between shapes via connectors)
        for connect in root.iter(f"{{{VISIO_NS}}}Connect"):
            from_sheet = connect.get("FromSheet", "")
            to_sheet = connect.get("ToSheet", "")
            from_cell = connect.get("FromCell", "")

            if from_sheet and to_sheet:
                # Connect records link connector shapes to target shapes
                # FromCell="BeginX" means connector starts at this shape
                # FromCell="EndX" means connector ends at this shape
                connections.append((from_sheet, to_sheet, from_cell))

        # Resolve connector pairs: match Begin->End for each connector
        connector_begins: dict[str, str] = {}  # connector_id -> target_shape_id
        connector_ends: dict[str, str] = {}  # connector_id -> target_shape_id

        for from_sheet, to_sheet, from_cell in connections:
            if from_cell == "BeginX":
                connector_begins[from_sheet] = to_sheet
            elif from_cell == "EndX":
                connector_ends[from_sheet] = to_sheet

        for connector_id, begin_target in connector_begins.items():
            end_target = connector_ends.get(connector_id)
            if end_target and begin_target in shape_map and end_target in shape_map:
                model.edges.append(
                    ProcessEdge(
                        source_id=begin_target,
                        target_id=end_target,
                        edge_type=EdgeType.PRECEDES,
                    )
                )

        # Detect swim lanes by looking for shapes that contain other shapes
        self._detect_lanes(root, model, shape_map, masters)

    def _detect_lanes(
        self,
        root: Any,
        model: ImportedModel,
        shape_map: dict[str, ProcessElement],
        masters: dict[str, str],
    ) -> None:
        """Detect swim lane containers and assign roles."""
        for shape in root.iter(f"{{{VISIO_NS}}}Shape"):
            master_id = shape.get("Master", "")
            master_name = masters.get(master_id, "").lower()

            # Swim lanes/pools are typically "Swimlane", "Functional band", etc.
            if "lane" not in master_name and "band" not in master_name:
                continue

            shape_id = shape.get("ID", "")
            text_elem = shape.find(f".//{{{VISIO_NS}}}Text")
            lane_name = (text_elem.text or "").strip() if text_elem is not None else ""

            if not lane_name:
                continue

            if lane_name not in model.roles:
                model.roles.append(lane_name)

            # Find shapes contained within this lane (child shapes)
            for child_shape in shape.iter(f"{{{VISIO_NS}}}Shape"):
                child_id = child_shape.get("ID", "")
                if child_id != shape_id and child_id in shape_map:
                    shape_map[child_id].lane = lane_name
                    model.edges.append(
                        ProcessEdge(
                            source_id=child_id,
                            target_id=f"role:{lane_name}",
                            edge_type=EdgeType.PERFORMED_BY,
                            label=lane_name,
                        )
                    )

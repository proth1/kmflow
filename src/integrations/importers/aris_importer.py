"""ARIS AML/XML process model importer (Story #328).

Parses ARIS Architect AML (ARIS Markup Language) export files to extract
process elements, sequence flows, and swim lane role assignments.

Uses ``defusedxml`` for XXE protection since AML files are untrusted
external artifacts.

Supports ARIS 9.x and 10.x AML schemas.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import parse as safe_parse

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

# ARIS AML type symbol mappings to BPMN-equivalent types
_ARIS_TYPE_MAP: dict[str, ElementType] = {
    "OT_FUNC": ElementType.TASK,
    "OT_EVT": ElementType.INTERMEDIATE_EVENT,
    "OT_RULE": ElementType.GATEWAY,
    "OT_ORG_UNIT": ElementType.UNKNOWN,
    "OT_ROLE": ElementType.UNKNOWN,
    "OT_FUNC_CLUSTER": ElementType.SUBPROCESS,
}

# Connection types that represent sequence flow
_SEQUENCE_FLOW_TYPES = {"CT_IS_PRED_OF", "CT_LEADS_TO"}

# Connection types for role/org assignment
_ROLE_ASSIGNMENT_TYPES = {"CT_EXEC", "CT_IS_RESP_FOR", "CT_CONTR_TO"}

SUPPORTED_VERSIONS = ["9.x", "10.x"]


class ARISImporter(ModelImporter):
    """Importer for ARIS AML (ARIS Markup Language) XML files."""

    def parse(self, file_path: str | Path) -> ImportedModel:
        """Parse an ARIS AML/XML file.

        Args:
            file_path: Path to the AML file.

        Returns:
            ImportedModel with elements and edges.
        """
        path = Path(file_path)
        model = ImportedModel(source_format="aris_aml", source_file=str(path))

        if not path.exists():
            model.errors.append(f"File not found: {path}")
            return model

        if path.suffix.lower() not in (".aml", ".xml"):
            model.errors.append(f"Unsupported file extension: {path.suffix}")
            return model

        try:
            tree = safe_parse(str(path))
        except ParseError as exc:
            model.errors.append(f"XML parse error: {exc}")
            return model

        root = tree.getroot()

        # Detect AML version from root attributes
        self._validate_version(root)

        # Extract object definitions (process elements)
        obj_map = self._extract_objects(root, model)

        # Extract connections (sequence flows and role assignments)
        self._extract_connections(root, model, obj_map)

        # Extract lanes and create PERFORMED_BY edges
        self._extract_lanes(root, model, obj_map)

        logger.info(
            "ARIS import complete: %d elements, %d edges from %s",
            model.element_count,
            model.edge_count,
            path.name,
        )

        return model

    def _validate_version(self, root: Any) -> None:
        """Check AML version compatibility."""
        # AML files may have version in attributes or header
        version = root.get("Version", root.get("version", ""))
        # Accept 9.x, 10.x, or missing version (assume compatible)
        if version:
            major = version.split(".")[0]
            supported_majors = {v.split(".")[0] for v in SUPPORTED_VERSIONS}
            if major not in supported_majors:
                raise ImportFormatError(
                    "Unsupported ARIS AML version",
                    format_name="aris_aml",
                    detected_version=version,
                    supported_versions=SUPPORTED_VERSIONS,
                )

    def _extract_objects(
        self, root: Any, model: ImportedModel
    ) -> dict[str, ProcessElement]:
        """Extract object definitions from AML."""
        obj_map: dict[str, ProcessElement] = {}

        # AML stores objects in <Group>/<ObjDef> or directly in <ObjDef>
        for obj_def in root.iter("ObjDef"):
            obj_id = obj_def.get("ObjDef.ID", "")
            type_num = obj_def.get("TypeNum", obj_def.get("SymbolNum", ""))
            symbol = obj_def.get("SymbNum", type_num)

            # Get name from AttrDef with AttrTypeNum="AT_NAME"
            name = ""
            for attr_def in obj_def.iter("AttrDef"):
                if attr_def.get("AttrDef.Type", "") == "AT_NAME" or attr_def.get(
                    "AttrTypeNum", ""
                ) == "AT_NAME":
                    # Name is in AttrValue child
                    attr_val = attr_def.find("AttrValue")
                    if attr_val is not None and attr_val.text:
                        name = attr_val.text.strip()
                    break

            if not name:
                # Fallback: use ObjDef text content or ID
                name = obj_def.text.strip() if obj_def.text and obj_def.text.strip() else obj_id

            element_type = _ARIS_TYPE_MAP.get(symbol, ElementType.UNKNOWN)

            element = ProcessElement(
                id=obj_id,
                name=name,
                element_type=element_type,
                source_format="aris_aml",
                attributes={"aris_type": symbol},
            )
            obj_map[obj_id] = element
            model.elements.append(element)

        return obj_map

    def _extract_connections(
        self,
        root: Any,
        model: ImportedModel,
        obj_map: dict[str, ProcessElement],
    ) -> None:
        """Extract connections (edges) from AML."""
        for cxn_def in root.iter("CxnDef"):
            source_id = cxn_def.get("SourceObjDef.IdRef", "")
            target_id = cxn_def.get("TargetObjDef.IdRef", "")
            cxn_type = cxn_def.get("CxnDef.Type", "")

            if not source_id or not target_id:
                continue

            if cxn_type in _SEQUENCE_FLOW_TYPES:
                model.edges.append(
                    ProcessEdge(
                        source_id=source_id,
                        target_id=target_id,
                        edge_type=EdgeType.PRECEDES,
                    )
                )
            elif cxn_type in _ROLE_ASSIGNMENT_TYPES:
                # Role assignment: source is role/org, target is activity
                source_elem = obj_map.get(source_id)
                if source_elem:
                    role_name = source_elem.name
                    if role_name and role_name not in model.roles:
                        model.roles.append(role_name)
                    model.edges.append(
                        ProcessEdge(
                            source_id=target_id,
                            target_id=source_id,
                            edge_type=EdgeType.PERFORMED_BY,
                            label=role_name,
                        )
                    )

    def _extract_lanes(
        self,
        root: Any,
        model: ImportedModel,
        obj_map: dict[str, ProcessElement],
    ) -> None:
        """Extract swim lane assignments from AML Lane elements."""
        for lane in root.iter("Lane"):
            lane_name = ""
            # Lane name from AttrDef
            for attr_def in lane.iter("AttrDef"):
                attr_val = attr_def.find("AttrValue")
                if attr_val is not None and attr_val.text:
                    lane_name = attr_val.text.strip()
                    break

            if not lane_name:
                lane_name = lane.get("Lane.ID", "UnknownLane")

            # Objects referenced in this lane
            for obj_occ in lane.iter("ObjOcc"):
                obj_ref = obj_occ.get("ObjDef.IdRef", "")
                if obj_ref in obj_map:
                    obj_map[obj_ref].lane = lane_name

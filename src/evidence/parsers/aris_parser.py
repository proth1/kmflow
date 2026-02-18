"""ARIS process model parser for .aml files.

Parses ARIS Markup Language (AML) XML exports to extract process elements
(activities, events, roles) and sequence flows (connections).
"""

from __future__ import annotations

import logging
from pathlib import Path

from defusedxml import ElementTree as DefusedET  # noqa: N817

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# ARIS object type symbols mapped to process element types
_ARIS_TYPE_MAP: dict[str, str] = {
    "OT_FUNC": "activity",
    "OT_EVT": "event",
    "OT_ORG_UNIT": "org_unit",
    "OT_ROLE": "role",
    "OT_RULE": "gateway",
    "OT_SYS": "system",
    "OT_APPL_SYS_TYPE": "application",
    "OT_CLST": "cluster",
    "OT_INFO_CARR": "document",
    "OT_KPI": "kpi",
}

# ARIS connection type symbols
_ARIS_CXN_MAP: dict[str, str] = {
    "CT_IS_PREDEC_OF": "sequence_flow",
    "CT_LEADS_TO": "sequence_flow",
    "CT_IS_EVAL_BY": "evaluation",
    "CT_EXEC": "executes",
    "CT_IS_RESP_FOR": "responsible_for",
    "CT_HAS_OUT": "output",
    "CT_CRT_1": "creates",
}


class ArisParser(BaseParser):
    """Parser for ARIS AML export files.

    Extracts ObjDef elements as activities/events/roles and
    CxnDef elements as sequence flows. Returns PROCESS_ELEMENT
    fragments for each discovered element.
    """

    supported_formats = [".aml"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse an ARIS AML file.

        Reads the XML, extracts ObjDef and CxnDef elements,
        and returns process element fragments.

        Args:
            file_path: Path to the .aml file.
            file_name: Original filename.

        Returns:
            ParseResult with process element fragments.
        """
        path = Path(file_path)
        if not path.exists():
            return ParseResult(error=f"File not found: {file_path}")

        try:
            tree = DefusedET.parse(str(path))
        except DefusedET.ParseError as e:
            return ParseResult(error=f"Invalid XML in ARIS file: {e}")
        except Exception as e:
            return ParseResult(error=f"Failed to parse ARIS file: {e}")

        root = tree.getroot()
        fragments: list[ParsedFragment] = []

        # Extract objects (ObjDef)
        objects: dict[str, dict[str, str]] = {}
        for obj_def in root.iter("ObjDef"):
            obj_id = obj_def.get("ObjDef.ID", "")
            type_num = obj_def.get("TypeNum", "")

            # Get the object name from AttrDef with AttrTypeNum "AT_NAME"
            name = ""
            for attr_def in obj_def.iter("AttrDef"):
                if attr_def.get("AttrDef.Type") == "AT_NAME":
                    # Name is in AttrValue child
                    attr_val = attr_def.find("AttrValue")
                    if attr_val is not None and attr_val.text:
                        name = attr_val.text.strip()
                        break

            # Fallback: try PlainText
            if not name:
                for plain in obj_def.iter("PlainText"):
                    text = plain.get("TextValue", "") or (plain.text or "")
                    if text.strip():
                        name = text.strip()
                        break

            element_type = _ARIS_TYPE_MAP.get(type_num, "unknown")
            objects[obj_id] = {"name": name, "type": element_type, "type_num": type_num}

            if name:
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.PROCESS_ELEMENT,
                        content=name,
                        metadata={
                            "aris_id": obj_id,
                            "element_type": element_type,
                            "aris_type_num": type_num,
                            "source": "aris_object",
                        },
                    )
                )

        # Extract connections (CxnDef)
        connections: list[dict[str, str]] = []
        for cxn_def in root.iter("CxnDef"):
            cxn_type = cxn_def.get("CxnDef.Type", "")
            source_id = cxn_def.get("ToObjDef.IdRef", "")
            target_id = cxn_def.get("FromObjDef.IdRef", "")

            # Note: ARIS CxnDef uses ToObjDef/FromObjDef which can be confusing
            # The convention varies; we capture both directions
            if not source_id:
                source_id = cxn_def.get("SourceObjDef.IdRef", "")
            if not target_id:
                target_id = cxn_def.get("TargetObjDef.IdRef", "")

            source_name = objects.get(source_id, {}).get("name", source_id)
            target_name = objects.get(target_id, {}).get("name", target_id)
            flow_type = _ARIS_CXN_MAP.get(cxn_type, "unknown")

            connections.append({
                "source": source_name,
                "target": target_name,
                "type": flow_type,
                "aris_type": cxn_type,
            })

        # Add a summary fragment for connections
        if connections:
            flow_lines = []
            for cxn in connections:
                flow_lines.append(f"{cxn['source']} --[{cxn['type']}]--> {cxn['target']}")

            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.RELATIONSHIP,
                    content="\n".join(flow_lines),
                    metadata={
                        "connection_count": len(connections),
                        "source": "aris_connections",
                    },
                )
            )

        return ParseResult(
            fragments=fragments,
            metadata={
                "file_name": file_name,
                "evidence_category": "bpm_process_models",
                "parser": "aris",
                "format": "aml",
                "object_count": len(objects),
                "connection_count": len(connections),
                "object_types": sorted({o["type"] for o in objects.values() if o["type"] != "unknown"}),
            },
        )

"""BPMN 2.0 XML assembly for the LCD algorithm.

Step 7: Generates valid BPMN 2.0 XML from scored process elements with
activities, gateways, events, sequence flows, and custom properties
for confidence scores and evidence IDs.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET

from src.pov.consensus import ConsensusElement
from src.semantic.entity_extraction import EntityType

logger = logging.getLogger(__name__)

# BPMN 2.0 namespaces
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
KMFLOW_NS = "http://kmflow.ai/bpmn/extensions"

# Entity type to BPMN element mapping
_ENTITY_TO_BPMN = {
    EntityType.ACTIVITY: "task",
    EntityType.DECISION: "exclusiveGateway",
    EntityType.ROLE: "lane",
    EntityType.SYSTEM: "dataStoreReference",
    EntityType.DOCUMENT: "dataObjectReference",
}


def _make_id(prefix: str = "elem") -> str:
    """Generate a unique BPMN element ID."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def assemble_bpmn(
    scored_elements: list[tuple[ConsensusElement, float, str]],
    process_name: str = "Generated Process",
    process_id: str | None = None,
) -> str:
    """Generate BPMN 2.0 XML from scored process elements.

    Creates a valid BPMN process with:
    - Start event
    - Activities for each ACTIVITY entity
    - Exclusive gateways for each DECISION entity
    - End event
    - Sequence flows connecting elements
    - Custom extension properties for confidence and evidence data

    Args:
        scored_elements: List of (element, score, level) tuples.
        process_name: Name for the BPMN process.
        process_id: Optional process ID (generated if not provided).

    Returns:
        BPMN 2.0 XML string.
    """
    if process_id is None:
        process_id = _make_id("process")

    # Register namespaces for clean output
    ET.register_namespace("bpmn", BPMN_NS)
    ET.register_namespace("bpmndi", BPMNDI_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("di", DI_NS)
    ET.register_namespace("kmflow", KMFLOW_NS)

    # Root definitions element
    # Namespace declarations are handled by ET.register_namespace above;
    # only non-namespace attributes go in the attrib dict.
    definitions = ET.Element(
        f"{{{BPMN_NS}}}definitions",
        {
            "id": "Definitions_1",
            "targetNamespace": "http://kmflow.ai/bpmn",
        },
    )

    # Process element
    process_elem = ET.SubElement(
        definitions,
        f"{{{BPMN_NS}}}process",
        {"id": process_id, "name": process_name, "isExecutable": "false"},
    )

    # Collect flow elements for sequence flows
    flow_node_ids: list[str] = []

    # Start event
    start_id = _make_id("start")
    ET.SubElement(process_elem, f"{{{BPMN_NS}}}startEvent", {"id": start_id, "name": "Start"})
    flow_node_ids.append(start_id)

    # Filter to activities and decisions for the flow
    activities = [
        (elem, score, level)
        for elem, score, level in scored_elements
        if elem.triangulated.entity.entity_type in (EntityType.ACTIVITY, EntityType.DECISION)
    ]

    # Sort by confidence score descending for optimal ordering
    activities.sort(key=lambda x: x[1], reverse=True)

    # Create BPMN elements
    for elem, score, level in activities:
        entity = elem.triangulated.entity
        elem_id = _make_id("elem")

        if entity.entity_type == EntityType.ACTIVITY:
            bpmn_tag = f"{{{BPMN_NS}}}task"
        elif entity.entity_type == EntityType.DECISION:
            bpmn_tag = f"{{{BPMN_NS}}}exclusiveGateway"
        else:
            continue

        bpmn_elem = ET.SubElement(
            process_elem,
            bpmn_tag,
            {"id": elem_id, "name": entity.name},
        )

        # Add extension elements for confidence and evidence
        ext_elements = ET.SubElement(bpmn_elem, f"{{{BPMN_NS}}}extensionElements")

        # Confidence score
        ET.SubElement(
            ext_elements,
            f"{{{KMFLOW_NS}}}confidence",
            {"score": f"{score:.4f}", "level": level},
        )

        # Evidence IDs
        ET.SubElement(
            ext_elements,
            f"{{{KMFLOW_NS}}}evidence",
            {
                "source_count": str(elem.triangulated.source_count),
                "ids": ",".join(elem.triangulated.evidence_ids),
            },
        )

        flow_node_ids.append(elem_id)

    # End event
    end_id = _make_id("end")
    ET.SubElement(process_elem, f"{{{BPMN_NS}}}endEvent", {"id": end_id, "name": "End"})
    flow_node_ids.append(end_id)

    # Sequence flows connecting all elements linearly
    for i in range(len(flow_node_ids) - 1):
        flow_id = _make_id("flow")
        ET.SubElement(
            process_elem,
            f"{{{BPMN_NS}}}sequenceFlow",
            {
                "id": flow_id,
                "sourceRef": flow_node_ids[i],
                "targetRef": flow_node_ids[i + 1],
            },
        )

    # Add data store references for systems
    systems = [
        (elem, score, level)
        for elem, score, level in scored_elements
        if elem.triangulated.entity.entity_type == EntityType.SYSTEM
    ]
    for elem, _score, _level in systems:
        ds_id = _make_id("dataStore")
        ET.SubElement(
            process_elem,
            f"{{{BPMN_NS}}}dataStoreReference",
            {"id": ds_id, "name": elem.triangulated.entity.name},
        )

    # Add data object references for documents
    documents = [
        (elem, score, level)
        for elem, score, level in scored_elements
        if elem.triangulated.entity.entity_type == EntityType.DOCUMENT
    ]
    for elem, _score, _level in documents:
        do_id = _make_id("dataObject")
        ET.SubElement(
            process_elem,
            f"{{{BPMN_NS}}}dataObjectReference",
            {"id": do_id, "name": elem.triangulated.entity.name},
        )

    # Generate XML string
    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ")

    # Convert to string
    xml_str = ET.tostring(definitions, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    logger.info(
        "Assembled BPMN with %d flow nodes, %d systems, %d documents",
        len(flow_node_ids),
        len(systems),
        len(documents),
    )

    return xml_str

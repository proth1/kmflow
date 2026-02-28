"""BPMN 2.0 XML assembly for the LCD algorithm.

Step 9: Generates valid BPMN 2.0 XML from scored process elements with
activities, gateways, events, sequence flows, and custom properties
for three-dimensional confidence scores, evidence citations, gap markers,
and variant annotations.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET

from src.pov.consensus import ConsensusElement, VariantAnnotation
from src.pov.constants import (
    BRIGHTNESS_BRIGHT_THRESHOLD,
    BRIGHTNESS_DIM_THRESHOLD,
    GRADES_CAPPED_AT_DIM,
    MVC_THRESHOLD,
)
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


def _classify_brightness(score: float, evidence_grade: str) -> str:
    """Classify brightness from score and evidence grade.

    Applies the coherence constraint: grades D or U cap brightness at DIM
    regardless of the numeric score.

    Args:
        score: Confidence score between 0 and 1.
        evidence_grade: Evidence grade (A, B, C, D, U).

    Returns:
        Brightness classification: BRIGHT, DIM, or DARK.
    """
    # Score-based brightness
    if score >= BRIGHTNESS_BRIGHT_THRESHOLD:
        score_brightness = "BRIGHT"
    elif score >= BRIGHTNESS_DIM_THRESHOLD:
        score_brightness = "DIM"
    else:
        score_brightness = "DARK"

    # Grade-based cap
    grade_brightness = "DIM" if evidence_grade in GRADES_CAPPED_AT_DIM else "BRIGHT"

    # Coherence: take minimum (DARK < DIM < BRIGHT)
    brightness_order = {"DARK": 0, "DIM": 1, "BRIGHT": 2}
    min_val = min(brightness_order[score_brightness], brightness_order[grade_brightness])
    return {0: "DARK", 1: "DIM", 2: "BRIGHT"}[min_val]


def _determine_evidence_grade(element: ConsensusElement) -> str:
    """Determine evidence grade (A-U) for a consensus element.

    Grade logic from PRD Section 6.3:
    - A: 3+ sources from 2+ evidence planes (strong multi-plane corroboration)
    - B: 2+ sources with some validation
    - C: 2+ sources but unvalidated
    - D: Single source
    - U: No evidence

    Args:
        element: The consensus element with triangulation data.

    Returns:
        Evidence grade string: A, B, C, D, or U.
    """
    tri = element.triangulated
    source_count = tri.source_count
    evidence_ids = tri.evidence_ids

    if not evidence_ids or source_count == 0:
        return "U"
    if source_count == 1:
        return "D"

    # Check for multi-plane coverage (from triangulation data)
    plane_count = len(tri.supporting_planes)
    if source_count >= 3 and plane_count >= 2:
        return "A"
    if source_count >= 2 and plane_count >= 2:
        return "B"
    # 2+ sources but single plane (unvalidated cross-plane)
    return "C"


def _add_confidence_extensions(
    ext_elements: ET.Element,
    elem: ConsensusElement,
    score: float,
    level: str,
) -> tuple[str, str]:
    """Add three-dimensional confidence extensions to a BPMN element.

    Adds:
    - kmflow:confidence with score, level, brightness, evidence_grade
    - kmflow:evidence with source_count and evidence IDs

    Args:
        ext_elements: The extensionElements XML node.
        elem: The consensus element.
        score: Confidence score.
        level: Confidence level string.

    Returns:
        Tuple of (brightness, evidence_grade) for use in gap detection.
    """
    evidence_grade = _determine_evidence_grade(elem)
    brightness = _classify_brightness(score, evidence_grade)

    # Three-dimensional confidence
    ET.SubElement(
        ext_elements,
        f"{{{KMFLOW_NS}}}confidence",
        {
            "score": f"{score:.4f}",
            "level": level,
            "brightness": brightness,
            "evidence_grade": evidence_grade,
        },
    )

    # Evidence citations
    ET.SubElement(
        ext_elements,
        f"{{{KMFLOW_NS}}}evidence",
        {
            "source_count": str(elem.triangulated.source_count),
            "ids": ",".join(elem.triangulated.evidence_ids),
        },
    )

    return brightness, evidence_grade


def _add_gap_marker(
    ext_elements: ET.Element,
    element_name: str,
    score: float,
) -> None:
    """Add a gap marker annotation for DARK elements below MVC threshold.

    Args:
        ext_elements: The extensionElements XML node.
        element_name: Name of the element for the gap description.
        score: The element's confidence score.
    """
    ET.SubElement(
        ext_elements,
        f"{{{KMFLOW_NS}}}gapMarker",
        {
            "type": "insufficient_evidence",
            "description": f"'{element_name}' has confidence {score:.2f} below MVC threshold {MVC_THRESHOLD}",
            "requires_additional_evidence": "true",
        },
    )


def _add_variant_annotation(
    ext_elements: ET.Element,
    variant: VariantAnnotation,
) -> None:
    """Add variant annotation to a BPMN element.

    Args:
        ext_elements: The extensionElements XML node.
        variant: The variant annotation data.
    """
    ET.SubElement(
        ext_elements,
        f"{{{KMFLOW_NS}}}variant",
        {
            "label": variant.variant_label,
            "evidence_count": str(len(variant.evidence_ids)),
            "evidence_ids": ",".join(variant.evidence_ids),
            "coverage": f"{variant.evidence_coverage:.4f}",
        },
    )


def assemble_bpmn(
    scored_elements: list[tuple[ConsensusElement, float, str]],
    process_name: str = "Generated Process",
    process_id: str | None = None,
    variants: list[VariantAnnotation] | None = None,
) -> str:
    """Generate BPMN 2.0 XML from scored process elements.

    Creates a valid BPMN process with:
    - Start event
    - Activities for each ACTIVITY entity
    - Exclusive gateways for each DECISION entity
    - End event
    - Sequence flows connecting elements
    - Three-dimensional confidence (score + brightness + evidence_grade)
    - Evidence citations on every element
    - Gap markers on DARK elements below MVC threshold
    - Variant annotations for multi-path evidence

    Args:
        scored_elements: List of (element, score, level) tuples.
        process_name: Name for the BPMN process.
        process_id: Optional process ID (generated if not provided).
        variants: Optional list of variant annotations from consensus.

    Returns:
        BPMN 2.0 XML string.
    """
    if process_id is None:
        process_id = _make_id("process")

    variants = variants or []

    # Build variant lookup: element_name → list[VariantAnnotation]
    variant_map: dict[str, list[VariantAnnotation]] = {}
    for v in variants:
        variant_map.setdefault(v.element_name, []).append(v)

    # Register namespaces for clean output
    ET.register_namespace("bpmn", BPMN_NS)
    ET.register_namespace("bpmndi", BPMNDI_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("di", DI_NS)
    ET.register_namespace("kmflow", KMFLOW_NS)

    # Root definitions element
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
    gap_count = 0

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

        # Add extension elements for three-dimensional confidence + evidence
        ext_elements = ET.SubElement(bpmn_elem, f"{{{BPMN_NS}}}extensionElements")
        brightness, _evidence_grade = _add_confidence_extensions(ext_elements, elem, score, level)

        # Gap marker for DARK elements
        if brightness == "DARK" and score < MVC_THRESHOLD:
            _add_gap_marker(ext_elements, entity.name, score)
            gap_count += 1

        # Variant annotations
        if entity.name in variant_map:
            for variant in variant_map[entity.name]:
                _add_variant_annotation(ext_elements, variant)

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
        "Assembled BPMN with %d flow nodes, %d systems, %d documents, %d gaps",
        len(flow_node_ids),
        len(systems),
        len(documents),
        gap_count,
    )

    return xml_str

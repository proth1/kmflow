"""Auto-generate BPMN 2.0 XML from POV activities.

Takes a list of process activities with sequence information and produces
valid BPMN 2.0 XML with task nodes, sequence flows, start/end events,
and optional exclusive gateways for decision points.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

# Layout constants (matching KMFlow BPMN standards)
TASK_WIDTH = 100
TASK_HEIGHT = 80
GATEWAY_SIZE = 50
EVENT_SIZE = 36
H_SPACING = 52  # Edge-to-edge horizontal gap
LANE_Y_START = 100
LANE_X_START = 247


@dataclass
class BPMNActivity:
    """An activity to include in the generated BPMN model."""

    id: str = ""
    name: str = ""
    performer_role: str | None = None
    is_gateway: bool = False
    gateway_paths: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"Activity_{uuid.uuid4().hex[:8]}"


def _build_bpmn_process(
    definitions: ET.Element,
    process_name: str,
    activities: list[BPMNActivity],
) -> tuple[str, str, str, list[str], list[tuple[str, str, str]]]:
    """Add the process element with all tasks and flows to definitions.

    Returns:
        (process_id, start_id, end_id, task_ids, flow_elements)
    """
    process_id = f"Process_{uuid.uuid4().hex[:8]}"
    process = ET.SubElement(
        definitions,
        f"{{{BPMN_NS}}}process",
        {"id": process_id, "name": process_name, "isExecutable": "true"},
    )

    start_id = f"StartEvent_{uuid.uuid4().hex[:8]}"
    ET.SubElement(process, f"{{{BPMN_NS}}}startEvent", {"id": start_id, "name": "Start"})

    end_id = f"EndEvent_{uuid.uuid4().hex[:8]}"
    ET.SubElement(process, f"{{{BPMN_NS}}}endEvent", {"id": end_id, "name": "End"})

    task_ids: list[str] = []
    for activity in activities:
        task_id = activity.id
        task_ids.append(task_id)
        tag = f"{{{BPMN_NS}}}exclusiveGateway" if activity.is_gateway else f"{{{BPMN_NS}}}task"
        ET.SubElement(process, tag, {"id": task_id, "name": activity.name})

    flow_elements: list[tuple[str, str, str]] = []

    def _add_flow(src: str, tgt: str) -> None:
        fid = f"Flow_{uuid.uuid4().hex[:8]}"
        flow_elements.append((fid, src, tgt))
        ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", {"id": fid, "sourceRef": src, "targetRef": tgt})

    _add_flow(start_id, task_ids[0])
    for i in range(len(task_ids) - 1):
        _add_flow(task_ids[i], task_ids[i + 1])
    _add_flow(task_ids[-1], end_id)

    return process_id, start_id, end_id, task_ids, flow_elements


def _build_bpmn_diagram_layout(
    definitions: ET.Element,
    process_id: str,
    start_id: str,
    end_id: str,
    task_ids: list[str],
    flow_elements: list[tuple[str, str, str]],
) -> None:
    """Append BPMNDiagram layout section to definitions (left-to-right)."""
    diagram = ET.SubElement(definitions, f"{{{BPMNDI_NS}}}BPMNDiagram", {"id": f"BPMNDiagram_{uuid.uuid4().hex[:8]}"})
    plane = ET.SubElement(
        diagram, f"{{{BPMNDI_NS}}}BPMNPlane", {"id": f"BPMNPlane_{uuid.uuid4().hex[:8]}", "bpmnElement": process_id}
    )

    x = LANE_X_START
    y = LANE_Y_START

    _add_shape(plane, start_id, x, y + (TASK_HEIGHT - EVENT_SIZE) // 2, EVENT_SIZE, EVENT_SIZE)
    x += EVENT_SIZE + H_SPACING

    element_positions: dict[str, tuple[int, int]] = {start_id: (LANE_X_START, y)}
    for task_id in task_ids:
        _add_shape(plane, task_id, x, y, TASK_WIDTH, TASK_HEIGHT)
        element_positions[task_id] = (x, y)
        x += TASK_WIDTH + H_SPACING

    _add_shape(plane, end_id, x, y + (TASK_HEIGHT - EVENT_SIZE) // 2, EVENT_SIZE, EVENT_SIZE)
    element_positions[end_id] = (x, y)

    for fid, src, tgt in flow_elements:
        _add_edge(plane, fid, element_positions, src, tgt)


def generate_bpmn_xml(
    process_name: str,
    activities: list[BPMNActivity],
    engagement_id: str | None = None,
) -> str:
    """Generate BPMN 2.0 XML from a list of activities.

    Creates a simple left-to-right process with start event, task nodes
    connected by sequence flows, and an end event.

    Args:
        process_name: Name of the process.
        activities: Ordered list of activities to include.
        engagement_id: Optional engagement ID for metadata.

    Returns:
        BPMN 2.0 XML string.
    """
    if not activities:
        return _empty_bpmn(process_name)

    ET.register_namespace("bpmn", BPMN_NS)
    ET.register_namespace("bpmndi", BPMNDI_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("di", DI_NS)

    definitions = ET.Element(
        f"{{{BPMN_NS}}}definitions",
        {"id": f"Definitions_{uuid.uuid4().hex[:8]}", "targetNamespace": "http://bpmn.io/schema/bpmn"},
    )

    process_id, start_id, end_id, task_ids, flow_elements = _build_bpmn_process(definitions, process_name, activities)
    _build_bpmn_diagram_layout(definitions, process_id, start_id, end_id, task_ids, flow_elements)

    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", xml_declaration=True)


def _empty_bpmn(process_name: str) -> str:
    """Generate minimal BPMN with just start and end events."""
    ET.register_namespace("bpmn", BPMN_NS)
    definitions = ET.Element(
        f"{{{BPMN_NS}}}definitions",
        {
            "id": f"Definitions_{uuid.uuid4().hex[:8]}",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
        },
    )
    process = ET.SubElement(
        definitions,
        f"{{{BPMN_NS}}}process",
        {
            "id": f"Process_{uuid.uuid4().hex[:8]}",
            "name": process_name,
            "isExecutable": "true",
        },
    )
    ET.SubElement(process, f"{{{BPMN_NS}}}startEvent", {"id": "Start", "name": "Start"})
    ET.SubElement(process, f"{{{BPMN_NS}}}endEvent", {"id": "End", "name": "End"})
    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", xml_declaration=True)


def _add_shape(
    plane: ET.Element,
    element_id: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Add a BPMNShape element to the diagram plane."""
    shape = ET.SubElement(
        plane,
        f"{{{BPMNDI_NS}}}BPMNShape",
        {
            "id": f"{element_id}_di",
            "bpmnElement": element_id,
        },
    )
    ET.SubElement(
        shape,
        f"{{{DC_NS}}}Bounds",
        {
            "x": str(x),
            "y": str(y),
            "width": str(width),
            "height": str(height),
        },
    )


def _add_edge(
    plane: ET.Element,
    flow_id: str,
    positions: dict[str, tuple[int, int]],
    src: str,
    tgt: str,
) -> None:
    """Add a BPMNEdge element to the diagram plane."""
    edge = ET.SubElement(
        plane,
        f"{{{BPMNDI_NS}}}BPMNEdge",
        {
            "id": f"{flow_id}_di",
            "bpmnElement": flow_id,
        },
    )
    src_pos = positions.get(src, (0, 0))
    tgt_pos = positions.get(tgt, (0, 0))

    # Simple straight line from right edge of source to left edge of target
    ET.SubElement(
        edge,
        f"{{{DI_NS}}}waypoint",
        {
            "x": str(src_pos[0] + TASK_WIDTH),
            "y": str(src_pos[1] + TASK_HEIGHT // 2),
        },
    )
    ET.SubElement(
        edge,
        f"{{{DI_NS}}}waypoint",
        {
            "x": str(tgt_pos[0]),
            "y": str(tgt_pos[1] + TASK_HEIGHT // 2),
        },
    )

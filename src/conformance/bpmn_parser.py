"""BPMN XML parser for conformance checking.

Parses BPMN 2.0 XML into a graph representation suitable for
alignment and conformance analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import defusedxml.ElementTree as ET  # noqa: N817

logger = logging.getLogger(__name__)

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


@dataclass
class BPMNElement:
    """A parsed BPMN element (task, gateway, event, etc.)."""
    id: str
    name: str
    element_type: str  # "task", "gateway", "startEvent", "endEvent", etc.
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class BPMNFlow:
    """A sequence flow connecting two BPMN elements."""
    id: str
    source_id: str
    target_id: str
    name: str = ""
    condition: str | None = None


@dataclass
class BPMNGraph:
    """Graph representation of a BPMN process model."""
    elements: dict[str, BPMNElement] = field(default_factory=dict)
    flows: list[BPMNFlow] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)

    @property
    def tasks(self) -> list[BPMNElement]:
        return [e for e in self.elements.values() if e.element_type in ("task", "userTask", "serviceTask", "sendTask", "receiveTask", "scriptTask", "manualTask", "businessRuleTask")]

    @property
    def gateways(self) -> list[BPMNElement]:
        return [e for e in self.elements.values() if "gateway" in e.element_type.lower()]

    @property
    def events(self) -> list[BPMNElement]:
        return [e for e in self.elements.values() if "event" in e.element_type.lower()]


def parse_bpmn_xml(bpmn_xml: str) -> BPMNGraph:
    """Parse BPMN XML string into a BPMNGraph.

    Args:
        bpmn_xml: Raw BPMN 2.0 XML string.

    Returns:
        BPMNGraph with elements, flows, and adjacency list.
    """
    graph = BPMNGraph()

    try:
        root = ET.fromstring(bpmn_xml)
    except ET.ParseError as e:
        logger.error("Failed to parse BPMN XML: %s", e)
        return graph

    # Find all process elements
    for process in root.iter(f"{{{BPMN_NS}}}process"):
        _parse_process(process, graph)

    # Also check for processes without namespace (common in some exports)
    if not graph.elements:
        for process in root.iter("process"):
            _parse_process(process, graph)

    # Build adjacency list from flows
    for flow in graph.flows:
        if flow.source_id not in graph.adjacency:
            graph.adjacency[flow.source_id] = []
        graph.adjacency[flow.source_id].append(flow.target_id)

    return graph


def _parse_process(process: ET.Element, graph: BPMNGraph) -> None:
    """Parse a single BPMN process element."""
    element_types = [
        "task", "userTask", "serviceTask", "sendTask", "receiveTask",
        "scriptTask", "manualTask", "businessRuleTask",
        "exclusiveGateway", "parallelGateway", "inclusiveGateway",
        "eventBasedGateway", "complexGateway",
        "startEvent", "endEvent", "intermediateThrowEvent",
        "intermediateCatchEvent", "boundaryEvent",
        "subProcess", "callActivity",
    ]

    for elem_type in element_types:
        # Try with namespace
        for elem in process.iter(f"{{{BPMN_NS}}}{elem_type}"):
            _add_element(elem, elem_type, graph)
        # Try without namespace
        for elem in process.iter(elem_type):
            elem_id = elem.get("id", "")
            if elem_id and elem_id not in graph.elements:
                _add_element(elem, elem_type, graph)

    # Parse sequence flows
    for flow in process.iter(f"{{{BPMN_NS}}}sequenceFlow"):
        _add_flow(flow, graph)
    for flow in process.iter("sequenceFlow"):
        flow_id = flow.get("id", "")
        if flow_id and not any(f.id == flow_id for f in graph.flows):
            _add_flow(flow, graph)


def _add_element(elem: ET.Element, elem_type: str, graph: BPMNGraph) -> None:
    """Add a BPMN element to the graph."""
    elem_id = elem.get("id", "")
    if not elem_id:
        return
    name = elem.get("name", elem_id)
    graph.elements[elem_id] = BPMNElement(
        id=elem_id,
        name=name,
        element_type=elem_type,
    )


def _add_flow(flow: ET.Element, graph: BPMNGraph) -> None:
    """Add a sequence flow to the graph."""
    flow_id = flow.get("id", "")
    source = flow.get("sourceRef", "")
    target = flow.get("targetRef", "")
    if not (flow_id and source and target):
        return

    condition = None
    cond_elem = flow.find(f"{{{BPMN_NS}}}conditionExpression")
    if cond_elem is not None and cond_elem.text:
        condition = cond_elem.text

    graph.flows.append(BPMNFlow(
        id=flow_id,
        source_id=source,
        target_id=target,
        name=flow.get("name", ""),
        condition=condition,
    ))

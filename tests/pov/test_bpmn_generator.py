"""Tests for the POV BPMN generator module."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.pov.bpmn_generator import (
    BPMN_NS,
    BPMNDI_NS,
    DC_NS,
    EVENT_SIZE,
    TASK_HEIGHT,
    TASK_WIDTH,
    BPMNActivity,
    generate_bpmn_xml,
)


class TestBPMNActivity:
    """Tests for the BPMNActivity dataclass."""

    def test_auto_id_generation(self) -> None:
        activity = BPMNActivity(name="Test Task")
        assert activity.id.startswith("Activity_")
        assert len(activity.id) > 9

    def test_explicit_id(self) -> None:
        activity = BPMNActivity(id="custom_id", name="Test Task")
        assert activity.id == "custom_id"

    def test_default_values(self) -> None:
        activity = BPMNActivity(name="Test")
        assert activity.performer_role is None
        assert activity.is_gateway is False
        assert activity.gateway_paths == []
        assert activity.confidence == 0.0


class TestGenerateBpmnXml:
    """Tests for generate_bpmn_xml."""

    def _parse(self, xml_str: str) -> ET.Element:
        return ET.fromstring(xml_str)

    def test_empty_activities_produces_minimal_bpmn(self) -> None:
        xml_str = generate_bpmn_xml("Empty Process", [])
        root = self._parse(xml_str)

        assert root.tag == f"{{{BPMN_NS}}}definitions"

        processes = root.findall(f".//{{{BPMN_NS}}}process")
        assert len(processes) == 1
        assert processes[0].get("name") == "Empty Process"

        starts = root.findall(f".//{{{BPMN_NS}}}startEvent")
        assert len(starts) == 1
        ends = root.findall(f".//{{{BPMN_NS}}}endEvent")
        assert len(ends) == 1

    def test_single_activity(self) -> None:
        activities = [BPMNActivity(id="task1", name="Submit Form")]
        xml_str = generate_bpmn_xml("Simple Process", activities)
        root = self._parse(xml_str)

        tasks = root.findall(f".//{{{BPMN_NS}}}task")
        assert len(tasks) == 1
        assert tasks[0].get("name") == "Submit Form"

        flows = root.findall(f".//{{{BPMN_NS}}}sequenceFlow")
        assert len(flows) == 2  # start->task, task->end

    def test_multiple_activities(self) -> None:
        activities = [
            BPMNActivity(id="t1", name="Step 1"),
            BPMNActivity(id="t2", name="Step 2"),
            BPMNActivity(id="t3", name="Step 3"),
        ]
        xml_str = generate_bpmn_xml("Multi Step", activities)
        root = self._parse(xml_str)

        tasks = root.findall(f".//{{{BPMN_NS}}}task")
        assert len(tasks) == 3

        flows = root.findall(f".//{{{BPMN_NS}}}sequenceFlow")
        assert len(flows) == 4  # start->t1, t1->t2, t2->t3, t3->end

    def test_sequence_flow_connections(self) -> None:
        activities = [
            BPMNActivity(id="t1", name="A"),
            BPMNActivity(id="t2", name="B"),
        ]
        xml_str = generate_bpmn_xml("Flow Test", activities)
        root = self._parse(xml_str)

        flows = root.findall(f".//{{{BPMN_NS}}}sequenceFlow")
        # start->t1
        assert any(f.get("targetRef") == "t1" for f in flows)
        # t1->t2
        assert any(f.get("sourceRef") == "t1" and f.get("targetRef") == "t2" for f in flows)
        # t2->end
        assert any(f.get("sourceRef") == "t2" for f in flows)

    def test_bpmn_diagram_elements(self) -> None:
        activities = [BPMNActivity(id="t1", name="Task")]
        xml_str = generate_bpmn_xml("Diagram Test", activities)
        root = self._parse(xml_str)

        diagrams = root.findall(f".//{{{BPMNDI_NS}}}BPMNDiagram")
        assert len(diagrams) == 1

        plane = root.find(f".//{{{BPMNDI_NS}}}BPMNPlane")
        assert plane is not None

        shapes = root.findall(f".//{{{BPMNDI_NS}}}BPMNShape")
        # start event + task + end event = 3 shapes
        assert len(shapes) == 3

        edges = root.findall(f".//{{{BPMNDI_NS}}}BPMNEdge")
        assert len(edges) == 2  # start->task, task->end

    def test_shape_dimensions(self) -> None:
        activities = [BPMNActivity(id="t1", name="Task")]
        xml_str = generate_bpmn_xml("Dim Test", activities)
        root = self._parse(xml_str)

        shapes = root.findall(f".//{{{BPMNDI_NS}}}BPMNShape")
        task_shape = None
        for shape in shapes:
            if shape.get("bpmnElement") == "t1":
                task_shape = shape
                break

        assert task_shape is not None
        bounds = task_shape.find(f"{{{DC_NS}}}Bounds")
        assert bounds is not None
        assert bounds.get("width") == str(TASK_WIDTH)
        assert bounds.get("height") == str(TASK_HEIGHT)

    def test_start_event_dimensions(self) -> None:
        activities = [BPMNActivity(id="t1", name="Task")]
        xml_str = generate_bpmn_xml("Event Dim", activities)
        root = self._parse(xml_str)

        shapes = root.findall(f".//{{{BPMNDI_NS}}}BPMNShape")
        # Find start event shape (first one created)
        start_shape = shapes[0]
        bounds = start_shape.find(f"{{{DC_NS}}}Bounds")
        assert bounds is not None
        assert bounds.get("width") == str(EVENT_SIZE)
        assert bounds.get("height") == str(EVENT_SIZE)

    def test_xml_declaration(self) -> None:
        xml_str = generate_bpmn_xml("Test", [])
        assert xml_str.startswith("<?xml version=")

    def test_process_is_executable(self) -> None:
        xml_str = generate_bpmn_xml("Exec Test", [])
        root = self._parse(xml_str)
        process = root.find(f".//{{{BPMN_NS}}}process")
        assert process is not None
        assert process.get("isExecutable") == "true"

    def test_layout_left_to_right(self) -> None:
        activities = [
            BPMNActivity(id="t1", name="A"),
            BPMNActivity(id="t2", name="B"),
            BPMNActivity(id="t3", name="C"),
        ]
        xml_str = generate_bpmn_xml("Layout Test", activities)
        root = self._parse(xml_str)

        shapes = root.findall(f".//{{{BPMNDI_NS}}}BPMNShape")
        x_positions = []
        for shape in shapes:
            bounds = shape.find(f"{{{DC_NS}}}Bounds")
            if bounds is not None:
                x_positions.append(int(bounds.get("x", "0")))

        # All x positions should be strictly increasing (left to right)
        for i in range(len(x_positions) - 1):
            assert x_positions[i] < x_positions[i + 1], (
                f"Shape {i} at x={x_positions[i]} should be left of shape {i + 1} at x={x_positions[i + 1]}"
            )

    def test_gateway_renders_as_exclusive_gateway(self) -> None:
        """The is_gateway flag should render as exclusiveGateway."""
        activities = [
            BPMNActivity(id="t1", name="Check", is_gateway=True, gateway_paths=["Yes", "No"]),
        ]
        xml_str = generate_bpmn_xml("Gateway Test", activities)
        root = self._parse(xml_str)

        gateways = root.findall(f".//{{{BPMN_NS}}}exclusiveGateway")
        assert len(gateways) == 1
        assert gateways[0].get("name") == "Check"

        # No regular tasks
        tasks = root.findall(f".//{{{BPMN_NS}}}task")
        assert len(tasks) == 0

    def test_engagement_id_metadata(self) -> None:
        activities = [BPMNActivity(id="t1", name="Task")]
        xml_str = generate_bpmn_xml("Meta Test", activities, engagement_id="eng-123")
        # Should not crash with engagement_id
        assert "Meta Test" in xml_str

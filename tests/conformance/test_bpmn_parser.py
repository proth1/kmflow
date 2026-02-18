"""Tests for BPMN XML parser (src/conformance/bpmn_parser.py)."""

from __future__ import annotations

from src.conformance.bpmn_parser import parse_bpmn_xml

SAMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="Start" name="Start"/>
    <bpmn:task id="Task_1" name="Review Document"/>
    <bpmn:exclusiveGateway id="Gateway_1" name="Approved?"/>
    <bpmn:task id="Task_2" name="Approve"/>
    <bpmn:endEvent id="End" name="End"/>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_1"/>
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Gateway_1"/>
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Gateway_1" targetRef="Task_2" name="Yes"/>
    <bpmn:sequenceFlow id="Flow_4" sourceRef="Task_2" targetRef="End"/>
  </bpmn:process>
</bpmn:definitions>"""


class TestParseBpmnXml:
    def test_parses_elements(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        assert "Start" in graph.elements
        assert "Task_1" in graph.elements
        assert "Gateway_1" in graph.elements
        assert "End" in graph.elements

    def test_parses_tasks(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        task_names = {t.name for t in graph.tasks}
        assert "Review Document" in task_names
        assert "Approve" in task_names

    def test_parses_gateways(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        assert len(graph.gateways) == 1
        assert graph.gateways[0].name == "Approved?"

    def test_parses_events(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        assert len(graph.events) == 2

    def test_parses_flows(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        assert len(graph.flows) == 4

    def test_builds_adjacency(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        assert "Task_1" in graph.adjacency["Start"]
        assert "Gateway_1" in graph.adjacency["Task_1"]

    def test_empty_xml_returns_empty_graph(self) -> None:
        graph = parse_bpmn_xml("<invalid/>")
        assert len(graph.elements) == 0

    def test_flow_names_preserved(self) -> None:
        graph = parse_bpmn_xml(SAMPLE_BPMN)
        yes_flows = [f for f in graph.flows if f.name == "Yes"]
        assert len(yes_flows) == 1

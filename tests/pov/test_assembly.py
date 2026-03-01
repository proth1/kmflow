"""Tests for BPMN XML assembly (Consensus Step 7)."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

from src.core.models import CorroborationLevel
from src.pov.assembly import BPMN_NS, KMFLOW_NS, assemble_bpmn
from src.pov.consensus import ConsensusElement
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity


def _make_entity(
    name: str = "Test",
    entity_type: str = EntityType.ACTIVITY,
) -> ExtractedEntity:
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _make_scored(
    entity: ExtractedEntity,
    score: float = 0.75,
    level: str = "HIGH",
    evidence_ids: list[str] | None = None,
) -> tuple[ConsensusElement, float, str]:
    ev_ids = evidence_ids or [str(uuid.uuid4())]
    tri = TriangulatedElement(
        entity=entity,
        source_count=len(ev_ids),
        total_sources=5,
        triangulation_score=0.5,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
    )
    consensus = ConsensusElement(
        triangulated=tri,
        weighted_vote_score=0.75,
    )
    return (consensus, score, level)


class TestAssembleBpmn:
    """Tests for the assemble_bpmn function."""

    def test_generates_valid_xml(self):
        entity = _make_entity("Submit Request")
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)

        assert xml_str.startswith('<?xml version="1.0"')
        # Should be parseable XML
        root = ET.fromstring(xml_str)
        assert root is not None

    def test_contains_process_element(self):
        entity = _make_entity("Approve Invoice")
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored, process_name="Test Process")
        root = ET.fromstring(xml_str)

        process = root.find(f"{{{BPMN_NS}}}process")
        assert process is not None
        assert process.get("name") == "Test Process"

    def test_contains_start_and_end_events(self):
        entity = _make_entity("Task One")
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        start = process.find(f"{{{BPMN_NS}}}startEvent")
        end = process.find(f"{{{BPMN_NS}}}endEvent")
        assert start is not None
        assert end is not None

    def test_contains_task_for_activity(self):
        entity = _make_entity("Process Payment", EntityType.ACTIVITY)
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        tasks = process.findall(f"{{{BPMN_NS}}}task")
        assert len(tasks) == 1
        assert tasks[0].get("name") == "Process Payment"

    def test_contains_gateway_for_decision(self):
        entity = _make_entity("Amount Exceeds Threshold", EntityType.DECISION)
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        gateways = process.findall(f"{{{BPMN_NS}}}exclusiveGateway")
        assert len(gateways) == 1
        assert gateways[0].get("name") == "Amount Exceeds Threshold"

    def test_contains_sequence_flows(self):
        entity = _make_entity("Task A")
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        flows = process.findall(f"{{{BPMN_NS}}}sequenceFlow")
        # Start -> Task -> End = 2 flows
        assert len(flows) == 2

    def test_multiple_activities_connected(self):
        e1 = _make_entity("Task A")
        e2 = _make_entity("Task B")
        scored = [_make_scored(e1), _make_scored(e2)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        flows = process.findall(f"{{{BPMN_NS}}}sequenceFlow")
        # Start -> Task A -> Task B -> End = 3 flows
        assert len(flows) == 3

    def test_extension_elements_present(self):
        entity = _make_entity("Review Document")
        scored = [_make_scored(entity, score=0.82, level="HIGH")]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        assert ext is not None

        confidence = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert confidence is not None
        assert confidence.get("score") == "0.8200"
        assert confidence.get("level") == "HIGH"

    def test_data_store_for_system(self):
        entity = _make_entity("SAP", EntityType.SYSTEM)
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        data_stores = process.findall(f"{{{BPMN_NS}}}dataStoreReference")
        assert len(data_stores) == 1
        assert data_stores[0].get("name") == "SAP"

    def test_data_object_for_document(self):
        entity = _make_entity("Invoice", EntityType.DOCUMENT)
        scored = [_make_scored(entity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        data_objects = process.findall(f"{{{BPMN_NS}}}dataObjectReference")
        assert len(data_objects) == 1
        assert data_objects[0].get("name") == "Invoice"

    def test_empty_input_generates_minimal_bpmn(self):
        xml_str = assemble_bpmn([])
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        assert process is not None
        # Should still have start and end
        assert process.find(f"{{{BPMN_NS}}}startEvent") is not None
        assert process.find(f"{{{BPMN_NS}}}endEvent") is not None
        # One flow: start -> end
        flows = process.findall(f"{{{BPMN_NS}}}sequenceFlow")
        assert len(flows) == 1

    def test_custom_process_id(self):
        xml_str = assemble_bpmn([], process_id="my_process_123")
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")
        assert process.get("id") == "my_process_123"

    def test_roles_not_in_flow(self):
        """Roles should not appear as flow nodes (they are lanes)."""
        role = _make_entity("Finance Manager", EntityType.ROLE)
        activity = _make_entity("Process Invoice", EntityType.ACTIVITY)
        scored = [_make_scored(role), _make_scored(activity)]

        xml_str = assemble_bpmn(scored)
        root = ET.fromstring(xml_str)
        process = root.find(f"{{{BPMN_NS}}}process")

        tasks = process.findall(f"{{{BPMN_NS}}}task")
        assert len(tasks) == 1  # Only the activity, not the role

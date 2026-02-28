"""Tests for BpmnParser (BPMN 2.0 XML) — Story #296.

Covers BDD Scenario 3 (BPMN process element extraction) and Scenario 5 (corrupted files).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.bpmn_parser import BpmnParser


@pytest.fixture
def parser() -> BpmnParser:
    return BpmnParser()


SAMPLE_BPMN = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_1">
  <bpmn:collaboration id="Collaboration_1">
    <bpmn:participant id="Participant_1" name="Loan Processing" processRef="Process_1" />
  </bpmn:collaboration>
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:laneSet id="LaneSet_1">
      <bpmn:lane id="Lane_1" name="Loan Officer">
        <bpmn:flowNodeRef>Start_1</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Gateway_1</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="Lane_2" name="Underwriter">
        <bpmn:flowNodeRef>Task_2</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>End_1</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="Start_1" name="Application Received" />
    <bpmn:userTask id="Task_1" name="Review Application" />
    <bpmn:exclusiveGateway id="Gateway_1" name="Approved?" />
    <bpmn:serviceTask id="Task_2" name="Process Loan" />
    <bpmn:endEvent id="End_1" name="Loan Completed" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Gateway_1" />
    <bpmn:sequenceFlow id="Flow_3" name="Yes" sourceRef="Gateway_1" targetRef="Task_2" />
    <bpmn:sequenceFlow id="Flow_4" sourceRef="Task_2" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""


# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------


class TestSupportedFormats:
    def test_bpmn_extension(self, parser: BpmnParser) -> None:
        assert parser.can_parse(".bpmn")

    def test_bpmn2_extension(self, parser: BpmnParser) -> None:
        assert parser.can_parse(".bpmn2")

    def test_xml_extension(self, parser: BpmnParser) -> None:
        assert parser.can_parse(".xml")


# ---------------------------------------------------------------------------
# BDD Scenario 3: BPMN 2.0 XML parsed into process elements
# ---------------------------------------------------------------------------


class TestBDDScenario3BpmnParsing:
    """Scenario 3: BPMN file activities, flows, gateways, lanes extracted."""

    @pytest.mark.asyncio
    async def test_activities_extracted(self, parser: BpmnParser, tmp_path: Path) -> None:
        """All activities are extracted with their names and IDs."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        assert result.error is None
        task_frags = [
            f
            for f in result.fragments
            if f.fragment_type == FragmentType.PROCESS_ELEMENT
            and f.metadata.get("element_type") in ("userTask", "serviceTask")
        ]
        assert len(task_frags) == 2
        names = [f.content for f in task_frags]
        assert any("Review Application" in n for n in names)
        assert any("Process Loan" in n for n in names)

    @pytest.mark.asyncio
    async def test_activity_ids_in_metadata(self, parser: BpmnParser, tmp_path: Path) -> None:
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        task_frags = [f for f in result.fragments if f.metadata.get("element_type") in ("userTask", "serviceTask")]
        ids = {f.metadata.get("element_id") for f in task_frags}
        assert "Task_1" in ids
        assert "Task_2" in ids

    @pytest.mark.asyncio
    async def test_sequence_flows_captured(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Sequence flows captured with source and target references."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        flow_frags = [
            f
            for f in result.fragments
            if f.fragment_type == FragmentType.RELATIONSHIP and f.metadata.get("element_type") == "sequenceFlow"
        ]
        assert len(flow_frags) == 4
        # Check source/target references
        flow_with_label = [f for f in flow_frags if "Yes" in f.content]
        assert len(flow_with_label) == 1
        assert flow_with_label[0].metadata.get("source_ref") == "Gateway_1"
        assert flow_with_label[0].metadata.get("target_ref") == "Task_2"

    @pytest.mark.asyncio
    async def test_gateways_extracted_with_type(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Gateways are extracted with their type (XOR = exclusiveGateway)."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        gw_frags = [f for f in result.fragments if f.metadata.get("element_type") == "exclusiveGateway"]
        assert len(gw_frags) == 1
        assert "Approved?" in gw_frags[0].content

    @pytest.mark.asyncio
    async def test_gateway_decision_label(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Gateway name serves as the decision label."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        gw_frags = [f for f in result.fragments if f.metadata.get("element_type") == "exclusiveGateway"]
        assert gw_frags[0].metadata.get("element_id") == "Gateway_1"

    @pytest.mark.asyncio
    async def test_participants_extracted(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Participants (pools) are extracted with their names."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        participant_frags = [f for f in result.fragments if f.metadata.get("element_type") == "participant"]
        assert len(participant_frags) == 1
        assert "Loan Processing" in participant_frags[0].content

    @pytest.mark.asyncio
    async def test_lanes_extracted(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Swim lanes are extracted with their participant assignments."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        lane_frags = [f for f in result.fragments if f.metadata.get("element_type") == "lane"]
        assert len(lane_frags) == 2
        lane_names = {f.content for f in lane_frags}
        assert any("Loan Officer" in n for n in lane_names)
        assert any("Underwriter" in n for n in lane_names)

    @pytest.mark.asyncio
    async def test_events_extracted(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Events (start, end) are extracted."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        event_frags = [f for f in result.fragments if f.metadata.get("element_type") in ("startEvent", "endEvent")]
        assert len(event_frags) == 2

    @pytest.mark.asyncio
    async def test_metadata_counts(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Metadata includes counts for tasks, gateways, events, flows."""
        bpmn_path = tmp_path / "process.bpmn"
        bpmn_path.write_text(SAMPLE_BPMN)

        result = await parser.parse(str(bpmn_path), "process.bpmn")

        assert result.metadata.get("process_count") == 1
        assert result.metadata.get("task_count") == 2
        assert result.metadata.get("gateway_count") == 1
        assert result.metadata.get("event_count") == 2
        assert result.metadata.get("flow_count") == 4


# ---------------------------------------------------------------------------
# BDD Scenario 5: Corrupted BPMN
# ---------------------------------------------------------------------------


class TestCorruptedBpmn:
    @pytest.mark.asyncio
    async def test_corrupted_xml(self, parser: BpmnParser, tmp_path: Path) -> None:
        bad_bpmn = tmp_path / "corrupt.bpmn"
        bad_bpmn.write_text("<not valid xml")

        result = await parser.parse(str(bad_bpmn), "corrupt.bpmn")

        assert result.error is not None
        assert "Parse error" in result.error

    @pytest.mark.asyncio
    async def test_non_bpmn_xml(self, parser: BpmnParser, tmp_path: Path) -> None:
        """Valid XML but not BPMN should still parse without error (zero elements)."""
        non_bpmn = tmp_path / "other.bpmn"
        non_bpmn.write_text('<?xml version="1.0"?><root><item>data</item></root>')

        result = await parser.parse(str(non_bpmn), "other.bpmn")

        # No BPMN elements found, but no crash
        assert result.error is None
        assert result.metadata.get("process_count") == 0

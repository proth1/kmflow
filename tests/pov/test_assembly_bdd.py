"""BDD tests for BPMN Model Assembly with Evidence Citations (Story #315).

Tests the enhanced assembly module covering:
- Scenario 1: Valid BPMN model generated from consensus activities
- Scenario 2: Evidence citations attached to every process element
- Scenario 3: Dark segment gap marker applied to low-confidence activity
- Scenario 4: Variant annotations applied for multi-path evidence
- Scenario 5: All process elements carry three-dimensional confidence scores
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

from src.core.models import CorroborationLevel
from src.pov.assembly import (
    BPMN_NS,
    KMFLOW_NS,
    _add_confidence_extensions,
    _add_gap_marker,
    _add_variant_annotation,
    _classify_brightness,
    _determine_evidence_grade,
    assemble_bpmn,
)
from src.pov.consensus import ConsensusElement, VariantAnnotation
from src.pov.constants import (
    BRIGHTNESS_BRIGHT_THRESHOLD,
    BRIGHTNESS_DIM_THRESHOLD,
    MVC_THRESHOLD,
)
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity

# ── Fixtures ──


def _entity(
    name: str = "Test Activity",
    entity_type: str = EntityType.ACTIVITY,
) -> ExtractedEntity:
    """Create a test entity."""
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _scored(
    name: str = "Test Activity",
    entity_type: str = EntityType.ACTIVITY,
    score: float = 0.75,
    level: str = "HIGH",
    evidence_ids: list[str] | None = None,
    source_count: int | None = None,
    evidence_planes: set[str] | None = None,
) -> tuple[ConsensusElement, float, str]:
    """Create a scored consensus element for assembly testing."""
    ev_ids = evidence_ids or [str(uuid.uuid4())]
    src_count = source_count if source_count is not None else len(ev_ids)
    tri = TriangulatedElement(
        entity=_entity(name, entity_type),
        source_count=src_count,
        total_sources=5,
        triangulation_score=0.5,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
        supporting_planes=evidence_planes or set(),
    )
    consensus = ConsensusElement(
        triangulated=tri,
        weighted_vote_score=0.75,
    )
    return (consensus, score, level)


def _parse(xml_str: str) -> ET.Element:
    """Parse XML and return root element."""
    return ET.fromstring(xml_str)


def _get_process(root: ET.Element) -> ET.Element:
    """Get the process element from the root definitions."""
    process = root.find(f"{{{BPMN_NS}}}process")
    assert process is not None
    return process


# ── Scenario 1: Valid BPMN model generated from consensus activities ──


class TestValidBpmnGeneration:
    """Scenario 1: Valid BPMN model generated from consensus activities."""

    def test_ten_activities_generate_ten_tasks(self):
        """Given 10 activities, the BPMN contains 10 task elements."""
        elements = [_scored(f"Activity {i}") for i in range(10)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        tasks = process.findall(f"{{{BPMN_NS}}}task")
        assert len(tasks) == 10

    def test_task_names_match_consensus_activities(self):
        """Task names match the original consensus activity names."""
        names = ["Submit Request", "Review Document", "Approve Invoice"]
        elements = [_scored(name) for name in names]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        task_names = {t.get("name") for t in process.findall(f"{{{BPMN_NS}}}task")}
        assert task_names == set(names)

    def test_sequence_flows_connect_all_nodes(self):
        """Sequence flows connect start → activities → end."""
        elements = [_scored(f"Act {i}") for i in range(10)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        flows = process.findall(f"{{{BPMN_NS}}}sequenceFlow")
        # start + 10 tasks + end = 12 nodes → 11 flows
        assert len(flows) == 11

    def test_gateway_elements_for_decisions(self):
        """Decisions produce exclusiveGateway elements."""
        elements = [
            _scored("Validate Input"),
            _scored("Is Amount Valid", EntityType.DECISION),
            _scored("Process Payment"),
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        gateways = process.findall(f"{{{BPMN_NS}}}exclusiveGateway")
        assert len(gateways) == 1
        assert gateways[0].get("name") == "Is Amount Valid"

    def test_syntactically_valid_bpmn_xml(self):
        """Output is syntactically valid BPMN 2.0 XML."""
        elements = [_scored(f"Activity {i}") for i in range(10)]
        xml_str = assemble_bpmn(elements)

        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        root = _parse(xml_str)
        assert root.tag == f"{{{BPMN_NS}}}definitions"
        assert root.get("targetNamespace") == "http://kmflow.ai/bpmn"

    def test_start_and_end_events_present(self):
        """BPMN always has start and end events."""
        elements = [_scored("Activity One")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        assert process.find(f"{{{BPMN_NS}}}startEvent") is not None
        assert process.find(f"{{{BPMN_NS}}}endEvent") is not None

    def test_mixed_activities_and_decisions(self):
        """Activities and decisions both appear in the flow."""
        elements = [
            _scored("Task A"),
            _scored("Decision X", EntityType.DECISION),
            _scored("Task B"),
            _scored("Decision Y", EntityType.DECISION),
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        tasks = process.findall(f"{{{BPMN_NS}}}task")
        gateways = process.findall(f"{{{BPMN_NS}}}exclusiveGateway")
        assert len(tasks) == 2
        assert len(gateways) == 2


# ── Scenario 2: Evidence citations attached to every process element ──


class TestEvidenceCitations:
    """Scenario 2: Evidence citations attached to every process element."""

    def test_evidence_citation_references_all_sources(self):
        """Activity with 3 evidence sources has all 3 cited."""
        ev_ids = [str(uuid.uuid4()) for _ in range(3)]
        elements = [_scored("Activity X", evidence_ids=ev_ids, source_count=3)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        evidence = ext.find(f"{{{KMFLOW_NS}}}evidence")
        assert evidence is not None
        assert evidence.get("source_count") == "3"

        cited_ids = evidence.get("ids").split(",")
        assert set(cited_ids) == set(ev_ids)

    def test_every_task_has_evidence_element(self):
        """Every task in the output has an evidence extension."""
        elements = [_scored(f"Task {i}") for i in range(5)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            assert ext is not None, f"Task {task.get('name')} missing extensionElements"
            evidence = ext.find(f"{{{KMFLOW_NS}}}evidence")
            assert evidence is not None, f"Task {task.get('name')} missing evidence citation"

    def test_single_source_citation(self):
        """A single-source element cites exactly 1 evidence ID."""
        ev_id = str(uuid.uuid4())
        elements = [_scored("Single Source Task", evidence_ids=[ev_id], source_count=1)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        evidence = ext.find(f"{{{KMFLOW_NS}}}evidence")
        assert evidence.get("source_count") == "1"
        assert evidence.get("ids") == ev_id

    def test_gateway_also_has_evidence_citation(self):
        """Gateways also get evidence citations, not just tasks."""
        ev_ids = [str(uuid.uuid4()) for _ in range(2)]
        elements = [_scored("Decision Gate", EntityType.DECISION, evidence_ids=ev_ids, source_count=2)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        gw = process.find(f"{{{BPMN_NS}}}exclusiveGateway")

        ext = gw.find(f"{{{BPMN_NS}}}extensionElements")
        evidence = ext.find(f"{{{KMFLOW_NS}}}evidence")
        assert evidence is not None
        assert evidence.get("source_count") == "2"


# ── Scenario 3: Dark segment gap marker applied to low-confidence activity ──


class TestDarkSegmentGapMarker:
    """Scenario 3: Dark segment gap marker for low-confidence activities."""

    def test_low_confidence_activity_gets_dark_brightness(self):
        """Activity with score 0.35 is classified as DARK."""
        elements = [_scored("Validate Submission", score=0.35, level="LOW")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        confidence = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert confidence.get("brightness") == "DARK"

    def test_gap_marker_attached_below_mvc(self):
        """Gap marker annotation attached to DARK elements below MVC threshold."""
        elements = [_scored("Validate Submission", score=0.35, level="LOW")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        gap = ext.find(f"{{{KMFLOW_NS}}}gapMarker")
        assert gap is not None
        assert gap.get("type") == "insufficient_evidence"
        assert gap.get("requires_additional_evidence") == "true"

    def test_gap_marker_description_contains_score(self):
        """Gap marker description references the actual score and MVC threshold."""
        elements = [_scored("Validate Submission", score=0.35, level="LOW")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        gap = ext.find(f"{{{KMFLOW_NS}}}gapMarker")
        desc = gap.get("description")
        assert "0.35" in desc
        assert str(MVC_THRESHOLD) in desc
        assert "Validate Submission" in desc

    def test_bright_activity_no_gap_marker(self):
        """Activity with high confidence does NOT get a gap marker."""
        elements = [_scored("Well Supported Task", score=0.85, level="HIGH")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        gap = ext.find(f"{{{KMFLOW_NS}}}gapMarker")
        assert gap is None

    def test_dim_above_mvc_no_gap_marker(self):
        """DIM activity at exactly MVC threshold gets no gap marker."""
        elements = [_scored("Borderline Task", score=0.40, level="MEDIUM")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        gap = ext.find(f"{{{KMFLOW_NS}}}gapMarker")
        assert gap is None

    def test_multiple_dark_elements_all_get_gap_markers(self):
        """Multiple DARK activities each get their own gap marker."""
        elements = [
            _scored("Dark Task A", score=0.20, level="VERY_LOW"),
            _scored("Dark Task B", score=0.30, level="LOW"),
            _scored("Bright Task", score=0.90, level="VERY_HIGH"),
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        gap_count = 0
        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            if ext.find(f"{{{KMFLOW_NS}}}gapMarker") is not None:
                gap_count += 1
        assert gap_count == 2


# ── Scenario 4: Variant annotations applied for multi-path evidence ──


class TestVariantAnnotations:
    """Scenario 4: Variant annotations for multi-path evidence."""

    def test_both_variants_annotated(self):
        """Both variant A and variant B paths are annotated."""
        ev_a = [str(uuid.uuid4()) for _ in range(4)]
        ev_b = [str(uuid.uuid4()) for _ in range(2)]
        variants = [
            VariantAnnotation(
                variant_label="Standard",
                element_name="Approval Process",
                evidence_ids=ev_a,
                evidence_coverage=0.67,
            ),
            VariantAnnotation(
                variant_label="Expedited",
                element_name="Approval Process",
                evidence_ids=ev_b,
                evidence_coverage=0.33,
            ),
        ]
        elements = [_scored("Approval Process")]
        xml_str = assemble_bpmn(elements, variants=variants)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        variant_elems = ext.findall(f"{{{KMFLOW_NS}}}variant")
        assert len(variant_elems) == 2

        labels = {v.get("label") for v in variant_elems}
        assert labels == {"Standard", "Expedited"}

    def test_variant_evidence_count_correct(self):
        """Variant annotations carry correct evidence counts."""
        ev_a = [str(uuid.uuid4()) for _ in range(4)]
        ev_b = [str(uuid.uuid4()) for _ in range(2)]
        variants = [
            VariantAnnotation(
                variant_label="Standard",
                element_name="Approval Process",
                evidence_ids=ev_a,
                evidence_coverage=0.67,
            ),
            VariantAnnotation(
                variant_label="Expedited",
                element_name="Approval Process",
                evidence_ids=ev_b,
                evidence_coverage=0.33,
            ),
        ]
        elements = [_scored("Approval Process")]
        xml_str = assemble_bpmn(elements, variants=variants)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        variant_elems = ext.findall(f"{{{KMFLOW_NS}}}variant")

        counts = {v.get("label"): v.get("evidence_count") for v in variant_elems}
        assert counts["Standard"] == "4"
        assert counts["Expedited"] == "2"

    def test_neither_variant_marked_canonical(self):
        """Neither variant is marked as the sole canonical path."""
        variants = [
            VariantAnnotation(variant_label="A", element_name="Task X", evidence_ids=["e1"], evidence_coverage=0.5),
            VariantAnnotation(variant_label="B", element_name="Task X", evidence_ids=["e2"], evidence_coverage=0.5),
        ]
        elements = [_scored("Task X")]
        xml_str = assemble_bpmn(elements, variants=variants)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        for v in ext.findall(f"{{{KMFLOW_NS}}}variant"):
            assert v.get("canonical") is None

    def test_no_variants_no_annotations(self):
        """Without variants, no variant annotations appear."""
        elements = [_scored("Simple Task")]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        variant_elems = ext.findall(f"{{{KMFLOW_NS}}}variant")
        assert len(variant_elems) == 0

    def test_variant_on_correct_element_only(self):
        """Variants are attached only to the matching element."""
        variants = [
            VariantAnnotation(variant_label="V1", element_name="Task A", evidence_ids=["e1"], evidence_coverage=1.0),
        ]
        elements = [_scored("Task A"), _scored("Task B")]
        xml_str = assemble_bpmn(elements, variants=variants)
        process = _get_process(_parse(xml_str))

        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            variant_elems = ext.findall(f"{{{KMFLOW_NS}}}variant")
            if task.get("name") == "Task A":
                assert len(variant_elems) == 1
            else:
                assert len(variant_elems) == 0

    def test_variant_evidence_ids_included(self):
        """Variant annotation includes all supporting evidence IDs."""
        ev_ids = ["ev-001", "ev-002", "ev-003"]
        variants = [
            VariantAnnotation(
                variant_label="Standard",
                element_name="My Task",
                evidence_ids=ev_ids,
                evidence_coverage=0.75,
            ),
        ]
        elements = [_scored("My Task")]
        xml_str = assemble_bpmn(elements, variants=variants)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        v = ext.find(f"{{{KMFLOW_NS}}}variant")
        cited_ids = v.get("evidence_ids").split(",")
        assert set(cited_ids) == set(ev_ids)


# ── Scenario 5: All process elements carry three-dimensional confidence scores ──


class TestThreeDimensionalConfidence:
    """Scenario 5: Three-dimensional confidence on every ProcessElement."""

    def test_every_element_has_numeric_score(self):
        """Every element has a numeric confidence score between 0 and 1."""
        elements = [_scored(f"Task {i}", score=0.1 * (i + 1)) for i in range(10)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
            score_val = float(conf.get("score"))
            assert 0.0 <= score_val <= 1.0, f"Score {score_val} out of range for {task.get('name')}"

    def test_every_element_has_brightness(self):
        """Every element has a brightness classification."""
        elements = [_scored(f"Task {i}", score=0.3 + 0.1 * i) for i in range(5)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        valid_brightness = {"BRIGHT", "DIM", "DARK"}
        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
            brightness = conf.get("brightness")
            assert brightness in valid_brightness, f"Invalid brightness '{brightness}' for {task.get('name')}"

    def test_every_element_has_evidence_grade(self):
        """Every element has an evidence grade (A, B, C, D, or U)."""
        elements = [_scored(f"Task {i}") for i in range(5)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))

        valid_grades = {"A", "B", "C", "D", "U"}
        for task in process.findall(f"{{{BPMN_NS}}}task"):
            ext = task.find(f"{{{BPMN_NS}}}extensionElements")
            conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
            grade = conf.get("evidence_grade")
            assert grade in valid_grades, f"Invalid grade '{grade}' for {task.get('name')}"

    def test_bright_classification_for_high_score(self):
        """Score >= BRIGHT threshold → BRIGHT brightness."""
        elements = [
            _scored(
                "High Confidence",
                score=BRIGHTNESS_BRIGHT_THRESHOLD + 0.05,
                evidence_ids=["e1", "e2", "e3"],
                source_count=3,
                evidence_planes={"system_behavioral", "documented_formal"},
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("brightness") == "BRIGHT"

    def test_dim_classification_for_medium_score(self):
        """Score between DIM and BRIGHT thresholds → DIM brightness."""
        mid_score = (BRIGHTNESS_DIM_THRESHOLD + BRIGHTNESS_BRIGHT_THRESHOLD) / 2
        elements = [
            _scored(
                "Medium Confidence",
                score=mid_score,
                evidence_ids=["e1", "e2"],
                source_count=2,
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("brightness") == "DIM"

    def test_dark_classification_for_low_score(self):
        """Score below DIM threshold → DARK brightness."""
        elements = [_scored("Low Confidence", score=0.20)]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("brightness") == "DARK"

    def test_coherence_constraint_grade_d_caps_at_dim(self):
        """Grade D caps brightness at DIM even if score would be BRIGHT."""
        # Single source → grade D, high score → should be capped at DIM
        elements = [
            _scored(
                "Single Source High Score",
                score=0.90,
                evidence_ids=["e1"],
                source_count=1,
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("evidence_grade") == "D"
        assert conf.get("brightness") == "DIM"  # Capped from BRIGHT to DIM

    def test_coherence_constraint_grade_u_caps_at_dim(self):
        """Grade U caps brightness at DIM."""
        # No evidence → grade U
        elements = [
            _scored(
                "No Evidence",
                score=0.80,
                evidence_ids=[],
                source_count=0,
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("evidence_grade") == "U"
        assert conf.get("brightness") == "DIM"  # Capped from BRIGHT to DIM

    def test_grade_a_requires_multiplane(self):
        """Grade A requires 3+ sources from 2+ evidence planes."""
        elements = [
            _scored(
                "Well Corroborated",
                score=0.85,
                evidence_ids=["e1", "e2", "e3"],
                source_count=3,
                evidence_planes={"system_behavioral", "documented_formal"},
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("evidence_grade") == "A"

    def test_grade_b_for_two_sources(self):
        """Grade B for 2+ sources without multi-plane threshold."""
        elements = [
            _scored(
                "Two Sources",
                score=0.70,
                evidence_ids=["e1", "e2"],
                source_count=2,
                evidence_planes={"documented_formal"},
            )
        ]
        xml_str = assemble_bpmn(elements)
        process = _get_process(_parse(xml_str))
        task = process.find(f"{{{BPMN_NS}}}task")

        ext = task.find(f"{{{BPMN_NS}}}extensionElements")
        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf.get("evidence_grade") == "B"


# ── Helper function unit tests ──


class TestClassifyBrightness:
    """Unit tests for _classify_brightness helper."""

    def test_bright_with_good_grade(self):
        assert _classify_brightness(0.80, "A") == "BRIGHT"

    def test_dim_with_medium_score(self):
        assert _classify_brightness(0.50, "B") == "DIM"

    def test_dark_with_low_score(self):
        assert _classify_brightness(0.20, "C") == "DARK"

    def test_grade_d_caps_bright_to_dim(self):
        assert _classify_brightness(0.90, "D") == "DIM"

    def test_grade_u_caps_bright_to_dim(self):
        assert _classify_brightness(0.85, "U") == "DIM"

    def test_grade_d_does_not_cap_dark(self):
        """Grade D caps at DIM, but DARK stays DARK (it's lower)."""
        assert _classify_brightness(0.10, "D") == "DARK"

    def test_boundary_bright_threshold(self):
        assert _classify_brightness(BRIGHTNESS_BRIGHT_THRESHOLD, "A") == "BRIGHT"

    def test_boundary_dim_threshold(self):
        assert _classify_brightness(BRIGHTNESS_DIM_THRESHOLD, "B") == "DIM"

    def test_just_below_dim_threshold(self):
        assert _classify_brightness(BRIGHTNESS_DIM_THRESHOLD - 0.01, "A") == "DARK"


class TestDetermineEvidenceGrade:
    """Unit tests for _determine_evidence_grade helper."""

    def test_grade_u_no_evidence(self):
        elem = _scored("No Ev", evidence_ids=[], source_count=0)[0]
        assert _determine_evidence_grade(elem) == "U"

    def test_grade_d_single_source(self):
        elem = _scored("One Src", evidence_ids=["e1"], source_count=1)[0]
        assert _determine_evidence_grade(elem) == "D"

    def test_grade_b_two_sources(self):
        elem = _scored("Two Src", evidence_ids=["e1", "e2"], source_count=2)[0]
        assert _determine_evidence_grade(elem) == "B"

    def test_grade_a_three_sources_two_planes(self):
        elem = _scored(
            "Strong",
            evidence_ids=["e1", "e2", "e3"],
            source_count=3,
            evidence_planes={"system_behavioral", "documented_formal"},
        )[0]
        assert _determine_evidence_grade(elem) == "A"

    def test_grade_b_three_sources_one_plane(self):
        """3 sources but only 1 plane → grade B (not A)."""
        elem = _scored(
            "Single Plane",
            evidence_ids=["e1", "e2", "e3"],
            source_count=3,
            evidence_planes={"documented_formal"},
        )[0]
        assert _determine_evidence_grade(elem) == "B"


class TestAddGapMarker:
    """Unit tests for _add_gap_marker helper."""

    def test_gap_marker_attributes(self):
        ext = ET.Element("extensionElements")
        _add_gap_marker(ext, "Test Element", 0.25)

        marker = ext.find(f"{{{KMFLOW_NS}}}gapMarker")
        assert marker is not None
        assert marker.get("type") == "insufficient_evidence"
        assert marker.get("requires_additional_evidence") == "true"
        assert "Test Element" in marker.get("description")
        assert "0.25" in marker.get("description")


class TestAddVariantAnnotation:
    """Unit tests for _add_variant_annotation helper."""

    def test_variant_annotation_attributes(self):
        ext = ET.Element("extensionElements")
        variant = VariantAnnotation(
            variant_label="Express",
            element_name="Approval",
            evidence_ids=["e1", "e2"],
            evidence_coverage=0.45,
        )
        _add_variant_annotation(ext, variant)

        v = ext.find(f"{{{KMFLOW_NS}}}variant")
        assert v is not None
        assert v.get("label") == "Express"
        assert v.get("evidence_count") == "2"
        assert v.get("coverage") == "0.4500"


class TestAddConfidenceExtensions:
    """Unit tests for _add_confidence_extensions helper."""

    def test_returns_brightness_and_grade(self):
        elem = _scored("Test", evidence_ids=["e1", "e2"], source_count=2)[0]
        ext = ET.Element("extensionElements")
        brightness, grade = _add_confidence_extensions(ext, elem, 0.80, "HIGH")

        assert brightness in {"BRIGHT", "DIM", "DARK"}
        assert grade in {"A", "B", "C", "D", "U"}

    def test_confidence_element_created(self):
        elem = _scored("Test", evidence_ids=["e1"], source_count=1)[0]
        ext = ET.Element("extensionElements")
        _add_confidence_extensions(ext, elem, 0.50, "MEDIUM")

        conf = ext.find(f"{{{KMFLOW_NS}}}confidence")
        assert conf is not None
        assert conf.get("score") == "0.5000"
        assert conf.get("level") == "MEDIUM"
        assert conf.get("brightness") is not None
        assert conf.get("evidence_grade") is not None

    def test_evidence_element_created(self):
        elem = _scored("Test", evidence_ids=["e1", "e2"], source_count=2)[0]
        ext = ET.Element("extensionElements")
        _add_confidence_extensions(ext, elem, 0.70, "HIGH")

        ev = ext.find(f"{{{KMFLOW_NS}}}evidence")
        assert ev is not None
        assert ev.get("source_count") == "2"

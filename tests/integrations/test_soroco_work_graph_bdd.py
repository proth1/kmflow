"""BDD tests for Soroco Scout Work Graph integration (Story #326).

Tests activity parsing, Activity node mapping with telemetric epistemic
frames, evidence record generation, and cross-source triangulation readiness.
"""

from __future__ import annotations

from src.integrations.soroco_work_graph import (
    EVIDENCE_CATEGORY_KM4WORK,
    ScoutActivity,
    SorocoWorkGraphMapper,
    WorkGraphImportResult,
    import_work_graph,
)

# --- Sample data ---

SAMPLE_ACTIVITY_DATA = {
    "activity_id": "act-001",
    "activity_name": "Submit Invoice",
    "application": "SAP GUI",
    "user": "john.doe",
    "start_time": "2026-01-15T09:00:00Z",
    "end_time": "2026-01-15T09:05:00Z",
    "duration_ms": 300000,
    "actions": [
        {"type": "click", "target": "Submit Button"},
        {"type": "type", "target": "Invoice Number"},
    ],
}

SAMPLE_ACTIVITY_DATA_2 = {
    "activity_id": "act-002",
    "activity_name": "Review Document",
    "application": "Microsoft Word",
    "user": "jane.smith",
    "start_time": "2026-01-15T09:10:00Z",
    "end_time": "2026-01-15T09:20:00Z",
    "duration_ms": 600000,
    "actions": [
        {"type": "scroll", "target": "Document Body"},
    ],
}

SAMPLE_ACTIVITY_ALT_KEYS = {
    "id": "act-003",
    "name": "Check Email",
    "application": "Outlook",
    "user_id": "bob.wilson",
}


GRAPH_ID = "wg-12345"
ENGAGEMENT_ID = "eng-001"


# --- Scenario 1: Work graph export to KMFlow evidence category 7 ---


class TestWorkGraphExport:
    """Scenario 1: Work graph export to KMFlow evidence category 7."""

    def test_activities_parsed_from_api_response(self) -> None:
        """Activities are parsed from Scout API response data."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA, SAMPLE_ACTIVITY_DATA_2],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.success
        assert result.activity_count == 2

    def test_evidence_category_is_km4work(self) -> None:
        """Each evidence record has category 7 (KM4Work)."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert len(result.evidence_records) == 1
        record = result.evidence_records[0]
        assert record["category"] == EVIDENCE_CATEGORY_KM4WORK
        assert record["category"] == 7

    def test_evidence_record_has_soroco_source(self) -> None:
        """Evidence record source is soroco_scout."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        record = result.evidence_records[0]
        assert record["source_system"] == "soroco_scout"
        assert record["source"] == "soroco_scout"

    def test_evidence_record_includes_activity_id(self) -> None:
        """Evidence record metadata includes the original Scout activity_id."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        record = result.evidence_records[0]
        assert record["metadata"]["activity_id"] == "act-001"

    def test_evidence_record_has_engagement_id(self) -> None:
        """Evidence record is associated with the correct engagement."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        record = result.evidence_records[0]
        assert record["engagement_id"] == ENGAGEMENT_ID


# --- Scenario 2: Task mining activities mapped to Activity nodes ---


class TestActivityToActivityNodeMapping:
    """Scenario 2: Activity → Activity node with telemetric frame."""

    def test_element_has_telemetric_epistemic_frame(self) -> None:
        """Each Activity node carries epistemic_frame='telemetric'."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert len(result.element_mappings) == 1
        mapping = result.element_mappings[0]
        assert mapping.epistemic_frame == "telemetric"

    def test_element_name_from_activity_name(self) -> None:
        """Activity node name comes from the activity name."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        mapping = result.element_mappings[0]
        assert mapping.name == "Submit Invoice"

    def test_element_id_prefixed_with_scout(self) -> None:
        """Activity node ID uses scout: prefix for namespace."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        mapping = result.element_mappings[0]
        assert mapping.element_id == "scout:act-001"

    def test_performed_by_set_to_desktop_user(self) -> None:
        """PERFORMED_BY edge target is the desktop user captured by Scout."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        mapping = result.element_mappings[0]
        assert mapping.performed_by == "john.doe"

    def test_element_attributes_include_application(self) -> None:
        """Element attributes include the desktop application used."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        mapping = result.element_mappings[0]
        assert mapping.attributes["application"] == "SAP GUI"
        assert mapping.attributes["duration_ms"] == 300000

    def test_multiple_activities_create_multiple_elements(self) -> None:
        """Each activity creates its own Activity node mapping."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA, SAMPLE_ACTIVITY_DATA_2],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.element_count == 2
        names = {m.name for m in result.element_mappings}
        assert "Submit Invoice" in names
        assert "Review Document" in names


# --- Scenario 3: Cross-source triangulation readiness ---


class TestCrossSourceTriangulation:
    """Scenario 3: Cross-source triangulation via SUPPORTED_BY edges."""

    def test_graph_operations_include_supported_by_edges(self) -> None:
        """Graph operations create SUPPORTED_BY edges for each element."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping = mapper.map_activity(activity)

        ops = mapper.build_graph_operations([mapping])

        supported_by_ops = [op for op in ops if op.get("type") == "SUPPORTED_BY"]
        assert len(supported_by_ops) == 1
        assert supported_by_ops[0]["to_properties"]["epistemic_frame"] == "telemetric"

    def test_graph_operations_include_performed_by_edges(self) -> None:
        """Graph operations create PERFORMED_BY edges to user roles."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping = mapper.map_activity(activity)

        ops = mapper.build_graph_operations([mapping])

        performed_by_ops = [op for op in ops if op.get("type") == "PERFORMED_BY"]
        assert len(performed_by_ops) == 1
        assert performed_by_ops[0]["to_id"] == "role:john.doe"

    def test_graph_operations_merge_activity_node(self) -> None:
        """Graph operations merge Activity nodes with correct properties."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping = mapper.map_activity(activity)

        ops = mapper.build_graph_operations([mapping])

        node_ops = [op for op in ops if op.get("op") == "merge_node"]
        assert len(node_ops) == 1
        assert node_ops[0]["label"] == "Activity"
        assert node_ops[0]["properties"]["epistemic_frame"] == "telemetric"
        assert node_ops[0]["properties"]["engagement_id"] == ENGAGEMENT_ID
        assert node_ops[0]["properties"]["source_system"] == "soroco_scout"

    def test_dual_evidence_links_for_same_element(self) -> None:
        """Two evidence sources on the same element both create SUPPORTED_BY edges."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)

        # First source: telemetric (Scout)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping_telemetric = mapper.map_activity(activity)

        ops_telemetric = mapper.build_graph_operations([mapping_telemetric])
        supported_by_ops = [op for op in ops_telemetric if op.get("type") == "SUPPORTED_BY"]

        # Verify telemetric evidence link
        assert len(supported_by_ops) == 1
        assert supported_by_ops[0]["to_properties"]["epistemic_frame"] == "telemetric"
        assert supported_by_ops[0]["to_properties"]["category"] == EVIDENCE_CATEGORY_KM4WORK

        # Second source would be documentary (from document import)
        # This test verifies the Scout side creates correct SUPPORTED_BY
        # that can coexist with documentary sources on the same Activity
        assert supported_by_ops[0]["from_id"] == "scout:act-001"

    def test_evidence_record_epistemic_frame_set(self) -> None:
        """Evidence record carries epistemic_frame for downstream triangulation."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        record = result.evidence_records[0]
        assert record["epistemic_frame"] == "telemetric"


# --- ScoutActivity parsing tests ---


class TestScoutActivityParsing:
    """ScoutActivity data structure and parsing."""

    def test_from_api_response_standard_keys(self) -> None:
        """Parse activity from standard Scout API response keys."""
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)

        assert activity.activity_id == "act-001"
        assert activity.activity_name == "Submit Invoice"
        assert activity.application == "SAP GUI"
        assert activity.user == "john.doe"
        assert activity.duration_ms == 300000
        assert len(activity.actions) == 2
        assert activity.graph_id == GRAPH_ID

    def test_from_api_response_alternate_keys(self) -> None:
        """Parse activity from alternate key names (id, name, user_id)."""
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_ALT_KEYS)

        assert activity.activity_id == "act-003"
        assert activity.activity_name == "Check Email"
        assert activity.user == "bob.wilson"

    def test_missing_id_skipped_in_import(self) -> None:
        """Activities without an ID are skipped with an error."""
        result = import_work_graph(
            [{"activity_name": "No ID Activity"}],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.activity_count == 0
        assert len(result.errors) == 1
        assert "missing ID" in result.errors[0]

    def test_empty_activities_result_not_successful(self) -> None:
        """Empty activity list produces unsuccessful result."""
        result = import_work_graph(
            [],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert not result.success
        assert result.activity_count == 0

    def test_graph_id_propagated_to_activities(self) -> None:
        """Graph ID is set on all parsed activities."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA, SAMPLE_ACTIVITY_DATA_2],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        for activity in result.activities:
            assert activity.graph_id == GRAPH_ID


# --- WorkGraphImportResult tests ---


class TestWorkGraphImportResult:
    """WorkGraphImportResult data structure."""

    def test_success_with_activities_no_errors(self) -> None:
        """Result is successful when activities present and no errors."""
        result = WorkGraphImportResult(
            activities=[ScoutActivity(activity_id="1", activity_name="Test")],
        )
        assert result.success

    def test_not_successful_with_errors(self) -> None:
        """Result is not successful when errors are present."""
        result = WorkGraphImportResult(
            activities=[ScoutActivity(activity_id="1", activity_name="Test")],
            errors=["something went wrong"],
        )
        assert not result.success

    def test_not_successful_when_empty(self) -> None:
        """Result is not successful when no activities imported."""
        result = WorkGraphImportResult()
        assert not result.success

    def test_counts(self) -> None:
        """Activity and element counts are correct."""
        result = import_work_graph(
            [SAMPLE_ACTIVITY_DATA, SAMPLE_ACTIVITY_DATA_2],
            graph_id=GRAPH_ID,
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.activity_count == 2
        assert result.element_count == 2
        assert len(result.evidence_records) == 2


# --- SorocoWorkGraphMapper tests ---


class TestSorocoWorkGraphMapper:
    """Mapper unit tests."""

    def test_build_evidence_record_format(self) -> None:
        """Evidence record has correct format and required fields."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping = mapper.map_activity(activity)

        record = mapper.build_evidence_record(mapping)

        assert record["format"] == "json"
        assert record["name"] == "soroco_activity_act-001"
        assert record["metadata"]["activity_name"] == "Submit Invoice"
        assert record["metadata"]["graph_id"] == GRAPH_ID

    def test_map_activity_source_is_soroco_scout(self) -> None:
        """Mapped element source is soroco_scout."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA)
        mapping = mapper.map_activity(activity)

        assert mapping.source == "soroco_scout"

    def test_map_activities_batch(self) -> None:
        """Batch mapping produces one mapping per activity."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activities = [
            ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID),
            ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA_2, graph_id=GRAPH_ID),
        ]

        mappings = mapper.map_activities(activities)

        assert len(mappings) == 2
        assert all(m.epistemic_frame == "telemetric" for m in mappings)

    def test_no_performed_by_edge_when_user_empty(self) -> None:
        """No PERFORMED_BY edge when activity has no user."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity(activity_id="x", activity_name="Test", user="")
        mapping = mapper.map_activity(activity)

        ops = mapper.build_graph_operations([mapping])

        performed_by_ops = [op for op in ops if op.get("type") == "PERFORMED_BY"]
        assert len(performed_by_ops) == 0

    def test_element_attributes_include_action_count(self) -> None:
        """Element attributes include the count of sub-actions."""
        mapper = SorocoWorkGraphMapper(engagement_id=ENGAGEMENT_ID)
        activity = ScoutActivity.from_api_response(SAMPLE_ACTIVITY_DATA, graph_id=GRAPH_ID)
        mapping = mapper.map_activity(activity)

        assert mapping.attributes["action_count"] == 2

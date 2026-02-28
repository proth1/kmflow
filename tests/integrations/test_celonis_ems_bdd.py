"""BDD tests for Celonis EMS integration (Story #325).

Tests event log import, process model graph mapping, conformance
deviation import, and partial import with checkpoint support.
"""

from __future__ import annotations

from src.integrations.celonis_ems import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    CelonisConformanceMapper,
    CelonisDeviation,
    CelonisEvent,
    CelonisProcessNode,
    CelonisSequenceFlow,
    ConformanceImportResult,
    EventLogImportResult,
    conformance_score_to_severity,
    import_conformance_results,
    import_event_log,
    import_process_model,
)

# --- Sample data ---

ENGAGEMENT_ID = "eng-celonis-001"

SAMPLE_EVENT_1 = {
    "case_id": "case-100",
    "activity": "Create Order",
    "timestamp": "2026-01-15T09:00:00Z",
    "resource": "alice",
    "variant": "v1",
    "duration": 120,
    "event_id": "evt-001",
}

SAMPLE_EVENT_2 = {
    "case_id": "case-100",
    "activity": "Approve Order",
    "timestamp": "2026-01-15T09:05:00Z",
    "resource": "bob",
    "variant": "v1",
    "duration": 60,
    "event_id": "evt-002",
}

SAMPLE_EVENT_ALT_KEYS = {
    "caseId": "case-200",
    "activityName": "Process Payment",
    "eventTime": "2026-01-15T10:00:00Z",
    "user": "charlie",
    "eventId": "evt-003",
}

SAMPLE_NODE_1 = {
    "nodeId": "n1",
    "activityName": "Create Order",
    "frequency": 500,
    "avgDuration": 120.5,
}

SAMPLE_NODE_2 = {
    "nodeId": "n2",
    "activityName": "Approve Order",
    "frequency": 480,
    "avgDuration": 60.0,
}

SAMPLE_NODE_3 = {
    "nodeId": "n3",
    "activityName": "Ship Order",
    "frequency": 450,
    "avgDuration": 300.0,
}

SAMPLE_FLOW_1 = {
    "sourceNodeId": "n1",
    "targetNodeId": "n2",
    "frequency": 480,
}

SAMPLE_FLOW_2 = {
    "sourceNodeId": "n2",
    "targetNodeId": "n3",
    "frequency": 450,
}

SAMPLE_DEVIATION_SEQUENCE = {
    "deviationId": "dev-001",
    "deviationType": "sequence_violation",
    "affectedActivity": "Approve Order",
    "expectedActivity": "Create Order",
    "conformanceScore": 0.45,
    "caseCount": 120,
    "description": "Order approved without prior creation",
}

SAMPLE_DEVIATION_EXISTENCE = {
    "deviationId": "dev-002",
    "deviationType": "missing_activity",
    "affectedActivity": "Quality Check",
    "conformanceScore": 0.72,
    "caseCount": 80,
}


# --- Scenario 1: Event log import ---


class TestEventLogImport:
    """Scenario 1: Event log import from Celonis EMS."""

    def test_events_parsed_from_api_response(self) -> None:
        """Events are parsed from Celonis API response data."""
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_2],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.success
        assert result.event_count == 2

    def test_canonical_events_created(self) -> None:
        """Each event becomes a CanonicalActivityEvent candidate."""
        result = import_event_log(
            [SAMPLE_EVENT_1],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.new_event_count == 1
        canonical = result.canonical_events[0]
        assert canonical["activity_name"] == "Create Order"
        assert canonical["source_system"] == "celonis_ems"
        assert canonical["case_id"] == "case-100"
        assert canonical["actor"] == "alice"

    def test_evidence_source_is_celonis_ems(self) -> None:
        """Source system is celonis_ems."""
        result = import_event_log(
            [SAMPLE_EVENT_1],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.canonical_events[0]["source_system"] == "celonis_ems"

    def test_idempotent_import_skips_duplicates(self) -> None:
        """Re-importing the same events does not create duplicates."""
        existing = {"evt-001"}
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_2],
            engagement_id=ENGAGEMENT_ID,
            existing_event_ids=existing,
        )

        # All events are parsed, but only new ones become canonical
        assert result.event_count == 2
        assert result.new_event_count == 1  # Only evt-002
        assert result.canonical_events[0]["activity_name"] == "Approve Order"

    def test_idempotent_within_single_batch(self) -> None:
        """Duplicate events within a single batch are deduplicated."""
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_1],  # Same event twice
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.event_count == 2
        assert result.new_event_count == 1  # Deduplicated

    def test_checkpoint_tracks_latest_timestamp(self) -> None:
        """Checkpoint is set to the latest event timestamp."""
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_2],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.checkpoint == "2026-01-15T09:05:00Z"

    def test_alternate_api_keys(self) -> None:
        """Events parsed from alternate Celonis API key names."""
        result = import_event_log(
            [SAMPLE_EVENT_ALT_KEYS],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.event_count == 1
        event = result.events[0]
        assert event.case_id == "case-200"
        assert event.activity == "Process Payment"
        assert event.resource == "charlie"

    def test_missing_activity_skipped(self) -> None:
        """Events without activity are skipped with error."""
        result = import_event_log(
            [{"case_id": "case-300"}],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.event_count == 0
        assert len(result.errors) == 1
        assert "missing case_id or activity" in result.errors[0]


# --- Scenario 2: Process model graph mapping ---


class TestProcessModelImport:
    """Scenario 2: Process model graph mapping to KMFlow knowledge graph."""

    def test_nodes_create_process_elements(self) -> None:
        """Activity nodes become ProcessElement nodes."""
        result = import_process_model(
            [SAMPLE_NODE_1, SAMPLE_NODE_2],
            [],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.success
        assert result.node_count == 2

    def test_flows_create_precedes_edges(self) -> None:
        """Sequence flows create PRECEDES edges."""
        result = import_process_model(
            [SAMPLE_NODE_1, SAMPLE_NODE_2, SAMPLE_NODE_3],
            [SAMPLE_FLOW_1, SAMPLE_FLOW_2],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.edge_count == 2

    def test_graph_operations_have_source_connector(self) -> None:
        """All nodes and edges have source_connector='celonis'."""
        result = import_process_model(
            [SAMPLE_NODE_1],
            [SAMPLE_FLOW_1],
            engagement_id=ENGAGEMENT_ID,
        )

        node_ops = [op for op in result.graph_operations if op["op"] == "merge_node"]
        edge_ops = [op for op in result.graph_operations if op["op"] == "merge_edge"]

        assert len(node_ops) == 1
        assert node_ops[0]["properties"]["source_connector"] == "celonis"

        assert len(edge_ops) == 1
        assert edge_ops[0]["properties"]["source_connector"] == "celonis"

    def test_nodes_preserve_celonis_ids_as_external_id(self) -> None:
        """Original Celonis node IDs preserved as external_id."""
        result = import_process_model(
            [SAMPLE_NODE_1],
            [],
            engagement_id=ENGAGEMENT_ID,
        )

        node_ops = [op for op in result.graph_operations if op["op"] == "merge_node"]
        assert node_ops[0]["properties"]["external_id"] == "n1"

    def test_node_id_uses_celonis_prefix(self) -> None:
        """ProcessElement ID uses celonis: prefix."""
        result = import_process_model(
            [SAMPLE_NODE_1],
            [],
            engagement_id=ENGAGEMENT_ID,
        )

        node_ops = [op for op in result.graph_operations if op["op"] == "merge_node"]
        assert node_ops[0]["id"] == "celonis:n1"

    def test_precedes_edge_references(self) -> None:
        """PRECEDES edges reference correct from/to node IDs."""
        result = import_process_model(
            [SAMPLE_NODE_1, SAMPLE_NODE_2],
            [SAMPLE_FLOW_1],
            engagement_id=ENGAGEMENT_ID,
        )

        edge_ops = [op for op in result.graph_operations if op["op"] == "merge_edge"]
        assert edge_ops[0]["from_id"] == "celonis:n1"
        assert edge_ops[0]["to_id"] == "celonis:n2"
        assert edge_ops[0]["type"] == "PRECEDES"

    def test_missing_node_id_skipped(self) -> None:
        """Nodes without an ID are skipped."""
        result = import_process_model(
            [{"activityName": "No ID"}],
            [],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.node_count == 0
        assert len(result.errors) == 1

    def test_engagement_id_on_nodes(self) -> None:
        """ProcessElement nodes include engagement_id."""
        result = import_process_model(
            [SAMPLE_NODE_1],
            [],
            engagement_id=ENGAGEMENT_ID,
        )

        node_ops = [op for op in result.graph_operations if op["op"] == "merge_node"]
        assert node_ops[0]["properties"]["engagement_id"] == ENGAGEMENT_ID


# --- Scenario 3: Conformance deviation import ---


class TestConformanceDeviationImport:
    """Scenario 3: Conformance deviation import as ConflictObjects."""

    def test_deviations_create_conflict_candidates(self) -> None:
        """Deviations create ConflictObject candidates."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_SEQUENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.success
        assert result.deviation_count == 1
        assert len(result.conflict_candidates) == 1

    def test_sequence_deviation_maps_to_sequence_mismatch(self) -> None:
        """Sequence violations become SEQUENCE_MISMATCH type."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_SEQUENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        conflict = result.conflict_candidates[0]
        assert conflict["mismatch_type"] == "sequence_mismatch"

    def test_existence_deviation_maps_to_existence_mismatch(self) -> None:
        """Missing activity deviations become EXISTENCE_MISMATCH type."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_EXISTENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        conflict = result.conflict_candidates[0]
        assert conflict["mismatch_type"] == "existence_mismatch"

    def test_conflict_links_to_affected_elements(self) -> None:
        """ConflictObject includes affected ProcessElement names."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_SEQUENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        conflict = result.conflict_candidates[0]
        assert conflict["affected_activity"] == "Approve Order"
        assert conflict["expected_activity"] == "Create Order"

    def test_severity_from_conformance_score(self) -> None:
        """Celonis conformance score mapped to severity indicator."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_SEQUENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        conflict = result.conflict_candidates[0]
        # Score 0.45 < 0.6 → HIGH severity
        assert conflict["severity"] == SEVERITY_HIGH
        assert conflict["conformance_score"] == 0.45

    def test_medium_severity_mapping(self) -> None:
        """Score 0.6-0.8 maps to MEDIUM severity."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_EXISTENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        conflict = result.conflict_candidates[0]
        # Score 0.72, 0.6 <= 0.72 < 0.8 → MEDIUM
        assert conflict["severity"] == SEVERITY_MEDIUM

    def test_low_severity_mapping(self) -> None:
        """Score > 0.8 maps to LOW severity."""
        deviation = {
            "deviationId": "dev-003",
            "deviationType": "sequence_violation",
            "affectedActivity": "Archive",
            "conformanceScore": 0.92,
            "caseCount": 10,
        }
        result = import_conformance_results(
            [deviation],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.conflict_candidates[0]["severity"] == SEVERITY_LOW

    def test_conflict_includes_celonis_deviation_id(self) -> None:
        """ConflictObject preserves Celonis deviation_id."""
        result = import_conformance_results(
            [SAMPLE_DEVIATION_SEQUENCE],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.conflict_candidates[0]["celonis_deviation_id"] == "dev-001"


# --- Scenario 4: Partial import and checkpoint ---


class TestPartialImportAndCheckpoint:
    """Scenario 4: Graceful handling of Celonis API unavailability."""

    def test_partial_results_preserved_on_error(self) -> None:
        """Events imported before error are preserved."""
        # Simulate: 2 good events, 1 bad event
        events_data = [
            SAMPLE_EVENT_1,
            SAMPLE_EVENT_2,
            {"bad": "data"},  # This will produce an error
        ]
        result = import_event_log(events_data, engagement_id=ENGAGEMENT_ID)

        # Good events are still imported
        assert result.event_count == 2
        assert len(result.errors) == 1
        assert result.success  # Partial success

    def test_checkpoint_set_for_resume(self) -> None:
        """Checkpoint timestamp available for retry."""
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_2],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.checkpoint != ""
        assert result.checkpoint == "2026-01-15T09:05:00Z"

    def test_import_status_defaults_to_complete(self) -> None:
        """Successful import has status 'complete'."""
        result = import_event_log(
            [SAMPLE_EVENT_1],
            engagement_id=ENGAGEMENT_ID,
        )

        assert result.status == "complete"

    def test_seen_event_ids_tracked_for_resume(self) -> None:
        """Seen event IDs are tracked for idempotent resume."""
        result = import_event_log(
            [SAMPLE_EVENT_1, SAMPLE_EVENT_2],
            engagement_id=ENGAGEMENT_ID,
        )

        assert "evt-001" in result.seen_event_ids
        assert "evt-002" in result.seen_event_ids


# --- Conformance score mapping tests ---


class TestConformanceScoreMapping:
    """conformance_score_to_severity function."""

    def test_high_severity_below_0_6(self) -> None:
        assert conformance_score_to_severity(0.3) == SEVERITY_HIGH
        assert conformance_score_to_severity(0.59) == SEVERITY_HIGH

    def test_medium_severity_0_6_to_0_8(self) -> None:
        assert conformance_score_to_severity(0.6) == SEVERITY_MEDIUM
        assert conformance_score_to_severity(0.79) == SEVERITY_MEDIUM

    def test_low_severity_above_0_8(self) -> None:
        assert conformance_score_to_severity(0.8) == SEVERITY_LOW
        assert conformance_score_to_severity(0.95) == SEVERITY_LOW

    def test_zero_score_is_high(self) -> None:
        assert conformance_score_to_severity(0.0) == SEVERITY_HIGH

    def test_perfect_score_is_low(self) -> None:
        assert conformance_score_to_severity(1.0) == SEVERITY_LOW


# --- Data structure tests ---


class TestCelonisDataStructures:
    """Data parsing and structure tests."""

    def test_celonis_event_from_standard_keys(self) -> None:
        event = CelonisEvent.from_api_response(SAMPLE_EVENT_1)
        assert event.case_id == "case-100"
        assert event.activity == "Create Order"
        assert event.duration == 120

    def test_celonis_process_node_from_api(self) -> None:
        node = CelonisProcessNode.from_api_response(SAMPLE_NODE_1)
        assert node.node_id == "n1"
        assert node.activity_name == "Create Order"
        assert node.frequency == 500

    def test_celonis_sequence_flow_from_api(self) -> None:
        flow = CelonisSequenceFlow.from_api_response(SAMPLE_FLOW_1)
        assert flow.source_node_id == "n1"
        assert flow.target_node_id == "n2"
        assert flow.frequency == 480

    def test_celonis_deviation_from_api(self) -> None:
        dev = CelonisDeviation.from_api_response(SAMPLE_DEVIATION_SEQUENCE)
        assert dev.deviation_id == "dev-001"
        assert dev.deviation_type == "sequence_violation"
        assert dev.conformance_score == 0.45

    def test_event_log_result_not_successful_when_empty(self) -> None:
        result = EventLogImportResult()
        assert not result.success

    def test_conformance_result_not_successful_with_errors(self) -> None:
        result = ConformanceImportResult(
            deviations=[CelonisDeviation(deviation_id="x", deviation_type="seq", affected_activity="A")],
            errors=["something wrong"],
        )
        assert not result.success

    def test_conformance_mapper_role_deviation(self) -> None:
        """Role deviations map to role_mismatch."""
        mapper = CelonisConformanceMapper(engagement_id=ENGAGEMENT_ID)
        deviation = CelonisDeviation(
            deviation_id="dev-r1",
            deviation_type="resource_mismatch",
            affected_activity="Review",
            conformance_score=0.65,
        )
        conflict = mapper.map_deviation(deviation)
        assert conflict["mismatch_type"] == "role_mismatch"

    def test_conformance_mapper_builds_description(self) -> None:
        """Auto-generated description when none provided."""
        mapper = CelonisConformanceMapper(engagement_id=ENGAGEMENT_ID)
        deviation = CelonisDeviation(
            deviation_id="dev-d1",
            deviation_type="sequence",
            affected_activity="Ship",
            expected_activity="Pack",
            conformance_score=0.50,
            case_count=42,
        )
        conflict = mapper.map_deviation(deviation)
        assert "expected 'Pack'" in conflict["description"]
        assert "found 'Ship'" in conflict["description"]
        assert "42 cases" in conflict["description"]

    def test_conformance_score_clamps_negative(self) -> None:
        """Negative conformance score is clamped to HIGH severity."""
        assert conformance_score_to_severity(-0.5) == SEVERITY_HIGH

    def test_conformance_score_clamps_above_one(self) -> None:
        """Score > 1.0 is clamped to LOW severity."""
        assert conformance_score_to_severity(1.5) == SEVERITY_LOW

    def test_malformed_event_triggers_exception_handler(self) -> None:
        """Malformed event data triggers ValueError exception path."""
        malformed = {
            "case_id": "x",
            "activity": "y",
            "duration": "not-a-number",
        }
        result = import_event_log([malformed], engagement_id=ENGAGEMENT_ID)
        assert len(result.errors) == 1
        assert "Failed to parse event" in result.errors[0]

    def test_unknown_deviation_type_uses_default_mismatch(self) -> None:
        """Unrecognized deviation type falls back to sequence_mismatch."""
        mapper = CelonisConformanceMapper(engagement_id=ENGAGEMENT_ID)
        deviation = CelonisDeviation(
            deviation_id="dev-u1",
            deviation_type="completely_unknown_type",
            affected_activity="Task",
            conformance_score=0.50,
        )
        conflict = mapper.map_deviation(deviation)
        assert conflict["mismatch_type"] == "sequence_mismatch"

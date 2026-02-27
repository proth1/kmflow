"""BDD tests for Rule and Existence Conflict Detection (Story #375).

Covers 3 acceptance scenarios:
1. Rule value mismatch creates RULE_MISMATCH ConflictObject
2. Existence mismatch when one source omits an activity
3. Temporal shift suggested when effective dates explain the conflict

Plus unit tests for authority weights, temporal resolution, and pipeline integration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ConflictObject, MismatchType, ResolutionStatus
from src.semantic.conflict_detection import (
    DEFAULT_AUTHORITY_WEIGHTS,
    DetectedConflict,
    DetectionResult,
    ExistenceConflictDetector,
    RuleConflictDetector,
    check_temporal_resolution,
    get_authority_weight,
    run_conflict_detection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = str(uuid.uuid4())
SOURCE_A = str(uuid.uuid4())
SOURCE_B = str(uuid.uuid4())


def _make_graph_service(records: list[dict[str, Any]]) -> Any:
    """Create a mock graph service returning the given records."""
    svc = MagicMock()
    svc.run_query = AsyncMock(return_value=records)
    return svc


def _make_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None  # No existing conflicts
    session.execute = AsyncMock(return_value=result_mock)
    session.flush = AsyncMock()
    return session


# ===========================================================================
# Scenario 1: Rule value mismatch creates RULE_MISMATCH ConflictObject
# ===========================================================================


class TestScenario1RuleMismatch:
    """Rule conflict detection for contradictory business rules."""

    @pytest.mark.asyncio
    async def test_rule_mismatch_detected(self) -> None:
        """Given two sources with different approval thresholds,
        When the rule conflict detector runs,
        Then a RULE_MISMATCH ConflictObject is created."""
        records = [
            {
                "activity_name": "Approve Transaction",
                "rule_text_a": "Approval required for transactions > $10,000",
                "rule_text_b": "Approval required for transactions > $5,000",
                "threshold_a": 10000,
                "threshold_b": 5000,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.8,
                "weight_b": 0.7,
                "created_a": None,
                "created_b": None,
                "effective_from_a": None,
                "effective_to_a": None,
                "effective_from_b": None,
                "effective_to_b": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.mismatch_type == MismatchType.RULE_MISMATCH
        assert c.source_a_id == SOURCE_A
        assert c.source_b_id == SOURCE_B

    @pytest.mark.asyncio
    async def test_rule_text_stored_in_conflict_detail(self) -> None:
        """Rule text from each source is stored in conflict_detail for SME review."""
        records = [
            {
                "activity_name": "Approve Transaction",
                "rule_text_a": "Approval required for transactions > $10,000",
                "rule_text_b": "Approval required for transactions > $5,000",
                "threshold_a": 10000,
                "threshold_b": 5000,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.8,
                "weight_b": 0.7,
                "created_a": None,
                "created_b": None,
                "effective_from_a": None,
                "effective_to_a": None,
                "effective_from_b": None,
                "effective_to_b": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        detail = conflicts[0].conflict_detail

        assert detail is not None
        assert detail["rule_text_a"] == "Approval required for transactions > $10,000"
        assert detail["rule_text_b"] == "Approval required for transactions > $5,000"
        assert detail["threshold_a"] == 10000
        assert detail["threshold_b"] == 5000
        assert detail["activity"] == "Approve Transaction"

    @pytest.mark.asyncio
    async def test_rule_conflict_references_both_sources(self) -> None:
        """Conflict references both source evidence items."""
        records = [
            {
                "activity_name": "Approve Transaction",
                "rule_text_a": "Rule A",
                "rule_text_b": "Rule B",
                "threshold_a": 100,
                "threshold_b": 200,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.5,
                "weight_b": 0.5,
                "created_a": None,
                "created_b": None,
                "effective_from_a": None,
                "effective_to_a": None,
                "effective_from_b": None,
                "effective_to_b": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        c = conflicts[0]

        assert c.edge_a_data["rule_text"] == "Rule A"
        assert c.edge_b_data["rule_text"] == "Rule B"
        assert "Rule A" in c.detail
        assert "Rule B" in c.detail

    @pytest.mark.asyncio
    async def test_no_rule_conflicts_returns_empty(self) -> None:
        """No conflicts when no rule mismatches exist."""
        graph = _make_graph_service([])
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_rule_conflict_graph_failure_returns_empty(self) -> None:
        """Graph connection failure returns empty list without crashing."""
        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=ConnectionError("Neo4j down"))
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        assert conflicts == []


# ===========================================================================
# Scenario 2: Existence mismatch when one source omits an activity
# ===========================================================================


class TestScenario2ExistenceMismatch:
    """Existence conflict detection when one source omits an activity."""

    @pytest.mark.asyncio
    async def test_existence_mismatch_detected(self) -> None:
        """Given Source A includes 'Quality Check' but Source B omits it,
        When the existence conflict detector runs,
        Then an EXISTENCE_MISMATCH ConflictObject is created."""
        records = [
            {
                "activity_name": "Quality Check",
                "source_present_id": SOURCE_A,
                "source_absent_id": SOURCE_B,
                "type_present": "policy_document",
                "type_absent": "interview_transcript",
                "weight_present": 0.9,
                "weight_absent": 0.5,
                "created_present": None,
                "created_absent": None,
                "effective_from_present": None,
                "effective_to_present": None,
                "effective_from_absent": None,
                "effective_to_absent": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.mismatch_type == MismatchType.EXISTENCE_MISMATCH
        assert c.source_a_id == SOURCE_A
        assert c.source_b_id == SOURCE_B

    @pytest.mark.asyncio
    async def test_severity_reflects_authority_weight(self) -> None:
        """Severity reflects weight differential (policy doc vs interview)."""
        records = [
            {
                "activity_name": "Quality Check",
                "source_present_id": SOURCE_A,
                "source_absent_id": SOURCE_B,
                "type_present": "policy_document",
                "type_absent": "interview_transcript",
                "weight_present": 0.9,
                "weight_absent": 0.5,
                "created_present": None,
                "created_absent": None,
                "effective_from_present": None,
                "effective_to_present": None,
                "effective_from_absent": None,
                "effective_to_absent": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        c = conflicts[0]

        # Weight diff = |0.9 - 0.5| = 0.4, base_severity = 0.6
        assert c.severity_score < 0.8  # Not critical (large weight diff)
        assert c.severity_label in ("medium", "high")

    @pytest.mark.asyncio
    async def test_conflict_detail_notes_authority(self) -> None:
        """Conflict detail notes the authority weight comparison."""
        records = [
            {
                "activity_name": "Quality Check",
                "source_present_id": SOURCE_A,
                "source_absent_id": SOURCE_B,
                "type_present": "policy_document",
                "type_absent": "interview_transcript",
                "weight_present": 0.9,
                "weight_absent": 0.5,
                "created_present": None,
                "created_absent": None,
                "effective_from_present": None,
                "effective_to_present": None,
                "effective_from_absent": None,
                "effective_to_absent": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        detail = conflicts[0].conflict_detail

        assert detail is not None
        assert "lower" in detail["note"]  # interview has lower weight than policy
        assert detail["source_present_type"] == "policy_document"
        assert detail["source_absent_type"] == "interview_transcript"

    @pytest.mark.asyncio
    async def test_existence_uses_default_authority_weights(self) -> None:
        """When graph returns default 0.5 weight, evidence type lookup is used."""
        records = [
            {
                "activity_name": "Quality Check",
                "source_present_id": SOURCE_A,
                "source_absent_id": SOURCE_B,
                "type_present": "policy_document",
                "type_absent": "interview_transcript",
                "weight_present": 0.5,  # Default → will be overridden by type lookup
                "weight_absent": 0.5,  # Default → will be overridden by type lookup
                "created_present": None,
                "created_absent": None,
                "effective_from_present": None,
                "effective_to_present": None,
                "effective_from_absent": None,
                "effective_to_absent": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        detail = conflicts[0].conflict_detail

        # Policy doc should get 0.9, interview 0.5
        assert detail["weight_present"] == 0.9
        assert detail["weight_absent"] == 0.5

    @pytest.mark.asyncio
    async def test_existence_graph_failure_returns_empty(self) -> None:
        """Graph connection failure returns empty list without crashing."""
        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=ConnectionError("Neo4j down"))
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        assert conflicts == []


# ===========================================================================
# Scenario 3: Temporal shift suggested when effective dates explain conflict
# ===========================================================================


class TestScenario3TemporalResolution:
    """Temporal resolution when effective dates explain the conflict."""

    def test_non_overlapping_ranges_suggest_temporal_shift(self) -> None:
        """Non-overlapping date ranges return TEMPORAL_SHIFT annotation."""
        result = check_temporal_resolution(
            effective_from_a=date(2022, 1, 1),
            effective_to_a=date(2023, 12, 31),
            effective_from_b=date(2024, 1, 1),
            effective_to_b=None,
        )

        assert result is not None
        assert result["resolution_type"] == "TEMPORAL_SHIFT"
        assert "2022" in result["annotation"]
        assert "2024" in result["annotation"]

    def test_overlapping_ranges_return_none(self) -> None:
        """Overlapping date ranges do not suggest temporal shift."""
        result = check_temporal_resolution(
            effective_from_a=date(2022, 1, 1),
            effective_to_a=date(2024, 6, 30),
            effective_from_b=date(2024, 1, 1),
            effective_to_b=None,
        )

        assert result is None

    def test_missing_dates_return_none(self) -> None:
        """Missing effective dates cannot suggest temporal resolution."""
        result = check_temporal_resolution(
            effective_from_a=date(2022, 1, 1),
            effective_to_a=None,
            effective_from_b=None,
            effective_to_b=None,
        )

        assert result is None

    def test_both_dates_none_returns_none(self) -> None:
        """Both dates None cannot suggest temporal resolution."""
        result = check_temporal_resolution(None, None, None, None)
        assert result is None

    def test_datetime_inputs_normalised_to_date(self) -> None:
        """Datetime inputs are normalised for comparison."""
        result = check_temporal_resolution(
            effective_from_a=datetime(2022, 1, 1, 12, 0),
            effective_to_a=datetime(2023, 12, 31, 23, 59),
            effective_from_b=datetime(2024, 1, 1, 0, 0),
            effective_to_b=None,
        )

        assert result is not None
        assert result["resolution_type"] == "TEMPORAL_SHIFT"

    @pytest.mark.asyncio
    async def test_rule_conflict_with_temporal_shift(self) -> None:
        """Rule conflict with non-overlapping dates gets TEMPORAL_SHIFT hint."""
        records = [
            {
                "activity_name": "Approve Transaction",
                "rule_text_a": "Approval > $10,000",
                "rule_text_b": "Approval > $5,000",
                "threshold_a": 10000,
                "threshold_b": 5000,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.8,
                "weight_b": 0.7,
                "created_a": None,
                "created_b": None,
                "effective_from_a": date(2022, 1, 1),
                "effective_to_a": date(2023, 12, 31),
                "effective_from_b": date(2024, 1, 1),
                "effective_to_b": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = RuleConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        c = conflicts[0]

        assert c.resolution_hint == "temporal_shift"
        assert c.conflict_detail is not None
        assert "temporal_annotation" in c.conflict_detail
        assert "2022" in c.conflict_detail["temporal_annotation"]
        assert "2024" in c.conflict_detail["temporal_annotation"]

    @pytest.mark.asyncio
    async def test_existence_conflict_with_temporal_shift(self) -> None:
        """Existence conflict with non-overlapping dates gets TEMPORAL_SHIFT hint."""
        records = [
            {
                "activity_name": "Quality Check",
                "source_present_id": SOURCE_A,
                "source_absent_id": SOURCE_B,
                "type_present": "policy_document",
                "type_absent": "interview_transcript",
                "weight_present": 0.9,
                "weight_absent": 0.5,
                "created_present": None,
                "created_absent": None,
                "effective_from_present": date(2022, 1, 1),
                "effective_to_present": date(2023, 6, 30),
                "effective_from_absent": date(2024, 1, 1),
                "effective_to_absent": None,
            }
        ]
        graph = _make_graph_service(records)
        detector = ExistenceConflictDetector(graph)

        conflicts = await detector.detect(ENGAGEMENT_ID)
        c = conflicts[0]

        assert c.resolution_hint == "temporal_shift"
        assert c.conflict_detail is not None
        assert "temporal_annotation" in c.conflict_detail

    @pytest.mark.asyncio
    async def test_conflict_status_open_with_resolution_hint(self) -> None:
        """ConflictObject status remains UNRESOLVED but resolution_hint is set."""
        records = [
            {
                "activity_name": "Approve Transaction",
                "rule_text_a": "Rule A",
                "rule_text_b": "Rule B",
                "threshold_a": 100,
                "threshold_b": 200,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.5,
                "weight_b": 0.5,
                "created_a": None,
                "created_b": None,
                "effective_from_a": date(2022, 1, 1),
                "effective_to_a": date(2023, 12, 31),
                "effective_from_b": date(2024, 1, 1),
                "effective_to_b": None,
            }
        ]
        graph = _make_graph_service(records)
        session = _make_session()

        # Run full pipeline
        await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        # Verify the added ConflictObject has UNRESOLVED status + hint
        added_calls = session.add.call_args_list
        rule_added = [
            call
            for call in added_calls
            if isinstance(call[0][0], ConflictObject) and call[0][0].mismatch_type == MismatchType.RULE_MISMATCH
        ]
        assert len(rule_added) >= 1
        obj = rule_added[0][0][0]
        assert obj.resolution_status == ResolutionStatus.UNRESOLVED
        assert obj.resolution_hint == "temporal_shift"


# ===========================================================================
# Authority weight configuration tests
# ===========================================================================


class TestAuthorityWeights:
    """Tests for configurable authority weights per evidence category."""

    def test_policy_document_weight(self) -> None:
        assert get_authority_weight("policy_document") == 0.9

    def test_interview_weight(self) -> None:
        assert get_authority_weight("interview_transcript") == 0.5

    def test_unknown_type_defaults_to_half(self) -> None:
        assert get_authority_weight("unknown_type") == 0.5

    def test_none_type_defaults_to_half(self) -> None:
        assert get_authority_weight(None) == 0.5

    def test_all_weights_valid_range(self) -> None:
        for weight in DEFAULT_AUTHORITY_WEIGHTS.values():
            assert 0.0 <= weight <= 1.0


# ===========================================================================
# Pipeline integration tests
# ===========================================================================


class TestPipelineIntegration:
    """Pipeline integrates all four detector types."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_all_four_detectors(self) -> None:
        """Pipeline runs sequence, role, rule, and existence detectors."""
        graph = _make_graph_service([])
        session = _make_session()

        result = await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        # Should have called run_query at least 4 times (one per detector)
        assert graph.run_query.call_count >= 4
        assert isinstance(result, DetectionResult)
        assert result.sequence_conflicts_found == 0
        assert result.role_conflicts_found == 0
        assert result.rule_conflicts_found == 0
        assert result.existence_conflicts_found == 0

    @pytest.mark.asyncio
    async def test_pipeline_persists_conflict_detail_and_hint(self) -> None:
        """Persisted ConflictObject includes conflict_detail and resolution_hint."""
        # Return a rule conflict with temporal shift from one of the detectors
        call_count = 0

        async def _mock_query(query: str, params: dict) -> list:
            nonlocal call_count
            call_count += 1
            # 3rd call is the rule detector (after seq + role)
            if call_count == 3:
                return [
                    {
                        "activity_name": "Approve",
                        "rule_text_a": "Rule A",
                        "rule_text_b": "Rule B",
                        "threshold_a": 100,
                        "threshold_b": 200,
                        "source_a_id": SOURCE_A,
                        "source_b_id": SOURCE_B,
                        "weight_a": 0.5,
                        "weight_b": 0.5,
                        "created_a": None,
                        "created_b": None,
                        "effective_from_a": date(2022, 1, 1),
                        "effective_to_a": date(2023, 12, 31),
                        "effective_from_b": date(2024, 1, 1),
                        "effective_to_b": None,
                    }
                ]
            return []

        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=_mock_query)
        session = _make_session()

        result = await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        assert result.rule_conflicts_found == 1
        # Check persisted object
        added_calls = session.add.call_args_list
        assert len(added_calls) == 1
        obj = added_calls[0][0][0]
        assert isinstance(obj, ConflictObject)
        assert obj.conflict_detail is not None
        assert obj.conflict_detail["rule_text_a"] == "Rule A"
        assert obj.resolution_hint == "temporal_shift"

    @pytest.mark.asyncio
    async def test_pipeline_idempotent_for_rule_conflicts(self) -> None:
        """Re-running pipeline with existing rule conflict skips duplicate."""
        records = [
            {
                "activity_name": "Approve",
                "rule_text_a": "Rule A",
                "rule_text_b": "Rule B",
                "threshold_a": 100,
                "threshold_b": 200,
                "source_a_id": SOURCE_A,
                "source_b_id": SOURCE_B,
                "weight_a": 0.5,
                "weight_b": 0.5,
                "created_a": None,
                "created_b": None,
                "effective_from_a": None,
                "effective_to_a": None,
                "effective_from_b": None,
                "effective_to_b": None,
            }
        ]
        call_count = 0

        async def _mock_query(query: str, params: dict) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 3:  # Rule detector
                return records
            return []

        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=_mock_query)

        # Session returns existing conflict for duplicates
        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()  # Existing found
        session.execute = AsyncMock(return_value=existing_result)
        session.flush = AsyncMock()

        result = await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        assert result.rule_conflicts_found == 1
        session.add.assert_not_called()  # Duplicate not persisted


# ===========================================================================
# ConflictObject model field tests
# ===========================================================================


class TestConflictObjectModelFields:
    """Verify the new model fields exist."""

    def test_conflict_detail_field_exists(self) -> None:
        assert hasattr(ConflictObject, "conflict_detail")

    def test_resolution_hint_field_exists(self) -> None:
        assert hasattr(ConflictObject, "resolution_hint")

    def test_detection_result_has_rule_count(self) -> None:
        r = DetectionResult(engagement_id="test")
        assert r.rule_conflicts_found == 0

    def test_detection_result_has_existence_count(self) -> None:
        r = DetectionResult(engagement_id="test")
        assert r.existence_conflicts_found == 0

    def test_detected_conflict_has_detail_fields(self) -> None:
        c = DetectedConflict(
            mismatch_type=MismatchType.RULE_MISMATCH,
            engagement_id="test",
            source_a_id="a",
            source_b_id="b",
            severity_score=0.5,
            severity_label="medium",
            conflict_detail={"rule_text_a": "X"},
            resolution_hint="temporal_shift",
        )
        assert c.conflict_detail == {"rule_text_a": "X"}
        assert c.resolution_hint == "temporal_shift"

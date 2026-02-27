"""Tests for ConflictObject model and schemas (Story #299).

Covers all 5 BDD scenarios plus enum and model structure tests.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.api.schemas.conflict import (
    ConflictObjectCreate,
    ConflictObjectRead,
    ConflictResolutionUpdate,
)
from src.core.models.conflict import (
    ConflictObject,
    MismatchType,
    ResolutionStatus,
    ResolutionType,
)

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestMismatchType:
    """MismatchType enum completeness per PRD Section 6.10.5."""

    def test_all_six_types_present(self) -> None:
        types = list(MismatchType)
        assert len(types) == 6

    def test_mismatch_type_values(self) -> None:
        expected = {
            "sequence_mismatch",
            "role_mismatch",
            "rule_mismatch",
            "existence_mismatch",
            "io_mismatch",
            "control_gap",
        }
        assert {t.value for t in MismatchType} == expected


class TestResolutionType:
    """ResolutionType enum — three-way distinction."""

    def test_all_three_types_present(self) -> None:
        types = list(ResolutionType)
        assert len(types) == 3

    def test_resolution_type_values(self) -> None:
        expected = {"genuine_disagreement", "naming_variant", "temporal_shift"}
        assert {t.value for t in ResolutionType} == expected


class TestResolutionStatus:
    """ResolutionStatus lifecycle states."""

    def test_all_three_states_present(self) -> None:
        states = list(ResolutionStatus)
        assert len(states) == 3

    def test_resolution_status_values(self) -> None:
        expected = {"unresolved", "resolved", "escalated"}
        assert {s.value for s in ResolutionStatus} == expected


# ---------------------------------------------------------------------------
# SQLAlchemy Model Tests
# ---------------------------------------------------------------------------


class TestConflictObjectModel:
    """SQLAlchemy model structure tests."""

    def test_table_name(self) -> None:
        assert ConflictObject.__tablename__ == "conflict_objects"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in ConflictObject.__table__.columns}
        expected = {
            "id",
            "engagement_id",
            "mismatch_type",
            "resolution_type",
            "resolution_status",
            "source_a_id",
            "source_b_id",
            "severity",
            "escalation_flag",
            "resolution_notes",
            "created_at",
            "resolved_at",
        }
        assert expected.issubset(cols)

    def test_composite_index_exists(self) -> None:
        index_names = {idx.name for idx in ConflictObject.__table__.indexes}
        assert "ix_conflict_objects_engagement_status" in index_names

    def test_engagement_id_indexed(self) -> None:
        index_names = {idx.name for idx in ConflictObject.__table__.indexes}
        assert "ix_conflict_objects_engagement_id" in index_names

    def test_source_id_indexes(self) -> None:
        index_names = {idx.name for idx in ConflictObject.__table__.indexes}
        assert "ix_conflict_objects_source_a_id" in index_names
        assert "ix_conflict_objects_source_b_id" in index_names

    def test_engagement_fk(self) -> None:
        col = ConflictObject.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"

    def test_source_a_fk(self) -> None:
        col = ConflictObject.__table__.columns["source_a_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "evidence_items.id"

    def test_source_b_fk(self) -> None:
        col = ConflictObject.__table__.columns["source_b_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "evidence_items.id"

    def test_resolution_status_default(self) -> None:
        col = ConflictObject.__table__.columns["resolution_status"]
        assert col.default is not None
        assert col.default.arg == ResolutionStatus.UNRESOLVED

    def test_repr(self) -> None:
        obj = ConflictObject(
            id=uuid.uuid4(),
            mismatch_type=MismatchType.SEQUENCE_MISMATCH,
            resolution_status=ResolutionStatus.UNRESOLVED,
        )
        r = repr(obj)
        assert "ConflictObject" in r
        assert "sequence_mismatch" in r
        assert "unresolved" in r


# ---------------------------------------------------------------------------
# BDD Scenario 1: SEQUENCE_MISMATCH conflict created
# ---------------------------------------------------------------------------


class TestBDDScenario1SequenceMismatch:
    """Scenario 1: SEQUENCE_MISMATCH ConflictObject created."""

    def test_conflict_fields_set_correctly(self) -> None:
        eng_id = uuid.uuid4()
        ev_a = uuid.uuid4()
        ev_b = uuid.uuid4()

        conflict = ConflictObject(
            id=uuid.uuid4(),
            engagement_id=eng_id,
            mismatch_type=MismatchType.SEQUENCE_MISMATCH,
            source_a_id=ev_a,
            source_b_id=ev_b,
            resolution_status=ResolutionStatus.UNRESOLVED,
        )

        assert conflict.engagement_id == eng_id
        assert conflict.mismatch_type == MismatchType.SEQUENCE_MISMATCH
        assert conflict.source_a_id == ev_a
        assert conflict.source_b_id == ev_b
        assert conflict.resolution_status == ResolutionStatus.UNRESOLVED

    def test_pydantic_create_schema_accepts_valid_conflict(self) -> None:
        payload = ConflictObjectCreate(
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.SEQUENCE_MISMATCH,
            source_a_id=uuid.uuid4(),
            source_b_id=uuid.uuid4(),
            severity=0.8,
        )

        assert payload.mismatch_type == MismatchType.SEQUENCE_MISMATCH
        assert payload.severity == 0.8


# ---------------------------------------------------------------------------
# BDD Scenario 2: NAMING_VARIANT resolution
# ---------------------------------------------------------------------------


class TestBDDScenario2NamingVariantResolution:
    """Scenario 2: ConflictObject resolved as NAMING_VARIANT."""

    def test_resolution_update_schema(self) -> None:
        update = ConflictResolutionUpdate(
            resolution_type=ResolutionType.NAMING_VARIANT,
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_notes="Merged 'Know Your Customer Review' into 'KYC Check'",
        )

        assert update.resolution_type == ResolutionType.NAMING_VARIANT
        assert update.resolution_status == ResolutionStatus.RESOLVED

    def test_model_accepts_resolved_state(self) -> None:
        conflict = ConflictObject(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.EXISTENCE_MISMATCH,
            resolution_type=ResolutionType.NAMING_VARIANT,
            resolution_status=ResolutionStatus.RESOLVED,
        )

        assert conflict.resolution_type == ResolutionType.NAMING_VARIANT
        assert conflict.resolution_status == ResolutionStatus.RESOLVED


# ---------------------------------------------------------------------------
# BDD Scenario 3: CONTROL_GAP escalation after 48 hours
# ---------------------------------------------------------------------------


class TestBDDScenario3Escalation:
    """Scenario 3: CONTROL_GAP conflict escalation."""

    def test_escalation_flag_defaults_to_false(self) -> None:
        col = ConflictObject.__table__.columns["escalation_flag"]
        assert col.default is not None
        assert col.default.arg is False

    def test_model_accepts_escalated_state(self) -> None:
        conflict = ConflictObject(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.CONTROL_GAP,
            resolution_status=ResolutionStatus.ESCALATED,
            escalation_flag=True,
        )

        assert conflict.resolution_status == ResolutionStatus.ESCALATED
        assert conflict.escalation_flag is True

    def test_escalated_status_in_enum(self) -> None:
        assert ResolutionStatus.ESCALATED == "escalated"


# ---------------------------------------------------------------------------
# BDD Scenario 4: Filterable conflicts
# ---------------------------------------------------------------------------


class TestBDDScenario4FilterableConflicts:
    """Scenario 4: ConflictObjects filterable by type and status."""

    def test_composite_index_for_queue_queries(self) -> None:
        """Composite index on (engagement_id, resolution_status) exists."""
        index_names = {idx.name for idx in ConflictObject.__table__.indexes}
        assert "ix_conflict_objects_engagement_status" in index_names

    def test_engagement_id_not_nullable(self) -> None:
        col = ConflictObject.__table__.columns["engagement_id"]
        assert col.nullable is False

    def test_all_mismatch_types_assignable(self) -> None:
        for mt in MismatchType:
            conflict = ConflictObject(
                id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                mismatch_type=mt,
            )
            assert conflict.mismatch_type == mt

    def test_read_schema_serialization(self) -> None:
        read = ConflictObjectRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            mismatch_type="role_mismatch",
            resolution_status="unresolved",
            severity=0.6,
            escalation_flag=False,
            created_at="2026-02-27T12:00:00Z",
        )

        assert read.mismatch_type == "role_mismatch"
        assert read.resolution_status == "unresolved"


# ---------------------------------------------------------------------------
# BDD Scenario 5: TEMPORAL_SHIFT resolution
# ---------------------------------------------------------------------------


class TestBDDScenario5TemporalShiftResolution:
    """Scenario 5: TEMPORAL_SHIFT resolution links to bitemporal validity."""

    def test_temporal_shift_resolution(self) -> None:
        update = ConflictResolutionUpdate(
            resolution_type=ResolutionType.TEMPORAL_SHIFT,
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_notes="Older assertion retracted; newer supersedes",
        )

        assert update.resolution_type == ResolutionType.TEMPORAL_SHIFT
        assert update.resolution_status == ResolutionStatus.RESOLVED

    def test_model_accepts_temporal_shift(self) -> None:
        conflict = ConflictObject(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.RULE_MISMATCH,
            resolution_type=ResolutionType.TEMPORAL_SHIFT,
            resolution_status=ResolutionStatus.RESOLVED,
        )

        assert conflict.resolution_type == ResolutionType.TEMPORAL_SHIFT


# ---------------------------------------------------------------------------
# Edge Case / Validation Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional validation edge cases."""

    def test_severity_bounded_low(self) -> None:
        with pytest.raises(ValidationError):
            ConflictObjectCreate(
                engagement_id=uuid.uuid4(),
                mismatch_type=MismatchType.SEQUENCE_MISMATCH,
                severity=-0.1,
            )

    def test_severity_bounded_high(self) -> None:
        with pytest.raises(ValidationError):
            ConflictObjectCreate(
                engagement_id=uuid.uuid4(),
                mismatch_type=MismatchType.SEQUENCE_MISMATCH,
                severity=1.1,
            )

    def test_severity_at_boundaries(self) -> None:
        low = ConflictObjectCreate(
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.IO_MISMATCH,
            severity=0.0,
        )
        high = ConflictObjectCreate(
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.IO_MISMATCH,
            severity=1.0,
        )
        assert low.severity == 0.0
        assert high.severity == 1.0

    def test_severity_defaults(self) -> None:
        payload = ConflictObjectCreate(
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.ROLE_MISMATCH,
        )
        assert payload.severity == 0.5

    def test_resolution_type_nullable(self) -> None:
        col = ConflictObject.__table__.columns["resolution_type"]
        assert col.nullable is True

    def test_resolved_at_nullable(self) -> None:
        col = ConflictObject.__table__.columns["resolved_at"]
        assert col.nullable is True

    def test_source_ids_nullable(self) -> None:
        col_a = ConflictObject.__table__.columns["source_a_id"]
        col_b = ConflictObject.__table__.columns["source_b_id"]
        assert col_a.nullable is True
        assert col_b.nullable is True

    def test_resolution_notes_optional(self) -> None:
        payload = ConflictObjectCreate(
            engagement_id=uuid.uuid4(),
            mismatch_type=MismatchType.CONTROL_GAP,
        )
        assert payload.resolution_notes is None

    def test_read_schema_with_all_fields(self) -> None:
        read = ConflictObjectRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            mismatch_type="control_gap",
            resolution_type="genuine_disagreement",
            resolution_status="resolved",
            source_a_id=str(uuid.uuid4()),
            source_b_id=str(uuid.uuid4()),
            severity=0.9,
            escalation_flag=True,
            resolution_notes="Confirmed genuine disagreement",
            created_at="2026-02-27T12:00:00Z",
            resolved_at="2026-02-27T14:00:00Z",
        )

        assert read.resolution_type == "genuine_disagreement"
        assert read.resolved_at == "2026-02-27T14:00:00Z"

    def test_genuine_disagreement_resolution(self) -> None:
        update = ConflictResolutionUpdate(
            resolution_type=ResolutionType.GENUINE_DISAGREEMENT,
            resolution_status=ResolutionStatus.RESOLVED,
        )
        assert update.resolution_type == ResolutionType.GENUINE_DISAGREEMENT

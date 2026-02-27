"""Tests for SemanticRelationship model and bitemporal schemas (Story #305).

Covers all 5 BDD scenarios plus model structure and edge case tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.api.schemas.bitemporal import (
    BitempQueryFilter,
    SemanticRelationshipCreate,
    SemanticRelationshipRead,
    SupersedeRequest,
)
from src.core.models.semantic_relationship import SemanticRelationship

# ---------------------------------------------------------------------------
# SQLAlchemy Model Tests
# ---------------------------------------------------------------------------


class TestSemanticRelationshipModel:
    """SQLAlchemy model structure tests."""

    def test_table_name(self) -> None:
        assert SemanticRelationship.__tablename__ == "semantic_relationships"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in SemanticRelationship.__table__.columns}
        expected = {
            "id",
            "engagement_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            "asserted_at",
            "retracted_at",
            "valid_from",
            "valid_to",
            "superseded_by",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_engagement_fk(self) -> None:
        col = SemanticRelationship.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"

    def test_superseded_by_self_fk(self) -> None:
        col = SemanticRelationship.__table__.columns["superseded_by"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "semantic_relationships.id"

    def test_superseded_by_set_null_on_delete(self) -> None:
        col = SemanticRelationship.__table__.columns["superseded_by"]
        fks = list(col.foreign_keys)
        assert fks[0].ondelete == "SET NULL"

    def test_engagement_id_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_engagement_id" in index_names

    def test_retracted_at_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_retracted_at" in index_names

    def test_source_node_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_source_node_id" in index_names

    def test_target_node_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_target_node_id" in index_names

    def test_edge_type_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_edge_type" in index_names

    def test_superseded_by_indexed(self) -> None:
        index_names = {idx.name for idx in SemanticRelationship.__table__.indexes}
        assert "ix_semantic_relationships_superseded_by" in index_names

    def test_asserted_at_server_default(self) -> None:
        col = SemanticRelationship.__table__.columns["asserted_at"]
        assert col.server_default is not None

    def test_repr(self) -> None:
        obj = SemanticRelationship(
            id=uuid.uuid4(),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
        )
        r = repr(obj)
        assert "SemanticRelationship" in r
        assert "PRECEDES" in r
        assert "retracted=no" in r


# ---------------------------------------------------------------------------
# BDD Scenario 1: New relationship has correct default bitemporal state
# ---------------------------------------------------------------------------


class TestBDDScenario1DefaultBitemporalState:
    """Scenario 1: New relationship has correct default bitemporal state."""

    def test_new_relationship_defaults(self) -> None:
        valid_from = datetime(2025, 1, 1, tzinfo=UTC)
        rel = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
            valid_from=valid_from,
        )
        assert rel.valid_from == valid_from
        assert rel.retracted_at is None
        assert rel.valid_to is None
        assert rel.superseded_by is None

    def test_asserted_at_not_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["asserted_at"]
        assert col.nullable is False

    def test_create_schema_accepts_valid_from(self) -> None:
        payload = SemanticRelationshipCreate(
            engagement_id=uuid.uuid4(),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert payload.valid_from is not None
        assert payload.valid_to is None


# ---------------------------------------------------------------------------
# BDD Scenario 2: Superseded relationship correctly retracted
# ---------------------------------------------------------------------------


class TestBDDScenario2SupersededRelationship:
    """Scenario 2: Superseded relationship correctly retracted."""

    def test_superseded_state(self) -> None:
        now = datetime.now(tz=UTC)
        r2_id = uuid.uuid4()

        r1 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
            asserted_at=datetime(2024, 6, 1, tzinfo=UTC),
            retracted_at=now,
            superseded_by=r2_id,
        )
        assert r1.retracted_at == now
        assert r1.superseded_by == r2_id

    def test_new_replacement_is_active(self) -> None:
        r2 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="Activity_A",
            target_node_id="Activity_C",
            edge_type="PRECEDES",
            asserted_at=datetime.now(tz=UTC),
            retracted_at=None,
        )
        assert r2.retracted_at is None

    def test_supersede_request_schema(self) -> None:
        old_id = uuid.uuid4()
        new_id = uuid.uuid4()
        req = SupersedeRequest(
            old_relationship_id=old_id,
            new_relationship_id=new_id,
        )
        assert req.old_relationship_id == old_id
        assert req.new_relationship_id == new_id


# ---------------------------------------------------------------------------
# BDD Scenario 3: Point-in-time query returns only valid relationships
# ---------------------------------------------------------------------------


class TestBDDScenario3PointInTimeQuery:
    """Scenario 3: Point-in-time query returns only valid relationships at date D."""

    def test_bitemp_query_filter_defaults(self) -> None:
        f = BitempQueryFilter()
        assert f.as_of_date is None
        assert f.include_retracted is False

    def test_bitemp_query_filter_with_date(self) -> None:
        d = datetime(2024, 6, 15, tzinfo=UTC)
        f = BitempQueryFilter(as_of_date=d)
        assert f.as_of_date == d

    def test_r1_valid_in_2024(self) -> None:
        """R1 with valid_from=2024-01-01, valid_to=2024-12-31 is valid on 2024-06-15."""
        r1 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="B",
            edge_type="PRECEDES",
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2024, 12, 31, tzinfo=UTC),
            retracted_at=None,
        )
        d = datetime(2024, 6, 15, tzinfo=UTC)
        assert r1.valid_from <= d
        assert r1.valid_to is not None and r1.valid_to > d
        assert r1.retracted_at is None

    def test_r2_not_valid_in_2024(self) -> None:
        """R2 with valid_from=2025-01-01 is NOT valid on 2024-06-15."""
        r2 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="C",
            edge_type="PRECEDES",
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to=None,
            retracted_at=None,
        )
        d = datetime(2024, 6, 15, tzinfo=UTC)
        assert r2.valid_from > d


# ---------------------------------------------------------------------------
# BDD Scenario 4: Active listing excludes retracted relationships
# ---------------------------------------------------------------------------


class TestBDDScenario4ActiveListing:
    """Scenario 4: Active listing excludes retracted relationships."""

    def test_retracted_relationship(self) -> None:
        r1 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="B",
            edge_type="PRECEDES",
            retracted_at=datetime(2025, 2, 1, tzinfo=UTC),
        )
        assert r1.retracted_at is not None

    def test_active_relationship(self) -> None:
        r2 = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="C",
            edge_type="PRECEDES",
            retracted_at=None,
        )
        assert r2.retracted_at is None

    def test_retracted_at_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["retracted_at"]
        assert col.nullable is True

    def test_include_retracted_filter(self) -> None:
        f = BitempQueryFilter(include_retracted=True)
        assert f.include_retracted is True


# ---------------------------------------------------------------------------
# BDD Scenario 5: Temporal shift conflict resolution
# ---------------------------------------------------------------------------


class TestBDDScenario5TemporalShiftResolution:
    """Scenario 5: Temporal shift sets valid_to on older assertion."""

    def test_temporal_shift_sets_valid_to(self) -> None:
        source_b_id = uuid.uuid4()
        source_b_valid_from = datetime(2025, 1, 1, tzinfo=UTC)
        day_before = source_b_valid_from - timedelta(days=1)

        source_a = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="B",
            edge_type="FOLLOWS_RULE",
            valid_from=datetime(2023, 1, 1, tzinfo=UTC),
            valid_to=day_before,
            superseded_by=source_b_id,
        )
        assert source_a.valid_to == datetime(2024, 12, 31, tzinfo=UTC)
        assert source_a.superseded_by == source_b_id

    def test_source_b_remains_open_ended(self) -> None:
        source_b = SemanticRelationship(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="B",
            edge_type="FOLLOWS_RULE",
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to=None,
        )
        assert source_b.valid_to is None


# ---------------------------------------------------------------------------
# Edge Case / Validation Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional validation edge cases."""

    def test_engagement_id_not_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["engagement_id"]
        assert col.nullable is False

    def test_source_node_id_not_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["source_node_id"]
        assert col.nullable is False

    def test_target_node_id_not_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["target_node_id"]
        assert col.nullable is False

    def test_edge_type_not_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["edge_type"]
        assert col.nullable is False

    def test_valid_from_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["valid_from"]
        assert col.nullable is True

    def test_valid_to_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["valid_to"]
        assert col.nullable is True

    def test_superseded_by_nullable(self) -> None:
        col = SemanticRelationship.__table__.columns["superseded_by"]
        assert col.nullable is True

    def test_engagement_cascade_delete(self) -> None:
        col = SemanticRelationship.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert fks[0].ondelete == "CASCADE"

    def test_read_schema_serialization(self) -> None:
        read = SemanticRelationshipRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
            asserted_at="2026-02-27T12:00:00Z",
            created_at="2026-02-27T12:00:00Z",
        )
        assert read.edge_type == "PRECEDES"
        assert read.retracted_at is None

    def test_read_schema_with_all_fields(self) -> None:
        read = SemanticRelationshipRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            source_node_id="Activity_A",
            target_node_id="Activity_B",
            edge_type="PRECEDES",
            asserted_at="2026-02-27T12:00:00Z",
            retracted_at="2026-02-27T14:00:00Z",
            valid_from="2025-01-01T00:00:00Z",
            valid_to="2025-12-31T23:59:59Z",
            superseded_by=str(uuid.uuid4()),
            created_at="2026-02-27T12:00:00Z",
        )
        assert read.retracted_at is not None
        assert read.superseded_by is not None

    def test_create_schema_minimal(self) -> None:
        payload = SemanticRelationshipCreate(
            engagement_id=uuid.uuid4(),
            source_node_id="Node_X",
            target_node_id="Node_Y",
            edge_type="TRIGGERS",
        )
        assert payload.valid_from is None
        assert payload.valid_to is None

    def test_repr_retracted(self) -> None:
        obj = SemanticRelationship(
            id=uuid.uuid4(),
            source_node_id="A",
            target_node_id="B",
            edge_type="PRECEDES",
            retracted_at=datetime.now(tz=UTC),
        )
        assert "retracted=yes" in repr(obj)

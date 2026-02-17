"""Tests for SQLAlchemy ORM models."""

from __future__ import annotations

import uuid

from src.core.models import (
    Engagement,
    EngagementStatus,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    FragmentType,
    ValidationStatus,
)


class TestEngagement:
    """Test suite for the Engagement model."""

    def test_explicit_status(self) -> None:
        """Engagements created with a status should retain it."""
        engagement = Engagement(
            name="Test Engagement",
            client="Test Client",
            business_area="Operations",
            status=EngagementStatus.DRAFT,
        )
        assert engagement.status == EngagementStatus.DRAFT

    def test_status_column_default_defined(self) -> None:
        """The status column should have a server-side default of DRAFT.

        SQLAlchemy 2.x `default=` on mapped_column applies at flush time,
        not at Python object construction. We verify the column metadata
        has the expected default configured.
        """
        col = Engagement.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == EngagementStatus.DRAFT

    def test_engagement_statuses(self) -> None:
        """All expected engagement statuses should be defined."""
        statuses = list(EngagementStatus)
        assert len(statuses) == 5
        assert EngagementStatus.DRAFT in statuses
        assert EngagementStatus.ARCHIVED in statuses

    def test_repr(self) -> None:
        """Engagement repr should include id, name, and client."""
        engagement = Engagement(
            id=uuid.uuid4(),
            name="Test",
            client="Client",
            business_area="Ops",
        )
        assert "Test" in repr(engagement)
        assert "Client" in repr(engagement)


class TestEvidenceItem:
    """Test suite for the EvidenceItem model."""

    def test_quality_score_calculation(self) -> None:
        """quality_score should be the average of four quality dimensions."""
        item = EvidenceItem(
            name="test.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            completeness_score=0.8,
            reliability_score=0.6,
            freshness_score=0.9,
            consistency_score=0.7,
            engagement_id=uuid.uuid4(),
        )
        expected = (0.8 + 0.6 + 0.9 + 0.7) / 4.0
        assert abs(item.quality_score - expected) < 0.001

    def test_quality_score_zeros(self) -> None:
        """quality_score with all zeros should be 0.0."""
        item = EvidenceItem(
            name="empty.csv",
            category=EvidenceCategory.STRUCTURED_DATA,
            format="csv",
            completeness_score=0.0,
            reliability_score=0.0,
            freshness_score=0.0,
            consistency_score=0.0,
            engagement_id=uuid.uuid4(),
        )
        assert item.quality_score == 0.0

    def test_validation_status_column_default_defined(self) -> None:
        """The validation_status column should have PENDING as server default.

        SQLAlchemy 2.x `default=` on mapped_column applies at flush time,
        not at Python object construction.
        """
        col = EvidenceItem.__table__.columns["validation_status"]
        assert col.default is not None
        assert col.default.arg == ValidationStatus.PENDING

    def test_explicit_validation_status(self) -> None:
        """Evidence items created with explicit status should retain it."""
        item = EvidenceItem(
            name="test.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            engagement_id=uuid.uuid4(),
            validation_status=ValidationStatus.VALIDATED,
        )
        assert item.validation_status == ValidationStatus.VALIDATED

    def test_all_evidence_categories(self) -> None:
        """All 12 evidence categories should be defined."""
        categories = list(EvidenceCategory)
        assert len(categories) == 12
        assert EvidenceCategory.DOCUMENTS in categories
        assert EvidenceCategory.JOB_AIDS_EDGE_CASES in categories


class TestEvidenceFragment:
    """Test suite for the EvidenceFragment model."""

    def test_fragment_types(self) -> None:
        """All expected fragment types should be defined."""
        types = list(FragmentType)
        assert FragmentType.TEXT in types
        assert FragmentType.PROCESS_ELEMENT in types
        assert len(types) == 6

    def test_repr(self) -> None:
        """Fragment repr should include id and type."""
        frag = EvidenceFragment(
            id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            fragment_type=FragmentType.TEXT,
            content="sample",
        )
        assert "TEXT" in repr(frag) or "text" in repr(frag)

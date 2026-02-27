"""Tests for SeedTerm model and schemas (Story #302).

Covers all 5 BDD scenarios plus enum, model structure, and edge case tests.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.api.schemas.seed_term import SeedTermCreate, SeedTermMergeRequest, SeedTermRead
from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestTermCategory:
    """TermCategory enum completeness per PRD Section 6.10.3."""

    def test_all_five_categories_present(self) -> None:
        assert len(list(TermCategory)) == 5

    def test_category_values(self) -> None:
        expected = {"activity", "system", "role", "regulation", "artifact"}
        assert {c.value for c in TermCategory} == expected


class TestTermSource:
    """TermSource enum — three-way distinction."""

    def test_all_three_sources_present(self) -> None:
        assert len(list(TermSource)) == 3

    def test_source_values(self) -> None:
        expected = {"consultant_provided", "nlp_discovered", "evidence_extracted"}
        assert {s.value for s in TermSource} == expected


class TestTermStatus:
    """TermStatus lifecycle states."""

    def test_all_three_statuses_present(self) -> None:
        assert len(list(TermStatus)) == 3

    def test_status_values(self) -> None:
        expected = {"active", "deprecated", "merged"}
        assert {s.value for s in TermStatus} == expected


# ---------------------------------------------------------------------------
# SQLAlchemy Model Tests
# ---------------------------------------------------------------------------


class TestSeedTermModel:
    """SQLAlchemy model structure tests."""

    def test_table_name(self) -> None:
        assert SeedTerm.__tablename__ == "seed_terms"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in SeedTerm.__table__.columns}
        expected = {
            "id",
            "engagement_id",
            "term",
            "domain",
            "category",
            "source",
            "status",
            "merged_into",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_unique_constraint_exists(self) -> None:
        constraint_names = {c.name for c in SeedTerm.__table__.constraints if hasattr(c, "name") and c.name}
        assert "uq_seed_terms_engagement_term_domain" in constraint_names

    def test_engagement_id_indexed(self) -> None:
        index_names = {idx.name for idx in SeedTerm.__table__.indexes}
        assert "ix_seed_terms_engagement_id" in index_names

    def test_engagement_status_composite_index(self) -> None:
        index_names = {idx.name for idx in SeedTerm.__table__.indexes}
        assert "ix_seed_terms_engagement_status" in index_names

    def test_merged_into_indexed(self) -> None:
        index_names = {idx.name for idx in SeedTerm.__table__.indexes}
        assert "ix_seed_terms_merged_into" in index_names

    def test_fts_index_exists(self) -> None:
        index_names = {idx.name for idx in SeedTerm.__table__.indexes}
        assert "ix_seed_terms_term_fts" in index_names

    def test_engagement_fk(self) -> None:
        col = SeedTerm.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"

    def test_merged_into_self_fk(self) -> None:
        col = SeedTerm.__table__.columns["merged_into"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "seed_terms.id"

    def test_status_default(self) -> None:
        col = SeedTerm.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == TermStatus.ACTIVE

    def test_repr(self) -> None:
        obj = SeedTerm(
            id=uuid.uuid4(),
            term="KYC Review",
            category=TermCategory.ACTIVITY,
            status=TermStatus.ACTIVE,
        )
        r = repr(obj)
        assert "SeedTerm" in r
        assert "KYC Review" in r
        assert "activity" in r
        assert "active" in r


# ---------------------------------------------------------------------------
# BDD Scenario 1: Consultant-provided seed term
# ---------------------------------------------------------------------------


class TestBDDScenario1ConsultantProvided:
    """Scenario 1: Consultant-provided SeedTerm created successfully."""

    def test_consultant_seed_term_fields(self) -> None:
        eng_id = uuid.uuid4()
        term = SeedTerm(
            id=uuid.uuid4(),
            engagement_id=eng_id,
            term="KYC Review",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.CONSULTANT_PROVIDED,
            status=TermStatus.ACTIVE,
        )
        assert term.engagement_id == eng_id
        assert term.term == "KYC Review"
        assert term.domain == "loan_origination"
        assert term.category == TermCategory.ACTIVITY
        assert term.source == TermSource.CONSULTANT_PROVIDED
        assert term.status == TermStatus.ACTIVE

    def test_create_schema_accepts_valid_consultant_term(self) -> None:
        payload = SeedTermCreate(
            engagement_id=uuid.uuid4(),
            term="KYC Review",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.CONSULTANT_PROVIDED,
        )
        assert payload.source == TermSource.CONSULTANT_PROVIDED
        assert payload.category == TermCategory.ACTIVITY


# ---------------------------------------------------------------------------
# BDD Scenario 2: NLP-discovered seed term
# ---------------------------------------------------------------------------


class TestBDDScenario2NLPDiscovered:
    """Scenario 2: NLP-discovered SeedTerm assigned correct source."""

    def test_nlp_discovered_source(self) -> None:
        term = SeedTerm(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            term="AML Check",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.NLP_DISCOVERED,
            status=TermStatus.ACTIVE,
        )
        assert term.source == TermSource.NLP_DISCOVERED
        assert term.status == TermStatus.ACTIVE

    def test_create_schema_accepts_nlp_source(self) -> None:
        payload = SeedTermCreate(
            engagement_id=uuid.uuid4(),
            term="AML Check",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.NLP_DISCOVERED,
        )
        assert payload.source == TermSource.NLP_DISCOVERED


# ---------------------------------------------------------------------------
# BDD Scenario 3: Seed term merge
# ---------------------------------------------------------------------------


class TestBDDScenario3Merge:
    """Scenario 3: Deprecated term points to surviving term."""

    def test_merged_term_state(self) -> None:
        canonical_id = uuid.uuid4()
        deprecated = SeedTerm(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            term="Know Your Customer",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.CONSULTANT_PROVIDED,
            status=TermStatus.MERGED,
            merged_into=canonical_id,
        )
        assert deprecated.status == TermStatus.MERGED
        assert deprecated.merged_into == canonical_id

    def test_canonical_term_remains_active(self) -> None:
        canonical = SeedTerm(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            term="KYC",
            domain="loan_origination",
            category=TermCategory.ACTIVITY,
            source=TermSource.CONSULTANT_PROVIDED,
            status=TermStatus.ACTIVE,
            merged_into=None,
        )
        assert canonical.status == TermStatus.ACTIVE
        assert canonical.merged_into is None

    def test_merge_request_schema(self) -> None:
        deprecated_id = uuid.uuid4()
        canonical_id = uuid.uuid4()
        req = SeedTermMergeRequest(
            deprecated_term_id=deprecated_id,
            canonical_term_id=canonical_id,
        )
        assert req.deprecated_term_id == deprecated_id
        assert req.canonical_term_id == canonical_id

    def test_self_referential_fk_allows_set_null(self) -> None:
        col = SeedTerm.__table__.columns["merged_into"]
        fks = list(col.foreign_keys)
        assert fks[0].ondelete == "SET NULL"


# ---------------------------------------------------------------------------
# BDD Scenario 4: Engagement-scoped listing
# ---------------------------------------------------------------------------


class TestBDDScenario4EngagementScoped:
    """Scenario 4: SeedTerms scoped to engagement."""

    def test_engagement_id_not_nullable(self) -> None:
        col = SeedTerm.__table__.columns["engagement_id"]
        assert col.nullable is False

    def test_engagement_id_has_cascade_delete(self) -> None:
        col = SeedTerm.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert fks[0].ondelete == "CASCADE"

    def test_engagement_index_for_scoped_queries(self) -> None:
        index_names = {idx.name for idx in SeedTerm.__table__.indexes}
        assert "ix_seed_terms_engagement_id" in index_names

    def test_all_categories_assignable(self) -> None:
        for cat in TermCategory:
            term = SeedTerm(
                id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                term=f"test_{cat.value}",
                domain="test",
                category=cat,
                source=TermSource.CONSULTANT_PROVIDED,
            )
            assert term.category == cat


# ---------------------------------------------------------------------------
# BDD Scenario 5: Duplicate term rejected
# ---------------------------------------------------------------------------


class TestBDDScenario5UniqueConstraint:
    """Scenario 5: Duplicate term rejected via unique constraint."""

    def test_unique_constraint_columns(self) -> None:
        """Verify the unique constraint covers (engagement_id, term, domain)."""
        for constraint in SeedTerm.__table__.constraints:
            if hasattr(constraint, "name") and constraint.name == "uq_seed_terms_engagement_term_domain":
                col_names = {c.name for c in constraint.columns}
                assert col_names == {"engagement_id", "term", "domain"}
                return
        pytest.fail("Unique constraint uq_seed_terms_engagement_term_domain not found")


# ---------------------------------------------------------------------------
# Edge Case / Validation Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional validation edge cases."""

    def test_term_min_length(self) -> None:
        with pytest.raises(ValidationError):
            SeedTermCreate(
                engagement_id=uuid.uuid4(),
                term="",
                domain="loan_origination",
                category=TermCategory.ACTIVITY,
                source=TermSource.CONSULTANT_PROVIDED,
            )

    def test_term_max_length(self) -> None:
        with pytest.raises(ValidationError):
            SeedTermCreate(
                engagement_id=uuid.uuid4(),
                term="x" * 501,
                domain="loan_origination",
                category=TermCategory.ACTIVITY,
                source=TermSource.CONSULTANT_PROVIDED,
            )

    def test_domain_min_length(self) -> None:
        with pytest.raises(ValidationError):
            SeedTermCreate(
                engagement_id=uuid.uuid4(),
                term="KYC",
                domain="",
                category=TermCategory.ACTIVITY,
                source=TermSource.CONSULTANT_PROVIDED,
            )

    def test_domain_max_length(self) -> None:
        with pytest.raises(ValidationError):
            SeedTermCreate(
                engagement_id=uuid.uuid4(),
                term="KYC",
                domain="x" * 201,
                category=TermCategory.ACTIVITY,
                source=TermSource.CONSULTANT_PROVIDED,
            )

    def test_merged_into_nullable(self) -> None:
        col = SeedTerm.__table__.columns["merged_into"]
        assert col.nullable is True

    def test_term_not_nullable(self) -> None:
        col = SeedTerm.__table__.columns["term"]
        assert col.nullable is False

    def test_domain_not_nullable(self) -> None:
        col = SeedTerm.__table__.columns["domain"]
        assert col.nullable is False

    def test_evidence_extracted_source(self) -> None:
        payload = SeedTermCreate(
            engagement_id=uuid.uuid4(),
            term="Credit Score Check",
            domain="loan_origination",
            category=TermCategory.SYSTEM,
            source=TermSource.EVIDENCE_EXTRACTED,
        )
        assert payload.source == TermSource.EVIDENCE_EXTRACTED

    def test_deprecated_status(self) -> None:
        term = SeedTerm(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            term="Old Term",
            domain="test",
            category=TermCategory.ARTIFACT,
            source=TermSource.CONSULTANT_PROVIDED,
            status=TermStatus.DEPRECATED,
        )
        assert term.status == TermStatus.DEPRECATED

    def test_read_schema_serialization(self) -> None:
        read = SeedTermRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            term="KYC Review",
            domain="loan_origination",
            category="activity",
            source="consultant_provided",
            status="active",
            created_at="2026-02-27T12:00:00Z",
        )
        assert read.term == "KYC Review"
        assert read.status == "active"

    def test_read_schema_with_merged_into(self) -> None:
        read = SeedTermRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            term="Know Your Customer",
            domain="loan_origination",
            category="activity",
            source="consultant_provided",
            status="merged",
            merged_into=str(uuid.uuid4()),
            created_at="2026-02-27T12:00:00Z",
        )
        assert read.status == "merged"
        assert read.merged_into is not None

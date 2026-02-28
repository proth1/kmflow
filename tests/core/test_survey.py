"""Tests for SurveyClaim and EpistemicFrame models and schemas.

Covers all 5 BDD acceptance criteria from Story #297.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.api.schemas.survey import (
    EpistemicFrameCreate,
    EpistemicFrameRead,
    SurveyClaimCreate,
    SurveyClaimRead,
)
from src.core.models.survey import (
    AUTHORITY_SCOPE_VOCABULARY,
    CertaintyTier,
    EpistemicFrame,
    FrameKind,
    ProbeType,
    SurveyClaim,
)

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestCertaintyTier:
    """CertaintyTier enum completeness."""

    def test_all_tiers_present(self) -> None:
        tiers = list(CertaintyTier)
        assert len(tiers) == 4
        assert CertaintyTier.KNOWN in tiers
        assert CertaintyTier.SUSPECTED in tiers
        assert CertaintyTier.UNKNOWN in tiers
        assert CertaintyTier.CONTRADICTED in tiers

    def test_str_values(self) -> None:
        assert CertaintyTier.KNOWN == "known"
        assert CertaintyTier.CONTRADICTED == "contradicted"


class TestProbeType:
    """ProbeType enum completeness per PRD Section 6.10.2."""

    def test_all_probe_types_present(self) -> None:
        probes = list(ProbeType)
        assert len(probes) == 8

    def test_probe_type_values(self) -> None:
        expected = {
            "existence",
            "sequence",
            "dependency",
            "input_output",
            "governance",
            "performer",
            "exception",
            "uncertainty",
        }
        assert {p.value for p in ProbeType} == expected


class TestFrameKind:
    """FrameKind enum completeness."""

    def test_all_frame_kinds_present(self) -> None:
        kinds = list(FrameKind)
        assert len(kinds) == 6

    def test_frame_kind_values(self) -> None:
        expected = {
            "procedural",
            "regulatory",
            "experiential",
            "telemetric",
            "elicited",
            "behavioral",
        }
        assert {k.value for k in FrameKind} == expected


class TestAuthorityVocabulary:
    """Controlled vocabulary for authority_scope."""

    def test_vocabulary_is_frozenset(self) -> None:
        assert isinstance(AUTHORITY_SCOPE_VOCABULARY, frozenset)

    def test_vocabulary_has_expected_roles(self) -> None:
        assert len(AUTHORITY_SCOPE_VOCABULARY) == 12
        assert "operations_team" in AUTHORITY_SCOPE_VOCABULARY
        assert "compliance_officer" in AUTHORITY_SCOPE_VOCABULARY
        assert "process_owner" in AUTHORITY_SCOPE_VOCABULARY
        assert "system_administrator" in AUTHORITY_SCOPE_VOCABULARY
        assert "business_analyst" in AUTHORITY_SCOPE_VOCABULARY
        assert "risk_manager" in AUTHORITY_SCOPE_VOCABULARY
        assert "quality_assurance" in AUTHORITY_SCOPE_VOCABULARY
        assert "external_auditor" in AUTHORITY_SCOPE_VOCABULARY
        assert "system_telemetry" in AUTHORITY_SCOPE_VOCABULARY
        assert "task_mining_agent" in AUTHORITY_SCOPE_VOCABULARY
        assert "survey_respondent" in AUTHORITY_SCOPE_VOCABULARY
        assert "subject_matter_expert" in AUTHORITY_SCOPE_VOCABULARY


# ---------------------------------------------------------------------------
# SQLAlchemy Model Tests
# ---------------------------------------------------------------------------


class TestSurveyClaimModel:
    """SQLAlchemy model tests for SurveyClaim."""

    def test_table_name(self) -> None:
        assert SurveyClaim.__tablename__ == "survey_claims"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in SurveyClaim.__table__.columns}
        expected = {
            "id",
            "engagement_id",
            "session_id",
            "probe_type",
            "respondent_role",
            "claim_text",
            "certainty_tier",
            "proof_expectation",
            "related_seed_terms",
            "metadata_json",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_indexes_defined(self) -> None:
        index_names = {idx.name for idx in SurveyClaim.__table__.indexes}
        assert "ix_survey_claims_engagement_id" in index_names
        assert "ix_survey_claims_session_id" in index_names

    def test_engagement_fk(self) -> None:
        col = SurveyClaim.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"

    def test_repr(self) -> None:
        claim = SurveyClaim(
            id=uuid.uuid4(),
            certainty_tier=CertaintyTier.KNOWN,
            probe_type=ProbeType.UNCERTAINTY,
        )
        r = repr(claim)
        assert "SurveyClaim" in r
        assert "known" in r
        assert "uncertainty" in r


class TestEpistemicFrameModel:
    """SQLAlchemy model tests for EpistemicFrame."""

    def test_table_name(self) -> None:
        assert EpistemicFrame.__tablename__ == "epistemic_frames"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in EpistemicFrame.__table__.columns}
        expected = {
            "id",
            "claim_id",
            "engagement_id",
            "frame_kind",
            "authority_scope",
            "access_policy",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_claim_id_unique(self) -> None:
        col = EpistemicFrame.__table__.columns["claim_id"]
        assert col.unique is True

    def test_claim_id_fk(self) -> None:
        col = EpistemicFrame.__table__.columns["claim_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "survey_claims.id"

    def test_engagement_id_fk(self) -> None:
        col = EpistemicFrame.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"
        assert col.nullable is False

    def test_indexes_defined(self) -> None:
        index_names = {idx.name for idx in EpistemicFrame.__table__.indexes}
        assert "ix_epistemic_frames_claim_id" in index_names
        assert "ix_epistemic_frames_engagement_id" in index_names

    def test_repr(self) -> None:
        frame = EpistemicFrame(
            id=uuid.uuid4(),
            frame_kind=FrameKind.EXPERIENTIAL,
            authority_scope="compliance_officer",
        )
        r = repr(frame)
        assert "EpistemicFrame" in r
        assert "experiential" in r
        assert "compliance_officer" in r


class TestRelationships:
    """Test ORM relationship configuration."""

    def test_survey_claim_has_epistemic_frame_relationship(self) -> None:
        rels = SurveyClaim.__mapper__.relationships
        assert "epistemic_frame" in rels
        rel = rels["epistemic_frame"]
        assert rel.uselist is False  # one-to-one

    def test_epistemic_frame_has_survey_claim_relationship(self) -> None:
        rels = EpistemicFrame.__mapper__.relationships
        assert "survey_claim" in rels


# ---------------------------------------------------------------------------
# BDD Scenario 1: SurveyClaim created with KNOWN certainty tier
# ---------------------------------------------------------------------------


class TestBDDScenario1ClaimCreation:
    """Scenario 1: SurveyClaim created with all required fields."""

    def test_claim_fields_set_correctly(self) -> None:
        eng_id = uuid.uuid4()
        sess_id = uuid.uuid4()

        claim = SurveyClaim(
            id=uuid.uuid4(),
            engagement_id=eng_id,
            session_id=sess_id,
            probe_type=ProbeType.UNCERTAINTY,
            respondent_role="compliance_officer",
            claim_text="KYC Review always precedes AML Check",
            certainty_tier=CertaintyTier.KNOWN,
            proof_expectation="audit log from 2025 Q4",
        )

        assert claim.engagement_id == eng_id
        assert claim.session_id == sess_id
        assert claim.probe_type == ProbeType.UNCERTAINTY
        assert claim.respondent_role == "compliance_officer"
        assert claim.claim_text == "KYC Review always precedes AML Check"
        assert claim.certainty_tier == CertaintyTier.KNOWN
        assert claim.proof_expectation == "audit log from 2025 Q4"

    def test_pydantic_create_schema_accepts_valid_claim(self) -> None:
        payload = SurveyClaimCreate(
            engagement_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            probe_type=ProbeType.UNCERTAINTY,
            respondent_role="compliance_officer",
            claim_text="KYC Review always precedes AML Check",
            certainty_tier=CertaintyTier.KNOWN,
            proof_expectation="audit log from 2025 Q4",
            related_seed_terms=["KYC", "AML"],
        )

        assert payload.certainty_tier == CertaintyTier.KNOWN
        assert payload.related_seed_terms == ["KYC", "AML"]

    def test_pydantic_create_with_nested_epistemic_frame(self) -> None:
        payload = SurveyClaimCreate(
            engagement_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            probe_type=ProbeType.EXISTENCE,
            respondent_role="process_owner",
            claim_text="Invoice approval step exists",
            certainty_tier=CertaintyTier.SUSPECTED,
            epistemic_frame=EpistemicFrameCreate(
                frame_kind=FrameKind.EXPERIENTIAL,
                authority_scope="process_owner",
            ),
        )

        assert payload.epistemic_frame is not None
        assert payload.epistemic_frame.frame_kind == FrameKind.EXPERIENTIAL
        assert payload.epistemic_frame.authority_scope == "process_owner"


# ---------------------------------------------------------------------------
# BDD Scenario 2: authority_scope validation
# ---------------------------------------------------------------------------


class TestBDDScenario2AuthorityScopeValidation:
    """Scenario 2: EpistemicFrame authority_scope must be from controlled vocabulary."""

    def test_valid_authority_scope_accepted(self) -> None:
        for scope in AUTHORITY_SCOPE_VOCABULARY:
            frame = EpistemicFrameCreate(
                frame_kind=FrameKind.PROCEDURAL,
                authority_scope=scope,
            )
            assert frame.authority_scope == scope

    def test_invalid_authority_scope_rejected(self) -> None:
        with pytest.raises(ValidationError, match="controlled engagement role vocabulary"):
            EpistemicFrameCreate(
                frame_kind=FrameKind.EXPERIENTIAL,
                authority_scope="freeform text not in vocabulary",
            )

    def test_empty_authority_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpistemicFrameCreate(
                frame_kind=FrameKind.PROCEDURAL,
                authority_scope="",
            )

    def test_nested_frame_invalid_scope_rejects_entire_claim(self) -> None:
        with pytest.raises(ValidationError, match="controlled engagement role vocabulary"):
            SurveyClaimCreate(
                engagement_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                probe_type=ProbeType.GOVERNANCE,
                respondent_role="analyst",
                claim_text="Policy XYZ applies",
                certainty_tier=CertaintyTier.KNOWN,
                epistemic_frame=EpistemicFrameCreate(
                    frame_kind=FrameKind.REGULATORY,
                    authority_scope="random_role_not_in_vocab",
                ),
            )


# ---------------------------------------------------------------------------
# BDD Scenario 3: Elicited frame_kind for survey-originated claims
# ---------------------------------------------------------------------------


class TestBDDScenario3ElicitedFrameKind:
    """Scenario 3: Elicited frame_kind auto-assigned for survey-originated claims.

    Note: Auto-assignment is a service-layer responsibility (not enforced at
    the schema/model level). Here we verify that the ELICITED frame_kind
    exists and can be used in the schema.
    """

    def test_elicited_frame_kind_exists(self) -> None:
        assert FrameKind.ELICITED == "elicited"

    def test_schema_accepts_elicited_frame(self) -> None:
        frame = EpistemicFrameCreate(
            frame_kind=FrameKind.ELICITED,
            authority_scope="survey_respondent",
        )
        assert frame.frame_kind == FrameKind.ELICITED

    def test_model_accepts_elicited_frame(self) -> None:
        frame = EpistemicFrame(
            id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            frame_kind=FrameKind.ELICITED,
            authority_scope="survey_respondent",
        )
        assert frame.frame_kind == FrameKind.ELICITED


# ---------------------------------------------------------------------------
# BDD Scenario 4: CONTRADICTED certainty tier
# ---------------------------------------------------------------------------


class TestBDDScenario4ContradictedTier:
    """Scenario 4: CONTRADICTED certainty tier triggers ConflictObject creation.

    Note: ConflictObject creation is a service-layer responsibility, not
    enforced at the model/schema level. Here we verify the schema and model
    accept CONTRADICTED claims correctly.
    """

    def test_contradicted_tier_accepted_in_schema(self) -> None:
        payload = SurveyClaimCreate(
            engagement_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            probe_type=ProbeType.SEQUENCE,
            respondent_role="operations_team",
            claim_text="AML Check precedes KYC Review",
            certainty_tier=CertaintyTier.CONTRADICTED,
        )
        assert payload.certainty_tier == CertaintyTier.CONTRADICTED

    def test_contradicted_tier_accepted_in_model(self) -> None:
        claim = SurveyClaim(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            probe_type=ProbeType.SEQUENCE,
            respondent_role="operations_team",
            claim_text="AML Check precedes KYC Review",
            certainty_tier=CertaintyTier.CONTRADICTED,
        )
        assert claim.certainty_tier == CertaintyTier.CONTRADICTED


# ---------------------------------------------------------------------------
# BDD Scenario 5: Engagement-scoped retrieval
# ---------------------------------------------------------------------------


class TestBDDScenario5EngagementScoping:
    """Scenario 5: SurveyClaim retrieval is scoped to engagement.

    Note: Scoping is enforced at the query/service layer, not the model.
    Here we verify the engagement_id column is non-nullable and FK-linked,
    and that two claims with different engagement_ids are distinct.
    """

    def test_engagement_id_not_nullable(self) -> None:
        col = SurveyClaim.__table__.columns["engagement_id"]
        assert col.nullable is False

    def test_engagement_id_indexed(self) -> None:
        index_names = {idx.name for idx in SurveyClaim.__table__.indexes}
        assert "ix_survey_claims_engagement_id" in index_names

    def test_claims_carry_distinct_engagement_ids(self) -> None:
        eng1 = uuid.uuid4()
        eng2 = uuid.uuid4()

        c1 = SurveyClaim(
            id=uuid.uuid4(),
            engagement_id=eng1,
            session_id=uuid.uuid4(),
            probe_type=ProbeType.EXISTENCE,
            respondent_role="analyst",
            claim_text="Step A exists",
            certainty_tier=CertaintyTier.KNOWN,
        )
        c2 = SurveyClaim(
            id=uuid.uuid4(),
            engagement_id=eng2,
            session_id=uuid.uuid4(),
            probe_type=ProbeType.EXISTENCE,
            respondent_role="analyst",
            claim_text="Step B exists",
            certainty_tier=CertaintyTier.KNOWN,
        )

        assert c1.engagement_id == eng1
        assert c2.engagement_id == eng2
        assert c1.engagement_id != c2.engagement_id


# ---------------------------------------------------------------------------
# Pydantic Read Schema Tests
# ---------------------------------------------------------------------------


class TestReadSchemas:
    """Test Pydantic read schemas for serialization."""

    def test_survey_claim_read_schema(self) -> None:
        claim_id = str(uuid.uuid4())
        eng_id = str(uuid.uuid4())
        sess_id = str(uuid.uuid4())

        read = SurveyClaimRead(
            id=claim_id,
            engagement_id=eng_id,
            session_id=sess_id,
            probe_type="uncertainty",
            respondent_role="compliance_officer",
            claim_text="KYC always precedes AML",
            certainty_tier="known",
            proof_expectation="audit log",
            related_seed_terms=["KYC", "AML"],
            created_at="2026-02-27T12:00:00Z",
        )

        assert read.id == claim_id
        assert read.certainty_tier == "known"
        assert read.related_seed_terms == ["KYC", "AML"]

    def test_survey_claim_read_with_frame(self) -> None:
        frame_read = EpistemicFrameRead(
            id=str(uuid.uuid4()),
            claim_id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            frame_kind="experiential",
            authority_scope="compliance_officer",
            created_at="2026-02-27T12:00:00Z",
        )
        claim_read = SurveyClaimRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            probe_type="existence",
            respondent_role="process_owner",
            claim_text="Step exists",
            certainty_tier="suspected",
            epistemic_frame=frame_read,
            created_at="2026-02-27T12:00:00Z",
        )

        assert claim_read.epistemic_frame is not None
        assert claim_read.epistemic_frame.frame_kind == "experiential"

    def test_survey_claim_read_without_frame(self) -> None:
        read = SurveyClaimRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            probe_type="sequence",
            respondent_role="analyst",
            claim_text="A then B",
            certainty_tier="unknown",
            created_at="2026-02-27T12:00:00Z",
        )

        assert read.epistemic_frame is None

    def test_epistemic_frame_read_schema(self) -> None:
        read = EpistemicFrameRead(
            id=str(uuid.uuid4()),
            claim_id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            frame_kind="procedural",
            authority_scope="operations_team",
            access_policy="internal_only",
            created_at="2026-02-27T12:00:00Z",
        )

        assert read.frame_kind == "procedural"
        assert read.access_policy == "internal_only"


# ---------------------------------------------------------------------------
# Edge Case / Validation Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional validation edge cases."""

    def test_claim_text_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            SurveyClaimCreate(
                engagement_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                probe_type=ProbeType.EXISTENCE,
                respondent_role="analyst",
                claim_text="",
                certainty_tier=CertaintyTier.KNOWN,
            )

    def test_respondent_role_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            SurveyClaimCreate(
                engagement_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                probe_type=ProbeType.EXISTENCE,
                respondent_role="",
                claim_text="Step exists",
                certainty_tier=CertaintyTier.KNOWN,
            )

    def test_optional_fields_default_to_none(self) -> None:
        payload = SurveyClaimCreate(
            engagement_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            probe_type=ProbeType.PERFORMER,
            respondent_role="analyst",
            claim_text="Role X performs step Y",
            certainty_tier=CertaintyTier.SUSPECTED,
        )

        assert payload.proof_expectation is None
        assert payload.related_seed_terms is None
        assert payload.epistemic_frame is None

    def test_access_policy_optional_on_frame(self) -> None:
        frame = EpistemicFrameCreate(
            frame_kind=FrameKind.TELEMETRIC,
            authority_scope="system_telemetry",
        )
        assert frame.access_policy is None

    def test_access_policy_accepts_string(self) -> None:
        frame = EpistemicFrameCreate(
            frame_kind=FrameKind.REGULATORY,
            authority_scope="external_auditor",
            access_policy="restricted_to_engagement_members",
        )
        assert frame.access_policy == "restricted_to_engagement_members"

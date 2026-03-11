"""Tests for ontology derivation engine (KMFLOW-6)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.ontology import OntologyVersion
from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus
from src.semantic.ontology_derivation import (
    OntologyDerivationService,
    OntologyValidationService,
)


def _make_seed_term(
    engagement_id: uuid.UUID,
    term: str,
    category: TermCategory = TermCategory.ACTIVITY,
    domain: str = "general",
) -> SeedTerm:
    """Create a mock SeedTerm."""
    t = MagicMock(spec=SeedTerm)
    t.id = uuid.uuid4()
    t.engagement_id = engagement_id
    t.term = term
    t.category = category
    t.domain = domain
    t.source = TermSource.CONSULTANT_PROVIDED
    t.status = TermStatus.ACTIVE
    return t


class TestComputeCompleteness:
    """Test completeness score computation."""

    def test_empty_seed_terms_returns_zero(self) -> None:
        service = OntologyDerivationService.__new__(OntologyDerivationService)
        score = service._compute_completeness([], {}, [])
        assert score == 0.0

    def test_full_coverage_with_connected_classes(self) -> None:
        service = OntologyDerivationService.__new__(OntologyDerivationService)
        eng_id = uuid.uuid4()
        terms = [
            _make_seed_term(eng_id, "t1", TermCategory.ACTIVITY),
            _make_seed_term(eng_id, "t2", TermCategory.SYSTEM),
        ]

        cls1 = MagicMock()
        cls1.id = uuid.uuid4()
        cls2 = MagicMock()
        cls2.id = uuid.uuid4()

        classes = {"activity": cls1, "system": cls2}

        prop = MagicMock()
        prop.domain_class_id = cls1.id
        prop.range_class_id = cls2.id

        score = service._compute_completeness(terms, classes, [prop])
        # category_score = 1.0 (2/2), term_score = 1.0, property_score = 1.0 (2/2 connected)
        assert score == 1.0

    def test_partial_category_coverage(self) -> None:
        service = OntologyDerivationService.__new__(OntologyDerivationService)
        eng_id = uuid.uuid4()
        terms = [
            _make_seed_term(eng_id, "t1", TermCategory.ACTIVITY),
            _make_seed_term(eng_id, "t2", TermCategory.SYSTEM),
            _make_seed_term(eng_id, "t3", TermCategory.ROLE),
        ]

        cls1 = MagicMock()
        cls1.id = uuid.uuid4()

        classes = {"activity": cls1}  # Only 1 of 3 categories

        score = service._compute_completeness(terms, classes, [])
        # category_score = 1/3 ~= 0.333, term_score = 1.0, property_score = 0.0
        assert 0.0 < score < 0.5

    def test_no_classes_from_terms(self) -> None:
        service = OntologyDerivationService.__new__(OntologyDerivationService)
        eng_id = uuid.uuid4()
        terms = [_make_seed_term(eng_id, "t1")]

        score = service._compute_completeness(terms, {}, [])
        # category_score = 0.0, term_score = 0.0, property_score = 0.0
        assert score == 0.0


class TestCreateClasses:
    """Test class creation from seed terms."""

    @pytest.mark.asyncio
    async def test_groups_by_category(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        eng_id = uuid.uuid4()
        ontology_id = uuid.uuid4()
        terms = [
            _make_seed_term(eng_id, "Review Application", TermCategory.ACTIVITY),
            _make_seed_term(eng_id, "Approve Loan", TermCategory.ACTIVITY),
            _make_seed_term(eng_id, "SAP", TermCategory.SYSTEM),
        ]

        classes = await service._create_classes(ontology_id, terms)

        assert len(classes) == 2
        assert "activity" in classes
        assert "system" in classes
        assert classes["activity"].instance_count == 2
        assert classes["system"].instance_count == 1

    @pytest.mark.asyncio
    async def test_confidence_scales_with_count(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        eng_id = uuid.uuid4()
        terms = [_make_seed_term(eng_id, f"t{i}", TermCategory.ACTIVITY) for i in range(15)]

        classes = await service._create_classes(uuid.uuid4(), terms)

        # 15 terms → confidence should be capped at 1.0 (min(1.0, 15/10))
        assert classes["activity"].confidence == 1.0

    @pytest.mark.asyncio
    async def test_empty_terms_produces_no_classes(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        classes = await service._create_classes(uuid.uuid4(), [])
        assert len(classes) == 0


class TestExtractRelationshipPatterns:
    """Test Neo4j relationship pattern extraction."""

    @pytest.mark.asyncio
    async def test_extracts_patterns(self) -> None:
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(
            return_value=[
                {"source_label": "Activity", "rel_type": "PERFORMED_BY", "target_label": "Role", "cnt": 10},
                {"source_label": "Activity", "rel_type": "PRECEDES", "target_label": "Activity", "cnt": 5},
            ]
        )

        mock_neo_session = AsyncMock()
        mock_neo_session.run = AsyncMock(return_value=mock_result)

        mock_driver = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_neo_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session.return_value = mock_session_ctx

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.neo4j_driver = mock_driver

        patterns = await service._extract_relationship_patterns(uuid.uuid4())

        assert len(patterns) == 2
        assert patterns[0]["relationship_type"] == "PERFORMED_BY"
        assert patterns[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_handles_neo4j_error(self) -> None:
        mock_driver = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(side_effect=ConnectionError("down"))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session.return_value = mock_session_ctx

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.neo4j_driver = mock_driver

        patterns = await service._extract_relationship_patterns(uuid.uuid4())
        assert patterns == []


class TestCreateProperties:
    """Test property creation from relationship patterns."""

    @pytest.mark.asyncio
    async def test_creates_properties_from_valid_patterns(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        cls_activity = MagicMock()
        cls_activity.id = uuid.uuid4()
        cls_role = MagicMock()
        cls_role.id = uuid.uuid4()

        classes = {"activity": cls_activity, "role": cls_role}

        patterns = [
            {"source_label": "Activity", "relationship_type": "PERFORMED_BY", "target_label": "Role", "count": 10},
        ]

        properties = await service._create_properties(uuid.uuid4(), patterns, classes)

        assert len(properties) == 1
        assert properties[0].source_edge_type == "PERFORMED_BY"
        assert properties[0].usage_count == 10

    @pytest.mark.asyncio
    async def test_skips_invalid_relationship_types(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        patterns = [
            {"source_label": "Foo", "relationship_type": "NOT_A_REAL_TYPE", "target_label": "Bar", "count": 5},
        ]

        properties = await service._create_properties(uuid.uuid4(), patterns, {})
        assert len(properties) == 0


class TestGenerateAxioms:
    """Test axiom generation from patterns."""

    @pytest.mark.asyncio
    async def test_generates_existential_axiom(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        patterns = [
            {"source_label": "Activity", "relationship_type": "PERFORMED_BY", "target_label": "Role", "count": 20},
        ]

        axioms = await service._generate_axioms(uuid.uuid4(), patterns, {})

        # Should generate at least an existential axiom (count=20 >> threshold)
        existential = [a for a in axioms if a.axiom_type == "existential"]
        assert len(existential) >= 1
        assert "Activity" in existential[0].expression

    @pytest.mark.asyncio
    async def test_generates_domain_range_for_exclusive(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        # Single target with 100% exclusivity
        patterns = [
            {"source_label": "Activity", "relationship_type": "PERFORMED_BY", "target_label": "Role", "count": 20},
        ]

        axioms = await service._generate_axioms(uuid.uuid4(), patterns, {})

        domain_range = [a for a in axioms if a.axiom_type == "domain_range"]
        assert len(domain_range) >= 1

    @pytest.mark.asyncio
    async def test_skips_low_frequency_patterns(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        service = OntologyDerivationService.__new__(OntologyDerivationService)
        service.session = session

        patterns = [
            {"source_label": "Activity", "relationship_type": "PERFORMED_BY", "target_label": "Role", "count": 1},
        ]

        axioms = await service._generate_axioms(uuid.uuid4(), patterns, {})
        assert len(axioms) == 0


class TestOntologyValidationService:
    """Test ontology validation."""

    @pytest.mark.asyncio
    async def test_identifies_orphan_classes(self) -> None:
        session = AsyncMock()

        ontology = MagicMock(spec=OntologyVersion)
        ontology.id = uuid.uuid4()
        ontology.completeness_score = 0.5
        session.get = AsyncMock(return_value=ontology)

        # Two classes, no properties → both are orphans
        cls1 = MagicMock()
        cls1.id = uuid.uuid4()
        cls1.name = "Activity"
        cls1.instance_count = 5
        cls1.confidence = 0.8

        cls2 = MagicMock()
        cls2.id = uuid.uuid4()
        cls2.name = "Role"
        cls2.instance_count = 3
        cls2.confidence = 0.7

        # Mock three separate execute calls
        classes_result = MagicMock()
        classes_result.scalars.return_value.all.return_value = [cls1, cls2]

        props_result = MagicMock()
        props_result.scalars.return_value.all.return_value = []

        axioms_result = MagicMock()
        axioms_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[classes_result, props_result, axioms_result])
        session.commit = AsyncMock()

        service = OntologyValidationService(session)
        report = await service.validate(ontology.id)

        assert len(report["orphan_classes"]) == 2
        assert any(o["name"] == "Activity" for o in report["orphan_classes"])

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        service = OntologyValidationService(session)
        report = await service.validate(uuid.uuid4())
        assert "error" in report

    @pytest.mark.asyncio
    async def test_generates_recommendations(self) -> None:
        session = AsyncMock()

        ontology = MagicMock(spec=OntologyVersion)
        ontology.id = uuid.uuid4()
        ontology.completeness_score = 0.3
        session.get = AsyncMock(return_value=ontology)

        cls1 = MagicMock()
        cls1.id = uuid.uuid4()
        cls1.name = "Activity"
        cls1.instance_count = 2
        cls1.confidence = 0.2  # Low confidence

        classes_result = MagicMock()
        classes_result.scalars.return_value.all.return_value = [cls1]
        props_result = MagicMock()
        props_result.scalars.return_value.all.return_value = []
        axioms_result = MagicMock()
        axioms_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[classes_result, props_result, axioms_result])
        session.commit = AsyncMock()

        service = OntologyValidationService(session)
        report = await service.validate(ontology.id)

        assert len(report["recommendations"]) > 0
        assert any("low confidence" in r for r in report["recommendations"])

"""BDD tests for claim write-back service (Story #324).

Tests the ClaimWriteBackService which ingests SurveyClaims into Neo4j,
creating SUPPORTS/CONTRADICTS edges, EpistemicFrame nodes, and
auto-creating ConflictObjects for contradicted claims.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.conflict import ConflictObject, MismatchType
from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.semantic.claim_write_back import CERTAINTY_WEIGHTS, ClaimWriteBackService

# ── Helpers ──────────────────────────────────────────────────────────


def _make_claim(
    *,
    certainty_tier: CertaintyTier = CertaintyTier.KNOWN,
    probe_type: ProbeType = ProbeType.EXISTENCE,
    engagement_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    epistemic_frame: MagicMock | None = None,
) -> MagicMock:
    """Create a mock SurveyClaim."""
    claim = MagicMock(spec=SurveyClaim)
    claim.id = uuid.uuid4()
    claim.engagement_id = engagement_id or uuid.uuid4()
    claim.session_id = session_id or uuid.uuid4()
    claim.claim_text = "Test claim text"
    claim.probe_type = probe_type
    claim.certainty_tier = certainty_tier
    claim.respondent_role = "process_owner"
    claim.epistemic_frame = epistemic_frame
    return claim


def _make_epistemic_frame() -> MagicMock:
    """Create a mock EpistemicFrame."""
    frame = MagicMock()
    frame.id = uuid.uuid4()
    frame.frame_kind = MagicMock(value="elicited")
    frame.authority_scope = "process_owner"
    return frame


# ── Scenario 1: SUPPORTS Edge Creation ──────────────────────────────


class TestSupportsEdgeCreation:
    """Scenario 1: SUPPORTS Edge Creation on Claim Ingest."""

    @pytest.mark.asyncio
    async def test_creates_claim_node_in_neo4j(self) -> None:
        """Given a KNOWN claim, a Claim node is created via MERGE."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        graph.run_query = AsyncMock(return_value=[])
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.KNOWN)

        await service.ingest_claim(claim, target_activity_id="act_001")

        # First call creates the Claim node
        first_call = graph.run_write_query.call_args_list[0]
        cypher = first_call[0][0]
        assert "MERGE (c:Claim" in cypher
        assert "claim_text" in cypher

    @pytest.mark.asyncio
    async def test_supports_edge_for_known_claim(self) -> None:
        """A KNOWN claim creates a SUPPORTS edge."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.KNOWN)

        result = await service.ingest_claim(claim, target_activity_id="act_001")

        assert result["edge_type"] == "SUPPORTS"

    @pytest.mark.asyncio
    async def test_supports_edge_for_suspected_claim(self) -> None:
        """A SUSPECTED claim also creates a SUPPORTS edge."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.SUSPECTED)

        result = await service.ingest_claim(claim, target_activity_id="act_001")

        assert result["edge_type"] == "SUPPORTS"

    @pytest.mark.asyncio
    async def test_edge_weight_from_certainty_tier(self) -> None:
        """Edge weight is derived from CERTAINTY_WEIGHTS mapping."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.KNOWN)

        result = await service.ingest_claim(claim, target_activity_id="act_001")

        assert result["weight"] == 1.0

    @pytest.mark.asyncio
    async def test_no_edge_without_target_activity(self) -> None:
        """Claim node created but no edge if target_activity_id is None."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim()

        result = await service.ingest_claim(claim, target_activity_id=None)

        assert result["edge_type"] is None
        assert result["conflict_id"] is None


# ── Scenario 2: CONTRADICTS Edge and ConflictObject ──────────────────


class TestContradictsEdgeCreation:
    """Scenario 2: CONTRADICTS Edge and ConflictObject Creation."""

    @pytest.mark.asyncio
    async def test_contradicts_edge_for_contradicted_claim(self) -> None:
        """A CONTRADICTED claim creates a CONTRADICTS edge."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()
        session.flush = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.CONTRADICTED)

        result = await service.ingest_claim(claim, target_activity_id="act_002")

        assert result["edge_type"] == "CONTRADICTS"

    @pytest.mark.asyncio
    async def test_conflict_object_created_for_contradicted(self) -> None:
        """ConflictObject is auto-created for contradicted claims."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.CONTRADICTED)

        result = await service.ingest_claim(claim, target_activity_id="act_002")

        assert result["conflict_id"] is not None
        # Verify session.add was called with ConflictObject
        add_calls = session.add.call_args_list
        conflict_added = any(isinstance(call[0][0], ConflictObject) for call in add_calls)
        assert conflict_added

    @pytest.mark.asyncio
    async def test_conflict_object_has_correct_severity(self) -> None:
        """ConflictObject severity is set to 0.7."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        claim = _make_claim(certainty_tier=CertaintyTier.CONTRADICTED)

        await service.ingest_claim(claim, target_activity_id="act_002")

        # Find the ConflictObject that was added
        for call in session.add.call_args_list:
            obj = call[0][0]
            if isinstance(obj, ConflictObject):
                assert obj.severity == 0.7
                assert obj.escalation_flag is True
                assert obj.mismatch_type == MismatchType.EXISTENCE_MISMATCH
                break

    @pytest.mark.asyncio
    async def test_no_conflict_for_non_contradicted(self) -> None:
        """No ConflictObject for KNOWN/SUSPECTED/UNKNOWN claims."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)

        for tier in [CertaintyTier.KNOWN, CertaintyTier.SUSPECTED, CertaintyTier.UNKNOWN]:
            claim = _make_claim(certainty_tier=tier)
            result = await service.ingest_claim(claim, target_activity_id="act_001")
            assert result["conflict_id"] is None


# ── Scenario 3: EpistemicFrame Node Creation ─────────────────────────


class TestEpistemicFrameCreation:
    """Scenario 3: EpistemicFrame Node Creation and Linkage."""

    @pytest.mark.asyncio
    async def test_creates_epistemic_frame_node(self) -> None:
        """EpistemicFrame node is created and linked via HAS_FRAME."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        frame = _make_epistemic_frame()
        claim = _make_claim(epistemic_frame=frame)

        service = ClaimWriteBackService(graph=graph, session=session)
        await service.ingest_claim(claim, target_activity_id=None)

        # Second write_query call should create the EpistemicFrame
        assert graph.run_write_query.call_count >= 2
        frame_call = graph.run_write_query.call_args_list[1]
        cypher = frame_call[0][0]
        assert "EpistemicFrame" in cypher
        assert "HAS_FRAME" in cypher

    @pytest.mark.asyncio
    async def test_no_frame_when_claim_has_none(self) -> None:
        """No EpistemicFrame created when claim has no frame."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        claim = _make_claim(epistemic_frame=None)

        service = ClaimWriteBackService(graph=graph, session=session)
        await service.ingest_claim(claim, target_activity_id=None)

        # Only one write_query call (Claim node only)
        assert graph.run_write_query.call_count == 1

    @pytest.mark.asyncio
    async def test_frame_keyed_on_session_and_role(self) -> None:
        """Frame MERGE is keyed on session_id + respondent_role."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        frame = _make_epistemic_frame()
        claim = _make_claim(epistemic_frame=frame)

        service = ClaimWriteBackService(graph=graph, session=session)
        await service.ingest_claim(claim, target_activity_id=None)

        frame_call = graph.run_write_query.call_args_list[1]
        params = frame_call[0][1]
        assert "session_id" in params
        assert "respondent_role" in params


# ── Scenario 4: Confidence Score Recomputation ───────────────────────


class TestConfidenceRecomputation:
    """Scenario 4: Confidence Score Update on Supporting Claims."""

    @pytest.mark.asyncio
    async def test_recomputes_from_claim_weights(self) -> None:
        """Confidence is computed as average of claim weights."""
        graph = AsyncMock()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "claim_count": 5,
                    "total_weight": 4.0,
                    "weights": [1.0, 1.0, 0.6, 0.6, 0.8],
                }
            ]
        )
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        result = await service.recompute_activity_confidence("act_001", uuid.uuid4())

        assert result["claim_count"] == 5
        assert result["aggregate_weight"] == 4.0
        assert result["claim_confidence"] == 0.8  # 4.0 / 5

    @pytest.mark.asyncio
    async def test_confidence_bounded_zero_to_one(self) -> None:
        """Confidence is clamped to [0.0, 1.0]."""
        graph = AsyncMock()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "claim_count": 2,
                    "total_weight": 5.0,
                    "weights": [3.0, 2.0],
                }
            ]
        )
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        result = await service.recompute_activity_confidence("act_002", uuid.uuid4())

        assert result["claim_confidence"] == 1.0  # Clamped to max

    @pytest.mark.asyncio
    async def test_zero_confidence_with_no_claims(self) -> None:
        """Zero confidence when no claims exist for the activity."""
        graph = AsyncMock()
        graph.run_query = AsyncMock(return_value=[])
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        result = await service.recompute_activity_confidence("act_003", uuid.uuid4())

        assert result["claim_count"] == 0
        assert result["claim_confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_updates_activity_node_with_confidence(self) -> None:
        """Activity node is updated with claim_confidence in Neo4j."""
        graph = AsyncMock()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "claim_count": 3,
                    "total_weight": 2.4,
                    "weights": [1.0, 0.6, 0.8],
                }
            ]
        )
        graph.run_write_query = AsyncMock(return_value=None)
        session = AsyncMock()

        service = ClaimWriteBackService(graph=graph, session=session)
        await service.recompute_activity_confidence("act_001", uuid.uuid4())

        # Verify confidence update was written
        write_call = graph.run_write_query.call_args_list[0]
        cypher = write_call[0][0]
        assert "claim_confidence" in cypher


# ── Batch Ingest ─────────────────────────────────────────────────────


class TestBatchIngest:
    """Batch claim ingestion with activity recomputation."""

    @pytest.mark.asyncio
    async def test_batch_ingest_counts(self) -> None:
        """Batch ingest returns correct counts."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "claim_count": 2,
                    "total_weight": 1.6,
                    "weights": [1.0, 0.6],
                }
            ]
        )
        session = AsyncMock()
        session.flush = AsyncMock()

        engagement_id = uuid.uuid4()
        claims = [
            _make_claim(
                certainty_tier=CertaintyTier.KNOWN,
                engagement_id=engagement_id,
            ),
            _make_claim(
                certainty_tier=CertaintyTier.SUSPECTED,
                engagement_id=engagement_id,
            ),
        ]

        service = ClaimWriteBackService(graph=graph, session=session)
        target_map = {claims[0].id: "act_001", claims[1].id: "act_001"}
        result = await service.batch_ingest_claims(claims, target_map)

        assert result["claims_ingested"] == 2
        assert result["edges_created"] == 2
        assert result["conflicts_created"] == 0
        assert result["activities_recomputed"] == 1

    @pytest.mark.asyncio
    async def test_batch_ingest_with_contradicted(self) -> None:
        """Batch ingest creates conflict for contradicted claim."""
        graph = AsyncMock()
        graph.run_write_query = AsyncMock(return_value=None)
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "claim_count": 2,
                    "total_weight": 0.5,
                    "weights": [1.0, -0.5],
                }
            ]
        )
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        claims = [
            _make_claim(
                certainty_tier=CertaintyTier.KNOWN,
                engagement_id=engagement_id,
            ),
            _make_claim(
                certainty_tier=CertaintyTier.CONTRADICTED,
                engagement_id=engagement_id,
            ),
        ]

        service = ClaimWriteBackService(graph=graph, session=session)
        target_map = {claims[0].id: "act_001", claims[1].id: "act_001"}
        result = await service.batch_ingest_claims(claims, target_map)

        assert result["conflicts_created"] == 1


# ── Certainty Weight Mapping ─────────────────────────────────────────


class TestCertaintyWeights:
    """Verify the CERTAINTY_WEIGHTS mapping."""

    def test_known_weight_is_1(self) -> None:
        assert CERTAINTY_WEIGHTS[CertaintyTier.KNOWN] == 1.0

    def test_suspected_weight_is_0_6(self) -> None:
        assert CERTAINTY_WEIGHTS[CertaintyTier.SUSPECTED] == 0.6

    def test_unknown_weight_is_0_3(self) -> None:
        assert CERTAINTY_WEIGHTS[CertaintyTier.UNKNOWN] == 0.3

    def test_contradicted_weight_is_negative(self) -> None:
        assert CERTAINTY_WEIGHTS[CertaintyTier.CONTRADICTED] == -0.5

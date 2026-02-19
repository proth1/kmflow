"""Tests for semantic bridges.

Validates ProcessEvidenceBridge, EvidencePolicyBridge, ProcessTOMBridge,
and CommunicationDeviationBridge functionality.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.semantic.bridges.communication_deviation import CommunicationDeviationBridge
from src.semantic.bridges.evidence_policy import EvidencePolicyBridge
from src.semantic.bridges.process_evidence import ProcessEvidenceBridge
from src.semantic.bridges.process_tom import ProcessTOMBridge
from src.semantic.graph import GraphNode, KnowledgeGraphService


@pytest.fixture
def mock_graph():
    """Mock KnowledgeGraphService."""
    return AsyncMock(spec=KnowledgeGraphService)


# =============================================================================
# ProcessEvidenceBridge tests (word-overlap mode)
# =============================================================================


@pytest.fixture
def process_evidence_bridge(mock_graph):
    """ProcessEvidenceBridge instance (no embedding service)."""
    return ProcessEvidenceBridge(mock_graph)


@pytest.mark.asyncio
async def test_process_evidence_creates_relationships(process_evidence_bridge, mock_graph):
    """Test that ProcessEvidenceBridge creates SUPPORTED_BY relationships."""
    engagement_id = "eng-1"

    # Process and evidence with overlapping words
    process_node = GraphNode(
        id="proc-1",
        label="Process",
        properties={"name": "Customer Onboarding Workflow", "engagement_id": engagement_id},
    )

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "Customer Onboarding Guide Document", "engagement_id": engagement_id},
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [process_node],  # Process nodes
            [],  # Activity nodes
            [evidence_node],  # Evidence nodes
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_evidence_bridge.run(engagement_id)

    assert result.relationships_created == 1
    call_kwargs = mock_graph.create_relationship.call_args[1]
    assert call_kwargs["from_id"] == "proc-1"
    assert call_kwargs["to_id"] == "ev-1"
    assert call_kwargs["relationship_type"] == "SUPPORTED_BY"
    assert call_kwargs["properties"]["source"] == "process_evidence_bridge"
    assert call_kwargs["properties"]["confidence"] == 0.7


@pytest.mark.asyncio
async def test_process_evidence_no_overlap(process_evidence_bridge, mock_graph):
    """Test that no relationships are created when names don't overlap."""
    engagement_id = "eng-1"

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Invoice Processing", "engagement_id": engagement_id}
    )

    evidence_node = GraphNode(
        id="ev-1", label="Evidence", properties={"name": "Customer Feedback Survey", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [process_node],
            [],
            [evidence_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_evidence_bridge.run(engagement_id)

    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


@pytest.mark.asyncio
async def test_process_evidence_includes_activities(process_evidence_bridge, mock_graph):
    """Test that Activity nodes are also checked for relationships."""
    engagement_id = "eng-1"

    activity_node = GraphNode(
        id="act-1", label="Activity", properties={"name": "Verify Customer Documents", "engagement_id": engagement_id}
    )

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "Customer Document Verification Checklist", "engagement_id": engagement_id},
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [],  # Process nodes
            [activity_node],  # Activity nodes
            [evidence_node],  # Evidence nodes
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_evidence_bridge.run(engagement_id)

    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once()


@pytest.mark.asyncio
async def test_process_evidence_empty_nodes(process_evidence_bridge, mock_graph):
    """No relationships created when nodes are empty."""
    mock_graph.find_nodes = AsyncMock(side_effect=[[], [], []])
    mock_graph.create_relationship = AsyncMock()

    result = await process_evidence_bridge.run("eng-1")

    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


# =============================================================================
# ProcessEvidenceBridge tests (embedding mode)
# =============================================================================


def _make_embedding_service(similarity: float) -> MagicMock:
    """Mock embedding service returning embeddings with given cosine similarity."""
    svc = MagicMock()
    # Normalized vectors: [1, 0] and [cos(θ), sin(θ)] have dot product cos(θ)
    import math

    v1 = [1.0, 0.0]
    angle = math.acos(max(-1.0, min(1.0, similarity)))
    v2 = [math.cos(angle), math.sin(angle)]
    # embed_texts_async called twice: once for proc names (returns [v1]), once for ev names (returns [v2])
    svc.embed_texts_async = AsyncMock(side_effect=[[v1], [v2]])
    return svc


@pytest.mark.asyncio
async def test_process_evidence_with_embedding_above_threshold(mock_graph):
    """With embeddings above threshold, relationships are created."""
    embedding_service = _make_embedding_service(0.8)
    bridge = ProcessEvidenceBridge(mock_graph, embedding_service=embedding_service)

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Invoice Review", "engagement_id": "eng-1"}
    )
    evidence_node = GraphNode(
        id="ev-1", label="Evidence", properties={"name": "Finance Invoice Document", "engagement_id": "eng-1"}
    )

    mock_graph.find_nodes = AsyncMock(side_effect=[[process_node], [], [evidence_node]])
    mock_graph.create_relationship = AsyncMock()

    result = await bridge.run("eng-1")

    assert result.relationships_created == 1
    props = mock_graph.create_relationship.call_args[1]["properties"]
    assert props["confidence"] == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_process_evidence_with_embedding_below_threshold(mock_graph):
    """With embeddings below threshold, no relationships are created."""
    embedding_service = _make_embedding_service(0.3)
    bridge = ProcessEvidenceBridge(mock_graph, embedding_service=embedding_service)

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Invoice Review", "engagement_id": "eng-1"}
    )
    evidence_node = GraphNode(
        id="ev-1", label="Evidence", properties={"name": "Finance Invoice Document", "engagement_id": "eng-1"}
    )

    mock_graph.find_nodes = AsyncMock(side_effect=[[process_node], [], [evidence_node]])
    mock_graph.create_relationship = AsyncMock()

    result = await bridge.run("eng-1")

    assert result.relationships_created == 0


# =============================================================================
# EvidencePolicyBridge tests
# =============================================================================


@pytest.fixture
def evidence_policy_bridge(mock_graph):
    """EvidencePolicyBridge instance (no embedding service)."""
    return EvidencePolicyBridge(mock_graph)


@pytest.mark.asyncio
async def test_evidence_policy_creates_governed_by(evidence_policy_bridge, mock_graph):
    """Test that EvidencePolicyBridge creates GOVERNED_BY relationships."""
    engagement_id = "eng-1"

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "Data Retention Policy Compliance Report", "engagement_id": engagement_id},
    )

    policy_node = GraphNode(
        id="policy-1", label="Policy", properties={"name": "Data Retention Policy", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [evidence_node],
            [policy_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await evidence_policy_bridge.run(engagement_id)

    assert result.relationships_created == 1
    call_kwargs = mock_graph.create_relationship.call_args[1]
    assert call_kwargs["from_id"] == "ev-1"
    assert call_kwargs["to_id"] == "policy-1"
    assert call_kwargs["relationship_type"] == "GOVERNED_BY"
    assert call_kwargs["properties"]["source"] == "evidence_policy_bridge"


@pytest.mark.asyncio
async def test_evidence_policy_no_match(evidence_policy_bridge, mock_graph):
    """Test that no relationships are created when names don't match."""
    engagement_id = "eng-1"

    evidence_node = GraphNode(
        id="ev-1", label="Evidence", properties={"name": "Customer Survey Results", "engagement_id": engagement_id}
    )

    policy_node = GraphNode(
        id="policy-1", label="Policy", properties={"name": "Data Retention Policy", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [evidence_node],
            [policy_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await evidence_policy_bridge.run(engagement_id)

    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_policy_empty_nodes(evidence_policy_bridge, mock_graph):
    """No relationships created when evidence or policy nodes are empty."""
    mock_graph.find_nodes = AsyncMock(side_effect=[[], []])
    mock_graph.create_relationship = AsyncMock()

    result = await evidence_policy_bridge.run("eng-1")

    assert result.relationships_created == 0


@pytest.mark.asyncio
async def test_evidence_policy_with_embedding_above_threshold(mock_graph):
    """With embeddings above threshold, GOVERNED_BY relationships are created."""
    embedding_service = _make_embedding_service(0.75)
    bridge = EvidencePolicyBridge(mock_graph, embedding_service=embedding_service)

    ev_node = GraphNode(id="ev-1", label="Evidence", properties={"name": "Compliance Report", "engagement_id": "eng-1"})
    policy_node = GraphNode(
        id="p-1", label="Policy", properties={"name": "Compliance Framework", "engagement_id": "eng-1"}
    )

    mock_graph.find_nodes = AsyncMock(side_effect=[[ev_node], [policy_node]])
    mock_graph.create_relationship = AsyncMock()

    result = await bridge.run("eng-1")

    assert result.relationships_created == 1
    props = mock_graph.create_relationship.call_args[1]["properties"]
    assert "similarity_score" in props
    assert props["similarity_score"] == pytest.approx(0.75, abs=0.01)


# =============================================================================
# ProcessTOMBridge tests
# =============================================================================


@pytest.fixture
def process_tom_bridge(mock_graph):
    """ProcessTOMBridge instance."""
    return ProcessTOMBridge(mock_graph)


@pytest.mark.asyncio
async def test_process_tom_classifies_dimensions(process_tom_bridge, mock_graph):
    """Test that ProcessTOMBridge classifies process dimensions correctly."""
    engagement_id = "eng-1"

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Workflow Management Process", "engagement_id": engagement_id}
    )

    tom_node = GraphNode(
        id="tom-1", label="TOM", properties={"name": "Target Operating Model", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [process_node],
            [],  # Activity nodes
            [tom_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_tom_bridge.run(engagement_id)

    assert result.relationships_created >= 1
    mock_graph.create_relationship.assert_called()

    call_args = mock_graph.create_relationship.call_args
    assert call_args[1]["properties"]["dimension"] == "process_architecture"


@pytest.mark.asyncio
async def test_process_tom_risk_keywords(process_tom_bridge, mock_graph):
    """Test that risk-related keywords map to RISK_AND_COMPLIANCE dimension."""
    engagement_id = "eng-1"

    process_node = GraphNode(
        id="proc-1",
        label="Process",
        properties={"name": "Risk Assessment Control Process", "engagement_id": engagement_id},
    )

    tom_node = GraphNode(
        id="tom-1", label="TOM", properties={"name": "Target Operating Model", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [process_node],
            [],
            [tom_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_tom_bridge.run(engagement_id)

    assert result.relationships_created >= 1

    call_args_list = [call[1]["properties"]["dimension"] for call in mock_graph.create_relationship.call_args_list]
    assert "risk_and_compliance" in call_args_list


@pytest.mark.asyncio
async def test_process_tom_no_match(process_tom_bridge, mock_graph):
    """Test that generic process names don't create relationships."""
    engagement_id = "eng-1"

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "ABC XYZ", "engagement_id": engagement_id}
    )

    tom_node = GraphNode(
        id="tom-1", label="TOM", properties={"name": "Target Operating Model", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [process_node],
            [],
            [tom_node],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await process_tom_bridge.run(engagement_id)

    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


# =============================================================================
# CommunicationDeviationBridge tests
# =============================================================================


@pytest.fixture
def communication_deviation_bridge(mock_graph):
    """CommunicationDeviationBridge instance."""
    return CommunicationDeviationBridge(mock_graph)


@pytest.mark.asyncio
async def test_deviation_detected(communication_deviation_bridge, mock_graph):
    """Test that deviations are detected with workaround keyword."""
    engagement_id = "eng-1"

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "Email about approval workaround process", "engagement_id": engagement_id},
    )

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Approval Process", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [evidence_node],
            [process_node],
            [],  # Activity nodes
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await communication_deviation_bridge.run(engagement_id)

    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once_with(
        from_id="ev-1",
        to_id="proc-1",
        relationship_type="DEVIATES_FROM",
        properties={"source": "communication_deviation_bridge"},
    )


@pytest.mark.asyncio
async def test_no_deviation_keywords(communication_deviation_bridge, mock_graph):
    """Test that normal evidence doesn't create deviation relationships."""
    engagement_id = "eng-1"

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "Standard approval process documentation", "engagement_id": engagement_id},
    )

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Approval Process", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [evidence_node],
            [process_node],
            [],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await communication_deviation_bridge.run(engagement_id)

    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


@pytest.mark.asyncio
async def test_deviation_multiple_keywords(communication_deviation_bridge, mock_graph):
    """Test that bypass keyword also triggers deviation detection."""
    engagement_id = "eng-1"

    evidence_node = GraphNode(
        id="ev-1",
        label="Evidence",
        properties={"name": "We bypass the normal review process", "engagement_id": engagement_id},
    )

    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Review Process", "engagement_id": engagement_id}
    )

    mock_graph.find_nodes = AsyncMock(
        side_effect=[
            [evidence_node],
            [process_node],
            [],
        ]
    )
    mock_graph.create_relationship = AsyncMock()

    result = await communication_deviation_bridge.run(engagement_id)

    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once()

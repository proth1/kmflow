"""Tests for semantic bridges.

Validates ProcessEvidenceBridge, EvidencePolicyBridge, ProcessTOMBridge,
and CommunicationDeviationBridge functionality.
"""

from unittest.mock import AsyncMock

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
# ProcessEvidenceBridge tests
# =============================================================================


@pytest.fixture
def process_evidence_bridge(mock_graph):
    """ProcessEvidenceBridge instance."""
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

    # Execute
    result = await process_evidence_bridge.run(engagement_id)

    # Assertions
    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once_with(
        from_id="proc-1",
        to_id="ev-1",
        relationship_type="SUPPORTED_BY",
        properties={"source": "process_evidence_bridge", "confidence": 0.7},
    )


@pytest.mark.asyncio
async def test_process_evidence_no_overlap(process_evidence_bridge, mock_graph):
    """Test that no relationships are created when names don't overlap."""
    engagement_id = "eng-1"

    # Process and evidence with no common words
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

    # Execute
    result = await process_evidence_bridge.run(engagement_id)

    # Assertions
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

    # Execute
    result = await process_evidence_bridge.run(engagement_id)

    # Assertions
    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once()


# =============================================================================
# EvidencePolicyBridge tests
# =============================================================================


@pytest.fixture
def evidence_policy_bridge(mock_graph):
    """EvidencePolicyBridge instance."""
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

    # Execute
    result = await evidence_policy_bridge.run(engagement_id)

    # Assertions
    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once_with(
        from_id="ev-1",
        to_id="policy-1",
        relationship_type="GOVERNED_BY",
        properties={"source": "evidence_policy_bridge"},
    )


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

    # Execute
    result = await evidence_policy_bridge.run(engagement_id)

    # Assertions
    assert result.relationships_created == 0
    mock_graph.create_relationship.assert_not_called()


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

    # Execute
    result = await process_tom_bridge.run(engagement_id)

    # Assertions
    # "workflow" and "process" keywords should map to PROCESS_ARCHITECTURE dimension
    assert result.relationships_created >= 1
    mock_graph.create_relationship.assert_called()

    # Verify the dimension property
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

    # Execute
    result = await process_tom_bridge.run(engagement_id)

    # Assertions
    # Should create relationships for risk_and_compliance and process_architecture
    assert result.relationships_created >= 1

    # Check that risk_and_compliance dimension was used
    call_args_list = [call[1]["properties"]["dimension"] for call in mock_graph.create_relationship.call_args_list]
    assert "risk_and_compliance" in call_args_list


@pytest.mark.asyncio
async def test_process_tom_no_match(process_tom_bridge, mock_graph):
    """Test that generic process names don't create relationships."""
    engagement_id = "eng-1"

    # Generic name with no matching keywords
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

    # Execute
    result = await process_tom_bridge.run(engagement_id)

    # Assertions
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

    # Execute
    result = await communication_deviation_bridge.run(engagement_id)

    # Assertions
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

    # Execute
    result = await communication_deviation_bridge.run(engagement_id)

    # Assertions
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

    # Execute
    result = await communication_deviation_bridge.run(engagement_id)

    # Assertions
    assert result.relationships_created == 1
    mock_graph.create_relationship.assert_called_once()

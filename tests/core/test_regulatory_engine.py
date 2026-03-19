"""Tests for RegulatoryOverlayEngine.

Validates governance chain building, compliance assessment, and ungoverned
process detection functionality.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ComplianceLevel, Control, ControlEffectiveness, Policy, PolicyType, Regulation
from src.core.regulatory import ComplianceState, RegulatoryOverlayEngine
from src.semantic.graph import GraphNode, KnowledgeGraphService


@pytest.fixture
def mock_graph():
    """Mock KnowledgeGraphService."""
    return AsyncMock(spec=KnowledgeGraphService)


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database queries."""
    return AsyncMock()


@pytest.fixture
def regulatory_engine(mock_graph):
    """Regulatory engine instance with mocked graph service."""
    return RegulatoryOverlayEngine(mock_graph)


@pytest.fixture
def sample_policy():
    """Sample policy for testing."""
    policy = MagicMock(spec=Policy)
    policy.id = uuid.uuid4()
    policy.name = "Data Retention Policy"
    policy.policy_type = PolicyType.ORGANIZATIONAL
    return policy


@pytest.fixture
def sample_control():
    """Sample control for testing."""
    control = MagicMock(spec=Control)
    control.id = uuid.uuid4()
    control.name = "Monthly Data Cleanup"
    control.effectiveness = ControlEffectiveness.EFFECTIVE
    control.linked_policy_ids = []
    return control


@pytest.fixture
def sample_regulation():
    """Sample regulation for testing."""
    regulation = MagicMock(spec=Regulation)
    regulation.id = uuid.uuid4()
    regulation.name = "GDPR Article 5"
    regulation.framework = "GDPR"
    return regulation


@pytest.mark.asyncio
async def test_build_governance_chains(
    regulatory_engine, mock_graph, mock_session, sample_policy, sample_control, sample_regulation
):
    """Test governance chain building with policies, controls, and regulations."""
    engagement_id = "eng-1"

    # Mock database queries
    mock_policy_result = MagicMock()
    mock_policy_result.scalars.return_value.all.return_value = [sample_policy]

    mock_control_result = MagicMock()
    mock_control_result.scalars.return_value.all.return_value = [sample_control]

    mock_reg_result = MagicMock()
    mock_reg_result.scalars.return_value.all.return_value = [sample_regulation]

    mock_session.execute = AsyncMock(side_effect=[mock_policy_result, mock_control_result, mock_reg_result])

    # Mock graph nodes
    process_node = GraphNode(
        id="proc-1", label="Process", properties={"name": "Review Customer Data", "engagement_id": engagement_id}
    )
    mock_graph.find_nodes = AsyncMock(return_value=[process_node])
    mock_graph.run_write_query = AsyncMock()

    # The batch chain query returns a row linking proc-1 to the policy
    policy_node_id = f"policy-{sample_policy.id}"
    mock_graph.run_query = AsyncMock(
        return_value=[
            {
                "process_id": "proc-1",
                "process_name": "Review Customer Data",
                "policy_id": policy_node_id,
                "policy_name": sample_policy.name,
                "rel_type": "GOVERNED_BY",
            }
        ]
    )

    # Execute
    chains = await regulatory_engine.build_governance_chains(mock_session, engagement_id)

    # Assertions
    assert len(chains) == 1
    assert chains[0].process_id == "proc-1"
    assert chains[0].process_name == "Review Customer Data"
    assert len(chains[0].policies) == 1
    assert chains[0].policies[0]["name"] == sample_policy.name

    # Verify run_write_query was called to upsert the Policy node
    mock_graph.run_write_query.assert_called()


@pytest.mark.asyncio
async def test_build_governance_chains_no_processes(regulatory_engine, mock_graph, mock_session, sample_policy):
    """Test governance chain building with no processes in graph."""
    engagement_id = "eng-1"

    # Mock empty database results
    mock_policy_result = MagicMock()
    mock_policy_result.scalars.return_value.all.return_value = [sample_policy]

    mock_control_result = MagicMock()
    mock_control_result.scalars.return_value.all.return_value = []

    mock_reg_result = MagicMock()
    mock_reg_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[mock_policy_result, mock_control_result, mock_reg_result])

    # Mock empty process nodes
    mock_graph.find_nodes = AsyncMock(return_value=[])
    mock_graph.run_write_query = AsyncMock()
    mock_graph.run_query = AsyncMock(return_value=[])

    # Execute
    chains = await regulatory_engine.build_governance_chains(mock_session, engagement_id)

    # Assertions
    assert len(chains) == 0


@pytest.mark.asyncio
async def test_build_governance_chains_creates_policy_nodes(regulatory_engine, mock_graph, mock_session, sample_policy):
    """Test that governance chain building calls run_write_query for Policy nodes."""
    engagement_id = "eng-1"

    # Mock database queries
    mock_policy_result = MagicMock()
    mock_policy_result.scalars.return_value.all.return_value = [sample_policy]

    mock_control_result = MagicMock()
    mock_control_result.scalars.return_value.all.return_value = []

    mock_reg_result = MagicMock()
    mock_reg_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[mock_policy_result, mock_control_result, mock_reg_result])

    # Mock process nodes
    mock_graph.find_nodes = AsyncMock(return_value=[])
    mock_graph.run_write_query = AsyncMock()
    mock_graph.run_query = AsyncMock(return_value=[])

    # Execute
    await regulatory_engine.build_governance_chains(mock_session, engagement_id)

    # Verify run_write_query was called (MERGE for policy node upsert)
    mock_graph.run_write_query.assert_called()
    call_kwargs_list = [call.args[1] for call in mock_graph.run_write_query.call_args_list]
    # The policy upsert call should include the policy id and name
    policy_node_id = f"policy-{sample_policy.id}"
    assert any(kw.get("id") == policy_node_id for kw in call_kwargs_list)
    assert any(kw.get("name") == sample_policy.name for kw in call_kwargs_list)


@pytest.mark.asyncio
async def test_assess_compliance_fully_compliant(regulatory_engine, mock_graph, mock_session):
    """Test compliance assessment with >90% coverage."""
    engagement_id = "eng-1"

    # Create 10 process nodes, all with GOVERNED_BY relationships
    process_nodes = [
        GraphNode(id=f"proc-{i}", label="Process", properties={"name": f"Process {i}", "engagement_id": engagement_id})
        for i in range(10)
    ]

    mock_graph.find_nodes = AsyncMock(return_value=process_nodes)

    # Batch query returns all 10 processes with policy_count > 0
    mock_graph.run_query = AsyncMock(
        return_value=[{"process_id": f"proc-{i}", "process_name": f"Process {i}", "policy_count": 1} for i in range(10)]
    )

    # Execute
    state = await regulatory_engine.assess_compliance(mock_session, engagement_id)

    # Assertions
    assert state.engagement_id == engagement_id
    assert state.total_processes == 10
    assert state.governed_count == 10
    assert state.ungoverned_count == 0
    assert state.policy_coverage == 100.0
    assert state.level == ComplianceLevel.FULLY_COMPLIANT


@pytest.mark.asyncio
async def test_assess_compliance_partially_compliant(regulatory_engine, mock_graph, mock_session):
    """Test compliance assessment with 50-89% coverage."""
    engagement_id = "eng-1"

    # Create 10 process nodes
    process_nodes = [
        GraphNode(id=f"proc-{i}", label="Process", properties={"name": f"Process {i}", "engagement_id": engagement_id})
        for i in range(10)
    ]

    mock_graph.find_nodes = AsyncMock(return_value=process_nodes)

    # 7 out of 10 have governance (70% coverage)
    batch_rows = [
        {"process_id": f"proc-{i}", "process_name": f"Process {i}", "policy_count": 1 if i < 7 else 0}
        for i in range(10)
    ]
    mock_graph.run_query = AsyncMock(return_value=batch_rows)

    # Execute
    state = await regulatory_engine.assess_compliance(mock_session, engagement_id)

    # Assertions
    assert state.total_processes == 10
    assert state.governed_count == 7
    assert state.ungoverned_count == 3
    assert state.policy_coverage == 70.0
    assert state.level == ComplianceLevel.PARTIALLY_COMPLIANT


@pytest.mark.asyncio
async def test_assess_compliance_non_compliant(regulatory_engine, mock_graph, mock_session):
    """Test compliance assessment with <50% coverage."""
    engagement_id = "eng-1"

    # Create 10 process nodes
    process_nodes = [
        GraphNode(id=f"proc-{i}", label="Process", properties={"name": f"Process {i}", "engagement_id": engagement_id})
        for i in range(10)
    ]

    mock_graph.find_nodes = AsyncMock(return_value=process_nodes)

    # Only 4 out of 10 have governance (40% coverage)
    batch_rows = [
        {"process_id": f"proc-{i}", "process_name": f"Process {i}", "policy_count": 1 if i < 4 else 0}
        for i in range(10)
    ]
    mock_graph.run_query = AsyncMock(return_value=batch_rows)

    # Execute
    state = await regulatory_engine.assess_compliance(mock_session, engagement_id)

    # Assertions
    assert state.total_processes == 10
    assert state.governed_count == 4
    assert state.ungoverned_count == 6
    assert state.policy_coverage == 40.0
    assert state.level == ComplianceLevel.NON_COMPLIANT


@pytest.mark.asyncio
async def test_assess_compliance_not_assessed(regulatory_engine, mock_graph, mock_session):
    """Test compliance assessment with no processes."""
    engagement_id = "eng-1"

    mock_graph.find_nodes = AsyncMock(return_value=[])
    mock_graph.run_query = AsyncMock(return_value=[])

    # Execute
    state = await regulatory_engine.assess_compliance(mock_session, engagement_id)

    # Assertions
    assert state.total_processes == 0
    assert state.governed_count == 0
    assert state.ungoverned_count == 0
    assert state.policy_coverage == 0.0
    assert state.level == ComplianceLevel.NOT_ASSESSED


@pytest.mark.asyncio
async def test_find_ungoverned_processes(regulatory_engine, mock_graph):
    """Test finding processes without governance links."""
    engagement_id = "eng-1"

    # Mix of governed and ungoverned processes
    process_nodes = [
        GraphNode(id="proc-1", label="Process", properties={"name": "Governed Process"}),
        GraphNode(id="proc-2", label="Process", properties={"name": "Ungoverned Process"}),
        GraphNode(id="proc-3", label="Process", properties={"name": "Another Ungoverned"}),
    ]

    mock_graph.find_nodes = AsyncMock(return_value=process_nodes)

    # Batch query returns only the ungoverned processes
    mock_graph.run_query = AsyncMock(
        return_value=[
            {"process_id": "proc-2", "process_name": "Ungoverned Process"},
            {"process_id": "proc-3", "process_name": "Another Ungoverned"},
        ]
    )

    # Execute
    ungoverned = await regulatory_engine.find_ungoverned_processes(engagement_id)

    # Assertions
    assert len(ungoverned) == 2
    assert ungoverned[0]["process_id"] == "proc-2"
    assert ungoverned[0]["process_name"] == "Ungoverned Process"
    assert ungoverned[1]["process_id"] == "proc-3"
    assert ungoverned[1]["process_name"] == "Another Ungoverned"


@pytest.mark.asyncio
async def test_find_ungoverned_all_governed(regulatory_engine, mock_graph):
    """Test finding ungoverned processes when all are governed."""
    engagement_id = "eng-1"

    process_nodes = [
        GraphNode(id="proc-1", label="Process", properties={"name": "Process 1"}),
        GraphNode(id="proc-2", label="Process", properties={"name": "Process 2"}),
    ]

    mock_graph.find_nodes = AsyncMock(return_value=process_nodes)

    # Batch query returns empty (no ungoverned processes)
    mock_graph.run_query = AsyncMock(return_value=[])

    # Execute
    ungoverned = await regulatory_engine.find_ungoverned_processes(engagement_id)

    # Assertions
    assert len(ungoverned) == 0


def test_compliance_state_dataclass():
    """Test ComplianceState dataclass default values."""
    state = ComplianceState()

    assert state.engagement_id == ""
    assert state.level == ComplianceLevel.NOT_ASSESSED
    assert state.governed_count == 0
    assert state.ungoverned_count == 0
    assert state.total_processes == 0
    assert state.policy_coverage == 0.0
    assert state.details == []

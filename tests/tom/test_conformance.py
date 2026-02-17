"""Tests for ConformanceCheckingEngine.

Validates process model conformance checking, fitness score calculation,
and deviation detection functionality.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ProcessElement, ProcessElementType
from src.tom.conformance import ConformanceCheckingEngine, ConformanceResult, Deviation


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database queries."""
    return AsyncMock()


@pytest.fixture
def conformance_engine():
    """ConformanceCheckingEngine instance."""
    return ConformanceCheckingEngine()


def create_mock_element(name: str, model_id: str) -> MagicMock:
    """Create a mock ProcessElement."""
    element = MagicMock(spec=ProcessElement)
    element.name = name
    element.model_id = model_id
    element.element_type = ProcessElementType.ACTIVITY
    return element


@pytest.mark.asyncio
async def test_check_conformance_perfect_match(conformance_engine, mock_session):
    """Test conformance checking with identical elements."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    # Same elements in both models
    elements = [
        create_mock_element("Review Application", pov_model_id),
        create_mock_element("Verify Documents", pov_model_id),
        create_mock_element("Approve Request", pov_model_id),
    ]

    ref_elements = [
        create_mock_element("Review Application", ref_model_id),
        create_mock_element("Verify Documents", ref_model_id),
        create_mock_element("Approve Request", ref_model_id),
    ]

    # Mock database queries
    async def mock_execute(query):
        result = MagicMock()
        # First call returns POV elements, second returns reference elements
        if not hasattr(mock_execute, 'call_count'):
            mock_execute.call_count = 0
        mock_execute.call_count += 1

        if mock_execute.call_count == 1:
            result.scalars.return_value.all.return_value = elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.pov_model_id == pov_model_id
    assert result.reference_model_id == ref_model_id
    assert result.fitness_score == 1.0
    assert result.matching_elements == 3
    assert result.total_reference_elements == 3
    assert len(result.deviations) == 0


@pytest.mark.asyncio
async def test_check_conformance_partial_match(conformance_engine, mock_session):
    """Test conformance checking with partial overlap."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    # POV has 2 matching and 1 different
    pov_elements = [
        create_mock_element("Review Application", pov_model_id),
        create_mock_element("Verify Documents", pov_model_id),
        create_mock_element("Send Notification", pov_model_id),
    ]

    # Reference has 2 matching and 1 different
    ref_elements = [
        create_mock_element("Review Application", ref_model_id),
        create_mock_element("Verify Documents", ref_model_id),
        create_mock_element("Approve Request", ref_model_id),
    ]

    # Mock database queries
    call_count = [0]

    async def mock_execute(query):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalars.return_value.all.return_value = pov_elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.fitness_score == round(2 / 3, 4)  # 2 matches out of 3 reference elements
    assert result.matching_elements == 2
    assert result.total_reference_elements == 3
    assert len(result.deviations) == 2  # 1 missing + 1 extra

    # Check deviation types
    deviation_types = {d.deviation_type for d in result.deviations}
    assert "missing" in deviation_types
    assert "extra" in deviation_types


@pytest.mark.asyncio
async def test_check_conformance_no_match(conformance_engine, mock_session):
    """Test conformance checking with no overlap."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    # Completely different elements
    pov_elements = [
        create_mock_element("POV Activity A", pov_model_id),
        create_mock_element("POV Activity B", pov_model_id),
    ]

    ref_elements = [
        create_mock_element("Ref Activity X", ref_model_id),
        create_mock_element("Ref Activity Y", ref_model_id),
        create_mock_element("Ref Activity Z", ref_model_id),
    ]

    # Mock database queries
    call_count = [0]

    async def mock_execute(query):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalars.return_value.all.return_value = pov_elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.fitness_score == 0.0
    assert result.matching_elements == 0
    assert result.total_reference_elements == 3
    assert len(result.deviations) == 5  # 3 missing + 2 extra


@pytest.mark.asyncio
async def test_check_conformance_extra_elements(conformance_engine, mock_session):
    """Test conformance checking with POV having extra elements."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    # POV has all reference elements plus extras
    pov_elements = [
        create_mock_element("Review Application", pov_model_id),
        create_mock_element("Verify Documents", pov_model_id),
        create_mock_element("Extra Step 1", pov_model_id),
        create_mock_element("Extra Step 2", pov_model_id),
    ]

    ref_elements = [
        create_mock_element("Review Application", ref_model_id),
        create_mock_element("Verify Documents", ref_model_id),
    ]

    # Mock database queries
    call_count = [0]

    async def mock_execute(query):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalars.return_value.all.return_value = pov_elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.fitness_score == 1.0  # All reference elements found
    assert result.matching_elements == 2
    assert result.total_reference_elements == 2

    # Should have 2 "extra" deviations
    extra_deviations = [d for d in result.deviations if d.deviation_type == "extra"]
    assert len(extra_deviations) == 2


@pytest.mark.asyncio
async def test_check_conformance_no_reference(conformance_engine, mock_session):
    """Test conformance checking with empty reference model."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    pov_elements = [
        create_mock_element("Activity A", pov_model_id),
        create_mock_element("Activity B", pov_model_id),
    ]

    ref_elements = []

    # Mock database queries
    call_count = [0]

    async def mock_execute(query):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalars.return_value.all.return_value = pov_elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.fitness_score == 0.0
    assert result.matching_elements == 0
    assert result.total_reference_elements == 0


@pytest.mark.asyncio
async def test_check_conformance_case_insensitive(conformance_engine, mock_session):
    """Test that conformance checking is case-insensitive."""
    pov_model_id = str(uuid.uuid4())
    ref_model_id = str(uuid.uuid4())

    # Same elements with different case
    pov_elements = [
        create_mock_element("REVIEW APPLICATION", pov_model_id),
        create_mock_element("verify documents", pov_model_id),
    ]

    ref_elements = [
        create_mock_element("Review Application", ref_model_id),
        create_mock_element("Verify Documents", ref_model_id),
    ]

    # Mock database queries
    call_count = [0]

    async def mock_execute(query):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalars.return_value.all.return_value = pov_elements
        else:
            result.scalars.return_value.all.return_value = ref_elements
        return result

    mock_session.execute = mock_execute

    # Execute
    result = await conformance_engine.check_conformance(mock_session, pov_model_id, ref_model_id)

    # Assertions
    assert result.fitness_score == 1.0
    assert result.matching_elements == 2
    assert len(result.deviations) == 0


def test_deviation_severity():
    """Test that deviation severity values are correct."""
    # Missing elements have severity 0.7
    missing = Deviation(
        element_name="Test",
        deviation_type="missing",
        severity=0.7,
        description="Test missing"
    )
    assert missing.severity == 0.7

    # Extra elements have severity 0.3
    extra = Deviation(
        element_name="Test",
        deviation_type="extra",
        severity=0.3,
        description="Test extra"
    )
    assert extra.severity == 0.3

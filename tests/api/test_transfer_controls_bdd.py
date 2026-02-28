"""BDD tests for Story #395: Cross-Border Data Transfer Controls.

Tests transfer evaluation with EU_ONLY restrictions, TIA + SCC requirements,
blocking without legal mechanisms, and jurisdiction registry lookups.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.transfer_control import TransferControlService
from src.core.models import (
    StandardContractualClause,
    TIAStatus,
    TransferDecision,
    TransferImpactAssessment,
)
from src.core.models.transfer import (
    JURISDICTION_REGISTRY,
    RESTRICTED_DESTINATIONS,
    DataResidencyRestriction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _mock_tia(*, approved: bool = True) -> MagicMock:
    tia = MagicMock(spec=TransferImpactAssessment)
    tia.id = uuid.uuid4()
    tia.engagement_id = ENGAGEMENT_ID
    tia.connector_id = "anthropic"
    tia.destination_jurisdiction = "US"
    tia.status = TIAStatus.APPROVED if approved else TIAStatus.PENDING
    tia.approved_at = datetime.now(UTC) if approved else None
    tia.approved_by = "dpo" if approved else None
    return tia


def _mock_scc() -> MagicMock:
    scc = MagicMock(spec=StandardContractualClause)
    scc.id = uuid.uuid4()
    scc.engagement_id = ENGAGEMENT_ID
    scc.connector_id = "anthropic"
    scc.scc_version = "EU-2021"
    scc.reference_id = "SCC-2024-001"
    scc.executed_at = datetime.now(UTC)
    return scc


# ---------------------------------------------------------------------------
# BDD Scenario 1: EU_ONLY engagement blocks US transfer without TIA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_eu_only_blocks_us_transfer_without_tia() -> None:
    """Given EU_ONLY restriction and no TIA,
    When transfer to US (Anthropic) is evaluated,
    Then transfer is blocked with reason transfer_impact_assessment_required."""
    session = _mock_session()

    # No TIA found
    no_tia_result = MagicMock()
    no_tia_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_tia_result)

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        data_residency=DataResidencyRestriction.EU_ONLY,
    )

    assert result["decision"] == TransferDecision.BLOCKED_NO_TIA
    assert result["reason"] == "transfer_impact_assessment_required"
    assert "US" in result["destination"]
    assert "anthropic" in result["destination"]
    # Transfer log recorded
    session.add.assert_called()


@pytest.mark.asyncio
async def test_scenario_1_eu_only_blocks_us_transfer_without_scc() -> None:
    """Given EU_ONLY with approved TIA but no SCC,
    When transfer is evaluated,
    Then transfer is blocked with reason no_scc_on_file."""
    session = _mock_session()
    tia = _mock_tia(approved=True)

    tia_result = MagicMock()
    tia_result.scalar_one_or_none.return_value = tia

    no_scc_result = MagicMock()
    no_scc_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[tia_result, no_scc_result])

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        data_residency=DataResidencyRestriction.EU_ONLY,
    )

    assert result["decision"] == TransferDecision.BLOCKED_NO_SCC
    assert result["reason"] == "no_scc_on_file"
    assert "tia_id" in result


# ---------------------------------------------------------------------------
# BDD Scenario 2: Transfer permitted with TIA + SCC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_transfer_permitted_with_tia_and_scc() -> None:
    """Given EU_ONLY with approved TIA and SCC on file,
    When transfer to US is evaluated,
    Then transfer is PERMITTED with logged references."""
    session = _mock_session()
    tia = _mock_tia(approved=True)
    scc = _mock_scc()

    tia_result = MagicMock()
    tia_result.scalar_one_or_none.return_value = tia

    scc_result = MagicMock()
    scc_result.scalar_one_or_none.return_value = scc

    session.execute = AsyncMock(side_effect=[tia_result, scc_result])

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        data_residency=DataResidencyRestriction.EU_ONLY,
    )

    assert result["decision"] == TransferDecision.PERMITTED
    assert result["reason"] == "tia_and_scc_valid"
    assert result["scc_reference_id"] == "SCC-2024-001"
    assert "tia_id" in result


# ---------------------------------------------------------------------------
# BDD Scenario 3: No legal mechanism blocks with guidance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_no_mechanism_returns_guidance() -> None:
    """Given EU_ONLY with no TIA or SCC,
    When transfer is blocked,
    Then compliance guidance is provided."""
    session = _mock_session()

    no_tia_result = MagicMock()
    no_tia_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_tia_result)

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        data_residency=DataResidencyRestriction.EU_ONLY,
    )

    assert result["decision"] == TransferDecision.BLOCKED_NO_TIA
    assert "guidance" in result
    assert "Transfer Impact Assessment" in result["guidance"]
    assert "SCCs" in result["guidance"]


# ---------------------------------------------------------------------------
# BDD Scenario 4: No restriction = always permit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_no_restriction_always_permits() -> None:
    """Given NONE residency restriction,
    When any transfer is evaluated,
    Then it is always permitted."""
    session = _mock_session()

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        data_residency=DataResidencyRestriction.NONE,
    )

    assert result["decision"] == TransferDecision.PERMITTED
    assert result["reason"] == "no_residency_restriction"


# ---------------------------------------------------------------------------
# Additional: EU connector not restricted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eu_connector_not_restricted_by_eu_only() -> None:
    """EU_ONLY restriction doesn't block transfers to EU connectors."""
    session = _mock_session()

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=ENGAGEMENT_ID,
        connector_id="azure_openai",  # EU jurisdiction
        data_residency=DataResidencyRestriction.EU_ONLY,
    )

    assert result["decision"] == TransferDecision.PERMITTED
    assert result["reason"] == "destination_not_restricted"


# ---------------------------------------------------------------------------
# TIA lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tia() -> None:
    """Create a Transfer Impact Assessment."""
    session = _mock_session()
    service = TransferControlService(session)

    tia = await service.create_tia(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        assessor="dpo_user",
    )

    assert isinstance(tia, TransferImpactAssessment)
    assert tia.status == TIAStatus.PENDING
    assert tia.destination_jurisdiction == "US"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_approve_tia() -> None:
    """Approve a pending TIA."""
    session = _mock_session()
    tia = _mock_tia(approved=False)

    result = MagicMock()
    result.scalar_one_or_none.return_value = tia
    session.execute = AsyncMock(return_value=result)

    service = TransferControlService(session)
    approved = await service.approve_tia(
        tia_id=tia.id,
        approved_by="ciso",
    )

    assert approved.status == TIAStatus.APPROVED
    assert approved.approved_by == "ciso"
    assert approved.approved_at is not None


@pytest.mark.asyncio
async def test_approve_tia_not_found_raises() -> None:
    """Approving non-existent TIA raises ValueError."""
    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    service = TransferControlService(session)
    with pytest.raises(ValueError, match="not found"):
        await service.approve_tia(tia_id=uuid.uuid4(), approved_by="ciso")


# ---------------------------------------------------------------------------
# SCC recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_scc() -> None:
    """Record Standard Contractual Clauses."""
    session = _mock_session()
    service = TransferControlService(session)

    scc = await service.record_scc(
        engagement_id=ENGAGEMENT_ID,
        connector_id="anthropic",
        scc_version="EU-2021",
        reference_id="SCC-2024-001",
        executed_at=datetime.now(UTC),
    )

    assert isinstance(scc, StandardContractualClause)
    assert scc.reference_id == "SCC-2024-001"
    session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_jurisdiction_registry_completeness() -> None:
    """Jurisdiction registry covers all known providers."""
    assert "anthropic" in JURISDICTION_REGISTRY
    assert "openai" in JURISDICTION_REGISTRY
    assert JURISDICTION_REGISTRY["anthropic"] == "US"
    assert JURISDICTION_REGISTRY["azure_openai"] == "EU"


def test_restricted_destinations_eu_only() -> None:
    """EU_ONLY restricts US, CN, RU, IN destinations."""
    restricted = RESTRICTED_DESTINATIONS[DataResidencyRestriction.EU_ONLY]
    assert "US" in restricted
    assert "CN" in restricted


def test_data_residency_enum_values() -> None:
    """DataResidencyRestriction has correct enum values."""
    assert DataResidencyRestriction.NONE == "none"
    assert DataResidencyRestriction.EU_ONLY == "eu_only"
    assert DataResidencyRestriction.UK_ONLY == "uk_only"
    assert DataResidencyRestriction.CUSTOM == "custom"


def test_transfer_decision_enum_values() -> None:
    """TransferDecision has correct enum values."""
    assert TransferDecision.PERMITTED == "permitted"
    assert TransferDecision.BLOCKED_NO_TIA == "blocked_no_tia"
    assert TransferDecision.BLOCKED_NO_SCC == "blocked_no_scc"

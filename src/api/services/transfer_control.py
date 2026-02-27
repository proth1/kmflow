"""Cross-border data transfer control service.

Evaluates whether data transfers are permitted based on engagement
residency restrictions, Transfer Impact Assessments, and Standard
Contractual Clauses.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    DataTransferLog,
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

logger = logging.getLogger(__name__)


class TransferControlService:
    """Evaluates and enforces cross-border data transfer controls."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate_transfer(
        self,
        engagement_id: uuid.UUID,
        connector_id: str,
        data_residency: DataResidencyRestriction,
    ) -> dict[str, Any]:
        """Evaluate whether a cross-border transfer is permitted.

        Args:
            engagement_id: The engagement context.
            connector_id: The integration connector identifier.
            data_residency: The engagement's residency restriction.

        Returns:
            Transfer decision with reason and supporting references.
        """
        # Look up destination jurisdiction
        jurisdiction = JURISDICTION_REGISTRY.get(connector_id.lower())
        if jurisdiction is None:
            jurisdiction = "UNKNOWN"

        # No restriction — always permit
        if data_residency == DataResidencyRestriction.NONE:
            decision = TransferDecision.PERMITTED
            log_entry = DataTransferLog(
                engagement_id=engagement_id,
                connector_id=connector_id,
                destination_jurisdiction=jurisdiction,
                decision=decision,
                details_json={"reason": "no_residency_restriction"},
            )
            self._session.add(log_entry)
            await self._session.flush()

            return {
                "decision": decision,
                "reason": "no_residency_restriction",
                "destination": f"{jurisdiction} ({connector_id})",
                "connector_id": connector_id,
            }

        # Check if destination is restricted
        restricted = RESTRICTED_DESTINATIONS.get(data_residency, set())
        if jurisdiction not in restricted:
            decision = TransferDecision.PERMITTED
            log_entry = DataTransferLog(
                engagement_id=engagement_id,
                connector_id=connector_id,
                destination_jurisdiction=jurisdiction,
                decision=decision,
                details_json={"reason": "destination_not_restricted"},
            )
            self._session.add(log_entry)
            await self._session.flush()

            return {
                "decision": decision,
                "reason": "destination_not_restricted",
                "destination": f"{jurisdiction} ({connector_id})",
                "connector_id": connector_id,
            }

        # Destination is restricted — check for TIA
        tia_result = await self._session.execute(
            select(TransferImpactAssessment).where(
                TransferImpactAssessment.engagement_id == engagement_id,
                TransferImpactAssessment.connector_id == connector_id,
                TransferImpactAssessment.status == TIAStatus.APPROVED,
            )
        )
        tia = tia_result.scalar_one_or_none()

        if tia is None:
            decision = TransferDecision.BLOCKED_NO_TIA
            log_entry = DataTransferLog(
                engagement_id=engagement_id,
                connector_id=connector_id,
                destination_jurisdiction=jurisdiction,
                decision=decision,
                details_json={
                    "reason": "transfer_impact_assessment_required",
                    "guidance": "Complete Transfer Impact Assessment before activating this connector",
                },
            )
            self._session.add(log_entry)
            await self._session.flush()

            return {
                "decision": decision,
                "reason": "transfer_impact_assessment_required",
                "destination": f"{jurisdiction} ({connector_id})",
                "connector_id": connector_id,
                "guidance": "Complete Transfer Impact Assessment and record SCCs before activating this connector",
            }

        # Check for SCC
        scc_result = await self._session.execute(
            select(StandardContractualClause).where(
                StandardContractualClause.engagement_id == engagement_id,
                StandardContractualClause.connector_id == connector_id,
            )
        )
        scc = scc_result.scalar_one_or_none()

        if scc is None:
            decision = TransferDecision.BLOCKED_NO_SCC
            log_entry = DataTransferLog(
                engagement_id=engagement_id,
                connector_id=connector_id,
                destination_jurisdiction=jurisdiction,
                decision=decision,
                tia_id=tia.id,
                details_json={
                    "reason": "no_scc_on_file",
                    "guidance": "Record Standard Contractual Clauses before activating this connector",
                },
            )
            self._session.add(log_entry)
            await self._session.flush()

            return {
                "decision": decision,
                "reason": "no_scc_on_file",
                "destination": f"{jurisdiction} ({connector_id})",
                "connector_id": connector_id,
                "tia_id": str(tia.id),
                "guidance": "Record Standard Contractual Clauses before activating this connector",
            }

        # Both TIA and SCC in place — permit
        decision = TransferDecision.PERMITTED
        log_entry = DataTransferLog(
            engagement_id=engagement_id,
            connector_id=connector_id,
            destination_jurisdiction=jurisdiction,
            decision=decision,
            scc_reference_id=scc.reference_id,
            tia_id=tia.id,
            details_json={
                "reason": "tia_and_scc_valid",
                "scc_version": scc.scc_version,
            },
        )
        self._session.add(log_entry)
        await self._session.flush()

        return {
            "decision": decision,
            "reason": "tia_and_scc_valid",
            "destination": f"{jurisdiction} ({connector_id})",
            "connector_id": connector_id,
            "scc_reference_id": scc.reference_id,
            "tia_id": str(tia.id),
        }

    async def create_tia(
        self,
        engagement_id: uuid.UUID,
        connector_id: str,
        assessor: str,
    ) -> TransferImpactAssessment:
        """Create a Transfer Impact Assessment.

        Args:
            engagement_id: The engagement context.
            connector_id: The connector being assessed.
            assessor: Identity of the assessor.

        Returns:
            Created TIA record.
        """
        jurisdiction = JURISDICTION_REGISTRY.get(connector_id.lower(), "UNKNOWN")

        now = datetime.now(UTC)
        tia = TransferImpactAssessment(
            id=uuid.uuid4(),
            engagement_id=engagement_id,
            connector_id=connector_id,
            destination_jurisdiction=jurisdiction,
            assessor=assessor,
            status=TIAStatus.PENDING,
            created_at=now,
        )
        self._session.add(tia)
        await self._session.flush()
        return tia

    async def approve_tia(
        self,
        tia_id: uuid.UUID,
        approved_by: str,
    ) -> TransferImpactAssessment:
        """Approve a Transfer Impact Assessment.

        Args:
            tia_id: The TIA to approve.
            approved_by: Identity of the approver.

        Returns:
            Updated TIA record.
        """
        result = await self._session.execute(
            select(TransferImpactAssessment).where(TransferImpactAssessment.id == tia_id)
        )
        tia = result.scalar_one_or_none()
        if tia is None:
            raise ValueError(f"TIA {tia_id} not found")

        tia.status = TIAStatus.APPROVED
        tia.approved_at = datetime.now(UTC)
        tia.approved_by = approved_by
        await self._session.flush()
        return tia

    async def record_scc(
        self,
        engagement_id: uuid.UUID,
        connector_id: str,
        scc_version: str,
        reference_id: str,
        executed_at: datetime,
    ) -> StandardContractualClause:
        """Record Standard Contractual Clauses for a connector.

        Args:
            engagement_id: The engagement context.
            connector_id: The connector covered by the SCC.
            scc_version: Version of the SCC document.
            reference_id: External reference ID for the SCC.
            executed_at: When the SCC was executed.

        Returns:
            Created SCC record.
        """
        scc = StandardContractualClause(
            id=uuid.uuid4(),
            engagement_id=engagement_id,
            connector_id=connector_id,
            scc_version=scc_version,
            reference_id=reference_id,
            executed_at=executed_at,
            created_at=datetime.now(UTC),
        )
        self._session.add(scc)
        await self._session.flush()
        return scc

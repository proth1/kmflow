"""Survey claim history model for certainty tier transition audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.models.survey import CertaintyTier


class SurveyClaimHistory(Base):
    """Audit trail for certainty tier transitions on survey claims."""

    __tablename__ = "survey_claim_history"
    __table_args__ = (Index("ix_survey_claim_history_claim_id", "claim_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("survey_claims.id", ondelete="CASCADE"), nullable=False
    )
    previous_tier: Mapped[CertaintyTier] = mapped_column(
        Enum(CertaintyTier, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    new_tier: Mapped[CertaintyTier] = mapped_column(
        Enum(CertaintyTier, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

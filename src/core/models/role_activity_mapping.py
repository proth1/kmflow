"""Role-activity mapping for reviewer routing (Story #365).

Maps performing roles to specific reviewers, enabling automatic
assignment of review packs to the correct SME based on the pack's
primary role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class RoleActivityMapping(Base):
    """Maps a performing role to a reviewer (SME) for an engagement.

    Used during review pack generation to route packs to the correct
    reviewer based on the pack's primary performing role.
    """

    __tablename__ = "role_activity_mappings"
    __table_args__ = (
        Index("ix_role_activity_mappings_engagement_id", "engagement_id"),
        Index("ix_role_activity_mappings_role_name", "role_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

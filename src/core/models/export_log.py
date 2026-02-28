"""Export log model for watermarked document tracking (Story #387).

Append-only table — no UPDATE or DELETE operations permitted.
Records who received what document and when for forensic tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExportLog(Base):
    """Append-only log of watermarked document exports."""

    __tablename__ = "export_logs"
    __table_args__ = (
        Index("ix_export_logs_engagement_id", "engagement_id"),
        Index("ix_export_logs_recipient_id", "recipient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ExportLog(id={self.id}, recipient={self.recipient_id}, type={self.document_type})>"

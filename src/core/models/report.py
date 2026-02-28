"""Report model for async report generation tracking."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ReportStatus(enum.StrEnum):
    """Status of an async report generation job."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


class ReportFormat(enum.StrEnum):
    """Output format for a generated report."""

    PDF = "pdf"
    HTML = "html"


class Report(Base):
    """Tracks async report generation jobs and their outputs."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReportStatus.PENDING
    )
    format: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ReportFormat.HTML
    )
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections_included: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_reports_engagement_id", "engagement_id"),
    )

"""SeedTerm model for domain vocabulary store.

Implements PRD v2.1 Section 6.10.3 (Seed List Pipeline). Seed terms are
the domain lens applied across all four evidence planes — they drive survey
probe generation, focus evidence extraction, and enable entity resolution
across heterogeneous sources.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class TermCategory(enum.StrEnum):
    """Controlled vocabulary for seed term categories."""

    ACTIVITY = "activity"
    SYSTEM = "system"
    ROLE = "role"
    REGULATION = "regulation"
    ARTIFACT = "artifact"


class TermSource(enum.StrEnum):
    """How the seed term was originated."""

    CONSULTANT_PROVIDED = "consultant_provided"
    NLP_DISCOVERED = "nlp_discovered"
    EVIDENCE_EXTRACTED = "evidence_extracted"


class TermStatus(enum.StrEnum):
    """Lifecycle status of a seed term."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    MERGED = "merged"


class SeedTerm(Base):
    """A domain vocabulary entry scoped to an engagement.

    Seed terms are the foundational building blocks of the seed list pipeline.
    They drive survey probe generation, focus evidence extraction, and enable
    entity resolution across heterogeneous sources.
    """

    __tablename__ = "seed_terms"
    __table_args__ = (
        UniqueConstraint("engagement_id", "term", "domain", name="uq_seed_terms_engagement_term_domain"),
        Index("ix_seed_terms_engagement_id", "engagement_id"),
        Index("ix_seed_terms_engagement_status", "engagement_id", "status"),
        Index("ix_seed_terms_merged_into", "merged_into"),
        Index(
            "ix_seed_terms_term_fts",
            text("to_tsvector('english', term)"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    term: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[TermCategory] = mapped_column(
        Enum(TermCategory, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    source: Mapped[TermSource] = mapped_column(
        Enum(TermSource, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    status: Mapped[TermStatus] = mapped_column(
        Enum(TermStatus, values_callable=lambda e: [x.value for x in e]),
        default=TermStatus.ACTIVE,
        nullable=False,
    )
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seed_terms.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SeedTerm(id={self.id}, term={self.term!r}, category={self.category}, status={self.status})>"

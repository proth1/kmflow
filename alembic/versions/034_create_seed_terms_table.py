"""Create seed_terms table.

Adds the SeedTerm table for domain vocabulary store per PRD v2.1
Section 6.10.3 (Seed List Pipeline).

Revision ID: 034
Revises: 033
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "034"
down_revision: str | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TERM_CATEGORY = sa.Enum(
    "activity",
    "system",
    "role",
    "regulation",
    "artifact",
    name="termcategory",
)
_TERM_SOURCE = sa.Enum(
    "consultant_provided",
    "nlp_discovered",
    "evidence_extracted",
    name="termsource",
)
_TERM_STATUS = sa.Enum(
    "active",
    "deprecated",
    "merged",
    name="termstatus",
)


def upgrade() -> None:
    _TERM_CATEGORY.create(op.get_bind(), checkfirst=True)
    _TERM_SOURCE.create(op.get_bind(), checkfirst=True)
    _TERM_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "seed_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(200), nullable=False),
        sa.Column("category", _TERM_CATEGORY, nullable=False),
        sa.Column("source", _TERM_SOURCE, nullable=False),
        sa.Column("status", _TERM_STATUS, nullable=False, server_default="active"),
        sa.Column(
            "merged_into", UUID(as_uuid=True), sa.ForeignKey("seed_terms.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "term", "domain", name="uq_seed_terms_engagement_term_domain"),
    )
    op.create_index("ix_seed_terms_engagement_id", "seed_terms", ["engagement_id"])
    op.create_index("ix_seed_terms_engagement_status", "seed_terms", ["engagement_id", "status"])
    op.create_index("ix_seed_terms_merged_into", "seed_terms", ["merged_into"])
    op.execute("CREATE INDEX ix_seed_terms_term_fts ON seed_terms USING gin (to_tsvector('english', term))")


def downgrade() -> None:
    op.drop_table("seed_terms")
    _TERM_STATUS.drop(op.get_bind(), checkfirst=True)
    _TERM_SOURCE.drop(op.get_bind(), checkfirst=True)
    _TERM_CATEGORY.drop(op.get_bind(), checkfirst=True)

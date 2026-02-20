"""Add engagement_id to alternative_suggestions for GDPR deletion-by-engagement.

Enables direct bulk deletion of LLM interaction records by engagement
without requiring a join through simulation_scenarios.

Revision ID: 019
Revises: 018
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alternative_suggestions",
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=True,  # Nullable for backfill; can tighten later
        ),
    )
    op.create_index(
        "ix_alternative_suggestions_engagement_id",
        "alternative_suggestions",
        ["engagement_id"],
    )
    # Backfill from scenario -> engagement
    op.execute(
        """
        UPDATE alternative_suggestions AS s
        SET engagement_id = sc.engagement_id
        FROM simulation_scenarios AS sc
        WHERE s.scenario_id = sc.id
        AND s.engagement_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_alternative_suggestions_engagement_id")
    op.drop_column("alternative_suggestions", "engagement_id")

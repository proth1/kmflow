"""Add uplift_projections table for evidence gap ranking.

Revision ID: 057
Revises: 056
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uplift_projections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("element_id", sa.String(512), nullable=False),
        sa.Column("element_name", sa.String(512), nullable=False),
        sa.Column("evidence_type", sa.String(255), nullable=False),
        sa.Column("current_confidence", sa.Float, nullable=False),
        sa.Column("projected_confidence", sa.Float, nullable=False),
        sa.Column("projected_uplift", sa.Float, nullable=False),
        sa.Column("actual_uplift", sa.Float, nullable=True),
        sa.Column("brightness", sa.String(50), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_uplift_projections_engagement_id", "uplift_projections", ["engagement_id"])
    op.create_index("ix_uplift_projections_element_id", "uplift_projections", ["element_id"])


def downgrade() -> None:
    op.drop_index("ix_uplift_projections_element_id", table_name="uplift_projections")
    op.drop_index("ix_uplift_projections_engagement_id", table_name="uplift_projections")
    op.drop_table("uplift_projections")

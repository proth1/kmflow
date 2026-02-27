"""Add control_effectiveness_scores table.

Revision ID: 054
Revises: 053
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_effectiveness_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "control_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("controls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "effectiveness",
            sa.Enum(
                "highly_effective",
                "effective",
                "moderately_effective",
                "ineffective",
                name="controleffectiveness",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("execution_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("evidence_source_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scored_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_control_effectiveness_scores_control_id", "control_effectiveness_scores", ["control_id"]
    )
    op.create_index(
        "ix_control_effectiveness_scores_engagement_id", "control_effectiveness_scores", ["engagement_id"]
    )
    op.create_index(
        "ix_control_effectiveness_scores_scored_at", "control_effectiveness_scores", ["scored_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_control_effectiveness_scores_scored_at", table_name="control_effectiveness_scores")
    op.drop_index("ix_control_effectiveness_scores_engagement_id", table_name="control_effectiveness_scores")
    op.drop_index("ix_control_effectiveness_scores_control_id", table_name="control_effectiveness_scores")
    op.drop_table("control_effectiveness_scores")

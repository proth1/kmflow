"""Create grading_snapshots table for evidence grade progression tracking.

Revision ID: 072
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grading_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pov_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("grade_u", sa.Integer, server_default="0", nullable=False),
        sa.Column("grade_d", sa.Integer, server_default="0", nullable=False),
        sa.Column("grade_c", sa.Integer, server_default="0", nullable=False),
        sa.Column("grade_b", sa.Integer, server_default="0", nullable=False),
        sa.Column("grade_a", sa.Integer, server_default="0", nullable=False),
        sa.Column("total_elements", sa.Integer, server_default="0", nullable=False),
        sa.Column("improvement_pct", sa.Float, nullable=True),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_grading_snapshots_engagement_id",
        "grading_snapshots",
        ["engagement_id"],
    )
    op.create_index(
        "ix_grading_snapshots_pov_version_id",
        "grading_snapshots",
        ["pov_version_id"],
    )
    op.create_unique_constraint(
        "uq_grading_snapshots_engagement_version",
        "grading_snapshots",
        ["engagement_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_table("grading_snapshots")

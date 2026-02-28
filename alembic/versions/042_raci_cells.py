"""Create raci_cells table for Story #351.

Stores auto-derived RACI matrix cells with activity-role assignments,
SME validation tracking, and engagement scoping.

Revision ID: 042
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raci_cells",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", sa.String(255), nullable=False),
        sa.Column("activity_name", sa.String(512), nullable=False),
        sa.Column("role_id", sa.String(255), nullable=False),
        sa.Column("role_name", sa.String(512), nullable=False),
        sa.Column("assignment", sa.String(1), nullable=False),
        sa.Column("status", sa.String(20), server_default="proposed", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("source_edge_type", sa.String(50), nullable=True),
        sa.Column("validator_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "activity_id", "role_id", name="uq_raci_cell"),
    )
    op.create_index("ix_raci_cells_engagement_id", "raci_cells", ["engagement_id"])
    op.create_index("ix_raci_cells_activity_id", "raci_cells", ["activity_id"])


def downgrade() -> None:
    op.drop_index("ix_raci_cells_activity_id", table_name="raci_cells")
    op.drop_index("ix_raci_cells_engagement_id", table_name="raci_cells")
    op.drop_table("raci_cells")

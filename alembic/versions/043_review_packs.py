"""Create review_packs table for Story #349.

Stores segmented review packs with activity groups, evidence,
confidence scores, conflict flags, and SME routing.

Revision ID: 043
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_packs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pov_version_id", sa.UUID(), sa.ForeignKey("process_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("segment_activities", sa.JSON(), nullable=False),
        sa.Column("activity_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evidence_list", sa.JSON(), nullable=True),
        sa.Column("confidence_scores", sa.JSON(), nullable=True),
        sa.Column("conflict_flags", sa.JSON(), nullable=True),
        sa.Column("seed_terms", sa.JSON(), nullable=True),
        sa.Column("process_fragment_bpmn", sa.Text(), nullable=True),
        sa.Column("assigned_sme_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_role", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("avg_confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("task_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_review_packs_engagement_id", "review_packs", ["engagement_id"])
    op.create_index("ix_review_packs_pov_version_id", "review_packs", ["pov_version_id"])
    op.create_index("ix_review_packs_assigned_sme_id", "review_packs", ["assigned_sme_id"])


def downgrade() -> None:
    op.drop_index("ix_review_packs_assigned_sme_id", table_name="review_packs")
    op.drop_index("ix_review_packs_pov_version_id", table_name="review_packs")
    op.drop_index("ix_review_packs_engagement_id", table_name="review_packs")
    op.drop_table("review_packs")

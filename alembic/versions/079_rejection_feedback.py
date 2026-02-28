"""Add rejection_feedback table for LLM suggestion feedback loop.

Revision ID: 079
Revises: 078
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rejection_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_pattern_summary", sa.Text(), nullable=False),
        sa.Column("rejected_suggestion_ids", JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rejection_feedback_engagement_id", "rejection_feedback", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_rejection_feedback_engagement_id")
    op.drop_table("rejection_feedback")

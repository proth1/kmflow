"""Create validation_decisions table.

Revision ID: 071
Create Date: 2026-02-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_pack_id",
            UUID(as_uuid=True),
            sa.ForeignKey("review_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("element_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "reviewer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", JSON, nullable=True),
        sa.Column("graph_write_back_result", JSON, nullable=True),
        sa.Column(
            "decision_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_validation_decisions_review_pack_id",
        "validation_decisions",
        ["review_pack_id"],
    )
    op.create_index(
        "ix_validation_decisions_engagement_id",
        "validation_decisions",
        ["engagement_id"],
    )
    op.create_index(
        "ix_validation_decisions_reviewer_id",
        "validation_decisions",
        ["reviewer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_validation_decisions_reviewer_id", "validation_decisions")
    op.drop_index("ix_validation_decisions_engagement_id", "validation_decisions")
    op.drop_index("ix_validation_decisions_review_pack_id", "validation_decisions")
    op.drop_table("validation_decisions")

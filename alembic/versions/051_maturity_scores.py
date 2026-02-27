"""Create maturity_scores table.

Revision ID: 051
Revises: 050
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maturity_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "process_model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "maturity_level",
            sa.Enum(
                "initial",
                "managed",
                "defined",
                "quantitatively_managed",
                "optimizing",
                name="processmaturity",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("level_number", sa.Integer, nullable=False),
        sa.Column("evidence_dimensions", sa.JSON, nullable=True),
        sa.Column("recommendations", sa.JSON, nullable=True),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_maturity_scores_engagement_id",
        "maturity_scores",
        ["engagement_id"],
    )
    op.create_index(
        "ix_maturity_scores_process_model_id",
        "maturity_scores",
        ["process_model_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_maturity_scores_process_model_id", table_name="maturity_scores")
    op.drop_index("ix_maturity_scores_engagement_id", table_name="maturity_scores")
    op.drop_table("maturity_scores")

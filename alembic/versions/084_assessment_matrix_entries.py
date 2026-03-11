"""Create assessment_matrix_entries table.

Revision ID: 084_assessment_matrix
Revises: 083_abac_policy_bundles_obligations
Create Date: 2026-03-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_matrix_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("process_area_name", sa.String(512), nullable=False),
        sa.Column("process_area_description", sa.Text(), nullable=True),
        sa.Column("ability_to_execute", sa.Float(), nullable=False),
        sa.Column("ability_components", postgresql.JSON(), nullable=True),
        sa.Column("value_score", sa.Float(), nullable=False),
        sa.Column("value_components", postgresql.JSON(), nullable=True),
        sa.Column(
            "quadrant",
            sa.Enum("transform", "invest", "maintain", "deprioritize", name="quadrant"),
            nullable=False,
        ),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assessment_matrix_entries_engagement_id",
        "assessment_matrix_entries",
        ["engagement_id"],
    )
    op.create_unique_constraint(
        "uq_assessment_matrix_area",
        "assessment_matrix_entries",
        ["engagement_id", "process_area_name"],
    )


def downgrade() -> None:
    op.drop_table("assessment_matrix_entries")
    op.execute("DROP TYPE IF EXISTS quadrant")

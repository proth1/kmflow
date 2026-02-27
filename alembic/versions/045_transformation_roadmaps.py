"""Add transformation_roadmaps table and gap_analysis_results columns.

Revision ID: 045
Revises: 044
Create Date: 2026-02-27

Story #368: Gap-Prioritized Transformation Roadmap Generator
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to gap_analysis_results
    op.add_column(
        "gap_analysis_results",
        sa.Column("remediation_cost", sa.Integer(), nullable=True),
    )
    op.add_column(
        "gap_analysis_results",
        sa.Column("depends_on_ids", JSON(), nullable=True),
    )

    # Create transformation_roadmaps table
    op.create_table(
        "transformation_roadmaps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "final", name="roadmapstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("phases", JSON(), nullable=True),
        sa.Column("total_initiatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_duration_weeks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index(
        "ix_transformation_roadmaps_engagement_id",
        "transformation_roadmaps",
        ["engagement_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transformation_roadmaps_engagement_id", table_name="transformation_roadmaps")
    op.drop_table("transformation_roadmaps")
    op.execute("DROP TYPE IF EXISTS roadmapstatus")
    op.drop_column("gap_analysis_results", "depends_on_ids")
    op.drop_column("gap_analysis_results", "remediation_cost")

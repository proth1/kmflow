"""Create TOM (Target Operating Model) tables.

Tables: target_operating_models, gap_analysis_results, best_practices, benchmarks.

Revision ID: 008
Revises: 007
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Create target_operating_models table --
    op.create_table(
        "target_operating_models",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=True),
        sa.Column("maturity_targets", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_tom_engagement_id", "target_operating_models", ["engagement_id"])

    # -- Create gap_analysis_results table --
    op.create_table(
        "gap_analysis_results",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tom_id",
            sa.UUID(),
            sa.ForeignKey("target_operating_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gap_type",
            sa.Enum(
                "full_gap", "partial_gap", "deviation", "no_gap",
                name="tomgaptype", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "dimension",
            sa.Enum(
                "process_architecture", "people_and_organization",
                "technology_and_data", "governance_structures",
                "performance_management", "risk_and_compliance",
                name="tomdimension", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("severity", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_gap_results_engagement_id", "gap_analysis_results", ["engagement_id"])
    op.create_index("ix_gap_results_tom_id", "gap_analysis_results", ["tom_id"])

    # -- Create best_practices table --
    op.create_table(
        "best_practices",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(512), nullable=True),
        sa.Column(
            "tom_dimension",
            sa.Enum(
                "process_architecture", "people_and_organization",
                "technology_and_data", "governance_structures",
                "performance_management", "risk_and_compliance",
                name="tomdimension", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )

    # -- Create benchmarks table --
    op.create_table(
        "benchmarks",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(255), nullable=False),
        sa.Column("p25", sa.Float(), nullable=False),
        sa.Column("p50", sa.Float(), nullable=False),
        sa.Column("p75", sa.Float(), nullable=False),
        sa.Column("p90", sa.Float(), nullable=False),
        sa.Column("source", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("benchmarks")
    op.drop_table("best_practices")
    op.drop_table("gap_analysis_results")
    op.drop_table("target_operating_models")

    op.execute("DROP TYPE IF EXISTS processmaturity")
    op.execute("DROP TYPE IF EXISTS tomgaptype")
    op.execute("DROP TYPE IF EXISTS tomdimension")

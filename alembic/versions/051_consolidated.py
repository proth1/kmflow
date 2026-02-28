"""Consolidated: governance soft-delete, maturity scores, TOM alignment runs/results.

Merges three 051 migrations that were created concurrently with the same
revision ID.  Combined into a single migration to eliminate the duplicate-head
problem.

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
    # --- governance soft-delete columns ---
    op.add_column("policies", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("controls", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("regulations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # --- maturity_scores table ---
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
    op.create_index("ix_maturity_scores_engagement_id", "maturity_scores", ["engagement_id"])
    op.create_index("ix_maturity_scores_process_model_id", "maturity_scores", ["process_model_id"])

    # --- tom_alignment_runs table ---
    op.create_table(
        "tom_alignment_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tom_id",
            UUID(as_uuid=True),
            sa.ForeignKey("target_operating_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "complete", "failed",
                name="alignmentrunstatus",
                create_type=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tom_alignment_runs_engagement_id", "tom_alignment_runs", ["engagement_id"])
    op.create_index("ix_tom_alignment_runs_tom_id", "tom_alignment_runs", ["tom_id"])

    # --- tom_alignment_results table ---
    op.create_table(
        "tom_alignment_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tom_alignment_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "dimension_type",
            sa.Enum(
                "process_architecture",
                "people_and_organization",
                "technology_and_data",
                "governance_structures",
                "performance_management",
                "risk_and_compliance",
                name="tomdimension",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "gap_type",
            sa.Enum(
                "full_gap", "partial_gap", "deviation", "no_gap",
                name="tomgaptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("deviation_score", sa.Float(), nullable=False),
        sa.Column("alignment_evidence", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tom_alignment_results_run_id", "tom_alignment_results", ["run_id"])
    op.create_index("ix_tom_alignment_results_activity_id", "tom_alignment_results", ["activity_id"])


def downgrade() -> None:
    # tom_alignment_results
    op.drop_index("ix_tom_alignment_results_activity_id", table_name="tom_alignment_results")
    op.drop_index("ix_tom_alignment_results_run_id", table_name="tom_alignment_results")
    op.drop_table("tom_alignment_results")
    # tom_alignment_runs
    op.drop_index("ix_tom_alignment_runs_tom_id", table_name="tom_alignment_runs")
    op.drop_index("ix_tom_alignment_runs_engagement_id", table_name="tom_alignment_runs")
    op.drop_table("tom_alignment_runs")
    # maturity_scores
    op.drop_index("ix_maturity_scores_process_model_id", table_name="maturity_scores")
    op.drop_index("ix_maturity_scores_engagement_id", table_name="maturity_scores")
    op.drop_table("maturity_scores")
    # governance soft-delete
    op.drop_column("regulations", "deleted_at")
    op.drop_column("controls", "deleted_at")
    op.drop_column("policies", "deleted_at")

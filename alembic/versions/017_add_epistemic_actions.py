"""Add epistemic_actions table for Phase 3.2.

Creates epistemic_actions table and extends auditaction enum.

Revision ID: 017
Revises: 016
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "epistemic_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("simulation_scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_element_id", sa.String(512), nullable=False),
        sa.Column("target_element_name", sa.String(512), nullable=False),
        sa.Column("evidence_gap_description", sa.Text, nullable=False),
        sa.Column("current_confidence", sa.Float, nullable=False),
        sa.Column("estimated_confidence_uplift", sa.Float, nullable=False),
        sa.Column("projected_confidence", sa.Float, nullable=False),
        sa.Column("information_gain_score", sa.Float, nullable=False),
        sa.Column("recommended_evidence_category", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column(
            "shelf_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shelf_data_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_epistemic_actions_scenario_id",
        "epistemic_actions",
        ["scenario_id"],
    )

    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'epistemic_plan_generated'")


def downgrade() -> None:
    op.drop_index("ix_epistemic_actions_scenario_id")
    op.drop_table("epistemic_actions")

"""Add scenario workbench tables for Phase 3.1.

Creates scenario_modifications table, modificationtype enum,
and adds status/evidence_confidence_score to simulation_scenarios.

Revision ID: 016
Revises: 015
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create modificationtype enum
    modificationtype_enum = sa.Enum(
        "task_add",
        "task_remove",
        "task_modify",
        "role_reassign",
        "gateway_restructure",
        "control_add",
        "control_remove",
        name="modificationtype",
    )
    modificationtype_enum.create(op.get_bind(), checkfirst=True)

    # Extend simulation_scenarios with status and evidence_confidence_score
    op.add_column(
        "simulation_scenarios",
        sa.Column("status", sa.String(50), nullable=True, server_default="draft"),
    )
    op.add_column(
        "simulation_scenarios",
        sa.Column("evidence_confidence_score", sa.Float, nullable=True),
    )

    # Create scenario_modifications table
    op.create_table(
        "scenario_modifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("simulation_scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("modification_type", modificationtype_enum, nullable=False),
        sa.Column("element_id", sa.String(512), nullable=False),
        sa.Column("element_name", sa.String(512), nullable=False),
        sa.Column("change_data", sa.dialects.postgresql.JSON, nullable=True),
        sa.Column("template_key", sa.String(100), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_scenario_modifications_scenario_id",
        "scenario_modifications",
        ["scenario_id"],
    )

    # Extend auditaction enum with new values
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'scenario_modified'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'scenario_compared'")


def downgrade() -> None:
    op.drop_index("ix_scenario_modifications_scenario_id")
    op.drop_table("scenario_modifications")
    op.drop_column("simulation_scenarios", "evidence_confidence_score")
    op.drop_column("simulation_scenarios", "status")
    sa.Enum(name="modificationtype").drop(op.get_bind(), checkfirst=True)

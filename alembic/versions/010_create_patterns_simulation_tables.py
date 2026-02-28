"""Create pattern library and simulation tables.

Tables: pattern_library_entries, pattern_access_rules,
        simulation_scenarios, simulation_results.

Revision ID: 010
Revises: 009
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- pattern_library_entries --
    op.create_table(
        "pattern_library_entries",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.Enum("process_optimization", "control_improvement", "technology_enablement", "organizational_change", "risk_mitigation", name="patterncategory", create_type=True), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("anonymized_data", sa.JSON(), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),  # pgvector would be better
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effectiveness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # -- pattern_access_rules --
    op.create_table(
        "pattern_access_rules",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("pattern_id", sa.UUID(), sa.ForeignKey("pattern_library_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pattern_id", "engagement_id", name="uq_pattern_engagement"),
    )

    # -- simulation_scenarios --
    op.create_table(
        "simulation_scenarios",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("process_model_id", sa.UUID(), sa.ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("simulation_type", sa.Enum("what_if", "capacity", "process_change", "control_removal", name="simulationtype", create_type=True), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_simulation_scenarios_engagement_id", "simulation_scenarios", ["engagement_id"])

    # -- simulation_results --
    op.create_table(
        "simulation_results",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scenario_id", sa.UUID(), sa.ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", name="simulationstatus", create_type=True), nullable=False, server_default="pending"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("impact_analysis", sa.JSON(), nullable=True),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_simulation_results_scenario_id", "simulation_results", ["scenario_id"])


def downgrade() -> None:
    op.drop_table("simulation_results")
    op.drop_table("simulation_scenarios")
    op.drop_table("pattern_access_rules")
    op.drop_table("pattern_library_entries")

    op.execute("DROP TYPE IF EXISTS patterncategory")
    op.execute("DROP TYPE IF EXISTS simulationtype")
    op.execute("DROP TYPE IF EXISTS simulationstatus")

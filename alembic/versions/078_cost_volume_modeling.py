"""Add role rate assumptions and volume forecasts for cost modeling.

Revision ID: 078
Revises: 077
Create Date: 2026-02-27

Story #359: Cost-per-role and volume forecast modeling.

Creates RoleRateAssumption and VolumeForecast tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_rate_assumptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_name", sa.String(256), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("annual_rate", sa.Float(), nullable=True),
        sa.Column("rate_variance_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_role_rate_assumptions_engagement_id", "role_rate_assumptions", ["engagement_id"])
    op.create_unique_constraint(
        "uq_role_rate_engagement_role", "role_rate_assumptions", ["engagement_id", "role_name"]
    )

    op.create_table(
        "volume_forecasts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("baseline_volume", sa.Integer(), nullable=False),
        sa.Column("variance_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("seasonal_factors", sa.dialects.postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_volume_forecasts_engagement_id", "volume_forecasts", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_volume_forecasts_engagement_id", "volume_forecasts")
    op.drop_table("volume_forecasts")
    op.drop_constraint("uq_role_rate_engagement_role", "role_rate_assumptions", type_="unique")
    op.drop_index("ix_role_rate_assumptions_engagement_id", "role_rate_assumptions")
    op.drop_table("role_rate_assumptions")

"""Create dark_room_snapshots table for Story #370.

Tracks per-version dark/dim/bright segment counts for the
Dark-Room Shrink Rate KPI dashboard.

Revision ID: 044
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dark_room_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pov_version_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("dark_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("dim_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("bright_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("total_elements", sa.Integer, server_default="0", nullable=False),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_dark_room_snapshots_engagement_id",
        "dark_room_snapshots",
        ["engagement_id"],
    )
    op.create_index(
        "ix_dark_room_snapshots_pov_version_id",
        "dark_room_snapshots",
        ["pov_version_id"],
    )
    op.create_unique_constraint(
        "uq_dark_room_snapshots_engagement_version",
        "dark_room_snapshots",
        ["engagement_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_dark_room_snapshots_engagement_version", "dark_room_snapshots")
    op.drop_index("ix_dark_room_snapshots_pov_version_id", "dark_room_snapshots")
    op.drop_index("ix_dark_room_snapshots_engagement_id", "dark_room_snapshots")
    op.drop_table("dark_room_snapshots")

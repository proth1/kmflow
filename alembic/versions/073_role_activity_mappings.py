"""Create role_activity_mappings table.

Revision ID: 073
Revises: 072
Create Date: 2026-02-27

Story #365: Role-activity mapping for reviewer routing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_activity_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_name", sa.String(255), nullable=False),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_role_activity_mappings_engagement_id", "role_activity_mappings", ["engagement_id"])
    op.create_index("ix_role_activity_mappings_role_name", "role_activity_mappings", ["role_name"])


def downgrade() -> None:
    op.drop_index("ix_role_activity_mappings_role_name", table_name="role_activity_mappings")
    op.drop_index("ix_role_activity_mappings_engagement_id", table_name="role_activity_mappings")
    op.drop_table("role_activity_mappings")

"""Add illumination_actions table for evidence acquisition planning.

Revision ID: 058
Revises: 057
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "illumination_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("element_id", sa.String(512), nullable=False),
        sa.Column("element_name", sa.String(512), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("target_knowledge_form", sa.Integer, nullable=False),
        sa.Column("target_form_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("linked_item_id", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_illumination_actions_engagement_id", "illumination_actions", ["engagement_id"])
    op.create_index("ix_illumination_actions_element_id", "illumination_actions", ["element_id"])


def downgrade() -> None:
    op.drop_index("ix_illumination_actions_element_id", table_name="illumination_actions")
    op.drop_index("ix_illumination_actions_engagement_id", table_name="illumination_actions")
    op.drop_table("illumination_actions")

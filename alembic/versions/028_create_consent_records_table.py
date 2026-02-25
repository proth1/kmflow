"""Create consent_records table.

Revision ID: 028
Revises: 027
Create Date: 2026-02-25

Creates the consent_records table for tracking per-agent consent grants
and revocations (Story #213, Epic #210 Privacy and Compliance).
"""

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(50), nullable=False),
        sa.Column("capture_mode", sa.String(50), nullable=False, server_default="action_level"),
        sa.Column("user_acknowledged", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "consented_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_consent_records_agent_id", "consent_records", ["agent_id"])
    op.create_index("ix_consent_records_engagement_id", "consent_records", ["engagement_id"])


def downgrade() -> None:
    op.drop_table("consent_records")

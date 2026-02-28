"""Create survey_sessions table.

Revision ID: 070
Revises: 069
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("respondent_role", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "abandoned", name="surveysessionstatus", create_type=True),
            nullable=False,
            server_default="active",
        ),
        sa.Column("claims_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("summary", sa.dialects.postgresql.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_survey_sessions_engagement_id", "survey_sessions", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_survey_sessions_engagement_id")
    op.drop_table("survey_sessions")
    op.execute("DROP TYPE IF EXISTS surveysessionstatus")

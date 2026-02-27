"""Add gap_findings table for governance gap detection.

Revision ID: 055
Revises: 050
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "055"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute(
        "CREATE TYPE governancegaptype AS ENUM ('control_gap')"
    )
    op.execute(
        "CREATE TYPE governancegapseverity AS ENUM ('critical', 'high', 'medium', 'low')"
    )
    op.execute(
        "CREATE TYPE governancegapstatus AS ENUM ('open', 'resolved')"
    )

    op.create_table(
        "gap_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("process_elements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "regulation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "gap_type",
            sa.Enum("control_gap", name="governancegaptype", create_type=False),
            nullable=False,
            server_default="control_gap",
        ),
        sa.Column(
            "severity",
            sa.Enum("critical", "high", "medium", "low", name="governancegapseverity", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "resolved", name="governancegapstatus", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gap_findings_engagement_id", "gap_findings", ["engagement_id"])
    op.create_index("ix_gap_findings_activity_id", "gap_findings", ["activity_id"])
    op.create_index("ix_gap_findings_status", "gap_findings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_gap_findings_status", table_name="gap_findings")
    op.drop_index("ix_gap_findings_activity_id", table_name="gap_findings")
    op.drop_index("ix_gap_findings_engagement_id", table_name="gap_findings")
    op.drop_table("gap_findings")
    op.execute("DROP TYPE IF EXISTS governancegapstatus")
    op.execute("DROP TYPE IF EXISTS governancegapseverity")
    op.execute("DROP TYPE IF EXISTS governancegaptype")

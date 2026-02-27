"""Add hallucination flagging columns to llm_audit_logs.

Revision ID: 064
Revises: 063
Create Date: 2026-02-27

Story #386: Full Audit Trail for LLM Interactions — adds hallucination
flagging, reason, timestamp, and flagging user columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit_logs",
        sa.Column("hallucination_flagged", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "llm_audit_logs",
        sa.Column("hallucination_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "llm_audit_logs",
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "llm_audit_logs",
        sa.Column(
            "flagged_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_llm_audit_logs_hallucination_flagged",
        "llm_audit_logs",
        ["hallucination_flagged"],
        postgresql_where=sa.text("hallucination_flagged = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_llm_audit_logs_hallucination_flagged", table_name="llm_audit_logs")
    op.drop_column("llm_audit_logs", "flagged_by_user_id")
    op.drop_column("llm_audit_logs", "flagged_at")
    op.drop_column("llm_audit_logs", "hallucination_reason")
    op.drop_column("llm_audit_logs", "hallucination_flagged")

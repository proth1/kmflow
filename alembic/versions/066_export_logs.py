"""Add export_logs table for watermarked document tracking.

Revision ID: 066
Revises: 065
Create Date: 2026-02-27

Story #387: Export Watermarking with Recipient Tracking — append-only
log of watermarked document exports for forensic tracking.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "exported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_export_logs_engagement_id",
        "export_logs",
        ["engagement_id"],
    )
    op.create_index(
        "ix_export_logs_recipient_id",
        "export_logs",
        ["recipient_id"],
    )

    # Append-only policy: prevent UPDATE and DELETE via trigger.
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_export_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'export_logs is append-only: UPDATE and DELETE are prohibited';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_export_logs_no_update
        BEFORE UPDATE ON export_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_export_log_mutation();
    """)
    op.execute("""
        CREATE TRIGGER trg_export_logs_no_delete
        BEFORE DELETE ON export_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_export_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_export_logs_no_delete ON export_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_export_logs_no_update ON export_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_export_log_mutation();")
    op.drop_index("ix_export_logs_recipient_id", table_name="export_logs")
    op.drop_index("ix_export_logs_engagement_id", table_name="export_logs")
    op.drop_table("export_logs")

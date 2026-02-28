"""Add audit log enhancements: new columns, composite index, append-only trigger.

Revision ID: 040
Revises: 039
Create Date: 2026-02-27

Story #314: Audit Logging Middleware
- Adds user_id, resource_type, resource_id, before_value, after_value,
  ip_address, user_agent, result_status columns to audit_logs
- Creates composite index on (user_id, created_at DESC)
- Creates append-only trigger to prevent UPDATE/DELETE on audit_logs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "040"
down_revision: str | None = "039"
branch_labels: str | None = None
depends_on: str | None = None

TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log entries are append-only and cannot be modified or deleted';
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_SQL = """
CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_modification();
"""


def upgrade() -> None:
    # Add new columns
    op.add_column("audit_logs", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("audit_logs", sa.Column("resource_type", sa.String(255), nullable=True))
    op.add_column("audit_logs", sa.Column("resource_id", UUID(as_uuid=True), nullable=True))
    op.add_column("audit_logs", sa.Column("before_value", JSONB, nullable=True))
    op.add_column("audit_logs", sa.Column("after_value", JSONB, nullable=True))
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(45), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(512), nullable=True))
    op.add_column("audit_logs", sa.Column("result_status", sa.Integer(), nullable=True))

    # Composite index for querying by user + time range
    op.create_index(
        "ix_audit_logs_user_id_created_at",
        "audit_logs",
        ["user_id", sa.text("created_at DESC")],
    )

    # Append-only trigger: prevent UPDATE/DELETE
    op.execute(TRIGGER_FUNCTION_SQL)
    op.execute(TRIGGER_SQL)


def downgrade() -> None:
    # Remove trigger and function
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification();")

    # Remove index
    op.drop_index("ix_audit_logs_user_id_created_at", table_name="audit_logs")

    # Remove columns
    op.drop_column("audit_logs", "result_status")
    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "after_value")
    op.drop_column("audit_logs", "before_value")
    op.drop_column("audit_logs", "resource_id")
    op.drop_column("audit_logs", "resource_type")
    op.drop_column("audit_logs", "user_id")

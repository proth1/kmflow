"""Change AuditLog engagement FK from CASCADE to SET NULL.

Revision ID: 025
Revises: 024
Create Date: 2026-02-20

Preserves audit logs when an engagement is deleted by setting engagement_id
to NULL instead of cascading the delete. Audit immutability is a compliance
requirement — deleting an engagement should not erase its audit trail.

Changes:
- audit_logs.engagement_id: nullable=False -> nullable=True
- audit_logs.engagement_id FK: ondelete CASCADE -> ondelete SET NULL
"""

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # Make column nullable first
    op.alter_column(
        "audit_logs",
        "engagement_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )

    # Drop old FK constraint and recreate with SET NULL
    op.drop_constraint(
        "audit_logs_engagement_id_fkey",
        "audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audit_logs_engagement_id_fkey",
        "audit_logs",
        "engagements",
        ["engagement_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Revert FK to CASCADE
    op.drop_constraint(
        "audit_logs_engagement_id_fkey",
        "audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audit_logs_engagement_id_fkey",
        "audit_logs",
        "engagements",
        ["engagement_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Note: any rows with NULL engagement_id must be handled before
    # making the column non-nullable again. Delete orphaned rows.
    op.execute("DELETE FROM audit_logs WHERE engagement_id IS NULL")

    op.alter_column(
        "audit_logs",
        "engagement_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )

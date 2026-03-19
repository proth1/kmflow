"""Add forensic columns to http_audit_events and index to pdp_audit_entries.

Revision ID: 088
Revises: 087
Create Date: 2026-03-19
"""

import sqlalchemy as sa
from alembic import op

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add forensic columns to http_audit_events
    op.add_column("http_audit_events", sa.Column("ip_address", sa.String(45), nullable=True))
    op.add_column("http_audit_events", sa.Column("user_agent", sa.String(512), nullable=True))
    op.add_column("http_audit_events", sa.Column("resource_type", sa.String(100), nullable=True))

    # Add index on pdp_audit_entries.policy_id for query performance
    op.create_index("ix_pdp_audit_entries_policy_id", "pdp_audit_entries", ["policy_id"])


def downgrade() -> None:
    op.drop_index("ix_pdp_audit_entries_policy_id", table_name="pdp_audit_entries")
    op.drop_column("http_audit_events", "resource_type")
    op.drop_column("http_audit_events", "user_agent")
    op.drop_column("http_audit_events", "ip_address")

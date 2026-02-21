"""Add created_at index on copilot_messages for retention cleanup.

Revision ID: 024
Revises: 023
Create Date: 2026-02-20

Changes:
- copilot_messages: add index on created_at for efficient retention queries
"""

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.create_index(
        "ix_copilot_messages_created_at",
        "copilot_messages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_messages_created_at", table_name="copilot_messages")

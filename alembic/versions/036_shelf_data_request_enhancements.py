"""Enhance shelf data request models with BDD-aligned statuses and follow-up reminders.

Adds new enum values to shelf request/item status, new columns for
assigned_to, completion_timestamp, received_at, uploaded_by, and
creates the follow_up_reminders table.

Revision ID: 036
Revises: 035
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "036"
down_revision: str | None = "035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new enum values to shelfrequeststatus
    op.execute("ALTER TYPE shelfrequeststatus ADD VALUE IF NOT EXISTS 'open'")
    op.execute("ALTER TYPE shelfrequeststatus ADD VALUE IF NOT EXISTS 'complete'")
    op.execute("ALTER TYPE shelfrequeststatus ADD VALUE IF NOT EXISTS 'cancelled'")

    # Add new enum values to shelfrequestitemstatus
    op.execute("ALTER TYPE shelfrequestitemstatus ADD VALUE IF NOT EXISTS 'requested'")
    op.execute("ALTER TYPE shelfrequestitemstatus ADD VALUE IF NOT EXISTS 'validated'")
    op.execute("ALTER TYPE shelfrequestitemstatus ADD VALUE IF NOT EXISTS 'active'")

    # Add columns to shelf_data_requests
    op.add_column("shelf_data_requests", sa.Column("assigned_to", sa.String(255), nullable=True))
    op.add_column(
        "shelf_data_requests",
        sa.Column("completion_timestamp", sa.DateTime(timezone=True), nullable=True),
    )

    # Add columns to shelf_data_request_items
    op.add_column(
        "shelf_data_request_items",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shelf_data_request_items",
        sa.Column("uploaded_by", sa.String(255), nullable=True),
    )

    # Create follow_up_reminders table
    op.create_table(
        "follow_up_reminders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shelf_data_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shelf_data_request_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reminder_type", sa.String(50), nullable=False, server_default="overdue"),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_follow_up_reminders_request_id", "follow_up_reminders", ["request_id"])
    op.create_index("ix_follow_up_reminders_item_id", "follow_up_reminders", ["item_id"])


def downgrade() -> None:
    op.drop_table("follow_up_reminders")
    op.drop_column("shelf_data_request_items", "uploaded_by")
    op.drop_column("shelf_data_request_items", "received_at")
    op.drop_column("shelf_data_requests", "completion_timestamp")
    op.drop_column("shelf_data_requests", "assigned_to")
    # Note: Cannot remove enum values in PostgreSQL without recreating the type

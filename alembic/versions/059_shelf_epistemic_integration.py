"""Add epistemic_action_id and source to shelf_data_request_items.

Revision ID: 059
Revises: 058
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shelf_data_request_items",
        sa.Column(
            "epistemic_action_id",
            UUID(as_uuid=True),
            sa.ForeignKey("epistemic_actions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "shelf_data_request_items",
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
    )
    op.create_index(
        "ix_shelf_request_items_epistemic_action_id",
        "shelf_data_request_items",
        ["epistemic_action_id"],
    )
    op.create_index(
        "ix_shelf_request_items_source",
        "shelf_data_request_items",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("ix_shelf_request_items_source", table_name="shelf_data_request_items")
    op.drop_index("ix_shelf_request_items_epistemic_action_id", table_name="shelf_data_request_items")
    op.drop_column("shelf_data_request_items", "source")
    op.drop_column("shelf_data_request_items", "epistemic_action_id")

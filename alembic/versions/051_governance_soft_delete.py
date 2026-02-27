"""Add deleted_at columns for soft-delete on policies, controls, and regulations.

Revision ID: 051
Revises: 050
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policies", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("controls", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("regulations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("regulations", "deleted_at")
    op.drop_column("controls", "deleted_at")
    op.drop_column("policies", "deleted_at")

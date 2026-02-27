"""Add cohort_minimum_size column to engagements table.

Revision ID: 064
Revises: 063
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engagements",
        sa.Column("cohort_minimum_size", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("engagements", "cohort_minimum_size")

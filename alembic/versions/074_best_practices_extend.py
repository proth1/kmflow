"""Add title and maturity_level_applicable to best_practices.

Revision ID: 074
Revises: 073
Create Date: 2026-02-27

Story #363: Best practices library enhancements.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("best_practices", sa.Column("title", sa.String(512), server_default="", nullable=False))
    op.add_column("best_practices", sa.Column("maturity_level_applicable", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("best_practices", "maturity_level_applicable")
    op.drop_column("best_practices", "title")

"""Add quality_weights JSONB column to engagements for configurable scoring weights.

Revision ID: 037
Revises: 036
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "037"
down_revision: str | None = "036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("engagements", sa.Column("quality_weights", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("engagements", "quality_weights")

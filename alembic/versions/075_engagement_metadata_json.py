"""Add metadata_json to engagements.

Revision ID: 075
Revises: 074
Create Date: 2026-02-27

Story #363: Engagement-level metadata for client metrics and benchmarking.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engagements", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("engagements", "metadata_json")

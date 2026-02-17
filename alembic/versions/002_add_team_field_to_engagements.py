"""Add team JSON field to engagements table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "engagements",
        sa.Column("team", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("engagements", "team")

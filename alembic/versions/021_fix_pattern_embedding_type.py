"""Fix pattern_library_entries embedding column type from LargeBinary to Vector(768).

Revision ID: 021
Revises: 020
Create Date: 2026-02-20
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Convert LargeBinary to Vector(768)
    op.alter_column(
        "pattern_library_entries",
        "embedding",
        type_=Vector(768),
        postgresql_using="embedding::vector(768)",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "pattern_library_entries",
        "embedding",
        type_=sa.LargeBinary(),
        existing_nullable=True,
    )

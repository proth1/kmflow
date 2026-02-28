"""Add conflict_detail and resolution_hint columns to conflict_objects.

Revision ID: 047
Revises: 046
Create Date: 2026-02-27

Supports Story #375: Rule and Existence Conflict Detection with
Temporal Resolution via Effective Dates.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conflict_objects", sa.Column("conflict_detail", JSON, nullable=True))
    op.add_column("conflict_objects", sa.Column("resolution_hint", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("conflict_objects", "resolution_hint")
    op.drop_column("conflict_objects", "conflict_detail")

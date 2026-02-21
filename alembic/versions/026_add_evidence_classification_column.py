"""Add classification column to evidence_items.

Revision ID: 026
Revises: 025
Create Date: 2026-02-20

Adds a DataClassification enum column to evidence_items so that evidence
can be filtered by sensitivity level (public, internal, confidential,
restricted). Defaults to 'internal'.
"""

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # The DataClassification enum type already exists in the DB (used by
    # data_catalog_entries). Just add the column referencing it.
    op.add_column(
        "evidence_items",
        sa.Column(
            "classification",
            sa.Enum(
                "public", "internal", "confidential", "restricted",
                name="dataclassification",
                create_type=False,
            ),
            nullable=False,
            server_default="internal",
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "classification")

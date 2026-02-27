"""Add resolution_details, classified_at, classifier_version to conflict_objects.

Revision ID: 048
Revises: 047
Create Date: 2026-02-27

Supports Story #384: Three-Way Distinction Classifier.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conflict_objects", sa.Column("resolution_details", JSON, nullable=True))
    op.add_column("conflict_objects", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conflict_objects", sa.Column("classifier_version", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("conflict_objects", "classifier_version")
    op.drop_column("conflict_objects", "classified_at")
    op.drop_column("conflict_objects", "resolution_details")

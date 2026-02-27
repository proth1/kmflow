"""Add resolver_id, assigned_to to conflict_objects.

Revision ID: 049
Revises: 048
Create Date: 2026-02-27

Supports Story #388: Disagreement Resolution Workflow.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conflict_objects", sa.Column("resolver_id", UUID(as_uuid=True), nullable=True))
    op.add_column("conflict_objects", sa.Column("assigned_to", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("conflict_objects", "assigned_to")
    op.drop_column("conflict_objects", "resolver_id")

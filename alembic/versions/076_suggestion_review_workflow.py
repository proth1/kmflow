"""Add suggestion review workflow columns.

Revision ID: 076
Revises: 075
Create Date: 2026-02-27

Story #379: Suggestion review workflow — ACCEPT/MODIFY/REJECT with traceability.

AlternativeSuggestion gains: modified_content, disposed_at, disposed_by_user_id
ScenarioModification gains: template_source, suggestion_id, original_suggestion_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

# revision identifiers
revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AlternativeSuggestion extensions
    op.add_column("alternative_suggestions", sa.Column("modified_content", JSON(), nullable=True))
    op.add_column(
        "alternative_suggestions",
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alternative_suggestions",
        sa.Column("disposed_by_user_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_alt_suggestions_disposed_by",
        "alternative_suggestions",
        "users",
        ["disposed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ScenarioModification extensions
    op.add_column("scenario_modifications", sa.Column("template_source", sa.String(100), nullable=True))
    op.add_column(
        "scenario_modifications",
        sa.Column("suggestion_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "scenario_modifications",
        sa.Column("original_suggestion_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scenario_mod_suggestion",
        "scenario_modifications",
        "alternative_suggestions",
        ["suggestion_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scenario_mod_original_suggestion",
        "scenario_modifications",
        "alternative_suggestions",
        ["original_suggestion_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_scenario_mod_original_suggestion", "scenario_modifications", type_="foreignkey")
    op.drop_constraint("fk_scenario_mod_suggestion", "scenario_modifications", type_="foreignkey")
    op.drop_column("scenario_modifications", "original_suggestion_id")
    op.drop_column("scenario_modifications", "suggestion_id")
    op.drop_column("scenario_modifications", "template_source")

    op.drop_constraint("fk_alt_suggestions_disposed_by", "alternative_suggestions", type_="foreignkey")
    op.drop_column("alternative_suggestions", "disposed_by_user_id")
    op.drop_column("alternative_suggestions", "disposed_at")
    op.drop_column("alternative_suggestions", "modified_content")

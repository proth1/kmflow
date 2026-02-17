"""Create POV (Process Point of View) tables.

Tables: process_models, process_elements, contradictions, evidence_gaps.

Revision ID: 006
Revises: 004
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Create enum types --
    op.execute(
        "CREATE TYPE processmodelstatus AS ENUM ('generating', 'completed', 'failed')"
    )
    op.execute(
        "CREATE TYPE processelementtype AS ENUM "
        "('activity', 'gateway', 'event', 'role', 'system', 'document')"
    )
    op.execute(
        "CREATE TYPE corroborationlevel AS ENUM ('strongly', 'moderately', 'weakly')"
    )
    op.execute("CREATE TYPE gaptype AS ENUM ('missing_data', 'weak_evidence', 'single_source')")
    op.execute("CREATE TYPE gapseverity AS ENUM ('high', 'medium', 'low')")

    # -- Create process_models table --
    op.create_table(
        "process_models",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scope", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "generating",
                "completed",
                "failed",
                name="processmodelstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="generating",
        ),
        sa.Column(
            "confidence_score", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("bpmn_xml", sa.Text(), nullable=True),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "contradiction_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_by",
            sa.String(255),
            nullable=False,
            server_default="lcd_algorithm",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_process_models_engagement_id", "process_models", ["engagement_id"]
    )

    # -- Create process_elements table --
    op.create_table(
        "process_elements",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "model_id",
            sa.UUID(),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "element_type",
            sa.Enum(
                "activity",
                "gateway",
                "event",
                "role",
                "system",
                "document",
                name="processelementtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column(
            "confidence_score", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "triangulation_score", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "corroboration_level",
            sa.Enum(
                "strongly",
                "moderately",
                "weakly",
                name="corroborationlevel",
                create_type=False,
            ),
            nullable=False,
            server_default="weakly",
        ),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_ids", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_process_elements_model_id", "process_elements", ["model_id"]
    )

    # -- Create contradictions table --
    op.create_table(
        "contradictions",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "model_id",
            sa.UUID(),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("element_name", sa.String(512), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("values", sa.JSON(), nullable=True),
        sa.Column("resolution_value", sa.Text(), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_contradictions_model_id", "contradictions", ["model_id"])

    # -- Create evidence_gaps table --
    op.create_table(
        "evidence_gaps",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "model_id",
            sa.UUID(),
            sa.ForeignKey("process_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gap_type",
            sa.Enum(
                "missing_data",
                "weak_evidence",
                "single_source",
                name="gaptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("high", "medium", "low", name="gapseverity", create_type=False),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column(
            "related_element_id",
            sa.UUID(),
            sa.ForeignKey("process_elements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_evidence_gaps_model_id", "evidence_gaps", ["model_id"])


def downgrade() -> None:
    op.drop_table("evidence_gaps")
    op.drop_table("contradictions")
    op.drop_table("process_elements")
    op.drop_table("process_models")

    op.execute("DROP TYPE IF EXISTS gapseverity")
    op.execute("DROP TYPE IF EXISTS gaptype")
    op.execute("DROP TYPE IF EXISTS corroborationlevel")
    op.execute("DROP TYPE IF EXISTS processelementtype")
    op.execute("DROP TYPE IF EXISTS processmodelstatus")

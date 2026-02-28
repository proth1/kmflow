"""Add three-dimensional confidence model columns to process_elements.

Adds evidence_grade, brightness_classification, and mvc_threshold_passed
columns per PRD v2.1 Section 6.3 confidence model.

Revision ID: 031
Revises: 030
Create Date: 2026-02-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVIDENCE_GRADE = sa.Enum("A", "B", "C", "D", "U", name="evidencegrade")
_BRIGHTNESS = sa.Enum("bright", "dim", "dark", name="brightnessclassification")


def upgrade() -> None:
    _EVIDENCE_GRADE.create(op.get_bind(), checkfirst=True)
    _BRIGHTNESS.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "process_elements",
        sa.Column("evidence_grade", _EVIDENCE_GRADE, nullable=False, server_default="U"),
    )
    op.add_column(
        "process_elements",
        sa.Column("brightness_classification", _BRIGHTNESS, nullable=False, server_default="dark"),
    )
    op.add_column(
        "process_elements",
        sa.Column("mvc_threshold_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("process_elements", "mvc_threshold_passed")
    op.drop_column("process_elements", "brightness_classification")
    op.drop_column("process_elements", "evidence_grade")

    _BRIGHTNESS.drop(op.get_bind(), checkfirst=True)
    _EVIDENCE_GRADE.drop(op.get_bind(), checkfirst=True)

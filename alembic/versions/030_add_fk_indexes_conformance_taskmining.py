"""Add FK indexes for conformance and taskmining models.

Adds B-tree indexes on foreign key columns that were missing indexes:
- conformance_results.pov_model_id
- task_mining_actions.evidence_item_id

Revision ID: 030
Revises: 029
Create Date: 2026-02-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_conformance_results_pov_model_id", "conformance_results", "pov_model_id"),
    ("ix_task_mining_actions_evidence_item_id", "task_mining_actions", "evidence_item_id"),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name)

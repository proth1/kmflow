"""Add missing indexes on ForeignKey columns for query performance.

14 FK columns across 6 model files lacked B-tree indexes, causing
potential full table scans during joins and filtered queries.

Revision ID: 029
Revises: 028
Create Date: 2026-02-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index_name, table_name, column_name)
_INDEXES = [
    # evidence.py
    ("ix_evidence_items_lineage_id", "evidence_items", "lineage_id"),
    ("ix_evidence_items_duplicate_of_id", "evidence_items", "duplicate_of_id"),
    ("ix_evidence_lineage_parent_version_id", "evidence_lineage", "parent_version_id"),
    # engagement.py
    ("ix_shelf_data_request_items_matched_evidence_id", "shelf_data_request_items", "matched_evidence_id"),
    # pov.py
    ("ix_evidence_gaps_related_element_id", "evidence_gaps", "related_element_id"),
    # monitoring.py
    ("ix_process_baselines_process_model_id", "process_baselines", "process_model_id"),
    ("ix_monitoring_jobs_connection_id", "monitoring_jobs", "connection_id"),
    ("ix_monitoring_jobs_baseline_id", "monitoring_jobs", "baseline_id"),
    ("ix_process_deviations_baseline_id", "process_deviations", "baseline_id"),
    # governance.py
    ("ix_policies_source_evidence_id", "policies", "source_evidence_id"),
    # simulation.py
    ("ix_simulation_scenarios_process_model_id_2", "simulation_scenarios", "process_model_id"),
    ("ix_epistemic_actions_shelf_request_id", "epistemic_actions", "shelf_request_id"),
    ("ix_financial_assumptions_source_evidence_id", "financial_assumptions", "source_evidence_id"),
    ("ix_alternative_suggestions_created_by", "alternative_suggestions", "created_by"),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name)

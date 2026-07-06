"""Add missing indexes to pool-hub tables

Adds indexes on frequently-filtered columns in match_results, feedback,
sla_metrics, and sla_violations tables.

Revision ID: c3b2d6e7f8a9
Revises: b2a1c4d5e6f7
Create Date: 2026-07-05 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3b2d6e7f8a9"
down_revision = "b2a1c4d5e6f7"
branch_labels = None
depends_on = None


# (index_name, table_name, column_name) for single-column indexes.
_INDEXES: list[tuple[str, str, str]] = [
    ("ix_match_results_miner_id", "match_results", "miner_id"),
    ("ix_match_results_created_at", "match_results", "created_at"),
    ("ix_feedback_miner_id", "feedback", "miner_id"),
    ("ix_feedback_created_at", "feedback", "created_at"),
    ("ix_sla_metrics_miner_id", "sla_metrics", "miner_id"),
    ("ix_sla_violations_miner_id", "sla_violations", "miner_id"),
    ("ix_sla_violations_created_at", "sla_violations", "created_at"),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name], if_not_exists=True)


def downgrade() -> None:
    for index_name, _table_name, _column_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=_table_name)

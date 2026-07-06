"""Migrate pool-hub monetary columns from Float to Numeric

Changes Float columns to Numeric(20, 8) for precise decimal arithmetic,
preventing rounding errors in miner base prices, match result prices, and
feedback token spending.

Affected tables:
- ``miners``: base_price
- ``match_results``: price
- ``feedback``: tokens_spent

Non-monetary float fields (gpu_vram_gb, ram_gb, trust_score, mem_free_gb,
uptime_pct, score, metric_value, threshold, capacity_utilization_pct) are
left as Float — they are specs/metrics, not monetary values.

Revision ID: d4c3e7f8a9b0
Revises: c3b2d6e7f8a9
Create Date: 2026-07-06 00:00:03.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4c3e7f8a9b0"
down_revision = "c3b2d6e7f8a9"
branch_labels = None
depends_on = None


# (table, column, nullable) for each migration.
_COLUMNS: list[tuple[str, str, bool]] = [
    # miners
    ("miners", "base_price", False),
    # match_results
    ("match_results", "price", True),
    # feedback
    ("feedback", "tokens_spent", True),
]


def upgrade() -> None:
    for table, column, nullable in _COLUMNS:
        op.alter_column(
            table_name=table,
            column_name=column,
            type_=sa.Numeric(20, 8),
            existing_type=sa.Float(),
            nullable=nullable,
        )


def downgrade() -> None:
    for table, column, nullable in _COLUMNS:
        op.alter_column(
            table_name=table,
            column_name=column,
            type_=sa.Float(),
            existing_type=sa.Numeric(20, 8),
            nullable=nullable,
        )

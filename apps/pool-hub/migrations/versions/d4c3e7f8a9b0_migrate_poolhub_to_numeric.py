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


def _convert(to_type: sa.types.TypeEngine, from_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    for table, column, nullable in _COLUMNS:
        # SQLite has no `ALTER COLUMN`/`SET NOT NULL` at all, so it takes the
        # batch copy-and-rebuild path; PostgreSQL keeps the native ALTER the
        # bare op.alter_column used to emit. The rebuild does not carry
        # separately-created indexes across, so snapshot and restore them.
        inspector = sa.inspect(bind)
        indexes = inspector.get_indexes(table) if sqlite else []
        with op.batch_alter_table(table, recreate="always" if sqlite else "auto") as batch_op:
            batch_op.alter_column(
                column_name=column,
                type_=to_type,
                existing_type=from_type,
                nullable=nullable,
            )
        if sqlite:
            surviving = {i["name"] for i in sa.inspect(bind).get_indexes(table)}
            for index in indexes:
                if index["name"] not in surviving:
                    op.create_index(
                        index["name"],
                        table,
                        index["column_names"],
                        unique=index["unique"],
                        if_not_exists=True,
                    )


def upgrade() -> None:
    _convert(sa.Numeric(20, 8), sa.Float())


def downgrade() -> None:
    _convert(sa.Float(), sa.Numeric(20, 8))

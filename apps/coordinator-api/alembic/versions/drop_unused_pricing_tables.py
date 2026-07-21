"""drop unused pricing tables

Drop legacy marketplace pricing tables that are no longer used:
- pricing_optimizations
- pricing_alerts
- pricing_rules
- price_forecast

Revision ID: a0288b36720c
Revises: e9cf23ae4640
Create Date: 2026-07-21 20:19:09.087406+00:00

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a0288b36720c"
down_revision: str | Sequence[str] | None = "add_query_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the unused pricing tables."""
    for table in ("pricing_optimizations", "pricing_alerts", "pricing_rules", "price_forecast"):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    """Downgrade is a no-op; the tables are obsolete and not recreated."""
    pass

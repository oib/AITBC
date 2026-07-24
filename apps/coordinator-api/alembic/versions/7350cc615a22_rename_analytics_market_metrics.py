"""rename analytics market metrics

Rename the analytics ``market_metrics`` table to ``analytics_market_metrics``
to resolve the conflict with the trading ``market_metrics`` table defined in
``apps/coordinator-api/src/coordinator_api/contexts/trading/domain/pricing_models.py``.

Revision ID: 7350cc615a22
Revises: add_developer_platform
Create Date: 2026-07-22 15:55:56.926522+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "7350cc615a22"
down_revision: str | Sequence[str] | None = "add_developer_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(bind: sa.engine.Engine, table_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return table_name in sa.inspect(bind).get_table_names()


def _has_column(bind: sa.engine.Engine, table_name: str, column_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    columns = {c["name"] for c in sa.inspect(bind).get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    """Create or rename the analytics market metrics table."""
    bind = op.get_bind()

    if _has_table(bind, "analytics_market_metrics"):
        return

    # If the old analytics table still exists, rename it.
    if _has_column(bind, "market_metrics", "recorded_at"):
        op.rename_table("market_metrics", "analytics_market_metrics")
        return

    # Otherwise create the analytics table from scratch.
    op.create_table(
        "analytics_market_metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("metric_type", sa.String(), nullable=False),
        sa.Column("period_type", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("previous_value", sa.Float(), nullable=True),
        sa.Column("change_percentage", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=False, server_default=""),
        sa.Column("category", sa.String(), nullable=False, server_default="general"),
        sa.Column("subcategory", sa.String(), nullable=False, server_default=""),
        sa.Column("geographic_region", sa.String(), nullable=True),
        sa.Column("agent_tier", sa.String(), nullable=True),
        sa.Column("trade_type", sa.String(), nullable=True),
        sa.Column("metric_meta_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comparisons", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_market_metrics_metric_name",
        "analytics_market_metrics",
        ["metric_name"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop or rename back the analytics market metrics table."""
    bind = op.get_bind()

    if not _has_table(bind, "analytics_market_metrics"):
        return

    # If there is no trading market_metrics table, the analytics table was
    # renamed from market_metrics, so rename it back.
    if not _has_table(bind, "market_metrics"):
        op.rename_table("analytics_market_metrics", "market_metrics")
        return

    # Otherwise we created the analytics table separately; drop it.
    op.drop_index(
        "ix_analytics_market_metrics_metric_name",
        table_name="analytics_market_metrics",
        if_exists=True,
    )
    op.drop_table("analytics_market_metrics", if_exists=True)

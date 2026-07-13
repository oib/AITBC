"""Migrate trading monetary columns from Float to Numeric

Changes Float columns to Numeric(20, 8) for precise decimal arithmetic,
preventing rounding errors in trade agreements, settlements, pricing
history, provider strategies, market metrics, forecasts, and analytics.

Affected tables:
- ``trade_agreements``: total_price
- ``trade_settlements``: total_amount, platform_fee, processing_fee, gas_fee, net_amount_seller
- ``trading_analytics``: total_trade_volume, average_trade_value, total_platform_fees
- ``pricing_history``: price, base_price, price_change
- ``provider_pricing_strategies``: min_price, max_price, total_revenue_impact
- ``market_metrics``: average_price, average_competitor_price, price_spread, trading_volume
- ``price_forecasts``: average_forecast_price

JSON columns (budget_range, price_range, pricing_factors, competitor_prices,
custom_metrics, price_range_forecast, impact dicts) are not migrated — they
store arbitrary JSON and the type annotations were relaxed to ``dict[str, Any]``
/ ``list[Any]`` to accept Decimal-serializable values.

Revision ID: migrate_trading_to_numeric
Revises: migrate_wallet_to_numeric
Create Date: 2026-07-06 00:00:01.000000

"""

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "migrate_trading_to_numeric"
down_revision = "migrate_wallet_to_numeric"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


# (table, column, nullable) for each migration.
_COLUMNS: list[tuple[str, str, bool]] = [
    # trade_agreements
    ("trade_agreements", "total_price", False),
    # trade_settlements
    ("trade_settlements", "total_amount", False),
    ("trade_settlements", "platform_fee", False),
    ("trade_settlements", "processing_fee", False),
    ("trade_settlements", "gas_fee", False),
    ("trade_settlements", "net_amount_seller", False),
    # trading_analytics
    ("trading_analytics", "total_trade_volume", False),
    ("trading_analytics", "average_trade_value", False),
    ("trading_analytics", "total_platform_fees", False),
    # pricing_history
    ("pricing_history", "price", False),
    ("pricing_history", "base_price", False),
    ("pricing_history", "price_change", True),
    # provider_pricing_strategies
    ("provider_pricing_strategies", "min_price", True),
    ("provider_pricing_strategies", "max_price", True),
    ("provider_pricing_strategies", "total_revenue_impact", False),
    # market_metrics
    ("market_metrics", "average_price", False),
    ("market_metrics", "average_competitor_price", False),
    ("market_metrics", "price_spread", False),
    ("market_metrics", "trading_volume", False),
    # price_forecasts
    ("price_forecasts", "average_forecast_price", False),
]


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, nullable in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=sa.Numeric(20, 8),
                    existing_type=sa.Float(),
                    nullable=nullable,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=sa.Numeric(20, 8),
                existing_type=sa.Float(),
                nullable=nullable,
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, nullable in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=sa.Float(),
                    existing_type=sa.Numeric(20, 8),
                    nullable=nullable,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=sa.Float(),
                existing_type=sa.Numeric(20, 8),
                nullable=nullable,
            )

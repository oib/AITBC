"""Migrate marketplace monetary columns from Float to Numeric

Changes Float columns to Numeric(20, 8) for precise decimal arithmetic,
preventing rounding errors in marketplace offers, bids, software services,
global marketplace offers, and transactions.

Affected tables:
- ``marketplaceoffer``: price, price_per_hour
- ``marketplace_bid``: price
- ``softwareservice``: price
- ``global_marketplace_offers``: base_price, cross_chain_fee
- ``global_marketplace_transactions``: unit_price, total_amount, cross_chain_fee

JSON columns (price_per_region, cross_chain_pricing, regional_fees) are not
migrated — they store arbitrary JSON and the type annotations were relaxed
to ``dict[str, Any]`` to accept Decimal-serializable values.

Revision ID: migrate_marketplace_to_numeric
Revises: migrate_trading_to_numeric
Create Date: 2026-07-06 00:00:02.000000

"""

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "migrate_marketplace_to_numeric"
down_revision = "migrate_trading_to_numeric"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


# (table, column, nullable) for each migration.
_COLUMNS: list[tuple[str, str, bool]] = [
    # marketplaceoffer
    ("marketplaceoffer", "price", False),
    ("marketplaceoffer", "price_per_hour", True),
    # marketplace_bid
    ("marketplace_bid", "price", False),
    # softwareservice
    ("softwareservice", "price", False),
    # global_marketplace_offers
    ("global_marketplace_offers", "base_price", False),
    # global_marketplace_transactions
    ("global_marketplace_transactions", "unit_price", False),
    ("global_marketplace_transactions", "total_amount", False),
    ("global_marketplace_transactions", "cross_chain_fee", False),
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

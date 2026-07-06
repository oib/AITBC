"""Migrate wallet monetary columns from Float to Numeric

Changes Float columns to Numeric(20, 8) for precise decimal arithmetic,
preventing rounding errors in wallet balances and transaction values.

Affected tables (in the ``aitbc`` schema):
- ``token_balance``: balance
- ``wallet_transaction``: value, gas_price

This migration also merges the two branches that diverged from
``add_query_performance_indexes`` (``migrate_usage_records_to_numeric``
and ``drop_unused_pricing_tables``).

Revision ID: migrate_wallet_to_numeric
Revises: migrate_usage_records_to_numeric, drop_unused_pricing_tables
Create Date: 2026-07-06 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "migrate_wallet_to_numeric"
down_revision = ("migrate_usage_records_to_numeric", "drop_unused_pricing_tables")
branch_labels = None
depends_on = None


# (table, column, nullable) for each migration.
_COLUMNS: list[tuple[str, str, bool]] = [
    # token_balance
    ("token_balance", "balance", False),
    # wallet_transaction
    ("wallet_transaction", "value", False),
    ("wallet_transaction", "gas_price", True),
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

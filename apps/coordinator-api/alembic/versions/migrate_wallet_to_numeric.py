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

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "migrate_wallet_to_numeric"
down_revision = "drop_unused_pricing_tables"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


# (table, column, nullable) for each migration.
_COLUMNS: list[tuple[str, str, bool]] = [
    # token_balance
    ("token_balance", "balance", False),
    # wallet_transaction
    ("wallet_transaction", "value", False),
    ("wallet_transaction", "gas_price", True),
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

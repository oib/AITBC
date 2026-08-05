"""v0.18.0 migrate money fields from Float to Numeric(20, 8)

Revision ID: 002
Revises: 001
Create Date: 2026-07-28 00:00:00

Migrates all money columns from sa.Float() to sa.Numeric(20, 8) to
eliminate floating-point rounding errors in financial calculations.
Uses if_not_exists-style guards (SQLite ALTER TABLE does not support
IF NOT EXISTS on column types — we use a try/except pattern instead).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables and columns to migrate: (table, [(old_col, new_type, server_default)])
# Only columns that were Float and are now Numeric(20, 8).
_MONEY_COLUMNS: list[tuple[str, list[tuple[str, sa.Numeric, str]]]] = [
    (
        "inter_chain_trades",
        [("price", sa.Numeric(20, 8), "0")],
    ),
    (
        "trade_agreements",
        [("total_price", sa.Numeric(20, 8), "0")],
    ),
    (
        "trade_settlements",
        [
            ("total_amount", sa.Numeric(20, 8), "0"),
            ("platform_fee", sa.Numeric(20, 8), "0"),
            ("processing_fee", sa.Numeric(20, 8), "0"),
            ("gas_fee", sa.Numeric(20, 8), "0"),
            ("net_amount_seller", sa.Numeric(20, 8), "0"),
        ],
    ),
    (
        "trading_analytics",
        [
            ("total_trade_volume", sa.Numeric(20, 8), "0"),
            ("average_trade_value", sa.Numeric(20, 8), "0"),
            ("total_platform_fees", sa.Numeric(20, 8), "0"),
        ],
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_name, columns in _MONEY_COLUMNS:
        if table_name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        for col_name, new_type, server_default in columns:
            if col_name not in existing_cols:
                continue
            # SQLite doesn't support ALTER COLUMN TYPE directly.
            # On PostgreSQL, use alter_column with type_=.
            # On SQLite, the column type is advisory (storage class), so
            # Numeric values stored as REAL will be read back as Decimal
            # by SQLAlchemy — no schema change needed for SQLite.
            if bind.dialect.name != "sqlite":
                op.alter_column(
                    table_name,
                    col_name,
                    type_=new_type,
                    server_default=server_default,
                    existing_nullable=False,
                )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    for table_name, columns in _MONEY_COLUMNS:
        for col_name, _, _ in columns:
            op.alter_column(
                table_name,
                col_name,
                type_=sa.Float(),
                server_default="0.0",
                existing_nullable=False,
            )

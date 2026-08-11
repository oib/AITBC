"""v23_gpu_money_columns_to_numeric

The GPU service's first migration. Three Float money columns to Numeric(20, 8):

    gpu_registry.price_per_hour            34 rows in the deployed database
    consumer_gpu_profiles.market_price_usd  2 rows
    gpu_bookings.total_cost                 0 rows

The models have declared these ``Decimal`` with ``max_digits=20, decimal_places=8`` since the
V23 money migration, but this app had no Alembic and ``init_db`` only calls
``SQLModel.metadata.create_all``, which adds missing *tables* and never alters existing
columns. So the declaration and the deployed schema disagreed, and the 34 live prices in
``gpu_registry`` were still being stored as binary floats.

SQLite cannot ALTER a column type, hence ``batch_alter_table(recreate="always")``: the table
is rebuilt, rows copied, original dropped. ``_table_exists``/``_column_exists`` keep this
runnable against a database created before or after any given table existed -- a fresh
``create_all`` database already has these columns as Numeric, and the guards make the
migration a no-op there rather than an error.

``upgrade`` is lossless: every float that reaches Numeric(20, 8) keeps the value SQLite hands
back. ``downgrade`` is not -- it re-introduces binary representation error for any value that
is not exactly representable. It exists so the revision can be stepped back, not because
stepping back is free.

Revision ID: b8f3a2c91d04
Revises:
Create Date: 2026-08-11 21:10:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "b8f3a2c91d04"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)

# (table, column, nullable)
_COLUMNS: list[tuple[str, str, bool]] = [
    ("gpu_registry", "price_per_hour", False),
    ("consumer_gpu_profiles", "market_price_usd", True),
    ("gpu_bookings", "total_cost", False),
]


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    if context.is_offline_mode():
        return True
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


def _convert(to_type: sa.types.TypeEngine, from_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite" and not context.is_offline_mode()
    for table, column, nullable in _COLUMNS:
        if not _table_exists(bind, table) or not _column_exists(bind, table, column):
            continue
        if sqlite:
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=to_type,
                    existing_type=from_type,
                    nullable=nullable,
                )
        else:
            extra = {}
            if to_type is MONEY:
                extra["postgresql_using"] = f"{column}::numeric(20,8)"
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=to_type,
                existing_type=from_type,
                nullable=nullable,
                **extra,
            )


def upgrade() -> None:
    _convert(MONEY, sa.Float())


def downgrade() -> None:
    _convert(sa.Float(), MONEY)

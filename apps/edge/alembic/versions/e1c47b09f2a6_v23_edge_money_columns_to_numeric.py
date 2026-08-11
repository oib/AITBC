"""v23_edge_money_columns_to_numeric

The Edge service's first migration. Four Float money columns to Numeric(20, 8):

    gpu_listings.price_per_hour
    marketplaceoffer.price
    marketplaceoffer.price_per_hour
    marketplace_bid.price

All four are empty in the deployed database, so nothing moves -- but the schema was wrong,
and a schema that is only right while the table is empty is not right. ``GPUListing`` has
declared ``price_per_hour`` as ``Decimal`` since the V23 money migration; the other three
come from ``packages/aitbc-shared``'s marketplace models, which this app registers on the
same ``SQLModel.metadata``. The same tables are already ``Numeric(20, 8)`` in the GPU
service's database, so this migration also brings the two into agreement.

The cause is the same one V23-47 fixes for both apps: ``init_db`` calls
``SQLModel.metadata.create_all``, which adds missing *tables* and never alters existing
columns, and there was no Alembic to do it instead.

See ``apps/gpu/alembic/versions/b8f3a2c91d04`` for why ``batch_alter_table(recreate="always")``
and the existence guards are needed. ``upgrade`` is lossless; ``downgrade`` re-introduces
binary representation error and exists so the revision can be stepped back, not because
stepping back is free.

Revision ID: e1c47b09f2a6
Revises:
Create Date: 2026-08-11 21:15:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "e1c47b09f2a6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)

# (table, column, nullable)
_COLUMNS: list[tuple[str, str, bool]] = [
    ("gpu_listings", "price_per_hour", False),
    ("marketplaceoffer", "price", False),
    ("marketplaceoffer", "price_per_hour", True),
    ("marketplace_bid", "price", False),
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

"""v23_gpu_resource_money_to_numeric

Migrate the two money columns on the on-chain GPU resource tables from Float to
Numeric(20, 8): ``gpu_registration.price_per_hour`` and ``gpu_allocation.total_cost``.

Both are written by ``rpc/gpu_resources.py``, which takes them straight from a request
body and stores them. Neither goes through the mempool, so unlike ``payment`` in
``rpc/ai_services.py`` or ``price`` in ``rpc/marketplace.py`` this is not part of any
signed or hashed payload -- those two are left as ``float`` deliberately and carry a
``# not-money:`` marker saying why.

Revision ID: d4e8b91c0a37
Revises: 459d59e234e4
Create Date: 2026-08-11 14:40:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "d4e8b91c0a37"
down_revision: str | Sequence[str] | None = "459d59e234e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)

# (table, column, nullable)
_COLUMNS: list[tuple[str, str, bool]] = [
    ("gpu_registration", "price_per_hour", False),
    ("gpu_allocation", "total_cost", False),
]


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _convert(to_type: sa.types.TypeEngine, from_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite" and not context.is_offline_mode()
    for table, column, nullable in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if sqlite:
            # SQLite cannot ALTER COLUMN; batch_alter_table rebuilds the table.
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
    """Reversible, but not lossless: this puts the values back into binary floating point."""
    _convert(sa.Float(), MONEY)

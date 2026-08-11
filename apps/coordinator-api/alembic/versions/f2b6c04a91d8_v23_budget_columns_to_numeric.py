"""v23_budget_columns_to_numeric

Three more Float money columns to Numeric(20, 8), missed by ``c7d1f4a9e230``:

    regional_councils.budget_allocation
    regional_hub.budget_allocation
    regional_hub.spent_budget

They were missed because ``scripts/lint/no_float_money.py`` did not know the words
``budget`` or ``spent``. A budget allocation is an amount of currency, and ``spent_budget``
is how much of it has been paid out -- the guard reported this app at zero while both sat
one row away from ``BountyTask.reward_amount``, which is already ``Numeric(20, 8)``, and in
the same file as ``total_balance`` and ``allocated_funds``, which are too.

Both tables exist in the deployed coordinator database and both are empty, so the
conversion moves no data. See ``c7d1f4a9e230`` for why ``_table_exists`` and
``batch_alter_table(recreate="always")`` are needed; the same reasoning applies unchanged,
as does the note that ``upgrade`` is lossless and ``downgrade`` is not.

Revision ID: f2b6c04a91d8
Revises: c7d1f4a9e230
Create Date: 2026-08-11 15:05:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "f2b6c04a91d8"
down_revision: str | Sequence[str] | None = "c7d1f4a9e230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    if context.is_offline_mode():
        return True
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


# (table, column, nullable)
_COLUMNS: list[tuple[str, str, bool]] = [
    # regional_councils (governance)
    ("regional_councils", "budget_allocation", False),
    # regional_hub (developer_platform)
    ("regional_hub", "budget_allocation", False),
    ("regional_hub", "spent_budget", False),
]


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

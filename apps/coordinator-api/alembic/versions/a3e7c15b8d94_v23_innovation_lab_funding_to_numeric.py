"""v23_innovation_lab_funding_to_numeric

Two more Float money columns to Numeric(20, 8):

    innovation_labs.funding_goal
    innovation_labs.current_funding

Missed by ``c7d1f4a9e230`` and ``f2b6c04a91d8`` because the guard did not know the word
``funding``. ``InnovationLabService.fund_lab`` does ``lab.current_funding += amount`` and
then compares ``current_funding >= funding_goal`` to decide whether a lab is fully funded --
a threshold comparison on a binary float, which is the shape of bug that funds a lab at
999.9999999999999 out of 1000.

The table exists in the deployed coordinator database and is empty, so nothing moves. See
``c7d1f4a9e230`` for why ``_table_exists`` and ``batch_alter_table(recreate="always")`` are
needed; ``upgrade`` is lossless, ``downgrade`` is not.

Revision ID: a3e7c15b8d94
Revises: f2b6c04a91d8
Create Date: 2026-08-11 17:40:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "a3e7c15b8d94"
down_revision: str | Sequence[str] | None = "f2b6c04a91d8"
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
    ("innovation_labs", "funding_goal", False),
    ("innovation_labs", "current_funding", False),
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

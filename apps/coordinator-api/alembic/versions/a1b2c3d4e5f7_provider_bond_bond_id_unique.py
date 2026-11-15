"""unique partial index on provider_bond.bond_id (#1967)

A chain ``bond_id`` may back exactly one provider: before this, two miners
could bind the same on-chain bond (the wallet was self-declared and
unproven). The index is partial — ``bond_id <> ''`` — because bondless
lock/release rows keep the ``""`` default and must not collide.

Fresh databases already carry the index — 001_initial_migration builds the
schema from SQLModel.metadata.create_all, which now includes it — so the
CREATE is guarded by an inspector check like ``i3j4k5l6m7n8``. In offline
SQL mode there is no bind to inspect, so the historical state is assumed
and the DDL is emitted unconditionally.

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_provider_bond_bond_id"
_TABLE = "provider_bond"


def _index_exists() -> bool:
    """True when the partial unique index is already present."""
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return False
    return any(i["name"] == _INDEX for i in inspector.get_indexes(_TABLE))


def upgrade() -> None:
    if _index_exists():
        return
    op.create_index(
        _INDEX,
        _TABLE,
        ["bond_id"],
        unique=True,
        sqlite_where=sa.text("bond_id <> ''"),
        postgresql_where=sa.text("bond_id <> ''"),
    )


def downgrade() -> None:
    if not _index_exists() and not context.is_offline_mode():
        return
    op.drop_index(_INDEX, table_name=_TABLE)

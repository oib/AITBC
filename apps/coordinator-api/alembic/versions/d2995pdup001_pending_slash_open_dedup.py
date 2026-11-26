"""dedup open pending_bond_slash rows per (job_id, condition)

Revision ID: d2995pdup001
Revises: d2976pslash001
Create Date: 2026-11-26 12:00:00.000000+00:00

#2995 (BOND-SLASH-WINDOW-DUP-1): the sweeper re-detects the same stale job
every pass; without a guard each pass queued another pending_bond_slash row
for the same violation, and every open row would submit its own BOND_SLASH
at window expiry. A partial unique index on (job_id, condition) restricted
to the open statuses (pending/executing) makes the second insert fail at
the DB layer; terminal rows (executed/cancelled/failed) never block a
genuine re-detection.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import context


# revision identifiers, used by Alembic.
revision: str = "d2995pdup001"
down_revision: str | Sequence[str] | None = "d2976pslash001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "pending_bond_slash"
_INDEX = "uq_pending_bond_slash_open_job_condition"
_OPEN_STATUSES = "('pending', 'executing')"


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
        ["job_id", "condition"],
        unique=True,
        sqlite_where=sa.text(f"status IN {_OPEN_STATUSES}"),
        postgresql_where=sa.text(f"status IN {_OPEN_STATUSES}"),
    )


def downgrade() -> None:
    if not _index_exists() and not context.is_offline_mode():
        return
    op.drop_index(_INDEX, table_name=_TABLE)
